package tofa_test

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestDesktopRefusesProviderTransitionThatRemovesInstalledPlugin(t *testing.T) {
	for _, config := range []string{"[plugins.\"code-review@openai-bundled\"]\nenabled = true\n", "user_setting = true\n"} {
		t.Run(config, func(t *testing.T) {
			bundle, capture := desktopFixture(t, "normal")
			home := filepath.Join(os.Getenv("HOME"), ".codex")
			plugin := filepath.Join(home, "plugins/cache/openai-bundled/code-review/fixture/skills/review/SKILL.md")
			if err := os.MkdirAll(filepath.Dir(plugin), 0700); err != nil {
				t.Fatal(err)
			}
			if err := os.WriteFile(filepath.Join(home, "config.toml"), []byte(config), 0600); err != nil {
				t.Fatal(err)
			}
			if err := os.WriteFile(plugin, []byte("ordinary installed plugin\n"), 0600); err != nil {
				t.Fatal(err)
			}
			// Reproduce the native app boundary: adapted startup reconciles away an
			// installed plugin before it asks the engine to uninstall it. Ordinary
			// restart cannot undo the fact that the shared files were removed.
			native := filepath.Join(bundle, "Contents/MacOS/ChatGPT")
			raw, err := os.ReadFile(native)
			if err != nil {
				t.Fatal(err)
			}
			text := strings.Replace(string(raw), "profile=pathlib.Path(os.environ['CODEX_ELECTRON_USER_DATA_PATH'])", "import shutil\nshutil.rmtree(home/'plugins/cache/openai-bundled/code-review')\nconfig_path.write_text('')\nprofile=pathlib.Path(os.environ['CODEX_ELECTRON_USER_DATA_PATH'])", 1)
			if err := os.WriteFile(native, []byte(text), 0700); err != nil {
				t.Fatal(err)
			}
			app, _ := adapterFixture(t, nil, nil)
			err = app.Run([]string{"launch", "codex-desktop", "--app-bundle", bundle, "--model", "moonshotai/Kimi-K3", "--allow-unverified"})
			if err == nil || !strings.Contains(err.Error(), "code-review@openai-bundled") || !strings.Contains(err.Error(), "startup blocked") {
				t.Errorf("unsafe provider transition was not explicitly refused: %v", err)
			}
			if got, err := os.ReadFile(plugin); err != nil || string(got) != "ordinary installed plugin\n" {
				t.Error("installed plugin was removed or modified")
			}
			if got, err := os.ReadFile(filepath.Join(home, "config.toml")); err != nil || string(got) != config {
				t.Error("ordinary plugin configuration changed")
			}
			if _, err := os.Stat(capture + ".pid"); !os.IsNotExist(err) {
				t.Error("Desktop started before the preservation check")
			}
			if _, err := os.Stat(filepath.Join(app.Dir, "desktop-bridge-v2")); !os.IsNotExist(err) {
				t.Error("blocked launch installed or replaced the retained bridge")
			}
		})
	}
}

func TestDesktopPreservesConfiguredPluginWhenCacheIsMissing(t *testing.T) {
	for _, enabled := range []string{"true", "false"} {
		t.Run("enabled="+enabled, func(t *testing.T) {
			bundle, capture := desktopFixture(t, "normal")
			home := filepath.Join(os.Getenv("HOME"), ".codex")
			if err := os.MkdirAll(home, 0700); err != nil {
				t.Fatal(err)
			}
			config := "[plugins.\"code-review@openai-bundled\"]\nenabled = " + enabled + "\n"
			if err := os.WriteFile(filepath.Join(home, "config.toml"), []byte(config), 0600); err != nil {
				t.Fatal(err)
			}
			engine := filepath.Join(bundle, "Contents/Resources/codex")
			raw, err := os.ReadFile(engine)
			if err != nil {
				t.Fatal(err)
			}
			text := strings.Replace(string(raw), "        if req['method'] == 'configRequirements/read':", "        if req['method'] == 'config/read': result['config']['plugins'] = {'code-review@openai-bundled': {'enabled': values['plugins.\"code-review@openai-bundled\".enabled']}}\n        if req['method'] == 'configRequirements/read':", 1)
			if err := os.WriteFile(engine, []byte(text), 0700); err != nil {
				t.Fatal(err)
			}
			app, _ := adapterFixture(t, nil, nil)
			err = app.Run([]string{"launch", "codex-desktop", "--app-bundle", bundle, "--model", "moonshotai/Kimi-K3", "--allow-unverified"})
			if err == nil || !strings.Contains(err.Error(), "code-review@openai-bundled") {
				t.Errorf("configured plugin was not protected: %v", err)
			}
			if got, err := os.ReadFile(filepath.Join(home, "config.toml")); err != nil || string(got) != config {
				t.Error("ordinary plugin configuration changed")
			}
			if _, err := os.Stat(capture + ".pid"); !os.IsNotExist(err) {
				t.Error("Desktop started before the preservation check")
			}
			if _, err := os.Stat(filepath.Join(app.Dir, "desktop-bridge-v2")); !os.IsNotExist(err) {
				t.Error("blocked launch installed or replaced the retained bridge")
			}
		})
	}
}
