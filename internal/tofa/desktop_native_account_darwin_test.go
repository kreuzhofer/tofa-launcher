package tofa_test

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"net/http/httputil"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

func nativeCandidateObserver(t *testing.T) string {
	t.Helper()
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(`{"ready":true}`))
	}))
	t.Cleanup(server.Close)
	path := filepath.Join(t.TempDir(), "observer.json")
	raw, _ := json.Marshal(map[string]any{"version": 2, "endpoint": server.URL, "secret": "synthetic-qualification-control", "seconds": 900})
	if err := os.WriteFile(path, raw, 0600); err != nil {
		t.Fatal(err)
	}
	return path
}

func TestDesktopNativeCandidateRequiresSignedInAccountBeforeStartup(t *testing.T) {
	bundle, capture := desktopFixture(t, "ignore")
	app, _ := adapterFixture(t, nil, nil)
	err := app.Run([]string{"launch", "codex-desktop", "--app-bundle", bundle, "--model", "moonshotai/Kimi-K3", "--native-account-candidate", "--evaluation-observer", nativeCandidateObserver(t)})
	if err == nil || !strings.Contains(err.Error(), "ChatGPT sign-in") {
		t.Fatalf("expected actionable account prerequisite, got %v", err)
	}
	if _, err := os.Stat(capture); !os.IsNotExist(err) {
		t.Fatal("missing account launched Desktop")
	}
	if _, err := os.Stat(filepath.Join(os.Getenv("HOME"), ".codex", "config.toml")); !os.IsNotExist(err) {
		t.Fatal("missing account changed shared configuration")
	}
}

func nativeCandidateFixture(t *testing.T) (string, string) {
	t.Helper()
	bundle, capture := desktopFixture(t, "ignore")
	engine := filepath.Join(bundle, "Contents/Resources/codex")
	raw, err := os.ReadFile(engine)
	if err != nil {
		t.Fatal(err)
	}
	script := strings.Replace(string(raw), "        if req['method'] == 'config/read':", "        if req['method'] == 'account/read': result = {'account':{'type':'chatgpt'},'requiresOpenaiAuth':True}\n        if req['method'] == 'config/read':", 1)
	if err := os.WriteFile(engine, []byte(script), 0700); err != nil {
		t.Fatal(err)
	}
	return bundle, capture
}

func TestDesktopNativeCandidateIsolatesInferenceAndControl(t *testing.T) {
	bundle, capture := nativeCandidateFixture(t)
	app, _ := adapterFixture(t, func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer fixture-secret" || r.Header.Get("X-TOFA-Launch") != "" || r.Header.Get("ChatGPT-Account-ID") != "" {
			t.Error("upstream credential separation failed")
		}
		w.Write([]byte(`{"output":[]}`))
	}, nil)
	// The observer forwards the owned adapter; it does not grant admission itself.
	observer := candidateProxyObserver(t)
	child, stop := liveDesktopFixture(t, app, bundle, capture, "--native-account-candidate", "--evaluation-observer", observer)
	defer stop()
	request, _ := http.NewRequest("GET", child.Env["TOFA_DESKTOP_CONTEXT"]+"/desktop-launch", nil)
	request.Header.Set("Authorization", "Bearer "+child.Env["TOFA_API_KEY"])
	response, err := http.DefaultClient.Do(request)
	if err != nil {
		t.Fatal(err)
	}
	var route struct {
		InferenceCapability string
		Overrides           []string
	}
	json.NewDecoder(response.Body).Decode(&route)
	response.Body.Close()
	if route.InferenceCapability == "" || route.InferenceCapability == child.Env["TOFA_API_KEY"] {
		t.Fatal("inference capability is absent or grants launch control")
	}
	for _, tc := range []struct {
		name, method, path, auth string
		headers                  []string
		want                     int
	}{
		{"native credentials alone", "POST", "/responses", "native-account", nil, 401},
		{"control cannot infer", "POST", "/responses", child.Env["TOFA_API_KEY"], nil, 401},
		{"missing", "POST", "/responses", "", nil, 401},
		{"wrong", "POST", "/responses", "native-account", []string{"wrong"}, 401},
		{"malformed native bearer", "POST", "/responses", "a,b", []string{route.InferenceCapability}, 401},
		{"duplicate", "POST", "/responses", "native-account", []string{route.InferenceCapability, route.InferenceCapability}, 401},
		{"comma", "POST", "/responses", "native-account", []string{route.InferenceCapability + ", " + route.InferenceCapability}, 401},
		{"inference cannot read control", "GET", "/desktop-launch", "", []string{route.InferenceCapability}, 401},
		{"inference cannot stop", "POST", "/evaluation-stop", "", []string{route.InferenceCapability}, 401},
		{"inference cannot cancel review", "POST", "/desktop-review-cancel", "", []string{route.InferenceCapability}, 401},
		{"legacy inference cannot cancel review", "POST", "/desktop-review-cancel", route.InferenceCapability, nil, 401},
		{"wrong method", "GET", "/responses", "native-account", []string{route.InferenceCapability}, 405},
		{"query", "POST", "/responses?x=1", "native-account", []string{route.InferenceCapability}, 404},
		{"authorized", "POST", "/responses", "native-account", []string{route.InferenceCapability}, 200},
	} {
		t.Run(tc.name, func(t *testing.T) {
			req, _ := http.NewRequest(tc.method, child.Env["TOFA_DESKTOP_CONTEXT"]+tc.path, strings.NewReader(`{"model":"moonshotai/Kimi-K3","input":[]}`))
			if tc.auth != "" {
				req.Header.Set("Authorization", "Bearer "+tc.auth)
			}
			for _, value := range tc.headers {
				req.Header.Add("X-TOFA-Launch", value)
			}
			req.Header.Set("ChatGPT-Account-ID", "synthetic-private-account")
			res, err := http.DefaultClient.Do(req)
			if err != nil {
				t.Fatal(err)
			}
			res.Body.Close()
			if res.StatusCode != tc.want {
				t.Fatalf("got %d, want %d", res.StatusCode, tc.want)
			}
		})
	}
}

