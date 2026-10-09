package tofa_test

import (
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync/atomic"
	"testing"
)

func TestDesktopSupportedMainLaunchesWithoutExperimentalOptIn(t *testing.T) {
	for _, main := range []string{"deepseek-ai/DeepSeek-V4.1-Flash", "zai-org/GLM-5.3"} {
		t.Run(main, func(t *testing.T) {
			bundle, capture := desktopFixture(t, "normal")
			app, output := adapterFixture(t, nil, nil)
			if err := app.Run([]string{"launch", "codex-desktop", "--app-bundle", bundle, "--model", main}); err != nil {
				t.Fatal(err)
			}
			if _, err := os.Stat(capture); err != nil {
				t.Fatal("supported selection did not launch desktop:", err)
			}
			for _, want := range []string{"Main: " + main, "Guardian: zai-org/GLM-5.3-Flash", "Status: supported", "Route: adapted", "Naming: nvidia/Nemotron-3_5-Lightning"} {
				if !strings.Contains(output.String(), want) {
					t.Errorf("missing %q in %s", want, output.String())
				}
			}
		})
	}
}

func TestDesktopExplicitMainAndGuardianMetadata(t *testing.T) {
	for _, model := range []struct {
		id      string
		context float64
		images  bool
	}{
		{"zai-org/GLM-5.3-Flash", 1024000, true},
		{"deepseek-ai/DeepSeek-V4.1-Flash", 1048000, true},
		{"zai-org/GLM-5.3", 1024000, false},
		{"moonshotai/Kimi-K3", 1024000, true},
		{"nvidia/Nemotron-3-Ultra-550b-a55b", 1048576, false},
	} {
		t.Run(model.id, func(t *testing.T) {
			bundle, capture := desktopFixture(t, "ignore")
			app, output := adapterFixture(t, nil, nil)
			child, stop := liveDesktopFixture(t, app, bundle, capture, "--model", model.id)
			data, err := os.ReadFile(child.CatalogPath)
			if err != nil {
				t.Fatal(err)
			}
			var catalog struct{ Models []map[string]any }
			if err := json.Unmarshal(data, &catalog); err != nil {
				t.Fatal(err)
			}
			found := false
			for _, entry := range catalog.Models {
				if entry["slug"] != model.id {
					continue
				}
				found = true
				modalities := entry["input_modalities"].([]any)
				if entry["context_window"] != model.context || (len(modalities) == 2) != model.images || entry["auto_review_model_override"] != "zai-org/GLM-5.3-Flash" {
					t.Fatalf("incorrect model-specific metadata: %v", entry)
				}
			}
			stop()
			if !found {
				t.Fatal("selected main missing from engine catalog")
			}
			status := "experimental (unverified)"
			if model.id == "deepseek-ai/DeepSeek-V4.1-Flash" || model.id == "zai-org/GLM-5.3" {
				status = "supported"
			}
			for _, want := range []string{"Main: " + model.id, "Guardian: zai-org/GLM-5.3-Flash", "Status: " + status, "Route: adapted"} {
				if !strings.Contains(output.String(), want) {
					t.Fatalf("missing %q in %s", want, output.String())
				}
			}
		})
	}
}

