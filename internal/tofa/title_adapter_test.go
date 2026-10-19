package tofa_test

import (
	"encoding/json"
	"io"
	"net/http"
	"os"
	"reflect"
	"strings"
	"testing"
)

func desktopTitleFixture(t *testing.T) []byte {
	t.Helper()
	body, err := os.ReadFile("testdata/desktop-title-request.json")
	if err != nil {
		t.Fatal(err)
	}
	return body
}

func TestCLIDoesNotRouteNativeDesktopTitle(t *testing.T) {
	for _, fixture := range []string{"testdata/desktop-native-title-request.json", "testdata/desktop-luna6-title-request.json"} {
		t.Run(fixture, func(t *testing.T) {
			body, err := os.ReadFile(fixture)
			if err != nil {
				t.Fatal(err)
			}
			app, output := adapterFixture(t, func(w http.ResponseWriter, r *http.Request) {
				got, err := io.ReadAll(r.Body)
				if err != nil || !reflect.DeepEqual(jsonValue(t, got), jsonValue(t, body)) {
					t.Error("desktop title policy changed a CLI request")
				}
			}, func(endpoint, token string) error {
				response := adapterRequest(t, endpoint, token, string(body))
				if response.StatusCode != 200 {
					t.Error(response.Status)
				}
				return nil
			})
			runAdapted(t, app)
			if strings.Contains(output.String(), "Automatic title routing:") || strings.Contains(output.String(), "Automatic-title context") {
				t.Fatal("CLI announced a desktop-only route")
			}
		})
	}
}

func TestAdapterPreservesDesktopTitleContract(t *testing.T) {
	body := desktopTitleFixture(t)
	want := jsonValue(t, body).(map[string]any)
	format := want["text"].(map[string]any)["format"].(map[string]any)
	schema, _ := json.Marshal(format["schema"])
	delete(want["text"].(map[string]any), "format")
	instructions := want["instructions"].(string)
	responseBody := `{"title":"Explain Python addition","description":"How a tiny Python calculator adds two numbers"}`
	calls := 0
	app, output := adapterFixture(t, func(w http.ResponseWriter, r *http.Request) {
		calls++
		raw, _ := io.ReadAll(r.Body)
		got := jsonValue(t, raw).(map[string]any)
		guidance, _ := got["instructions"].(string)
		if !strings.HasPrefix(guidance, instructions+"\n") || !strings.Contains(guidance, string(schema)) || !strings.Contains(guidance, "final") {
			t.Error("original instructions and complete final-answer schema must be preserved")
		}
		got["instructions"] = instructions
		if !reflect.DeepEqual(got, want) {
			t.Error("title adaptation changed tools, metadata, input, model, or other generation settings")
		}
		io.WriteString(w, responseBody)
	}, func(endpoint, token string) error {
		for range 2 {
			response := adapterRequest(t, endpoint, token, string(body))
			raw, _ := io.ReadAll(response.Body)
			response.Body.Close()
			if response.StatusCode != 200 || string(raw) != responseBody {
				t.Errorf("title response changed: %s %s", response.Status, raw)
			}
		}
		return nil
	})
	runAdapted(t, app)
	if calls != 2 || strings.Count(output.String(), "desktop title schema") != 1 {
		t.Errorf("title adaptation must be announced once: calls=%d output=%s", calls, output)
	}
}

func TestAdapterRejectsUnrecognizedDesktopTitleVariants(t *testing.T) {
	for name, change := range map[string]func(map[string]any){
		"non-strict schema":       func(p map[string]any) { titleFormat(p)["strict"] = false },
		"missing strict":          func(p map[string]any) { delete(titleFormat(p), "strict") },
		"extra format constraint": func(p map[string]any) { titleFormat(p)["future"] = true },
		"different schema name":   func(p map[string]any) { titleFormat(p)["name"] = "other" },
		"different format":        func(p map[string]any) { titleFormat(p)["type"] = "text" },
		"different schema":        func(p map[string]any) { titleFormat(p)["schema"].(map[string]any)["required"] = []string{"title"} },
		"missing text":            func(p map[string]any) { delete(p, "text") },
		"missing instructions":    func(p map[string]any) { delete(p, "instructions") },
		"forced tool":             func(p map[string]any) { p["tool_choice"] = "required" },
		"disabled tools":          func(p map[string]any) { p["tool_choice"] = "none" },
		"empty tools":             func(p map[string]any) { p["tools"] = []any{} },
		"extra tool": func(p map[string]any) {
			p["tools"] = append(p["tools"].([]any), map[string]any{"type": "function", "name": "unknown"})
		},
		"renamed tool":      func(p map[string]any) { p["tools"].([]any)[0].(map[string]any)["name"] = "other" },
		"duplicate tool":    func(p map[string]any) { p["tools"].([]any)[1] = p["tools"].([]any)[0] },
		"changed tool type": func(p map[string]any) { p["tools"].([]any)[0].(map[string]any)["type"] = "custom" },
		"changed namespace": func(p map[string]any) { p["tools"].([]any)[7].(map[string]any)["name"] = "mcp__other" },
		"changed namespace member": func(p map[string]any) {
			p["tools"].([]any)[7].(map[string]any)["tools"].([]any)[0].(map[string]any)["name"] = "other"
		},
		"malformed tools":     func(p map[string]any) { p["tools"] = []any{"exec_command"} },
		"missing source":      func(p map[string]any) { delete(p, "client_metadata") },
		"malformed source":    func(p map[string]any) { p["client_metadata"] = map[string]any{"x-codex-turn-metadata": "invalid"} },
		"unrelated auxiliary": func(p map[string]any) { titleSource(t, p, "thread_summary", "thread_summary") },
		"main turn":           func(p map[string]any) { titleSource(t, p, "user", "composer") },
		"mismatched trigger":  func(p map[string]any) { titleSource(t, p, "thread_title", "composer") },
	} {
		t.Run(name, func(t *testing.T) {
			p := jsonValue(t, desktopTitleFixture(t)).(map[string]any)
			change(p)
			body, _ := json.Marshal(p)
			app, _ := adapterFixture(t, func(http.ResponseWriter, *http.Request) { t.Error("unsupported title reached upstream") }, func(endpoint, token string) error {
				response := adapterRequest(t, endpoint, token, string(body))
				raw, _ := io.ReadAll(response.Body)
				if response.StatusCode != 400 || !strings.Contains(string(raw), "request was not sent upstream") {
					t.Errorf("missing explicit local rejection: %s %s", response.Status, raw)
				}
				return nil
			})
			runAdapted(t, app)
		})
	}
}

