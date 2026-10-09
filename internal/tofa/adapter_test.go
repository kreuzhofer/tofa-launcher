package tofa_test

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/kreuzhofer/tofa-launcher/internal/tofa"
)

func adapterFixture(t *testing.T, upstream http.HandlerFunc, client func(string, string) error) (*tofa.App, *bytes.Buffer) {
	t.Helper()
	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		if request.Header.Get("Authorization") != "Bearer fixture-secret" || request.URL.Query().Get("ai_project_id") != "fixture-project" {
			t.Error("upstream credentials or project changed")
		}
		if request.URL.Path == "/models" {
			io.WriteString(writer, `{"data":[{"id":"fixture-model"},{"id":"moonshotai/Kimi-K3"},{"id":"zai-org/GLM-5.3-Flash"},{"id":"deepseek-ai/DeepSeek-V4.1-Flash"},{"id":"zai-org/GLM-5.3"},{"id":"nvidia/Nemotron-3-Ultra-550b-a55b"}]}`)
			return
		}
		upstream(writer, request)
	}))
	t.Cleanup(server.Close)
	vault := &vault{values: map[string]string{}}
	store := tofa.Store{Dir: t.TempDir(), Vault: vault}
	if err := store.Login("fixture-project", "fixture-secret", "keyring"); err != nil {
		t.Fatal(err)
	}
	output := &bytes.Buffer{}
	app := &tofa.App{Dir: store.Dir, Vault: vault, Out: output, Endpoint: server.URL, HTTP: server.Client()}
	app.RunClient = func(args, env []string) error {
		settings := strings.Join(args, " ")
		match := regexp.MustCompile(`base_url = ("[^"]+")`).FindStringSubmatch(settings)
		if len(match) != 2 {
			t.Fatal("missing client endpoint")
		}
		endpoint, err := strconv.Unquote(match[1])
		if err != nil {
			t.Fatal(err)
		}
		if !strings.HasPrefix(endpoint, "http://127.0.0.1:") || endpoint == server.URL {
			t.Fatal("default launch did not use its own loopback adapter")
		}
		token := ""
		for _, entry := range env {
			if strings.Contains(entry, "fixture-secret") {
				t.Fatal("upstream key reached child environment")
			}
			if strings.HasPrefix(entry, "TOFA_API_KEY=") {
				token = strings.TrimPrefix(entry, "TOFA_API_KEY=")
			}
		}
		if len(token) < 32 || strings.Contains(settings, token) {
			t.Fatal("local token missing or leaked into argv")
		}
		return client(endpoint, token)
	}
	return app, output
}

func adapterRequest(t *testing.T, endpoint, token, body string) *http.Response {
	t.Helper()
	request, err := http.NewRequest(http.MethodPost, endpoint+"/responses", strings.NewReader(body))
	if err != nil {
		t.Fatal(err)
	}
	request.Header.Set("Authorization", "Bearer "+token)
	request.Header.Set("Content-Type", "application/json")
	client := &http.Client{Timeout: 3 * time.Second}
	response, err := client.Do(request)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { response.Body.Close() })
	return response
}

func runAdapted(t *testing.T, app *tofa.App) {
	t.Helper()
	if err := app.Run([]string{"launch", "codex", "--model", "moonshotai/Kimi-K3", "--allow-unverified"}); err != nil {
		t.Fatal(err)
	}
}

