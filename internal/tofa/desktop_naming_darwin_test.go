package tofa_test

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

func TestDesktopNamesWithIndependentLightningAcrossMains(t *testing.T) {
	for _, main := range []string{"zai-org/GLM-5.3", "deepseek-ai/DeepSeek-V4.1-Flash", "moonshotai/Kimi-K3", "zai-org/GLM-5.3-Flash", "nvidia/Nemotron-3-Ultra-550b-a55b"} {
		t.Run(main, func(t *testing.T) {
			bundle, capture := desktopFixture(t, "ignore")
			var calls atomic.Int32
			const title = `{"title":"Explain integer addition","description":"How adding integers produces a sum"}`
			app, output := adapterFixture(t, func(w http.ResponseWriter, r *http.Request) {
				body, err := io.ReadAll(r.Body)
				if err != nil {
					t.Error(err)
				}
				request := jsonValue(t, body).(map[string]any)
				if request["model"] != "nvidia/Nemotron-3_5-Lightning" {
					t.Errorf("naming reached %v instead of the fixed Lightning model", request["model"])
				}
				calls.Add(1)
				io.WriteString(w, title)
			}, nil)
			child, stop := liveDesktopFixture(t, app, bundle, capture, "--model", main)
			body, err := os.ReadFile("testdata/desktop-luna6-title-request.json")
			if err != nil {
				t.Fatal(err)
			}
			response := adapterRequest(t, child.Env["TOFA_DESKTOP_CONTEXT"], child.Env["TOFA_API_KEY"], string(body))
			got, err := io.ReadAll(response.Body)
			response.Body.Close()
			stop()
			if err != nil || response.StatusCode != http.StatusOK || string(got) != title || calls.Load() != 1 {
				t.Fatalf("GLM desktop naming failed: status=%d calls=%d response=%s error=%v", response.StatusCode, calls.Load(), got, err)
			}
			if !strings.Contains(output.String(), "Naming: nvidia/Nemotron-3_5-Lightning") {
				t.Fatal("independent naming model was not announced")
			}
		})
	}
}

func TestDesktopNamingCompletesWhileMainStreams(t *testing.T) {
	bundle, capture := desktopFixture(t, "ignore")
	mainCancelled := make(chan struct{})
	app, _ := adapterFixture(t, func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		model := jsonValue(t, body).(map[string]any)["model"]
		if model == "zai-org/GLM-5.3" {
			w.Header().Set("Content-Type", "text/event-stream")
			io.WriteString(w, ": main still running\n\n")
			w.(http.Flusher).Flush()
			<-r.Context().Done()
			close(mainCancelled)
			return
		}
		if model != "nvidia/Nemotron-3_5-Lightning" {
			t.Errorf("unexpected model %v", model)
		}
		io.WriteString(w, `{"title":"Independent title","description":"Naming while the main conversation is still running"}`)
	}, nil)
	child, stop := liveDesktopFixture(t, app, bundle, capture, "--model", "zai-org/GLM-5.3")
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	request, _ := http.NewRequestWithContext(ctx, http.MethodPost, child.Env["TOFA_DESKTOP_CONTEXT"]+"/responses", strings.NewReader(`{"model":"zai-org/GLM-5.3","input":[]}`))
	request.Header.Set("Authorization", "Bearer "+child.Env["TOFA_API_KEY"])
	request.Header.Set("Content-Type", "application/json")
	main, err := (&http.Client{Timeout: 5 * time.Second}).Do(request)
	if err != nil {
		t.Fatal(err)
	}
	defer main.Body.Close()
	body, _ := os.ReadFile("testdata/desktop-luna6-title-request.json")
	title := adapterRequest(t, child.Env["TOFA_DESKTOP_CONTEXT"], child.Env["TOFA_API_KEY"], string(body))
	data, err := io.ReadAll(title.Body)
	title.Body.Close()
	if err != nil || title.StatusCode != http.StatusOK || !strings.Contains(string(data), "Independent title") {
		t.Fatalf("naming waited for main: %s %v", data, err)
	}
	cancel()
	select {
	case <-mainCancelled:
	case <-time.After(2 * time.Second):
		t.Fatal("main cancellation did not reach upstream")
	}
	stop()
}

