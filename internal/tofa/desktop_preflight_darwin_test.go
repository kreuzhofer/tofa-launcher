package tofa_test

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"os/exec"
	"path/filepath"
	"reflect"
	"strconv"
	"strings"
	"testing"
	"time"
)

// An account prerequisite refusal must not refresh another engine's system
// skills. This uses the public launch entry point and actual app-server startup;
// the Desktop executable is a fixture and must never be reached.
func TestDesktopNativePreflightPreservesOtherEngineSkills(t *testing.T) {
	for _, scenario := range []string{"signed-out", "account-verified", "provider-conflict", "routing-check", "compatibility"} {
		t.Run(scenario, func(t *testing.T) { testDesktopPreflightPreservation(t, scenario) })
	}
}

func testDesktopPreflightPreservation(t *testing.T, scenario string) {
	t.Helper()
	installed, other := os.Getenv("TOFA_TEST_DESKTOP_ENGINE"), os.Getenv("TOFA_TEST_OTHER_ENGINE")
	if installed == "" || other == "" {
		t.Skip("set TOFA_TEST_DESKTOP_ENGINE and TOFA_TEST_OTHER_ENGINE")
	}
	bundle, capture := desktopFixture(t, "ignore")
	home := filepath.Join(os.Getenv("HOME"), ".codex")
	if err := os.MkdirAll(home, 0700); err != nil {
		t.Fatal(err)
	}
	// File-only fake state prevents access to the operator's keychain/account.
	config := []byte("cli_auth_credentials_store=\"file\"\n")
	if err := os.WriteFile(filepath.Join(home, "config.toml"), config, 0600); err != nil {
		t.Fatal(err)
	}
	personal := filepath.Join(home, "skills", "personal-fixture", "SKILL.md")
	if err := os.MkdirAll(filepath.Dir(personal), 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(personal, []byte("# Personal fixture\nPreserve this skill.\n"), 0600); err != nil {
		t.Fatal(err)
	}
	child := capturedDesktop{Cwd: home, Env: map[string]string{
		"PATH": os.Getenv("PATH"), "HOME": os.Getenv("HOME"), "CODEX_HOME": home, "CODEX_CLI_PATH": other,
	}}
	seed := openDesktopEngine(t, child)
	seed.close()
	want := "ChatGPT sign-in"
	var auth []byte
	if scenario == "account-verified" || scenario == "routing-check" || scenario == "compatibility" {
		// The native account parser receives synthetic tokens only. Any attempted
		// account discovery is confined to this owned server, never a live account.
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.Header().Set("Content-Type", "application/json")
			if strings.HasSuffix(r.URL.Path, "/accounts/check") {
				w.Write([]byte(`{"accounts":[{"id":"synthetic-account","workspace_backend_origin":"https://127.0.0.1:1","account_routing_override":"NO_CONSTRAINT"}]}`))
				return
			}
			w.Write([]byte(`{}`))
		}))
		defer server.Close()
		encode := func(s string) string { return base64.RawURLEncoding.EncodeToString([]byte(s)) }
		token := encode(`{"alg":"none","typ":"JWT"}`) + "." + encode(`{"https://api.openai.com/auth":{"chatgpt_plan_type":"plus","chatgpt_account_id":"synthetic-account","chatgpt_user_id":"synthetic-user"}}`) + "." + encode("signature")
		auth, _ = json.Marshal(map[string]any{"auth_mode": "chatgpt", "tokens": map[string]string{"id_token": token, "access_token": "synthetic-access", "refresh_token": "synthetic-refresh", "account_id": "synthetic-account"}, "last_refresh": time.Now().UTC().Format(time.RFC3339)})
		if err := os.WriteFile(filepath.Join(home, "auth.json"), auth, 0600); err != nil {
			t.Fatal(err)
		}
		config = append(config, []byte("chatgpt_base_url="+strconv.Quote(server.URL)+"\n")...)
		// Stop at the next existing guard after the real account/config checks.
		if scenario == "account-verified" {
			plugin := filepath.Join(home, "plugins/cache/openai-bundled/code-review/fixture")
			if err := os.MkdirAll(plugin, 0700); err != nil {
				t.Fatal(err)
			}
		}
		want = "startup blocked"
	}
	if scenario == "provider-conflict" {
		config = append(config, []byte("[model_providers.tofa-native-router]\nname=\"user-owned\"\nbase_url=\"http://127.0.0.1:0\"\nwire_api=\"responses\"\n")...)
		want = "conflicts"
	}
	if err := os.WriteFile(filepath.Join(home, "config.toml"), config, 0600); err != nil {
		t.Fatal(err)
	}
	for _, engine := range []string{other, installed} {
		command := exec.Command(engine, "--version")
		command.Env = []string{"HOME=" + os.Getenv("HOME"), "CODEX_HOME=" + home, "PATH=" + os.Getenv("PATH")}
		version, err := command.Output()
		if err != nil {
			t.Fatal(err)
		}
		t.Logf("engine %s: %s", engine, strings.TrimSpace(string(version)))
	}
	before := preflightSkillFiles(t, filepath.Join(home, "skills"))
	if _, ok := before[".system/.codex-system-skills.marker"]; !ok {
		t.Fatal("other engine did not seed the system cache")
	}
	// A normal invocation of the target still installs its own skills. Confirm
	// this fixture really has competing cache versions rather than a vacuous pass.
	controlHome := t.TempDir()
	if err := os.WriteFile(filepath.Join(controlHome, "config.toml"), []byte("cli_auth_credentials_store=\"file\"\n"), 0600); err != nil {
		t.Fatal(err)
	}
	control := openDesktopEngine(t, capturedDesktop{Cwd: controlHome, Env: map[string]string{
		"PATH": os.Getenv("PATH"), "HOME": os.Getenv("HOME"), "CODEX_HOME": controlHome, "CODEX_CLI_PATH": installed,
	}})
	control.close()
	controlSkills := preflightSkillFiles(t, filepath.Join(controlHome, "skills"))
	if controlSkills[".system/.codex-system-skills.marker"] == "" {
		t.Fatal("ordinary target engine did not install its system skills")
	}
	if controlSkills[".system/.codex-system-skills.marker"] == before[".system/.codex-system-skills.marker"] && scenario != "compatibility" {
		t.Skip("selected engines have identical system skills; choose a distinct fixture engine")
	}
	engine := filepath.Join(bundle, "Contents/Resources/codex")
	if scenario == "routing-check" {
		// Keep the existing owned fake Desktop/worker, but send every config
		// helper to the actual engine, including the later routing check.
		script, err := os.ReadFile(engine)
		if err != nil {
			t.Fatal(err)
		}
		delegate := fmt.Sprintf("if 'app-server' in sys.argv:\n    os.execv(%q, [%q, *sys.argv[1:]])\n", installed, installed)
		script = []byte(strings.Replace(string(script), "if 'app-server' in sys.argv:\n", delegate+"if 'app-server' in sys.argv:\n", 1))
		if err := os.WriteFile(engine, script, 0700); err != nil {
			t.Fatal(err)
		}
		catalogCommand := exec.Command(installed, "debug", "models", "--bundled")
		catalogCommand.Env = []string{"PATH=" + os.Getenv("PATH"), "HOME=" + os.Getenv("HOME"), "CODEX_HOME=" + controlHome}
		catalog, err := catalogCommand.Output()
		if err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(filepath.Join(bundle, "Contents/Resources/native-catalog.json"), catalog, 0600); err != nil {
			t.Fatal(err)
		}
		app, _ := adapterFixture(t, nil, nil)
		_, stop := liveDesktopFixture(t, app, bundle, capture, "--native-account-candidate", "--evaluation-observer", candidateProxyObserver(t))
		stop()
		after := preflightSkillFiles(t, filepath.Join(home, "skills"))
		if !reflect.DeepEqual(before, after) {
			t.Fatal("later routing/configuration helper changed skills")
		}
		return
	}
	if err := os.Remove(engine); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(installed, engine); err != nil {
		t.Fatal(err)
	}
	app, _ := adapterFixture(t, nil, nil)
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	var output bytes.Buffer
	app.Out = &output
	if scenario == "compatibility" {
		err := app.RunContext(ctx, []string{"desktop-compatibility", "--app-bundle", bundle})
		if err != nil {
			t.Fatal(err)
		}
		if !strings.Contains(output.String(), `"status":"compatible"`) {
			t.Fatal("missing compatibility result")
		}
		if strings.Contains(output.String(), "synthetic-access") || strings.Contains(output.String(), "synthetic-account") {
			t.Fatal("private account data in report")
		}
	} else {
		err := app.RunContext(ctx, []string{"launch", "codex-desktop", "--app-bundle", bundle, "--model", "moonshotai/Kimi-K3", "--native-account-candidate", "--evaluation-observer", nativeCandidateObserver(t)})
		if err == nil || !strings.Contains(err.Error(), want) {
			t.Fatalf("expected %q refusal, got %v", want, err)
		}
	}
	if _, err := os.Stat(capture); !os.IsNotExist(err) {
		t.Fatal("account preflight launched Desktop")
	}
	if raw, err := os.ReadFile(filepath.Join(home, "config.toml")); err != nil || string(raw) != string(config) {
		t.Fatal("account preflight changed configuration")
	}
	if raw, err := os.ReadFile(filepath.Join(home, "auth.json")); len(auth) == 0 {
		if !os.IsNotExist(err) {
			t.Fatal("account preflight created credentials")
		}
	} else if err != nil || string(raw) != string(auth) {
		t.Fatal("account preflight changed fixture credentials")
	}
	after := preflightSkillFiles(t, filepath.Join(home, "skills"))
	if !reflect.DeepEqual(before, after) {
		for path, value := range before {
			if after[path] != value {
				t.Errorf("account preflight changed skill: %s", path)
			}
		}
		for path := range after {
			if _, ok := before[path]; !ok {
				t.Errorf("account preflight added skill: %s", path)
			}
		}
	}
}

func preflightSkillFiles(t *testing.T, root string) map[string]string {
	t.Helper()
	files := map[string]string{}
	if err := filepath.Walk(root, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}
		if info.Mode().IsRegular() {
			raw, err := os.ReadFile(path)
			if err != nil {
				return err
			}
			rel, err := filepath.Rel(root, path)
			if err != nil {
				return err
			}
			files[rel] = string(raw)
		}
		return nil
	}); err != nil {
		t.Fatal(err)
	}
	return files
}