func TestDesktopRejectsInvalidSelectionBeforeStartingTarget(t *testing.T) {
	for _, tc := range []struct {
		name, main, catalog, want string
		flags                     []string
	}{
		{name: "missing main", want: "explicit --model"},
		{name: "unavailable main", main: "absent/model", want: "main model absent/model: not available"},
		{name: "main metadata", main: "fixture-model", want: "main model fixture-model: missing bundled model metadata"},
		{name: "unavailable default", main: "moonshotai/Kimi-K3", catalog: `{"data":[{"id":"moonshotai/Kimi-K3"}]}`, want: "Guardian model zai-org/GLM-5.3-Flash: not available"},
		{name: "unavailable override", main: "moonshotai/Kimi-K3", flags: []string{"--guardian-model", "absent/model"}, want: "Guardian model absent/model: not available"},
		{name: "Guardian metadata", main: "moonshotai/Kimi-K3", flags: []string{"--guardian-model", "fixture-model"}, want: "Guardian model fixture-model: missing bundled model metadata"},
		{name: "empty Guardian", main: "moonshotai/Kimi-K3", flags: []string{"--guardian-model", ""}, want: "valid model ID"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			bundle, capture := desktopFixture(t, "normal")
			app, _ := adapterFixture(t, nil, nil)
			if tc.catalog != "" {
				server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { io.WriteString(w, tc.catalog) }))
				defer server.Close()
				app.Endpoint = server.URL
			}
			args := append([]string{"launch", "codex-desktop", "--app-bundle", bundle, "--model", tc.main, "--allow-unverified"}, tc.flags...)
			if err := app.Run(args); err == nil || !strings.Contains(err.Error(), tc.want) {
				t.Fatalf("want %q, got %v", tc.want, err)
			}
			if _, err := os.Stat(capture); !os.IsNotExist(err) {
				t.Fatal("invalid selection started target")
			}
		})
	}
}

func TestDesktopNamingAndGuardianLanesRemainScoped(t *testing.T) {
	bundle, capture := desktopFixture(t, "ignore")
	var upstream atomic.Int32
	app, output := adapterFixture(t, func(w http.ResponseWriter, r *http.Request) { upstream.Add(1); io.WriteString(w, "ok") }, nil)
	child, stop := liveDesktopFixture(t, app, bundle, capture, "--model", "deepseek-ai/DeepSeek-V4.1-Flash")
	for _, tc := range []struct{ name, body, want string }{
		{"malformed model", `{"model":"deepseek-ai/DeepSeek-V4.1-Flash","model":123,"input":[]}`, "invalid model"},
		{"changed review", strings.Replace(strings.Replace(guardianRequestFixture(), "moonshotai/Kimi-K3", "zai-org/GLM-5.3-Flash", 1), `"strict":false`, `"strict":true`, 1), "unsupported"},
		{"wrong reviewer", guardianRequestFixture(), "unsupported Guardian"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			response := adapterRequest(t, child.Env["TOFA_DESKTOP_CONTEXT"], child.Env["TOFA_API_KEY"], tc.body)
			body, _ := io.ReadAll(response.Body)
			response.Body.Close()
			if response.StatusCode != 400 || !strings.Contains(string(body), tc.want) {
				t.Fatalf("unexpected lane response: %d %s", response.StatusCode, body)
			}
		})
	}
	for _, model := range []string{"deepseek-ai/DeepSeek-V4.1-Flash", "moonshotai/Kimi-K3"} {
		body, err := os.ReadFile("testdata/desktop-luna6-title-request.json")
		if err != nil {
			t.Fatal(err)
		}
		body = []byte(strings.Replace(string(body), `"model": "gpt-6-luna"`, `"model": "`+model+`"`, 1))
		response := adapterRequest(t, child.Env["TOFA_DESKTOP_CONTEXT"], child.Env["TOFA_API_KEY"], string(body))
		data, _ := io.ReadAll(response.Body)
		response.Body.Close()
		if response.StatusCode != 400 || !strings.Contains(string(data), "automatic title generation is unavailable") {
			t.Fatalf("unsupported naming escaped: %s", data)
		}
	}
	stop()
	if upstream.Load() != 0 || !strings.Contains(output.String(), "Naming: nvidia/Nemotron-3_5-Lightning") {
		t.Fatal("unsupported lane reached provider or naming limitation was hidden")
	}
}

