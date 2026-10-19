package tofa_test

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

func TestDesktopDisclosesLaunchWideNaming(t *testing.T) {
	for _, candidate := range []bool{false, true} {
		t.Run(fmt.Sprint(candidate), func(t *testing.T) {
			bundle, capture := nativeCandidateFixture(t)
			app, output := adapterFixture(t, nil, nil)
			var flags []string
			if candidate {
				flags = []string{"--native-account-candidate", "--evaluation-observer", candidateProxyObserver(t)}
			}
			_, stop := liveDesktopFixture(t, app, bundle, capture, flags...)
			stop()
			if !strings.Contains(output.String(), "Automatic-title context, including native GPT context, is sent to Token Factory during this launch.") {
				t.Fatal("launch did not disclose the accepted title context destination")
			}
		})
	}
}

// Replay the installed Desktop helper's separate ephemeral thread, not an
// invented parent association. Actual renderer invocation/visibility is #142.
func startLaunchTitle(t *testing.T, e *desktopEngine, child capturedDesktop, text string) string {
	t.Helper()
	started := e.call("thread/start", map[string]any{
		"model": "gpt-6-luna", "modelProvider": nil,
		"allowProviderModelFallback": true, "cwd": child.Cwd,
		"approvalPolicy": "never", "permissions": ":read-only",
		"runtimeWorkspaceRoots": []any{}, "ephemeral": true, "threadSource": "thread_title",
		"config": map[string]any{
			"features.enable_fanout": false, "features.hooks": false,
			"features.multi_agent": false, "features.multi_agent_v2": false,
			"features.plugins": false, "features.shell_snapshot": false,
			"features.tool_suggest": false, "features.apps": false,
			"mcp_servers.codex_app":  map[string]any{"enabled": false, "command": ""},
			"model_reasoning_effort": "low", "web_search": "disabled",
		},
	})
	if started["model"] != "gpt-6-luna" || started["modelProvider"] != "tofa-native-router" {
		t.Fatalf("title helper must use launch default without parent migration: %v", started["modelProvider"])
	}
	id := started["thread"].(map[string]any)["id"].(string)
	var fixture map[string]any
	if err := json.Unmarshal(desktopTitleFixture(t), &fixture); err != nil {
		t.Fatal(err)
	}
	e.call("turn/start", map[string]any{
		"threadId": id, "turnTrigger": "thread_title", "model": nil,
		"permissions": ":read-only", "runtimeWorkspaceRoots": []any{},
		"input":        []any{map[string]any{"type": "text", "text": text, "text_elements": []any{}}},
		"outputSchema": titleFormat(fixture)["schema"],
	})
	return id
}

func finishLaunchTitle(t *testing.T, e *desktopEngine, id, wantStatus string) string {
	t.Helper()
	generated := ""
	for {
		message := e.read()
		params, _ := message["params"].(map[string]any)
		if params["threadId"] != id {
			continue
		}
		if message["method"] == "item/completed" {
			item := params["item"].(map[string]any)
			if item["type"] == "agentMessage" {
				generated, _ = item["text"].(string)
			}
		}
		if message["method"] == "turn/completed" {
			turn := params["turn"].(map[string]any)
			if turn["status"] != wantStatus {
				t.Fatalf("title status %v, want %s", turn, wantStatus)
			}
			return generated
		}
	}
}

