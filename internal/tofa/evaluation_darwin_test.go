package tofa_test

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"net/http/httputil"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"

	"github.com/kreuzhofer/tofa-launcher/internal/tofa"
)

func TestDesktopEvaluationPreflightDoesNotLaunchOrWriteConfiguration(t *testing.T) {
	bundle, capture := desktopFixture(t, "ignore")
	app := &tofa.App{Dir: t.TempDir(), Out: io.Discard}
	if err := app.RunContext(context.Background(), []string{"evaluation-protocol", "--app-bundle", bundle}); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(capture); !os.IsNotExist(err) {
		t.Fatal("preflight launched a desktop")
	}
	entries, err := os.ReadDir(app.Dir)
	if err != nil || len(entries) != 0 {
		t.Fatal("preflight changed launcher configuration")
	}
}

func TestDesktopEvaluationRetainsNamingAndOwnershipChecks(t *testing.T) {
	bundle, capture := desktopFixture(t, "ignore")
	var lock sync.Mutex
	var upstream string
	observer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/register" {
			var registration map[string]string
			json.NewDecoder(r.Body).Decode(&registration)
			lock.Lock()
			upstream = registration["endpoint"]
			lock.Unlock()
			io.WriteString(w, `{"ready":true}`)
			return
		}
		lock.Lock()
		endpoint, _ := url.Parse(upstream)
		lock.Unlock()
		httputil.NewSingleHostReverseProxy(endpoint).ServeHTTP(w, r)
	}))
	defer observer.Close()
	config := filepath.Join(t.TempDir(), "observer.json")
	data, _ := json.Marshal(map[string]any{"version": 1, "endpoint": observer.URL,
		"secret": "synthetic-control-secret", "seconds": 180})
	os.WriteFile(config, data, 0600)
	app, _ := adapterFixture(t, func(w http.ResponseWriter, r *http.Request) {
		var body map[string]any
		json.NewDecoder(r.Body).Decode(&body)
		if body["model"] != "nvidia/Nemotron-3_5-Lightning" {
			t.Error("evaluation changed independent naming")
		}
		io.WriteString(w, `{"title":"Synthetic title","description":"Synthetic task"}`)
	}, nil)
	child, stop := liveDesktopFixture(t, app, bundle, capture, "--model", "zai-org/GLM-5.3", "--evaluation-observer", config)
	defer stop()
	if child.Env["TOFA_DESKTOP_CONTEXT"] != observer.URL {
		t.Fatal("desktop bypassed evaluator")
	}
	body, _ := os.ReadFile("testdata/desktop-luna6-title-request.json")
	response := adapterRequest(t, observer.URL, child.Env["TOFA_API_KEY"], string(body))
	raw, _ := io.ReadAll(response.Body)
	response.Body.Close()
	if response.StatusCode != 200 || !strings.Contains(string(raw), "Synthetic title") {
		t.Fatal("naming did not reach native adapter")
	}
	// The regular desktop fixture verifies native singleton/bridge ownership;
	// the observer cannot bypass its authenticated launch handshake.
	request, _ := http.NewRequest(http.MethodPost, observer.URL+"/evaluation-stop", nil)
	request.Header.Set("Authorization", "Bearer unrelated-launch-token")
	denied, err := http.DefaultClient.Do(request)
	if err != nil {
		t.Fatal(err)
	}
	denied.Body.Close()
	if denied.StatusCode != 401 {
		t.Fatal("another launch can stop this experiment")
	}
}