func TestDesktopNamingDeadlineCancelsUpstream(t *testing.T) {
	bundle, capture := desktopFixture(t, "ignore")
	cancelled := make(chan struct{})
	var calls atomic.Int32
	app, _ := adapterFixture(t, func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		if jsonValue(t, body).(map[string]any)["model"] != "nvidia/Nemotron-3_5-Lightning" {
			t.Error("deadline used another model")
		}
		calls.Add(1)
		w.Header().Set("Content-Type", "text/event-stream")
		io.WriteString(w, ": naming still running\n\n")
		w.(http.Flusher).Flush()
		<-r.Context().Done()
		close(cancelled)
	}, nil)
	child, stop := liveDesktopFixture(t, app, bundle, capture, "--model", "zai-org/GLM-5.3")
	body, _ := os.ReadFile("testdata/desktop-luna6-title-request.json")
	ctx, cancel := context.WithTimeout(context.Background(), 500*time.Millisecond)
	defer cancel()
	request, _ := http.NewRequestWithContext(ctx, http.MethodPost, child.Env["TOFA_DESKTOP_CONTEXT"]+"/responses", strings.NewReader(string(body)))
	request.Header.Set("Authorization", "Bearer "+child.Env["TOFA_API_KEY"])
	request.Header.Set("Content-Type", "application/json")
	response, err := http.DefaultClient.Do(request)
	if err != nil {
		t.Fatal(err)
	}
	_, err = io.ReadAll(response.Body)
	response.Body.Close()
	if err == nil {
		t.Fatal("timed-out title was reported complete")
	}
	select {
	case <-cancelled:
	case <-time.After(2 * time.Second):
		t.Fatal("naming cancellation did not reach upstream")
	}
	stop()
	if calls.Load() != 1 {
		t.Fatal("naming retried or fell back after deadline")
	}
}

func TestDesktopUnavailableNamingDoesNotFallBackOrBlockMain(t *testing.T) {
	bundle, capture := desktopFixture(t, "ignore")
	var calls atomic.Int32
	app, output := adapterFixture(t, nil, nil)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/models" {
			io.WriteString(w, `{"data":[{"id":"zai-org/GLM-5.3"},{"id":"zai-org/GLM-5.3-Flash"}]}`)
			return
		}
		body, _ := io.ReadAll(r.Body)
		if jsonValue(t, body).(map[string]any)["model"] != "zai-org/GLM-5.3" {
			t.Error("unavailable naming request reached provider or fell back")
		}
		calls.Add(1)
		io.WriteString(w, "main works")
	}))
	defer server.Close()
	app.Endpoint = server.URL
	child, stop := liveDesktopFixture(t, app, bundle, capture, "--model", "zai-org/GLM-5.3")
	body, err := os.ReadFile("testdata/desktop-luna6-title-request.json")
	if err != nil {
		t.Fatal(err)
	}
	response := adapterRequest(t, child.Env["TOFA_DESKTOP_CONTEXT"], child.Env["TOFA_API_KEY"], string(body))
	data, _ := io.ReadAll(response.Body)
	response.Body.Close()
	if response.StatusCode != http.StatusBadRequest || !strings.Contains(string(data), "naming model nvidia/Nemotron-3_5-Lightning is unavailable") {
		t.Errorf("missing explicit naming failure: %d %s", response.StatusCode, data)
	}
	response = adapterRequest(t, child.Env["TOFA_DESKTOP_CONTEXT"], child.Env["TOFA_API_KEY"], `{"model":"zai-org/GLM-5.3","input":[]}`)
	response.Body.Close()
	stop()
	if response.StatusCode != http.StatusOK || calls.Load() != 1 {
		t.Fatalf("main route changed or naming fell back: status=%d calls=%d", response.StatusCode, calls.Load())
	}
	if !strings.Contains(output.String(), "naming model nvidia/Nemotron-3_5-Lightning is unavailable") {
		t.Fatal("naming unavailability was not visible")
	}
}

// Lightning rejects these native fields and namespace tools before generation.
// Keep that observed provider boundary in the public-launcher regression.
func TestDesktopLightningUsesToolFreeStructuredNaming(t *testing.T) {
	bundle, capture := desktopFixture(t, "ignore")
	app, output := adapterFixture(t, func(w http.ResponseWriter, r *http.Request) {
		raw, _ := io.ReadAll(r.Body)
		p := jsonValue(t, raw).(map[string]any)
		for _, field := range []string{"include", "reasoning", "prompt_cache_key", "tools"} {
			if _, found := p[field]; found {
				http.Error(w, "Lightning rejects native naming field: "+field, 400)
				return
			}
		}
		if p["text"].(map[string]any)["format"] == nil {
			t.Error("native title schema removed")
		}
		io.WriteString(w, `{"title":"Python addition","description":"How integers are added"}`)
	}, nil)
	child, stop := liveDesktopFixture(t, app, bundle, capture, "--model", "zai-org/GLM-5.3")
	p := nativeTitleFixture(t)
	p["include"] = []string{"reasoning.encrypted_content"}
	p["prompt_cache_key"] = "synthetic-title-cache"
	raw, _ := json.Marshal(p)
	response := adapterRequest(t, child.Env["TOFA_DESKTOP_CONTEXT"], child.Env["TOFA_API_KEY"], string(raw))
	data, _ := io.ReadAll(response.Body)
	response.Body.Close()
	stop()
	if response.StatusCode != 200 {
		t.Fatalf("Lightning title failed: status=%d body=%s", response.StatusCode, data)
	}
	if !strings.Contains(output.String(), "tool-free; provider-default reasoning; native title schema retained") {
		t.Fatal("naming adaptation not announced")
	}
}