func candidateProxyObserver(t *testing.T) string {
	t.Helper()
	var mu sync.Mutex
	var upstream string
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/register" {
			var data struct {
				Version   int    `json:"version"`
				Endpoint  string `json:"endpoint"`
				Control   string `json:"control_token"`
				Inference string `json:"inference_token"`
			}
			if err := json.NewDecoder(r.Body).Decode(&data); err != nil || data.Version != 2 || len(data.Control) != 64 || len(data.Inference) != 64 || data.Control == data.Inference {
				t.Error("invalid v2 observer registration")
				w.WriteHeader(400)
				return
			}
			mu.Lock()
			upstream = data.Endpoint
			mu.Unlock()
			w.Write([]byte(`{"ready":true}`))
			return
		}
		mu.Lock()
		endpoint, _ := url.Parse(upstream)
		mu.Unlock()
		httputil.NewSingleHostReverseProxy(endpoint).ServeHTTP(w, r)
	}))
	t.Cleanup(server.Close)
	path := filepath.Join(t.TempDir(), "observer.json")
	raw, _ := json.Marshal(map[string]any{"version": 2, "endpoint": server.URL, "secret": "synthetic-qualification-control", "seconds": 900})
	if err := os.WriteFile(path, raw, 0600); err != nil {
		t.Fatal(err)
	}
	return path
}

