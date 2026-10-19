package tofa_test

import (
	"encoding/json"
	"net/http"
	"strings"
	"testing"
)

// Reuse the same ownership/fault boundaries for legacy and native-account
// routes. The fake Desktop is test-owned; this does not qualify native UI.
func fixtureDesktopLifecycle(t *testing.T, native bool, mode string) (string, string) {
	t.Helper()
	if native {
		return nativeCandidateFixture(t, mode)
	}
	return desktopFixture(t, mode)
}

func desktopLifecycleSelection(t *testing.T, native bool) []string {
	t.Helper()
	if native {
		return []string{"--native-account-candidate", "--evaluation-observer", candidateProxyObserver(t)}
	}
	return nil
}

func desktopLifecycleInference(t *testing.T, child capturedDesktop) string {
	t.Helper()
	req, _ := http.NewRequest("GET", child.Env["TOFA_DESKTOP_CONTEXT"]+"/desktop-launch", nil)
	req.Header.Set("Authorization", "Bearer "+child.Env["TOFA_API_KEY"])
	res, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	defer res.Body.Close()
	var route struct{ InferenceCapability string }
	if err := json.NewDecoder(res.Body).Decode(&route); err != nil || route.InferenceCapability == "" {
		t.Fatal("missing fixture inference capability")
	}
	return route.InferenceCapability
}

func assertDesktopLifecycleCapabilityRejected(t *testing.T, endpoint, capability string, control bool, exactStatus ...int) {
	t.Helper()
	path, method, body := "/responses", "POST", `{"model":"moonshotai/Kimi-K3","input":[]}`
	if control {
		path, method, body = "/desktop-launch", "GET", ""
	}
	req, _ := http.NewRequest(method, endpoint+path, strings.NewReader(body))
	if control {
		req.Header.Set("Authorization", "Bearer "+capability)
	} else {
		req.Header.Set("X-TOFA-Launch", capability)
	}
	res, err := http.DefaultClient.Do(req)
	if err != nil {
		if len(exactStatus) > 0 {
			t.Fatalf("fresh route unavailable during stale authorization check: %v", err)
		}
		return
	}
	defer res.Body.Close()
	if res.StatusCode < 400 || (len(exactStatus) > 0 && res.StatusCode != exactStatus[0]) {
		t.Fatalf("expired %s capability accepted: %d", method, res.StatusCode)
	}
}
