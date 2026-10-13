package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

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
