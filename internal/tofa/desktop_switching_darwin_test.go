package tofa_test

import (
	"bytes"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"image"
	"image/png"
	"io"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"
)

type nativeFixtureTransport struct {
	native   *url.URL
	fallback http.RoundTripper
}

func (t nativeFixtureTransport) RoundTrip(r *http.Request) (*http.Response, error) {
	if r.URL.Host == "chatgpt.com" {
		if r.URL.String() != "https://chatgpt.com/backend-api/codex/responses" {
			return nil, fmt.Errorf("unexpected native destination")
		}
		r = r.Clone(r.Context())
		u := *r.URL
		u.Scheme = t.native.Scheme
		u.Host = t.native.Host
		r.URL = &u
		r.Host = t.native.Host
	}
	return t.fallback.RoundTrip(r)
}

func routedCandidateEngine(t *testing.T, tf, native http.HandlerFunc, observers ...func(*testing.T) string) (*desktopEngine, capturedDesktop, func()) {
	return routedCandidateEngineGuardian(t, "", tf, native, observers...)
}

func routedCandidateEngineGuardian(t *testing.T, guardian string, tf, native http.HandlerFunc, observers ...func(*testing.T) string) (*desktopEngine, capturedDesktop, func()) {
	t.Helper()
	installed := os.Getenv("TOFA_TEST_DESKTOP_ENGINE")
	if installed == "" {
		t.Skip("set TOFA_TEST_DESKTOP_ENGINE")
	}
	bundle, capture := nativeCandidateFixture(t)
	command := exec.Command(installed, "debug", "models", "--bundled")
	command.Env = []string{"PATH=" + os.Getenv("PATH"), "HOME=" + os.Getenv("HOME"), "CODEX_HOME=" + filepath.Join(os.Getenv("HOME"), ".codex")}
	catalog, err := command.Output()
	if err != nil {
		t.Fatal(err)
	}
	if err = os.WriteFile(filepath.Join(bundle, "Contents/Resources/native-catalog.json"), catalog, 0600); err != nil {
		t.Fatal(err)
	}
	app, _ := adapterFixture(t, tf, nil)
	server := httptest.NewServer(native)
	t.Cleanup(server.Close)
	target, _ := url.Parse(server.URL)
	app.HTTP.Transport = nativeFixtureTransport{target, http.DefaultTransport}
	observer := candidateProxyObserver
	if len(observers) > 0 {
		observer = observers[0]
	}
	args := []string{"--native-account-candidate", "--evaluation-observer", observer(t)}
	if guardian != "" {
		args = append(args, "--guardian-model", guardian)
	}
	child, stop := liveDesktopFixture(t, app, bundle, capture, args...)
	t.Cleanup(stop)
	deadline := time.Now().Add(10 * time.Second)
	for {
		if _, err = os.Stat(capture + ".pid"); err == nil {
			break
		}
		if time.Now().After(deadline) {
			t.Fatal("worker not ready")
		}
		time.Sleep(10 * time.Millisecond)
	}
	path := filepath.Join(bundle, "Contents/Resources/codex")
	if err = os.Remove(path); err != nil {
		t.Fatal(err)
	}
	if err = os.Symlink(installed, path); err != nil {
		t.Fatal(err)
	}
	if err = os.WriteFile(filepath.Join(child.Env["CODEX_HOME"], "auth.json"), []byte(`{"OPENAI_API_KEY":"synthetic-native"}`), 0600); err != nil {
		t.Fatal(err)
	}
	// These owned protocol fixtures test routing and native action gates, not
	// plugin initialization/preservation. Avoid asynchronous marketplace clones;
	// actual Desktop qualification retains the ordinary enabled plugins.
	return openDesktopEngine(t, child, "features.plugins=false"), child, stop
}

