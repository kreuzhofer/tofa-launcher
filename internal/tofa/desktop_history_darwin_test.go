package tofa_test

import (
	"context"
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"net/http/httptest"
	"os"
	"os/exec"
	"path/filepath"
	"reflect"
	"strconv"
	"strings"
	"sync/atomic"
	"syscall"
	"testing"
	"time"

	"github.com/kreuzhofer/tofa-launcher/internal/tofa"
)

func TestDesktopHistoryRoundTripRequiresFreshLaunch(t *testing.T) {
	for _, model := range []string{
		"zai-org/GLM-5.3-Flash", "deepseek-ai/DeepSeek-V4.1-Flash", "zai-org/GLM-5.3",
		"moonshotai/Kimi-K3", "nvidia/Nemotron-3-Ultra-550b-a55b",
	} {
		t.Run(model, func(t *testing.T) { desktopHistoryRoundTrip(t, "cancellation", model) })
	}
}

func TestDesktopHistoryRecoversFailures(t *testing.T) {
	for _, failure := range []string{"normal exit", "engine loss", "adapter failure", "startup failure", "abrupt death"} {
		t.Run(failure, func(t *testing.T) { desktopHistoryRoundTrip(t, failure, "moonshotai/Kimi-K3") })
	}
	for _, tc := range []struct{ failure, model string }{
		{"normal exit", "zai-org/GLM-5.3-Flash"},
		{"engine loss", "nvidia/Nemotron-3-Ultra-550b-a55b"},
		{"adapter failure", "zai-org/GLM-5.3"},
		{"startup failure", "deepseek-ai/DeepSeek-V4.1-Flash"},
		{"abrupt death", "deepseek-ai/DeepSeek-V4.1-Flash"},
	} {
		t.Run(tc.failure+"/"+tc.model, func(t *testing.T) { desktopHistoryRoundTrip(t, tc.failure, tc.model) })
	}
}

func TestDesktopHistorySurvivesInstalledRemoval(t *testing.T) {
	for _, model := range []string{"moonshotai/Kimi-K3", "deepseek-ai/DeepSeek-V4.1-Flash"} {
		t.Run(model, func(t *testing.T) { desktopHistoryRoundTrip(t, "uninstall", model) })
	}
}

