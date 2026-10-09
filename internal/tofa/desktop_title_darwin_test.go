package tofa_test

import (
	"encoding/json"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"
)

func nativeTitleFixture(t *testing.T) map[string]any {
	t.Helper()
	body, err := os.ReadFile("testdata/desktop-native-title-request.json")
	if err != nil {
		t.Fatal(err)
	}
	return jsonValue(t, body).(map[string]any)
}

func TestDesktopPreservesRoutedTitleContractAndFailures(t *testing.T) {
	for _, fixture := range []string{"desktop-native-title-request.json", "desktop-luna6-title-request.json"} {
		t.Run(fixture, func(t *testing.T) {
			for _, tc := range []struct {
				name, response string
				status         int
			}{
				{"valid title", `{"title":"Explain Python integer addition","description":"Why integer addition produces a sum"}`, 200},
				{"malformed JSON", `not JSON`, 200},
				{"missing description", `{"title":"Python addition"}`, 200},
				{"empty title", `{"title":"","description":"Addition"}`, 200},
				{"wrong title type", `{"title":123,"description":"Addition"}`, 200},
				{"long title", `{"title":"This title is longer than thirty six characters","description":"Addition"}`, 200},
				{"failed stream", "event: response.failed\ndata: {\"type\":\"response.failed\",\"response\":{\"error\":{\"message\":\"fixture failure\"}}}\n\n", 200},
				{"upstream rejection", `{"error":{"message":"fixture bad request"}}`, 400},
				{"rate limit", `{"error":{"message":"fixture rate limit"}}`, 429},
				{"unavailable", `{"error":{"message":"fixture unavailable"}}`, 503},
			} {
				t.Run(tc.name, func(t *testing.T) {
					bundle, capture := desktopFixture(t, "ignore")
					fixtureRaw, err := os.ReadFile(filepath.Join("testdata", fixture))
					if err != nil {
						t.Fatal(err)
					}
					original := jsonValue(t, fixtureRaw).(map[string]any)
					body, err := json.Marshal(original)
					if err != nil {
						t.Fatal(err)
					}
					original["model"] = "nvidia/Nemotron-3_5-Lightning"
					input := original["input"].([]any)
					delete(original, "reasoning")
					delete(original, "include")
					delete(original, "prompt_cache_key")
					original["input"] = input[1:]
					app, _ := adapterFixture(t, func(w http.ResponseWriter, r *http.Request) {
						raw, err := io.ReadAll(r.Body)
						got := jsonValue(t, raw).(map[string]any)
						if err != nil || !reflect.DeepEqual(got, original) {
							t.Error("title adaptation changed prompt, schema, metadata or unrelated settings")
						}
						w.WriteHeader(tc.status)
						io.WriteString(w, tc.response)
					}, nil)
					child, stop := liveDesktopFixture(t, app, bundle, capture)
					response := adapterRequest(t, child.Env["TOFA_DESKTOP_CONTEXT"], child.Env["TOFA_API_KEY"], string(body))
					raw, err := io.ReadAll(response.Body)
					response.Body.Close()
					if err != nil || response.StatusCode != tc.status || string(raw) != tc.response {
						t.Fatalf("title result must reach the client unchanged: %d %s %v", response.StatusCode, raw, err)
					}
					stop()
				})
			}
		})
	}
}

