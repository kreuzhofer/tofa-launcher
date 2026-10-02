package tofa_test

import (
	"bytes"
	"github.com/kreuzhofer/tofa-launcher/internal/tofa"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestExplicitUnverifiedLaunchScopesOnlyChild(t *testing.T) {
	v := &vault{values: map[string]string{}}
	dir := t.TempDir()
	s := tofa.Store{Dir: dir, Vault: v}
	if err := s.Login("project-one", "dummy-secret", "keyring"); err != nil {
		t.Fatal(err)
	}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/models" || r.URL.Query().Get("ai_project_id") != "override" || r.Header.Get("Authorization") != "Bearer dummy-secret" {
			t.Errorf("incorrect scoped model discovery")
		}
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(`{"data":[{"id":"moonshotai/Kimi-K3"}]}`))
	}))
	defer server.Close()
	var out bytes.Buffer
	calls := 0
	app := tofa.App{Dir: dir, Vault: v, Out: &out, Endpoint: server.URL, HTTP: server.Client(), RunClient: func(args, env []string) error {
		calls++
		all := strings.Join(args, " ")
		for _, want := range []string{`model="moonshotai/Kimi-K3"`, `model_provider="nebius-tofa"`, `ai_project_id = "override"`, `wire_api = "responses"`} {
			if !strings.Contains(all, want) {
				t.Errorf("missing %s in %s", want, all)
			}
		}
		if strings.Contains(all, "dummy-secret") {
			t.Fatal("key in process arguments")
		}
		if !strings.Contains(strings.Join(env, "\n"), "TOFA_API_KEY=dummy-secret") {
			t.Fatal("key missing from child environment")
		}
		return nil
	}}
	if err := app.Run([]string{"launch", "codex", "--model", "moonshotai/Kimi-K3", "--direct", "--project-id", "override"}); err == nil {
		t.Fatal("unverified model accepted by default")
	}
	if err := app.Run([]string{"launch", "codex", "--model", "moonshotai/Kimi-K3", "--allow-unverified", "--direct", "--project-id", "override", "--", "hello"}); err != nil {
		t.Fatal(err)
	}
	if calls != 1 {
		t.Fatal("incorrect child count")
	}
	if err := app.Run([]string{"launch", "codex", "--model", "moonshotai/Kimi-K3", "--allow-unverified", "--", "-c", "model_provider=evil"}); err == nil {
		t.Fatal("accepted routing override")
	}
	c, _, err := s.Credentials()
	if err != nil || c.ProjectID != "project-one" {
		t.Fatal("project override changed stored preferences")
	}
}