func TestAdaptedLaunchRepairsAssistantHistory(t *testing.T) {
	requests := 0
	app, output := adapterFixture(t, func(writer http.ResponseWriter, request *http.Request) {
		requests++
		var payload struct {
			Input []struct {
				Status  string `json:"status"`
				Content []struct {
					Annotations json.RawMessage `json:"annotations"`
				} `json:"content"`
			} `json:"input"`
		}
		if err := json.NewDecoder(request.Body).Decode(&payload); err != nil {
			t.Error(err)
		}
		if len(payload.Input) != 0 && (payload.Input[0].Status != "completed" || string(payload.Input[0].Content[0].Annotations) != "[]") {
			writer.WriteHeader(http.StatusUnprocessableEntity)
			return
		}
		io.WriteString(writer, `{"output":[]}`)
	}, func(endpoint, token string) error {
		for _, body := range []string{
			`{"model":"fixture-model","input":[]}`,
			`{"model":"fixture-model","input":[{"type":"message","role":"assistant","id":"msg_1","content":[{"type":"output_text","text":"first reply"}]}]}`,
		} {
			response := adapterRequest(t, endpoint, token, body)
			if response.StatusCode != http.StatusOK {
				t.Errorf("conversation returned HTTP %d", response.StatusCode)
			}
			response.Body.Close()
		}
		return nil
	})
	runAdapted(t, app)
	if requests != 2 || !strings.Contains(output.String(), "adapter") {
		t.Fatalf("route not announced or wrong request count: %d %s", requests, output.String())
	}
}

func TestAdaptedLaunchRepairsMissingAssistantMessageID(t *testing.T) {
	// The installed 0.159.2 desktop sent this assistant-message shape on
	// continuation; Token Factory returned 422 at body.input.4.id.
	body := `{"model":"fixture-model","input":[{"type":"message","role":"assistant","status":"completed","content":[{"type":"output_text","text":"previous reply","annotations":[]}]}]}`
	app, _ := adapterFixture(t, func(writer http.ResponseWriter, request *http.Request) {
		var payload struct {
			Input []struct {
				ID string `json:"id"`
			} `json:"input"`
		}
		if err := json.NewDecoder(request.Body).Decode(&payload); err != nil {
			t.Error(err)
			return
		}
		if len(payload.Input) != 1 || payload.Input[0].ID == "" {
			writer.WriteHeader(http.StatusUnprocessableEntity)
			io.WriteString(writer, `{"detail":[{"type":"missing","loc":["body","input",0,"id"],"msg":"Field required"}]}`)
			return
		}
		io.WriteString(writer, `{"output":[]}`)
	}, func(endpoint, token string) error {
		response := adapterRequest(t, endpoint, token, body)
		if response.StatusCode != http.StatusOK {
			t.Errorf("assistant-history continuation returned HTTP %d", response.StatusCode)
		}
		return nil
	})
	runAdapted(t, app)
}

func TestAdapterPreservesExistingAndUnrelatedFields(t *testing.T) {
	body := `{"model":"fixture-model","future":9007199254740993,"input":[{"type":"message","role":"assistant","id":"msg_existing","status":"incomplete","content":[{"type":"output_text","text":"existing","annotations":[{"type":"custom","value":7}]},{"type":"output_text","text":"missing"}],"extra":{"status":null}},{"type":"message","role":"user","content":[{"type":"input_text","text":"follow up"}]},{"type":"function_call","name":"shell","arguments":"{}","call_id":"call_1"},{"type":"function_call_output","call_id":"call_1","output":"done"},{"type":"reasoning","encrypted_content":"opaque"},{"type":"message","role":"assistant","id":null,"status":null,"content":[{"type":"output_text","annotations":null,"text":"explicit null"}]}]}`
	want := strings.Replace(body, `"text":"missing"`, `"text":"missing","annotations":[]`, 1)
	app, _ := adapterFixture(t, func(writer http.ResponseWriter, request *http.Request) {
		got, err := io.ReadAll(request.Body)
		if err != nil {
			t.Error(err)
		}
		canonical := func(raw []byte) string {
			decoder := json.NewDecoder(bytes.NewReader(raw))
			decoder.UseNumber()
			var value any
			if err := decoder.Decode(&value); err != nil {
				t.Fatal(err)
			}
			encoded, _ := json.Marshal(value)
			return string(encoded)
		}
		if canonical(got) != canonical([]byte(want)) {
			t.Errorf("unrelated or existing fields changed: %s", got)
		}
		writer.WriteHeader(http.StatusOK)
	}, func(endpoint, token string) error {
		response := adapterRequest(t, endpoint, token, body)
		if response.StatusCode != http.StatusOK {
			t.Error(response.Status)
		}
		return nil
	})
	runAdapted(t, app)
}

