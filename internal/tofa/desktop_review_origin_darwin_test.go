package tofa_test

import (
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"
)

func TestDesktopNativeCandidateReviewOrigin(t *testing.T) {
	for _, scenario := range []struct {
		name, model, service, assessment, guardian string
		allow, cancel, inspect                     bool
	}{
		{name: "TF allow through observer", model: "moonshotai/Kimi-K3", service: "tf", assessment: "allow", allow: true},
		{name: "TF deny through observer", model: "moonshotai/Kimi-K3", service: "tf", assessment: "deny"},
		{name: "native deny through observer", model: "gpt-6-astra", service: "native", assessment: "deny"},
		{name: "native allow after inspection", model: "gpt-6-astra", service: "native", assessment: "allow", allow: true, inspect: true},
		{name: "TF explicit Guardian override", model: "moonshotai/Kimi-K3", service: "tf", assessment: "allow", guardian: "moonshotai/Kimi-K3", allow: true},
		{name: "TF pending cancellation", model: "moonshotai/Kimi-K3", service: "tf", assessment: "allow", cancel: true},
		{name: "native pending cancellation", model: "gpt-6-astra", service: "native", assessment: "allow", cancel: true},
	} {
		t.Run(scenario.name, func(t *testing.T) {
			started := make(chan struct{}, 1)
			release := make(chan struct{})
			cancelled := make(chan struct{}, 1)
			reviewEnded := make(chan struct{}, 1)
			marker := filepath.Join(t.TempDir(), "review-command-ran")
			defer func() {
				select {
				case <-release:
				default:
					close(release)
				}
			}()
			var mu sync.Mutex
			mainCalls := map[string]int{}
			lastModel := map[string]string{}
			reviews := 0
			var originThread, originTurn string
			var observerConfig string
			handler := func(service string) http.HandlerFunc {
				return func(w http.ResponseWriter, r *http.Request) {
					var body map[string]any
					if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
						t.Error(err)
						return
					}
					metadata, _ := body["client_metadata"].(map[string]any)
					wantAuth := "Bearer fixture-secret"
					if service == "native" {
						wantAuth = "Bearer synthetic-native"
					}
					if r.Header.Get("Authorization") != wantAuth || r.Header.Get("X-TOFA-Launch") != "" {
						t.Error("review/main credential boundary changed")
					}
					if metadata["x-openai-subagent"] == "guardian" {
						mu.Lock()
						reviews++
						thread, turn := originThread, originTurn
						count := reviews
						mu.Unlock()
						if service != scenario.service {
							t.Errorf("review changed service: %s", service)
						}
						if metadata["x-codex-parent-thread-id"] != thread || metadata["parent_turn_id"] != turn {
							t.Error("review does not identify originating work")
						}
						wantGuardian := scenario.guardian
						if wantGuardian == "" {
							wantGuardian = "zai-org/GLM-5.3-Flash"
						}
						if service == "tf" && body["model"] != wantGuardian {
							t.Error("configured Guardian not selected")
						}
						if scenario.inspect && count > 1 {
							raw, _ := json.Marshal(body["input"])
							if !strings.Contains(string(raw), "origin-inspected") {
								t.Error("native inspection continuation missing")
							}
						}
						// Native reviewer model is chosen by the installed engine/catalog, not this fixture.
						w.Header().Set("Content-Type", "text/event-stream")
						w.WriteHeader(http.StatusOK)
						w.(http.Flusher).Flush()
						if count == 1 {
							started <- struct{}{}
						}
						if scenario.cancel {
							defer func() { reviewEnded <- struct{}{} }()
						}
						if scenario.cancel && scenario.service == "native" {
							<-r.Context().Done()
							cancelled <- struct{}{}
							<-release
							// Deliberately attempt an allow after cancellation; disconnected review
							// bytes must never authorize the interrupted command.
							emitFixtureModelResponse(w, fixtureMessage(`{"outcome":"allow"}`), fmt.Sprint(body["model"]))
							return
						}
						select {
						case <-release:
							if scenario.inspect && count == 1 {
								emitFixtureModelResponse(w, map[string]any{"id": "origin_inspect", "type": "function_call", "call_id": "origin_inspect_call", "name": "exec_command", "status": "completed", "arguments": `{"cmd":"printf origin-inspected","max_output_tokens":100}`}, fmt.Sprint(body["model"]))
								return
							}
							emitFixtureModelResponse(w, fixtureMessage(`{"outcome":"`+scenario.assessment+`"}`), fmt.Sprint(body["model"]))
						case <-r.Context().Done():
							cancelled <- struct{}{}
						}
						return
					}
					thread := fmt.Sprint(metadata["thread_id"])
					mu.Lock()
					mainCalls[thread]++
					lastModel[thread] = fmt.Sprint(body["model"])
					first := len(mainCalls) == 1 && mainCalls[thread] == 1
					if first {
						originThread = thread
						originTurn = fmt.Sprint(metadata["turn_id"])
					}
					mu.Unlock()
					if first {
						argsBytes, _ := json.Marshal(map[string]any{"cmd": "printf origin-review-approved | tee '" + marker + "'", "sandbox_permissions": "require_escalated", "justification": "Run the harmless review fixture.", "max_output_tokens": 100})
						args := string(argsBytes)
						item := map[string]any{"id": "origin_action", "type": "function_call", "call_id": "origin_call", "name": "exec_command", "arguments": args, "status": "completed"}
						if service == "native" {
							item = map[string]any{"id": "origin_action", "type": "custom_tool_call", "call_id": "origin_call", "namespace": "functions", "name": "exec", "input": "text(await tools.exec_command(" + args + "))", "status": "completed"}
						}
						emitFixtureModelResponse(w, item, fmt.Sprint(body["model"]))
						return
					}
					emitFixtureModelResponse(w, fixtureMessage("Fixture completed."), fmt.Sprint(body["model"]))
				}
			}
			e, child, stop := routedCandidateEngineGuardian(t, scenario.guardian, handler("tf"), handler("native"), func(t *testing.T) string {
				if scenario.cancel || scenario.guardian != "" {
					return candidateProxyObserver(t)
				}
				observerConfig = actualCandidateObserver(t, map[string]string{"moonshotai/Kimi-K3": "token_factory", "gpt-6-astra": "native"})
				return observerConfig
			})
			defer stop()
			defer e.close()
			thread := e.call("thread/start", map[string]any{"cwd": child.Cwd, "model": scenario.model, "approvalPolicy": "on-request", "approvalsReviewer": "auto_review", "sandbox": "read-only"})
			id := thread["thread"].(map[string]any)["id"].(string)
			turn := e.call("turn/start", map[string]any{"threadId": id, "input": []any{map[string]string{"type": "text", "text": "Run harmless fixture once and stop on failure."}}})
			select {
			case <-started:
			case <-time.After(12 * time.Second):
				if observerConfig != "" {
					if data, err := os.ReadFile(filepath.Join(filepath.Dir(observerConfig), "requests.json")); err == nil {
						t.Logf("owned observer records: %s", data)
					}
				}
				t.Fatal("origin review never reached owned upstream")
			}
			switched := "gpt-6-astra"
			if scenario.service == "native" {
				switched = "moonshotai/Kimi-K3"
			}
			e.call("thread/settings/update", map[string]any{"threadId": id, "model": switched})
			other := e.call("thread/start", map[string]any{"cwd": child.Cwd, "model": switched, "approvalPolicy": "never", "sandbox": "read-only"})
			e.turnText(other["thread"].(map[string]any)["id"].(string), "completed", "Concurrent work while review remains pending")
			if scenario.cancel {
				e.call("turn/interrupt", map[string]any{"threadId": id, "turnId": turn["turn"].(map[string]any)["id"]})
			} else {
				close(release)
			}
			executed := false
			for {
				message := e.read()
				if message["method"] == "item/completed" {
					item := message["params"].(map[string]any)["item"].(map[string]any)
					if item["type"] == "commandExecution" && item["exitCode"] == float64(0) && strings.Contains(fmt.Sprint(item["aggregatedOutput"]), "origin-review-approved") {
						executed = true
					}
				}
				if message["method"] == "turn/completed" {
					params := message["params"].(map[string]any)
					wantStatus := "completed"
					if scenario.cancel {
						wantStatus = "interrupted"
					}
					if params["threadId"] != id || params["turn"].(map[string]any)["status"] != wantStatus {
						t.Fatalf("unexpected originating turn outcome: %v", params)
					}
					break
				}
			}
			if scenario.cancel && scenario.service == "native" {
				// The relay invalidates this exact origin before native interruption.
				// Cancellation must reach the owned upstream before its late allow attempt.
				select {
				case <-cancelled:
				case <-time.After(5 * time.Second):
					t.Fatal("native originating review remained live after cancellation")
				}
				close(release)
				select {
				case <-reviewEnded:
				case <-time.After(5 * time.Second):
					t.Fatal("native review did not finish within bounded teardown")
				}
			} else if scenario.cancel {
				select {
				case <-cancelled:
				case <-time.After(5 * time.Second):
					t.Fatal("pending review cancellation did not propagate")
				}
			}
			if executed != scenario.allow {
				t.Fatalf("native execution gate: executed=%v want=%v", executed, scenario.allow)
			}
			e.turnText(id, "completed", "Subsequent turn uses selected service")
			e.close()
			_, markerErr := os.Stat(marker)
			if (markerErr == nil) != scenario.allow {
				t.Fatalf("command marker existence=%v want=%v", markerErr == nil, scenario.allow)
			}
			mu.Lock()
			defer mu.Unlock()
			if lastModel[id] != switched {
				t.Error("subsequent turn did not retain explicit selection")
			}
			wantReviews := 1
			if scenario.inspect {
				wantReviews = 2
			}
			if reviews != wantReviews {
				t.Fatalf("reviews=%d", reviews)
			}
		})
	}
}