func TestDesktopNativeCandidateBundledEngineTurn(t *testing.T) {
	installed := os.Getenv("TOFA_TEST_DESKTOP_ENGINE")
	if installed == "" {
		t.Skip("set TOFA_TEST_DESKTOP_ENGINE")
	}
	bundle, capture := nativeCandidateFixture(t)
	t.Setenv("EXISTING_PRIVATE", "synthetic-user-private")
	// desktopFixture has set HOME to t.TempDir; additionally prove containment before fixture writes.
	fixtureHome := filepath.Join(os.Getenv("HOME"), ".codex")
	relative, err := filepath.Rel(os.TempDir(), fixtureHome)
	if err != nil || strings.HasPrefix(relative, "..") {
		t.Fatal("fixture home must be beneath test temporary root")
	}
	os.MkdirAll(fixtureHome, 0700)
	if err := os.WriteFile(filepath.Join(fixtureHome, "config.toml"), []byte(`shell_environment_policy.exclude = ["EXISTING_PRIVATE"]`+"\n"), 0600); err != nil {
		t.Fatal(err)
	}
	command := exec.Command(installed, "debug", "models", "--bundled")
	command.Env = []string{"PATH=" + os.Getenv("PATH"), "HOME=" + os.Getenv("HOME"), "CODEX_HOME=" + filepath.Join(os.Getenv("HOME"), ".codex")}
	catalog, err := command.Output()
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(bundle, "Contents/Resources/native-catalog.json"), catalog, 0600); err != nil {
		t.Fatal(err)
	}
	var requests atomic.Int32
	var childOutputs atomic.Int32
	app, _ := adapterFixture(t, func(w http.ResponseWriter, r *http.Request) {
		step := requests.Add(1)
		var body struct{ Input []map[string]any }
		json.NewDecoder(r.Body).Decode(&body)
		for _, item := range body.Input {
			if item["type"] == "function_call_output" && strings.Contains(fmt.Sprint(item["output"]), "CONTROL=unset INFERENCE=unset USER=unset") {
				childOutputs.Add(1)
			}
		}
		if r.Header.Get("Authorization") != "Bearer fixture-secret" || r.Header.Get("X-TOFA-Launch") != "" {
			t.Error("native credential/header escaped to Token Factory")
		}
		if step <= 2 {
			args, _ := json.Marshal(map[string]any{"cmd": `printf 'CONTROL=%s INFERENCE=%s USER=%s' "${TOFA_API_KEY-unset}" "${TOFA_DESKTOP_INFERENCE-unset}" "${EXISTING_PRIVATE-unset}"`, "login": step == 1, "max_output_tokens": 100})
			emitFixtureResponse(w, map[string]any{"id": fmt.Sprintf("env_%d", step), "type": "function_call", "call_id": fmt.Sprintf("env_call_%d", step), "name": "exec_command", "arguments": string(args), "status": "completed"})
			return
		}
		w.Header().Set("Content-Type", "text/event-stream")
		w.Write([]byte("event: response.completed\ndata: {\"type\":\"response.completed\",\"response\":{\"id\":\"fixture\",\"status\":\"completed\",\"output\":[],\"usage\":{\"input_tokens\":1,\"output_tokens\":0,\"total_tokens\":1}}}\n\n"))
	}, nil)
	child, stop := liveDesktopFixture(t, app, bundle, capture, "--native-account-candidate", "--evaluation-observer", actualCandidateObserver(t))
	defer stop()
	// Fake account preflight is separate from this actual-engine transport fixture.
	// Signed-in account preservation is verified independently, without inference.
	deadline := time.Now().Add(10 * time.Second)
	for {
		if _, err := os.Stat(capture + ".pid"); err == nil {
			break
		}
		if time.Now().After(deadline) {
			t.Fatal("fixture worker not ready")
		}
		time.Sleep(10 * time.Millisecond)
	}
	path := filepath.Join(bundle, "Contents/Resources/codex")
	if err := os.Remove(path); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(installed, path); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(child.Env["CODEX_HOME"], "auth.json"), []byte(`{"OPENAI_API_KEY":"synthetic-native"}`), 0600); err != nil {
		t.Fatal(err)
	}
	python, err := exec.LookPath("python3")
	if err != nil {
		t.Fatal(err)
	}
	mcpScript := filepath.Join(t.TempDir(), "probe.py")
	mcpResult := filepath.Join(t.TempDir(), "presence.json")
	script := `import json,os,sys
with open(sys.argv[1],'w') as output: json.dump({name:name in os.environ for name in ['TOFA_API_KEY','TOFA_DESKTOP_CONTEXT','TOFA_DESKTOP_INFERENCE']},output)
for line in sys.stdin:
 request=json.loads(line)
 if 'id' not in request: continue
 result={'protocolVersion':'2024-11-05','capabilities':{'tools':{}},'serverInfo':{'name':'synthetic-env-probe','version':'1'}} if request.get('method')=='initialize' else {'tools':[]}
 print(json.dumps({'jsonrpc':'2.0','id':request['id'],'result':result}),flush=True)
`
	if err := os.WriteFile(mcpScript, []byte(script), 0600); err != nil {
		t.Fatal(err)
	}
	mcpArgs, _ := json.Marshal([]string{mcpScript, mcpResult})
	engine := openDesktopEngine(t, child, "mcp_servers.synthetic_env_probe.command="+strconv.Quote(python), "mcp_servers.synthetic_env_probe.args="+string(mcpArgs))
	started := engine.call("thread/start", map[string]any{"cwd": child.Cwd, "approvalPolicy": "never", "sandbox": "read-only"})
	if started["modelProvider"] != "tofa-native-router" {
		t.Fatalf("wrong new-conversation provider: %v", started["modelProvider"])
	}
	id := started["thread"].(map[string]any)["id"].(string)
	engine.turn(id, "completed")
	raw, err := os.ReadFile(mcpResult)
	if err != nil {
		t.Fatal(err)
	}
	var presence map[string]bool
	if json.Unmarshal(raw, &presence) != nil {
		t.Fatal("invalid MCP presence result")
	}
	for _, name := range []string{"TOFA_API_KEY", "TOFA_DESKTOP_CONTEXT", "TOFA_DESKTOP_INFERENCE"} {
		value, observed := presence[name]
		if !observed || value {
			t.Errorf("MCP child unexpectedly inherits %s", name)
		}
	}
	if requests.Load() != 3 || childOutputs.Load() != 3 {
		t.Fatalf("actual login/nonlogin tool inheritance checks: requests=%d outputs=%d", requests.Load(), childOutputs.Load())
	}
	engine.close()
	request, _ := http.NewRequest("GET", child.Env["TOFA_DESKTOP_CONTEXT"]+"/desktop-launch", nil)
	request.Header.Set("Authorization", "Bearer "+child.Env["TOFA_API_KEY"])
	response, err := http.DefaultClient.Do(request)
	if err != nil {
		t.Fatal(err)
	}
	var route struct {
		Overrides           []string
		InferenceCapability string
	}
	json.NewDecoder(response.Body).Decode(&route)
	response.Body.Close()
	if strings.Contains(strings.Join(route.Overrides, " "), route.InferenceCapability) {
		t.Fatal("capability leaked into engine arguments")
	}
	err = filepath.WalkDir(child.Env["CODEX_HOME"], func(path string, entry os.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if !entry.Type().IsRegular() {
			return nil
		}
		raw, err := os.ReadFile(path)
		if err != nil {
			return err
		}
		if strings.Contains(string(raw), route.InferenceCapability) {
			return fmt.Errorf("capability leaked into retained engine artifact %s", entry.Name())
		}
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
	for _, fault := range []string{"handshake", "disconnect"} {
		for _, secretLocation := range []string{"path-negative-control", "header"} {
			t.Run(fault+"/"+secretLocation, func(t *testing.T) {
				var observed atomic.Bool
				var headerReceived atomic.Bool
				upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
					if r.Method != "GET" {
						w.WriteHeader(503)
						return
					}
					observed.Store(true)
					headerReceived.Store(r.Header.Get("X-TOFA-Launch") == route.InferenceCapability)
					connection, _, err := w.(http.Hijacker).Hijack()
					if err != nil {
						t.Error(err)
						return
					}
					defer connection.Close()
					if fault == "handshake" {
						connection.Write([]byte("HTTP/1.0 426 Upgrade Required\r\nContent-Length: 0\r\n\r\n"))
					}
				}))
				defer upstream.Close()
				endpoint := upstream.URL
				probeSecret := route.InferenceCapability
				if secretLocation == "path-negative-control" {
					probeSecret = strings.Repeat("a", 64)
					endpoint += "/" + probeSecret
				}
				overrides := append([]string{}, route.Overrides...)
				overrides = append(overrides, `model="gpt-6-astra"`, `model_providers.tofa-native-router.supports_websockets=true`, "model_providers.tofa-native-router.base_url="+strconv.Quote(endpoint))
				if secretLocation == "path-negative-control" {
					overrides = append(overrides, `model_providers.tofa-native-router.env_http_headers={}`)
				}
				direct := child
				direct.Env = map[string]string{}
				for key, value := range child.Env {
					if !strings.HasPrefix(key, "TOFA_") {
						direct.Env[key] = value
					}
				}
				direct.Env["CODEX_CLI_PATH"] = installed
				direct.Env["TOFA_DESKTOP_INFERENCE"] = route.InferenceCapability
				probe := openDesktopEngine(t, direct, overrides...)
				started := probe.call("thread/start", map[string]any{"cwd": child.Cwd, "approvalPolicy": "never", "sandbox": "read-only"})
				probe.call("turn/start", map[string]any{"threadId": started["thread"].(map[string]any)["id"], "input": []any{map[string]string{"type": "text", "text": "Synthetic local transport fault; no tools."}}})
				deadline := time.Now().Add(10 * time.Second)
				var diagnostics []byte
				for time.Now().Before(deadline) {
					diagnostics, _ = os.ReadFile(probe.stderrPath)
					if observed.Load() && strings.Contains(string(diagnostics), "responses_websocket") {
						break
					}
					time.Sleep(25 * time.Millisecond)
				}
				probe.close()
				if !observed.Load() || !strings.Contains(string(diagnostics), "responses_websocket") {
					t.Fatal("native websocket error trigger did not run")
				}
				leaked := strings.Contains(string(diagnostics), probeSecret)
				if leaked != (secretLocation == "path-negative-control") {
					t.Fatalf("unexpected secret disclosure outcome: leaked=%v", leaked)
				}
				if secretLocation == "header" && !headerReceived.Load() {
					t.Fatal("engine did not deliver header capability")
				}
				// Retain only sanitized error evidence even for the intentional negative control.
				os.WriteFile(probe.stderrPath, []byte(strings.ReplaceAll(string(diagnostics), probeSecret, "<REDACTED>")), 0600)
			})
		}
	}
}

