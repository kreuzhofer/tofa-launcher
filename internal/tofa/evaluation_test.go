package tofa_test

import (
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"testing"

	"github.com/kreuzhofer/tofa-launcher/internal/tofa"
)

func TestEvaluationLaunchRegistersOnlyItsAdapterBeforeStartingClient(t *testing.T) {
	if runtime.GOOS != "darwin" {
		t.Skip("macOS evaluator pilot")
	}
	var registration map[string]string
	observer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/register" || r.Header.Get("Authorization") != "Bearer synthetic-control-secret" {
			t.Error("invalid evaluation registration")
		}
		json.NewDecoder(r.Body).Decode(&registration)
		io.WriteString(w, `{"ready":true}`)
	}))
	defer observer.Close()
	config := filepath.Join(t.TempDir(), "observer.json")
	data, _ := json.Marshal(map[string]any{"version": 1, "endpoint": observer.URL,
		"secret": "synthetic-control-secret", "seconds": 180})
	if err := os.WriteFile(config, data, 0600); err != nil {
		t.Fatal(err)
	}
	app, _ := adapterFixture(t, func(w http.ResponseWriter, r *http.Request) {
		t.Fatal("registration performed inference")
	}, func(endpoint, token string) error {
		if endpoint != observer.URL || registration["token"] != token ||
			!strings.HasPrefix(registration["endpoint"], "http://127.0.0.1:") ||
			registration["endpoint"] == endpoint {
			t.Fatal("client did not use the registered evaluation boundary")
		}
		return nil
	})
	if err := app.Run([]string{"launch", "codex", "--model", "moonshotai/Kimi-K3", "--allow-unverified",
		"--evaluation-observer", config}); err != nil {
		t.Fatal(err)
	}
}

func TestEvaluationLaunchScopesSuppliedRuntimeMCPWithoutEditingSettings(t *testing.T) {
	if runtime.GOOS != "darwin" {
		t.Skip("macOS evaluator pilot")
	}
	root := t.TempDir()
	runtimeRoot := filepath.Join(root, "supplied runtime")
	python := filepath.Join(runtimeRoot, "dependencies/python/bin/python3")
	if err := os.MkdirAll(filepath.Dir(python), 0700); err != nil {
		t.Fatal(err)
	}
	os.WriteFile(python, []byte("fixture never executed"), 0700)
	script := filepath.Join(root, "presentation_runtime.py")
	os.WriteFile(script, []byte("fixture never executed"), 0600)
	bin := filepath.Join(root, "bin")
	os.Mkdir(bin, 0700)
	os.WriteFile(filepath.Join(bin, "codex"), []byte("#!/bin/sh\nprintf '[]\\n'\n"), 0700)
	t.Setenv("PATH", bin+string(os.PathListSeparator)+os.Getenv("PATH"))
	home := filepath.Join(root, "home")
	os.Mkdir(home, 0700)
	settings := filepath.Join(home, "config.toml")
	os.WriteFile(settings, []byte("# preserve unrelated settings\n"), 0600)
	t.Setenv("CODEX_HOME", home)
	observer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		io.WriteString(w, `{"ready":true}`)
	}))
	defer observer.Close()
	config := filepath.Join(root, "observer.json")
	data, _ := json.Marshal(map[string]any{"version": 1, "endpoint": observer.URL,
		"secret": "synthetic-control-secret", "seconds": 180,
		"presentation_runtime": map[string]string{"root": runtimeRoot, "script": script}})
	os.WriteFile(config, data, 0600)
	app, _ := adapterFixture(t, func(w http.ResponseWriter, r *http.Request) { t.Fatal("unexpected inference") }, nil)
	app.RunClient = func(args, env []string) error {
		all := strings.Join(args, " ")
		for _, want := range []string{"mcp_servers.tofa_presentation_runtime=", strconv.Quote(python),
			strconv.Quote(script), "load_workspace_dependencies", `"-I"`, `"-B"`} {
			if !strings.Contains(all, want) {
				t.Errorf("missing runtime scope %s in %s", want, all)
			}
		}
		return nil
	}
	if err := app.Run([]string{"launch", "codex", "--model", "moonshotai/Kimi-K3", "--allow-unverified", "--evaluation-observer", config}); err != nil {
		t.Fatal(err)
	}
	after, _ := os.ReadFile(settings)
	if string(after) != "# preserve unrelated settings\n" {
		t.Fatal("changed ordinary settings")
	}
}

