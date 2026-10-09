package tofa

import (
	"bytes"
	"context"
	"crypto/rand"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"net"
	"net/http"
	"net/http/httputil"
	"net/url"
	"reflect"
	"strconv"
	"sync"
	"sync/atomic"
	"time"
)

const maxAdapterBody = 16 << 20

type requestAdapter struct {
	endpoint string
	token    string
	server   *http.Server
	cancel   context.CancelFunc
	context  context.Context
	done     chan error
	desktop  atomic.Pointer[desktopRoute]
}

func (a *App) startAdapter(ctx context.Context, project, key, selectedModel, guardian string) (*requestAdapter, error) {
	endpoint := a.Endpoint
	if endpoint == "" {
		endpoint = Endpoint
	}
	upstream, err := url.Parse(endpoint + "/responses")
	if err != nil || upstream.Host == "" || upstream.User != nil || upstream.RawQuery != "" || upstream.Fragment != "" || (upstream.Scheme != "http" && upstream.Scheme != "https") {
		return nil, errors.New("invalid adapter upstream endpoint")
	}
	query := url.Values{"ai_project_id": {project}}
	upstream.RawQuery = query.Encode()
	secret := make([]byte, 32)
	if _, err := rand.Read(secret); err != nil {
		return nil, errors.New("could not generate adapter credential")
	}
	listen := a.Listen
	if listen == nil {
		listen = net.Listen
	}
	listener, err := listen("tcp4", "127.0.0.1:0")
	if err != nil {
		return nil, errors.New("could not start loopback request adapter")
	}
	ctx, cancel := context.WithCancel(ctx)
	adapter := &requestAdapter{endpoint: "http://" + listener.Addr().String(), token: hex.EncodeToString(secret), cancel: cancel, context: ctx, done: make(chan error, 1)}
	var noticeMu sync.Mutex
	notice := func(message string) {
		if selectedModel != "" {
			noticeMu.Lock()
			defer noticeMu.Unlock()
			fmt.Fprintln(a.Out, "Desktop request failed:", message)
		}
	}
	transport := http.DefaultTransport
	if a.HTTP != nil && a.HTTP.Transport != nil {
		transport = a.HTTP.Transport
	}
	proxy := &httputil.ReverseProxy{
		Rewrite: func(request *httputil.ProxyRequest) {
			target := *upstream
			request.Out.URL = &target
			request.Out.Host = upstream.Host
			request.Out.Header = make(http.Header)
			request.Out.Header.Set("Authorization", "Bearer "+key)
			request.Out.Header.Set("Content-Type", "application/json")
			request.Out.Header.Set("Accept", "text/event-stream, application/json")
			request.Out.GetBody = nil
			request.Out.Trailer = nil
			request.Out.TransferEncoding = nil
		},
		Transport:     transport,
		FlushInterval: -1,
		ErrorLog:      log.New(io.Discard, "", 0),
		ErrorHandler: func(writer http.ResponseWriter, request *http.Request, err error) {
			notice("upstream connection failed; request was not retried")
			http.Error(writer, "request adapter: upstream connection failed; request was not retried", http.StatusBadGateway)
		},
		ModifyResponse: func(response *http.Response) error {
			if response.StatusCode >= 400 {
				notice(fmt.Sprintf("upstream HTTP %d", response.StatusCode))
			}
			if response.StatusCode >= 300 && response.StatusCode < 400 {
				return errors.New("upstream redirect rejected")
			}
			return nil
		},
	}
	var approvalNotice sync.Once
	var titleNotice sync.Once
	var reasoningNotice sync.Once
	var imageLimitNotice sync.Once
	imageNotices := map[string]bool{}
	adapter.server = &http.Server{
		ReadHeaderTimeout: 5 * time.Second,
		ReadTimeout:       30 * time.Second,
		IdleTimeout:       30 * time.Second,
		MaxHeaderBytes:    32 << 10,
		ErrorLog:          log.New(io.Discard, "", 0),
		BaseContext:       func(net.Listener) context.Context { return ctx },
		Handler: http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
			if subtle.ConstantTimeCompare([]byte(request.Header.Get("Authorization")), []byte("Bearer "+adapter.token)) != 1 {
				http.Error(writer, "request adapter: unauthorized", http.StatusUnauthorized)
				return
			}
			if route := adapter.desktop.Load(); route != nil && request.Method == http.MethodGet && request.URL.Path == "/desktop-launch" && request.URL.RawPath == "" && request.URL.RawQuery == "" {
				if route.ready != nil {
					pid, _ := strconv.Atoi(request.Header.Get("X-Tofa-Parent-Pid"))
					select {
					case route.claim <- pid:
					default:
					}
					select {
					case <-route.ready:
					case <-request.Context().Done():
						return
					case <-ctx.Done():
						http.Error(writer, "desktop launch cancelled", http.StatusServiceUnavailable)
						return
					}
				}
				if value := request.Header.Get("X-Tofa-Main-Engine-Pid"); value != "" {
					pid, err := strconv.ParseInt(value, 10, 32)
					if err != nil || pid <= 0 || route.mainPID == nil || (!route.mainPID.CompareAndSwap(0, pid) && route.mainPID.Load() != pid) {
						http.Error(writer, "desktop main engine registration conflicts with this launch", http.StatusConflict)
						return
					}
				}
				writer.Header().Set("Content-Type", "application/json")
				writer.Header().Set("Cache-Control", "no-store")
				json.NewEncoder(writer).Encode(route)
				return
			}
			if request.URL.Path != "/responses" || request.URL.RawPath != "" || request.URL.RawQuery != "" {
				notice("unsupported route (including auxiliary/compaction endpoints)")
				http.Error(writer, "request adapter: unsupported route", http.StatusNotFound)
				return
			}
			if request.Method != http.MethodPost {
				writer.Header().Set("Allow", http.MethodPost)
				http.Error(writer, "request adapter: POST required", http.StatusMethodNotAllowed)
				return
			}
			if route := adapter.desktop.Load(); route != nil && route.ready != nil {
				select {
				case <-route.ready:
				default:
					http.Error(writer, "desktop ownership and routing are not yet qualified", http.StatusServiceUnavailable)
					return
				}
			}
			if request.Header.Get("Content-Encoding") != "" && request.Header.Get("Content-Encoding") != "identity" {
				http.Error(writer, "request adapter: encoded requests are unsupported", http.StatusUnsupportedMediaType)
				return
			}
			body, err := io.ReadAll(http.MaxBytesReader(writer, request.Body, maxAdapterBody))
			if err != nil {
				var tooLarge *http.MaxBytesError
				if errors.As(err, &tooLarge) {
					http.Error(writer, "request adapter: request exceeds 16 MiB", http.StatusRequestEntityTooLarge)
				} else {
					http.Error(writer, "request adapter: could not read request", http.StatusBadRequest)
				}
				return
			}
			body, err = normalizeHistory(body)
			if err != nil {
				http.Error(writer, "request adapter: expected a JSON object", http.StatusBadRequest)
				return
			}
			titleRouted := false
			if selectedModel != "" {
				body, titleRouted, err = routeDesktopTitle(body)
				if err != nil {
					notice(err.Error())
					http.Error(writer, "request adapter: "+err.Error(), http.StatusBadRequest)
					return
				}
				if titleRouted {
					if route := adapter.desktop.Load(); route == nil || route.namingUnavailable != "" {
						message := "automatic naming is unavailable before desktop routing is ready"
						if route != nil {
							message = route.namingUnavailable
						}
						notice(message)
						http.Error(writer, "request adapter: "+message, http.StatusBadRequest)
						return
					}
				}
			}
			if selectedModel != "" {
				var payload struct {
					Model          string          `json:"model"`
					ClientMetadata json.RawMessage `json:"client_metadata"`
				}
				if err := json.Unmarshal(body, &payload); err != nil {
					notice("invalid model request; request was not sent upstream")
					http.Error(writer, "request adapter: invalid model request", http.StatusBadRequest)
					return
				}
				var review map[string]json.RawMessage
				json.Unmarshal(body, &review)
				_, _, _, isReview := approvalReviewFormat(review)
				allowedMain := payload.Model == selectedModel
				if route := adapter.desktop.Load(); route != nil {
					allowedMain = route.mainModels[payload.Model]
				}
				message := ""
				if isDesktopCompaction(payload.ClientMetadata) {
					message = "automatic context compaction is unsupported; request was not sent upstream. Select a model with enough context or start a new conversation; the saved conversation history is retained."
				} else if isDesktopTitle(payload.ClientMetadata) && !titleRouted {
					message = "automatic title generation is unavailable: unsupported desktop title contract; request was not sent upstream"
				} else if !isReview && isApprovalReviewCandidate(review) {
					message = "unsupported desktop approval review contract; request was not sent upstream"
				} else if isReview && payload.Model != guardian {
					message = "unsupported Guardian model; relaunch with the configured --guardian-model; request was not sent upstream"
				} else if !allowedMain && !(payload.Model == guardian && isReview) && !titleRouted {
					message = "unsupported model; request was not sent upstream"
					if _, err := metadataFor(payload.Model); err == nil {
						message = "Token Factory conversation model " + payload.Model + " is unavailable in this launch's project catalog; request was not sent upstream. Check project availability and relaunch to refresh the catalog, or explicitly select an available model."
					} else {
						message = "unsupported model: " + err.Error() + "; request was not sent upstream. Explicitly select an available model with compatible metadata; relaunch after catalog or launcher metadata updates."
					}
					if isDesktopTitle(payload.ClientMetadata) {
						message = "automatic title generation is unavailable: the desktop requested an unsupported model; request was not sent upstream"
					}
				}
				if message != "" {
					notice(message)
					http.Error(writer, "request adapter: "+message, http.StatusBadRequest)
					return
				}
				// The pinned engine preserves stored images but replaces their input
				// with this explicit marker for a text-only model. Make that native
				// capability limit visible without modifying conversation history.
				if !isReview && bytes.Contains(body, []byte("image content omitted because you do not support image input")) {
					noticeMu.Lock()
					if !imageNotices[payload.Model] {
						fmt.Fprintf(a.Out, "Model context notice for %s: saved images remain in history but are omitted for this model. Select an image-capable model to use them again.\n", payload.Model)
						imageNotices[payload.Model] = true
					}
					noticeMu.Unlock()
				}
			}
			titleAdapted := false
			if !titleRouted {
				body, titleAdapted, err = adaptDesktopTitle(body)
			}
			if err != nil {
				notice(err.Error())
				http.Error(writer, "request adapter: "+err.Error(), http.StatusBadRequest)
				return
			}
			if titleAdapted {
				titleNotice.Do(func() {
					noticeMu.Lock()
					defer noticeMu.Unlock()
					fmt.Fprintln(a.Out, "Request adapter: Kimi-K3 desktop title schema moved to final-answer instructions; tools retained, desktop still validates the title.")
				})
			}
			body, adapted, err := adaptApprovalReview(body)
			if err != nil {
				notice(err.Error())
				http.Error(writer, "request adapter: "+err.Error(), http.StatusBadRequest)
				return
			}
			if adapted {
				approvalNotice.Do(func() {
					noticeMu.Lock()
					defer noticeMu.Unlock()
					fmt.Fprintln(a.Out, "Request adapter: Kimi-K3 approval-review schema moved to final-answer instructions; Codex still validates the decision.")
				})
			}
			if adjusted, changed := adaptReasoningDefault(body); changed {
				body = adjusted
				reasoningNotice.Do(func() {
					noticeMu.Lock()
					defer noticeMu.Unlock()
					fmt.Fprintln(a.Out, "GLM 5.3 thinking: using the provider default; native None is not a supported off switch. Reasoning stays separate from answer text.")
				})
			}
			if adjusted, changed := adaptImageOutputDefault(body); changed {
				body = adjusted
				imageLimitNotice.Do(func() {
					noticeMu.Lock()
					defer noticeMu.Unlock()
					fmt.Fprintln(a.Out, "DeepSeek image output: using a 32768-token limit for reasoning and answer combined when no output limit is supplied; workaround for the provider's image-request default failure. Explicit limits are preserved.")
				})
			}
			request.Body = io.NopCloser(bytes.NewReader(body))
			request.ContentLength = int64(len(body))
			proxy.ServeHTTP(writer, request)
		}),
	}
	fmt.Fprintln(a.Out, "Route: per-launch Responses request adapter (assistant-history repair).")
	if selectedModel != "" {
		fmt.Fprintf(a.Out, "Naming: %s (automatic desktop titles; independent of main and Guardian; no fallback).\n", desktopNamingModel)
		fmt.Fprintln(a.Out, "Automatic title routing: recognized gpt-5.6-luna/gpt-6-luna thread_title requests use the naming model; tool-free; provider-default reasoning; native title schema retained. Native reasoning inclusion and cache hints are omitted. Other auxiliary requests remain unsupported.")
	}
	go func() {
		err := adapter.server.Serve(listener)
		if errors.Is(err, http.ErrServerClosed) {
			err = nil
		}
		if err != nil {
			cancel()
		}
		adapter.done <- err
	}()
	return adapter, nil
}

