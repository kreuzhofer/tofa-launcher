package tofa_test

import (
	"bytes"
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"github.com/kreuzhofer/tofa-launcher/internal/tofa"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

func declaredCandidateObserver(t *testing.T, app *tofa.App, bundle string) string {
	t.Helper()
	home := filepath.Join(os.Getenv("HOME"), ".codex")
	os.MkdirAll(home, 0700)
	for path, raw := range map[string]string{
		filepath.Join(bundle, "Contents/Resources/app.asar"):                                                  "owned-fixture-archive",
		filepath.Join(bundle, "Contents/Resources/plugins/openai-bundled/plugins/codex-app-tools/server.mjs"): "owned-fixture-transport",
		filepath.Join(home, "models_cache.json"):                                                              `{"fetched_at":"volatile","models":[{"slug":"gpt-6-astra","display_name":"Native fixture","context_window":100000}]}`,
	} {
		os.MkdirAll(filepath.Dir(path), 0700)
		if err := os.WriteFile(path, []byte(raw), 0600); err != nil {
			t.Fatal(err)
		}
	}
	runtimeRoot := filepath.Join(os.Getenv("HOME"), ".cache/codex-runtimes/owned-fixture")
	os.MkdirAll(runtimeRoot, 0700)
	os.WriteFile(filepath.Join(runtimeRoot, "runtime.json"), []byte(`{"bundleFormatVersion":2,"targetPlatform":"darwin","targetArch":"arm64"}`), 0600)
	for _, relative := range []string{"dependencies/node/bin/node", "dependencies/python/bin/python3", "dependencies/bin/override/soffice", "dependencies/bin/override/pdfinfo", "dependencies/bin/override/pdftoppm", "dependencies/node/node_modules/@oai/artifact-tool/package.json"} {
		path := filepath.Join(runtimeRoot, relative)
		os.MkdirAll(filepath.Dir(path), 0700)
		os.WriteFile(path, []byte("fixture"), 0700)
	}
	harness, err := filepath.Abs("../../scripts")
	if err != nil {
		t.Fatal(err)
	}
	var output bytes.Buffer
	previous := app.Out
	app.Out = &output
	err = app.Run([]string{"desktop-qualification", "snapshot", "--app-bundle", bundle, "--runtime-root", runtimeRoot, "--harness-root", harness, "--source-revision", strings.Repeat("a", 40)})
	app.Out = previous
	if err != nil {
		t.Fatal(err)
	}
	var snapshot map[string]json.RawMessage
	if err := json.Unmarshal(output.Bytes(), &snapshot); err != nil {
		t.Fatal(err)
	}
	os.MkdirAll("/tmp/tofa-presentation-validation", 0700)
	run, err := os.MkdirTemp("/tmp/tofa-presentation-validation", "admission-public-")
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { os.RemoveAll(run) })
	old := candidateProxyObserver(t)
	raw, err := os.ReadFile(old)
	if err != nil {
		t.Fatal(err)
	}
	var observer map[string]any
	json.Unmarshal(raw, &observer)
	observer["qualification_declaration"] = filepath.Join(run, "declaration.json")
	raw, _ = json.Marshal(observer)
	path := filepath.Join(run, "observer.json")
	os.WriteFile(path, raw, 0600)
	now := time.Now().UTC()
	declaration := map[string]any{"schema": "tofa-native-account-declaration-v1", "attempt": filepath.Base(run), "case": "clean-exit", "root": run, "identity": snapshot["identity"], "issued_utc": now, "expires_utc": now.Add(900 * time.Second), "seconds": 900, "requests": 8}
	raw, _ = json.Marshal(declaration)
	os.WriteFile(filepath.Join(run, "declaration.json"), raw, 0600)
	return path
}

