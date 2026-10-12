package tofa_test

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

func TestInstalledCodexToolAndContinuationThroughAdapter(t *testing.T) {
	clientPath := os.Getenv("TOFA_TEST_CODEX")
	if clientPath == "" {
		t.Skip("set TOFA_TEST_CODEX to run installed Codex against synthetic local responses")
	}
	if !filepath.IsAbs(clientPath) {
		t.Fatal("TOFA_TEST_CODEX must be absolute")
	}
	version, err := exec.Command(clientPath, "--version").Output()
	if err != nil {
		t.Fatal(err)
	}
	t.Log(strings.TrimSpace(string(version)))
	var requests, histories, toolResults atomic.Int32
	upstream := func(writer http.ResponseWriter, request *http.Request) {
		var payload struct {
			Instructions string `json:"instructions"`
			Input        []struct {
				Type    string `json:"type"`
				Role    string `json:"role"`
				Status  string `json:"status"`
				Content []struct {
					Type        string          `json:"type"`
					Text        string          `json:"text"`
					Annotations json.RawMessage `json:"annotations"`
				} `json:"content"`
				Output json.RawMessage `json:"output"`
			} `json:"input"`
			Tools []struct {
				Name string `json:"name"`
			} `json:"tools"`
		}
		if err := json.NewDecoder(request.Body).Decode(&payload); err != nil {
			t.Error(err)
			writer.WriteHeader(400)
			return
		}
		codingInstructions := strings.Contains(payload.Instructions, "You are a coding agent running in the Codex CLI")
		for _, item := range payload.Input {
			if item.Role == "developer" {
				for _, part := range item.Content {
					codingInstructions = codingInstructions || part.Type == "input_text" && strings.Contains(part.Text, "You are a coding agent running in the Codex CLI")
				}
			}
		}
		if !codingInstructions {
			t.Error("default coding instructions missing")
			writer.WriteHeader(400)
			return
		}
		count := requests.Add(1)
		if count > 3 {
			t.Error("unexpected extra client request")
			writer.WriteHeader(500)
			return
		}
		for _, item := range payload.Input {
			if item.Role == "assistant" && item.Type == "message" {
				histories.Add(1)
				if item.Status == "" {
					t.Error("missing assistant status")
					writer.WriteHeader(422)
					return
				}
				for _, part := range item.Content {
					if part.Type == "output_text" && part.Annotations == nil {
						t.Error("missing annotations")
						writer.WriteHeader(422)
						return
					}
				}
			}
			if item.Type == "function_call_output" && strings.Contains(string(item.Output), "tofa-fixture-tool") {
				if !strings.Contains(string(item.Output), "Process exited with code 0") {
					t.Error("synthetic command did not report successful execution")
					writer.WriteHeader(400)
					return
				}
				toolResults.Add(1)
			}
		}
		var item map[string]any
		if count == 1 {
			var name, arguments string
			for _, tool := range payload.Tools {
				switch tool.Name {
				case "exec_command":
					name, arguments = tool.Name, `{"cmd":"echo tofa-fixture-tool","max_output_tokens":100}`
				case "shell_command":
					name, arguments = tool.Name, `{"command":"echo tofa-fixture-tool"}`
				case "shell":
					name, arguments = tool.Name, `{"command":["sh","-c","echo tofa-fixture-tool"]}`
				}
				if name != "" {
					break
				}
			}
			if name == "" {
				t.Error("no known shell tool advertised")
				writer.WriteHeader(400)
				return
			}
			item = map[string]any{"id": "fc_fixture", "type": "function_call", "call_id": "call_fixture", "name": name, "arguments": arguments, "status": "completed"}
		} else {
			item = map[string]any{"id": fmt.Sprintf("msg_%d", count), "type": "message", "role": "assistant", "status": "completed", "content": []any{map[string]any{"type": "output_text", "text": "Fixture complete.", "annotations": []any{}}}}
		}
		response := map[string]any{"id": fmt.Sprintf("resp_%d", count), "object": "response", "status": "completed", "model": "moonshotai/Kimi-K3", "output": []any{item}, "usage": map[string]int{"input_tokens": 10, "output_tokens": 2, "total_tokens": 12}}
		writer.Header().Set("Content-Type", "text/event-stream")
		emit := func(name string, body map[string]any) {
			body["type"] = name
			encoded, _ := json.Marshal(body)
			fmt.Fprintf(writer, "event: %s\ndata: %s\n\n", name, encoded)
			writer.(http.Flusher).Flush()
		}
		emit("response.created", map[string]any{"response": map[string]any{"id": response["id"], "status": "in_progress", "output": []any{}}})
		emit("response.output_item.added", map[string]any{"output_index": 0, "item": item})
		emit("response.output_item.done", map[string]any{"output_index": 0, "item": item})
		emit("response.completed", map[string]any{"response": response})
	}
	app, _ := adapterFixture(t, upstream, nil)
	root := t.TempDir()
	clientHome := filepath.Join(root, "codex")
	if err := os.Mkdir(clientHome, 0700); err != nil {
		t.Fatal(err)
	}
	sentinel := []byte("model_provider = \"original-provider\"\n")
	configPath := filepath.Join(clientHome, "config.toml")
	if err := os.WriteFile(configPath, sentinel, 0600); err != nil {
		t.Fatal(err)
	}
	app.RunClient = func(args, env []string) error {
		isolated := []string{"HOME=" + root, "CODEX_HOME=" + clientHome, "OTEL_SDK_DISABLED=true"}
		for _, entry := range env {
			name, _, _ := strings.Cut(entry, "=")
			switch name {
			case "PATH", "TMPDIR", "SYSTEMROOT", "WINDIR", "TOFA_API_KEY":
				isolated = append(isolated, entry)
			}
		}
		ctx, cancel := context.WithTimeout(context.Background(), 40*time.Second)
		defer cancel()
		// Isolated Windows homes have no configured sandbox backend. Enable the
		// restricted-token backend so read-only tools remain sandboxed.
		if runtime.GOOS == "windows" {
			args = append([]string{"-c", `windows.sandbox="unelevated"`}, args...)
		}
		command := exec.CommandContext(ctx, clientPath, args...)
		command.Dir, command.Env = root, isolated
		output, err := command.CombinedOutput()
		if strings.Contains(string(output), "Model metadata for") {
			t.Error("Codex still reports missing model metadata")
		}
		if err != nil {
			t.Log(string(output))
		}
		return err
	}
	for _, extra := range [][]string{
		{"--ask-for-approval", "never", "exec", "--sandbox", "read-only", "--skip-git-repo-check", "--json", "Run the synthetic fixture tool and reply."},
		{"exec", "resume", "--last", "--skip-git-repo-check", "--json", "Continue the fixture conversation."},
	} {
		args := append([]string{"launch", "codex", "--model", "moonshotai/Kimi-K3", "--allow-unverified", "--"}, extra...)
		if err := app.Run(args); err != nil {
			t.Fatal(err)
		}
	}
	if requests.Load() != 3 || histories.Load() == 0 || toolResults.Load() == 0 {
		t.Fatalf("missing tool/continuation evidence: requests=%d histories=%d toolResults=%d", requests.Load(), histories.Load(), toolResults.Load())
	}
	after, err := os.ReadFile(configPath)
	if err != nil || string(after) != string(sentinel) {
		t.Fatal("Codex config changed")
	}
	if _, err := os.Stat(filepath.Join(clientHome, "auth.json")); !os.IsNotExist(err) {
		t.Fatal("unexpected client auth file")
	}
}

