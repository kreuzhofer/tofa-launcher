package tofa_test

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"os/exec"
	"path/filepath"
	"reflect"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

// Public app-server protocol driver. Responses and notifications share stdout.
type desktopEngine struct {
	t          *testing.T
	command    *exec.Cmd
	input      io.WriteCloser
	encoder    *json.Encoder
	decoder    *json.Decoder
	id         int
	stderrPath string
}

func TestDesktopUsesAuthenticatedNativeCatalog(t *testing.T) {
	installed := os.Getenv("TOFA_TEST_DESKTOP_ENGINE")
	if installed == "" {
		t.Skip("set TOFA_TEST_DESKTOP_ENGINE")
	}
	for _, scenario := range []string{"online", "unavailable", "unavailable with foreign cache", "bundled-identical account", "static custom catalog"} {
		t.Run(scenario, func(t *testing.T) {
			unavailable := strings.HasPrefix(scenario, "unavailable")
			bundledOnly := scenario == "bundled-identical account"
			static := scenario == "static custom catalog"
			bundle, capture := desktopFixture(t, "normal")
			probeHome := t.TempDir()
			command := exec.Command(installed, "debug", "models", "--bundled")
			command.Dir = probeHome
			command.Env = []string{"PATH=" + os.Getenv("PATH"), "HOME=" + probeHome, "CODEX_HOME=" + probeHome}
			raw, err := command.Output()
			if err != nil {
				t.Fatal(err)
			}
			var bundled struct{ Models []map[string]any }
			if err := json.Unmarshal(raw, &bundled); err != nil || len(bundled.Models) == 0 {
				t.Fatal("missing bundled test descriptor")
			}
			descriptor := bundled.Models[0]
			descriptor["slug"], descriptor["display_name"], descriptor["supported_in_api"] = "fixture-account-native", "Native account choice", false
			var requests atomic.Int32
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				requests.Add(1)
				if r.URL.Path != "/models" || r.Header.Get("Authorization") != "Bearer synthetic-access" {
					t.Error("native catalog discovery lost account auth")
				}
				if unavailable {
					w.WriteHeader(http.StatusUnauthorized)
					return
				}
				if bundledOnly {
					w.Write(raw)
					return
				}
				json.NewEncoder(w).Encode(map[string]any{"models": []any{descriptor}})
			}))
			defer server.Close()
			encode := func(value string) string { return base64.RawURLEncoding.EncodeToString([]byte(value)) }
			token := encode(`{"alg":"none","typ":"JWT"}`) + "." + encode(`{"https://api.openai.com/auth":{"chatgpt_plan_type":"plus","chatgpt_account_id":"synthetic-account","chatgpt_user_id":"synthetic-user"}}`) + "." + encode("signature")
			auth := map[string]any{"auth_mode": "chatgpt", "tokens": map[string]string{"id_token": token, "access_token": "synthetic-access", "refresh_token": "synthetic-refresh", "account_id": "synthetic-account"}, "last_refresh": time.Now().UTC().Format(time.RFC3339)}
			discovery := map[string]any{"engine": installed, "endpoint": server.URL, "auth": auth}
			if static {
				discovery["catalog"] = map[string]any{"models": []any{descriptor}}
			}
			if scenario == "unavailable with foreign cache" {
				// Keep the cache version valid for the selected real engine so the
				// foreign identity remains the reason it must reject this cache.
				versionCommand := exec.Command(installed, "--version")
				versionCommand.Env, versionCommand.Dir = command.Env, command.Dir
				version, err := versionCommand.Output()
				if err != nil {
					t.Fatal(err)
				}
				cacheVersion := strings.TrimPrefix(strings.TrimSpace(string(version)), "codex-cli ")
				cacheVersion, _, _ = strings.Cut(cacheVersion, "-")
				cacheVersion, _, _ = strings.Cut(cacheVersion, "+")
				var shipped struct{ Models []map[string]any }
				if err := json.Unmarshal(raw, &shipped); err != nil {
					t.Fatal(err)
				}
				for _, model := range shipped.Models {
					delete(model, "base_instructions")
				}
				discovery["cache"] = map[string]any{"models": shipped.Models, "fetched_at": time.Now().UTC().Format(time.RFC3339), "client_version": cacheVersion, "identity": "another-synthetic-account"}
			}
			spec, err := json.Marshal(discovery)
			if err != nil {
				t.Fatal(err)
			}
			if err := os.WriteFile(filepath.Join(bundle, "Contents/Resources/native-discovery.json"), spec, 0600); err != nil {
				t.Fatal(err)
			}
			app, _ := adapterFixture(t, nil, nil)
			err = app.Run([]string{"launch", "codex-desktop", "--app-bundle", bundle, "--model", "moonshotai/Kimi-K3", "--allow-unverified"})
			if static {
				if requests.Load() != 0 {
					t.Fatal("static catalog unexpectedly performed native discovery")
				}
				if err == nil || !strings.Contains(err.Error(), "model_catalog_json") {
					t.Fatalf("static catalog refusal must identify the setting that bypasses discovery: %v", err)
				}
				if _, err := os.Stat(capture); !os.IsNotExist(err) {
					t.Fatal("desktop initialized with an unqualified static account catalog")
				}
				home := filepath.Join(os.Getenv("HOME"), ".codex")
				configPath := filepath.Join(home, "config.toml")
				config, readErr := os.ReadFile(configPath)
				if readErr != nil {
					t.Fatal(readErr)
				}
				staticLine := "model_catalog_json=" + fmt.Sprintf("%q", filepath.Join(home, "static-models.json")) + "\n"
				if !strings.Contains(string(config), staticLine) {
					t.Fatal("refused launch removed the user's static catalog setting")
				}
				// Only the operator's explicit correction enables native discovery.
				// Apply that correction to this synthetic profile, then retry.
				if err := os.WriteFile(configPath, []byte(strings.Replace(string(config), staticLine, "", 1)), 0600); err != nil {
					t.Fatal(err)
				}
				err = app.Run([]string{"launch", "codex-desktop", "--app-bundle", bundle, "--model", "moonshotai/Kimi-K3", "--allow-unverified"})
			}
			if requests.Load() == 0 {
				t.Fatal("native account catalog was never requested")
			}
			if unavailable || bundledOnly {
				if err == nil || !strings.Contains(err.Error(), "freshness") {
					t.Fatalf("authenticated discovery silently fell back to shipped metadata: %v", err)
				}
				if scenario == "unavailable with foreign cache" && !strings.Contains(err.Error(), "ambiguous") {
					t.Fatalf("foreign cache did not exercise bundled-fallback ambiguity: %v", err)
				}
				if _, err := os.Stat(capture); !os.IsNotExist(err) {
					t.Fatal("desktop started after authenticated discovery failure")
				}
				return
			}
			if err != nil {
				t.Fatal(err)
			}
			raw, err = os.ReadFile(capture)
			if err != nil {
				t.Fatal(err)
			}
			var child struct {
				Catalog struct{ Models []map[string]any }
				Env     map[string]string
			}
			if err := json.Unmarshal(raw, &child); err != nil {
				t.Fatal(err)
			}
			if len(child.Catalog.Models) != 6 || !reflect.DeepEqual(child.Catalog.Models[0], descriptor) {
				t.Fatal("effective account catalog replaced with bundled choices or altered")
			}
			raw, err = os.ReadFile(filepath.Join(child.Env["CODEX_HOME"], "auth.json"))
			if err != nil {
				t.Fatal(err)
			}
			var retained map[string]any
			if json.Unmarshal(raw, &retained) != nil {
				t.Fatal("synthetic account state damaged")
			}
			before, _ := json.Marshal(auth)
			after, _ := json.Marshal(retained)
			if string(before) != string(after) {
				t.Fatal("launch changed account credentials")
			}

			cached, err := os.ReadFile(filepath.Join(child.Env["CODEX_HOME"], "models_cache.json"))
			if err != nil {
				t.Fatal(err)
			}
			for _, scenario := range []string{"fresh", "expired", "different account", "different version"} {
				t.Run(scenario, func(t *testing.T) {
					var cache map[string]any
					if err := json.Unmarshal(cached, &cache); err != nil {
						t.Fatal(err)
					}
					switch scenario {
					case "expired":
						cache["fetched_at"] = time.Now().Add(-6 * time.Minute).UTC().Format(time.RFC3339)
					case "different account":
						cache["identity"] = "another-synthetic-account"
					case "different version":
						cache["client_version"] = "0.0.0"
					}
					spec, err := json.Marshal(map[string]any{"engine": installed, "endpoint": server.URL, "auth": auth, "cache": cache})
					if err != nil {
						t.Fatal(err)
					}
					if err := os.WriteFile(filepath.Join(bundle, "Contents/Resources/native-discovery.json"), spec, 0600); err != nil {
						t.Fatal(err)
					}
					cacheData, err := json.Marshal(cache)
					if err != nil {
						t.Fatal(err)
					}
					if err := os.WriteFile(filepath.Join(child.Env["CODEX_HOME"], "models_cache.json"), cacheData, 0600); err != nil {
						t.Fatal(err)
					}
					previous := requests.Load()
					if err := app.Run([]string{"launch", "codex-desktop", "--app-bundle", bundle, "--model", "moonshotai/Kimi-K3", "--allow-unverified"}); err != nil {
						t.Fatal(err)
					}
					want := previous + 1
					if scenario == "fresh" {
						want = previous
					}
					if requests.Load() != want {
						t.Fatalf("native catalog refresh contract changed: got %d requests, want %d", requests.Load(), want)
					}
				})
			}
		})
	}
}

