package tofa

import (
	"path/filepath"
	"runtime"
	"testing"
)

// Compiled only into test binaries, including the copied bridge fixtures.
// Installer integration builds use this same executable via a linker override.
var DesktopProcessFixture string

func init() {
	_, source, _, _ := runtime.Caller(0)
	DesktopProcessFixture = filepath.Join(filepath.Dir(source), "../../scripts/fixtures/desktop_ps.sh")
	desktopProcessCommand = DesktopProcessFixture
}

// Explicit real-app qualification must inspect the actual host inventory.
func UseRealDesktopProcessesForTest(t *testing.T) {
	previous := desktopProcessCommand
	desktopProcessCommand = "/bin/ps"
	t.Cleanup(func() { desktopProcessCommand = previous })
}