func isDesktopCompaction(raw json.RawMessage) bool {
	var envelope map[string]json.RawMessage
	if json.Unmarshal(raw, &envelope) != nil {
		return false
	}
	var encoded string
	if json.Unmarshal(envelope["x-codex-turn-metadata"], &encoded) != nil {
		return false
	}
	var metadata struct {
		RequestKind string `json:"request_kind"`
	}
	return json.Unmarshal([]byte(encoded), &metadata) == nil && metadata.RequestKind == "compaction"
}

func (adapter *requestAdapter) close() error {
	adapter.cancel()
	if err := adapter.server.Close(); err != nil {
		return errors.New("request adapter could not close its connections")
	}
	return nil
}

// GLM 5.3 emits reasoning as answer text for effort:none. Native presets can
// supply that value when our catalog advertises no verified effort controls.
// Use the qualified provider default, preserving its native reasoning events.
func adaptReasoningDefault(body []byte) ([]byte, bool) {
	var payload, reasoning map[string]json.RawMessage
	if json.Unmarshal(body, &payload) != nil || string(payload["model"]) != `"zai-org/GLM-5.3"` || json.Unmarshal(payload["reasoning"], &reasoning) != nil || string(reasoning["effort"]) != `"none"` {
		return body, false
	}
	delete(reasoning, "effort")
	if len(reasoning) == 0 {
		delete(payload, "reasoning")
	} else {
		payload["reasoning"], _ = json.Marshal(reasoning)
	}
	adjusted, _ := json.Marshal(payload)
	return adjusted, true
}