func TestDesktopDeclaredCandidatePreservesProtectedPlugin(t *testing.T) {
	bundle, capture := nativeCandidateFixture(t)
	home := filepath.Join(os.Getenv("HOME"), ".codex")
	plugin := filepath.Join(home, "plugins/cache/openai-bundled/code-review/owned/plugin.txt")
	os.MkdirAll(filepath.Dir(plugin), 0700)
	os.WriteFile(plugin, []byte("installed plugin remains"), 0600)
	app, _ := adapterFixture(t, nil, nil)
	observer := declaredCandidateObserver(t, app, bundle)
	_, stop := liveDesktopFixture(t, app, bundle, capture, "--native-account-candidate", "--evaluation-observer", observer)
	stop()
	raw, err := os.ReadFile(plugin)
	if err != nil || string(raw) != "installed plugin remains" {
		t.Fatal("protected plugin changed")
	}
	if _, err := os.Stat(filepath.Join(filepath.Dir(observer), "start.json")); err != nil {
		t.Fatal("missing consumed attempt receipt")
	}
	err = app.Run([]string{"launch", "codex-desktop", "--app-bundle", bundle, "--model", "moonshotai/Kimi-K3", "--native-account-candidate", "--evaluation-observer", observer})
	if err == nil || !strings.Contains(err.Error(), "consumed") {
		t.Fatalf("replay admitted: %v", err)
	}
}

func TestDesktopSnapshotAcceptsIndependentCachedPluginVersions(t *testing.T) {
	bundle, _ := nativeCandidateFixture(t)
	home := filepath.Join(os.Getenv("HOME"), ".codex")
	files := map[string][]byte{}
	for _, version := range []string{"26.1007.71326", "26.1001.10000"} {
		root := filepath.Join(home, "plugins/cache/openai-bundled/unified-computer-use", version)
		manifest := filepath.Join(root, ".codex-plugin/plugin.json")
		mcp := filepath.Join(root, ".mcp.json")
		files[manifest] = []byte(`{"name":"unified-computer-use","version":"` + version + `"}`)
		raw, err := json.Marshal(map[string]any{"mcpServers": map[string]any{"cua_repl": map[string]any{"env": map[string]any{"CODEX_CLI_PATH": filepath.Join(bundle, "Contents/Resources/codex")}}}})
		if err != nil {
			t.Fatal(err)
		}
		files[mcp] = raw
	}
	for path, raw := range files {
		if err := os.MkdirAll(filepath.Dir(path), 0700); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(path, raw, 0600); err != nil {
			t.Fatal(err)
		}
	}
	app, _ := adapterFixture(t, nil, nil)
	declaredCandidateObserver(t, app, bundle) // Calls the public snapshot entry point.
	for path, expected := range files {
		raw, err := os.ReadFile(path)
		if err != nil || !bytes.Equal(raw, expected) {
			t.Fatalf("snapshot modified plugin %s: %v", path, err)
		}
	}
}
func TestDesktopDeclaredCandidateRejectsDriftBeforeNativeStart(t *testing.T) {
	bundle, capture := nativeCandidateFixture(t)
	app, _ := adapterFixture(t, nil, nil)
	observer := declaredCandidateObserver(t, app, bundle)
	os.WriteFile(filepath.Join(bundle, "Contents/Resources/app.asar"), []byte("changed app bytes"), 0600)
	err := app.Run([]string{"launch", "codex-desktop", "--app-bundle", bundle, "--model", "moonshotai/Kimi-K3", "--native-account-candidate", "--evaluation-observer", observer})
	if err == nil || !strings.Contains(err.Error(), "mismatched") {
		t.Fatalf("drift admitted: %v", err)
	}
	if _, err := os.Stat(capture); !os.IsNotExist(err) {
		t.Fatal("drift launched native process")
	}
}