func TestDesktopRejectsChangedNativeTitleContracts(t *testing.T) {
	bundle, capture := desktopFixture(t, "ignore")
	app, _ := adapterFixture(t, func(http.ResponseWriter, *http.Request) {
		t.Error("unrecognized title request reached Token Factory")
	}, nil)
	child, stop := liveDesktopFixture(t, app, bundle, capture)
	for name, change := range map[string]func(map[string]any){
		"missing additional tools":  func(p map[string]any) { p["input"] = p["input"].([]any)[1:] },
		"multiple additional tools": func(p map[string]any) { p["input"] = append(p["input"].([]any), p["input"].([]any)[0]) },
		"changed tool role":         func(p map[string]any) { p["input"].([]any)[0].(map[string]any)["role"] = "user" },
		"new tool item field":       func(p map[string]any) { p["input"].([]any)[0].(map[string]any)["future"] = true },
		"changed namespace": func(p map[string]any) {
			p["input"].([]any)[0].(map[string]any)["tools"].([]any)[0].(map[string]any)["name"] = "other"
		},
		"changed code tool": func(p map[string]any) {
			p["input"].([]any)[0].(map[string]any)["tools"].([]any)[0].(map[string]any)["tools"].([]any)[0].(map[string]any)["name"] = "other"
		},
		"changed code tool type": func(p map[string]any) {
			p["input"].([]any)[0].(map[string]any)["tools"].([]any)[0].(map[string]any)["tools"].([]any)[0].(map[string]any)["type"] = "function"
		},
		"wrong inventory for Luna 6": func(p map[string]any) { p["model"] = "gpt-6-luna" },
		"other native model":         func(p map[string]any) { p["model"] = "gpt-7-luna" },
		"Guardian":                   func(p map[string]any) { p["model"] = "codex-auto-review" },
		"added tools":                func(p map[string]any) { p["tools"] = []any{map[string]any{"type": "function", "name": "exec_command"}} },
		"empty tools":                func(p map[string]any) { p["tools"] = []any{} },
		"null tools":                 func(p map[string]any) { p["tools"] = nil },
		"instructions":               func(p map[string]any) { p["instructions"] = "Different instructions" },
		"missing source":             func(p map[string]any) { delete(p, "client_metadata") },
		"main turn":                  func(p map[string]any) { titleSource(t, p, "user", "composer") },
		"summary":                    func(p map[string]any) { titleSource(t, p, "thread_summary", "thread_summary") },
		"mismatched trigger":         func(p map[string]any) { titleSource(t, p, "thread_title", "composer") },
		"schema":                     func(p map[string]any) { titleFormat(p)["schema"].(map[string]any)["required"] = []string{"title"} },
		"non-strict":                 func(p map[string]any) { titleFormat(p)["strict"] = false },
		"schema name":                func(p map[string]any) { titleFormat(p)["name"] = "other" },
		"format extension":           func(p map[string]any) { titleFormat(p)["future"] = true },
		"forced tool":                func(p map[string]any) { p["tool_choice"] = "required" },
	} {
		t.Run(name, func(t *testing.T) {
			p := nativeTitleFixture(t)
			change(p)
			body, err := json.Marshal(p)
			if err != nil {
				t.Fatal(err)
			}
			response := adapterRequest(t, child.Env["TOFA_DESKTOP_CONTEXT"], child.Env["TOFA_API_KEY"], string(body))
			raw, err := io.ReadAll(response.Body)
			response.Body.Close()
			if err != nil || response.StatusCode != 400 || !strings.Contains(string(raw), "request was not sent upstream") {
				t.Fatalf("missing local rejection: %d %s %v", response.StatusCode, raw, err)
			}
		})
	}
	stop()
}

func TestDesktopTitleFailureRequiresBothSourceMarkers(t *testing.T) {
	bundle, capture := desktopFixture(t, "ignore")
	app, output := adapterFixture(t, func(http.ResponseWriter, *http.Request) {
		t.Error("unsupported model reached Token Factory")
	}, nil)
	child, stop := liveDesktopFixture(t, app, bundle, capture)
	for _, tc := range []struct {
		name, metadata string
		title          bool
	}{
		{"title", `{"thread_source":"thread_title","turn_trigger":"thread_title"}`, true},
		{"source only", `{"thread_source":"thread_title"}`, false},
		{"trigger only", `{"turn_trigger":"thread_title"}`, false},
		{"main turn", `{"thread_source":"user","turn_trigger":"composer"}`, false},
		{"review", `{"thread_source":"guardian","turn_trigger":"guardian"}`, false},
		{"malformed", `not JSON`, false},
	} {
		t.Run(tc.name, func(t *testing.T) {
			body, err := json.Marshal(map[string]any{
				"model": "gpt-5.6-luna", "input": []any{},
				"client_metadata": map[string]string{"x-codex-turn-metadata": tc.metadata},
			})
			if err != nil {
				t.Fatal(err)
			}
			response := adapterRequest(t, child.Env["TOFA_DESKTOP_CONTEXT"], child.Env["TOFA_API_KEY"], string(body))
			raw, err := io.ReadAll(response.Body)
			response.Body.Close()
			if err != nil || response.StatusCode != 400 || !strings.Contains(string(raw), "request was not sent upstream") {
				t.Fatalf("missing explicit local rejection: status=%d body=%s error=%v", response.StatusCode, raw, err)
			}
			if strings.Contains(string(raw), "automatic title generation is unavailable") != tc.title {
				t.Fatalf("incorrect title attribution: %s", raw)
			}
		})
	}
	stop()
	if strings.Count(output.String(), "automatic title generation is unavailable") != 1 {
		t.Fatal("launcher must attribute only the actual title failure")
	}
}