// DeepSeek image requests fail upstream when max_output_tokens is omitted.
// This is an announced launcher policy, not a claimed provider default/ceiling.
func adaptImageOutputDefault(body []byte) ([]byte, bool) {
	var payload map[string]json.RawMessage
	var model string
	if json.Unmarshal(body, &payload) != nil || json.Unmarshal(payload["model"], &model) != nil || model != "deepseek-ai/DeepSeek-V4.1-Flash" {
		return body, false
	}
	if _, present := payload["max_output_tokens"]; present {
		return body, false
	}
	var items []struct {
		Type    string
		Content json.RawMessage
		Output  json.RawMessage
	}
	if json.Unmarshal(payload["input"], &items) != nil {
		return body, false
	}
	for _, item := range items {
		content := item.Content
		if item.Type == "function_call_output" || item.Type == "custom_tool_call_output" {
			content = item.Output
		}
		var parts []struct{ Type string }
		if json.Unmarshal(content, &parts) != nil {
			continue
		}
		for _, part := range parts {
			if part.Type == "input_image" {
				payload["max_output_tokens"] = json.RawMessage(`32768`)
				adjusted, _ := json.Marshal(payload)
				return adjusted, true
			}
		}
	}
	return body, false
}

func normalizeHistory(body []byte) ([]byte, error) {
	var payload map[string]json.RawMessage
	if err := json.Unmarshal(body, &payload); err != nil || payload == nil {
		return nil, errors.New("invalid JSON object")
	}
	var items []json.RawMessage
	if json.Unmarshal(payload["input"], &items) != nil {
		return body, nil
	}
	changed := false
	for index, raw := range items {
		var item map[string]json.RawMessage
		if json.Unmarshal(raw, &item) != nil || string(item["type"]) != `"message"` || string(item["role"]) != `"assistant"` {
			continue
		}
		var content []json.RawMessage
		if json.Unmarshal(item["content"], &content) != nil || content == nil {
			continue
		}
		itemChanged := false
		if _, exists := item["status"]; !exists {
			item["status"] = json.RawMessage(`"completed"`)
			itemChanged = true
		}
		for partIndex, partRaw := range content {
			var part map[string]json.RawMessage
			if json.Unmarshal(partRaw, &part) != nil || string(part["type"]) != `"output_text"` {
				continue
			}
			if _, exists := part["annotations"]; !exists {
				part["annotations"] = json.RawMessage(`[]`)
				content[partIndex], _ = json.Marshal(part)
				itemChanged = true
			}
		}
		if itemChanged {
			item["content"], _ = json.Marshal(content)
		}
		if _, exists := item["id"]; !exists {
			// Some desktop history messages omit the ID required by Token
			// Factory. Keep repairs stable on retries and distinguish repeated
			// identical messages by their position; never replace supplied IDs.
			canonical, _ := json.Marshal(item)
			digest := sha256.Sum256(append([]byte(strconv.Itoa(index)+":"), canonical...))
			item["id"], _ = json.Marshal("msg_tofa_" + hex.EncodeToString(digest[:24]))
			itemChanged = true
		}
		if itemChanged {
			items[index], _ = json.Marshal(item)
			changed = true
		}
	}
	if !changed {
		return body, nil
	}
	payload["input"], _ = json.Marshal(items)
	return json.Marshal(payload)
}