func TestDesktopNativeCandidateAdmissionAndConflict(t *testing.T) {
	for _, scenario := range []string{"missing observer", "old observer", "existing provider", "protected plugin"} {
		t.Run(scenario, func(t *testing.T) {
			bundle, capture := nativeCandidateFixture(t)
			app, _ := adapterFixture(t, nil, nil)
			args := []string{"launch", "codex-desktop", "--app-bundle", bundle, "--model", "moonshotai/Kimi-K3", "--native-account-candidate"}
			want := "bounded evaluation observer"
			if scenario != "missing observer" {
				observer := nativeCandidateObserver(t)
				if scenario == "old observer" {
					raw, _ := os.ReadFile(observer)
					os.WriteFile(observer, []byte(strings.Replace(string(raw), `"version":2`, `"version":1`, 1)), 0600)
					want = "version 2"
				}
				args = append(args, "--evaluation-observer", observer)
			}
			if scenario == "existing provider" {
				home := filepath.Join(os.Getenv("HOME"), ".codex")
				relative, _ := filepath.Rel(os.TempDir(), home)
				if strings.HasPrefix(relative, "..") {
					t.Fatal("nonfixture HOME")
				}
				os.MkdirAll(home, 0700)
				os.WriteFile(filepath.Join(home, "config.toml"), []byte("[model_providers.tofa-native-router]\nname=\"user-owned\"\n"), 0600)
				want = "conflicts"
			}
			if scenario == "protected plugin" {
				path := filepath.Join(os.Getenv("HOME"), ".codex/plugins/cache/openai-bundled/code-review/fixture")
				relative, _ := filepath.Rel(os.TempDir(), path)
				if strings.HasPrefix(relative, "..") {
					t.Fatal("nonfixture HOME")
				}
				os.MkdirAll(path, 0700)
				want = "startup blocked"
			}
			err := app.Run(args)
			if err == nil || !strings.Contains(err.Error(), want) {
				t.Fatalf("expected %q refusal, got %v", want, err)
			}
			if _, err := os.Stat(capture); !os.IsNotExist(err) {
				t.Fatal("invalid candidate launched Desktop")
			}
		})
	}
}

