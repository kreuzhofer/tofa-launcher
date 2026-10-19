package tofa_test

import (
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"syscall"
	"testing"
	"time"

	"github.com/kreuzhofer/tofa-launcher/internal/tofa"
)

// Kill the actual launcher process: cancelling an in-process context cannot
// demonstrate what survives when deferred cleanup never runs.
func executableDesktopFixture(t *testing.T, app *tofa.App, bundle, capture string, selection ...string) (capturedDesktop, func()) {
	t.Helper()
	store := tofa.Store{Dir: app.Dir, Vault: app.Vault}
	if err := store.Login("fixture-project", "fixture-secret", "file"); err != nil {
		t.Fatal(err)
	}
	executable, err := os.Executable()
	if err != nil {
		t.Fatal(err)
	}
	args := append([]string{"--test-desktop-launch", app.Dir, "launch", "codex-desktop", "--app-bundle", bundle, "--model", "moonshotai/Kimi-K3", "--allow-unverified"}, selection...)
	command := exec.Command(executable, args...)
	command.Env = append(os.Environ(), "TOFA_TEST_ENDPOINT="+app.Endpoint)
	log, err := os.CreateTemp(t.TempDir(), "launcher-output-")
	if err != nil {
		t.Fatal(err)
	}
	defer log.Close()
	command.Stdout, command.Stderr = log, log
	if err := command.Start(); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { command.Process.Kill(); command.Wait() })
	deadline := time.Now().Add(10 * time.Second)
	var child capturedDesktop
	for {
		raw, err := os.ReadFile(capture)
		_, workerErr := os.Stat(capture + ".pid")
		if err == nil && workerErr == nil && json.Unmarshal(raw, &child) == nil {
			break
		}
		if time.Now().After(deadline) {
			data, _ := os.ReadFile(log.Name())
			t.Fatalf("desktop did not start: %s", data)
		}
		time.Sleep(20 * time.Millisecond)
	}
	owner, err := os.Readlink(filepath.Join(child.Env["CODEX_ELECTRON_USER_DATA_PATH"], "SingletonLock"))
	if err != nil {
		t.Fatal(err)
	}
	pid, err := strconv.Atoi(owner[strings.LastIndex(owner, "-")+1:])
	if err != nil {
		t.Fatal(err)
	}
	// The test owns this synthetic desktop. Production must refuse a surviving
	// desktop, never infer permission to signal a process from a stale record.
	t.Cleanup(func() { syscall.Kill(-pid, syscall.SIGKILL) })
	return child, func() {
		if err := command.Process.Kill(); err != nil {
			t.Fatal(err)
		}
		if err := command.Wait(); err == nil {
			t.Fatal("launcher was not killed")
		}
	}
}

func TestDesktopCrashRecoveryPreservesStateAndExpiresRoute(t *testing.T) {
	desktopLifecycleCrashRecoveryPreservesStateAndExpiresRoute(t, false)
}

func TestDesktopNativeCandidateCrashRecoveryPreservesStateAndExpiresRoute(t *testing.T) {
	desktopLifecycleCrashRecoveryPreservesStateAndExpiresRoute(t, true)
}

