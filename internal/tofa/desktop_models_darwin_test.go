package tofa_test

import (
	"bytes"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"image"
	"image/png"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

func TestDesktopCatalogOffersAllEligibleModelsRegardlessOfDefault(t *testing.T) {
	for _, main := range []string{"deepseek-ai/DeepSeek-V4.1-Flash", "zai-org/GLM-5.3"} {
		t.Run(main, func(t *testing.T) {
			bundle, capture := desktopFixture(t, "ignore")
			app, output := adapterFixture(t, nil, nil)
			child, stop := liveDesktopFixture(t, app, bundle, capture, "--model", main, "--allow-unverified=false")
			data, err := os.ReadFile(child.CatalogPath)
			if err != nil {
				t.Fatal(err)
			}
			var catalog struct{ Models []map[string]any }
			if err := json.Unmarshal(data, &catalog); err != nil {
				t.Fatal(err)
			}
			entries := map[string]map[string]any{}
			for _, entry := range catalog.Models {
				entries[entry["slug"].(string)] = entry
			}
			for id, name := range map[string]string{
				"deepseek-ai/DeepSeek-V4.1-Flash":   "DeepSeek V4.1 Flash (Token Factory)",
				"zai-org/GLM-5.3":                   "GLM-5.3 (Token Factory)",
				"zai-org/GLM-5.3-Flash":             "GLM-5.3-Flash (Token Factory · Experimental)",
				"moonshotai/Kimi-K3":                "Kimi-K3 (Token Factory · Experimental)",
				"nvidia/Nemotron-3-Ultra-550b-a55b": "Nemotron 3 Ultra (Token Factory · Experimental)",
			} {
				entry := entries[id]
				if entry == nil {
					t.Errorf("available main %s missing from desktop picker", id)
					continue
				}
				if entry["visibility"] != "list" || entry["auto_review_model_override"] != "zai-org/GLM-5.3-Flash" {
					t.Errorf("main %s is not selectable with configured Guardian", id)
				}
				if entry["display_name"] != name {
					t.Errorf("incorrect picker name for %s: got %v, want %s", id, entry["display_name"], name)
				}
			}
			stop()
			if entries["fixture-model"] != nil || !strings.Contains(output.String(), "fixture-model: missing bundled model metadata") {
				t.Fatal("incompatible catalog entry must be explained without fabricated metadata")
			}
		})
	}
}

func TestDesktopBundledEngineContextPressureFailsWithoutReplacingHistory(t *testing.T) {
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
	var calls atomic.Int32
	app, output := adapterFixture(t, func(w http.ResponseWriter, r *http.Request) {
		calls.Add(1)
		emitFixtureResponse(w, fixtureMessage("Preserved response before context pressure."))
	}, nil)
	child, stop := liveDesktopFixture(t, app, bundle, capture, "--evaluation-observer", legacyProxyObserver(t), "--model", "deepseek-ai/DeepSeek-V4.1-Flash")
	e := openDesktopEngine(t, child)
	started := e.call("thread/start", map[string]any{"cwd": child.Cwd, "approvalPolicy": "never", "sandbox": "read-only"})
	id := started["thread"].(map[string]any)["id"].(string)
	e.turnText(id, "completed", "Preserve this original conversation")
	e.close()
	e = openDesktopEngine(t, child)
	// Use the native configurable threshold to force context pressure without
	// manufacturing a million-token conversation or paid inference.
	e.call("thread/resume", map[string]any{"threadId": id, "model": "zai-org/GLM-5.3", "config": map[string]any{"model_auto_compact_token_limit": 1}})
	e.call("turn/start", map[string]any{"threadId": id, "input": []any{map[string]string{"type": "text", "text": "Continue under the destination context constraint"}}})
	for {
		message := e.read()
		if message["method"] == "turn/completed" {
			turn := message["params"].(map[string]any)["turn"].(map[string]any)
			if turn["status"] != "failed" {
				t.Fatalf("context pressure silently continued: %v calls=%d", turn["status"], calls.Load())
			}
			break
		}
	}
	saved := e.call("thread/read", map[string]any{"threadId": id, "includeTurns": true})
	data, _ := json.Marshal(saved)
	if !bytes.Contains(data, []byte("Preserved response before context pressure.")) || !bytes.Contains(data, []byte("Preserve this original conversation")) {
		t.Fatal("context failure replaced original history")
	}
	e.close()
	stop()
	if calls.Load() != 1 || !strings.Contains(output.String(), "automatic context compaction is unsupported") {
		t.Fatalf("context handling did not fail explicitly before another main request: calls=%d", calls.Load())
	}
}

func TestDesktopBundledEngineTextOnlySwitchPreservesImageHistory(t *testing.T) {
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
	var mu sync.Mutex
	var inputs []bool
	app, output := adapterFixture(t, func(w http.ResponseWriter, r *http.Request) {
		var request struct {
			Model           string
			Input           json.RawMessage
			MaxOutputTokens int `json:"max_output_tokens"`
		}
		if err := json.NewDecoder(r.Body).Decode(&request); err != nil {
			t.Error(err)
			return
		}
		if request.Model == "deepseek-ai/DeepSeek-V4.1-Flash" && request.MaxOutputTokens != 32768 {
			t.Error("native image request omitted the qualified output-limit workaround")
		}
		if request.Model == "zai-org/GLM-5.3" && request.MaxOutputTokens != 0 {
			t.Error("text-only switch received an unrelated output limit")
		}
		mu.Lock()
		inputs = append(inputs, bytes.Contains(request.Input, []byte("input_image")))
		mu.Unlock()
		emitFixtureResponse(w, fixtureMessage("Synthetic image history response."))
	}, nil)
	child, stop := liveDesktopFixture(t, app, bundle, capture, "--evaluation-observer", legacyProxyObserver(t), "--model", "deepseek-ai/DeepSeek-V4.1-Flash")
	e := openDesktopEngine(t, child)
	thread := e.call("thread/start", map[string]any{"cwd": child.Cwd, "approvalPolicy": "never", "sandbox": "read-only"})
	id := thread["thread"].(map[string]any)["id"].(string)
	var pictureData bytes.Buffer
	if err := png.Encode(&pictureData, image.NewRGBA(image.Rect(0, 0, 32, 32))); err != nil {
		t.Fatal(err)
	}
	picture := "data:image/png;base64," + base64.StdEncoding.EncodeToString(pictureData.Bytes())
	e.call("turn/start", map[string]any{"threadId": id, "input": []any{map[string]string{"type": "text", "text": "Retain this synthetic image"}, map[string]string{"type": "image", "url": picture}}})
	for {
		m := e.read()
		if m["method"] == "turn/completed" {
			if m["params"].(map[string]any)["turn"].(map[string]any)["status"] != "completed" {
				t.Fatal("initial image turn failed")
			}
			break
		}
	}
	e.call("thread/settings/update", map[string]any{"threadId": id, "model": "zai-org/GLM-5.3"})
	e.call("turn/start", map[string]any{"threadId": id, "input": []any{map[string]string{"type": "text", "text": "Continue after a text-only selection"}}})
	var notices []any
	for {
		m := e.read()
		if m["method"] == "warning" || m["method"] == "error" {
			notices = append(notices, m["params"])
		}
		if m["method"] == "turn/completed" {
			if m["params"].(map[string]any)["turn"].(map[string]any)["status"] != "completed" {
				t.Fatalf("text-only switch failed: %v", notices)
			}
			break
		}
	}
	saved := e.call("thread/read", map[string]any{"threadId": id, "includeTurns": true})
	data, _ := json.Marshal(saved)
	if !bytes.Contains(data, []byte(picture)) {
		t.Fatal("text-only switch discarded persisted image history")
	}
	e.call("thread/settings/update", map[string]any{"threadId": id, "model": "deepseek-ai/DeepSeek-V4.1-Flash"})
	e.turnText(id, "completed", "Use the saved image again after switching back")
	e.close()
	stop()
	if !strings.Contains(output.String(), "saved images remain in history but are omitted for this model") {
		t.Error("image omission was not explained to the user")
	}
	mu.Lock()
	defer mu.Unlock()
	if fmt.Sprint(inputs) != "[true false true]" {
		t.Fatalf("image context did not follow model capabilities or recover: %v", inputs)
	}
}

func TestDesktopBundledEngineRecoversInterruptedAndUnavailableSelections(t *testing.T) {
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
	startedRequest, cancelledRequest := make(chan struct{}, 1), make(chan struct{}, 1)
	app, _ := adapterFixture(t, func(w http.ResponseWriter, r *http.Request) {
		var request struct{ Model string }
		if err := json.NewDecoder(r.Body).Decode(&request); err != nil {
			t.Error(err)
			return
		}
		switch request.Model {
		case "zai-org/GLM-5.3-Flash":
			startedRequest <- struct{}{}
			<-r.Context().Done()
			cancelledRequest <- struct{}{}
		case "deepseek-ai/DeepSeek-V4.1-Flash":
			emitFixtureResponse(w, fixtureMessage("Recovered explicit selection."))
		default:
			t.Errorf("unexpected upstream model: %s", request.Model)
		}
	}, nil)
	child, stop := liveDesktopFixture(t, app, bundle, capture, "--evaluation-observer", legacyProxyObserver(t), "--model", "deepseek-ai/DeepSeek-V4.1-Flash")
	e := openDesktopEngine(t, child)
	thread := e.call("thread/start", map[string]any{"cwd": child.Cwd, "approvalPolicy": "never", "sandbox": "read-only"})
	id := thread["thread"].(map[string]any)["id"].(string)
	e.call("thread/settings/update", map[string]any{"threadId": id, "model": "zai-org/GLM-5.3-Flash"})
	turn := e.call("turn/start", map[string]any{"threadId": id, "input": []any{map[string]string{"type": "text", "text": "Interrupt this synthetic request"}}})
	select {
	case <-startedRequest:
	case <-time.After(5 * time.Second):
		t.Fatal("selected model request never started")
	}
	// Native settings changes during a turn apply to subsequent turns; the
	// existing request retains its exact model until cancelled.
	e.call("thread/settings/update", map[string]any{"threadId": id, "model": "deepseek-ai/DeepSeek-V4.1-Flash"})
	e.call("turn/interrupt", map[string]any{"threadId": id, "turnId": turn["turn"].(map[string]any)["id"]})
	for {
		message := e.read()
		if message["method"] == "turn/completed" {
			if message["params"].(map[string]any)["turn"].(map[string]any)["status"] != "interrupted" {
				t.Fatal("turn was not interrupted")
			}
			break
		}
	}
	select {
	case <-cancelledRequest:
	case <-time.After(5 * time.Second):
		t.Fatal("interrupted selection stayed upstream")
	}
	e.turnText(id, "completed", "Use the selection made during the prior turn")
	e.call("thread/settings/update", map[string]any{"threadId": id, "model": "unavailable/model"})
	e.turnText(id, "failed", "Reject this unavailable selection without substitution")
	e.call("thread/settings/update", map[string]any{"threadId": id, "model": "deepseek-ai/DeepSeek-V4.1-Flash"})
	e.turnText(id, "completed", "Recover explicitly on the same conversation")
	e.close()
	stop()
}

func TestDesktopExperimentalDefaultNeedsNoOptIn(t *testing.T) {
	bundle, capture := desktopFixture(t, "normal")
	app, output := adapterFixture(t, nil, nil)
	if err := app.Run([]string{"launch", "codex-desktop", "--app-bundle", bundle, "--model", "zai-org/GLM-5.3-Flash"}); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(capture); err != nil {
		t.Fatal("experimental default did not launch:", err)
	}
	if !strings.Contains(output.String(), "Status: experimental (unverified)") {
		t.Fatal("experimental launch was not labelled")
	}
}

func TestDesktopBundledEngineSwitchesAndResumesConversationModels(t *testing.T) {
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
	var mu sync.Mutex
	var routed []string
	app, _ := adapterFixture(t, func(w http.ResponseWriter, r *http.Request) {
		var request struct {
			Model string
			Input []map[string]any
		}
		if err := json.NewDecoder(r.Body).Decode(&request); err != nil {
			t.Error(err)
			return
		}
		mu.Lock()
		routed = append(routed, request.Model)
		mu.Unlock()
		for i := len(request.Input) - 1; i >= 0; i-- {
			item := request.Input[i]
			if item["role"] == "user" {
				break
			}
			if item["type"] == "function_call_output" {
				if !strings.Contains(fmt.Sprint(item["output"]), "switch-tool-result") {
					t.Error("missing tool result after model selection")
				}
				emitFixtureResponse(w, fixtureMessage("Selected model completed the tool exchange."))
				return
			}
		}
		emitFixtureResponse(w, map[string]any{"id": "fc_switch", "type": "function_call", "call_id": "switch_call", "name": "exec_command", "arguments": `{"cmd":"printf switch-tool-result","max_output_tokens":100}`, "status": "completed"})
	}, nil)
	const initial = "deepseek-ai/DeepSeek-V4.1-Flash"
	const selected = "zai-org/GLM-5.3-Flash"
	child, stop := liveDesktopFixture(t, app, bundle, capture, "--evaluation-observer", legacyProxyObserver(t), "--model", initial, "--allow-unverified=false")
	e := openDesktopEngine(t, child)
	start := e.call("thread/start", map[string]any{"cwd": child.Cwd, "approvalPolicy": "never", "sandbox": "read-only"})
	id := start["thread"].(map[string]any)["id"].(string)
	e.turnText(id, "completed", "First turn before switching")
	e.call("thread/name/set", map[string]string{"threadId": id, "name": "Preserved switch title"})
	e.call("thread/settings/update", map[string]any{"threadId": id, "model": selected})
	e.turnText(id, "completed", "Continue this conversation with the selected model")
	e.turnText(id, "completed", "Keep using the selected model")
	other := e.call("thread/start", map[string]any{"cwd": child.Cwd, "approvalPolicy": "never", "sandbox": "read-only"})
	otherID := other["thread"].(map[string]any)["id"].(string)
	if other["model"] != initial {
		t.Fatal("conversation switch changed the launch default")
	}
	e.turnText(otherID, "completed", "Independent conversation keeps its main")
	e.close()
	stop()
	if err := os.Remove(capture); err != nil {
		t.Fatal(err)
	}
	child, stop = liveDesktopFixture(t, app, bundle, capture, "--evaluation-observer", legacyProxyObserver(t), "--model", "zai-org/GLM-5.3", "--allow-unverified=false")
	e = openDesktopEngine(t, child)
	resumed := e.call("thread/resume", map[string]any{"threadId": id, "model": nil, "modelProvider": nil})
	if resumed["model"] != selected || resumed["modelProvider"] != "nebius-tofa" {
		t.Fatalf("resume changed selection: %v %v", resumed["model"], resumed["modelProvider"])
	}
	e.turnText(id, "completed", "Continue after relaunch with a different default")
	saved := e.call("thread/read", map[string]any{"threadId": id, "includeTurns": true})["thread"].(map[string]any)
	if saved["id"] != id || saved["name"] != "Preserved switch title" || saved["cwd"] != child.Cwd || saved["modelProvider"] != "nebius-tofa" || len(saved["turns"].([]any)) != 4 {
		t.Fatal("model switch lost conversation identity, title, workspace, provider or turns")
	}
	e.close()
	stop()
	mu.Lock()
	defer mu.Unlock()
	want := []string{initial, initial, selected, selected, selected, selected, initial, initial, selected, selected}
	if fmt.Sprint(routed) != fmt.Sprint(want) {
		t.Fatalf("unexpected per-conversation routing: %v", routed)
	}
}
