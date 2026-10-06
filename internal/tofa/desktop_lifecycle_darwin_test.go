package tofa_test

import (
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"testing"

	"github.com/kreuzhofer/tofa-launcher/internal/tofa"
)

func TestDesktopLifecycleRefusesActiveOwner(t *testing.T) {
	bundle, capture := desktopFixture(t, "ignore")
	app, _ := adapterFixture(t, nil, nil)
	child, stop := liveDesktopFixture(t, app, bundle, capture)
	defer stop()
	before, err := os.ReadFile(child.Env["CODEX_CLI_PATH"])
	if err != nil {
		t.Fatal(err)
	}
	root := filepath.Join(t.TempDir(), "install")
	for _, args := range [][]string{
		{"desktop-lifecycle", "install", root},
		{"desktop-lifecycle", "uninstall"},
		{"desktop-lifecycle", "uninstall", "--purge"},
	} {
		err := app.Run(args)
		if err == nil || !strings.Contains(err.Error(), "desktop") || (!strings.Contains(err.Error(), "owned") && !strings.Contains(err.Error(), "owns")) {
			t.Fatalf("lifecycle must refuse the live owner explicitly: %v", err)
		}
	}
	after, err := os.ReadFile(child.Env["CODEX_CLI_PATH"])
	if err != nil || string(after) != string(before) {
		t.Fatal("active bridge changed")
	}
}

func TestDesktopLifecycleRefusesOtherRuntimeOwner(t *testing.T) {
	bundle, capture := desktopFixture(t, "ignore")
	app, _ := adapterFixture(t, nil, nil)
	child, stop := liveDesktopFixture(t, app, bundle, capture)
	stop()
	root := filepath.Join(app.Dir, "desktop-launches", "launch-other")
	if err := os.MkdirAll(root, 0700); err != nil {
		t.Fatal(err)
	}
	data, _ := json.Marshal(map[string]any{"Version": 1, "PID": os.Getpid(), "Profile": filepath.Join(t.TempDir(), "other-profile")})
	if err := os.WriteFile(filepath.Join(root, "owner.json"), data, 0600); err != nil {
		t.Fatal(err)
	}
	before, err := os.ReadFile(filepath.Join(filepath.Dir(child.Env["CODEX_CLI_PATH"]), "owner.json"))
	if err != nil {
		t.Fatal(err)
	}
	if err := app.Run([]string{"desktop-lifecycle", "uninstall"}); err == nil || !strings.Contains(err.Error(), "runtime owner") {
		t.Fatalf("another owner's integration was not refused: %v", err)
	}
	after, err := os.ReadFile(filepath.Join(filepath.Dir(child.Env["CODEX_CLI_PATH"]), "owner.json"))
	if err != nil || string(before) != string(after) {
		t.Fatal("another owner's bridge changed")
	}
}

func TestDesktopLifecycleInterruptedReplacementRemainsCallable(t *testing.T) {
	bundle, capture := desktopFixture(t, "ignore")
	app, _ := adapterFixture(t, nil, nil)
	child, stop := liveDesktopFixture(t, app, bundle, capture)
	stop()
	bridge := child.Env["CODEX_CLI_PATH"]
	record := filepath.Join(filepath.Dir(bridge), "owner.json")
	data, err := os.ReadFile(record)
	if err != nil {
		t.Fatal(err)
	}
	var owner map[string]any
	if err := json.Unmarshal(data, &owner); err != nil {
		t.Fatal(err)
	}
	// Public artifact state immediately after rename, before finalizing the
	// ownership record: the executable matches the write-ahead digest.
	owner["PendingSHA256"], owner["SHA256"] = owner["SHA256"], strings.Repeat("0", 64)
	data, _ = json.Marshal(owner)
	if err := os.WriteFile(record, data, 0600); err != nil {
		t.Fatal(err)
	}
	if output, err := exec.Command(bridge, "--version").CombinedOutput(); err != nil {
		t.Fatalf("interrupted update broke saved reference: %v %s", err, output)
	}
	// Now fail a replacement while writing its executable. Only this subprocess
	// has a file-size limit; the original reference must survive and be retryable.
	command := exec.Command("/bin/sh", "-c", `ulimit -f 2; trap '' XFSZ; exec "$@"`, "fixture", bridge, "--tofa-installed-lifecycle", "uninstall")
	if output, err := command.CombinedOutput(); err == nil || !strings.Contains(string(output), "file too large") {
		t.Fatalf("replacement failure not exercised: %v %s", err, output)
	}
	if output, err := exec.Command(bridge, "--version").CombinedOutput(); err != nil {
		t.Fatalf("failed update broke saved reference: %v %s", err, output)
	}
	if err := app.Run([]string{"desktop-lifecycle", "uninstall"}); err != nil {
		t.Fatalf("replacement retry failed: %v", err)
	}
}

