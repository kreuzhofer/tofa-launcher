package tofa_test

import (
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"runtime"
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

func TestEvaluationRefusesDirectConnectionBeforeCredentials(t *testing.T) {
	app := &tofa.App{Dir: t.TempDir(), Out: io.Discard}
	err := app.Run([]string{"launch", "codex", "--model", "moonshotai/Kimi-K3", "--direct",
		"--evaluation-observer", "/missing"})
	if err == nil || !strings.Contains(err.Error(), "evaluation requires the adapted connection") {
		t.Fatalf("unexpected error: %v", err)
	}
}
