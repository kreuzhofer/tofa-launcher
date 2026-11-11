package tofa_test

import (
	"bytes"
	"encoding/json"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// Ordinary users have neither a qualification kit nor a maintainer's receipt.
// Exercise the public launch path against an owned, signed-in Desktop fixture.
func TestDesktopNormalLaunchWithoutQualificationKit(t *testing.T) {
	bundle, capture := nativeCandidateFixture(t)
	home := filepath.Join(os.Getenv("HOME"), ".codex")
	plugin := filepath.Join(home, "plugins/cache/openai-bundled/code-review/current/plugin.txt")
	if err := os.MkdirAll(filepath.Dir(plugin), 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(plugin, []byte("preserve installed review"), 0600); err != nil {
		t.Fatal(err)
	}
	app, _ := adapterFixture(t, nil, nil)
	var output bytes.Buffer
	app.Out = &output
	child, stop := liveDesktopFixture(t, app, bundle, capture)
	request, _ := http.NewRequest("GET", child.Env["TOFA_DESKTOP_CONTEXT"]+"/desktop-launch", nil)
	request.Header.Set("Authorization", "Bearer "+child.Env["TOFA_API_KEY"])
	response, err := http.DefaultClient.Do(request)
	if err != nil {
		t.Fatal(err)
	}
	var route struct{ Overrides []string }
	err = json.NewDecoder(response.Body).Decode(&route)
	response.Body.Close()
	if err != nil {
		t.Fatal(err)
	}
	stop()
	if !strings.Contains(strings.Join(route.Overrides, "\n"), `model_provider="tofa-native-router"`) {
		t.Fatal("ordinary launch did not retain native account routing")
	}
	for _, text := range []string{"Native-account route", "quit Desktop", "launch through TOFA", "same conversation"} {
		if !strings.Contains(output.String(), text) {
			t.Fatalf("missing launch disclosure %q", text)
		}
	}
	raw, err := os.ReadFile(plugin)
	if err != nil || string(raw) != "preserve installed review" {
		t.Fatal("normal launch changed installed review")
	}
}

func TestDesktopNormalLaunchRequiresNativeSignIn(t *testing.T) {
	bundle, capture := desktopFixture(t, "signed-out") // Explicitly signed out.
	app, _ := adapterFixture(t, nil, nil)
	err := app.Run([]string{"launch", "codex-desktop", "--app-bundle", bundle, "--model", "moonshotai/Kimi-K3"})
	if err == nil || !strings.Contains(err.Error(), "sign") {
		t.Fatalf("missing sign-in refusal: %v", err)
	}
	if _, err := os.Stat(capture); !os.IsNotExist(err) {
		t.Fatal("signed-out launch started Desktop")
	}
}

func TestDesktopNormalAdmissionRechecksCurrentContracts(t *testing.T) {
	for _, scenario := range []string{"managed", "missing-policy", "ignored-routing", "provider-conflict", "protected-drift", "engine-drift", "compatible-update"} {
		t.Run(scenario, func(t *testing.T) {
			bundle, capture := nativeCandidateFixture(t)
			home := filepath.Join(os.Getenv("HOME"), ".codex")
			if err := os.MkdirAll(home, 0700); err != nil {
				t.Fatal(err)
			}
			config := []byte("model = \"personal-cli-default\"\n")
			if scenario == "provider-conflict" {
				config = append(config, []byte("[model_providers.tofa-native-router]\nname=\"personal-integration\"\n")...)
			}
			if err := os.WriteFile(filepath.Join(home, "config.toml"), config, 0600); err != nil {
				t.Fatal(err)
			}
			engine := filepath.Join(bundle, "Contents/Resources/codex")
			raw, err := os.ReadFile(engine)
			if err != nil {
				t.Fatal(err)
			}
			want := ""
			switch scenario {
			case "managed":
				raw = bytes.Replace(raw, []byte(`MODE = "ignore"`), []byte(`MODE = "managed"`), 1)
				want = "managed"
			case "missing-policy":
				raw = bytes.Replace(raw, []byte("result = {'requirements': {'modelProvider': 'openai'} if MODE == 'managed' else None}"), []byte("result = {'unsupported': 'private-policy'}"), 1)
				want = "managed-policy contract"
			case "ignored-routing":
				raw = bytes.Replace(raw, []byte("apply_overrides(values, overrides(sys.argv))"), []byte("pass # unsupported routing overrides"), 1)
				want = "routing"
			case "provider-conflict":
				want = "conflicts"
			case "protected-drift", "engine-drift":
				appPath := filepath.Join(bundle, "Contents/MacOS/ChatGPT")
				appRaw, err := os.ReadFile(appPath)
				if err != nil {
					t.Fatal(err)
				}
				mutation := "config_path.write_text('model = \\\"unexpected\\\"\\n')"
				if scenario == "engine-drift" {
					mutation = "with (pathlib.Path(__file__).parent.parent/'Resources/codex').open('a') as changed: changed.write('\\n# changed during startup\\n')"
				}
				appRaw = bytes.Replace(appRaw, []byte("profile=pathlib.Path(os.environ['CODEX_ELECTRON_USER_DATA_PATH'])"), []byte(mutation+"\nprofile=pathlib.Path(os.environ['CODEX_ELECTRON_USER_DATA_PATH'])"), 1)
				if err := os.WriteFile(appPath, appRaw, 0700); err != nil {
					t.Fatal(err)
				}
				want = "drifted"
			case "compatible-update":
				raw = bytes.Replace(raw, []byte("codex-cli 0.155.0-alpha.16.4"), []byte("codex-cli 0.190.0"), 1)
				if err := os.WriteFile(filepath.Join(home, "models_cache.json"), []byte(`{"catalog":"changed"}`), 0600); err != nil {
					t.Fatal(err)
				}
				if err := os.MkdirAll(filepath.Join(home, "plugins/cache/new-version"), 0700); err != nil {
					t.Fatal(err)
				}
			}
			if err := os.WriteFile(engine, raw, 0700); err != nil {
				t.Fatal(err)
			}
			app, _ := adapterFixture(t, nil, nil)
			if scenario == "compatible-update" {
				_, stop := liveDesktopFixture(t, app, bundle, capture)
				stop()
				return
			}
			err = app.Run([]string{"launch", "codex-desktop", "--app-bundle", bundle, "--model", "moonshotai/Kimi-K3"})
			if err == nil || !strings.Contains(err.Error(), want) {
				t.Fatalf("wanted %s refusal, got %v", want, err)
			}
			if _, err := os.Stat(capture); !os.IsNotExist(err) {
				t.Fatal("refused launch published a usable route")
			}
			if scenario != "protected-drift" {
				got, err := os.ReadFile(filepath.Join(home, "config.toml"))
				if err != nil || !bytes.Equal(got, config) {
					t.Fatal("refused launch changed configuration")
				}
			}
		})
	}
}