func TestDesktopNativeCandidateSwitchesServices(t *testing.T) {
	var mu sync.Mutex
	var sequence []string
	handler := func(service string) http.HandlerFunc {
		return func(w http.ResponseWriter, r *http.Request) {
			var body map[string]any
			if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
				t.Error(err)
				return
			}
			if r.Header.Get("X-TOFA-Launch") != "" {
				t.Error("launch capability leaked")
			}
			want := "Bearer fixture-secret"
			if service == "native" {
				want = "Bearer synthetic-native"
			}
			if r.Header.Get("Authorization") != want {
				t.Error("wrong upstream authorization")
			}
			mu.Lock()
			sequence = append(sequence, service+":"+fmt.Sprint(body["model"]))
			step := len(sequence)
			mu.Unlock()
			encoded, _ := json.Marshal(body["input"])
			if step > 1 && !strings.Contains(string(encoded), "first-service-answer") {
				t.Error("prior service context missing")
			}
			emitFixtureModelResponse(w, fixtureMessage("first-service-answer"), fmt.Sprint(body["model"]))
		}
	}
	e, child, stop := routedCandidateEngine(t, handler("tf"), handler("native"), func(t *testing.T) string {
		return actualCandidateObserver(t, map[string]string{"moonshotai/Kimi-K3": "token_factory", "gpt-6-astra": "native"})
	})
	defer stop()
	started := e.call("thread/start", map[string]any{"cwd": child.Cwd, "approvalPolicy": "never", "sandbox": "read-only"})
	if started["modelProvider"] != "tofa-native-router" {
		t.Fatal("incorrect provider")
	}
	id := started["thread"].(map[string]any)["id"].(string)
	e.turnText(id, "completed", "First service turn")
	for _, model := range []string{"gpt-6-astra", "moonshotai/Kimi-K3"} {
		e.call("thread/settings/update", map[string]any{"threadId": id, "model": model})
		e.turnText(id, "completed", "Continue across services")
	}
	saved := e.call("thread/read", map[string]any{"threadId": id, "includeTurns": true})["thread"].(map[string]any)
	if saved["id"] != id || saved["modelProvider"] != "tofa-native-router" || len(saved["turns"].([]any)) != 3 {
		t.Fatal("thread identity/history changed")
	}
	e.close()
	stop()
	mu.Lock()
	defer mu.Unlock()
	if fmt.Sprint(sequence) != "[tf:moonshotai/Kimi-K3 native:gpt-6-astra tf:moonshotai/Kimi-K3]" {
		t.Fatalf("wrong upstream sequence %v", sequence)
	}
}