func TestDesktopDeclaredCandidateExplainsPreflightRefusal(t *testing.T) {
	for _, scenario := range []string{"skills", "expired", "untrusted-key"} {
		t.Run(scenario, func(t *testing.T) {
			bundle, capture := nativeCandidateFixture(t)
			app, _ := adapterFixture(t, nil, nil)
			observer := declaredCandidateObserver(t, app, bundle)
			path := filepath.Join(filepath.Dir(observer), "declaration.json")
			raw, err := os.ReadFile(path)
			if err != nil {
				t.Fatal(err)
			}
			var declaration map[string]any
			if err := json.Unmarshal(raw, &declaration); err != nil {
				t.Fatal(err)
			}
			want := "identity mismatched (changed: skills)"
			if scenario == "skills" {
				skill := filepath.Join(os.Getenv("HOME"), ".codex/skills/personal/SKILL.md")
				if err := os.MkdirAll(filepath.Dir(skill), 0700); err != nil {
					t.Fatal(err)
				}
				if err := os.WriteFile(skill, []byte("changed skill"), 0600); err != nil {
					t.Fatal(err)
				}
			} else if scenario == "expired" {
				declaration["issued_utc"] = time.Now().UTC().Add(-20 * time.Minute)
				declaration["expires_utc"] = time.Now().UTC().Add(-5 * time.Minute)
				want = "declaration expired or invalid time window"
			} else {
				declaration["identity"].(map[string]any)["hashes"].(map[string]any)["private-user-supplied-key"] = "private-value"
				want = "identity mismatched (changed: identity metadata)"
			}
			raw, err = json.Marshal(declaration)
			if err != nil {
				t.Fatal(err)
			}
			if err := os.WriteFile(path, raw, 0600); err != nil {
				t.Fatal(err)
			}
			err = app.Run([]string{"launch", "codex-desktop", "--app-bundle", bundle, "--model", "moonshotai/Kimi-K3", "--native-account-candidate", "--evaluation-observer", observer})
			if err == nil || !strings.Contains(err.Error(), want) || strings.Contains(err.Error(), "private-") {
				t.Fatalf("expected safe %q diagnostic, got %v", want, err)
			}
			if _, err := os.Stat(capture); !os.IsNotExist(err) {
				t.Fatal("refused declaration launched Desktop")
			}
		})
	}
}
func TestDesktopQualifiedProofCannotBeCombinedWithCandidate(t *testing.T) {
	app, _ := adapterFixture(t, nil, nil)
	err := app.Run([]string{"launch", "codex-desktop", "--model", "moonshotai/Kimi-K3", "--native-account-candidate", "--native-account-proof", "/tmp/missing", "--evaluation-observer", "/tmp/missing"})
	if err == nil || !strings.Contains(err.Error(), "choose either") {
		t.Fatalf("ambiguous admission modes: %v", err)
	}
}

func TestDesktopDeclaredCandidateEnforcesAdapterRequestBudget(t *testing.T) {
	bundle, capture := nativeCandidateFixture(t)
	var forwarded atomic.Int32
	app, _ := adapterFixture(t, func(w http.ResponseWriter, r *http.Request) { forwarded.Add(1); w.Write([]byte(`{"output":[]}`)) }, nil)
	observer := declaredCandidateObserver(t, app, bundle)
	declarationPath := filepath.Join(filepath.Dir(observer), "declaration.json")
	raw, _ := os.ReadFile(declarationPath)
	var declaration map[string]any
	json.Unmarshal(raw, &declaration)
	declaration["requests"] = 2
	raw, _ = json.Marshal(declaration)
	os.WriteFile(declarationPath, raw, 0600)
	child, stop := liveDesktopFixture(t, app, bundle, capture, "--native-account-candidate", "--evaluation-observer", observer)
	defer stop()
	request, _ := http.NewRequest("GET", child.Env["TOFA_DESKTOP_CONTEXT"]+"/desktop-launch", nil)
	request.Header.Set("Authorization", "Bearer "+child.Env["TOFA_API_KEY"])
	response, e := http.DefaultClient.Do(request)
	if e != nil {
		t.Fatal(e)
	}
	var route struct{ InferenceCapability string }
	json.NewDecoder(response.Body).Decode(&route)
	response.Body.Close()
	for _, step := range []struct {
		token  string
		status int
	}{{"wrong", 401}, {route.InferenceCapability, 200}, {route.InferenceCapability, 200}, {route.InferenceCapability, 429}} {
		request, _ := http.NewRequest("POST", child.Env["TOFA_DESKTOP_CONTEXT"]+"/responses", strings.NewReader(`{"model":"moonshotai/Kimi-K3","input":[]}`))
		request.Header.Set("Authorization", "Bearer "+step.token)
		response, e := http.DefaultClient.Do(request)
		if e != nil {
			t.Fatal(e)
		}
		response.Body.Close()
		if response.StatusCode != step.status {
			t.Fatalf("got %d, want %d", response.StatusCode, step.status)
		}
	}
	if forwarded.Load() != 2 {
		t.Fatalf("upstream attempts=%d", forwarded.Load())
	}
}

