package tofa_test

import (
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

func TestDesktopDeclaredCandidateVerifiedSystemSkills(t *testing.T) {
	for _, scenario := range []string{"generated-refresh", "unknown-system-file", "modified-system-file", "personal-skill", "contract-drift", "engine-drift", "system-symlink", "forged-accepted-hash"} {
		t.Run(scenario, func(t *testing.T) {
			bundle, capture := nativeCandidateFixture(t)
			app, _ := adapterFixture(t, nil, nil)
			root := filepath.Join(os.Getenv("HOME"), ".codex/skills")
			write := func(name, body string) {
				t.Helper()
				p := filepath.Join(root, name)
				if e := os.MkdirAll(filepath.Dir(p), 0700); e != nil {
					t.Fatal(e)
				}
				if e := os.WriteFile(p, []byte(body), 0600); e != nil {
					t.Fatal(e)
				}
			}
			hash := func(s string) string { return fmt.Sprintf("%x", sha256.Sum256([]byte(s))) }
			write("personal/SKILL.md", "keep personal instructions")
			write(".system/.codex-system-skills.marker", "version-one")
			write(".system/openai-docs/SKILL.md", "bundled-one")
			os.MkdirAll("/tmp/tofa-presentation-validation", 0700)
			dir, e := os.MkdirTemp("/tmp/tofa-presentation-validation", "system-contract-")
			if e != nil {
				t.Fatal(e)
			}
			t.Cleanup(func() { os.RemoveAll(dir) })
			engine := filepath.Join(bundle, "Contents/Resources/codex")
			raw, e := os.ReadFile(engine)
			if e != nil {
				t.Fatal(e)
			}
			variants := []any{}
			for _, v := range []string{"one", "two"} {
				variants = append(variants, map[string]any{"engine": engine, "engine_sha256": fmt.Sprintf("%x", sha256.Sum256(raw)), "version": "codex-cli fixture-" + v, "files": map[string]string{".system/.codex-system-skills.marker": hash("version-" + v), ".system/openai-docs/SKILL.md": hash("bundled-" + v)}})
			}
			contract := filepath.Join(dir, "contract.json")
			raw, _ = json.Marshal(map[string]any{"schema": "tofa-generated-system-skills-v1", "sources": variants})
			os.WriteFile(contract, raw, 0600)
			observer := declaredCandidateObserver(t, app, bundle, "--system-skills-contract", contract)
			write(".system/.codex-system-skills.marker", "version-two")
			write(".system/openai-docs/SKILL.md", "bundled-two")
			switch scenario {
			case "unknown-system-file":
				write(".system/extra.md", "unexpected")
			case "modified-system-file":
				write(".system/openai-docs/SKILL.md", "altered instructions")
			case "personal-skill":
				write("personal/SKILL.md", "changed personal instructions")
			case "contract-drift":
				os.WriteFile(contract, append(raw, ' '), 0600)
			case "system-symlink":
				path := filepath.Join(root, ".system/openai-docs/SKILL.md")
				if e := os.Rename(path, path+".real"); e != nil {
					t.Fatal(e)
				}
				if e := os.Symlink(path+".real", path); e != nil {
					t.Fatal(e)
				}
			case "forged-accepted-hash":
				path := filepath.Join(filepath.Dir(observer), "declaration.json")
				data, _ := os.ReadFile(path)
				var declaration map[string]any
				json.Unmarshal(data, &declaration)
				evidence := declaration["identity"].(map[string]any)["system_skills"].(map[string]any)
				evidence["accepted_skills_sha256"] = []string{strings.Repeat("0", 64)}
				data, _ = json.Marshal(declaration)
				os.WriteFile(path, data, 0600)
			case "engine-drift":
				os.WriteFile(engine, []byte("#!/bin/sh\nexit 1\n"), 0700)
			}
			if scenario == "generated-refresh" {
				_, stop := liveDesktopFixture(t, app, bundle, capture, "--native-account-candidate", "--evaluation-observer", observer)
				stop()
				data, e := os.ReadFile(filepath.Join(root, "personal/SKILL.md"))
				if e != nil || string(data) != "keep personal instructions" {
					t.Fatal("user skill changed")
				}
				return
			}
			e = app.Run([]string{"launch", "codex-desktop", "--app-bundle", bundle, "--model", "moonshotai/Kimi-K3", "--native-account-candidate", "--evaluation-observer", observer})
			if e == nil {
				t.Fatal("unverified change admitted")
			}
			if scenario != "engine-drift" && !strings.Contains(e.Error(), "qualification") {
				t.Fatalf("wrong rejection: %v", e)
			}
			if _, e := os.Stat(capture); !os.IsNotExist(e) {
				t.Fatal("rejected change launched Desktop")
			}
		})
	}
}

// Actual engines generate both inventories in isolated homes. The public
// launcher observes their refresh; the Desktop executable is an owned fixture.
func TestDesktopDeclaredCandidateRealGeneratedSystemSkills(t *testing.T) {
	installed, other := os.Getenv("TOFA_TEST_DESKTOP_ENGINE"), os.Getenv("TOFA_TEST_OTHER_ENGINE")
	if installed == "" || other == "" {
		t.Skip("set both installed engine paths")
	}
	originalHome := os.Getenv("HOME")
	bundle, capture := nativeCandidateFixture(t) // desktopFixture sets HOME=t.TempDir().
	if os.Getenv("HOME") == originalHome {
		t.Fatal("fixture did not isolate HOME")
	}
	app, _ := adapterFixture(t, nil, nil)
	root := filepath.Join(os.Getenv("HOME"), ".codex/skills")
	sources := []any{}
	trees := []string{}
	markers := []string{}
	for _, engine := range []string{installed, other} {
		home := t.TempDir()
		os.WriteFile(filepath.Join(home, "config.toml"), []byte("cli_auth_credentials_store=\"file\"\n"), 0600)
		process := openDesktopEngine(t, capturedDesktop{Cwd: home, Env: map[string]string{"PATH": os.Getenv("PATH"), "HOME": os.Getenv("HOME"), "CODEX_HOME": home, "CODEX_CLI_PATH": engine}})
		process.close()
		tree := filepath.Join(home, "skills")
		files := preflightSkillFiles(t, tree)
		for name, raw := range files {
			files[name] = fmt.Sprintf("%x", sha256.Sum256([]byte(raw)))
		}
		markers = append(markers, files[".system/.codex-system-skills.marker"])
		trees = append(trees, tree)
		raw, e := os.ReadFile(engine)
		if e != nil {
			t.Fatal(e)
		}
		version, e := exec.Command(engine, "--version").Output()
		if e != nil {
			t.Fatal(e)
		}
		sources = append(sources, map[string]any{"engine": engine, "engine_sha256": fmt.Sprintf("%x", sha256.Sum256(raw)), "version": strings.TrimSpace(string(version)), "files": files})
	}
	if markers[0] == markers[1] {
		t.Skip("engines have identical system inventories")
	}
	install := func(tree string) {
		t.Helper()
		for rel := range preflightSkillFiles(t, tree) {
			raw, e := os.ReadFile(filepath.Join(tree, rel))
			if e != nil {
				t.Fatal(e)
			}
			dst := filepath.Join(root, rel)
			os.MkdirAll(filepath.Dir(dst), 0700)
			if e := os.WriteFile(dst, raw, 0600); e != nil {
				t.Fatal(e)
			}
		}
	}
	os.MkdirAll("/tmp/tofa-presentation-validation", 0700)
	dir, e := os.MkdirTemp("/tmp/tofa-presentation-validation", "real-system-contract-")
	if e != nil {
		t.Fatal(e)
	}
	t.Cleanup(func() { os.RemoveAll(dir) })
	raw, _ := json.Marshal(map[string]any{"schema": "tofa-generated-system-skills-v1", "sources": sources})
	contract := filepath.Join(dir, "contract.json")
	os.WriteFile(contract, raw, 0600)
	install(trees[0])
	observer := declaredCandidateObserver(t, app, bundle, "--system-skills-contract", contract)
	install(trees[1])
	_, stop := liveDesktopFixture(t, app, bundle, capture, "--native-account-candidate", "--evaluation-observer", observer)
	stop()
}

func TestDesktopSnapshotRejectsNonRegularGeneratedSource(t *testing.T) {
	bundle, _ := nativeCandidateFixture(t)
	app, _ := adapterFixture(t, nil, nil)
	observer := declaredCandidateObserver(t, app, bundle)
	raw, _ := os.ReadFile(filepath.Join(filepath.Dir(observer), "declaration.json"))
	var declaration struct {
		Identity struct {
			Runtime string `json:"runtime_root"`
			Harness string `json:"harness_root"`
			Source  string `json:"source_revision"`
		} `json:"identity"`
	}
	json.Unmarshal(raw, &declaration)
	root := filepath.Join(os.Getenv("HOME"), ".codex/skills/.system")
	os.MkdirAll(root, 0700)
	files := map[string]string{}
	for _, name := range []string{".codex-system-skills.marker", "SKILL.md"} {
		os.WriteFile(filepath.Join(root, name), []byte(name), 0600)
		files[".system/"+name] = fmt.Sprintf("%x", sha256.Sum256([]byte(name)))
	}
	contract := filepath.Join(filepath.Dir(observer), "system-skills.json")
	raw, _ = json.Marshal(map[string]any{"schema": "tofa-generated-system-skills-v1", "sources": []any{map[string]any{"engine": "/dev/null", "engine_sha256": fmt.Sprintf("%x", sha256.Sum256(nil)), "version": "not-an-engine", "files": files}}})
	os.WriteFile(contract, raw, 0600)
	e := app.Run([]string{"desktop-qualification", "snapshot", "--app-bundle", bundle, "--runtime-root", declaration.Identity.Runtime, "--harness-root", declaration.Identity.Harness, "--source-revision", declaration.Identity.Source, "--system-skills-contract", contract})
	if e == nil {
		t.Fatal("device admitted as a generated skill source")
	}
}