// Codex 0.155.1 guardian-reviewer/src/assessment.rs. This non-strict schema
// guides generation; Codex independently parses the decision and gates execution.
const guardianOutputSchema = `{"type":"object","additionalProperties":false,"properties":{"risk_level":{"type":"string","enum":["low","medium","high","critical"]},"user_authorization":{"type":"string","enum":["unknown","low","medium","high"]},"outcome":{"type":"string","enum":["allow","deny"]},"rationale":{"type":"string"}},"required":["outcome"]}`

func adaptApprovalReview(body []byte) ([]byte, bool, error) {
	var payload map[string]json.RawMessage
	if err := json.Unmarshal(body, &payload); err != nil {
		return nil, false, err
	}
	var model string
	json.Unmarshal(payload["model"], &model)
	if model != "moonshotai/Kimi-K3" {
		return body, false, nil
	}
	var textOptions, format map[string]json.RawMessage
	if json.Unmarshal(payload["text"], &textOptions) != nil || json.Unmarshal(textOptions["format"], &format) != nil {
		return body, false, nil
	}
	var formatType string
	json.Unmarshal(format["type"], &formatType)
	if formatType != "json_schema" {
		return body, false, nil
	}
	var choice string
	json.Unmarshal(payload["tool_choice"], &choice)
	if choice == "none" {
		return body, false, nil
	}
	var tools []json.RawMessage
	if len(payload["tools"]) == 0 || string(payload["tools"]) == "null" || (json.Unmarshal(payload["tools"], &tools) == nil && len(tools) == 0) {
		return body, false, nil
	}

	textOptions, format, instructions, valid := approvalReviewFormat(payload)
	if !valid {
		return nil, false, errors.New("Kimi-K3 tools with json_schema are unsupported except the recognized non-strict Codex approval review; request was not sent upstream")
	}
	*instructions += "\n\nWhen you are ready to give your final answer, return JSON matching this schema:\n" + string(format["schema"])
	payload["instructions"], _ = json.Marshal(instructions)
	delete(textOptions, "format")
	payload["text"], _ = json.Marshal(textOptions)
	result, err := json.Marshal(payload)
	return result, true, err
}

