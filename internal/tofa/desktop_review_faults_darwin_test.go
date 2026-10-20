package tofa_test

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"net/http/httputil"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

func reviewFaultObserver(t *testing.T, mutate func(map[string]any), rawMutators ...func([]byte) []byte) string {
	t.Helper()
	var mu sync.Mutex
	var upstream string
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/register" {
			var data struct{ Endpoint string }
			json.NewDecoder(r.Body).Decode(&data)
			mu.Lock()
			upstream = data.Endpoint
			mu.Unlock()
			io.WriteString(w, `{"ready":true}`)
			return
		}
		mu.Lock()
		target, _ := url.Parse(upstream)
		mu.Unlock()
		if r.URL.Path == "/responses" {
			var body map[string]any
			json.NewDecoder(r.Body).Decode(&body)
			mutate(body)
			raw, _ := json.Marshal(body)
			for _, mutator := range rawMutators {
				raw = mutator(raw)
			}
			r.Body = io.NopCloser(bytes.NewReader(raw))
			r.ContentLength = int64(len(raw))
		}
		httputil.NewSingleHostReverseProxy(target).ServeHTTP(w, r)
	}))
	t.Cleanup(server.Close)
	path := filepath.Join(t.TempDir(), "observer.json")
	raw, _ := json.Marshal(map[string]any{"version": 2, "endpoint": server.URL, "secret": "owned-fault-observer", "seconds": 900})
	if err := os.WriteFile(path, raw, 0600); err != nil {
		t.Fatal(err)
	}
	return path
}

func TestDesktopNativeCandidateReviewRejectsUnknownOrigin(t *testing.T) {
	for _, fault := range []string{"missing parent turn", "unknown parent turn", "conflicting encoded parent", "changed policy", "missing Main provenance", "duplicate parent", "duplicate schema", "native changed inventory", "native wrong service reviewer", "review transport failure", "native review transport failure", "unavailable Guardian", "native conflicting review role", "native conflicting review source", "invalid lifecycle metadata"} {
		t.Run(fault, func(t *testing.T) {
			var mainCalls, reviews atomic.Int32
			handler := func(w http.ResponseWriter, r *http.Request) {
				var body map[string]any
				wantAuth := "Bearer fixture-secret"
				if strings.HasPrefix(fault, "native") {
					wantAuth = "Bearer synthetic-native"
				}
				if r.Header.Get("Authorization") != wantAuth || r.Header.Get("X-TOFA-Launch") != "" {
					t.Error("review fault changed service or leaked launch authorization")
				}
				json.NewDecoder(r.Body).Decode(&body)
				metadata, _ := body["client_metadata"].(map[string]any)
				if metadata["x-openai-subagent"] == "guardian" {
					reviews.Add(1)
					if strings.Contains(fault, "transport failure") {
						w.WriteHeader(http.StatusServiceUnavailable)
						return
					}
					emitFixtureResponse(w, fixtureMessage(`{"outcome":"allow"}`))
					return
				}
				if mainCalls.Add(1) == 1 {
					emitFixtureResponse(w, map[string]any{"id": "reject_action", "type": "function_call", "call_id": "reject_call", "name": "exec_command", "status": "completed", "arguments": `{"cmd":"printf must-not-execute-origin","sandbox_permissions":"require_escalated","justification":"Synthetic fault fixture.","max_output_tokens":100}`})
					return
				}
				emitFixtureResponse(w, fixtureMessage("Stop after failed review."))
			}
			e, child, stop := routedCandidateEngine(t, handler, handler, func(t *testing.T) string {
				return reviewFaultObserver(t, func(body map[string]any) {
					metadata, _ := body["client_metadata"].(map[string]any)
					if fault == "missing Main provenance" && metadata["x-openai-subagent"] != "guardian" {
						delete(metadata, "thread_id")
						delete(metadata, "turn_id")
						return
					}
					if metadata["x-openai-subagent"] != "guardian" {
						return
					}
					switch fault {
					case "missing parent turn":
						delete(metadata, "parent_turn_id")
					case "unknown parent turn":
						metadata["parent_turn_id"] = "unobserved-turn"
					case "conflicting encoded parent":
						var encoded map[string]any
						json.Unmarshal([]byte(metadata["x-codex-turn-metadata"].(string)), &encoded)
						encoded["parent_turn_id"] = "conflicting-turn"
						raw, _ := json.Marshal(encoded)
						metadata["x-codex-turn-metadata"] = string(raw)
					case "invalid lifecycle metadata":
						metadata["unrelated"] = 42
					case "unavailable Guardian":
						body["model"] = "unavailable-reviewer"
					case "native conflicting review role", "native conflicting review source":
						var encoded map[string]any
						json.Unmarshal([]byte(metadata["x-codex-turn-metadata"].(string)), &encoded)
						if fault == "native conflicting review role" {
							encoded["request_kind"] = "compaction"
						} else {
							encoded["thread_source"] = "thread_title"
						}
						raw, _ := json.Marshal(encoded)
						metadata["x-codex-turn-metadata"] = string(raw)
					case "changed policy":
						body["instructions"] = 42
					case "native changed inventory":
						body["input"].([]any)[0].(map[string]any)["tools"] = []any{}
					case "native wrong service reviewer":
						body["model"] = "moonshotai/Kimi-K3"
					}
				}, func(raw []byte) []byte {
					if !bytes.Contains(raw, []byte(`"x-openai-subagent":"guardian"`)) {
						return raw
					}
					switch fault {
					case "duplicate parent":
						return bytes.Replace(raw, []byte(`"parent_turn_id":`), []byte(`"parent_turn_id":"ambiguous","parent_turn_id":`), 1)
					case "duplicate schema":
						return bytes.Replace(raw, []byte(`"outcome":{`), []byte(`"outcome":{"type":"number"},"outcome":{`), 1)
					}
					return raw
				})
			})
			defer stop()
			defer e.close()
			model := "moonshotai/Kimi-K3"
			if strings.HasPrefix(fault, "native") {
				model = "gpt-6-astra"
			}
			started := e.call("thread/start", map[string]any{"model": model, "cwd": child.Cwd, "approvalPolicy": "on-request", "approvalsReviewer": "auto_review", "sandbox": "read-only"})
			id := started["thread"].(map[string]any)["id"].(string)
			e.call("turn/start", map[string]any{"threadId": id, "input": []any{map[string]string{"type": "text", "text": "Attempt harmless command once. Stop if review fails."}}})
			for {
				message := e.read()
				if message["method"] == "item/completed" {
					item := message["params"].(map[string]any)["item"].(map[string]any)
					if item["type"] == "commandExecution" && item["exitCode"] == float64(0) && strings.Contains(item["aggregatedOutput"].(string), "must-not-execute-origin") {
						t.Fatal("missing review provenance bypassed approval")
					}
				}
				if message["method"] == "turn/completed" {
					break
				}
			}
			if strings.Contains(fault, "transport failure") {
				if reviews.Load() < 1 {
					t.Fatal("review failure never reached provider")
				}
				t.Logf("engine-originated review requests=%d; no command execution", reviews.Load())
			} else if reviews.Load() != 0 {
				t.Fatalf("unproven review sent upstream: %d", reviews.Load())
			}
		})
	}
}

