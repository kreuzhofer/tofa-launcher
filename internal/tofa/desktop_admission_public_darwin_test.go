package tofa_test

import (
	"bytes"
	"context"
	"encoding/json"
	"github.com/kreuzhofer/tofa-launcher/internal/tofa"
	"net/http"
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

func TestDesktopDeclaredCandidateDetectsExactCatalogNumericDrift(t *testing.T) {
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
	ctx, cancel := context.WithTimeout(context.Background(), 8*time.Second)
	defer cancel()
	e = app.RunContext(ctx, []string{"launch", "codex-desktop", "--app-bundle", bundle, "--model", "moonshotai/Kimi-K3", "--native-account-candidate", "--evaluation-observer", observer})
	if e == nil || !strings.Contains(e.Error(), "mismatched") {
		t.Fatalf("numeric drift admitted: %v", e)
	}
	if _, e := os.Stat(capture); !os.IsNotExist(e) {
		t.Fatal("drift started native fixture")
	}
}