func desktopHistoryRoundTrip(t *testing.T, failure, model string) {
	installed := os.Getenv("TOFA_TEST_DESKTOP_ENGINE")
	if installed == "" {
		t.Skip("set TOFA_TEST_DESKTOP_ENGINE")
	}
	bundle, capture := desktopFixture(t, "controlled")
	engine := filepath.Join(bundle, "Contents/Resources/codex")
	if err := os.Remove(engine); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(installed, engine); err != nil {
		t.Fatal(err)
	}
	var nativeCalls, tofaCalls atomic.Int32
	respond := func(w http.ResponseWriter, item map[string]any) {
		w.Header().Set("Content-Type", "text/event-stream")
		for _, event := range []struct {
			kind  string
			value map[string]any
		}{
			{"response.created", map[string]any{"response": map[string]any{"id": "response_fixture", "status": "in_progress", "output": []any{}}}},
			{"response.output_item.added", map[string]any{"output_index": 0, "item": item}},
			{"response.output_item.done", map[string]any{"output_index": 0, "item": item}},
			{"response.completed", map[string]any{"response": map[string]any{"id": "response_fixture", "status": "completed", "output": []any{item}, "usage": map[string]int{"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}}}},
		} {
			event.value["type"] = event.kind
			data, _ := json.Marshal(event.value)
			fmt.Fprintf(w, "event: %s\ndata: %s\n\n", event.kind, data)
		}
	}
	answer := func(text string) map[string]any {
		return map[string]any{"id": "message_fixture", "type": "message", "role": "assistant", "status": "completed", "content": []any{map[string]any{"type": "output_text", "text": text, "annotations": []any{}}}}
	}
	native := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			w.WriteHeader(http.StatusUpgradeRequired)
			return
		}
		var request struct{ Model string }
		if json.NewDecoder(r.Body).Decode(&request) != nil || request.Model != "gpt-6-astra" || r.Header.Get("Authorization") != "Bearer synthetic-native" {
			t.Error("native conversation routing changed")
		}
		nativeCalls.Add(1)
		respond(w, answer("Native history answer"))
	}))
	defer native.Close()
	app, _ := adapterFixture(t, func(w http.ResponseWriter, r *http.Request) {
		var request struct {
			Model string
			Input []map[string]any
		}
		if err := json.NewDecoder(r.Body).Decode(&request); err != nil {
			t.Error(err)
			w.WriteHeader(400)
			return
		}
		if request.Model != model {
			t.Error("Token Factory model changed")
		}
		tofaCalls.Add(1)
		// Only a tool result from the current user turn completes this response.
		// Earlier results must not bypass a fresh tool exchange after resume.
		for index := len(request.Input) - 1; index >= 0; index-- {
			item := request.Input[index]
			if item["role"] == "user" {
				break
			}
			if item["type"] == "function_call_output" {
				if !strings.Contains(fmt.Sprint(item["output"]), "history-tool-result") {
					t.Error("coding tool result missing from inference history")
				}
				respond(w, answer("Token Factory history answer"))
				return
			}
		}
		respond(w, map[string]any{"id": "function_fixture", "type": "function_call", "call_id": "history_call", "name": "exec_command", "arguments": `{"cmd":"printf history-tool-result","max_output_tokens":100}`, "status": "completed"})
	}, nil)
	if failure == "uninstall" {
		t.Setenv("XDG_CONFIG_HOME", filepath.Join(os.Getenv("HOME"), ".config"))
		t.Setenv("TOFA_INSTALL_DIR", filepath.Join(os.Getenv("HOME"), "removed-install"))
		app.Dir, _ = tofa.ConfigDir()
		if err := (tofa.Store{Dir: app.Dir, Vault: app.Vault}).Login("fixture-project", "fixture-secret", "file"); err != nil {
			t.Fatal(err)
		}
	}

	listening := make(chan net.Listener, 10)
	app.Listen = func(network, address string) (net.Listener, error) {
		listener, err := net.Listen(network, address)
		if err == nil {
			listening <- listener
		}
		return listener, err
	}
	home := filepath.Join(os.Getenv("HOME"), ".codex")
	workspace := filepath.Join(filepath.Dir(capture), "workspace")
	for _, path := range []string{home, workspace} {
		if err := os.MkdirAll(path, 0700); err != nil {
			t.Fatal(err)
		}
	}
	workspace, err := filepath.EvalSymlinks(workspace)
	if err != nil {
		t.Fatal(err)
	}
	config := "model = \"gpt-6-astra\"\ncli_auth_credentials_store = \"file\"\nopenai_base_url = " + fmt.Sprintf("%q", native.URL) + "\n"
	if err := os.WriteFile(filepath.Join(home, "config.toml"), []byte(config), 0600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(home, "auth.json"), []byte(`{"OPENAI_API_KEY":"synthetic-native"}`), 0600); err != nil {
		t.Fatal(err)
	}
	ordinary := capturedDesktop{Cwd: workspace, Env: map[string]string{"PATH": os.Getenv("PATH"), "HOME": os.Getenv("HOME"), "CODEX_HOME": home, "CODEX_CLI_PATH": installed}}
	e := openDesktopEngine(t, ordinary)
	started := e.call("thread/start", map[string]any{"cwd": workspace, "historyMode": "paginated", "model": "gpt-6-astra", "modelProvider": "openai", "approvalPolicy": "never", "sandbox": "read-only"})
	nativeID := started["thread"].(map[string]any)["id"].(string)
	e.turnText(nativeID, "completed", "Native first message")
	e.call("thread/name/set", map[string]string{"threadId": nativeID, "name": "Native title"})
	e.close()

	var child capturedDesktop
	var stop func()
	if failure == "abrupt death" {
		child, stop = executableDesktopFixture(t, app, bundle, capture, "--evaluation-observer", legacyProxyObserver(t), "--model", model)
	} else {
		child, stop = liveDesktopFixture(t, app, bundle, capture, "--evaluation-observer", legacyProxyObserver(t), "--model", model)
	}
	firstRoute, firstKey := child.Env["TOFA_DESKTOP_CONTEXT"], child.Env["TOFA_API_KEY"]
	e = openDesktopEngine(t, child)
	resumed := e.call("thread/resume", map[string]any{"threadId": nativeID, "model": nil, "modelProvider": nil})
	if resumed["modelProvider"] != "openai" || resumed["model"] != "gpt-6-astra" {
		t.Fatal("native identity changed")
	}
	e.turnText(nativeID, "completed", "Native second message during tofa")
	started = e.call("thread/start", map[string]any{"cwd": workspace, "historyMode": "paginated", "approvalPolicy": "never", "sandbox": "read-only"})
	tofaID := started["thread"].(map[string]any)["id"].(string)
	e.turnText(tofaID, "completed", "Token Factory first message")
	e.call("thread/name/set", map[string]string{"threadId": tofaID, "name": "Token Factory title"})

	e.close()
	// Edits made while the launch is active must survive every failure path.
	configPath := filepath.Join(home, "config.toml")
	file, err := os.OpenFile(configPath, os.O_APPEND|os.O_WRONLY, 0600)
	if err != nil {
		t.Fatal(err)
	}
	_, writeErr := file.WriteString("\n[tui]\nanimations = false\n")
	closeErr := file.Close()
	if writeErr != nil || closeErr != nil {
		t.Fatalf("write concurrent setting: %v %v", writeErr, closeErr)
	}
	workPath := filepath.Join(workspace, "ordinary-work.txt")
	if err := os.WriteFile(workPath, []byte("ordinary workspace content"), 0600); err != nil {
		t.Fatal(err)
	}
	preserved := map[string][]byte{}
	for _, path := range []string{configPath, filepath.Join(home, "auth.json"), workPath} {
		data, err := os.ReadFile(path)
		if err != nil {
			t.Fatal(err)
		}
		preserved[path] = data
	}
	owner, err := os.Readlink(filepath.Join(child.Env["CODEX_ELECTRON_USER_DATA_PATH"], "SingletonLock"))
	if err != nil {
		t.Fatal(err)
	}
	desktopPID, err := strconv.Atoi(owner[strings.LastIndex(owner, "-")+1:])
	if err != nil {
		t.Fatal(err)
	}
	switch failure {
	case "normal exit":
		if err := os.WriteFile(capture+".exit", nil, 0600); err != nil {
			t.Fatal(err)
		}
		waitDesktopPIDStopped(t, desktopPID)
	case "engine loss":
		data, err := os.ReadFile(capture + ".pid")
		if err != nil {
			t.Fatal(err)
		}
		pid, err := strconv.Atoi(string(data))
		if err != nil {
			t.Fatal(err)
		}
		if err := syscall.Kill(pid, syscall.SIGKILL); err != nil {
			t.Fatal(err)
		}
		// The engine-loss monitor grants five seconds for native quit, then
		// up to two seconds for termination. Keep the assertion bounded while
		// allowing both phases and the monitor's polling interval.
		waitDesktopPIDStoppedWithin(t, desktopPID, 10*time.Second)
	case "adapter failure":
		if err := (<-listening).Close(); err != nil {
			t.Fatal(err)
		}
		waitDesktopPIDStopped(t, desktopPID)
	}
	stop()
	if failure == "abrupt death" {
		assertExpiredDesktopContext(t, child)
		// Simulate manually quitting only the test's surviving desktop.
		syscall.Kill(-desktopPID, syscall.SIGKILL)
		waitDesktopPIDStopped(t, desktopPID)
	}
	if failure == "normal exit" {
		if err := os.Remove(capture + ".exit"); err != nil {
			t.Fatal(err)
		}
	}
	if failure == "startup failure" {
		// Fail a relaunch after history exists, before publishing its live route.
		if err := os.WriteFile(capture+".fail-startup", nil, 0600); err != nil {
			t.Fatal(err)
		}
		ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		err := app.RunContext(ctx, []string{"launch", "codex-desktop", "--app-bundle", bundle, "--model", model, "--allow-unverified", "--evaluation-observer", legacyProxyObserver(t)})
		cancel()
		if err == nil || !strings.Contains(err.Error(), "exit status 17") {
			t.Fatalf("startup failure was not surfaced: %v", err)
		}
		if err := os.Remove(capture + ".fail-startup"); err != nil {
			t.Fatal(err)
		}
	}
	assertExpiredDesktopContext(t, child)
	ordinary.Env["CODEX_CLI_PATH"] = child.Env["CODEX_CLI_PATH"]
	ordinary.Env["TOFA_API_KEY"] = child.Env["TOFA_API_KEY"] // Stale credentials must not revive ordinary inference.
	ordinary.Env["TOFA_DESKTOP_INACTIVE"] = "synthetic-inherited-credential"
	want := []string{"user:Token Factory first message", "tool:printf history-tool-result:history-tool-result", "assistant:Token Factory history answer"}

	check := func(e *desktopEngine) {
		t.Helper()
		for path, want := range preserved {
			data, err := os.ReadFile(path)
			if err != nil || string(data) != string(want) {
				t.Fatalf("failure recovery changed ordinary state: %s", filepath.Base(path))
			}
		}
		listed := e.call("thread/list", map[string]any{"modelProviders": []string{}, "useStateDbOnly": true})["data"].([]any)
		ids := map[string]int{}
		for _, raw := range listed {
			ids[raw.(map[string]any)["id"].(string)]++
		}
		if len(ids) != 2 || ids[nativeID] != 1 || ids[tofaID] != 1 {
			t.Fatalf("history identities changed: %v", ids)
		}
		for _, tc := range []struct {
			id, title, provider string
			messages            []string
		}{
			{nativeID, "Native title", "openai", []string{"user:Native first message", "assistant:Native history answer", "user:Native second message during tofa", "assistant:Native history answer"}},
			{tofaID, "Token Factory title", "nebius-tofa", want},
		} {
			thread := e.call("thread/read", map[string]any{"threadId": tc.id, "includeTurns": true})["thread"].(map[string]any)
			if thread["name"] != tc.title || thread["cwd"] != workspace || thread["modelProvider"] != tc.provider {
				t.Fatalf("history metadata changed: %v", thread)
			}
			var messages []string
			for _, rawTurn := range thread["turns"].([]any) {
				for _, rawItem := range rawTurn.(map[string]any)["items"].([]any) {
					item := rawItem.(map[string]any)
					switch item["type"] {
					case "userMessage":
						for _, raw := range item["content"].([]any) {
							part := raw.(map[string]any)
							if part["type"] == "text" {
								messages = append(messages, "user:"+part["text"].(string))
							}
						}
					case "agentMessage":
						messages = append(messages, "assistant:"+item["text"].(string))
					case "commandExecution":
						data, _ := json.Marshal(item)
						if !strings.Contains(string(data), "printf history-tool-result") || !strings.Contains(fmt.Sprint(item["aggregatedOutput"]), "history-tool-result") || item["exitCode"] != float64(0) {
							t.Fatalf("tool call/result lost: %s", data)
						}
						messages = append(messages, "tool:printf history-tool-result:history-tool-result")
					}
				}
			}
			if !reflect.DeepEqual(messages, tc.messages) {
				data, _ := json.Marshal(thread["turns"])
				t.Fatalf("ordered history changed: got %v want %v; turns: %s", messages, tc.messages, data)
			}
		}
	}
	for launch := 0; launch < 2; launch++ {
		e = openDesktopEngine(t, ordinary)
		check(e)
		resumed = e.call("thread/resume", map[string]any{"threadId": tofaID, "model": nil, "modelProvider": nil})
		if resumed["modelProvider"] != "nebius-tofa" || resumed["model"] != model {
			t.Fatal("ordinary hydration changed provider/model")
		}
		before := tofaCalls.Load()
		e.turnText(tofaID, "failed", "Inactive send")
		if tofaCalls.Load() != before || nativeCalls.Load() != 2 {
			t.Fatal("inactive conversation reached inference")
		}
		want = append(want, "user:Inactive send")
		e.close()
		if err := os.Remove(capture); err != nil {
			t.Fatal(err)
		}

		child, stop = liveDesktopFixture(t, app, bundle, capture, "--evaluation-observer", legacyProxyObserver(t), "--model", model)
		if child.Env["TOFA_DESKTOP_CONTEXT"] == firstRoute || child.Env["TOFA_API_KEY"] == firstKey {
			t.Fatal("history recovery reused stale inference access")
		}

		e = openDesktopEngine(t, child)
		check(e)
		resumed = e.call("thread/resume", map[string]any{"threadId": tofaID, "model": nil, "modelProvider": nil})
		if resumed["model"] != model || resumed["modelProvider"] != "nebius-tofa" || resumed["thread"].(map[string]any)["id"] != tofaID {
			t.Fatal("relaunch changed recorded identity")
		}
		e.turnText(tofaID, "completed", "Continue same thread after relaunch")
		want = append(want, "user:Continue same thread after relaunch", "tool:printf history-tool-result:history-tool-result", "assistant:Token Factory history answer")
		check(e)
		e.close()
		stop()
	}
	e = openDesktopEngine(t, ordinary)
	check(e)
	e.close()
	if nativeCalls.Load() != 2 || tofaCalls.Load() != 6 {
		t.Fatalf("unexpected routing counts: native=%d tofa=%d", nativeCalls.Load(), tofaCalls.Load())
	}
	if failure == "uninstall" {
		for _, args := range [][]string{{"--tofa-installed-lifecycle", "uninstall"}, {"--tofa-installed-lifecycle", "uninstall", "--purge"}} {
			command := exec.Command(child.Env["CODEX_CLI_PATH"], args...)
			if output, err := command.CombinedOutput(); err != nil {
				t.Fatalf("installed bridge removal: %v %s", err, output)
			}
			e = openDesktopEngine(t, ordinary)
			check(e)
			e.call("thread/resume", map[string]any{"threadId": tofaID, "model": nil, "modelProvider": nil})
			e.turnText(tofaID, "failed", "Unavailable after uninstall")
			want = append(want, "user:Unavailable after uninstall")
			check(e)
			e.close()
			if nativeCalls.Load() != 2 || tofaCalls.Load() != 6 {
				t.Fatal("removed integration retained inference access")
			}
		}
	}
}