func TestDesktopRejectsChangedLuna6TitleContracts(t *testing.T) {
	bundle, capture := desktopFixture(t, "ignore")
	app, _ := adapterFixture(t, func(http.ResponseWriter, *http.Request) {
		t.Error("unrecognized Luna 6 request reached Token Factory")
	}, nil)
	child, stop := liveDesktopFixture(t, app, bundle, capture)
	for name, change := range map[string]func(map[string]any){
		"other model":                  func(p map[string]any) { p["model"] = "gpt-7-luna" },
		"old model with new inventory": func(p map[string]any) { p["model"] = "gpt-5.6-luna" },
		"main turn":                    func(p map[string]any) { titleSource(t, p, "user", "composer") },
		"mismatched trigger":           func(p map[string]any) { titleSource(t, p, "thread_title", "composer") },
		"changed schema":               func(p map[string]any) { titleFormat(p)["schema"].(map[string]any)["required"] = []string{"title"} },
		"extra namespace": func(p map[string]any) {
			item := p["input"].([]any)[0].(map[string]any)
			item["tools"] = append(item["tools"].([]any), map[string]any{"type": "namespace", "name": "unknown", "tools": []any{}})
		},
		"duplicate namespace": func(p map[string]any) {
			tools := p["input"].([]any)[0].(map[string]any)["tools"].([]any)
			tools[2] = tools[1]
		},
		"unknown collaboration action": func(p map[string]any) {
			tools := p["input"].([]any)[0].(map[string]any)["tools"].([]any)[2].(map[string]any)["tools"].([]any)
			tools[0].(map[string]any)["name"] = "unknown"
		},
		"duplicate collaboration action": func(p map[string]any) {
			tools := p["input"].([]any)[0].(map[string]any)["tools"].([]any)[2].(map[string]any)["tools"].([]any)
			tools[1] = tools[0]
		},
		"changed tool type": func(p map[string]any) {
			tools := p["input"].([]any)[0].(map[string]any)["tools"].([]any)[1].(map[string]any)["tools"].([]any)
			tools[0].(map[string]any)["type"] = "custom"
		},
	} {
		t.Run(name, func(t *testing.T) {
			raw, err := os.ReadFile("testdata/desktop-luna6-title-request.json")
			if err != nil {
				t.Fatal(err)
			}
			p := jsonValue(t, raw).(map[string]any)
			change(p)
			body, err := json.Marshal(p)
			if err != nil {
				t.Fatal(err)
			}
			response := adapterRequest(t, child.Env["TOFA_DESKTOP_CONTEXT"], child.Env["TOFA_API_KEY"], string(body))
			result, err := io.ReadAll(response.Body)
			response.Body.Close()
			if err != nil || response.StatusCode != 400 || !strings.Contains(string(result), "request was not sent upstream") {
				t.Fatalf("missing local rejection: %d %s %v", response.StatusCode, result, err)
			}
		})
	}
	stop()
}