func TestDesktopLifecycleConflictsPreserveArtifacts(t *testing.T) {
	for _, kind := range []string{"edited executable", "missing record", "future record", "future lifecycle record", "partial installation", "symlink directory"} {
		t.Run(kind, func(t *testing.T) {
			bundle, capture := desktopFixture(t, "ignore")
			app, _ := adapterFixture(t, nil, nil)
			child, stop := liveDesktopFixture(t, app, bundle, capture)
			stop()
			bridge := child.Env["CODEX_CLI_PATH"]
			record := filepath.Join(filepath.Dir(bridge), "owner.json")
			switch kind {
			case "edited executable":
				if err := os.WriteFile(bridge, []byte("user-managed executable"), 0700); err != nil {
					t.Fatal(err)
				}
			case "missing record":
				if err := os.Remove(record); err != nil {
					t.Fatal(err)
				}
			case "future record":
				data, err := os.ReadFile(record)
				if err != nil {
					t.Fatal(err)
				}
				if err := os.WriteFile(record, []byte(strings.Replace(string(data), `"Version":2`, `"Version":99`, 1)), 0600); err != nil {
					t.Fatal(err)
				}
			case "future lifecycle record":
				data, err := os.ReadFile(record)
				if err != nil {
					t.Fatal(err)
				}
				if err := os.WriteFile(record, []byte(strings.Replace(string(data), `"LifecycleVersion":1`, `"LifecycleVersion":99`, 1)), 0600); err != nil {
					t.Fatal(err)
				}
			case "partial installation":
				if err := os.Mkdir(filepath.Join(app.Dir, "desktop-bridge-v2", "interrupted"), 0700); err != nil {
					t.Fatal(err)
				}
			case "symlink directory":
				parent := filepath.Join(app.Dir, "desktop-bridge-v2")
				if err := os.Rename(parent, parent+"-user"); err != nil {
					t.Fatal(err)
				}
				if err := os.Symlink(parent+"-user", parent); err != nil {
					t.Fatal(err)
				}
			}
			before, err := os.ReadFile(bridge)
			if err != nil {
				t.Fatal(err)
			}
			if err := app.Run([]string{"desktop-lifecycle", "uninstall"}); err == nil {
				t.Fatal("conflicting integration accepted")
			}
			after, err := os.ReadFile(bridge)
			if err != nil || string(after) != string(before) {
				t.Fatal("conflicting artifact was changed")
			}
		})
	}
}