func TestAdaptedLaunchRepairsMissingReasoningID(t *testing.T) {
	// Native Codex 0.160.1 omits the ID on replay. Token Factory rejects
	// this item with ResponseReasoningItem.id: Field required (HTTP 422).
	item := `{"type":"reasoning","summary":[],"content":[{"type":"reasoning_text","text":"fixture reasoning"}],"encrypted_content":"opaque","future":9007199254740993}`
	body := `{"model":"fixture-model","input":[` + item + `,` + item + `,{"type":"reasoning","id":"rs_existing","summary":[]},{"type":"reasoning","id":null,"summary":[]}]}`
	var originalIDs []string
	app, _ := adapterFixture(t, func(writer http.ResponseWriter, request *http.Request) {
		var payload struct {
			Input []map[string]json.RawMessage `json:"input"`
		}
		if err := json.NewDecoder(request.Body).Decode(&payload); err != nil {
			t.Fatal(err)
		}
		ids := []string{string(payload.Input[0]["id"]), string(payload.Input[1]["id"])}
		if ids[0] == "" || ids[1] == "" || ids[0] == ids[1] {
			writer.WriteHeader(http.StatusUnprocessableEntity)
			return
		}
		if originalIDs == nil {
			originalIDs = ids
		} else if ids[0] != originalIDs[0] || ids[1] != originalIDs[1] {
			t.Error("reasoning IDs changed on retry or continuation")
		}
		for _, index := range []int{0, 1} {
			var expected map[string]json.RawMessage
			json.Unmarshal([]byte(item), &expected)
			delete(payload.Input[index], "id")
			got, _ := json.Marshal(payload.Input[index])
			want, _ := json.Marshal(expected)
			if string(got) != string(want) {
				t.Error("reasoning content changed")
			}
		}
		if string(payload.Input[2]["id"]) != `"rs_existing"` || string(payload.Input[3]["id"]) != "null" {
			t.Error("supplied reasoning ID changed")
		}
		writer.WriteHeader(http.StatusOK)
	}, func(endpoint, token string) error {
		for _, input := range []string{body, body, strings.TrimSuffix(body, `]}`) + `,{"type":"message","role":"user","content":"next"}]}`} {
			response := adapterRequest(t, endpoint, token, input)
			if response.StatusCode != http.StatusOK {
				t.Errorf("reasoning continuation returned HTTP %d", response.StatusCode)
			}
			response.Body.Close()
		}
		return nil
	})
	runAdapted(t, app)
}

func TestAdaptedHistoryIDsSurviveRetriesAndAdditionalTurns(t *testing.T) {
	message := `{"type":"message","role":"assistant","content":[{"type":"output_text","text":"same reply"}]}`
	body := `{"model":"fixture-model","input":[` + message + `,` + message + `]}`
	var firstIDs []string
	requests := 0
	app, _ := adapterFixture(t, func(writer http.ResponseWriter, request *http.Request) {
		requests++
		var payload struct {
			Input []struct {
				ID string `json:"id"`
			} `json:"input"`
		}
		if err := json.NewDecoder(request.Body).Decode(&payload); err != nil {
			t.Error(err)
			return
		}
		if len(payload.Input) < 2 || payload.Input[0].ID == "" || payload.Input[1].ID == "" || payload.Input[0].ID == payload.Input[1].ID {
			t.Error("repeated assistant messages need distinct nonempty IDs")
			return
		}
		if firstIDs == nil {
			firstIDs = []string{payload.Input[0].ID, payload.Input[1].ID}
		} else if payload.Input[0].ID != firstIDs[0] || payload.Input[1].ID != firstIDs[1] {
			t.Error("retry or new turn changed prior message IDs")
		}
		writer.WriteHeader(http.StatusOK)
	}, func(endpoint, token string) error {
		for _, input := range []string{body, body, strings.TrimSuffix(body, `]}`) + `,{"type":"message","role":"user","content":[{"type":"input_text","text":"next turn"}]}]}`} {
			response := adapterRequest(t, endpoint, token, input)
			if response.StatusCode != http.StatusOK {
				t.Error(response.Status)
			}
			response.Body.Close()
		}
		return nil
	})
	runAdapted(t, app)
	if requests != 3 {
		t.Fatalf("got %d requests, want retry and continuation", requests)
	}
}