// Replays the title helper's current thread/start and turn/start contract at
// the bundled-engine boundary, retaining the launcher's merged native catalog.
func TestDesktopBundledEngineRoutesAutomaticTitleToLightning(t *testing.T) {
	installed := os.Getenv("TOFA_TEST_DESKTOP_ENGINE")
	if installed == "" {
		t.Skip("set TOFA_TEST_DESKTOP_ENGINE")
	}
	for _, model := range []string{"gpt-5.6-luna", "gpt-6-luna"} {
		t.Run(model, func(t *testing.T) {
			bundle, capture := desktopFixture(t, "ignore")
			engine := filepath.Join(bundle, "Contents/Resources/codex")
			if err := os.Remove(engine); err != nil {
				t.Fatal(err)
			}
			if err := os.Symlink(installed, engine); err != nil {
				t.Fatal(err)
			}
			title := `{"title":"Explain Python integer addition","description":"Why adding two integers produces their sum"}`
			app, output := adapterFixture(t, func(w http.ResponseWriter, r *http.Request) {
				var body map[string]any
				if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
					t.Error(err)
					return
				}
				for _, item := range body["input"].([]any) {
					if item.(map[string]any)["type"] == "additional_tools" {
						http.Error(w, "Unsupported Responses API input item type: additional_tools", 400)
						return
					}
				}
				if body["model"] != "nvidia/Nemotron-3_5-Lightning" || body["tools"] != nil || body["instructions"] != nil || body["text"].(map[string]any)["format"] == nil {
					t.Errorf("current title contract changed: model=%v tools=%v", body["model"], body["tools"])
				}
				emitFixtureResponse(w, fixtureMessage(title))
			}, nil)
			child, stop := liveDesktopFixture(t, app, bundle, capture, "--model", "zai-org/GLM-5.3")
			e := openDesktopEngine(t, child)
			started := e.call("thread/start", map[string]any{
				"model": model, "modelProvider": nil,
				"allowProviderModelFallback": true, "cwd": child.Cwd,
				"approvalPolicy": "never", "permissions": ":read-only",
				"runtimeWorkspaceRoots": []any{}, "ephemeral": true,
				"threadSource": "thread_title",
				"config": map[string]any{
					"features.enable_fanout": false, "features.hooks": false,
					"features.multi_agent": false, "features.multi_agent_v2": false,
					"features.plugins": false, "features.shell_snapshot": false,
					"features.tool_suggest": false, "features.apps": false,
					"mcp_servers.codex_app":  map[string]any{"enabled": false, "command": ""},
					"model_reasoning_effort": "low", "web_search": "disabled",
				},
			})
			if started["model"] != model || started["modelProvider"] != "nebius-tofa" {
				t.Fatalf("title selection contract changed: model=%v provider=%v", started["model"], started["modelProvider"])
			}
			id := started["thread"].(map[string]any)["id"].(string)
			var fixture map[string]any
			if err := json.Unmarshal(desktopTitleFixture(t), &fixture); err != nil {
				t.Fatal(err)
			}
			e.call("turn/start", map[string]any{
				"threadId": id, "turnTrigger": "thread_title", "model": nil,
				"permissions": ":read-only", "runtimeWorkspaceRoots": []any{},
				"input":        []any{map[string]any{"type": "text", "text": "Generate a title and description for explaining Python integer addition.", "text_elements": []any{}}},
				"outputSchema": titleFormat(fixture)["schema"],
			})
			var generated string
			for {
				message := e.read()
				if message["method"] == "item/completed" {
					params := message["params"].(map[string]any)
					item := params["item"].(map[string]any)
					if item["type"] == "agentMessage" {
						generated, _ = item["text"].(string)
					}
				}
				if message["method"] != "turn/completed" {
					continue
				}
				params := message["params"].(map[string]any)
				turn := params["turn"].(map[string]any)
				if params["threadId"] != id || turn["status"] != "completed" {
					t.Fatalf("title request failed: %v", params)
				}
				if generated != title {
					t.Fatalf("generated title response changed: %q", generated)
				}
				break
			}
			e.close()
			stop()
			if !strings.Contains(output.String(), "Naming: nvidia/Nemotron-3_5-Lightning") {
				t.Fatal("title routing not announced in launcher output")
			}
		})
	}
}