func desktopLifecycleCrashRecoveryPreservesStateAndExpiresRoute(t *testing.T, native bool) {
	bundle, capture := fixtureDesktopLifecycle(t, native, "ignore")
	app, _ := adapterFixture(t, func(w http.ResponseWriter, r *http.Request) { fmt.Fprint(w, "fixture response") }, nil)
	child, crash := executableDesktopFixture(t, app, bundle, capture, desktopLifecycleSelection(t, native)...)
	var oldInference string
	if native {
		oldInference = desktopLifecycleInference(t, child)
	}
	crash()

	root := filepath.Dir(child.Env["ZDOTDIR"])
	unrelated := exec.Command("/bin/sleep", "300")
	if err := unrelated.Start(); err != nil {
		t.Fatal(err)
	}
	defer func() { unrelated.Process.Kill(); unrelated.Wait() }()
	outside := filepath.Join(t.TempDir(), "outside.txt")
	if err := os.WriteFile(outside, []byte("user-owned outside runtime"), 0600); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(outside, filepath.Join(root, "outside-link")); err != nil {
		t.Fatal(err)
	}
	// The adapter is hosted by the killed launcher, not a surviving helper.
	address := strings.TrimPrefix(child.Env["TOFA_DESKTOP_CONTEXT"], "http://")
	if !native {
		if connection, err := net.DialTimeout("tcp", address, time.Second); err == nil {
			connection.Close()
			t.Fatal("adapter survived launcher death")
		}
	} else {
		// The observer belongs to this test and outlives the killed launcher.
		// Its live socket cannot revive either expired capability.
		assertDesktopLifecycleCapabilityRejected(t, child.Env["TOFA_DESKTOP_CONTEXT"], oldInference, false)
		assertDesktopLifecycleCapabilityRejected(t, child.Env["TOFA_DESKTOP_CONTEXT"], child.Env["TOFA_API_KEY"], true)
	}
	assertExpiredDesktopContext(t, child)
	config := filepath.Join(child.Env["CODEX_HOME"], "config.toml")
	file, err := os.OpenFile(config, os.O_APPEND|os.O_WRONLY, 0600)
	if err != nil {
		t.Fatal(err)
	}
	if _, err = file.WriteString("\n[user_preferences]\nkeep_after_crash = true\n"); err != nil {
		t.Fatal(err)
	}
	file.Close()
	preserved := map[string][]byte{}
	for _, path := range []string{config, filepath.Join(child.Env["CODEX_HOME"], "sessions/conversation.jsonl"), filepath.Join(child.Cwd, "user-work.txt")} {
		data, err := os.ReadFile(path)
		if err != nil {
			t.Fatal(err)
		}
		preserved[path] = data
	}
	auth := filepath.Join(child.Env["CODEX_HOME"], "auth.json")
	if err := os.WriteFile(auth, []byte("synthetic ordinary credentials"), 0600); err != nil {
		t.Fatal(err)
	}
	preserved[auth] = []byte("synthetic ordinary credentials")
	args := append([]string{"launch", "codex-desktop", "--app-bundle", bundle, "--model", "moonshotai/Kimi-K3", "--allow-unverified"}, desktopLifecycleSelection(t, native)...)
	if err := app.Run(args); err == nil || !strings.Contains(err.Error(), "Quit") {
		t.Fatalf("surviving desktop was not refused: %v", err)
	}
	if _, err := os.Stat(root); err != nil {
		t.Fatal("recovery removed resources while desktop still lived")
	}
	owner, _ := os.Readlink(filepath.Join(child.Env["CODEX_ELECTRON_USER_DATA_PATH"], "SingletonLock"))
	pid, _ := strconv.Atoi(owner[strings.LastIndex(owner, "-")+1:])
	syscall.Kill(-pid, syscall.SIGKILL) // Simulate the user quitting the surviving fixture.
	assertDesktopWorkerStopped(t, capture)
	waitDesktopPIDStopped(t, pid)
	for attempt := 0; attempt < 2; attempt++ {
		os.Remove(capture)
		next, stop := liveDesktopFixture(t, app, bundle, capture, desktopLifecycleSelection(t, native)...)
		if next.Env["TOFA_DESKTOP_CONTEXT"] == child.Env["TOFA_DESKTOP_CONTEXT"] || next.Env["TOFA_API_KEY"] == child.Env["TOFA_API_KEY"] {
			t.Fatal("relaunch reused an expired route")
		}
		if response := adapterRequest(t, next.Env["TOFA_DESKTOP_CONTEXT"], child.Env["TOFA_API_KEY"], `{"model":"moonshotai/Kimi-K3","input":[]}`); response.StatusCode != http.StatusUnauthorized {
			t.Fatal("old credential reached new adapter")
		}
		assertExpiredDesktopContext(t, child)
		if native {
			if desktopLifecycleInference(t, next) == oldInference {
				t.Fatal("recovery reused inference capability")
			}
			assertDesktopLifecycleCapabilityRejected(t, next.Env["TOFA_DESKTOP_CONTEXT"], oldInference, false, http.StatusUnauthorized)
			assertDesktopLifecycleCapabilityRejected(t, next.Env["TOFA_DESKTOP_CONTEXT"], child.Env["TOFA_API_KEY"], true, http.StatusUnauthorized)
		}
		stop()
		if _, err := os.Stat(root); !os.IsNotExist(err) {
			t.Fatal("abandoned launch resources survived recovery")
		}
		if _, err := os.Stat(child.CatalogPath); !os.IsNotExist(err) {
			t.Fatal("abandoned catalog survived recovery")
		}

		if err := syscall.Kill(unrelated.Process.Pid, 0); err != nil {
			t.Fatal("recovery stopped an unrelated process")
		}
		if data, err := os.ReadFile(outside); err != nil || string(data) != "user-owned outside runtime" {
			t.Fatal("recovery followed a symlink outside owned runtime")
		}
		for path, want := range preserved {
			got, err := os.ReadFile(path)
			if err != nil || string(got) != string(want) {
				t.Fatalf("recovery changed user state: %s", filepath.Base(path))
			}
		}
	}
}

