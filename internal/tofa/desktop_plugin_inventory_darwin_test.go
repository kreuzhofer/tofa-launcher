package tofa

import (
	"os"
	"path/filepath"
	"testing"
)

func cachedMCPFixture(t *testing.T, home, version, engine string) string {
	t.Helper()
	root := filepath.Join(home, "plugins/cache/openai-bundled/unified-computer-use", version)
	if err := os.MkdirAll(filepath.Join(root, ".codex-plugin"), 0700); err != nil {
		t.Fatal(err)
	}
	for name, raw := range map[string]string{
		".codex-plugin/plugin.json": `{"name":"unified-computer-use","version":"` + version + `","description":"retained metadata"}`,
		".mcp.json":                 `{"mcpServers":{"cua_repl":{"env":{"CODEX_CLI_PATH":"` + engine + `"}}}}`,
	} {
		if err := os.WriteFile(filepath.Join(root, name), []byte(raw), 0600); err != nil {
			t.Fatal(err)
		}
	}
	return root
}

func TestDesktopCachedMCPInventoryPreservesEveryVersion(t *testing.T) {
	home := t.TempDir()
	first := cachedMCPFixture(t, home, "older", "/engine")
	second := cachedMCPFixture(t, home, "newer", "/engine")
	files, err := desktopCachedMCPFiles(home)
	if err != nil || len(files) != 2 {
		t.Fatalf("inventory: %v %v", files, err)
	}
	hash := func() string {
		t.Helper()
		v, err := admissionTree(home, "/engine", "/owned-bridge", files...)
		if err != nil {
			t.Fatal(err)
		}
		return v
	}
	before := hash()
	for _, root := range []string{first, second} {
		os.WriteFile(filepath.Join(root, ".mcp.json"), []byte(`{"mcpServers":{"cua_repl":{"env":{"CODEX_CLI_PATH":"/owned-bridge"}}}}`), 0600)
	}
	if hash() != before {
		t.Fatal("recognized bridge references changed identity")
	}
	os.WriteFile(filepath.Join(first, "additional-resource"), []byte("drift"), 0600)
	if hash() == before {
		t.Fatal("older cached plugin resource drift hidden")
	}
	os.WriteFile(filepath.Join(second, ".mcp.json"), []byte(`{"mcpServers":{"cua_repl":{"env":{"CODEX_CLI_PATH":"/unowned"}}}}`), 0600)
	if _, err := admissionTree(home, "/engine", "/owned-bridge", files...); err == nil {
		t.Fatal("unowned executable accepted")
	}
}

func TestDesktopCachedMCPInventoryRejectsUnverifiableEntries(t *testing.T) {
	for _, fault := range []string{"wrong name", "wrong version", "duplicate key", "missing manifest", "version symlink", "manifest directory symlink", "manifest symlink", "mcp symlink", "cache symlink"} {
		t.Run(fault, func(t *testing.T) {
			home := t.TempDir()
			root := cachedMCPFixture(t, home, "installed", "/engine")
			manifest := filepath.Join(root, ".codex-plugin/plugin.json")
			switch fault {
			case "wrong name":
				os.WriteFile(manifest, []byte(`{"name":"other","version":"installed"}`), 0600)
			case "wrong version":
				os.WriteFile(manifest, []byte(`{"name":"unified-computer-use","version":"other"}`), 0600)
			case "duplicate key":
				os.WriteFile(manifest, []byte(`{"name":"unified-computer-use","version":"other","version":"installed"}`), 0600)
			case "missing manifest":
				os.Remove(manifest)
			default:
				path := root
				switch fault {
				case "manifest directory symlink":
					path = filepath.Dir(manifest)
				case "manifest symlink":
					path = manifest
				case "mcp symlink":
					path = filepath.Join(root, ".mcp.json")
				case "cache symlink":
					path = filepath.Dir(root)
				}
				target := path + "-target"
				if err := os.Rename(path, target); err != nil {
					t.Fatal(err)
				}
				if err := os.Symlink(target, path); err != nil {
					t.Fatal(err)
				}
			}
			if _, err := desktopCachedMCPFiles(home); err == nil {
				t.Fatal("unverifiable cache accepted")
			}
		})
	}
}

func TestDesktopCachedMCPInventoryAbsent(t *testing.T) {
	files, err := desktopCachedMCPFiles(t.TempDir())
	if err != nil || len(files) != 0 {
		t.Fatalf("absent cache: %v %v", files, err)
	}
}