func openDesktopEngine(t *testing.T, child capturedDesktop, overrides ...string) *desktopEngine {
	t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), 120*time.Second)
	t.Cleanup(cancel)
	args := []string{"app-server", "-c", "features.shell_snapshot=false"}
	for _, override := range overrides {
		args = append(args, "-c", override)
	}
	command := exec.CommandContext(ctx, child.Env["CODEX_CLI_PATH"], args...)
	stderrPath := filepath.Join(t.TempDir(), "engine.stderr")
	stderr, err := os.Create(stderrPath)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { stderr.Close() })
	command.Stderr = stderr
	command.Dir = child.Cwd
	for key, value := range child.Env {
		command.Env = append(command.Env, key+"="+value)
	}
	input, err := command.StdinPipe()
	if err != nil {
		t.Fatal(err)
	}
	output, err := command.StdoutPipe()
	if err != nil {
		t.Fatal(err)
	}
	if err := command.Start(); err != nil {
		t.Fatal(err)
	}
	e := &desktopEngine{t: t, stderrPath: stderrPath, command: command, input: input, encoder: json.NewEncoder(input), decoder: json.NewDecoder(output)}
	t.Cleanup(e.close)
	e.call("initialize", map[string]any{"clientInfo": map[string]string{"name": "tofa_catalog_fixture", "version": "1"}, "capabilities": map[string]bool{"experimentalApi": true}})
	if err := e.encoder.Encode(map[string]any{"method": "initialized"}); err != nil {
		t.Fatal(err)
	}
	return e
}

