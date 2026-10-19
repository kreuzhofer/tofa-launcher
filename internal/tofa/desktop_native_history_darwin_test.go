package tofa_test

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"syscall"
	"testing"
	"time"
)

func TestDesktopNativeCandidateRegistersInactiveHistory(t *testing.T) {
	bundle, capture := nativeCandidateFixture(t)
	app, _ := adapterFixture(t, nil, nil)
	child, stop := liveDesktopFixture(t, app, bundle, capture, "--native-account-candidate", "--evaluation-observer", candidateProxyObserver(t))
	defer stop()
	raw, err := os.ReadFile(filepath.Join(child.Env["CODEX_HOME"], "config.toml"))
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(raw), "[model_providers.tofa-native-router]") {
		t.Fatal("routed history has no inactive provider registration")
	}
}

func TestDesktopNativeCandidateHistoryAcrossLaunches(t *testing.T) {
	nativeHistoryAcrossLaunches(t, "clean")
}

func TestDesktopNativeCandidateHistoryLifecycle(t *testing.T) {
	for _, fault := range []string{"launcher crash", "client crash", "client exit", "interrupted replacement", "uninstall and reinstall"} {
		t.Run(fault, func(t *testing.T) { nativeHistoryAcrossLaunches(t, fault) })
	}
}