func TestDesktopRejectsChangedReviewEvenWhenItTargetsMain(t *testing.T) {
	for _, guardian := range []string{"zai-org/GLM-5.3-Flash", "moonshotai/Kimi-K3"} {
		t.Run(guardian, func(t *testing.T) {
			bundle, capture := desktopFixture(t, "ignore")
			var upstream atomic.Int32
			app, _ := adapterFixture(t, func(w http.ResponseWriter, r *http.Request) { upstream.Add(1) }, nil)
			child, stop := liveDesktopFixture(t, app, bundle, capture, "--model", "zai-org/GLM-5.3-Flash", "--guardian-model", guardian)
			for _, change := range [][2]string{{`"strict":false`, `"strict":true`}, {`"name":"view_image"`, `"name":"new_review_tool"`}, {`"outcome"`, `"new_outcome"`}} {
				body := strings.ReplaceAll(guardianRequestFixture(), "moonshotai/Kimi-K3", "zai-org/GLM-5.3-Flash")
				body = strings.ReplaceAll(body, change[0], change[1])
				response := adapterRequest(t, child.Env["TOFA_DESKTOP_CONTEXT"], child.Env["TOFA_API_KEY"], body)
				data, _ := io.ReadAll(response.Body)
				response.Body.Close()
				if response.StatusCode != 400 || !strings.Contains(string(data), "unsupported desktop approval review") {
					t.Errorf("changed review admitted: %d %s", response.StatusCode, data)
				}
			}
			stop()
			if upstream.Load() != 0 {
				t.Fatal("changed review contract reached provider")
			}
		})
	}
}

func TestDesktopMainStructuredOutcomeRemainsAnOrdinaryRequest(t *testing.T) {
	bundle, capture := desktopFixture(t, "ignore")
	const body = `{"model":"zai-org/GLM-5.3-Flash","input":[],"text":{"format":{"type":"json_schema","strict":true,"schema":{"type":"object","properties":{"outcome":{"type":"string"}},"required":["outcome"]}}}}`
	var calls atomic.Int32
	app, _ := adapterFixture(t, func(w http.ResponseWriter, r *http.Request) {
		data, _ := io.ReadAll(r.Body)
		if string(data) != body {
			t.Error("ordinary main schema changed")
		}
		calls.Add(1)
		io.WriteString(w, "ok")
	}, nil)
	child, stop := liveDesktopFixture(t, app, bundle, capture, "--model", "zai-org/GLM-5.3-Flash")
	response := adapterRequest(t, child.Env["TOFA_DESKTOP_CONTEXT"], child.Env["TOFA_API_KEY"], body)
	response.Body.Close()
	stop()
	if response.StatusCode != 200 || calls.Load() != 1 {
		t.Fatal("ordinary structured output was mistaken for review")
	}
}

func TestDesktopUnavailableMainExplainsRecovery(t *testing.T) {
	bundle, capture := desktopFixture(t, "ignore")
	var calls atomic.Int32
	app, output := adapterFixture(t, nil, nil)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/models" {
			io.WriteString(w, `{"data":[{"id":"deepseek-ai/DeepSeek-V4.1-Flash"},{"id":"zai-org/GLM-5.3-Flash"}]}`)
			return
		}
		calls.Add(1)
	}))
	defer server.Close()
	app.Endpoint = server.URL
	child, stop := liveDesktopFixture(t, app, bundle, capture, "--model", "deepseek-ai/DeepSeek-V4.1-Flash")
	for _, model := range []string{"zai-org/GLM-5.3", "fixture-model", "gpt-6-astra"} {
		response := adapterRequest(t, child.Env["TOFA_DESKTOP_CONTEXT"], child.Env["TOFA_API_KEY"], `{"model":"`+model+`","input":[]}`)
		body, err := io.ReadAll(response.Body)
		response.Body.Close()
		if err != nil || response.StatusCode != http.StatusBadRequest || calls.Load() != 0 {
			t.Fatalf("unavailable model escaped: %d %s", response.StatusCode, body)
		}
		if model != "zai-org/GLM-5.3" && (!strings.Contains(string(body), "missing bundled model metadata") || !strings.Contains(string(body), "select an available model")) {
			t.Errorf("missing incompatible-model recovery: %s", body)
		}
		if model == "zai-org/GLM-5.3" && !strings.Contains(string(body), "unavailable in this launch's project catalog") {
			t.Fatalf("missing recovery instructions: %s", body)
		}
	}
	stop()
	if !strings.Contains(output.String(), "relaunch to refresh the catalog") {
		t.Fatal("missing availability recovery notice")
	}
}

