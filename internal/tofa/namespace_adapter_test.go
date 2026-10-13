package tofa_test

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"testing"
	"time"
)

const namespaceCatalog = `[{"type":"namespace","name":"mcp__codex_app","description":"native tools","tools":[{"type":"function","name":"load_workspace_dependencies","strict":false,"parameters":{"type":"object","properties":{},"additionalProperties":false}}]},{"type":"function","name":"exec_command","parameters":{"type":"object"}}]`

func TestNamespaceAdapterRoundTrip(t *testing.T) {
	for _, model := range []string{"moonshotai/Kimi-K3", "zai-org/GLM-5.3"} {
		for _, stream := range []bool{false, true} {
			t.Run(fmt.Sprintf("%s/stream=%v", model, stream), func(t *testing.T) {
				alias := ""
				round := 0
				app, out := adapterFixture(t, func(w http.ResponseWriter, r *http.Request) {
					round++
					var body map[string]json.RawMessage
					json.NewDecoder(r.Body).Decode(&body)
					var tools []map[string]json.RawMessage
					json.Unmarshal(body["tools"], &tools)
					if len(tools) != 2 || string(tools[0]["type"]) != `"function"` {
						t.Error("namespace definition was not flattened")
						http.Error(w, "namespace tools unavailable", 400)
						return
					}
					var name string
					json.Unmarshal(tools[0]["name"], &name)
					if alias == "" {
						alias = name
					}
					if alias != name || len(name) > 64 || name == "load_workspace_dependencies" {
						t.Error("alias is not stable/bounded/qualified")
					}
					if string(tools[1]["name"]) != `"exec_command"` || string(body["future"]) != "9007199254740993" {
						t.Error("unrelated request fields changed")
					}
					if round == 2 {
						var input []map[string]json.RawMessage
						json.Unmarshal(body["input"], &input)
						if string(input[0]["name"]) != fmt.Sprintf("%q", alias) || input[0]["namespace"] != nil || string(input[0]["call_id"]) != `"call1"` || string(input[1]["output"]) != `"native-result"` {
							t.Error("history call/result was not preserved")
						}
					}
					item := fmt.Sprintf(`{"type":"function_call","id":"fc1","call_id":"call1","name":%q,"arguments":"{}","status":"completed","future":9007199254740993}`, alias)
					if stream {
						w.Header().Set("Content-Type", "text/event-stream")
						for _, event := range []string{"response.output_item.added", "response.output_item.done"} {
							fmt.Fprintf(w, "event: %s\ndata: {\"type\":%q,\"item\":%s}\n\n", event, event, item)
							w.(http.Flusher).Flush()
						}
						fmt.Fprintf(w, "data: {\"type\":\"response.function_call_arguments.done\",\"name\":%q,\"arguments\":\"{}\",\"item_id\":\"fc1\"}\n\n", alias)
						fmt.Fprintf(w, "event: response.completed\ndata: {\"type\":\"response.completed\",\"response\":{\"status\":\"completed\",\"output\":[%s]}}\n\n", item)
					} else {
						w.Header().Set("Content-Type", "application/json")
						fmt.Fprintf(w, `{"output":[%s]}`, item)
					}
				}, func(endpoint, token string) error {
					input := `[]`
					for i := 0; i < 2; i++ {
						body := fmt.Sprintf(`{"model":%q,"tools":%s,"input":%s,"stream":%v,"future":9007199254740993}`, model, namespaceCatalog, input, stream)
						response := adapterRequest(t, endpoint, token, body)
						raw, err := io.ReadAll(response.Body)
						if err != nil || response.StatusCode != 200 {
							t.Fatalf("response failed: %d %v %s", response.StatusCode, err, raw)
						}
						count := 1
						if stream {
							count = 4
						}
						if strings.Count(string(raw), `"namespace":"mcp__codex_app"`) != count || strings.Contains(string(raw), alias) || strings.Count(string(raw), `"name":"load_workspace_dependencies"`) != count || !strings.Contains(string(raw), "9007199254740993") {
							t.Fatalf("native call not restored: %s", raw)
						}
						input = `[{"type":"function_call","namespace":"mcp__codex_app","name":"load_workspace_dependencies","call_id":"call1","arguments":"{}"},{"type":"function_call_output","call_id":"call1","output":"native-result"}]`
					}
					return nil
				})
				runAdapted(t, app)
				if round != 2 {
					t.Fatal("follow-up not exercised")
				}
				if !strings.Contains(out.String(), "namespace") {
					t.Fatal("adaptation was not observable")
				}
			})
		}
	}
}