func (e *desktopEngine) close() {
	if e.command == nil {
		return
	}
	e.input.Close()
	e.command.Process.Kill()
	e.command.Wait()
	e.command = nil
}

func (e *desktopEngine) read() map[string]any {
	e.t.Helper()
	var message map[string]any
	if err := e.decoder.Decode(&message); err != nil {
		e.t.Fatal(err)
	}
	return message
}

func (e *desktopEngine) call(method string, params any) map[string]any {
	e.t.Helper()
	e.id++
	if err := e.encoder.Encode(map[string]any{"id": e.id, "method": method, "params": params}); err != nil {
		e.t.Fatal(err)
	}
	for {
		message := e.read()
		if message["id"] != float64(e.id) {
			continue
		}
		if message["error"] != nil {
			e.t.Fatalf("%s: %v", method, message["error"])
		}
		result, _ := message["result"].(map[string]any)
		return result
	}
}

func (e *desktopEngine) turn(id, status string) {
	e.turnText(id, status, "Synthetic coexistence check")
}

func (e *desktopEngine) turnText(id, status, text string) map[string]any {
	e.t.Helper()
	e.call("turn/start", map[string]any{"threadId": id, "input": []any{map[string]string{"type": "text", "text": text}}})
	for {
		message := e.read()
		if message["method"] != "turn/completed" {
			continue
		}
		params := message["params"].(map[string]any)
		turn := params["turn"].(map[string]any)
		if params["threadId"] != id || turn["status"] != status {
			e.t.Fatalf("unexpected turn result: %v", params)
		}
		if status == "failed" && !strings.Contains(fmt.Sprint(turn["error"]), "model") {
			e.t.Fatalf("missing explicit model failure: %v", turn["error"])
		}
		return turn
	}
}