// The installed client owns decision parsing and the execution gate. These
// responses intentionally exercise that real gate, including its optional fields.
func TestInstalledCodexApprovalReviewThroughAdapter(t *testing.T) {
	clientPath := os.Getenv("TOFA_TEST_CODEX")
	if clientPath == "" {
		t.Skip("set TOFA_TEST_CODEX to exercise installed Codex approval review against synthetic responses")
	}
	if !filepath.IsAbs(clientPath) {
		t.Fatal("TOFA_TEST_CODEX must be absolute")
	}
	version, err := exec.Command(clientPath, "--version").Output()
	if err != nil {
		t.Fatal(err)
	}
	t.Log(strings.TrimSpace(string(version)))
	for _, test := range []struct {
		name, assessment string
		guardian         string
		allow            bool
		status           int
	}{
		{"allow", `{"outcome":"allow"}`, "", true, 200},
		{"allow after tool check", `{"outcome":"allow"}`, "", true, 200},
		{"deny", `{"outcome":"deny"}`, "", false, 200},
		{"same-model allow", `{"outcome":"allow"}`, "moonshotai/Kimi-K3", true, 200},
		{"same-model deny", `{"outcome":"deny"}`, "moonshotai/Kimi-K3", false, 200},
		{"explicit distinct allow", `{"outcome":"allow"}`, "zai-org/GLM-5.3-Flash", true, 200},
		{"explicit distinct deny", `{"outcome":"deny"}`, "zai-org/GLM-5.3-Flash", false, 200},
		{"invalid JSON", `not an assessment`, "", false, 200},
		{"missing outcome", `{"risk_level":"low"}`, "", false, 200},
		{"invalid outcome", `{"outcome":"maybe"}`, "", false, 200},
		{"invalid risk", `{"outcome":"allow","risk_level":"safe"}`, "", false, 200},
		{"upstream error", "", "", false, 500},
		{"cancelled review", "", "", false, -1},
	} {
		t.Run(test.name, func(t *testing.T) {
			var mainRequests, reviewRequests, executions atomic.Int32
			reviewStarted := make(chan struct{}, 1)
			upstream := func(writer http.ResponseWriter, request *http.Request) {
				var payload struct {
					Model        string                     `json:"model"`
					Instructions string                     `json:"instructions"`
					Text         map[string]json.RawMessage `json:"text"`
					Input        []struct {
						Type   string          `json:"type"`
						Output json.RawMessage `json:"output"`
					} `json:"input"`
					Tools []struct {
						Name       string          `json:"name"`
						Type       string          `json:"type"`
						Parameters json.RawMessage `json:"parameters"`
					} `json:"tools"`
				}
				if err := json.NewDecoder(request.Body).Decode(&payload); err != nil {
					t.Error(err)
					writer.WriteHeader(400)
					return
				}
				reviewer := len(payload.Tools) == 3
				wantModel := "moonshotai/Kimi-K3"
				if reviewer {
					wantModel = test.guardian
					if wantModel == "" {
						wantModel = "zai-org/GLM-5.3-Flash"
					}
				}
				if payload.Model != wantModel {
					t.Errorf("upstream model = %s, want %s (review=%v)", payload.Model, wantModel, reviewer)
					writer.WriteHeader(400)
					return
				}
				var item map[string]any
				if reviewer {
					reviewCount := reviewRequests.Add(1)
					if payload.Model == "moonshotai/Kimi-K3" {
						if _, exists := payload.Text["format"]; exists {
							t.Error("review schema still constrains tool generation")
							writer.WriteHeader(400)
							return
						}
						if !strings.Contains(payload.Instructions, "When you are ready to give your final answer, return JSON matching this schema:") || !strings.Contains(payload.Instructions, `"required":["outcome"]`) {
							t.Error("complete final-answer schema missing from real reviewer instructions")
							writer.WriteHeader(400)
							return
						}
					} else {
						var format struct {
							Type   string          `json:"type"`
							Schema json.RawMessage `json:"schema"`
						}
						if json.Unmarshal(payload.Text["format"], &format) != nil || format.Type != "json_schema" || !strings.Contains(string(format.Schema), `"outcome"`) {
							t.Error("native Guardian schema lost for non-Kimi model")
							writer.WriteHeader(400)
							return
						}
						if strings.Contains(payload.Instructions, "When you are ready to give your final answer, return JSON matching this schema:") {
							t.Error("Kimi adaptation applied to another model")
						}
					}
					names := map[string]bool{"exec_command": true, "write_stdin": true, "view_image": true}
					for _, tool := range payload.Tools {
						if !names[tool.Name] || tool.Type != "function" || len(tool.Parameters) == 0 {
							t.Errorf("review tool changed: %+v", tool)
						}
						delete(names, tool.Name)
					}
					if len(names) != 0 {
						t.Error("review tool missing")
					}
					if test.status == -1 {
						reviewStarted <- struct{}{}
						<-request.Context().Done()
						return
					}
					if test.status != 200 {
						writer.WriteHeader(test.status)
						return
					}
					if test.name == "allow after tool check" && reviewCount == 1 {
						item = map[string]any{"id": "fc_inspection", "type": "function_call", "call_id": "call_inspection", "name": "exec_command", "arguments": `{"cmd":"echo tofa-review-inspection","max_output_tokens":100}`, "status": "completed"}
					} else {
						if test.name == "allow after tool check" {
							found := false
							for _, input := range payload.Input {
								if input.Type == "function_call_output" && strings.Contains(string(input.Output), "tofa-review-inspection") && strings.Contains(string(input.Output), "Process exited with code 0") {
									found = true
								}
							}
							if !found {
								t.Error("real review tool output missing from continuation")
							}
						}
						item = fixtureMessage(test.assessment)
					}
				} else {
					count := mainRequests.Add(1)
					if count > 2 {
						t.Error("unexpected client retry")
						writer.WriteHeader(400)
						return
					}
					for _, input := range payload.Input {
						if input.Type == "function_call_output" && strings.Contains(string(input.Output), "tofa-review-gated-action") && strings.Contains(string(input.Output), "Process exited with code 0") {
							executions.Add(1)
						}
					}
					if count == 1 {
						item = map[string]any{"id": "fc_review_fixture", "type": "function_call", "call_id": "call_review_fixture", "name": "exec_command", "arguments": `{"cmd":"echo tofa-review-gated-action","sandbox_permissions":"require_escalated","justification":"Run the user-authorized harmless approval fixture.","max_output_tokens":100}`, "status": "completed"}
					} else {
						item = fixtureMessage("Fixture complete.")
					}
				}
				emitFixtureResponse(writer, item)
			}
			app, _ := adapterFixture(t, upstream, nil)
			root := t.TempDir()
			clientHome := filepath.Join(root, "codex")
			if err := os.Mkdir(clientHome, 0700); err != nil {
				t.Fatal(err)
			}
			config := []byte("approval_policy = \"on-request\"\napprovals_reviewer = \"auto_review\"\n[features]\nplugins = false\n")
			configPath := filepath.Join(clientHome, "config.toml")
			if err := os.WriteFile(configPath, config, 0600); err != nil {
				t.Fatal(err)
			}
			var clientOutput []byte
			app.RunClient = func(args, env []string) error {
				isolated := []string{"HOME=" + root, "CODEX_HOME=" + clientHome, "OTEL_SDK_DISABLED=true"}
				for _, entry := range env {
					name, _, _ := strings.Cut(entry, "=")
					switch name {
					case "PATH", "TMPDIR", "SYSTEMROOT", "WINDIR", "TOFA_API_KEY":
						isolated = append(isolated, entry)
					}
				}
				ctx, cancel := context.WithTimeout(context.Background(), 35*time.Second)
				defer cancel()
				if test.status == -1 {
					go func() {
						select {
						case <-reviewStarted:
							cancel()
						case <-ctx.Done():
						}
					}()
				}
				// Isolated Windows homes have no configured sandbox backend. Enable the
				// restricted-token backend so read-only tools remain sandboxed.
				if runtime.GOOS == "windows" {
					args = append([]string{"-c", `windows.sandbox="unelevated"`}, args...)
				}
				command := exec.CommandContext(ctx, clientPath, args...)
				command.Dir, command.Env = root, isolated
				var err error
				clientOutput, err = command.CombinedOutput()
				return err
			}
			args := []string{"launch", "codex", "--model", "moonshotai/Kimi-K3", "--allow-unverified"}
			if test.guardian != "" {
				args = append(args, "--guardian-model", test.guardian)
			}
			args = append(args, "--", "--sandbox", "read-only", "exec", "--skip-git-repo-check", "--ignore-rules", "--json", "Run the harmless fixture command once. If review fails, stop without bypassing review or retrying.")
			err := app.Run(args)
			if err != nil && test.status != -1 {
				t.Fatalf("Codex failed: %v\n%s", err, clientOutput)
			}
			if test.status == -1 && err == nil {
				t.Fatal("cancelled Codex reported success")
			}
			// Codex owns review-session retries (three attempts on invalid
			// assessments, with additional HTTP attempts for server errors).
			wantMain := int32(2)
			if test.status == -1 {
				wantMain = 1
			}
			if reviewRequests.Load() < 1 || reviewRequests.Load() > 12 || mainRequests.Load() != wantMain {
				t.Fatalf("missing real review round trip: reviews=%d main=%d\n%s", reviewRequests.Load(), mainRequests.Load(), clientOutput)
			}
			if got := executions.Load(); (got == 1) != test.allow || got > 1 {
				t.Fatalf("execution gate: executions=%d want allow=%v\n%s", got, test.allow, clientOutput)
			}
			// The JSON event stream is an independent observation of actual command execution.
			completed := false
			for _, line := range strings.Split(string(clientOutput), "\n") {
				var event struct {
					Type string `json:"type"`
					Item struct {
						Type     string `json:"type"`
						Output   string `json:"aggregated_output"`
						ExitCode *int   `json:"exit_code"`
						Status   string `json:"status"`
					} `json:"item"`
				}
				if json.Unmarshal([]byte(line), &event) == nil && event.Type == "item.completed" && event.Item.Type == "command_execution" && event.Item.Status == "completed" && event.Item.ExitCode != nil && *event.Item.ExitCode == 0 && strings.TrimSpace(event.Item.Output) == "tofa-review-gated-action" {
					completed = true
				}
			}
			if completed != test.allow {
				t.Fatalf("command execution events disagree: allow=%v\n%s", test.allow, clientOutput)
			}
			after, err := os.ReadFile(configPath)
			if err != nil || string(after) != string(config) {
				t.Fatal("Codex configuration changed")
			}
			if _, err := os.Stat(filepath.Join(clientHome, "auth.json")); !os.IsNotExist(err) {
				t.Fatal("unexpected client auth file")
			}
		})
	}
}

func fixtureMessage(text string) map[string]any {
	return map[string]any{"id": "msg_review_fixture", "type": "message", "role": "assistant", "status": "completed", "content": []any{map[string]any{"type": "output_text", "text": text, "annotations": []any{}}}}
}

func emitFixtureResponse(writer http.ResponseWriter, item map[string]any) {
	response := map[string]any{"id": "resp_review_fixture", "object": "response", "status": "completed", "model": "moonshotai/Kimi-K3", "output": []any{item}, "usage": map[string]int{"input_tokens": 10, "output_tokens": 2, "total_tokens": 12}}
	writer.Header().Set("Content-Type", "text/event-stream")
	emit := func(name string, body map[string]any) {
		body["type"] = name
		encoded, _ := json.Marshal(body)
		fmt.Fprintf(writer, "event: %s\ndata: %s\n\n", name, encoded)
		writer.(http.Flusher).Flush()
	}
	emit("response.created", map[string]any{"response": map[string]any{"id": response["id"], "status": "in_progress", "output": []any{}}})
	emit("response.output_item.added", map[string]any{"output_index": 0, "item": item})
	emit("response.output_item.done", map[string]any{"output_index": 0, "item": item})
	emit("response.completed", map[string]any{"response": response})
}