func TestDesktopNativeCandidateNamesAllConversationCategories(t *testing.T) {
	const title = `{"title":"Launch wide title","description":"Independent automatic naming"}`
	var mu sync.Mutex
	counts := map[string]int{}
	handler := func(service string) http.HandlerFunc {
		return func(w http.ResponseWriter, r *http.Request) {
			if r.Method != http.MethodPost {
				w.WriteHeader(http.StatusUpgradeRequired)
				return
			}
			var body map[string]any
			if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
				t.Error(err)
				return
			}
			model := fmt.Sprint(body["model"])
			wantAuth := "Bearer fixture-secret"
			if service != "tf" {
				wantAuth = "Bearer synthetic-native"
			}
			if r.Header.Get("Authorization") != wantAuth || r.Header.Get("X-TOFA-Launch") != "" || r.Header.Get("ChatGPT-Account-Id") != "" {
				t.Error("title/Main credentials crossed destinations")
			}
			mu.Lock()
			counts[service+":"+model]++
			mu.Unlock()
			if model == "nvidia/Nemotron-3_5-Lightning" {
				if service != "tf" || body["tools"] != nil || body["instructions"] != nil {
					t.Error("naming destination or contract changed")
				}
				metadata, _ := body["client_metadata"].(map[string]any)
				if metadata["x-codex-parent-thread-id"] != nil || metadata["parent_turn_id"] != nil {
					t.Error("helper unexpectedly supplied a parent; revisit measured contract")
				}
				emitFixtureModelResponse(w, fixtureMessage(title), model)
				return
			}
			emitFixtureModelResponse(w, fixtureMessage("preserved-main-answer"), model)
		}
	}
	e, child, stop := routedCandidateEngine(t, handler("tf"), handler("routed-native"), func(t *testing.T) string {
		return actualCandidateObserver(t, map[string]string{"moonshotai/Kimi-K3": "token_factory", "gpt-6-astra": "native"})
	})
	defer stop()
	direct := httptest.NewServer(handler("direct-native"))
	defer direct.Close()
	e.close()
	override := "openai_base_url=" + fmt.Sprintf("%q", direct.URL)
	e = openDesktopEngine(t, child, override)
	existing := map[string]string{}
	for _, tc := range []struct{ category, provider, model string }{
		{"existing native", "openai", "gpt-6-astra"}, {"existing legacy", "nebius-tofa", "moonshotai/Kimi-K3"},
	} {
		started := e.call("thread/start", map[string]any{"cwd": child.Cwd, "model": tc.model, "modelProvider": tc.provider,
			"approvalPolicy": "never", "sandbox": "read-only", "historyMode": "paginated"})
		id := started["thread"].(map[string]any)["id"].(string)
		e.turnText(id, "completed", "Earlier saved "+tc.category+" work")
		existing[tc.category] = id
	}
	e.close()
	e = openDesktopEngine(t, child, override)
	for _, tc := range []struct{ category, provider, model string }{
		{"new routed TF", "tofa-native-router", "moonshotai/Kimi-K3"},
		{"new routed native", "tofa-native-router", "gpt-6-astra"},
		{"existing native", "openai", "gpt-6-astra"}, {"existing legacy", "nebius-tofa", "moonshotai/Kimi-K3"},
	} {
		id := existing[tc.category]
		var started map[string]any
		if id == "" {
			started = e.call("thread/start", map[string]any{"cwd": child.Cwd, "model": tc.model, "approvalPolicy": "never", "sandbox": "read-only", "historyMode": "paginated"})
			id = started["thread"].(map[string]any)["id"].(string)
		} else {
			started = e.call("thread/resume", map[string]any{"threadId": id, "model": nil, "modelProvider": nil})
		}
		if started["modelProvider"] != tc.provider {
			t.Fatalf("%s provider changed", tc.category)
		}
		e.turnText(id, "completed", "Continue "+tc.category+" work")
		titleID := startLaunchTitle(t, e, child, "Generate a title and description for "+tc.category+" work.")
		if got := finishLaunchTitle(t, e, titleID, "completed"); got != title {
			t.Fatalf("%s title result changed: %q", tc.category, got)
		}
		saved := e.call("thread/read", map[string]any{"threadId": id, "includeTurns": true})["thread"].(map[string]any)
		wantTurns := 1
		if existing[tc.category] != "" {
			wantTurns = 2
		}
		if saved["id"] != id || saved["modelProvider"] != tc.provider || len(saved["turns"].([]any)) != wantTurns {
			t.Fatalf("%s Main identity/history changed by naming", tc.category)
		}
	}
	e.close()
	stop()
	mu.Lock()
	defer mu.Unlock()
	for key, want := range map[string]int{"tf:nvidia/Nemotron-3_5-Lightning": 4, "tf:moonshotai/Kimi-K3": 3, "direct-native:gpt-6-astra": 2, "routed-native:gpt-6-astra": 1} {
		if counts[key] != want {
			t.Fatalf("%s requests=%d want=%d", key, counts[key], want)
		}
	}
	if len(counts) != 4 {
		t.Fatalf("unexpected route: %v", counts)
	}
}

