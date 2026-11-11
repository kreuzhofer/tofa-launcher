package tofa_test

import (
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// Exercise the native event boundary with the provider's observed item lifecycle.
// No generated provider reasoning or ordinary user profile is used here.
func TestDesktopBundledEngineKeepsReasoningSeparate(t *testing.T) {
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
	requests := make(chan json.RawMessage, 4)
	app, _ := adapterFixture(t, func(w http.ResponseWriter, r *http.Request) {
		var body map[string]json.RawMessage
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			t.Error(err)
			return
		}
		select {
		case requests <- body["reasoning"]:
		default:
			t.Error("unexpected extra provider request")
			http.Error(w, "request budget exceeded", http.StatusTooManyRequests)
			return
		}
		emitReasoningFixture(w)
	}, nil)
	child, stop := liveDesktopFixture(t, app, bundle, capture, "--model", "zai-org/GLM-5.3", "--evaluation-observer", legacyProxyObserver(t))
	defer stop()
	e := openDesktopEngine(t, child)
	defer e.close()
	started := e.call("thread/start", map[string]any{"cwd": child.Cwd, "approvalPolicy": "never", "sandbox": "read-only"})
	id := started["thread"].(map[string]any)["id"].(string)
	t.Logf("native thread reasoning effort: %v", started["reasoningEffort"])
	// The desktop's model preset supplies None when the catalog has no default.
	e.call("turn/start", map[string]any{"threadId": id, "effort": "none", "input": []any{map[string]string{"type": "text", "text": "Synthetic reasoning channel check"}}})
	var thought, summary, answer strings.Builder
	for {
		message := e.read()
		params, _ := message["params"].(map[string]any)
		switch message["method"] {
		case "item/reasoning/textDelta":
			thought.WriteString(params["delta"].(string))
		case "item/reasoning/summaryTextDelta":
			summary.WriteString(params["delta"].(string))
		case "item/agentMessage/delta":
			answer.WriteString(params["delta"].(string))
		case "turn/completed":
			if params["turn"].(map[string]any)["status"] != "completed" {
				t.Fatalf("turn failed: %v", params)
			}
			if thought.String() != "Synthetic reasoning." {
				t.Errorf("native reasoning channel: %q", thought.String())
			}
			if summary.String() != "Synthetic summary." {
				t.Errorf("native summary channel: %q", summary.String())
			}
			if answer.String() != "Literal </think> example." {
				t.Errorf("native answer channel: %q", answer.String())
			}
			var sent map[string]any
			if raw := <-requests; len(raw) != 0 {
				if err := json.Unmarshal(raw, &sent); err != nil {
					t.Fatal(err)
				}
			}
			if _, present := sent["effort"]; present {
				t.Errorf("unsupported native None reached provider: %v", sent)
			}
			e.close()
			e = openDesktopEngine(t, child)
			resumed := e.call("thread/resume", map[string]any{"threadId": id})
			if resumed["thread"].(map[string]any)["id"] != id || resumed["model"] != "zai-org/GLM-5.3" {
				t.Fatal("reasoning conversation identity changed on resume")
			}
			read := e.call("thread/read", map[string]any{"threadId": id, "includeTurns": true})
			retained := false
			for _, turn := range read["thread"].(map[string]any)["turns"].([]any) {
				for _, value := range turn.(map[string]any)["items"].([]any) {
					item := value.(map[string]any)
					if item["type"] == "reasoning" && strings.Contains(fmt.Sprint(item["content"]), "Synthetic reasoning.") && strings.Contains(fmt.Sprint(item["summary"]), "Synthetic summary.") {
						retained = true
					}
				}
			}
			if !retained {
				t.Fatal("resume did not retain distinct reasoning content and summary")
			}
			e.turnText(id, "completed", "Continue the synthetic reasoning conversation")
			if raw := <-requests; strings.Contains(string(raw), `"none"`) {
				t.Errorf("resumed None reached provider: %s", raw)
			}
			e.close()
			return
		}
	}
}
