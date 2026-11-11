package tofa_test

import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"syscall"
	"testing"

	"github.com/kreuzhofer/tofa-launcher/internal/tofa"
)

func TestDesktopCompatibilityWithoutQualificationKit(t *testing.T) {
	bundle, capture := nativeCandidateFixture(t)
	home := filepath.Join(os.Getenv("HOME"), ".codex")
	if err := os.MkdirAll(home, 0700); err != nil {
		t.Fatal(err)
	}
	config := []byte("# preserve ordinary CLI defaults\nmodel = \"user-model\"\n")
	if err := os.WriteFile(filepath.Join(home, "config.toml"), config, 0600); err != nil {
		t.Fatal(err)
	}
	var out bytes.Buffer
	app := &tofa.App{Dir: t.TempDir(), Out: &out}
	if err := app.Run([]string{"desktop-compatibility", "--app-bundle", bundle}); err != nil {
		t.Fatal(err)
	}
	var result struct {
		Schema           string            `json:"schema"`
		Status           string            `json:"status"`
		ReleaseQualified bool              `json:"release_qualified"`
		Checks           map[string]string `json:"checks"`
		Identity         map[string]string `json:"identity"`
	}
	if err := json.Unmarshal(out.Bytes(), &result); err != nil {
		t.Fatal(err)
	}
	if result.Schema != "tofa-desktop-compatibility-v1" || result.Status != "compatible" || result.ReleaseQualified {
		t.Fatalf("untruthful result: %s", out.String())
	}
	for _, name := range []string{"platform-layout", "ownership", "account-policy", "provider-configuration", "secret-exclusion"} {
		if result.Checks[name] != "passed" {
			t.Fatalf("missing check %s", name)
		}
	}
	if result.Identity["engine_sha256"] == "" {
		t.Fatal("missing observed engine identity")
	}
	if _, err := os.Stat(capture); !os.IsNotExist(err) {
		t.Fatal("compatibility probe launched Desktop")
	}
	raw, err := os.ReadFile(filepath.Join(home, "config.toml"))
	if err != nil || !bytes.Equal(raw, config) {
		t.Fatal("probe changed configuration")
	}
	if _, err := os.Stat(filepath.Join(app.Dir, "desktop-bridge-v2")); !os.IsNotExist(err) {
		t.Fatal("probe installed bridge")
	}
}

func TestDesktopCompatibilityRejectsMissingPolicyContract(t *testing.T) {
	bundle, _ := nativeCandidateFixture(t)
	home := filepath.Join(os.Getenv("HOME"), ".codex")
	if err := os.MkdirAll(home, 0700); err != nil {
		t.Fatal(err)
	}
	engine := filepath.Join(bundle, "Contents/Resources/codex")
	raw, err := os.ReadFile(engine)
	if err != nil {
		t.Fatal(err)
	}
	raw = bytes.Replace(raw, []byte("result = {'requirements': {'modelProvider': 'openai'} if MODE == 'managed' else None}"), []byte("result = {'unsupported': 'private-policy-payload'}"), 1)
	if err = os.WriteFile(engine, raw, 0700); err != nil {
		t.Fatal(err)
	}
	var out bytes.Buffer
	app := &tofa.App{Dir: t.TempDir(), Out: &out}
	err = app.Run([]string{"desktop-compatibility", "--app-bundle", bundle})
	if err == nil {
		t.Fatal("missing policy contract was accepted")
	}
	if strings.Contains(err.Error(), "private-policy-payload") {
		t.Fatal("private policy leaked")
	}
}