func assertExpiredDesktopContext(t *testing.T, child capturedDesktop, explanations ...string) {
	t.Helper()
	command := exec.Command(child.Env["CODEX_CLI_PATH"], "--version")
	for key, value := range child.Env {
		command.Env = append(command.Env, key+"="+value)
	}
	output, err := command.CombinedOutput()
	expected := "context is invalid or expired"
	if len(explanations) != 0 {
		expected = explanations[0]
	}
	if err == nil || !strings.Contains(string(output), expected) {
		t.Fatal("stale launch context delegated to engine")
	}
}

func waitDesktopPIDStopped(t *testing.T, pid int) {
	t.Helper()
	deadline := time.Now().Add(5 * time.Second)
	for syscall.Kill(pid, 0) == nil {
		if time.Now().After(deadline) {
			t.Fatal("owned desktop survived fixture shutdown")
		}
		time.Sleep(20 * time.Millisecond)
	}
}

func TestDesktopRecoveryRetainsUnprovenOwnership(t *testing.T) {
	bundle, _ := desktopFixture(t, "normal")
	app, output := adapterFixture(t, nil, nil)
	profile := filepath.Join(os.Getenv("HOME"), "Library/Application Support/Codex")
	parent := filepath.Join(app.Dir, "desktop-launches")
	preserved := map[string][]byte{}
	for _, kind := range []string{"missing", "malformed", "foreign-profile", "live-owner", "symlink-record", "symlink-directory"} {
		root := filepath.Join(parent, "launch-"+kind)
		if err := os.MkdirAll(root, 0700); err != nil {
			t.Fatal(err)
		}
		path := filepath.Join(root, "keep.txt")
		data := []byte("preserve " + kind)
		if err := os.WriteFile(path, data, 0600); err != nil {
			t.Fatal(err)
		}
		preserved[path] = data
		owner := map[string]any{"Version": 1, "PID": os.Getpid(), "Profile": profile}
		if kind == "foreign-profile" {
			owner["Profile"] = t.TempDir()
		}
		record, _ := json.Marshal(owner)
		if kind == "malformed" {
			record = []byte("not an ownership record")
		}
		if kind != "missing" {
			if err := os.WriteFile(filepath.Join(root, "owner.json"), record, 0600); err != nil {
				t.Fatal(err)
			}
		}
		if kind == "symlink-record" {
			path := filepath.Join(root, "owner.json")
			if err := os.Rename(path, path+".saved"); err != nil {
				t.Fatal(err)
			}
			if err := os.Symlink(path+".saved", path); err != nil {
				t.Fatal(err)
			}
		}
		if kind == "symlink-directory" {
			target := filepath.Join(t.TempDir(), "outside")
			if err := os.Rename(root, target); err != nil {
				t.Fatal(err)
			}
			if err := os.Symlink(target, root); err != nil {
				t.Fatal(err)
			}
		}
	}
	for attempt := 0; attempt < 2; attempt++ {
		if err := app.Run([]string{"launch", "codex-desktop", "--app-bundle", bundle, "--model", "moonshotai/Kimi-K3", "--allow-unverified"}); err != nil {
			t.Fatal(err)
		}

		for path, want := range preserved {
			got, err := os.ReadFile(path)
			if err != nil || string(got) != string(want) {
				t.Fatalf("recovery removed unproven resource: %s", path)
			}
		}
	}
	if !strings.Contains(output.String(), "Desktop recovery: retained") {
		t.Fatal("unrecovered artifacts were silently ignored")
	}
}