func TestDesktopDeclaredCandidateRetainsCatalogNumericDriftWithoutBlocking(t *testing.T) {
	bundle, capture := nativeCandidateFixture(t)
	app, _ := adapterFixture(t, nil, nil)
	observer := declaredCandidateObserver(t, app, bundle)
	cache := filepath.Join(os.Getenv("HOME"), ".codex/models_cache.json")
	raw, _ := os.ReadFile(cache)
	raw = bytes.Replace(raw, []byte(`100000`), []byte(`9007199254740992`), 1)
	os.WriteFile(cache, raw, 0600)
	// Freeze the large integer in a new read-only snapshot before changing only its last bit.
	declarationPath := filepath.Join(filepath.Dir(observer), "declaration.json")
	raw, _ = os.ReadFile(declarationPath)
	var d map[string]json.RawMessage
	json.Unmarshal(raw, &d)
	var id struct {
		Runtime string `json:"runtime_root"`
		Harness string `json:"harness_root"`
	}
	json.Unmarshal(d["identity"], &id)
	var output bytes.Buffer
	old := app.Out
	app.Out = &output
	e := app.Run([]string{"desktop-qualification", "snapshot", "--app-bundle", bundle, "--runtime-root", id.Runtime, "--harness-root", id.Harness, "--source-revision", strings.Repeat("a", 40)})
	app.Out = old
	if e != nil {
		t.Fatal(e)
	}
	var snapshot map[string]json.RawMessage
	json.Unmarshal(output.Bytes(), &snapshot)
	d["identity"] = snapshot["identity"]
	raw, _ = json.Marshal(d)
	os.WriteFile(declarationPath, raw, 0600)
	raw, _ = os.ReadFile(cache)
	raw = bytes.Replace(raw, []byte(`9007199254740992`), []byte(`9007199254740993`), 1)
	os.WriteFile(cache, raw, 0600)
	output.Reset()
	app.Out = &output
	e = app.Run([]string{"desktop-qualification", "snapshot", "--app-bundle", bundle, "--runtime-root", id.Runtime, "--harness-root", id.Harness, "--source-revision", strings.Repeat("a", 40)})
	app.Out = old
	if e != nil {
		t.Fatal(e)
	}
	var current map[string]json.RawMessage
	if e = json.Unmarshal(output.Bytes(), &current); e != nil {
		t.Fatal(e)
	}
	if bytes.Equal(current["identity"], snapshot["identity"]) {
		t.Fatal("catalog numeric change disappeared from provenance")
	}
	_, stop := liveDesktopFixture(t, app, bundle, capture, "--native-account-candidate", "--evaluation-observer", observer)
	stop()
}

func TestDesktopDeclaredCandidateAllowsCatalogAndExplicitModelChange(t *testing.T) {
	bundle, capture := nativeCandidateFixture(t)
	app, _ := adapterFixture(t, nil, nil)
	var refreshed atomic.Bool
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer fixture-secret" || r.URL.Query().Get("ai_project_id") != "fixture-project" {
			t.Error("wrong provider credentials")
		}
		if r.URL.Path != "/models" {
			t.Error("unexpected inference")
			w.WriteHeader(500)
			return
		}
		extra := ""
		if refreshed.Load() {
			extra = `,{"id":"new-unrelated-model"}`
		}
		io.WriteString(w, `{"data":[{"id":"moonshotai/Kimi-K3"},{"id":"zai-org/GLM-5.3"},{"id":"zai-org/GLM-5.3-Flash"},{"id":"nvidia/Nemotron-3_5-Lightning"}`+extra+`]}`)
	}))
	defer server.Close()
	app.Endpoint = server.URL
	observer := declaredCandidateObserver(t, app, bundle)
	refreshed.Store(true)
	_, stop := liveDesktopFixture(t, app, bundle, capture, "--model", "zai-org/GLM-5.3", "--native-account-candidate", "--evaluation-observer", observer)
	stop()
}