func TestDesktopNativeCandidateReviewRetriesConsumeObserverBudget(t *testing.T) {
	for _, model := range []string{"moonshotai/Kimi-K3", "gpt-6-astra"} {
		t.Run(model, func(t *testing.T) {
			var reviews atomic.Int32
			marker := filepath.Join(t.TempDir(), "must-not-run")
			handler := func(w http.ResponseWriter, r *http.Request) {
				var body map[string]any
				json.NewDecoder(r.Body).Decode(&body)
				metadata, _ := body["client_metadata"].(map[string]any)
				if metadata["x-openai-subagent"] == "guardian" {
					reviews.Add(1)
					w.WriteHeader(http.StatusServiceUnavailable)
					return
				}
				args, _ := json.Marshal(map[string]any{"cmd": "touch '" + marker + "'", "sandbox_permissions": "require_escalated", "justification": "Owned observer budget fixture.", "max_output_tokens": 100})
				emitFixtureModelResponse(w, map[string]any{"id": "budget_action", "type": "function_call", "call_id": "budget_call", "name": "exec_command", "status": "completed", "arguments": string(args)}, body["model"].(string))
			}
			var observerConfig string
			e, child, stop := routedCandidateEngine(t, handler, handler, func(t *testing.T) string {
				observerConfig = actualCandidateObserverBudget(t, map[string]string{"moonshotai/Kimi-K3": "token_factory", "gpt-6-astra": "native"}, 2)
				return observerConfig
			})
			defer stop()
			defer e.close()
			started := e.call("thread/start", map[string]any{"cwd": child.Cwd, "model": model, "approvalPolicy": "on-request", "approvalsReviewer": "auto_review", "sandbox": "read-only"})
			id := started["thread"].(map[string]any)["id"].(string)
			e.call("turn/start", map[string]any{"threadId": id, "input": []any{map[string]string{"type": "text", "text": "Attempt the owned fixture; stop on failed review."}}})
			deadline := time.Now().Add(15 * time.Second)
			for {
				reason, err := os.ReadFile(filepath.Join(filepath.Dir(observerConfig), "stop-reason.txt"))
				if err == nil {
					if string(reason) != "request_budget_limit" {
						t.Fatalf("unexpected observer stop: %s", reason)
					}
					break
				}
				if time.Now().After(deadline) {
					t.Fatal("native review retry did not consume observer request budget")
				}
				time.Sleep(10 * time.Millisecond)
			}
			e.close()
			stop()
			raw, err := os.ReadFile(filepath.Join(filepath.Dir(observerConfig), "requests.json"))
			if err != nil {
				t.Fatal(err)
			}
			var records []map[string]any
			json.Unmarshal(raw, &records)
			forwarded, guardian := 0, 0
			for _, record := range records {
				if record["forwarded"] == true {
					forwarded++
					if record["role"] == "guardian" {
						guardian++
					}
				}
			}
			if forwarded != 2 || guardian != 1 || reviews.Load() != 1 {
				t.Fatalf("review retries exceeded declared observer bound: forwarded=%d guardian=%d upstream=%d", forwarded, guardian, reviews.Load())
			}
			if _, err := os.Stat(marker); !os.IsNotExist(err) {
				t.Fatal("failed/budgeted review executed a command")
			}
		})
	}
}