func TestAdapterStopsAfterClientExitOrStartupFailure(t *testing.T) {
	for _, clientError := range []error{nil, errors.New("fixture startup failure")} {
		t.Run(fmtError(clientError), func(t *testing.T) {
			var address string
			app, _ := adapterFixture(t, func(http.ResponseWriter, *http.Request) { t.Error("unexpected upstream request") }, func(endpoint, token string) error {
				address = endpoint
				return clientError
			})
			err := app.Run([]string{"launch", "codex", "--model", "moonshotai/Kimi-K3", "--allow-unverified"})
			if !errors.Is(err, clientError) {
				t.Fatalf("lost client result: %v", err)
			}
			client := &http.Client{Timeout: time.Second}
			response, err := client.Get(address + "/responses")
			if err == nil {
				response.Body.Close()
				t.Fatal("adapter survived client exit")
			}
		})
	}
}

func fmtError(err error) string {
	if err == nil {
		return "normal exit"
	}
	return err.Error()
}

func TestAdapterRejectsInvalidRequestsBeforeUpstream(t *testing.T) {
	var calls atomic.Int32
	app, output := adapterFixture(t, func(http.ResponseWriter, *http.Request) { calls.Add(1) }, func(endpoint, token string) error {
		cases := []struct {
			name, method, path, key, body, encoding string
			status                                  int
		}{
			{name: "missing token", method: "POST", path: "/responses", body: `{}`, status: 401},
			{name: "wrong token", method: "POST", path: "/responses", key: "wrong", body: `{}`, status: 401},
			{name: "other route", method: "POST", path: "/models", key: token, body: `{}`, status: 404},
			{name: "project override", method: "POST", path: "/responses?ai_project_id=other", key: token, body: `{}`, status: 404},
			{name: "get", method: "GET", path: "/responses", key: token, status: 405},
			{name: "invalid JSON", method: "POST", path: "/responses", key: token, body: `{secret`, status: 400},
			{name: "null JSON", method: "POST", path: "/responses", key: token, body: `null`, status: 400},
			{name: "trailing JSON", method: "POST", path: "/responses", key: token, body: `{} {}`, status: 400},
			{name: "encoded body", method: "POST", path: "/responses", key: token, body: `{}`, encoding: "gzip", status: 415},
			{name: "large body", method: "POST", path: "/responses", key: token, body: strings.Repeat("x", (16<<20)+1), status: 413},
		}
		for _, test := range cases {
			t.Run(test.name, func(t *testing.T) {
				request, _ := http.NewRequest(test.method, endpoint+test.path, strings.NewReader(test.body))
				request.Header.Set("Authorization", "Bearer "+test.key)
				request.Header.Set("Content-Encoding", test.encoding)
				client := &http.Client{Timeout: 3 * time.Second}
				response, err := client.Do(request)
				if err != nil {
					t.Fatal(err)
				}
				defer response.Body.Close()
				if response.StatusCode != test.status {
					t.Errorf("got %d, want %d", response.StatusCode, test.status)
				}
			})
		}
		return nil
	})
	runAdapted(t, app)
	if calls.Load() != 0 || strings.Contains(output.String(), "fixture-secret") {
		t.Fatal("rejected input reached upstream or secret logged")
	}
}

func TestAdapterStreamsAndCancelsUpstream(t *testing.T) {
	cancelled := make(chan struct{})
	app, _ := adapterFixture(t, func(writer http.ResponseWriter, request *http.Request) {
		writer.Header().Set("Content-Type", "text/event-stream")
		io.WriteString(writer, "data: first\n\n")
		writer.(http.Flusher).Flush()
		<-request.Context().Done()
		close(cancelled)
	}, func(endpoint, token string) error {
		ctx, cancel := context.WithCancel(context.Background())
		defer cancel()
		request, _ := http.NewRequestWithContext(ctx, "POST", endpoint+"/responses", strings.NewReader(`{"input":[]}`))
		request.Header.Set("Authorization", "Bearer "+token)
		client := &http.Client{Timeout: 3 * time.Second}
		response, err := client.Do(request)
		if err != nil {
			t.Fatal(err)
		}
		defer response.Body.Close()
		first := make([]byte, len("data: first\n\n"))
		if _, err := io.ReadFull(response.Body, first); err != nil {
			t.Fatal("stream was buffered:", err)
		}
		if string(first) != "data: first\n\n" {
			t.Fatal("stream changed")
		}
		cancel()
		select {
		case <-cancelled:
		case <-time.After(3 * time.Second):
			t.Fatal("client cancellation did not reach upstream")
		}
		return nil
	})
	runAdapted(t, app)
}