// The public snapshot must retain the exact skill entries used for its aggregate,
// so a later review can identify changes without consulting the live installation.
func TestDesktopSnapshotRetainsFileInventories(t *testing.T) {
	bundle, _ := nativeCandidateFixture(t)
	home, err := filepath.EvalSymlinks(os.Getenv("HOME"))
	if err != nil {
		t.Fatal(err)
	}
	t.Setenv("HOME", home)
	app, _ := adapterFixture(t, nil, nil)
	declaredCandidateObserver(t, app, bundle) // prepare owned runtime/catalog fixtures
	runtimeRoot := filepath.Join(home, ".cache/codex-runtimes/owned-fixture")
	harness, err := filepath.Abs("../../scripts")
	if err != nil {
		t.Fatal(err)
	}
	capture := func() map[string]json.RawMessage {
		t.Helper()
		var out bytes.Buffer
		app.Out = &out
		err := app.Run([]string{"desktop-qualification", "snapshot", "--app-bundle", bundle, "--runtime-root", runtimeRoot, "--harness-root", harness, "--source-revision", strings.Repeat("a", 40)})
		if err != nil {
			t.Fatal(err)
		}
		var result map[string]json.RawMessage
		if err := json.Unmarshal(out.Bytes(), &result); err != nil {
			t.Fatal(err)
		}
		return result
	}
	before := capture()
	var pluginBefore map[string]string
	if err := json.Unmarshal(before["plugin_files"], &pluginBefore); err != nil {
		t.Fatal("plugin evidence missing:", err)
	}
	pluginRoot := filepath.Join(home, ".codex/plugins/cache")
	if err := os.MkdirAll(filepath.Join(pluginRoot, "example"), 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(pluginRoot, "example/private.txt"), []byte("private plugin content"), 0600); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink("example", filepath.Join(pluginRoot, "current")); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink("missing", filepath.Join(pluginRoot, "stale")); err != nil {
		t.Fatal(err)
	}

	var absent map[string]map[string]string
	if err := json.Unmarshal(before["skill_files"], &absent); err != nil {
		t.Fatal("skill evidence missing:", err)
	}
	for _, name := range []string{"skills", "agent_skills"} {
		if absent[name]["."] != "absent" {
			t.Fatalf("missing root is not evidenced: %s %v", name, absent)
		}
	}
	for _, root := range []string{filepath.Join(home, ".codex/skills"), filepath.Join(home, ".agents/skills")} {
		if err := os.MkdirAll(filepath.Join(root, "example"), 0700); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(filepath.Join(root, "example/SKILL.md"), []byte("private skill content"), 0600); err != nil {
			t.Fatal(err)
		}
		if err := os.Symlink("example", filepath.Join(root, "current")); err != nil {
			t.Fatal(err)
		}
	}
	after := capture()
	var files map[string]map[string]string
	if err := json.Unmarshal(after["skill_files"], &files); err != nil {
		t.Fatal(err)
	}
	var identity struct {
		Hashes map[string]string `json:"hashes"`
	}
	if err := json.Unmarshal(after["identity"], &identity); err != nil {
		t.Fatal(err)
	}
	for _, name := range []string{"skills", "agent_skills"} {
		if len(files[name]) != 2 || files[name]["example/SKILL.md"] != fmt.Sprintf("%x", sha256.Sum256([]byte("private skill content"))) || files[name]["current"] != "link:example" {
			t.Fatalf("wrong retained entries: %s %v", name, files[name])
		}
		raw, _ := json.Marshal(files[name])
		if fmt.Sprintf("%x", sha256.Sum256(raw)) != identity.Hashes[name] {
			t.Fatalf("inventory not bound to %s aggregate", name)
		}
	}
	var plugins map[string]string
	if err := json.Unmarshal(after["plugin_files"], &plugins); err != nil {
		t.Fatal(err)
	}
	if plugins["example/private.txt"] != fmt.Sprintf("%x", sha256.Sum256([]byte("private plugin content"))) || plugins["current"] != "link:example" || plugins["stale"] != "dangling-link:missing" {
		t.Fatal("wrong plugin entries", plugins)
	}
	if len(pluginBefore) != 1 || pluginBefore["."] != "absent" || len(plugins) != 3 {
		t.Fatal("absent and populated plugin roots not evidenced")
	}
	raw, _ := json.Marshal(plugins)
	if fmt.Sprintf("%x", sha256.Sum256(raw)) != identity.Hashes["plugins"] {
		t.Fatal("plugin inventory not bound to aggregate")
	}
	if bytes.Contains(after["plugin_files"], []byte("private plugin content")) {
		t.Fatal("plugin contents disclosed")
	}

	if bytes.Contains(after["skill_files"], []byte("private skill content")) {
		t.Fatal("skill contents disclosed")
	}
}
