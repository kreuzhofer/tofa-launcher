package tofa

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"net/http"
	"net/http/httputil"
	"net/url"
	"strconv"
	"strings"
)

type inferenceService string

const (
	tokenFactoryService    inferenceService = "token_factory"
	nativeInferenceService inferenceService = "native"
	// Native credentials are never sent to configurable/provider-supplied URLs.
	nativeResponsesEndpoint = "https://chatgpt.com/backend-api/codex/responses"
)

var nativeProtocolHeaders = [...]string{"Authorization", "ChatGPT-Account-Id", "OpenAI-Beta", "Originator", "Session-Id", "Thread-Id", "User-Agent", "X-Client-Request-Id", "X-Codex-Turn-State", "X-Codex-Turn-Metadata", "X-Codex-Beta-Features", "X-Codex-Window-Id", "X-Openai-Internal-Codex-Responses-Lite"}

// Native inference is HTTP Responses/SSE. The engine's provider disables
// WebSockets. Body bytes and streamed response events cross this boundary intact;
// Token Factory history, namespaces, reasoning and schema repairs do not apply.
func nativeResponsesProxy(transport http.RoundTripper) *httputil.ReverseProxy {
	target, _ := url.Parse(nativeResponsesEndpoint)
	return &httputil.ReverseProxy{
		Rewrite: func(p *httputil.ProxyRequest) {
			u := *target
			p.Out.URL = &u
			p.Out.Host = target.Host
			p.Out.Header = make(http.Header)
			for _, name := range nativeProtocolHeaders {
				if value := p.In.Header.Get(name); value != "" {
					p.Out.Header.Set(name, value)
				}
			}
			p.Out.Header.Set("Content-Type", "application/json")
			p.Out.Header.Set("Accept", "text/event-stream, application/json")
			p.Out.GetBody = nil
			p.Out.Trailer = nil
			p.Out.TransferEncoding = nil
		},
		Transport: transport, FlushInterval: -1, ErrorLog: log.New(io.Discard, "", 0),
		ModifyResponse: func(r *http.Response) error {
			if r.StatusCode >= 300 && r.StatusCode < 400 {
				return errors.New("native upstream redirect rejected")
			}
			if r.StatusCode >= 400 {
				// Native error bodies/headers may reflect account credentials.
				// Retain status and a bounded actionable class, never echo them.
				r.Body.Close()
				data := []byte(fmt.Sprintf(`{"error":{"type":"native_upstream_error","message":"ChatGPT inference returned HTTP %d; check the native account/service. No retry or service fallback was performed."}}`, r.StatusCode))
				r.Header = make(http.Header)
				r.Header.Set("Content-Type", "application/json")
				r.Header.Set("Content-Length", strconv.Itoa(len(data)))
				r.Body = io.NopCloser(bytes.NewReader(data))
				r.ContentLength = int64(len(data))
				r.TransferEncoding = nil
				r.Trailer = nil
			}
			return nil
		},
		ErrorHandler: func(w http.ResponseWriter, r *http.Request, err error) {
			http.Error(w, "native inference connection failed; request was not retried or rerouted", http.StatusBadGateway)
		},
	}
}