func TestDesktopNativeCandidateProtocolAndAdmission(t *testing.T) {
	var mu sync.Mutex
	var nativeBodies [][]byte
	var nativeHeaders []http.Header
	var tfCalls int
	redirect := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { t.Error("credential-bearing redirect followed") }))
	defer redirect.Close()
	native := func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		mu.Lock()
		nativeBodies = append(nativeBodies, body)
		nativeHeaders = append(nativeHeaders, r.Header.Clone())
		mu.Unlock()
		if bytes.Contains(body, []byte("error-fixture")) {
			w.Header().Set("X-Private-Echo", r.Header.Get("Authorization"))
			w.WriteHeader(401)
			fmt.Fprint(w, r.Header.Get("Authorization"), r.Header.Get("ChatGPT-Account-Id"))
			return
		}
		if bytes.Contains(body, []byte("redirect-fixture")) {
			http.Redirect(w, r, redirect.URL, 307)
			return
		}
		w.Header().Set("Content-Type", "text/event-stream")
		io.WriteString(w, "event: native-fixture\ndata: {\"unmodified\":true}\n\n")
	}
	e, child, stop := routedCandidateEngine(t, func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		tfCalls++
		mu.Unlock()
		emitFixtureResponse(w, fixtureMessage("TF"))
	}, native)
	defer stop()
	defer e.close()
	request, _ := http.NewRequest("GET", child.Env["TOFA_DESKTOP_CONTEXT"]+"/desktop-launch", nil)
	request.Header.Set("Authorization", "Bearer "+child.Env["TOFA_API_KEY"])
	response, err := http.DefaultClient.Do(request)
	if err != nil {
		t.Fatal(err)
	}
	var route struct{ InferenceCapability string }
	json.NewDecoder(response.Body).Decode(&route)
	response.Body.Close()
	original := `{ "model":"gpt-6-astra", "stream":true,"input":[{"role":"assistant","content":[{"type":"output_text","text":"unaltered history"}]},{"role":"user","content":[{"type":"input_image","image_url":"data:image/png;base64,c3ludGhldGlj"}]}],"tools":[{"type":"namespace","name":"functions","tools":[{"type":"function","name":"probe","parameters":{"type":"object"}}]}],"include":["reasoning.encrypted_content"],"reasoning":{"effort":"low"},"parallel_tool_calls":true }`
	cases := []struct {
		name, body, auth string
		header           bool
		status           int
	}{
		{"native exact protocol", original, "Bearer synthetic-native", true, 200},
		{"duplicate protocol header", original, "Bearer synthetic-native", true, 400},
		{"legacy cannot switch", original, "Bearer " + route.InferenceCapability, false, 401},
		{"native auth required", original, "", true, 401},
		{"unavailable", strings.Replace(original, "gpt-6-astra", "not-in-catalog", 1), "Bearer synthetic-native", true, 400},
		{"ambiguous model", strings.Replace(original, `"model":"gpt-6-astra"`, `"model":"moonshotai/Kimi-K3","model":"gpt-6-astra"`, 1), "Bearer synthetic-native", true, 400},
		{"ambiguous role", strings.Replace(original, `"role":"user"`, `"role":"developer","role":"user"`, 1), "Bearer synthetic-native", true, 400},
		{"non-stream native", strings.Replace(original, `"stream":true`, `"stream":false`, 1), "Bearer synthetic-native", true, 400},
		{"hidden prior context", strings.Replace(original, `"stream":true`, `"stream":true,"previous_response_id":"hidden"`, 1), "Bearer synthetic-native", true, 400},
		{"unknown role", strings.Replace(original, `"role":"user"`, `"role":"alien"`, 1), "Bearer synthetic-native", true, 400},
		{"unknown auxiliary", `{"model":"gpt-6-astra","input":[],"client_metadata":{"x-openai-subagent":"unknown"}}`, "Bearer synthetic-native", true, 400},
		{"TF unknown auxiliary", `{"model":"moonshotai/Kimi-K3","input":[],"client_metadata":{"x-codex-turn-metadata":"{\"thread_source\":\"thread_summary\"}"}}`, "Bearer synthetic-native", true, 400},
		{"compaction", `{"model":"gpt-6-astra","input":[],"client_metadata":{"x-codex-turn-metadata":"{\"request_kind\":\"compaction\"}"}}`, "Bearer synthetic-native", true, 400},
		{"native review pending provenance", `{"model":"gpt-6-astra","input":[],"client_metadata":{"x-openai-subagent":"guardian"}}`, "Bearer synthetic-native", true, 400},
		{"redirect refused", strings.Replace(original, "unaltered history", "redirect-fixture", 1), "Bearer synthetic-native", true, 502},
		{"native diagnostic bounded", strings.Replace(original, "unaltered history", "error-fixture", 1), "Bearer synthetic-native", true, 401},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			req, _ := http.NewRequest("POST", child.Env["TOFA_DESKTOP_CONTEXT"]+"/responses", strings.NewReader(tc.body))
			if tc.auth != "" {
				req.Header.Set("Authorization", tc.auth)
			}
			if tc.header {
				req.Header.Set("X-TOFA-Launch", route.InferenceCapability)
			}
			req.Header.Set("ChatGPT-Account-Id", "synthetic-account")
			req.Header.Set("Cookie", "private-cookie")
			req.Header.Set("X-Arbitrary-Upstream", redirect.URL)
			req.Header.Set("X-Codex-Turn-State", "synthetic-turn-state")
			for _, name := range []string{"Thread-Id", "User-Agent", "X-Codex-Beta-Features", "X-Codex-Window-Id", "X-Openai-Internal-Codex-Responses-Lite"} {
				req.Header.Set(name, "synthetic-protocol-value")
			}
			if tc.name == "duplicate protocol header" {
				req.Header.Add("Thread-Id", "ambiguous")
			}
			res, err := http.DefaultClient.Do(req)
			if err != nil {
				t.Fatal(err)
			}
			data, _ := io.ReadAll(res.Body)
			res.Body.Close()
			if res.StatusCode != tc.status {
				t.Fatalf("status %d: %s", res.StatusCode, data)
			}
			if tc.name == "native diagnostic bounded" && (strings.Contains(string(data), "synthetic-native") || strings.Contains(string(data), "synthetic-account") || res.Header.Get("X-Private-Echo") != "") {
				t.Fatal("native error leaked account credential diagnostics")
			}
			if tc.status == 200 && string(data) != "event: native-fixture\ndata: {\"unmodified\":true}\n\n" {
				t.Fatal("native stream changed")
			}
		})
	}
	catalog, err := os.ReadFile(child.CatalogPath)
	if err != nil {
		t.Fatal(err)
	}
	var parsed struct{ Models []map[string]any }
	json.Unmarshal(catalog, &parsed)
	labels := map[string]string{}
	for _, model := range parsed.Models {
		labels[fmt.Sprint(model["slug"])] = fmt.Sprint(model["display_name"])
	}
	t.Logf("generated service labels: native=%q TF=%q", labels["gpt-6-astra"], labels["moonshotai/Kimi-K3"])
	if !strings.Contains(labels["gpt-6-astra"], "ChatGPT") || !strings.Contains(labels["moonshotai/Kimi-K3"], "Token Factory") || !strings.Contains(labels["moonshotai/Kimi-K3"], "Experimental") {
		t.Fatalf("missing explicit service/status labels: %v", labels)
	}
	e.close()
	stop()
	mu.Lock()
	defer mu.Unlock()
	if tfCalls != 0 || len(nativeBodies) != 3 || string(nativeBodies[0]) != original {
		t.Fatalf("native protocol/routing changed: TF=%d native=%d", tfCalls, len(nativeBodies))
	}
	for _, headers := range nativeHeaders {
		for _, name := range []string{"Thread-Id", "User-Agent", "X-Codex-Beta-Features", "X-Codex-Window-Id", "X-Openai-Internal-Codex-Responses-Lite"} {
			if headers.Get(name) != "synthetic-protocol-value" {
				t.Errorf("native protocol header dropped: %s", name)
			}
		}
		if headers.Get("Authorization") != "Bearer synthetic-native" || headers.Get("ChatGPT-Account-Id") != "synthetic-account" || headers.Get("X-Codex-Turn-State") != "synthetic-turn-state" || headers.Get("Cookie") != "" || headers.Get("X-TOFA-Launch") != "" || headers.Get("X-Arbitrary-Upstream") != "" {
			t.Fatal("native header isolation failed")
		}
	}
}