func nativeHistoryAcrossLaunches(t *testing.T, fault string) {
	installed := os.Getenv("TOFA_TEST_DESKTOP_ENGINE")
	if installed == "" {
		t.Skip("set TOFA_TEST_DESKTOP_ENGINE")
	}
	bundle, capture := nativeCandidateFixture(t, "controlled")
	enginePath := filepath.Join(bundle, "Contents/Resources/codex")
	fake, err := os.ReadFile(enginePath)
	if err != nil {
		t.Fatal(err)
	}
	command := exec.Command(installed, "debug", "models", "--bundled")
	command.Env = []string{"PATH=" + os.Getenv("PATH"), "HOME=" + os.Getenv("HOME"), "CODEX_HOME=" + filepath.Join(os.Getenv("HOME"), ".codex")}
	catalog, err := command.Output()
	if err != nil {
		t.Fatal(err)
	}
	catalogPath := filepath.Join(bundle, "Contents/Resources/native-catalog.json")
	if err = os.WriteFile(catalogPath, catalog, 0600); err != nil {
		t.Fatal(err)
	}
	var mu sync.Mutex
	var calls []string
	handler := func(service string) http.HandlerFunc {
		return func(w http.ResponseWriter, r *http.Request) {
			if r.Method != "POST" {
				w.WriteHeader(426)
				return
			}
			var body map[string]any
			if json.NewDecoder(r.Body).Decode(&body) != nil {
				t.Error("invalid request")
				return
			}
			want := "Bearer synthetic-native"
			if service == "tf" {
				want = "Bearer fixture-secret"
			}
			if r.Header.Get("Authorization") != want || r.Header.Get("X-TOFA-Launch") != "" {
				t.Error("history authorization changed")
			}
			raw, _ := json.Marshal(body["input"])
			if strings.Contains(string(raw), "Verify all mixed history") {
				for _, expected := range []string{"Mixed TF first", "Mixed native second", "mixed-tool-output", "answer-moonshotai/Kimi-K3", "answer-gpt-6-astra"} {
					if !strings.Contains(string(raw), expected) {
						t.Errorf("resumed context missing %s", expected)
					}
				}
			}
			if service == "tf" && strings.Contains(string(raw), "Mixed TF first") && !strings.Contains(string(raw), "function_call_output") {
				emitFixtureResponse(w, map[string]any{"id": "mixed_tool", "type": "function_call", "call_id": "mixed_tool_call", "name": "exec_command", "arguments": `{"cmd":"printf mixed-tool-output","max_output_tokens":100}`, "status": "completed"})
				return
			}
			mu.Lock()
			calls = append(calls, service+":"+fmt.Sprint(body["model"]))
			mu.Unlock()
			emitFixtureModelResponse(w, fixtureMessage("answer-"+fmt.Sprint(body["model"])), fmt.Sprint(body["model"]))
		}
	}
	app, _ := adapterFixture(t, handler("tf"), nil)
	native := httptest.NewServer(handler("native"))
	defer native.Close()
	target, _ := url.Parse(native.URL)
	var removeKimi atomic.Bool
	app.HTTP.Transport = historyCatalogTransport{nativeFixtureTransport{target, http.DefaultTransport}, &removeKimi}
	launch := func(model string) (*desktopEngine, capturedDesktop, func()) {
		t.Helper()
		os.Remove(capture)
		os.Remove(capture + ".pid")
		if err := os.Remove(enginePath); err != nil && !os.IsNotExist(err) {
			t.Fatal(err)
		}
		if err := os.WriteFile(enginePath, fake, 0700); err != nil {
			t.Fatal(err)
		}
		child, stop := liveDesktopFixture(t, app, bundle, capture, "--model", model, "--native-account-candidate", "--evaluation-observer", candidateProxyObserver(t))
		deadline := time.Now().Add(10 * time.Second)
		for {
			if _, err := os.Stat(capture + ".pid"); err == nil {
				break
			}
			if time.Now().After(deadline) {
				t.Fatal("worker not ready")
			}
			time.Sleep(10 * time.Millisecond)
		}
		if err := os.Remove(enginePath); err != nil {
			t.Fatal(err)
		}
		if err := os.Symlink(installed, enginePath); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(filepath.Join(child.Env["CODEX_HOME"], "auth.json"), []byte(`{"OPENAI_API_KEY":"synthetic-native"}`), 0600); err != nil {
			t.Fatal(err)
		}
		return openDesktopEngine(t, child, "openai_base_url="+strconv.Quote(native.URL)), child, stop
	}
	e, child, stop := launch("moonshotai/Kimi-K3")
	start := func(provider, model, text string) string {
		s := e.call("thread/start", map[string]any{"cwd": child.Cwd, "modelProvider": provider, "model": model, "approvalPolicy": "never", "sandbox": "read-only"})
		id := s["thread"].(map[string]any)["id"].(string)
		e.turnText(id, "completed", text)
		return id
	}
	nativeID := start("openai", "gpt-6-astra", "Native first")
	legacyID := start("nebius-tofa", "moonshotai/Kimi-K3", "Legacy first")
	mixedID := start("tofa-native-router", "moonshotai/Kimi-K3", "Mixed TF first")
	e.call("thread/settings/update", map[string]any{"threadId": mixedID, "model": "gpt-6-astra"})
	e.turnText(mixedID, "completed", "Mixed native second")
	e.call("thread/name/set", map[string]string{"threadId": mixedID, "name": "Retained mixed history"})
	e.close()
	if fault == "launcher crash" {
		// Create history under the in-process owned transport first. The crashing
		// launcher subprocess then resumes the same profile without inference.
		stop()
		os.Remove(capture)
		os.Remove(capture + ".pid")
		if err := os.Remove(enginePath); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(enginePath, fake, 0700); err != nil {
			t.Fatal(err)
		}
		child, stop = executableDesktopFixture(t, app, bundle, capture, "--native-account-candidate", "--evaluation-observer", candidateProxyObserver(t))
		if err := os.Remove(enginePath); err != nil {
			t.Fatal(err)
		}
		if err := os.Symlink(installed, enginePath); err != nil {
			t.Fatal(err)
		}
	}
	preserved := map[string][]byte{}
	for _, path := range []string{filepath.Join(child.Env["CODEX_HOME"], "config.toml"), filepath.Join(child.Env["CODEX_HOME"], "auth.json")} {
		data, err := os.ReadFile(path)
		if err != nil {
			t.Fatal(err)
		}
		preserved[path] = data
	}
	owner, err := os.Readlink(filepath.Join(child.Env["CODEX_ELECTRON_USER_DATA_PATH"], "SingletonLock"))
	if err != nil {
		t.Fatal(err)
	}
	pid, err := strconv.Atoi(owner[strings.LastIndex(owner, "-")+1:])
	if err != nil {
		t.Fatal(err)
	}
	switch fault {
	case "client crash":
		if err := syscall.Kill(pid, syscall.SIGKILL); err != nil {
			t.Fatal(err)
		}
		waitDesktopPIDStopped(t, pid)
	case "client exit":
		if err := os.WriteFile(capture+".exit", nil, 0600); err != nil {
			t.Fatal(err)
		}
		waitDesktopPIDStopped(t, pid)
	}
	stop()
	if fault == "launcher crash" {
		assertExpiredDesktopContext(t, child)
		// Only the fixture's known process group is terminated; recovery never
		// assumes authority to stop a surviving native Desktop from a stale record.
		syscall.Kill(-pid, syscall.SIGKILL)
		waitDesktopPIDStopped(t, pid)
	}
	if fault == "client exit" {
		if err := os.Remove(capture + ".exit"); err != nil {
			t.Fatal(err)
		}
	}
	if fault == "interrupted replacement" {
		record := filepath.Join(filepath.Dir(child.Env["CODEX_CLI_PATH"]), "owner.json")
		data, err := os.ReadFile(record)
		if err != nil {
			t.Fatal(err)
		}
		var owner map[string]any
		if err := json.Unmarshal(data, &owner); err != nil {
			t.Fatal(err)
		}
		owner["PendingSHA256"], owner["SHA256"] = owner["SHA256"], strings.Repeat("0", 64)
		data, _ = json.Marshal(owner)
		if err := os.WriteFile(record, data, 0600); err != nil {
			t.Fatal(err)
		}
	}
	if fault == "uninstall and reinstall" {
		t.Setenv("TOFA_INSTALL_DIR", filepath.Join(t.TempDir(), "absent-install"))
		if err := app.Run([]string{"desktop-lifecycle", "uninstall"}); err != nil {
			t.Fatal(err)
		}
	}
	for path, before := range preserved {
		after, err := os.ReadFile(path)
		if err != nil || string(after) != string(before) {
			t.Fatalf("%s changed protected fixture state %s", fault, filepath.Base(path))
		}
	}
	if fault == "uninstall and reinstall" {
		assertExpiredDesktopContext(t, child, "uninstalled")
	} else {
		assertExpiredDesktopContext(t, child)
	}
	configPath := filepath.Join(child.Env["CODEX_HOME"], "config.toml")
	config, err := os.ReadFile(configPath)
	if err != nil {
		t.Fatal(err)
	}
	// A concurrent ordinary setting must survive every later launcher lifecycle.
	f, err := os.OpenFile(configPath, os.O_APPEND|os.O_WRONLY, 0600)
	if err != nil {
		t.Fatal(err)
	}
	f.WriteString("\n[tui]\nanimations = false\n")
	f.Close()
	config, _ = os.ReadFile(configPath)
	for _, secret := range []string{child.Env["TOFA_API_KEY"], "TOFA_DESKTOP_INFERENCE", "model_provider ="} {
		if secret != "" && strings.Contains(string(config), secret) {
			t.Fatal("inactive metadata persisted active authorization/default")
		}
	}
	ordinary := capturedDesktop{Cwd: child.Cwd, Env: map[string]string{"PATH": os.Getenv("PATH"), "HOME": os.Getenv("HOME"), "CODEX_HOME": child.Env["CODEX_HOME"], "CODEX_CLI_PATH": child.Env["CODEX_CLI_PATH"], "TOFA_API_KEY": child.Env["TOFA_API_KEY"], "TOFA_DESKTOP_INACTIVE": "stale-sentinel", "TOFA_DESKTOP_INFERENCE": "stale-inference"}}
	resume := func(id, provider, model string) {
		r := e.call("thread/resume", map[string]any{"threadId": id, "model": nil, "modelProvider": nil})
		if r["modelProvider"] != provider || r["model"] != model || r["thread"].(map[string]any)["id"] != id {
			t.Fatalf("recorded selection/identity changed: %v", r)
		}
	}
	checkHistory := func() {
		t.Helper()
		for id, provider := range map[string]string{nativeID: "openai", legacyID: "nebius-tofa", mixedID: "tofa-native-router"} {
			saved := e.call("thread/read", map[string]any{"threadId": id, "includeTurns": true})["thread"].(map[string]any)
			if saved["modelProvider"] != provider {
				t.Fatal("history provider migrated")
			}
			if id == mixedID {
				raw, _ := json.Marshal(saved)
				for _, text := range []string{"Retained mixed history", "Mixed TF first", "Mixed native second", "mixed-tool-output", "answer-gpt-6-astra", "answer-moonshotai/Kimi-K3"} {
					if !strings.Contains(string(raw), text) {
						t.Errorf("missing history %s", text)
					}
				}
			}
		}
	}
	// An explicit user-owned process definition must not inherit our sentinel.
	e = openDesktopEngine(t, ordinary, "model_catalog_json="+strconv.Quote(catalogPath), `model_providers.tofa-native-router.name="User-owned override"`)
	effective := e.call("config/read", map[string]any{})["config"].(map[string]any)
	provider := effective["model_providers"].(map[string]any)["tofa-native-router"].(map[string]any)
	if provider["env_key"] != nil {
		t.Fatal("ordinary bridge altered a user-owned process override")
	}
	e.close()
	for cycle := 0; cycle < 2; cycle++ {
		e = openDesktopEngine(t, ordinary, "model_catalog_json="+strconv.Quote(catalogPath), "openai_base_url="+strconv.Quote(native.URL))
		checkHistory()
		resume(mixedID, "tofa-native-router", "gpt-6-astra")
		mu.Lock()
		before := len(calls)
		mu.Unlock()
		result := historyTurn(t, e, mixedID, "Unavailable ordinary send")
		if result["status"] != "failed" || !strings.Contains(fmt.Sprint(result["error"]), "Relaunch through tofa") {
			t.Fatalf("missing actionable ordinary error: %v", result)
		}
		resume(legacyID, "nebius-tofa", "moonshotai/Kimi-K3")
		result = historyTurn(t, e, legacyID, "Unavailable legacy send")
		if result["status"] != "failed" || !strings.Contains(fmt.Sprint(result["error"]), "Relaunch through tofa") {
			t.Fatalf("legacy inactive guidance changed: %v", result)
		}
		mu.Lock()
		after := len(calls)
		mu.Unlock()
		if after != before {
			t.Fatal("ordinary routed history reached upstream")
		}
		resume(nativeID, "openai", "gpt-6-astra")
		e.turnText(nativeID, "completed", "Native ordinary continuation")
		e.close()
		e, child, stop = launch("zai-org/GLM-5.3")
		checkHistory()
		resume(mixedID, "tofa-native-router", "gpt-6-astra")
		e.turnText(mixedID, "completed", "Verify all mixed history")
		resume(legacyID, "nebius-tofa", "moonshotai/Kimi-K3")
		e.turnText(legacyID, "completed", "Legacy active continuation")
		resume(nativeID, "openai", "gpt-6-astra")
		e.turnText(nativeID, "completed", "Native active continuation")
		e.close()
		stop()
		current, _ := os.ReadFile(configPath)
		if string(current) != string(config) {
			t.Fatal("relaunch changed ordinary settings")
		}
	}
	if fault != "clean" {
		return
	}
	// Previously valid selected models remain recorded when the next catalog
	// omits them. Neither launch defaults nor native service are a fallback.
	e, child, stop = launch("zai-org/GLM-5.3")
	resume(mixedID, "tofa-native-router", "gpt-6-astra")
	e.call("thread/settings/update", map[string]any{"threadId": mixedID, "model": "moonshotai/Kimi-K3"})
	e.turnText(mixedID, "completed", "Select recorded TF model before it becomes unavailable")
	e.close()
	stop()
	removeKimi.Store(true)
	e, child, stop = launch("zai-org/GLM-5.3")
	checkHistory()
	for _, entry := range []struct{ id, provider string }{{mixedID, "tofa-native-router"}, {legacyID, "nebius-tofa"}} {
		resume(entry.id, entry.provider, "moonshotai/Kimi-K3")
		mu.Lock()
		before := len(calls)
		mu.Unlock()
		result := historyTurn(t, e, entry.id, "Unavailable recorded model")
		if result["status"] != "failed" || !strings.Contains(fmt.Sprint(result["error"]), "model") {
			t.Fatalf("unavailable recorded model failed without explicit model error: %v", result)
		}
		mu.Lock()
		after := len(calls)
		mu.Unlock()
		if before != after {
			t.Fatal("unavailable recorded model fell back to inference")
		}
	}
	resume(nativeID, "openai", "gpt-6-astra")
	e.turnText(nativeID, "completed", "Native stays available")
	e.close()
	stop()
	// Direct engine access keeps history readable and the route inert. Its native
	// error is not claimed as actionable Desktop guidance; native qualification
	// must verify ordinary Desktop actually uses the saved bridge above.
	direct := ordinary
	direct.Env = map[string]string{"PATH": os.Getenv("PATH"), "HOME": os.Getenv("HOME"), "CODEX_HOME": child.Env["CODEX_HOME"], "CODEX_CLI_PATH": installed}
	e = openDesktopEngine(t, direct, "model_catalog_json="+strconv.Quote(catalogPath), "openai_base_url="+strconv.Quote(native.URL))
	defer e.close()
	checkHistory()
	resume(mixedID, "tofa-native-router", "moonshotai/Kimi-K3")
	mu.Lock()
	before := len(calls)
	mu.Unlock()
	started := e.call("turn/start", map[string]any{"threadId": mixedID, "input": []any{map[string]string{"type": "text", "text": "Direct unavailable send"}}})
	turnID := started["turn"].(map[string]any)["id"].(string)
	// Without the saved bridge the native engine may retain a disconnected turn.
	// Explicitly cancel this bounded observation; it is not actionable guidance.
	timer := time.AfterFunc(time.Second, func() {
		e.encoder.Encode(map[string]any{"id": 9999, "method": "turn/interrupt", "params": map[string]string{"threadId": mixedID, "turnId": turnID}})
	})
	defer timer.Stop()
	for {
		m := e.read()
		t.Logf("direct inactive event: %v", m["method"])
		if m["method"] == "error" {
			t.Logf("direct inactive error: %v", m["params"])
		}
		if m["method"] == "turn/completed" {
			result := m["params"].(map[string]any)["turn"].(map[string]any)
			if result["status"] != "interrupted" && result["status"] != "failed" {
				t.Fatalf("inactive direct turn unexpectedly succeeded: %v", result)
			}
			break
		}
	}
	mu.Lock()
	defer mu.Unlock()
	if len(calls) != before {
		t.Fatal("direct ordinary access revived inference")
	}
}