// Resolve from the validated launch snapshot, never from model prefixes, timing
// or another conversation's current selection. Titles retain their separate
// strict classifier; reviews are admitted by their originating-work policy.
func nativeMainRequest(body []byte, route *desktopRoute) (bool, error) {
	if route == nil || route.services == nil {
		return false, nil
	}
	payload, err := routingObject(body)
	if err != nil {
		return false, err
	}
	var metadata map[string]json.RawMessage
	if raw, ok := payload["client_metadata"]; ok && string(raw) != "null" {
		metadata, err = routingObject(raw)
		if err != nil {
			return false, errors.New("invalid or ambiguous request role metadata")
		}
		if raw, ok := metadata["x-codex-turn-metadata"]; ok {
			var encoded string
			if json.Unmarshal(raw, &encoded) != nil {
				return false, errors.New("invalid turn metadata")
			}
			if _, err = routingObject([]byte(encoded)); err != nil {
				return false, errors.New("invalid or ambiguous turn metadata")
			}
		}
	}
	var model string
	json.Unmarshal(payload["model"], &model)
	if isDesktopTitle(payload["client_metadata"]) {
		return false, nil
	}
	service, exists := route.services[model]
	if !exists {
		return false, errors.New("selected model is unavailable in this launch catalog; explicitly select an available model or relaunch to refresh the catalog")
	}
	if service != nativeInferenceService && service != tokenFactoryService {
		return false, errors.New("ambiguous destination service; relaunch to refresh the catalog")
	}
	if isDesktopCompaction(payload["client_metadata"]) {
		return false, errors.New("automatic context compaction is unsupported; saved conversation history is retained")
	}
	var subagent string
	if raw, ok := metadata["x-openai-subagent"]; ok {
		if json.Unmarshal(raw, &subagent) != nil {
			return false, errors.New("unsupported request role")
		}
		if subagent != "guardian" {
			return false, errors.New("unsupported auxiliary request role")
		}
	}
	if subagent != "" || isApprovalReviewCandidate(payload) {
		if service == tokenFactoryService {
			return false, nil
		}
		return false, errors.New("native review requires verified originating-work provenance")
	}
	if raw, ok := metadata["x-codex-turn-metadata"]; ok {
		var encoded string
		var turn struct {
			Source  string `json:"thread_source"`
			Trigger string `json:"turn_trigger"`
			Kind    string `json:"request_kind"`
		}
		if json.Unmarshal(raw, &encoded) != nil || json.Unmarshal([]byte(encoded), &turn) != nil {
			return false, errors.New("invalid turn metadata")
		}
		if (turn.Source != "" && turn.Source != "user") || (turn.Trigger != "" && turn.Trigger != "composer") || (turn.Kind != "" && turn.Kind != "turn") {
			return false, errors.New("unsupported auxiliary request role")
		}
	}
	if service == tokenFactoryService {
		return false, nil
	}
	var streaming bool
	if json.Unmarshal(payload["stream"], &streaming) != nil || !streaming {
		return false, errors.New("native inference requires the streaming Responses contract")
	}
	for _, key := range []string{"previous_response_id", "conversation", "prompt"} {
		if raw, exists := payload[key]; exists && string(raw) != "null" {
			return false, errors.New("native inference requires explicit full-history context")
		}
	}
	var input []json.RawMessage
	if json.Unmarshal(payload["input"], &input) != nil || input == nil {
		return false, errors.New("native request requires explicit input history")
	}
	for _, raw := range input {
		item, err := routingObject(raw)
		if err != nil {
			return false, err
		}
		var kind string
		if raw, exists := item["type"]; exists {
			if json.Unmarshal(raw, &kind) != nil {
				return false, errors.New("unsupported native input item")
			}
		}
		switch kind {
		case "", "message", "function_call", "function_call_output", "custom_tool_call", "custom_tool_call_output", "reasoning", "additional_tools":
		default:
			return false, errors.New("unsupported native input item")
		}
		if raw, ok := item["role"]; ok {
			var role string
			if json.Unmarshal(raw, &role) != nil || (role != "user" && role != "assistant" && role != "developer" && role != "system") {
				return false, errors.New("unsupported native input role")
			}
		}
	}
	return true, nil
}

func serveNativeMain(proxy *httputil.ReverseProxy, w http.ResponseWriter, r *http.Request, body []byte) {
	// Header authorization distinguishes new routed threads from legacy bearer-only
	// provider histories. A legacy history cannot acquire native auth by selection.
	if r.Header.Get("X-TOFA-Launch") == "" || len(r.Header.Values("Authorization")) != 1 || len(r.Header.Values("ChatGPT-Account-Id")) > 1 || r.Header.Get("Authorization") == "" || len(r.Header.Get("ChatGPT-Account-Id")) > 512 || strings.ContainsAny(r.Header.Get("ChatGPT-Account-Id"), "\r\n\t,") {
		http.Error(w, "native inference requires the authenticated routing provider; legacy histories retain their original provider", http.StatusUnauthorized)
		return
	}
	for _, name := range nativeProtocolHeaders {
		if len(r.Header.Values(name)) > 1 || len(r.Header.Get(name)) > 8192 {
			http.Error(w, "invalid or ambiguous native protocol header", http.StatusBadRequest)
			return
		}
	}
	r.Body = io.NopCloser(bytes.NewReader(body))
	r.ContentLength = int64(len(body))
	proxy.ServeHTTP(w, r)
}

// Reject duplicate fields before forwarding original bytes: the adapter and
// upstream must not disagree about a model or input role due to parser choices.
func routingObject(raw []byte) (map[string]json.RawMessage, error) {
	fail := errors.New("ambiguous or invalid request object; request was not sent upstream")
	decoder := json.NewDecoder(bytes.NewReader(raw))
	token, err := decoder.Token()
	if err != nil || token != json.Delim('{') {
		return nil, fail
	}
	result := make(map[string]json.RawMessage)
	for decoder.More() {
		token, err = decoder.Token()
		key, ok := token.(string)
		if err != nil || !ok {
			return nil, fail
		}
		if _, exists := result[key]; exists {
			return nil, fail
		}
		var value json.RawMessage
		if decoder.Decode(&value) != nil {
			return nil, fail
		}
		result[key] = value
	}
	if _, err = decoder.Token(); err != nil {
		return nil, fail
	}
	if _, err = decoder.Token(); err != io.EOF {
		return nil, fail
	}
	return result, nil
}