func TestDesktopNativeCandidatePendingSelectionAndConcurrentThreads(t *testing.T) {
	started, cancelled := make(chan struct{}, 1), make(chan struct{}, 1)
	release := make(chan struct{})
	defer close(release)
	var mu sync.Mutex
	var sequence []string
	tf := func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		sequence = append(sequence, "tf")
		mu.Unlock()
		emitFixtureResponse(w, fixtureMessage("TF independent response"))
	}
	native := func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		sequence = append(sequence, "native")
		mu.Unlock()
		io.Copy(io.Discard, r.Body)
		w.Header().Set("Content-Type", "text/event-stream")
		events := []struct {
			name string
			body map[string]any
		}{
			{"response.created", map[string]any{"response": map[string]any{"id": "pending-native", "status": "in_progress", "output": []any{}}}},
			{"response.output_item.added", map[string]any{"output_index": 0, "item": map[string]any{"type": "message", "id": "native-stream", "role": "assistant", "status": "in_progress", "content": []any{}}}},
			{"response.content_part.added", map[string]any{"item_id": "native-stream", "output_index": 0, "content_index": 0, "part": map[string]any{"type": "output_text", "text": "", "annotations": []any{}}}},
			{"response.output_text.delta", map[string]any{"item_id": "native-stream", "output_index": 0, "content_index": 0, "delta": "native-stream-progress"}},
		}
		for _, event := range events {
			event.body["type"] = event.name
			raw, _ := json.Marshal(event.body)
			fmt.Fprintf(w, "event: %s\ndata: %s\n\n", event.name, raw)
			w.(http.Flusher).Flush()
		}
		started <- struct{}{}
		select {
		case <-r.Context().Done():
			cancelled <- struct{}{}
		case <-release:
		}
	}
	e, child, stop := routedCandidateEngine(t, tf, native)
	defer stop()
	defer e.close()
	thread := e.call("thread/start", map[string]any{"cwd": child.Cwd, "model": "gpt-6-astra", "approvalPolicy": "never", "sandbox": "read-only"})
	id := thread["thread"].(map[string]any)["id"].(string)
	turn := e.call("turn/start", map[string]any{"threadId": id, "input": []any{map[string]string{"type": "text", "text": "Pending native turn"}}})
	select {
	case <-started:
	case <-time.After(5 * time.Second):
		t.Fatal("native request did not start")
	}
	for {
		message := e.read()
		if message["method"] == "item/agentMessage/delta" {
			if message["params"].(map[string]any)["delta"] != "native-stream-progress" {
				t.Fatal("native stream delta changed")
			}
			break
		}
		if message["method"] == "turn/completed" {
			t.Fatal("native stream ended before cancellation")
		}
	}
	e.call("thread/settings/update", map[string]any{"threadId": id, "model": "moonshotai/Kimi-K3"})
	other := e.call("thread/start", map[string]any{"cwd": child.Cwd, "approvalPolicy": "never", "sandbox": "read-only"})
	otherID := other["thread"].(map[string]any)["id"].(string)
	e.turnText(otherID, "completed", "Independent TF thread during pending native request")
	select {
	case <-cancelled:
		t.Fatal("selection or another thread cancelled the originating request")
	default:
	}
	e.call("turn/interrupt", map[string]any{"threadId": id, "turnId": turn["turn"].(map[string]any)["id"]})
	for {
		message := e.read()
		if message["method"] == "turn/completed" {
			params := message["params"].(map[string]any)
			if params["threadId"] != id || params["turn"].(map[string]any)["status"] != "interrupted" {
				t.Fatal("wrong interrupted turn")
			}
			break
		}
	}
	select {
	case <-cancelled:
	case <-time.After(5 * time.Second):
		t.Fatal("native cancellation did not propagate")
	}
	e.turnText(id, "completed", "Subsequent turn follows explicit TF selection")
	e.call("thread/settings/update", map[string]any{"threadId": id, "model": "unknown-native-model"})
	e.turnText(id, "failed", "Unavailable selection never substitutes")
	e.close()
	stop()
	mu.Lock()
	defer mu.Unlock()
	if fmt.Sprint(sequence) != "[native tf tf]" {
		t.Fatalf("pending/concurrent routing changed: %v", sequence)
	}
}