func TestDesktopBundledEnginePreservesNativeConversations(t *testing.T) {
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
	var nativeRequests, tofaRequests atomic.Int32
	respond := func(w http.ResponseWriter) {
		w.Header().Set("Content-Type", "text/event-stream")
		fmt.Fprint(w, "event: response.created\ndata: {\"type\":\"response.created\",\"response\":{\"id\":\"resp_fixture\",\"status\":\"in_progress\",\"output\":[]}}\n\nevent: response.completed\ndata: {\"type\":\"response.completed\",\"response\":{\"id\":\"resp_fixture\",\"status\":\"completed\",\"output\":[],\"usage\":{\"input_tokens\":1,\"output_tokens\":0,\"total_tokens\":1}}}\n\n")
	}
	native := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			w.WriteHeader(http.StatusUpgradeRequired)
			return
		}
		var request struct{ Model string }
		if json.NewDecoder(r.Body).Decode(&request) != nil || request.Model != "gpt-6-astra" || r.Header.Get("Authorization") != "Bearer synthetic-native" {
			t.Error("native request changed model or credential")
		}
		nativeRequests.Add(1)
		respond(w)
	}))
	defer native.Close()
	app, output := adapterFixture(t, func(w http.ResponseWriter, r *http.Request) {
		var request struct{ Model string }
		if json.NewDecoder(r.Body).Decode(&request) != nil || request.Model != "moonshotai/Kimi-K3" {
			t.Error("unsupported model reached Token Factory")
		}
		tofaRequests.Add(1)
		respond(w)
	}, nil)
	child, stop := liveDesktopFixture(t, app, bundle, capture)
	if err := os.WriteFile(filepath.Join(child.Env["CODEX_HOME"], "auth.json"), []byte(`{"OPENAI_API_KEY":"synthetic-native"}`), 0600); err != nil {
		t.Fatal(err)
	}
	overrides := []string{`openai_base_url="` + native.URL + `"`}
	e := openDesktopEngine(t, child, overrides...)
	models := e.call("model/list", map[string]any{"includeHidden": true})["data"].([]any)
	identities := map[string]bool{}
	for _, model := range models {
		identities[model.(map[string]any)["model"].(string)] = true
	}
	for _, required := range []string{"gpt-6-astra", "moonshotai/Kimi-K3", "codex-auto-review"} {
		if !identities[required] {
			t.Fatalf("merged picker lost %s", required)
		}
	}
	started := e.call("thread/start", map[string]any{"model": "gpt-6-astra", "modelProvider": "openai", "cwd": child.Cwd, "approvalPolicy": "never", "sandbox": "read-only"})
	id := started["thread"].(map[string]any)["id"].(string)
	e.turn(id, "completed")
	e.close()
	e = openDesktopEngine(t, child, overrides...)
	resumed := e.call("thread/resume", map[string]any{"threadId": id, "model": nil, "modelProvider": nil})
	if resumed["model"] != "gpt-6-astra" || resumed["modelProvider"] != "openai" {
		t.Fatalf("native resume changed identity: %v", resumed)
	}
	e.turn(id, "completed")
	if nativeRequests.Load() != 2 || tofaRequests.Load() != 0 {
		t.Fatal("native conversation was rerouted")
	}
	started = e.call("thread/start", map[string]any{"cwd": child.Cwd, "approvalPolicy": "never", "sandbox": "read-only"})
	id = started["thread"].(map[string]any)["id"].(string)
	if started["model"] != "moonshotai/Kimi-K3" || started["modelProvider"] != "nebius-tofa" {
		t.Fatal("new conversation did not identify Token Factory")
	}
	e.turn(id, "completed")
	e.call("thread/settings/update", map[string]any{"threadId": id, "model": "gpt-6-astra"})
	e.turn(id, "failed")
	if nativeRequests.Load() != 2 || tofaRequests.Load() != 1 {
		t.Fatal("Astra selection silently migrated providers or substituted Kimi")
	}
	e.call("thread/settings/update", map[string]any{"threadId": id, "model": "moonshotai/Kimi-K3"})
	e.turn(id, "completed")
	if nativeRequests.Load() != 2 || tofaRequests.Load() != 2 {
		t.Fatal("returning to Kimi did not recover the same thread")
	}
	// The merged catalog exposes this native auxiliary descriptor. It must still
	// fail explicitly on the Token Factory route rather than being remapped.
	response := adapterRequest(t, child.Env["TOFA_DESKTOP_CONTEXT"], child.Env["TOFA_API_KEY"], `{"model":"codex-auto-review","input":[],"stream":true}`)
	body, _ := io.ReadAll(response.Body)
	response.Body.Close()
	if response.StatusCode != 400 || !strings.Contains(string(body), "model") || tofaRequests.Load() != 2 {
		t.Fatalf("native auxiliary request not rejected: %s", body)
	}
	e.close()
	stop()
	if !strings.Contains(output.String(), "Desktop request failed: unsupported model") {
		t.Fatal("unsupported auxiliary request was not reported")
	}
}