func TestNamespaceAdapterRejectsUnsupportedCatalogsBeforeUpstream(t *testing.T) {
	cases := []string{
		strings.Replace(namespaceCatalog, `"name":"exec_command"`, `"name":"tofa_ns_reserved"`, 1),
		strings.Replace(namespaceCatalog, `"name":"load_workspace_dependencies"`, `"name":""`, 1),
		strings.Replace(namespaceCatalog, `"type":"function"`, `"type":"custom"`, 1),
		strings.Replace(namespaceCatalog, `"description":"native tools"`, `"unexpected":true`, 1),
		strings.Replace(namespaceCatalog, `"name":"exec_command"`, `"name":"exec_command","type":"web_search"`, 1),
	}
	for i, tools := range cases {
		t.Run(fmt.Sprint(i), func(t *testing.T) {
			app, _ := adapterFixture(t, func(http.ResponseWriter, *http.Request) { t.Error("unsafe catalog reached provider") }, func(endpoint, token string) error {
				response := adapterRequest(t, endpoint, token, `{"model":"moonshotai/Kimi-K3","input":[],"tools":`+tools+`}`)
				if response.StatusCode != 400 {
					t.Fatalf("got status %d", response.StatusCode)
				}
				return nil
			})
			runAdapted(t, app)
		})
	}
}

func TestNamespaceAdapterRejectsUnmappedProviderCalls(t *testing.T) {
	for _, stream := range []bool{false, true} {
		t.Run(fmt.Sprint(stream), func(t *testing.T) {
			app, _ := adapterFixture(t, func(w http.ResponseWriter, r *http.Request) {
				if stream {
					w.Header().Set("Content-Type", "text/event-stream")
					io.WriteString(w, "data: {\"type\":\"response.output_item.done\",\"item\":{\"type\":\"function_call\",\"name\":\"unmapped_unsafe\",\"arguments\":\"{}\"}}\n\n")
				} else {
					w.Header().Set("Content-Type", "application/json")
					io.WriteString(w, `{"output":[{"type":"function_call","name":"unmapped_unsafe","arguments":"{}"}]}`)
				}
			}, func(endpoint, token string) error {
				response := adapterRequest(t, endpoint, token, `{"model":"moonshotai/Kimi-K3","input":[],"tools":`+namespaceCatalog+`}`)
				data, err := io.ReadAll(response.Body)
				if strings.Contains(string(data), "unmapped_unsafe") {
					t.Fatal("unmapped call leaked to native client")
				}
				if stream {
					if err == nil && !strings.Contains(string(data), "namespace_translation_failed") {
						t.Fatal("stream failed silently")
					}
				} else if response.StatusCode != 502 {
					t.Fatal("invalid JSON response accepted")
				}
				return nil
			})
			runAdapted(t, app)
		})
	}
}

func TestNamespaceAdapterStreamsBeforeCompletionAndCancels(t *testing.T) {
	cancelled := make(chan struct{})
	app, _ := adapterFixture(t, func(w http.ResponseWriter, r *http.Request) {
		var body struct{ Tools []struct{ Name string } }
		json.NewDecoder(r.Body).Decode(&body)
		w.Header().Set("Content-Type", "text/event-stream")
		fmt.Fprintf(w, "data: {\"type\":\"response.output_item.added\",\"item\":{\"type\":\"function_call\",\"name\":%q,\"call_id\":\"one\",\"arguments\":\"\"}}\n\n", body.Tools[0].Name)
		w.(http.Flusher).Flush()
		<-r.Context().Done()
		close(cancelled)
	}, func(endpoint, token string) error {
		ctx, cancel := context.WithCancel(context.Background())
		defer cancel()
		req, _ := http.NewRequestWithContext(ctx, "POST", endpoint+"/responses", strings.NewReader(`{"model":"moonshotai/Kimi-K3","input":[],"tools":`+namespaceCatalog+`}`))
		req.Header.Set("Authorization", "Bearer "+token)
		response, err := (&http.Client{Timeout: 3 * time.Second}).Do(req)
		if err != nil {
			t.Fatal(err)
		}
		defer response.Body.Close()
		buffer := make([]byte, 4096)
		n, err := response.Body.Read(buffer)
		if err != nil || !strings.Contains(string(buffer[:n]), `"namespace":"mcp__codex_app"`) {
			t.Fatalf("first event buffered or unmapped: %v %s", err, buffer[:n])
		}
		cancel()
		select {
		case <-cancelled:
		case <-time.After(3 * time.Second):
			t.Fatal("upstream remained active")
		}
		return nil
	})
	runAdapted(t, app)
}