// Failed turns can finish before turn/start acknowledges its request. Preserve
// both protocol orders instead of dropping early notifications in call().
func historyTurn(t *testing.T, e *desktopEngine, id, text string) map[string]any {
	t.Helper()
	e.id++
	if err := e.encoder.Encode(map[string]any{"id": e.id, "method": "turn/start", "params": map[string]any{"threadId": id, "input": []any{map[string]string{"type": "text", "text": text}}}}); err != nil {
		t.Fatal(err)
	}
	acknowledged := false
	var turn map[string]any
	for !acknowledged || turn == nil {
		m := e.read()
		if m["id"] == float64(e.id) {
			if m["error"] != nil {
				t.Fatalf("turn/start: %v", m["error"])
			}
			acknowledged = true
		}
		if m["method"] == "turn/completed" {
			params := m["params"].(map[string]any)
			if params["threadId"] == id {
				turn = params["turn"].(map[string]any)
			}
		}
	}
	return turn
}

func TestDesktopNativeCandidateInactiveOwnership(t *testing.T) {
	for _, scenario := range []string{"stale endpoint", "unexpected key", "competing edit"} {
		t.Run(scenario, func(t *testing.T) {
			bundle, capture := nativeCandidateFixture(t)
			app, _ := adapterFixture(t, nil, nil)
			child, stop := liveDesktopFixture(t, app, bundle, capture, "--native-account-candidate", "--evaluation-observer", candidateProxyObserver(t))
			stop()
			os.Remove(capture)
			path := filepath.Join(child.Env["CODEX_HOME"], "config.toml")
			raw, err := os.ReadFile(path)
			if err != nil {
				t.Fatal(err)
			}
			expected := raw
			want := "conflicts"
			switch scenario {
			case "stale endpoint":
				a := strings.Index(string(raw), "[model_providers.tofa-native-router]")
				expected = []byte(string(raw[:a]) + strings.Replace(string(raw[a:]), "http://127.0.0.1:0", "http://127.0.0.1:12345", 1))
				os.WriteFile(path, expected, 0600)
			case "unexpected key":
				expected = append(raw, []byte("unexpected_setting = true\n")...)
				os.WriteFile(path, expected, 0600)
			case "competing edit":
				// Delete only our owned router metadata, then interleave a user write before
				// the native version-checked batch inserts it again.
				a := strings.Index(string(raw), "[model_providers.tofa-native-router]")
				os.WriteFile(path, raw[:a], 0600)
				engine := filepath.Join(bundle, "Contents/Resources/codex")
				script, _ := os.ReadFile(engine)
				os.WriteFile(engine, []byte(strings.Replace(string(script), `MODE = "ignore"`, `MODE = "config-conflict"`, 1)), 0700)
				want = "competing configuration edit"
				expected = []byte("# concurrent user edit\nuser_setting = true\n")
			}
			err = app.Run([]string{"launch", "codex-desktop", "--app-bundle", bundle, "--model", "moonshotai/Kimi-K3", "--native-account-candidate", "--evaluation-observer", candidateProxyObserver(t)})
			if err == nil || !strings.Contains(err.Error(), want) {
				t.Fatalf("expected %s, got %v", want, err)
			}
			after, _ := os.ReadFile(path)
			if string(after) != string(expected) {
				t.Fatal("conflicting/competing user configuration overwritten")
			}
			if scenario != "competing edit" {
				if _, err := os.Stat(capture); !os.IsNotExist(err) {
					t.Fatal("incompatible router launched Desktop")
				}
			}
		})
	}
}