func TestDesktopNativeCandidateNativeToolsAndMedia(t *testing.T) {
	var mu sync.Mutex
	var nativeCalls int
	var tfCalls int
	var savedImage bool
	var toolOutput bool
	tf := func(w http.ResponseWriter, r *http.Request) {
		var body map[string]any
		json.NewDecoder(r.Body).Decode(&body)
		mu.Lock()
		tfCalls++
		encoded, _ := json.Marshal(body["input"])
		if strings.Contains(string(encoded), "native-tool-result") {
			toolOutput = true
		}
		mu.Unlock()
		emitFixtureResponse(w, fixtureMessage("Back on TF with native tool context"))
	}
	native := func(w http.ResponseWriter, r *http.Request) {
		var body map[string]any
		json.NewDecoder(r.Body).Decode(&body)
		mu.Lock()
		nativeCalls++
		step := nativeCalls
		encoded, _ := json.Marshal(body["input"])
		savedImage = savedImage || strings.Contains(string(encoded), "input_image")
		mu.Unlock()
		if step == 1 {
			emitFixtureResponse(w, map[string]any{"id": "native_call", "type": "custom_tool_call", "call_id": "native_tool", "namespace": "functions", "name": "exec", "input": "text('native-tool-result')", "status": "completed"})
			return
		}
		if !strings.Contains(string(encoded), "native-tool-result") {
			t.Errorf("native tool continuation output missing: %s", encoded)
		}
		emitFixtureResponse(w, fixtureMessage("Native tool and image turn complete"))
	}
	e, child, stop := routedCandidateEngine(t, tf, native)
	defer stop()
	defer e.close()
	thread := e.call("thread/start", map[string]any{"cwd": child.Cwd, "model": "gpt-6-astra", "approvalPolicy": "never", "sandbox": "read-only"})
	id := thread["thread"].(map[string]any)["id"].(string)
	var pictureData bytes.Buffer
	if err := png.Encode(&pictureData, image.NewRGBA(image.Rect(0, 0, 32, 32))); err != nil {
		t.Fatal(err)
	}
	picture := "data:image/png;base64," + base64.StdEncoding.EncodeToString(pictureData.Bytes())
	e.call("turn/start", map[string]any{"threadId": id, "input": []any{map[string]string{"type": "text", "text": "Use native tool and retain supplied image"}, map[string]string{"type": "image", "url": picture}}})
	for {
		message := e.read()
		if message["method"] == "turn/completed" {
			turn := message["params"].(map[string]any)["turn"].(map[string]any)
			if turn["status"] != "completed" {
				t.Fatalf("native tool/media turn failed: %v", turn["error"])
			}
			break
		}
	}
	e.call("thread/settings/update", map[string]any{"threadId": id, "model": "moonshotai/Kimi-K3"})
	e.turnText(id, "completed", "Continue with native tool result and saved media")
	saved := e.call("thread/read", map[string]any{"threadId": id, "includeTurns": true})
	encoded, _ := json.Marshal(saved)
	if !strings.Contains(string(encoded), picture) {
		t.Fatal("switch lost persisted image")
	}
	e.close()
	stop()
	mu.Lock()
	defer mu.Unlock()
	if nativeCalls != 2 || tfCalls != 1 || !savedImage || !toolOutput {
		t.Fatalf("native continuation: native=%d TF=%d image=%t tool=%t", nativeCalls, tfCalls, savedImage, toolOutput)
	}
}