func TestDesktopNativeCandidateNamingIndependentOfPendingMainAndReview(t *testing.T) {
	for _, namingStatus := range []int{200, 503} {
		t.Run(fmt.Sprint(namingStatus), func(t *testing.T) {
			nativeStarted, reviewStarted := make(chan struct{}, 1), make(chan struct{}, 1)
			release := make(chan struct{})
			var releaseOnce sync.Once
			defer releaseOnce.Do(func() { close(release) })
			var mainCalls, reviewCalls, titleCalls, nativeCalls atomic.Int32
			tf := func(w http.ResponseWriter, r *http.Request) {
				var body map[string]any
				if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
					t.Error(err)
					return
				}
				if r.Header.Get("Authorization") != "Bearer fixture-secret" || r.Header.Get("X-TOFA-Launch") != "" || r.Header.Get("ChatGPT-Account-Id") != "" {
					t.Error("native or launch credentials escaped into naming/review")
				}
				switch body["model"] {
				case "nvidia/Nemotron-3_5-Lightning":
					titleCalls.Add(1)
					if namingStatus != 200 {
						http.Error(w, "synthetic naming unavailable", namingStatus)
						return
					}
					emitFixtureModelResponse(w, fixtureMessage(`{"title":"Independent naming","description":"Title during pending work"}`), "nvidia/Nemotron-3_5-Lightning")
				case "zai-org/GLM-5.3-Flash":
					reviewCalls.Add(1)
					reviewStarted <- struct{}{}
					select {
					case <-release:
					case <-r.Context().Done():
						return
					}
					emitFixtureModelResponse(w, fixtureMessage(`{"outcome":"deny","rationale":"Synthetic denial"}`), "zai-org/GLM-5.3-Flash")
				case "moonshotai/Kimi-K3":
					if mainCalls.Add(1) == 1 {
						emitFixtureResponse(w, map[string]any{"id": "naming-review-command", "type": "function_call", "call_id": "naming-review-call", "name": "exec_command", "status": "completed",
							"arguments": `{"cmd":"printf naming-review-must-not-execute","sandbox_permissions":"require_escalated","justification":"Synthetic denied command for naming independence.","max_output_tokens":100}`})
					} else {
						emitFixtureResponse(w, fixtureMessage("Main work remains completed"))
					}
				default:
					t.Errorf("unexpected TF model %v", body["model"])
				}
			}
			native := func(w http.ResponseWriter, r *http.Request) {
				io.Copy(io.Discard, r.Body)
				if r.Header.Get("Authorization") != "Bearer synthetic-native" || r.Header.Get("X-TOFA-Launch") != "" {
					t.Error("native credential separation changed")
				}
				nativeCalls.Add(1)
				nativeStarted <- struct{}{}
				select {
				case <-release:
				case <-r.Context().Done():
					return
				}
				emitFixtureModelResponse(w, fixtureMessage("Native work remains completed"), "gpt-6-astra")
			}
			e, child, stop := routedCandidateEngine(t, tf, native)
			defer stop()
			defer e.close()
			nativeThread := e.call("thread/start", map[string]any{"cwd": child.Cwd, "model": "gpt-6-astra", "approvalPolicy": "never", "sandbox": "read-only"})
			nativeID := nativeThread["thread"].(map[string]any)["id"].(string)
			e.call("turn/start", map[string]any{"threadId": nativeID, "input": []any{map[string]string{"type": "text", "text": "Pending native work"}}})
			select {
			case <-nativeStarted:
			case <-time.After(10 * time.Second):
				t.Fatal("native Main did not start")
			}
			tfThread := e.call("thread/start", map[string]any{"cwd": child.Cwd, "model": "moonshotai/Kimi-K3", "approvalPolicy": "on-request", "approvalsReviewer": "auto_review", "sandbox": "read-only"})
			tfID := tfThread["thread"].(map[string]any)["id"].(string)
			e.call("turn/start", map[string]any{"threadId": tfID, "input": []any{map[string]string{"type": "text", "text": "Request the synthetic command once; stop after denial"}}})
			select {
			case <-reviewStarted:
			case <-time.After(10 * time.Second):
				t.Fatal("automatic Guardian did not start")
			}
			titleID := startLaunchTitle(t, e, child, "Generate a title and description while unrelated work is pending.")
			status := "completed"
			if namingStatus != 200 {
				status = "failed"
			}
			got := finishLaunchTitle(t, e, titleID, status)
			if status == "completed" && !strings.Contains(got, "Independent naming") {
				t.Fatal("naming result missing")
			}
			if titleCalls.Load() != 1 || mainCalls.Load() != 1 || reviewCalls.Load() != 1 || nativeCalls.Load() != 1 {
				t.Fatal("naming retried, fell back, or disturbed pending work")
			}
			releaseOnce.Do(func() { close(release) })
			pending := map[string]bool{nativeID: true, tfID: true}
			for len(pending) > 0 {
				message := e.read()
				params, _ := message["params"].(map[string]any)
				if message["method"] == "item/completed" {
					item := params["item"].(map[string]any)
					if item["type"] == "commandExecution" && item["exitCode"] == float64(0) {
						t.Fatal("denied command executed")
					}
				}
				if message["method"] == "turn/completed" {
					id, _ := params["threadId"].(string)
					if !pending[id] {
						continue
					}
					if params["turn"].(map[string]any)["status"] != "completed" {
						t.Fatal("naming outcome corrupted Main completion")
					}
					delete(pending, id)
				}
			}
			e.close()
			stop()
			if titleCalls.Load() != 1 || reviewCalls.Load() != 1 || nativeCalls.Load() != 1 || mainCalls.Load() != 2 {
				t.Fatal("unexpected retry, fallback, or extra work after naming")
			}
		})
	}
}