// Recognize only the existing native non-strict approval contract. This allows
// a distinct desktop Guardian without allowing its ordinary conversation lane.
func approvalReviewFormat(payload map[string]json.RawMessage) (map[string]json.RawMessage, map[string]json.RawMessage, *string, bool) {
	var textOptions, format map[string]json.RawMessage
	if json.Unmarshal(payload["text"], &textOptions) != nil || json.Unmarshal(textOptions["format"], &format) != nil || string(format["type"]) != `"json_schema"` {
		return nil, nil, nil, false
	}
	var choice string
	json.Unmarshal(payload["tool_choice"], &choice)
	var toolDefinitions []map[string]json.RawMessage
	if json.Unmarshal(payload["tools"], &toolDefinitions) != nil {
		return nil, nil, nil, false
	}
	for field := range format {
		switch field {
		case "type", "schema", "strict":
		case "name":
			var name *string
			if json.Unmarshal(format[field], &name) != nil || name == nil {
				return nil, nil, nil, false
			}
		default:
			return nil, nil, nil, false
		}
	}
	var strict *bool
	if json.Unmarshal(format["strict"], &strict) != nil || strict == nil || *strict {
		return nil, nil, nil, false
	}
	var schema, expected any
	if json.Unmarshal(format["schema"], &schema) != nil {
		return nil, nil, nil, false
	}
	json.Unmarshal([]byte(guardianOutputSchema), &expected)
	if !reflect.DeepEqual(schema, expected) {
		return nil, nil, nil, false
	}
	if choice != "auto" {
		return nil, nil, nil, false
	}
	allowed := map[string]bool{"exec_command": true, "write_stdin": true, "view_image": true}
	if len(toolDefinitions) != len(allowed) {
		return nil, nil, nil, false
	}
	for _, tool := range toolDefinitions {
		var name, kind string
		json.Unmarshal(tool["name"], &name)
		json.Unmarshal(tool["type"], &kind)
		if kind != "function" || !allowed[name] {
			return nil, nil, nil, false
		}
		delete(allowed, name)
	}
	var instructions *string
	if json.Unmarshal(payload["instructions"], &instructions) != nil || instructions == nil {
		return nil, nil, nil, false
	}
	return textOptions, format, instructions, true
}

// The pinned engine sends no role metadata with review requests. Recognize
// either its assessment fields or its inspection-tool inventory before admitting
// an ordinary main request, so a changed review cannot bypass the role gate.
func isApprovalReviewCandidate(payload map[string]json.RawMessage) bool {
	var text struct {
		Format struct {
			Schema struct{ Properties map[string]json.RawMessage }
		}
	}
	if json.Unmarshal(payload["text"], &text) == nil {
		properties := text.Format.Schema.Properties
		if properties["outcome"] != nil && (properties["risk_level"] != nil || properties["user_authorization"] != nil) {
			return true
		}
	}
	var tools []struct{ Name string }
	if json.Unmarshal(payload["tools"], &tools) != nil || len(tools) != 3 {
		return false
	}
	names := map[string]bool{"exec_command": true, "write_stdin": true, "view_image": true}
	for _, tool := range tools {
		if !names[tool.Name] {
			return false
		}
		delete(names, tool.Name)
	}
	return true
}