func TestEvaluationRefusesDirectConnectionBeforeCredentials(t *testing.T) {
	app := &tofa.App{Dir: t.TempDir(), Out: io.Discard}
	err := app.Run([]string{"launch", "codex", "--model", "moonshotai/Kimi-K3", "--direct",
		"--evaluation-observer", "/missing"})
	if err == nil || !strings.Contains(err.Error(), "evaluation requires the adapted connection") {
		t.Fatalf("unexpected error: %v", err)
	}
}

func TestEvaluationRuntimeRefusesConflictsAndUnsafeInputsBeforeCredentials(t *testing.T) {
	if runtime.GOOS != "darwin" {
		t.Skip("macOS evaluator pilot")
	}
	for _, test := range []struct{ name, catalog, failure string }{
		{"conflict", `[{"name":"tofa_presentation_runtime"}]`, "conflicts"},
		{"malformed_catalog", `{}`, "inspect existing MCP"},
		{"missing_name", `[{}]`, "inspect existing MCP"},
		{"non_executable", `[]`, "executable or loader unavailable"},
		{"outside_python", `[]`, "outside supplied runtime"},
		{"symlinked_loader", `[]`, "executable or loader unavailable"},
	} {
		t.Run(test.name, func(t *testing.T) {
			root := t.TempDir()
			runtimeRoot := filepath.Join(root, "runtime")
			python := filepath.Join(runtimeRoot, "dependencies/python/bin/python3")
			if err := os.MkdirAll(filepath.Dir(python), 0700); err != nil {
				t.Fatal(err)
			}
			if err := os.WriteFile(python, []byte("never executed"), 0700); err != nil {
				t.Fatal(err)
			}
			script := filepath.Join(root, "presentation_runtime.py")
			if err := os.WriteFile(script, []byte("never executed"), 0600); err != nil {
				t.Fatal(err)
			}
			if test.name == "non_executable" {
				os.Chmod(python, 0600)
			}
			if test.name == "outside_python" {
				outside := filepath.Join(root, "other-python")
				os.WriteFile(outside, []byte("never executed"), 0700)
				os.Remove(python)
				os.Symlink(outside, python)
			}
			if test.name == "symlinked_loader" {
				outside := filepath.Join(root, "other-script")
				os.WriteFile(outside, []byte("never executed"), 0600)
				os.Remove(script)
				os.Symlink(outside, script)
			}
			bin := filepath.Join(root, "bin")
			os.Mkdir(bin, 0700)
			os.WriteFile(filepath.Join(bin, "codex"), []byte("#!/bin/sh\nprintf '%s\\n' '"+test.catalog+"'\n"), 0700)
			t.Setenv("PATH", bin+string(os.PathListSeparator)+os.Getenv("PATH"))
			config := filepath.Join(root, "observer.json")
			data, _ := json.Marshal(map[string]any{"version": 1, "endpoint": "http://127.0.0.1:1",
				"secret": "synthetic-control-secret", "seconds": 180,
				"presentation_runtime": map[string]string{"root": runtimeRoot, "script": script}})
			os.WriteFile(config, data, 0600)
			app := &tofa.App{Dir: t.TempDir(), Out: io.Discard}
			err := app.Run([]string{"launch", "codex", "--model", "moonshotai/Kimi-K3", "--allow-unverified", "--evaluation-observer", config})
			if err == nil || !strings.Contains(err.Error(), test.failure) {
				t.Fatalf("wrong boundary failure: %v", err)
			}
		})
	}
}