func TestDesktopRefusesInvalidNativeCatalog(t *testing.T) {
	for _, tc := range []struct{ name, mode, catalog, want string }{
		{"export failed", "catalog-error", "", "discovery failed"},
		{"refresh warning", "catalog-warning", "", "discovery failed"},
		{"malformed", "normal", `{"models":`, "invalid or empty"},
		{"empty", "normal", `{"models":[]}`, "invalid or empty"},
		{"missing identity", "normal", `{"models":[{"display_name":"Astra"}]}`, "model identity"},
		{"duplicate identity", "normal", `{"models":[{"slug":"gpt-6-astra"},{"slug":"gpt-6-astra"}]}`, "model identity"},
		{"conflicting provider metadata", "normal", `{"models":[{"slug":"moonshotai/Kimi-K3"}]}`, "model identity"},
		{"conflicting Guardian metadata", "normal", `{"models":[{"slug":"zai-org/GLM-5.3-Flash"}]}`, "model identity"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			bundle, capture := desktopFixture(t, tc.mode)
			if tc.catalog != "" {
				if err := os.WriteFile(filepath.Join(bundle, "Contents/Resources/native-catalog.json"), []byte(tc.catalog), 0600); err != nil {
					t.Fatal(err)
				}
			}
			app, output := adapterFixture(t, nil, nil)
			err := app.Run([]string{"launch", "codex-desktop", "--app-bundle", bundle, "--model", "moonshotai/Kimi-K3", "--allow-unverified"})
			if err == nil || !strings.Contains(err.Error(), tc.want) {
				t.Fatalf("wanted explicit catalog refusal, got %v", err)
			}
			if strings.Contains(err.Error()+output.String(), "synthetic-account-private") {
				t.Fatal("native diagnostics leaked")
			}
			if _, err := os.Stat(capture); !os.IsNotExist(err) {
				t.Fatal("desktop started despite invalid native catalog")
			}
		})
	}
}