func TestDesktopNativeCandidateFailedCancellationControlStopsEngine(t *testing.T) {
	marker := filepath.Join(t.TempDir(), "cancelled-command")
	started, disconnected, release := make(chan struct{}), make(chan struct{}), make(chan struct{})
	defer close(release)
	var mainCalls atomic.Int32
	native := func(w http.ResponseWriter, r *http.Request) {
		var body map[string]any
		json.NewDecoder(r.Body).Decode(&body)
		metadata, _ := body["client_metadata"].(map[string]any)
		if metadata["x-openai-subagent"] == "guardian" {
			w.Header().Set("Content-Type", "text/event-stream")
			w.WriteHeader(http.StatusOK)
			w.(http.Flusher).Flush()
			close(started)
			<-r.Context().Done()
			close(disconnected)
			<-release
			emitFixtureModelResponse(w, fixtureMessage(`{"outcome":"allow"}`), fmt.Sprint(body["model"]))
			return
		}
		if mainCalls.Add(1) != 1 {
			t.Error("cancelled command unexpectedly continued")
		}
		args, _ := json.Marshal(map[string]any{"cmd": "touch '" + marker + "'", "sandbox_permissions": "require_escalated", "justification": "Owned cancellation fixture."})
		emitFixtureModelResponse(w, map[string]any{"id": "cancel_action", "type": "custom_tool_call", "call_id": "cancel_call", "namespace": "functions", "name": "exec", "input": "text(await tools.exec_command(" + string(args) + "))", "status": "completed"}, "gpt-6-astra")
	}
	e, child, stop := routedCandidateEngine(t, func(w http.ResponseWriter, r *http.Request) {
		t.Error("cancellation failure substituted Token Factory")
		http.Error(w, "unexpected", http.StatusInternalServerError)
	}, native)
	defer stop()
	e.close()
	target, _ := url.Parse(child.Env["TOFA_DESKTOP_CONTEXT"])
	proxy := httputil.NewSingleHostReverseProxy(target)
	control := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/desktop-review-cancel" {
			if r.Header.Get("Authorization") != "Bearer "+child.Env["TOFA_API_KEY"] || r.Header.Get("X-TOFA-Launch") != "" {
				t.Error("review cancellation did not use independent control authorization")
			}
			http.Error(w, "owned unavailable control", http.StatusServiceUnavailable)
			return
		}
		proxy.ServeHTTP(w, r)
	}))
	defer control.Close()
	child.Env["TOFA_DESKTOP_CONTEXT"] = control.URL
	e = openDesktopEngine(t, child, "features.plugins=false")
	defer e.close()
	thread := e.call("thread/start", map[string]any{"cwd": child.Cwd, "model": "gpt-6-astra", "approvalPolicy": "on-request", "approvalsReviewer": "auto_review", "sandbox": "read-only"})
	id := thread["thread"].(map[string]any)["id"].(string)
	turn := e.call("turn/start", map[string]any{"threadId": id, "input": []any{map[string]string{"type": "text", "text": "Run the owned fixture."}}})
	select {
	case <-started:
	case <-time.After(12 * time.Second):
		t.Fatal("review never reached owned upstream")
	}
	e.id++
	if err := e.encoder.Encode(map[string]any{"id": e.id, "method": "turn/interrupt", "params": map[string]any{"threadId": id, "turnId": turn["turn"].(map[string]any)["id"]}}); err != nil {
		t.Fatal(err)
	}
	for {
		message := e.read()
		if message["id"] != float64(e.id) {
			continue
		}
		raw, _ := json.Marshal(message["error"])
		if !strings.Contains(string(raw), "review cancellation could not be authenticated") {
			t.Fatalf("missing bounded cancellation error: %s", raw)
		}
		break
	}
	ended := make(chan error, 1)
	go func() { ended <- e.command.Wait() }()
	select {
	case err := <-ended:
		if err == nil {
			t.Error("control failure did not stop the owned engine")
		}
		e.command = nil
	case <-time.After(5 * time.Second):
		t.Fatal("failed cancellation did not terminate the owned engine")
	}
	select {
	case <-disconnected:
	case <-time.After(5 * time.Second):
		t.Fatal("engine exit left pending native review connected")
	}
	if _, err := os.Stat(marker); !os.IsNotExist(err) {
		t.Fatal("command executed after cancellation control failed")
	}
}

