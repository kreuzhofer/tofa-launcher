package tofa_test

import (
	"encoding/json"
	"os"
	"os/exec"
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
