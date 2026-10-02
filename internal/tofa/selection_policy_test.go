package tofa

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"runtime"
	"strings"
	"testing"
)

func TestLaunchSupportRespectsVerifiedPlatform(t *testing.T) {
	original := verificationSnapshot
	t.Cleanup(func() { verificationSnapshot = original })
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte(`{"data":[{"id":"moonshotai/Kimi-K3"},{"id":"zai-org/GLM-5.3-Flash"}]}`))
	}))
	defer server.Close()
	for _, test := range []struct {
		name, platform   string
		allow, supported bool
	}{
		{"verified platform", runtime.GOOS + "/" + runtime.GOARCH, false, true},
		{"unverified platform", "unverified/architecture", false, false},
		{"explicit experimental opt-in", "unverified/architecture", true, false},
	} {
		t.Run(test.name, func(t *testing.T) {
			verificationSnapshot = []byte(`{"records":[{"target":"codex","route":"adapted","main":"moonshotai/Kimi-K3","guardian":"zai-org/GLM-5.3-Flash","status":"supported","evidence":"test-only synthetic verification","platforms":["` + test.platform + `"]}]}`)
			dir := t.TempDir()
			if err := (&Store{Dir: dir}).Login("test-project", "synthetic-key", "file"); err != nil {
				t.Fatal(err)
			}
			var output bytes.Buffer
			launched := false
			app := App{Dir: dir, Endpoint: server.URL, Out: &output, RunClient: func([]string, []string) error { launched = true; return nil }}
			args := []string{"launch", "codex", "--model", "moonshotai/Kimi-K3"}
			if test.allow {
				args = append(args, "--allow-unverified")
			}
			err := app.Run(args)
			if test.supported || test.allow {
				want := "Status: supported"
				if !test.supported {
					want = "Status: experimental"
				}
				if err != nil || !launched || !strings.Contains(output.String(), want) {
					t.Fatalf("launch=%v err=%v output=%s", launched, err, &output)
				}
			} else if err == nil || launched || !strings.Contains(err.Error(), "--allow-unverified") {
				t.Fatalf("unverified platform launched=%v err=%v", launched, err)
			}
		})
	}
}

// Synthetic promotion evidence stays in tests. Exercise policy through App.Run,
// including availability, metadata, resulting launch and the visible status.
func TestLaunchSupportUsesExactRecordedCombination(t *testing.T) {
	original := verificationSnapshot
	t.Cleanup(func() { verificationSnapshot = original })
	verificationSnapshot = []byte(`{"records":[{"target":"codex","route":"adapted","main":"moonshotai/Kimi-K3","guardian":"zai-org/GLM-5.3-Flash","status":"supported","evidence":"test-only synthetic verification"}]}`)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte(`{"data":[{"id":"moonshotai/Kimi-K3"},{"id":"zai-org/GLM-5.3-Flash"},{"id":"deepseek-ai/DeepSeek-V4.1-Flash"}]}`))
	}))
	defer server.Close()
	for _, test := range []struct {
		name  string
		flags []string
		want  string
	}{
		{name: "verified pair", want: "Status: supported"},
		{name: "different main", flags: []string{"--model", "deepseek-ai/DeepSeek-V4.1-Flash"}, want: "--allow-unverified"},
		{name: "different Guardian", flags: []string{"--guardian-model", "moonshotai/Kimi-K3"}, want: "--allow-unverified"},
		{name: "different route", flags: []string{"--direct"}, want: "--allow-unverified"},
		{name: "explicit opt-in", flags: []string{"--guardian-model", "moonshotai/Kimi-K3", "--allow-unverified"}, want: "Status: experimental"},
	} {
		t.Run(test.name, func(t *testing.T) {
			dir := t.TempDir()
			store := Store{Dir: dir}
			if err := store.Login("test-project", "synthetic-key", "file"); err != nil {
				t.Fatal(err)
			}
			var output bytes.Buffer
			launched := false
			app := App{Dir: dir, Out: &output, Endpoint: server.URL, RunClient: func([]string, []string) error { launched = true; return nil }}
			args := append([]string{"launch", "codex", "--model", "moonshotai/Kimi-K3"}, test.flags...)
			err := app.Run(args)
			if strings.HasPrefix(test.want, "Status:") {
				if err != nil || !launched || !strings.Contains(output.String(), test.want) {
					t.Fatalf("launch=%v err=%v output=%s", launched, err, &output)
				}
			} else if err == nil || launched || !strings.Contains(err.Error(), test.want) {
				t.Fatalf("launch=%v err=%v", launched, err)
			}
		})
	}
}

func TestLaunchRejectsIncompatibleRoleMetadataEvenWithOptIn(t *testing.T) {
	original := candidateSnapshot
	t.Cleanup(func() { candidateSnapshot = original })
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte(`{"data":[{"id":"moonshotai/Kimi-K3"},{"id":"zai-org/GLM-5.3-Flash"}]}`))
	}))
	defer server.Close()
	for _, role := range []string{"main", "Guardian"} {
		for _, field := range []string{"context_window", "input_modalities", "responses_api", "function_calling"} {
			t.Run(role+"/"+field, func(t *testing.T) {
				var snapshot map[string]any
				if err := json.Unmarshal(original, &snapshot); err != nil {
					t.Fatal(err)
				}
				identity := "moonshotai/Kimi-K3"
				if role == "Guardian" {
					identity = "zai-org/GLM-5.3-Flash"
				}
				metadata := snapshot["models"].(map[string]any)[identity].(map[string]any)
				switch field {
				case "context_window":
					metadata[field] = 4096
				case "input_modalities":
					metadata[field] = []string{"audio"}
				default:
					metadata[field] = false
				}
				candidateSnapshot, _ = json.Marshal(snapshot)
				dir := t.TempDir()
				store := Store{Dir: dir}
				if err := store.Login("test-project", "synthetic-key", "file"); err != nil {
					t.Fatal(err)
				}
				var output bytes.Buffer
				app := App{Dir: dir, Out: &output, Endpoint: server.URL, RunClient: func([]string, []string) error { t.Fatal("incompatible model launched"); return nil }}
				err := app.Run([]string{"launch", "codex", "--model", "moonshotai/Kimi-K3", "--allow-unverified"})
				if err == nil || !strings.Contains(err.Error(), role+" model "+identity+": incompatible") {
					t.Fatalf("missing role-specific incompatibility: %v", err)
				}
			})
		}
	}
}
