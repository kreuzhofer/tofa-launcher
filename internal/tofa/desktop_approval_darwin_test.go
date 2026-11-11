package tofa_test

import (
	"encoding/json"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

func TestDesktopBundledEngineAutomaticApproval(t *testing.T) {
	installed := os.Getenv("TOFA_TEST_DESKTOP_ENGINE")
	if installed == "" {
		t.Skip("set TOFA_TEST_DESKTOP_ENGINE")
	}
	for _, scenario := range []struct {
		name, assessment string
		main, guardian   string
		allow, inspect   bool
		status           int
	}{
		{"allow", `{"outcome":"allow"}`, "deepseek-ai/DeepSeek-V4.1-Flash", "zai-org/GLM-5.3-Flash", true, false, 200},
		{"default Guardian for Kimi", `{"outcome":"allow"}`, "moonshotai/Kimi-K3", "zai-org/GLM-5.3-Flash", true, false, 200},
		{"distinct Kimi Guardian", `{"outcome":"allow"}`, "deepseek-ai/DeepSeek-V4.1-Flash", "moonshotai/Kimi-K3", true, false, 200},
		{"allow after inspection", `{"outcome":"allow"}`, "moonshotai/Kimi-K3", "moonshotai/Kimi-K3", true, true, 200},
		{"deny", `{"outcome":"deny"}`, "zai-org/GLM-5.3", "zai-org/GLM-5.3-Flash", false, false, 200},
		{"invalid assessment", `{"outcome":"maybe"}`, "nvidia/Nemotron-3-Ultra-550b-a55b", "zai-org/GLM-5.3-Flash", false, false, 200},
		{"provider failure", "", "zai-org/GLM-5.3-Flash", "zai-org/GLM-5.3-Flash", false, false, 503},
		{"cancel review", "", "deepseek-ai/DeepSeek-V4.1-Flash", "zai-org/GLM-5.3-Flash", false, false, 0},
		{"native review deadline", "", "deepseek-ai/DeepSeek-V4.1-Flash", "zai-org/GLM-5.3-Flash", false, false, -1},
	} {
		t.Run(scenario.name, func(t *testing.T) {
			bundle, capture := desktopFixture(t, "ignore")
			engine := filepath.Join(bundle, "Contents/Resources/codex")
			if err := os.Remove(engine); err != nil {
				t.Fatal(err)
			}
			if err := os.Symlink(installed, engine); err != nil {
				t.Fatal(err)
			}
			var mainRequests, reviewRequests atomic.Int32
			var inspected atomic.Bool
			reviewStarted := make(chan time.Time, 2)
			reviewCancelled := make(chan struct{}, 2)
			app, output := adapterFixture(t, func(w http.ResponseWriter, r *http.Request) {
				var request struct {
					Model        string
					Tools        []json.RawMessage
					Instructions string
					Text         map[string]json.RawMessage
					Input        []struct {
						Type   string
						Output json.RawMessage
					}
				}
				if err := json.NewDecoder(r.Body).Decode(&request); err != nil {
					t.Error(err)
					return
				}
				if len(request.Tools) == 3 {
					count := reviewRequests.Add(1)
					if request.Model != scenario.guardian {
						t.Errorf("Guardian identity: %s", request.Model)
					}
					if scenario.guardian == "moonshotai/Kimi-K3" && (request.Text["format"] != nil || !strings.Contains(request.Instructions, `"outcome"`)) {
						t.Error("review assessment guidance was lost or still uses constrained decoding")
					}
					if scenario.guardian != "moonshotai/Kimi-K3" && request.Text["format"] == nil {
						t.Error("non-Kimi reviewer lost native assessment schema")
					}
					if scenario.status <= 0 {
						reviewStarted <- time.Now()
						<-r.Context().Done()
						reviewCancelled <- struct{}{}
						return
					}
					if scenario.status != 200 {
						w.WriteHeader(scenario.status)
						return
					}
					if scenario.inspect && count == 1 {
						emitFixtureResponse(w, map[string]any{"id": "fc_inspect", "type": "function_call", "call_id": "call_inspect", "name": "exec_command", "status": "completed", "arguments": `{"cmd":"printf tofa-review-inspection","max_output_tokens":100}`})
						return
					}
					for _, item := range request.Input {
						if item.Type == "function_call_output" && strings.Contains(string(item.Output), "tofa-review-inspection") && strings.Contains(string(item.Output), "Process exited with code 0") {
							inspected.Store(true)
						}
					}
					emitFixtureResponse(w, fixtureMessage(scenario.assessment))
				} else if mainRequests.Add(1) == 1 {
					if request.Model != scenario.main {
						t.Errorf("main identity: %s", request.Model)
					}
					emitFixtureResponse(w, map[string]any{
						"id": "fc_desktop_review", "type": "function_call", "call_id": "call_desktop_review",
						"name": "exec_command", "status": "completed",
						"arguments": `{"cmd":"printf tofa-desktop-approved","sandbox_permissions":"require_escalated","justification":"Run the harmless desktop qualification fixture.","max_output_tokens":100}`,
					})
				} else {
					emitFixtureResponse(w, fixtureMessage("Fixture complete."))
				}
			}, nil)
			child, stop := liveDesktopFixture(t, app, bundle, capture, "--evaluation-observer", legacyProxyObserver(t), "--model", "deepseek-ai/DeepSeek-V4.1-Flash", "--guardian-model", scenario.guardian)
			e := openDesktopEngine(t, child)
			started := e.call("thread/start", map[string]any{
				"cwd": child.Cwd, "approvalPolicy": "on-request", "approvalsReviewer": "auto_review", "sandbox": "read-only",
			})
			if started["approvalPolicy"] != "on-request" || started["approvalsReviewer"] != "auto_review" {
				t.Fatalf("desktop approval settings changed: %v", started)
			}
			id := started["thread"].(map[string]any)["id"].(string)
			e.call("thread/settings/update", map[string]any{"threadId": id, "model": scenario.main})
			turn := e.call("turn/start", map[string]any{"threadId": id, "input": []any{map[string]string{"type": "text", "text": "Run the harmless fixture once. Stop if review fails."}}})
			var reviewStart time.Time
			if scenario.status <= 0 {
				select {
				case reviewStart = <-reviewStarted:
				case <-time.After(10 * time.Second):
					t.Fatal("review never started")
				}
				if scenario.status == 0 {
					e.call("turn/interrupt", map[string]any{"threadId": id, "turnId": turn["turn"].(map[string]any)["id"]})
				}
			}
			executed := false
			for {
				message := e.read()
				if message["method"] == "item/completed" {
					item := message["params"].(map[string]any)["item"].(map[string]any)
					if item["type"] == "commandExecution" && item["exitCode"] == float64(0) && strings.Contains(item["aggregatedOutput"].(string), "tofa-desktop-approved") {
						executed = true
					}
				}
				if message["method"] == "turn/completed" {
					params := message["params"].(map[string]any)
					wantStatus := "completed"
					if scenario.status == 0 {
						wantStatus = "interrupted"
					}
					if params["threadId"] != id || params["turn"].(map[string]any)["status"] != wantStatus {
						t.Fatalf("unexpected main turn result: %v", params)
					}
					break
				}
			}
			if scenario.status <= 0 {
				select {
				case <-reviewCancelled:
				case <-time.After(3 * time.Second):
					t.Fatal("cancelled review remained upstream")
				}
				elapsed := time.Since(reviewStart)
				if scenario.status == -1 && (elapsed < 85*time.Second || elapsed > 100*time.Second) {
					t.Fatalf("native 90-second deadline changed: %s", elapsed)
				}
			}
			e.close()
			stop()
			wantReviews := int32(1)
			if scenario.inspect {
				wantReviews = 2
			}
			// Native assessment parsing retries malformed decisions. Provider-error
			// retry counts belong to the engine and can change across compatible
			// releases; the required contract is a bounded failure with no execution.
			if scenario.name == "invalid assessment" {
				wantReviews = 3
			}
			if scenario.status == 503 {
				if reviewRequests.Load() < 1 {
					t.Fatal("provider-failure fixture never reached the Guardian")
				}
				t.Logf("native provider-failure review attempts: %d", reviewRequests.Load())
			} else if reviewRequests.Load() != wantReviews {
				t.Fatalf("unexpected review count: got %d, want %d", reviewRequests.Load(), wantReviews)
			}
			if executed != scenario.allow || inspected.Load() != scenario.inspect {
				t.Fatalf("desktop automatic approval did not reach a reviewer and execute its approved action: reviews=%d executed=%v\n%s", reviewRequests.Load(), executed, output.String())
			}
			if !strings.Contains(output.String(), "Automatic review for all eligible Token Factory conversations uses "+scenario.guardian) {
				t.Fatal("review model selection was not announced")
			}
		})
	}
}

func TestDesktopBundledEngineResumeUsesLaunchGuardian(t *testing.T) {
	installed := os.Getenv("TOFA_TEST_DESKTOP_ENGINE")
	if installed == "" {
		t.Skip("set TOFA_TEST_DESKTOP_ENGINE")
	}
	bundle, capture := desktopFixture(t, "ignore")
	engine := filepath.Join(bundle, "Contents/Resources/codex")
	if err := os.Remove(engine); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(installed, engine); err != nil {
		t.Fatal(err)
	}
	var guardian atomic.Value
	var mainCalls, reviews atomic.Int32
	app, output := adapterFixture(t, func(w http.ResponseWriter, r *http.Request) {
		var request struct {
			Model string
			Tools []json.RawMessage
		}
		if err := json.NewDecoder(r.Body).Decode(&request); err != nil {
			t.Error(err)
			return
		}
		if len(request.Tools) == 3 {
			if request.Model != guardian.Load().(string) {
				t.Error("resumed conversation retained the old Guardian")
			}
			reviews.Add(1)
			emitFixtureResponse(w, fixtureMessage(`{"outcome":"allow"}`))
		} else {
			if request.Model != "deepseek-ai/DeepSeek-V4.1-Flash" {
				t.Error("resumed conversation changed main")
			}
			if mainCalls.Add(1)%2 == 1 {
				emitFixtureResponse(w, map[string]any{"id": "fc_resume", "type": "function_call", "call_id": "call_resume", "name": "exec_command", "status": "completed", "arguments": `{"cmd":"printf tofa-resumed-approved","sandbox_permissions":"require_escalated","justification":"Synthetic resumed review fixture.","max_output_tokens":100}`})
			} else {
				emitFixtureResponse(w, fixtureMessage("Resumed review complete."))
			}
		}
	}, nil)
	var id string
	for _, selected := range []string{"moonshotai/Kimi-K3", "zai-org/GLM-5.3-Flash"} {
		guardian.Store(selected)
		child, stop := liveDesktopFixture(t, app, bundle, capture, "--evaluation-observer", legacyProxyObserver(t), "--model", "deepseek-ai/DeepSeek-V4.1-Flash", "--guardian-model", selected)
		e := openDesktopEngine(t, child)
		if id == "" {
			started := e.call("thread/start", map[string]any{"cwd": child.Cwd, "approvalPolicy": "on-request", "approvalsReviewer": "auto_review", "sandbox": "read-only"})
			id = started["thread"].(map[string]any)["id"].(string)
		} else {
			resumed := e.call("thread/resume", map[string]any{"threadId": id, "model": nil, "modelProvider": nil})
			if resumed["model"] != "deepseek-ai/DeepSeek-V4.1-Flash" || resumed["modelProvider"] != "nebius-tofa" {
				t.Fatal("resume changed conversation identity")
			}
		}
		e.call("turn/start", map[string]any{"threadId": id, "input": []any{map[string]string{"type": "text", "text": "Execute the synthetic fixture."}}})
		executed := false
		for {
			message := e.read()
			if message["method"] == "item/completed" {
				item := message["params"].(map[string]any)["item"].(map[string]any)
				if item["type"] == "commandExecution" && item["exitCode"] == float64(0) && strings.Contains(item["aggregatedOutput"].(string), "tofa-resumed-approved") {
					executed = true
				}
			}
			if message["method"] == "turn/completed" {
				break
			}
		}
		e.close()
		stop()
		if !strings.Contains(output.String(), "Guardian: "+selected) {
			t.Fatal("effective resume Guardian was not displayed")
		}
		if !executed {
			t.Fatal("launch Guardian did not approve resumed execution")
		}
		if err := os.Remove(capture); err != nil {
			t.Fatal(err)
		}
	}
	if reviews.Load() != 2 || mainCalls.Load() != 4 {
		t.Fatal("missing main/review round trip on resume")
	}
}