func TestDesktopNativeCandidateExpiresCapabilities(t *testing.T) {
	bundle, capture := nativeCandidateFixture(t)
	var requests atomic.Int32
	app, _ := adapterFixture(t, func(w http.ResponseWriter, r *http.Request) { requests.Add(1); w.Write([]byte(`{"output":[]}`)) }, nil)
	var previousCapability, previousEndpoint string
	for attempt := 0; attempt < 2; attempt++ {
		child, stop := liveDesktopFixture(t, app, bundle, capture, "--native-account-candidate", "--evaluation-observer", candidateProxyObserver(t))
		req, _ := http.NewRequest("GET", child.Env["TOFA_DESKTOP_CONTEXT"]+"/desktop-launch", nil)
		req.Header.Set("Authorization", "Bearer "+child.Env["TOFA_API_KEY"])
		res, err := http.DefaultClient.Do(req)
		if err != nil {
			t.Fatal(err)
		}
		var route struct{ InferenceCapability string }
		json.NewDecoder(res.Body).Decode(&route)
		res.Body.Close()
		if previousCapability != "" {
			if route.InferenceCapability == previousCapability {
				t.Fatal("new launch reused inference capability")
			}
			stale, _ := http.NewRequest("POST", child.Env["TOFA_DESKTOP_CONTEXT"]+"/responses", strings.NewReader(`{"model":"moonshotai/Kimi-K3","input":[]}`))
			stale.Header.Set("X-TOFA-Launch", previousCapability)
			denied, err := http.DefaultClient.Do(stale)
			if err != nil {
				t.Fatal(err)
			}
			denied.Body.Close()
			if denied.StatusCode != 401 {
				t.Fatal("another launch capability authorized inference")
			}
		}
		previousCapability, previousEndpoint = route.InferenceCapability, child.Env["TOFA_DESKTOP_CONTEXT"]
		stop()
		stale, _ := http.NewRequest("POST", previousEndpoint+"/responses", strings.NewReader(`{"model":"moonshotai/Kimi-K3","input":[]}`))
		stale.Header.Set("X-TOFA-Launch", previousCapability)
		ended, err := http.DefaultClient.Do(stale)
		if err == nil {
			ended.Body.Close()
			if ended.StatusCode < 400 {
				t.Fatal("expired route accepted inference")
			}
		}
		if requests.Load() != 0 {
			t.Fatal("expired or foreign launch sent inference upstream")
		}
		if err := os.Remove(capture); err != nil {
			t.Fatal(err)
		}
	}
}

