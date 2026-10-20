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
)

func TestDesktopNativeCandidateDeclaredObserverSwitching(t *testing.T) {
	var mu sync.Mutex
	var sequence []string
	var config string
	handler := func(service string) http.HandlerFunc {
		return func(w http.ResponseWriter, r *http.Request) {
			var body map[string]any
			if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
				t.Error(err)
				return
			}
			want := "Bearer fixture-secret"
			if service == "native" {
				want = "Bearer synthetic-native"
			}
			if r.Header.Get("Authorization") != want || r.Header.Get("X-TOFA-Launch") != "" {
				t.Error("scope changed credential boundary")
			}
			mu.Lock()
			sequence = append(sequence, service+":"+fmt.Sprint(body["model"]))
			step := len(sequence)
			mu.Unlock()
			raw, _ := json.Marshal(body["input"])
			if step > 1 && !strings.Contains(string(raw), "scoped-first-answer") {
				t.Error("service switch lost assistant context")
			}
			if step == 2 {
				emitFixtureModelResponse(w, map[string]any{"id": "scope_call", "type": "custom_tool_call", "call_id": "scope_tool", "namespace": "functions", "name": "exec", "input": "text('scoped-tool-result')", "status": "completed"}, fmt.Sprint(body["model"]))
				return
			}
			if step > 2 && !strings.Contains(string(raw), "scoped-tool-result") {
				t.Error("tool continuation lost result")
			}
			emitFixtureModelResponse(w, fixtureMessage("scoped-first-answer"), fmt.Sprint(body["model"]))
		}
	}
	models := []string{"moonshotai/Kimi-K3", "gpt-6-astra", "moonshotai/Kimi-K3"}
	prompts := []string{"Remember scoped synthetic value.", "Read scoped synthetic value with a tool.", "Finish scoped synthetic value."}
	services := map[string]string{"moonshotai/Kimi-K3": "token_factory", "gpt-6-astra": "native"}
	e, _, stop := routedCandidateEngine(t, handler("tf"), handler("native"), func(t *testing.T) string {
		turns := []any{}
		for i, model := range models {
			turns = append(turns, map[string]any{"model": model, "service": services[model], "prompt": prompts[i]})
		}
		config = actualCandidateObserverBudget(t, services, 8, map[string]any{"schema": "tofa-observer-scope-v1", "threads": []any{map[string]any{"label": "switch", "thread_id": nil, "workspace": "filled by owned fixture", "initial_user_messages_sha256": nil, "turns": turns}}})
		return config
	})
	t.Cleanup(func() {
		if t.Failed() {
			files, _ := filepath.Glob(filepath.Join(filepath.Dir(config), "rejected-request-*.json"))
			for _, path := range files {
				raw, _ := os.ReadFile(path)
				var body map[string]any
				json.Unmarshal(raw, &body)
				for _, value := range body["input"].([]any) {
					item, _ := value.(map[string]any)
					if item["role"] == "user" {
						t.Logf("owned rejected user context: %v", item)
					}
				}
			}
		}
	})
	defer stop()
	defer e.close()
	started := e.call("thread/start", map[string]any{"cwd": filepath.Join(filepath.Dir(config), "workspace"), "model": models[0], "approvalPolicy": "never", "sandbox": "read-only"})
	id := started["thread"].(map[string]any)["id"].(string)
	for i, model := range models {
		if i > 0 {
			e.call("thread/settings/update", map[string]any{"threadId": id, "model": model})
		}
		e.turnText(id, "completed", prompts[i])
	}
	saved := e.call("thread/read", map[string]any{"threadId": id, "includeTurns": true})["thread"].(map[string]any)
	if saved["id"] != id || len(saved["turns"].([]any)) != 3 {
		t.Fatal("scope changed native thread continuity")
	}
	e.close()
	stop()
	mu.Lock()
	defer mu.Unlock()
	if fmt.Sprint(sequence) != "[tf:moonshotai/Kimi-K3 native:gpt-6-astra native:gpt-6-astra tf:moonshotai/Kimi-K3]" {
		t.Fatalf("wrong declared route sequence: %v", sequence)
	}
	raw, err := os.ReadFile(filepath.Join(filepath.Dir(config), "requests.json"))
	if err != nil {
		t.Fatal(err)
	}
	var records []map[string]any
	if err = json.Unmarshal(raw, &records); err != nil {
		t.Fatal(err)
	}
	if len(records) != 4 {
		t.Fatalf("unexpected observer records: %s", raw)
	}
	for i, want := range []float64{0, 1, 1, 2} {
		if records[i]["scope"].(map[string]any)["turn_index"] != want || records[i]["completed"] != true {
			t.Fatalf("scope sequence/continuation failed: %s", raw)
		}
	}
}