func TestDesktopBundledEngineResumesRecordedMainWithAnyLaunchDefault(t *testing.T) {
	// Cover a recorded main that is also Guardian and a different supported main.
	for _, recorded := range []string{"zai-org/GLM-5.3-Flash", "zai-org/GLM-5.3"} {
		t.Run(recorded, func(t *testing.T) { desktopRecordedMainRoundTrip(t, recorded) })
	}
}

func desktopRecordedMainRoundTrip(t *testing.T, recorded string) {
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
	app, _ := adapterFixture(t, func(w http.ResponseWriter, r *http.Request) {
		var request struct{ Model string }
		if json.NewDecoder(r.Body).Decode(&request) != nil || request.Model != recorded {
			t.Error("conversation identity changed")
		}
		calls.Add(1)
		emitFixtureResponse(w, fixtureMessage("Retained conversation."))
	}, nil)
	var id string
	for index, main := range []string{recorded, "deepseek-ai/DeepSeek-V4.1-Flash", recorded} {
		child, stop := liveDesktopFixture(t, app, bundle, capture, "--model", main)
		e := openDesktopEngine(t, child)
		var thread map[string]any
		if index == 0 {
			thread = e.call("thread/start", map[string]any{"cwd": child.Cwd, "approvalPolicy": "never", "sandbox": "read-only"})
			id = thread["thread"].(map[string]any)["id"].(string)
		} else {
			thread = e.call("thread/resume", map[string]any{"threadId": id, "model": nil, "modelProvider": nil})
		}
		if thread["model"] != recorded || thread["modelProvider"] != "nebius-tofa" {
			t.Fatal("resume changed recorded identity")
		}
		e.turnText(id, "completed", "Continue the recorded conversation")
		if index == 0 {
			e.call("thread/name/set", map[string]string{"threadId": id, "name": "Retained title"})
		}
		saved := e.call("thread/read", map[string]any{"threadId": id, "includeTurns": true})["thread"].(map[string]any)
		if saved["id"] != id || saved["name"] != "Retained title" || saved["cwd"] != child.Cwd || saved["modelProvider"] != "nebius-tofa" {
			t.Fatalf("wrong-main recovery changed conversation metadata: %v", saved)
		}
		e.close()
		stop()
		if err := os.Remove(capture); err != nil {
			t.Fatal(err)
		}
	}
	if calls.Load() != 3 {
		t.Fatalf("recorded model did not receive all turns: %d", calls.Load())
	}
}

func TestDesktopOrdinaryRecoveryGuidanceSupportsSelectedMain(t *testing.T) {
	bundle, _ := desktopFixture(t, "normal")
	app, _ := adapterFixture(t, nil, nil)
	args := []string{"launch", "codex-desktop", "--app-bundle", bundle, "--model", "deepseek-ai/DeepSeek-V4.1-Flash", "--allow-unverified"}
	if err := app.Run(args); err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(os.Getenv("HOME"), ".codex", "config.toml")
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(data), "Relaunch through tofa with any default main model") {
		t.Fatalf("ordinary-mode guidance is tied to a different main: %s", data)
	}
	// An older launch's exactly owned inactive entry remains accepted. Avoid
	// migrating unrelated settings or accepting an arbitrary provider override.
	const current = "Token Factory is unavailable in ordinary mode. Relaunch through tofa with any default main model, then reopen this conversation; choosing GPT does not migrate its provider."
	for _, legacy := range []string{
		"Token Factory is unavailable in ordinary mode. Relaunch through tofa with --model moonshotai/Kimi-K3 --allow-unverified; choosing GPT does not migrate this conversation.",
		"Token Factory is unavailable in ordinary mode. Relaunch through tofa with the conversation's original main model: --model ID --allow-unverified; choosing GPT does not migrate this conversation.",
	} {
		if err := os.WriteFile(path, []byte(strings.Replace(string(data), current, legacy, 1)), 0600); err != nil {
			t.Fatal(err)
		}
		if err := app.Run(args); err != nil {
			t.Fatalf("legacy owned provider refused: %v", err)
		}
	}
}
