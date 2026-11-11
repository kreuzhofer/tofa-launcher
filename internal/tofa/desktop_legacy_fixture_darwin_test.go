package tofa_test

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"net/http/httputil"
	"net/url"
	"os"
	"path/filepath"
	"sync"
	"testing"
)

// Explicitly retain the historical v1 evaluation route for the legacy-provider
// regression corpus. Normal native-account coverage uses no observer/proof flags.
func legacyProxyObserver(t *testing.T) string {
	t.Helper()
	var mu sync.Mutex
	var target *url.URL
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/register" {
			var registration struct{ Endpoint, Token string }
			if json.NewDecoder(r.Body).Decode(&registration) != nil || registration.Token == "" {
				http.Error(w, "invalid fixture registration", 400)
				return
			}
			parsed, err := url.Parse(registration.Endpoint)
			if err != nil || parsed.Hostname() != "127.0.0.1" {
				http.Error(w, "invalid fixture target", 400)
				return
			}
			mu.Lock()
			target = parsed
			mu.Unlock()
			w.Write([]byte(`{"ready":true}`))
			return
		}
		mu.Lock()
		upstream := target
		mu.Unlock()
		if upstream == nil {
			http.Error(w, "fixture unregistered", 503)
			return
		}
		httputil.NewSingleHostReverseProxy(upstream).ServeHTTP(w, r)
	}))
	t.Cleanup(server.Close)
	path := filepath.Join(t.TempDir(), "legacy-observer.json")
	raw, err := json.Marshal(map[string]any{"version": 1, "endpoint": server.URL, "secret": "synthetic-legacy-control", "seconds": 900})
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, raw, 0600); err != nil {
		t.Fatal(err)
	}
	return path
}