func TestLaunchCancellationStopsActiveUpstream(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	cancelled := make(chan struct{})
	app, _ := adapterFixture(t, func(writer http.ResponseWriter, request *http.Request) {
		writer.Header().Set("Content-Type", "text/event-stream")
		io.WriteString(writer, "data: first\n\n")
		writer.(http.Flusher).Flush()
		<-request.Context().Done()
		close(cancelled)
	}, func(endpoint, token string) error {
		response := adapterRequest(t, endpoint, token, `{"input":[]}`)
		defer response.Body.Close()
		cancel()
		select {
		case <-cancelled:
		case <-time.After(3 * time.Second):
			t.Fatal("launch cancellation left upstream running")
		}
		return nil
	})
	err := app.RunContext(ctx, []string{"launch", "codex", "--model", "moonshotai/Kimi-K3", "--allow-unverified"})
	if !errors.Is(err, context.Canceled) {
		t.Fatalf("lost launch cancellation: %v", err)
	}
}

func TestAdapterListenerFailureIsReported(t *testing.T) {
	app, _ := adapterFixture(t, func(http.ResponseWriter, *http.Request) { t.Error("unexpected upstream request") }, func(string, string) error { t.Error("client started without listener"); return nil })
	app.Listen = func(string, string) (net.Listener, error) { return nil, errors.New("fixture listen failure") }
	err := app.Run([]string{"launch", "codex", "--model", "moonshotai/Kimi-K3", "--allow-unverified"})
	if err == nil || !strings.Contains(err.Error(), "adapter") {
		t.Fatalf("missing adapter startup failure: %v", err)
	}
}

func TestAdapterReportsUnexpectedListenerExitAndCancelsStream(t *testing.T) {
	var listener net.Listener
	cancelled := make(chan struct{})
	app, _ := adapterFixture(t, func(writer http.ResponseWriter, request *http.Request) {
		writer.Header().Set("Content-Type", "text/event-stream")
		io.WriteString(writer, "data: first\n\n")
		writer.(http.Flusher).Flush()
		<-request.Context().Done()
		close(cancelled)
	}, func(endpoint, token string) error {
		response := adapterRequest(t, endpoint, token, `{}`)
		defer response.Body.Close()
		listener.Close()
		select {
		case <-cancelled:
		case <-time.After(3 * time.Second):
			t.Fatal("adapter failure left upstream running")
		}
		return nil
	})
	app.Listen = func(network, address string) (net.Listener, error) {
		var err error
		listener, err = net.Listen(network, address)
		return listener, err
	}
	err := app.Run([]string{"launch", "codex", "--model", "moonshotai/Kimi-K3", "--allow-unverified"})
	if err == nil || !strings.Contains(err.Error(), "adapter stopped unexpectedly") {
		t.Fatalf("missing runtime failure: %v", err)
	}
}