func TestDesktopNativeCandidateRecreatesMissingInactiveMetadata(t *testing.T) {
	bundle, capture := nativeCandidateFixture(t)
	app, _ := adapterFixture(t, nil, nil)
	child, stop := liveDesktopFixture(t, app, bundle, capture, "--native-account-candidate", "--evaluation-observer", candidateProxyObserver(t))
	stop()
	os.Remove(capture)
	path := filepath.Join(child.Env["CODEX_HOME"], "config.toml")
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	a := strings.Index(string(raw), "[model_providers.tofa-native-router]")
	if a < 0 {
		t.Fatal("missing initial metadata")
	}
	if err = os.WriteFile(path, raw[:a], 0600); err != nil {
		t.Fatal(err)
	}
	_, stop = liveDesktopFixture(t, app, bundle, capture, "--native-account-candidate", "--evaluation-observer", candidateProxyObserver(t))
	stop()
	after, _ := os.ReadFile(path)
	if !strings.HasPrefix(string(after), string(raw[:a])) || strings.Count(string(after), "[model_providers.tofa-native-router]") != 1 {
		t.Fatal("missing metadata recovery changed unrelated settings or duplicated the provider")
	}
}

// Negative control: native env_http_headers silently omits an absent variable,
// so it cannot replace env_key as a fail-fast ordinary-route sentinel.
func TestDesktopNativeCandidateMissingOptionalHeader(t *testing.T) {
	var requests atomic.Int32
	e, child, stop := routedCandidateEngine(t, func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("X-TOFA-Inactive") != "" {
			t.Error("absent optional variable produced a header")
		}
		requests.Add(1)
		emitFixtureResponse(w, fixtureMessage("optional header omitted"))
	}, func(w http.ResponseWriter, r *http.Request) { t.Error("unexpected native service") })
	defer stop()
	e.close()
	req, _ := http.NewRequest("GET", child.Env["TOFA_DESKTOP_CONTEXT"]+"/desktop-launch", nil)
	req.Header.Set("Authorization", "Bearer "+child.Env["TOFA_API_KEY"])
	res, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	var route struct {
		Overrides           []string
		InferenceCapability string
	}
	if json.NewDecoder(res.Body).Decode(&route) != nil {
		t.Fatal("missing route")
	}
	res.Body.Close()
	direct := capturedDesktop{Cwd: child.Cwd, Env: map[string]string{"PATH": os.Getenv("PATH"), "HOME": os.Getenv("HOME"), "CODEX_HOME": child.Env["CODEX_HOME"], "CODEX_CLI_PATH": os.Getenv("TOFA_TEST_DESKTOP_ENGINE"), "TOFA_DESKTOP_INFERENCE": route.InferenceCapability}}
	overrides := append(route.Overrides, `model_providers.tofa-native-router.env_http_headers={"X-TOFA-Launch"="TOFA_DESKTOP_INFERENCE","X-TOFA-Inactive"="SYNTHETIC_MISSING_INACTIVE"}`)
	e = openDesktopEngine(t, direct, overrides...)
	defer e.close()
	config := e.call("config/read", map[string]any{})["config"].(map[string]any)
	provider := config["model_providers"].(map[string]any)["tofa-native-router"].(map[string]any)
	if provider["env_http_headers"].(map[string]any)["X-TOFA-Inactive"] != "SYNTHETIC_MISSING_INACTIVE" {
		t.Fatal("missing-header negative control absent from config")
	}
	s := e.call("thread/start", map[string]any{"cwd": child.Cwd, "approvalPolicy": "never", "sandbox": "read-only"})
	e.turnText(s["thread"].(map[string]any)["id"].(string), "completed", "Check optional header")
	if requests.Load() != 1 {
		t.Fatal("missing optional header did not reach the owned upstream")
	}
}

// Change only the owned fixture catalog between launches, preserving real
// adapter admission and the native destination interception.
type historyCatalogTransport struct {
	base       http.RoundTripper
	removeKimi *atomic.Bool
}

func (t historyCatalogTransport) RoundTrip(r *http.Request) (*http.Response, error) {
	res, err := t.base.RoundTrip(r)
	if err != nil || r.URL.Path != "/models" || !t.removeKimi.Load() {
		return res, err
	}
	defer res.Body.Close()
	var catalog struct {
		Data []map[string]any `json:"data"`
	}
	if err = json.NewDecoder(res.Body).Decode(&catalog); err != nil {
		return nil, err
	}
	var keep []map[string]any
	for _, m := range catalog.Data {
		if m["id"] != "moonshotai/Kimi-K3" {
			keep = append(keep, m)
		}
	}
	catalog.Data = keep
	raw, _ := json.Marshal(catalog)
	res.Body = io.NopCloser(bytes.NewReader(raw))
	res.ContentLength = int64(len(raw))
	return res, nil
}
