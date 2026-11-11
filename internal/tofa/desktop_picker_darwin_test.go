package tofa_test

import (
	"encoding/json"
	"os"
	"os/exec"
	"path/filepath"
	"testing"
)

// Use the existing executable desktop boundary with real terminal input. The
// Python driver isolates HOME, launcher credentials and the loopback provider.
func TestDesktopPicker(t *testing.T) {
	// Resolve build caches before desktopFixture isolates HOME. Otherwise Go's
	// default module cache lands in t.TempDir with read-only module directories,
	// making cleanup fail on hosts that do not explicitly export GOPATH.
	cache, err := exec.Command("go", "env", "-json", "GOPATH", "GOCACHE", "GOMODCACHE").Output()
	if err != nil {
		t.Fatal(err)
	}
	var buildEnv map[string]string
	if err := json.Unmarshal(cache, &buildEnv); err != nil {
		t.Fatal(err)
	}
	bundle, capture := desktopFixture(t, "controlled")
	if installed := os.Getenv("TOFA_TEST_DESKTOP_ENGINE"); installed != "" {
		// Keep signed-in preflight synthetic, but supply complete real metadata
		// for the installed engine used by the Python protocol tests after launch.
		command := exec.Command(installed, "debug", "models", "--bundled")
		command.Env = []string{"PATH=" + os.Getenv("PATH"), "HOME=" + os.Getenv("HOME"), "CODEX_HOME=" + filepath.Join(os.Getenv("HOME"), ".codex")}
		catalog, err := command.Output()
		if err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(filepath.Join(bundle, "Contents/Resources/native-catalog.json"), catalog, 0600); err != nil {
			t.Fatal(err)
		}
	}

	command := exec.Command("python3", "scripts/desktop_picker_test.py", "-v")
	command.Dir = "../.."
	command.Env = append(os.Environ(), "FIXTURE_DESKTOP_BUNDLE="+bundle, "FIXTURE_DESKTOP_CAPTURE="+capture)
	for key, value := range buildEnv {
		command.Env = append(command.Env, key+"="+value)
	}
	if output, err := command.CombinedOutput(); err != nil {
		t.Fatalf("desktop picker: %v\n%s", err, output)
	} else {
		t.Log(string(output))
	}
}