func titleFormat(p map[string]any) map[string]any {
	return p["text"].(map[string]any)["format"].(map[string]any)
}

func titleSource(t *testing.T, p map[string]any, source, trigger string) {
	t.Helper()
	metadata := p["client_metadata"].(map[string]any)
	turn := jsonValue(t, []byte(metadata["x-codex-turn-metadata"].(string))).(map[string]any)
	turn["thread_source"], turn["turn_trigger"] = source, trigger
	raw, _ := json.Marshal(turn)
	metadata["x-codex-turn-metadata"] = string(raw)
}

func TestAdapterPreservesDesktopTitleResponsesAndFailures(t *testing.T) {
	for _, test := range []struct {
		name, response string
		status         int
	}{
		{"stream", "event: response.output_text.delta\ndata: {\"type\":\"response.output_text.delta\",\"delta\":\"{\\\"title\\\":\\\"Python addition\\\",\\\"description\\\":\\\"Explain addition\\\"}\"}\n\nevent: response.completed\ndata: {\"type\":\"response.completed\"}\n\n", 200},
		{"malformed JSON", `not JSON`, 200},
		{"missing description", `{"title":"Python addition"}`, 200},
		{"empty title", `{"title":"","description":"Addition"}`, 200},
		{"wrong type", `{"title":123,"description":"Addition"}`, 200},
		{"too long", `{"title":"This title exceeds thirty six characters","description":"Addition"}`, 200},
		{"failed stream", "event: response.failed\ndata: {\"type\":\"response.failed\",\"response\":{\"error\":{\"message\":\"fixture failure\"}}}\n\n", 200},
		{"upstream bad request", `{"error":{"message":"fixture bad request"}}`, 400},
		{"rate limit", `{"error":{"message":"fixture rate limit"}}`, 429},
		{"upstream unavailable", `{"error":{"message":"fixture unavailable"}}`, 503},
	} {
		t.Run(test.name, func(t *testing.T) {
			calls := 0
			app, _ := adapterFixture(t, func(w http.ResponseWriter, r *http.Request) {
				calls++
				w.Header().Set("Content-Type", "text/event-stream")
				w.WriteHeader(test.status)
				io.WriteString(w, test.response)
			}, func(endpoint, token string) error {
				response := adapterRequest(t, endpoint, token, string(desktopTitleFixture(t)))
				raw, _ := io.ReadAll(response.Body)
				if response.StatusCode != test.status || string(raw) != test.response {
					t.Errorf("desktop must receive the original response for validation: %s %s", response.Status, raw)
				}
				return nil
			})
			runAdapted(t, app)
			if calls != 1 {
				t.Errorf("unexpected retry: %d upstream calls", calls)
			}
		})
	}
}

func TestAdapterLeavesOtherModelsTitleRequestsUnchanged(t *testing.T) {
	p := jsonValue(t, desktopTitleFixture(t)).(map[string]any)
	p["model"] = "another/model"
	body, _ := json.Marshal(p)
	app, output := adapterFixture(t, func(w http.ResponseWriter, r *http.Request) {
		got, _ := io.ReadAll(r.Body)
		if string(got) != string(body) {
			t.Error("other model's title contract changed")
		}
	}, func(endpoint, token string) error {
		response := adapterRequest(t, endpoint, token, string(body))
		if response.StatusCode != 200 {
			t.Error(response.Status)
		}
		return nil
	})
	runAdapted(t, app)
	if strings.Contains(output.String(), "desktop title schema") {
		t.Error("announced unused adaptation")
	}
}
