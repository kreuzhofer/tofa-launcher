package tofa_test

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
	"time"
)

func TestDesktopMainEngineRegistrationCannotBeReplaced(t *testing.T) {
	bundle, capture := desktopFixture(t, "ignore")
	app, _ := adapterFixture(t, nil, nil)
	child, stop := liveDesktopFixture(t, app, bundle, capture)
	defer stop()
	deadline := time.Now().Add(5 * time.Second)
	for {
		if _, err := os.Stat(capture + ".pid"); err == nil {
			break
		}
		if time.Now().After(deadline) {
			t.Fatal("conversation engine did not initialize")
		}
		time.Sleep(10 * time.Millisecond)
	}
	for _, pid := range []string{"invalid", "0", "-1", strconv.Itoa(os.Getpid())} {
		request, err := http.NewRequest(http.MethodGet, child.Env["TOFA_DESKTOP_CONTEXT"]+"/desktop-launch", nil)
		if err != nil {
			t.Fatal(err)
		}
		request.Header.Set("Authorization", "Bearer "+child.Env["TOFA_API_KEY"])
		request.Header.Set("X-Tofa-Main-Engine-Pid", pid)
		response, err := http.DefaultClient.Do(request)
		if err != nil {
			t.Fatal(err)
		}
		response.Body.Close()
		if response.StatusCode != http.StatusConflict {
			t.Fatalf("invalid or replacement engine registration accepted: %s", pid)
		}
	}
}

func TestDesktopStartupProbeDoesNotBecomeConversationEngine(t *testing.T) {
	bundle, _ := desktopFixture(t, "startup-probe")
	app, _ := adapterFixture(t, nil, nil)
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	err := app.RunContext(ctx, []string{"launch", "codex-desktop", "--app-bundle", bundle, "--model", "deepseek-ai/DeepSeek-V4.1-Flash"})
	if !errors.Is(err, context.DeadlineExceeded) {
		t.Fatalf("temporary startup engine stopped the healthy conversation engine: %v", err)
	}
}

func TestDesktopMinimumVersions(t *testing.T) {
	for _, tc := range []struct {
		name, appVersion, engineVersion string
		accepted                        bool
	}{
		{"minimum", "26.917.71314", "0.155.0-alpha.16.4", true},
		{"updated desktop", "26.928.21956", "0.159.2", true},
		{"later numeric prerelease", "26.917.71314", "0.155.0-alpha.16.10", true},
		{"stable engine", "26.917.71314", "0.155.0", true},
		{"future compatible version", "27.0.0", "1.0.0", true},
		{"old desktop", "26.917.71313", "0.159.2", false},
		{"old engine", "26.928.21956", "0.155.0-alpha.16.3", false},
		{"invalid desktop version", "26.unknown", "0.159.2", false},
		{"invalid engine version", "26.928.21956", "0.159.2junk", false},
	} {
		t.Run(tc.name, func(t *testing.T) {
			bundle, capture := desktopFixture(t, "normal")
			plist := filepath.Join(bundle, "Contents/Info.plist")
			data, err := os.ReadFile(plist)
			if err != nil {
				t.Fatal(err)
			}
			text := strings.ReplaceAll(string(data), "26.917.71314", tc.appVersion)
			text = strings.ReplaceAll(text, "10954", "12404")
			if err := os.WriteFile(plist, []byte(text), 0600); err != nil {
				t.Fatal(err)
			}
			engine := filepath.Join(bundle, "Contents/Resources/codex")
			data, err = os.ReadFile(engine)
			if err != nil {
				t.Fatal(err)
			}
			if err := os.WriteFile(engine, []byte(strings.ReplaceAll(string(data), "0.155.0-alpha.16.4", tc.engineVersion)), 0700); err != nil {
				t.Fatal(err)
			}
			app, _ := adapterFixture(t, nil, nil)
			err = app.Run([]string{"launch", "codex-desktop", "--app-bundle", bundle, "--model", "deepseek-ai/DeepSeek-V4.1-Flash"})
			if tc.accepted {
				if err != nil {
					t.Fatalf("compatible version rejected: %v", err)
				}
				if _, err := os.Stat(capture); err != nil {
					t.Fatal("accepted client never launched")
				}
			} else {
				if err == nil || !strings.Contains(err.Error(), "version") {
					t.Fatalf("expected explicit version refusal, got %v", err)
				}
				if _, err := os.Stat(capture); !os.IsNotExist(err) {
					t.Fatal("incompatible version launched")
				}
			}
		})
	}
}

