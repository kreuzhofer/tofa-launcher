package tofa_test

import (
	"bytes"
	"os"
	"path/filepath"
	"testing"
)

func TestDesktopDefaultSelectionPreservesCLIDefault(t *testing.T) {
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
	home := filepath.Join(os.Getenv("HOME"), ".codex")
	if err := os.MkdirAll(home, 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(home, "config.toml"), []byte("model = \"gpt-6-astra\"\nmodel_reasoning_effort = \"high\"\n"), 0600); err != nil {
		t.Fatal(err)
	}
	workspace, err := os.Getwd()
	if err != nil {
		t.Fatal(err)
	}
	ordinary := capturedDesktop{Cwd: workspace, Env: map[string]string{"PATH": os.Getenv("PATH"), "HOME": os.Getenv("HOME"), "CODEX_HOME": home, "CODEX_CLI_PATH": installed}}
	cli := openDesktopEngine(t, ordinary)
	assertCLI := func(phase string) {
		t.Helper()
		config := cli.call("config/read", map[string]any{"includeLayers": false})["config"].(map[string]any)
		if config["model"] != "gpt-6-astra" || config["model_reasoning_effort"] != "high" {
			t.Errorf("%s: CLI defaults changed: model=%v effort=%v", phase, config["model"], config["model_reasoning_effort"])
		}
	}
	assertCLI("before desktop")
	app, _ := adapterFixture(t, nil, nil)
	child, stop := liveDesktopFixture(t, app, bundle, capture, "--evaluation-observer", legacyProxyObserver(t), "--model", "deepseek-ai/DeepSeek-V4.1-Flash")
	assertCLI("after desktop startup")
	desktop := openDesktopEngine(t, child)
	before, err := os.ReadFile(filepath.Join(home, "config.toml"))
	if err != nil {
		t.Fatal(err)
	}
	// Match the installed desktop: scope default writes to the effective profile,
	// when present, otherwise write the global default.
	config := desktop.call("config/read", map[string]any{"includeLayers": false})["config"].(map[string]any)
	prefix := ""
	if profile, ok := config["profile"].(string); ok && profile != "" {
		prefix = "profiles." + profile + "."
	}
	result := desktop.call("config/batchWrite", map[string]any{"filePath": nil, "reloadUserConfig": true, "edits": []any{
		map[string]any{"keyPath": prefix + "model", "value": "zai-org/GLM-5.3-Flash", "mergeStrategy": "replace"},
		map[string]any{"keyPath": prefix + "model_reasoning_effort", "value": nil, "mergeStrategy": "replace"},
	}})
	if result["status"] != "okOverridden" {
		t.Errorf("desktop did not receive explicit session-only override status: %v", result["status"])
	}
	assertCLI("after desktop model selection")
	after, err := os.ReadFile(filepath.Join(home, "config.toml"))
	if err != nil || !bytes.Equal(before, after) {
		t.Fatal("desktop model write changed the ordinary settings file")
	}
	// The pinned renderer handles okOverridden by retaining its selected model
	// locally and supplying it to the next new thread.
	started := desktop.call("thread/start", map[string]any{"cwd": workspace, "model": "zai-org/GLM-5.3-Flash", "approvalPolicy": "never", "sandbox": "read-only"})
	if started["model"] != "zai-org/GLM-5.3-Flash" || started["modelProvider"] != "nebius-tofa" {
		t.Fatal("session-only desktop default did not reach its new conversation")
	}
	desktop.call("config/batchWrite", map[string]any{"filePath": nil, "reloadUserConfig": true, "edits": []any{map[string]any{"keyPath": "tui.animations", "value": false, "mergeStrategy": "replace"}}})
	ordinaryConfig := cli.call("config/read", map[string]any{"includeLayers": false})["config"].(map[string]any)
	if ordinaryConfig["tui"].(map[string]any)["animations"] != false {
		t.Fatal("unrelated settings write was intercepted")
	}
	desktop.close()
	stop()
	assertCLI("after desktop shutdown")
	cli.close()
	cli = openDesktopEngine(t, ordinary)
	assertCLI("fresh CLI after desktop shutdown")
	cli.close()
}

func TestDesktopModelDefaultWritesRejectPartialOrStaleChanges(t *testing.T) {
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
	app, _ := adapterFixture(t, nil, nil)
	child, stop := liveDesktopFixture(t, app, bundle, capture, "--evaluation-observer", legacyProxyObserver(t), "--model", "deepseek-ai/DeepSeek-V4.1-Flash")
	e := openDesktopEngine(t, child)
	path := filepath.Join(child.Env["CODEX_HOME"], "config.toml")
	before, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	model := map[string]any{"keyPath": "model", "value": "zai-org/GLM-5.3-Flash", "mergeStrategy": "upsert"}
	for _, tc := range []struct {
		name   string
		params map[string]any
	}{
		{"mixed model and unrelated settings", map[string]any{"edits": []any{model, map[string]any{"keyPath": "tui.animations", "value": false, "mergeStrategy": "replace"}}}},
		{"stale version", map[string]any{"expectedVersion": "stale-version", "edits": []any{model}}},
		{"invalid model type", map[string]any{"edits": []any{map[string]any{"keyPath": "model", "value": 123, "mergeStrategy": "replace"}}}},
		{"explicit file outside picker contract", map[string]any{"filePath": path, "edits": []any{model}}},
	} {
		t.Run(tc.name, func(t *testing.T) {
			e.id++
			if err := e.encoder.Encode(map[string]any{"id": e.id, "method": "config/batchWrite", "params": tc.params}); err != nil {
				t.Fatal(err)
			}
			for {
				response := e.read()
				if response["id"] == float64(e.id) {
					if response["error"] == nil {
						t.Fatal("unsafe or stale batch was accepted")
					}
					break
				}
			}
			after, err := os.ReadFile(path)
			if err != nil || !bytes.Equal(before, after) {
				t.Fatal("rejected batch partially modified ordinary settings")
			}
		})
	}
	e.close()
	stop()
}