// This starts the repository's actual observer, not a matching Go mock. It is
// deliberately case05 with no prompt restriction: this fixture tests transport,
// not presentation qualification or an externally submitted model task.
func actualCandidateObserver(t *testing.T, serviceMaps ...map[string]string) string {
	var services map[string]string
	if len(serviceMaps) > 0 {
		services = serviceMaps[0]
	}
	return actualCandidateObserverBudget(t, services, 10)
}

func actualCandidateObserverBudget(t *testing.T, services map[string]string, requests int) string {
	t.Helper()
	scripts, err := filepath.Abs("../../scripts")
	if err != nil {
		t.Fatal(err)
	}
	run := t.TempDir()
	config := filepath.Join(run, "observer.json")
	driver := `import json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from capability_observer import Observer
run=Path(sys.argv[2]);(run/'workspace').mkdir()
with Observer(run,model='moonshotai/Kimi-K3',guardian='zai-org/GLM-5.3-Flash',limits={'seconds':600,'requests':int(sys.argv[4]),'output_tokens':4096},model_services=json.loads(sys.argv[3])) as observer:
 config=run/'observer.json'
 config.write_text(json.dumps({'version':2,'endpoint':observer.url,'secret':observer.secret,'seconds':600}))
 config.chmod(0o600)
 (run/'ready').touch()
 sys.stdin.read()
`
	ctx, cancel := context.WithTimeout(context.Background(), 120*time.Second)
	declaration, _ := json.Marshal(services)
	command := exec.CommandContext(ctx, "python3", "-B", "-c", driver, scripts, run, string(declaration), strconv.Itoa(requests))
	input, err := command.StdinPipe()
	if err != nil {
		t.Fatal(err)
	}
	if err := command.Start(); err != nil {
		cancel()
		t.Fatal(err)
	}
	t.Cleanup(func() { input.Close(); command.Wait(); cancel() })
	deadline := time.Now().Add(10 * time.Second)
	for {
		if _, err := os.Stat(filepath.Join(run, "ready")); err == nil {
			return config
		}
		if time.Now().After(deadline) {
			cancel()
			t.Fatal("actual observer startup timed out")
		}
		time.Sleep(10 * time.Millisecond)
	}
}