func TestAdapterDoesNotRetryOrFollowRedirects(t *testing.T) {
	for _, status := range []int{307, 422, 429, 500, 503} {
		t.Run(strconv.Itoa(status), func(t *testing.T) {
			var calls atomic.Int32
			var redirectCalls atomic.Int32
			redirect := httptest.NewServer(http.HandlerFunc(func(http.ResponseWriter, *http.Request) { redirectCalls.Add(1) }))
			defer redirect.Close()
			app, _ := adapterFixture(t, func(writer http.ResponseWriter, request *http.Request) {
				calls.Add(1)
				if request.Header.Get("Cookie") != "" || request.Header.Get("Idempotency-Key") != "" || request.Header.Get("X-Forwarded-Host") != "" {
					t.Error("untrusted headers forwarded")
				}
				writer.Header().Set("Location", redirect.URL)
				writer.Header().Set("Retry-After", "1")
				writer.WriteHeader(status)
				io.WriteString(writer, `{"error":"fixture rejection"}`)
			}, func(endpoint, token string) error {
				request, _ := http.NewRequest("POST", endpoint+"/responses", strings.NewReader(`{}`))
				request.Header.Set("Authorization", "Bearer "+token)
				request.Header.Set("Cookie", "untrusted")
				request.Header.Set("Idempotency-Key", "must-not-trigger-retry")
				request.Header.Set("X-Forwarded-Host", "untrusted")
				client := &http.Client{Timeout: 3 * time.Second}
				response, err := client.Do(request)
				if err != nil {
					t.Fatal(err)
				}
				defer response.Body.Close()
				want := status
				if status == 307 {
					want = 502
				}
				if response.StatusCode != want {
					t.Errorf("got %d, want %d", response.StatusCode, want)
				}
				return nil
			})
			runAdapted(t, app)
			if calls.Load() != 1 || redirectCalls.Load() != 0 {
				t.Fatal("request retried or redirected")
			}
		})
	}
}

func TestSimultaneousLaunchesUseIsolatedEndpointsAndTokens(t *testing.T) {
	type route struct{ endpoint, token string }
	routes := make(chan route, 2)
	release := make(chan struct{})
	var runners sync.WaitGroup
	for range 2 {
		app, _ := adapterFixture(t, func(http.ResponseWriter, *http.Request) {}, func(endpoint, token string) error {
			routes <- route{endpoint, token}
			<-release
			return nil
		})
		runners.Add(1)
		go func() { defer runners.Done(); runAdapted(t, app) }()
	}
	t.Cleanup(func() { close(release); runners.Wait() })
	var active []route
	for range 2 {
		select {
		case entry := <-routes:
			active = append(active, entry)
		case <-time.After(3 * time.Second):
			t.Fatal("concurrent launch did not start")
		}
	}
	if active[0].endpoint == active[1].endpoint || active[0].token == active[1].token {
		t.Fatal("launches shared an endpoint or credential")
	}
	for index, entry := range active {
		wrong := adapterRequest(t, entry.endpoint, active[1-index].token, `{}`)
		if wrong.StatusCode != 401 {
			t.Error("other launch token was accepted")
		}
		wrong.Body.Close()
		right := adapterRequest(t, entry.endpoint, entry.token, `{}`)
		if right.StatusCode != 200 {
			t.Error("own launch token was rejected")
		}
		right.Body.Close()
	}
}

type readObservedListener struct {
	net.Listener
	readStarted chan struct{}
}

func (listener *readObservedListener) Accept() (net.Conn, error) {
	connection, err := listener.Listener.Accept()
	if err != nil {
		return nil, err
	}
	return &readObservedConnection{Conn: connection, readStarted: listener.readStarted}, nil
}

type readObservedConnection struct {
	net.Conn
	readStarted chan struct{}
	once        sync.Once
}

func (connection *readObservedConnection) Read(buffer []byte) (int, error) {
	connection.once.Do(func() { close(connection.readStarted) })
	return connection.Conn.Read(buffer)
}

func TestClientExitClosesAdapterWithAnIdleConnection(t *testing.T) {
	readStarted := make(chan struct{})
	app, _ := adapterFixture(t, nil, func(endpoint, token string) error {
		connection, err := net.DialTimeout("tcp", strings.TrimPrefix(endpoint, "http://"), time.Second)
		if err != nil {
			t.Fatal(err)
		}
		t.Cleanup(func() { connection.Close() })
		select {
		case <-readStarted:
		case <-time.After(time.Second):
			t.Fatal("server did not start reading the idle connection")
		}
		return nil
	})
	app.Listen = func(network, address string) (net.Listener, error) {
		listener, err := net.Listen(network, address)
		if err != nil {
			return nil, err
		}
		return &readObservedListener{Listener: listener, readStarted: readStarted}, nil
	}
	runAdapted(t, app)
}