func TestDesktopNativeCandidateDirectNativeHistoryInterrupt(t *testing.T) {
	var directCalls, routedCalls atomic.Int32
	started, disconnected := make(chan struct{}), make(chan struct{})
	release := make(chan struct{})
	defer close(release)
	direct := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost || !strings.HasSuffix(r.URL.Path, "/responses") {
			http.Error(w, "owned fixture supports only Responses POST", http.StatusUpgradeRequired)
			return
		}
		if r.Header.Get("Authorization") != "Bearer synthetic-native" || r.Header.Get("X-TOFA-Launch") != "" {
			t.Error("direct native credential/provider changed")
		}
		io.Copy(io.Discard, r.Body)
		if directCalls.Add(1) != 2 {
			emitFixtureModelResponse(w, fixtureMessage("Direct native history."), "gpt-6-astra")
			return
		}
		w.Header().Set("Content-Type", "text/event-stream")
		w.WriteHeader(http.StatusOK)
		w.(http.Flusher).Flush()
		close(started)
		select {
		case <-r.Context().Done():
			close(disconnected)
		case <-release:
		}
	}))
	defer direct.Close()
	e, child, stop := routedCandidateEngine(t, func(w http.ResponseWriter, r *http.Request) {
		routedCalls.Add(1)
		emitFixtureResponse(w, fixtureMessage("Routed work remains available."))
	}, func(w http.ResponseWriter, r *http.Request) {
		t.Error("ordinary native history entered the candidate adapter")
		http.Error(w, "unexpected", http.StatusInternalServerError)
	})
	defer stop()
	e.close()
	ordinary := capturedDesktop{Cwd: child.Cwd, Env: map[string]string{"PATH": os.Getenv("PATH"), "HOME": child.Env["HOME"], "CODEX_HOME": child.Env["CODEX_HOME"], "CODEX_CLI_PATH": os.Getenv("TOFA_TEST_DESKTOP_ENGINE")}}
	override := "openai_base_url=" + fmt.Sprintf("%q", direct.URL)
	e = openDesktopEngine(t, ordinary, override, "features.plugins=false")
	thread := e.call("thread/start", map[string]any{"cwd": child.Cwd, "model": "gpt-6-astra", "modelProvider": "openai", "approvalPolicy": "never", "sandbox": "read-only"})
	id := thread["thread"].(map[string]any)["id"].(string)
	e.turnText(id, "completed", "Ordinary native history before candidate resume")
	e.close()
	e = openDesktopEngine(t, child, override, "features.plugins=false")
	defer e.close()
	resumed := e.call("thread/resume", map[string]any{"threadId": id, "model": nil, "modelProvider": nil})
	if resumed["modelProvider"] != "openai" {
		t.Fatal("ordinary native history lost provider identity")
	}
	turn := e.call("turn/start", map[string]any{"threadId": id, "input": []any{map[string]string{"type": "text", "text": "Hold direct native work."}}})
	select {
	case <-started:
	case <-time.After(5 * time.Second):
		t.Fatal("direct native work did not reach owned upstream")
	}
	other := e.call("thread/start", map[string]any{"cwd": child.Cwd, "model": "moonshotai/Kimi-K3", "approvalPolicy": "never", "sandbox": "read-only"})
	otherID := other["thread"].(map[string]any)["id"].(string)
	e.turnText(otherID, "completed", "Routed work while direct native turn pending")
	e.call("turn/interrupt", map[string]any{"threadId": id, "turnId": turn["turn"].(map[string]any)["id"]})
	for {
		message := e.read()
		if message["method"] == "turn/completed" {
			params := message["params"].(map[string]any)
			if params["threadId"] != id || params["turn"].(map[string]any)["status"] != "interrupted" {
				t.Fatal("direct native interrupt changed")
			}
			break
		}
	}
	select {
	case <-disconnected:
	case <-time.After(5 * time.Second):
		t.Fatal("direct native interruption did not disconnect")
	}
	e.turnText(otherID, "completed", "Routed work survives unrelated direct native interrupt")
	e.turnText(id, "completed", "Direct native history continues after interrupt")
	if directCalls.Load() != 3 || routedCalls.Load() != 2 {
		t.Fatalf("direct/routed request boundary changed: direct=%d routed=%d", directCalls.Load(), routedCalls.Load())
	}
}
