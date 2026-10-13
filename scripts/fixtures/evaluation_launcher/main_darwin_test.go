package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

func TestExplicitRetainedFixtureStoreSurvivesExitWithoutCredentials(t *testing.T) {
	root := t.TempDir()
	binary := filepath.Join(root, "evaluation-launcher")
	if output, err := exec.Command("go", "build", "-o", binary, ".").CombinedOutput(); err != nil {
		t.Fatalf("build fixture: %v %s", err, output)
	}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body := `{"data":[{"id":"moonshotai/Kimi-K3"}]}`
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(body))
	}))
	defer server.Close()
	retained := filepath.Join(root, "retained")
	for attempt := 0; attempt < 2; attempt++ {
		command := exec.Command(binary, "models")
		command.Env = append(os.Environ(), "FIXTURE_ENDPOINT="+server.URL, "FIXTURE_RETAINED_DIR="+retained)
		if output, err := command.CombinedOutput(); err != nil {
			t.Fatalf("retained fixture invocation: %v %s", err, output)
		}
		if info, err := os.Stat(retained); err != nil || !info.IsDir() || info.Mode().Perm() != 0700 {
			t.Fatalf("retained fixture directory did not survive: %v", err)
		}
		if _, err := os.Stat(filepath.Join(retained, "credentials.yml")); !os.IsNotExist(err) {
			t.Fatal("retained fixture kept synthetic credentials after exit")
		}
	}
	for _, kind := range []string{"unowned", "public", "symlink", "marker-symlink"} {
		t.Run(kind, func(t *testing.T) {
			path := filepath.Join(root, kind)
			if kind == "symlink" {
				if err := os.Symlink(retained, path); err != nil {
					t.Fatal(err)
				}
			} else {
				if err := os.Mkdir(path, 0700); err != nil {
					t.Fatal(err)
				}
				if kind == "public" {
					if err := os.Chmod(path, 0755); err != nil {
						t.Fatal(err)
					}
				} else if kind == "marker-symlink" {
					if err := os.Symlink(filepath.Join(retained, ".evaluation-store"), filepath.Join(path, ".evaluation-store")); err != nil {
						t.Fatal(err)
					}
				}
			}
			command := exec.Command(binary, "models")
			command.Env = append(os.Environ(), "FIXTURE_ENDPOINT="+server.URL, "FIXTURE_RETAINED_DIR="+path)
			if output, err := command.CombinedOutput(); err == nil || !strings.Contains(string(output), "fixture retained directory") {
				t.Fatalf("unowned store was not refused: %v %s", err, output)
			}
			if _, err := os.Lstat(path); err != nil {
				t.Fatal("refusal removed an unowned path")
			}
			if _, err := os.Stat(filepath.Join(path, "credentials.yml")); !os.IsNotExist(err) {
				t.Fatal("refusal wrote credentials")
			}
		})
	}
}

func TestSavedBridgeDoesNotAllocateAnotherSyntheticStore(t *testing.T) {
	root := t.TempDir()
	bridge := filepath.Join(root, "tofa-desktop-engine")
	build := exec.Command("go", "build", "-o", bridge, ".")
	if output, err := build.CombinedOutput(); err != nil {
		t.Fatalf("build fixture: %v %s", err, output)
	}
	if err := os.Chmod(bridge, 0700); err != nil {
		t.Fatal(err)
	}
	engine := filepath.Join(root, "codex")
	if err := os.WriteFile(engine, []byte("#!/bin/sh\nprintf 'fixture-engine\\n'\n"), 0700); err != nil {
		t.Fatal(err)
	}
	raw, err := os.ReadFile(bridge)
	if err != nil {
		t.Fatal(err)
	}
	digest := sha256.Sum256(raw)
	owner, _ := json.Marshal(map[string]any{"Version": 2, "Engine": engine, "SHA256": hex.EncodeToString(digest[:])})
	if err := os.WriteFile(filepath.Join(root, "owner.json"), owner, 0600); err != nil {
		t.Fatal(err)
	}
	temporary := filepath.Join(root, "tmp")
	if err := os.Mkdir(temporary, 0700); err != nil {
		t.Fatal(err)
	}
	command := exec.Command(bridge, "--ordinary-probe")
	command.Env = []string{"PATH=" + os.Getenv("PATH"), "HOME=" + root, "TMPDIR=" + temporary, "FIXTURE_ENDPOINT=http://127.0.0.1:1"}
	output, err := command.CombinedOutput()
	if err != nil || strings.TrimSpace(string(output)) != "fixture-engine" {
		t.Fatalf("saved engine reference failed: %v %s", err, output)
	}
	stores, err := filepath.Glob(filepath.Join(temporary, "tofa-synthetic-store-*"))
	if err != nil || len(stores) != 0 {
		t.Fatalf("bridge leaked synthetic credential stores after exec: %v %v", stores, err)
	}
}