func TestDesktopSavedReferenceFollowsBundleEngineMove(t *testing.T) {
	bundle, capture := desktopFixture(t, "ignore")
	app, _ := adapterFixture(t, nil, nil)
	child, stop := liveDesktopFixture(t, app, bundle, capture, "--model", "deepseek-ai/DeepSeek-V4.1-Flash")
	stop()
	legacy := filepath.Join(bundle, "Contents/Resources/codex")
	packaged := filepath.Join(bundle, "Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex")
	if err := os.MkdirAll(filepath.Dir(packaged), 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.Rename(legacy, packaged); err != nil {
		t.Fatal(err)
	}
	command := exec.Command(child.Env["CODEX_CLI_PATH"], "--version")
	command.Env = []string{"PATH=" + os.Getenv("PATH"), "HOME=" + os.Getenv("HOME")}
	var diagnostics bytes.Buffer
	command.Stderr = &diagnostics
	output, err := command.Output()
	if err != nil || strings.TrimSpace(string(output)) != "codex-cli 0.155.0-alpha.16.4" {
		t.Fatalf("saved desktop reference stopped working after an engine move: %v %s", err, diagnostics.String())
	}
	if !strings.Contains(diagnostics.String(), "engine moved") {
		t.Fatal("engine relocation was not announced")
	}
}

func TestDesktopPackagedEngineLayout(t *testing.T) {
	for _, legacyPresent := range []bool{false, true} {
		t.Run(map[bool]string{false: "packaged only", true: "packaged takes precedence"}[legacyPresent], func(t *testing.T) {
			bundle, capture := desktopFixture(t, "normal")
			legacy := filepath.Join(bundle, "Contents/Resources/codex")
			packaged := filepath.Join(bundle, "Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex")
			if err := os.MkdirAll(filepath.Dir(packaged), 0700); err != nil {
				t.Fatal(err)
			}
			if err := os.Rename(legacy, packaged); err != nil {
				t.Fatal(err)
			}
			if legacyPresent {
				if err := os.WriteFile(legacy, []byte("#!/bin/sh\necho obsolete-flat-engine >&2\nexit 1\n"), 0700); err != nil {
					t.Fatal(err)
				}
			}
			app, _ := adapterFixture(t, nil, nil)
			if err := app.Run([]string{"launch", "codex-desktop", "--app-bundle", bundle, "--model", "deepseek-ai/DeepSeek-V4.1-Flash"}); err != nil {
				t.Fatalf("packaged native engine did not launch: %v", err)
			}
			if _, err := os.Stat(capture); err != nil {
				t.Fatal("packaged desktop never started")
			}
		})
	}
}

func TestDesktopIncompleteEnginePackageIsRefused(t *testing.T) {
	bundle, capture := desktopFixture(t, "normal")
	if err := os.MkdirAll(filepath.Join(bundle, "Contents/Resources/codex-cli"), 0700); err != nil {
		t.Fatal(err)
	}
	app, _ := adapterFixture(t, nil, nil)
	err := app.Run([]string{"launch", "codex-desktop", "--app-bundle", bundle, "--model", "deepseek-ai/DeepSeek-V4.1-Flash"})
	if err == nil || !strings.Contains(err.Error(), "bundled Codex engine") {
		t.Fatalf("incomplete package silently used the obsolete flat engine: %v", err)
	}
	if _, err := os.Stat(capture); !os.IsNotExist(err) {
		t.Fatal("incomplete app bundle launched")
	}
}

// Native app tools authenticate the Node peer, its engine parent and its Desktop
// grandparent. A long-lived launcher intermediary breaks this installed contract.
func TestDesktopEngineRetainsDirectNativeParent(t *testing.T) {
	bundle, capture := desktopFixture(t, "ignore")
	app, _ := adapterFixture(t, nil, nil)
	child, stop := liveDesktopFixture(t, app, bundle, capture)
	defer stop()
	deadline := time.Now().Add(10 * time.Second)
	for {
		ancestry, err := os.ReadFile(capture + ".ancestry")
		pid, pidErr := os.ReadFile(capture + ".pid")
		if err == nil && pidErr == nil {
			var observed struct {
				PID    int
				Parent int
			}
			if err := json.Unmarshal(ancestry, &observed); err != nil {
				t.Fatal(err)
			}
			lock, err := os.Readlink(filepath.Join(child.Env["CODEX_ELECTRON_USER_DATA_PATH"], "SingletonLock"))
			if err != nil {
				t.Fatal(err)
			}
			separator := strings.LastIndex(lock, "-")
			if separator < 0 {
				t.Fatal("missing native profile owner")
			}
			nativePID := lock[separator+1:]
			if strconv.Itoa(observed.PID) != string(pid) || strconv.Itoa(observed.Parent) != nativePID {
				t.Fatalf("bundled engine must replace Desktop child and retain native parent: engine=%d launched=%s parent=%d native=%s", observed.PID, pid, observed.Parent, nativePID)
			}
			return
		}
		if time.Now().After(deadline) {
			t.Fatal("engine ancestry was not observed")
		}
		time.Sleep(10 * time.Millisecond)
	}
}