func TestDesktopInstalledUpgradeAndStandalonePurge(t *testing.T) {
	cache, err := exec.Command("go", "env", "-json", "GOPATH", "GOCACHE").Output()
	if err != nil {
		t.Fatal(err)
	}
	var buildEnv map[string]string
	if err := json.Unmarshal(cache, &buildEnv); err != nil {
		t.Fatal(err)
	}
	bundle, capture := desktopFixture(t, "ignore")
	t.Setenv("XDG_CONFIG_HOME", filepath.Join(os.Getenv("HOME"), ".config"))
	t.Setenv("TOFA_INSTALL_DIR", filepath.Join(os.Getenv("HOME"), "install"))
	app, _ := adapterFixture(t, nil, nil)
	app.Dir, _ = tofa.ConfigDir()
	store := tofa.Store{Dir: app.Dir, Vault: app.Vault}
	if err := store.Login("fixture-project", "fixture-secret", "file"); err != nil {
		t.Fatal(err)
	}
	child, stop := liveDesktopFixture(t, app, bundle, capture, "--model", "deepseek-ai/DeepSeek-V4.1-Flash")
	stop()
	bridge := child.Env["CODEX_CLI_PATH"]
	preserved := map[string][]byte{}
	for path, content := range map[string]string{
		filepath.Join(child.Env["CODEX_HOME"], "auth.json"):                      `{"OPENAI_API_KEY":"synthetic-ordinary-account"}`,
		filepath.Join(child.Env["CODEX_ELECTRON_USER_DATA_PATH"], "Preferences"): `{"onboardingComplete":true,"userSetting":"preserve"}`,
		filepath.Join(t.TempDir(), "workspace.txt"):                              "ordinary workspace content",
	} {
		if err := os.WriteFile(path, []byte(content), 0600); err != nil {
			t.Fatal(err)
		}
		preserved[path] = []byte(content)
	}
	for _, path := range []string{filepath.Join(child.Env["CODEX_HOME"], "config.toml"), filepath.Join(child.Env["CODEX_ELECTRON_USER_DATA_PATH"], "tool-settings.json")} {
		data, err := os.ReadFile(path)
		if err != nil {
			t.Fatal(err)
		}
		preserved[path] = data
	}
	old, err := os.ReadFile(bridge)
	if err != nil {
		t.Fatal(err)
	}
	legacy := strings.Replace(bridge, "desktop-bridge-v2", "desktop-bridge-v1", 1)
	if err := os.MkdirAll(filepath.Dir(legacy), 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(legacy, old, 0700); err != nil {
		t.Fatal(err)
	}
	data, err := os.ReadFile(filepath.Join(filepath.Dir(bridge), "owner.json"))
	if err != nil {
		t.Fatal(err)
	}
	data = []byte(strings.Replace(string(data), `"Version":2`, `"Version":1`, 1))
	if err := os.WriteFile(filepath.Join(filepath.Dir(legacy), "owner.json"), data, 0600); err != nil {
		t.Fatal(err)
	}
	assets := t.TempDir()
	asset := filepath.Join(assets, "tofa_v0.0.0-test_darwin_"+runtime.GOARCH)
	build := exec.Command("go", "build", "-ldflags", fmt.Sprintf("-X %q", "github.com/kreuzhofer/tofa-launcher/internal/tofa.desktopProcessCommand="+tofa.DesktopProcessFixture), "-o", asset, "../../cmd/tofa")
	build.Env = os.Environ()
	for key, value := range buildEnv {
		build.Env = append(build.Env, key+"="+value)
	}
	if output, err := build.CombinedOutput(); err != nil {
		t.Fatalf("build: %v %s", err, output)
	}
	binary, err := os.ReadFile(asset)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(assets, "SHA256SUMS"), []byte(fmt.Sprintf("%x  %s\n", sha256.Sum256(binary), filepath.Base(asset))), 0600); err != nil {
		t.Fatal(err)
	}
	t.Setenv("TOFA_RELEASE_BASE_URL", "file://"+assets)
	for i := 0; i < 2; i++ {
		command := exec.Command("sh", "../../scripts/install.sh", "--version", "v0.0.0-test", "--no-modify-path")
		if output, err := command.CombinedOutput(); err != nil {
			t.Fatalf("install: %v %s", err, output)
		}
		updated, err := os.ReadFile(bridge)
		if err != nil || string(updated) == string(old) || string(updated) != string(binary) {
			t.Fatal("installed upgrade did not refresh the saved bridge")
		}
		if output, err := exec.Command(bridge, "--version").CombinedOutput(); err != nil || !strings.Contains(string(output), "alpha.16.4") {
			t.Fatalf("upgraded reference unusable: %v %s", err, output)
		}
	}
	// A fleet update may change both the app version and its engine layout.
	// The real installer must refresh saved references without losing history.
	flatEngine := filepath.Join(bundle, "Contents/Resources/codex")
	packagedEngine := filepath.Join(bundle, "Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex")
	if err := os.MkdirAll(filepath.Dir(packagedEngine), 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.Rename(flatEngine, packagedEngine); err != nil {
		t.Fatal(err)
	}
	if output, err := exec.Command("sh", "../../scripts/install.sh", "--version", "v0.0.0-test", "--no-modify-path").CombinedOutput(); err != nil {
		t.Fatalf("upgrade after engine relocation: %v %s", err, output)
	}
	if output, err := exec.Command(bridge, "--version").CombinedOutput(); err != nil || !strings.Contains(string(output), "engine moved") {
		t.Fatalf("upgraded saved reference lost relocated engine: %v %s", err, output)
	}
	// The ordinary desktop does not take the launcher lease. Its native owner
	// must independently block both scripts, including credential purge.
	lock := filepath.Join(child.Env["CODEX_ELECTRON_USER_DATA_PATH"], "SingletonLock")
	if err := os.Remove(lock); err != nil && !os.IsNotExist(err) {
		t.Fatal(err)
	}
	host, err := os.Hostname()
	if err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(fmt.Sprintf("%s-%d", host, os.Getpid()), lock); err != nil {
		t.Fatal(err)
	}
	for _, args := range [][]string{{"../../scripts/install.sh", "--version", "v0.0.0-test", "--no-modify-path"}, {"../../scripts/uninstall.sh", "--purge"}} {
		if output, err := exec.Command("sh", args...).CombinedOutput(); err == nil || !strings.Contains(string(output), "owned") {
			t.Fatalf("script did not respect ordinary desktop: %v %s", err, output)
		}
	}
	if _, err := os.Stat(filepath.Join(app.Dir, "credentials.yml")); err != nil {
		t.Fatal("refused purge removed credentials")
	}
	if err := os.Remove(lock); err != nil {
		t.Fatal(err)
	}
	// A downgrade below the supported minimum fails before changing any bridge.
	plist := filepath.Join(bundle, "Contents/Info.plist")
	metadata, err := os.ReadFile(plist)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(plist, []byte(strings.Replace(string(metadata), "26.917.71314", "26.917.71313", 1)), 0600); err != nil {
		t.Fatal(err)
	}
	if output, err := exec.Command("sh", "../../scripts/install.sh", "--version", "v0.0.0-test", "--no-modify-path").CombinedOutput(); err == nil || !strings.Contains(string(output), "incompatible") {
		t.Fatalf("incompatible client upgrade accepted: %v %s", err, output)
	}
	if current, err := os.ReadFile(bridge); err != nil || string(current) != string(binary) {
		t.Fatal("failed upgrade changed working bridge")
	}
	if err := os.WriteFile(plist, metadata, 0600); err != nil {
		t.Fatal(err)
	}
	installedBinary := filepath.Join(os.Getenv("TOFA_INSTALL_DIR"), "bin/tofa")
	if output, err := exec.Command(installedBinary, "uninstall").CombinedOutput(); err != nil {
		t.Fatalf("installed CLI uninstall: %v %s", err, output)
	}
	command := exec.Command(bridge, "--version")
	command.Env = append(os.Environ(), "TOFA_DESKTOP_CONTEXT="+child.Env["TOFA_DESKTOP_CONTEXT"])
	if output, err := command.CombinedOutput(); err == nil || !strings.Contains(string(output), "uninstalled") {
		t.Fatalf("CLI did not detach reference: %v %s", err, output)
	}
	if output, err := exec.Command("sh", "../../scripts/install.sh", "--version", "v0.0.0-test", "--no-modify-path").CombinedOutput(); err != nil {
		t.Fatalf("reinstall: %v %s", err, output)
	}
	command = exec.Command(bridge, "--version")
	command.Env = append(os.Environ(), "TOFA_DESKTOP_CONTEXT="+child.Env["TOFA_DESKTOP_CONTEXT"])
	if output, err := command.CombinedOutput(); err == nil || !strings.Contains(string(output), "expired") {
		t.Fatalf("reinstall failed to reattach reference with stale-context refusal: %v %s", err, output)
	}
	// Standalone recovery must also work when the main installed launcher fails.
	if err := os.WriteFile(filepath.Join(os.Getenv("TOFA_INSTALL_DIR"), "bin/tofa"), []byte("#!/bin/sh\necho BROKEN_INSTALLED_EXECUTED\nexit 9\n"), 0700); err != nil {
		t.Fatal(err)
	}
	for _, args := range [][]string{{}, {"--purge"}, {"--purge"}} {
		command := exec.Command("sh", append([]string{"../../scripts/uninstall.sh"}, args...)...)
		if output, err := command.CombinedOutput(); err != nil {
			t.Fatalf("uninstall: %v %s", err, output)
		}
		if output, err := exec.Command(bridge, "--version").CombinedOutput(); err != nil || !strings.Contains(string(output), "alpha.16.4") {
			t.Fatalf("removed launcher left dangling reference: %v %s", err, output)
		}
		if output, err := exec.Command(legacy, "--version").CombinedOutput(); err != nil || !strings.Contains(string(output), "alpha.16.4") {
			t.Fatalf("legacy saved reference became unusable: %v %s", err, output)
		}
		for path, want := range preserved {
			if actual, err := os.ReadFile(path); err != nil || string(actual) != string(want) {
				t.Fatalf("lifecycle changed shared state: %s", filepath.Base(path))
			}
		}
	}
	if _, err := os.Stat(filepath.Join(app.Dir, "credentials.yml")); !os.IsNotExist(err) {
		t.Fatal("purge retained launcher credentials")
	}
	if err := os.WriteFile(bridge, []byte("#!/bin/sh\necho USER_OVERRIDE_RAN\n"), 0700); err != nil {
		t.Fatal(err)
	}
	command = exec.Command("sh", "../../scripts/uninstall.sh", "--purge")
	if output, err := command.CombinedOutput(); err == nil || strings.Contains(string(output), "USER_OVERRIDE_RAN") {
		t.Fatalf("recovery executed a user-edited helper: %v %s", err, output)
	}
}

func TestDesktopUninstallDetachesSavedReference(t *testing.T) {
	bundle, capture := desktopFixture(t, "ignore")
	app, _ := adapterFixture(t, nil, nil)
	child, stop := liveDesktopFixture(t, app, bundle, capture)
	stop()
	root := filepath.Join(t.TempDir(), "install")
	if err := os.MkdirAll(filepath.Join(root, "bin"), 0700); err != nil {
		t.Fatal(err)
	}
	for path, value := range map[string]string{".tofa-install": "tofa-install-v1\n", "bin/tofa": "synthetic installed launcher"} {
		if err := os.WriteFile(filepath.Join(root, path), []byte(value), 0600); err != nil {
			t.Fatal(err)
		}
	}
	t.Setenv("TOFA_INSTALL_DIR", root)
	settings := filepath.Join(child.Env["CODEX_ELECTRON_USER_DATA_PATH"], "tool-settings.json")
	before, err := os.ReadFile(settings)
	if err != nil {
		t.Fatal(err)
	}
	if err := app.Run([]string{"desktop-lifecycle", "uninstall"}); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(filepath.Join(root, "bin/tofa")); !os.IsNotExist(err) {
		t.Fatal("installation survived uninstall")
	}
	after, err := os.ReadFile(settings)
	if err != nil || string(after) != string(before) {
		t.Fatal("uninstall rewrote shared tool settings")
	}
	bridge := child.Env["CODEX_CLI_PATH"]
	command := exec.Command(bridge, "--ordinary-probe", "argument with spaces")
	command.Env = append(os.Environ(), "CODEX_HOME="+child.Env["CODEX_HOME"], "TOFA_API_KEY=stale", "TOFA_DESKTOP_INACTIVE=stale")
	output, err := command.Output()
	var probe struct {
		Args    []string
		TofaKey *string `json:"tofa_key"`
	}
	if exit, ok := err.(*exec.ExitError); !ok || exit.ExitCode() != 23 || json.Unmarshal(output, &probe) != nil || probe.TofaKey != nil || len(probe.Args) != 2 || probe.Args[1] != "argument with spaces" {
		t.Fatalf("detached reference lost ordinary behavior: %v %s", err, output)
	}
	command = exec.Command(bridge, "--version")
	command.Env = append(os.Environ(), "TOFA_DESKTOP_CONTEXT="+child.Env["TOFA_DESKTOP_CONTEXT"], "TOFA_API_KEY="+child.Env["TOFA_API_KEY"])
	if output, err := command.CombinedOutput(); err == nil || !strings.Contains(string(output), "uninstalled") {
		t.Fatalf("detached reference did not explicitly disable launch access: %v %s", err, output)
	}
	if err := app.Run([]string{"desktop-lifecycle", "uninstall"}); err != nil {
		t.Fatalf("repeat uninstall: %v", err)
	}
	if err := os.Remove(capture); err != nil {
		t.Fatal(err)
	}
	relaunched, finish := liveDesktopFixture(t, app, bundle, capture)
	if relaunched.Env["CODEX_CLI_PATH"] != bridge || relaunched.Env["TOFA_API_KEY"] == child.Env["TOFA_API_KEY"] || relaunched.Env["TOFA_DESKTOP_CONTEXT"] == child.Env["TOFA_DESKTOP_CONTEXT"] {
		t.Fatal("relaunch did not reattach the saved path with fresh routing")
	}
	finish()
	assertExpiredDesktopContext(t, child)
}