func TestDesktopCompatibilityPrerequisitesAndCompatibleUpdates(t *testing.T) {
	for _, scenario := range []string{"signed-out", "managed", "provider-conflict", "native-conflict", "owned", "missing-config", "ignored-routing", "updated-client"} {
		t.Run(scenario, func(t *testing.T) {
			bundle, capture := nativeCandidateFixture(t)
			home := filepath.Join(os.Getenv("HOME"), ".codex")
			if err := os.MkdirAll(home, 0700); err != nil {
				t.Fatal(err)
			}
			config := "model = \"personal-cli-default\"\n"
			if scenario == "provider-conflict" {
				config += "[model_providers.nebius-tofa]\nname=\"personal-integration\"\n"
			}
			if scenario == "native-conflict" {
				config += "[model_providers.tofa-native-router]\nname=\"personal-integration\"\n"
			}
			if err := os.WriteFile(filepath.Join(home, "config.toml"), []byte(config), 0600); err != nil {
				t.Fatal(err)
			}
			engine := filepath.Join(bundle, "Contents/Resources/codex")
			raw, err := os.ReadFile(engine)
			if err != nil {
				t.Fatal(err)
			}
			switch scenario {
			case "signed-out":
				raw = bytes.Replace(raw, []byte("'type':'chatgpt'"), []byte("'type':'apiKey'"), 1)
			case "managed":
				raw = bytes.Replace(raw, []byte("MODE = \"ignore\""), []byte("MODE = \"managed\""), 1)
			case "missing-config":
				raw = bytes.Replace(raw, []byte("'config':config_response()"), []byte("'unsupported':config_response()"), 1)
			case "ignored-routing":
				raw = bytes.Replace(raw, []byte("apply_overrides(values, overrides(sys.argv))"), []byte("pass # unsupported overrides"), 1)
			case "owned":
				profile := filepath.Join(os.Getenv("HOME"), "Library/Application Support/Codex")
				if err := os.MkdirAll(profile, 0700); err != nil {
					t.Fatal(err)
				}
				if err := os.WriteFile(filepath.Join(profile, "SingletonLock"), []byte("unknown-owner"), 0600); err != nil {
					t.Fatal(err)
				}
			case "updated-client":
				raw = bytes.Replace(raw, []byte("codex-cli 0.155.0-alpha.16.4"), []byte("codex-cli 0.190.0"), 1)
				plist := filepath.Join(bundle, "Contents/Info.plist")
				data, err := os.ReadFile(plist)
				if err != nil {
					t.Fatal(err)
				}
				if err = os.WriteFile(plist, bytes.Replace(data, []byte("26.917.71314"), []byte("27.1001.12345"), 1), 0600); err != nil {
					t.Fatal(err)
				}
				for _, dir := range []string{"plugins/cache/arbitrary-new-version", "skills/personal"} {
					if err := os.MkdirAll(filepath.Join(home, dir), 0700); err != nil {
						t.Fatal(err)
					}
				}
				if err := os.WriteFile(filepath.Join(home, "models_cache.json"), []byte(`{"unrelated":"catalog churn"}`), 0600); err != nil {
					t.Fatal(err)
				}
			}
			if err = os.WriteFile(engine, raw, 0700); err != nil {
				t.Fatal(err)
			}
			var out bytes.Buffer
			app := &tofa.App{Dir: t.TempDir(), Out: &out}
			err = app.Run([]string{"desktop-compatibility", "--app-bundle", bundle})
			if (err == nil) != (scenario == "updated-client") {
				t.Fatalf("%s: %v; %s", scenario, err, out.String())
			}
			if err != nil && out.Len() != 0 {
				t.Fatal("refusal emitted compatibility success")
			}
			if _, err = os.Stat(capture); !os.IsNotExist(err) {
				t.Fatal("probe launched Desktop")
			}
			got, err := os.ReadFile(filepath.Join(home, "config.toml"))
			if err != nil || string(got) != config {
				t.Fatal("probe changed settings")
			}
		})
	}
}

func TestDesktopCompatibilityRejectsUnsafeProfileAndPolicy(t *testing.T) {
	for _, scenario := range []string{"profile-symlink", "held-lease", "malformed-policy"} {
		t.Run(scenario, func(t *testing.T) {
			bundle, _ := nativeCandidateFixture(t)
			home := filepath.Join(os.Getenv("HOME"), ".codex")
			if err := os.MkdirAll(home, 0700); err != nil {
				t.Fatal(err)
			}
			profile := filepath.Join(os.Getenv("HOME"), "Library/Application Support/Codex")
			if err := os.MkdirAll(filepath.Dir(profile), 0700); err != nil {
				t.Fatal(err)
			}
			if scenario == "profile-symlink" {
				if err := os.Symlink(t.TempDir(), profile); err != nil {
					t.Fatal(err)
				}
			}
			if scenario == "held-lease" {
				if err := os.MkdirAll(profile, 0700); err != nil {
					t.Fatal(err)
				}
				f, err := os.OpenFile(filepath.Join(profile, ".tofa-launch.lock"), os.O_CREATE|os.O_RDWR, 0600)
				if err != nil {
					t.Fatal(err)
				}
				defer f.Close()
				if err := syscall.Flock(int(f.Fd()), syscall.LOCK_EX|syscall.LOCK_NB); err != nil {
					t.Fatal(err)
				}
			}
			if scenario == "malformed-policy" {
				if err := os.WriteFile(filepath.Join(home, "config.toml"), []byte("shell_environment_policy = \"unsupported\"\n"), 0600); err != nil {
					t.Fatal(err)
				}
			}
			var out bytes.Buffer
			app := &tofa.App{Dir: t.TempDir(), Out: &out}
			if err := app.Run([]string{"desktop-compatibility", "--app-bundle", bundle}); err == nil {
				t.Fatal("unsafe prerequisite accepted")
			}
		})
	}
}
