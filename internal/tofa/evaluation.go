package tofa

// Evaluation is an explicit per-launch transport hook. It cannot change the
// provider, credentials, model catalog, native approval policy or ownership gate.
import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"time"
)

type evaluationObserver struct {
	Version             int                `json:"version"`
	Endpoint            string             `json:"endpoint"`
	Secret              string             `json:"secret"`
	Seconds             int                `json:"seconds"`
	PresentationRuntime *evaluationRuntime `json:"presentation_runtime,omitempty"`
}

type evaluationRuntime struct {
	Root   string `json:"root"`
	Script string `json:"script"`
}

func (e *evaluationRuntime) arguments(ctx context.Context) ([]string, error) {
	if !filepath.IsAbs(e.Root) || !filepath.IsAbs(e.Script) || filepath.Base(e.Script) != "presentation_runtime.py" {
		return nil, errors.New("invalid supplied presentation runtime configuration")
	}
	python := filepath.Join(e.Root, "dependencies/python/bin/python3")
	rootInfo, rootErr := os.Lstat(e.Root)
	pythonInfo, pythonErr := os.Stat(python)
	scriptInfo, scriptErr := os.Lstat(e.Script)
	if rootErr != nil || !rootInfo.IsDir() || pythonErr != nil || !pythonInfo.Mode().IsRegular() ||
		pythonInfo.Mode().Perm()&0111 == 0 || scriptErr != nil || !scriptInfo.Mode().IsRegular() {
		return nil, errors.New("supplied presentation runtime executable or loader unavailable")
	}
	resolvedRoot, rootErr := filepath.EvalSymlinks(e.Root)
	resolvedPython, pythonErr := filepath.EvalSymlinks(python)
	relative, relativeErr := filepath.Rel(resolvedRoot, resolvedPython)
	if rootErr != nil || pythonErr != nil || relativeErr != nil || relative == ".." || strings.HasPrefix(relative, ".."+string(os.PathSeparator)) {
		return nil, errors.New("Python executable is outside supplied runtime; launch refused")
	}
	probe, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()
	command := exec.CommandContext(probe, "codex", "mcp", "list", "--json")
	command.Env = childEnv("")
	data, err := command.Output()
	var servers []struct {
		Name string `json:"name"`
	}
	if err != nil || len(data) > 1024*1024 || string(bytes.TrimSpace(data)) == "null" || json.Unmarshal(data, &servers) != nil {
		return nil, errors.New("could not inspect existing MCP configuration; presentation launch refused")
	}
	for _, server := range servers {
		if server.Name == "" {
			return nil, errors.New("could not inspect existing MCP configuration; presentation launch refused")
		}
		if server.Name == "tofa_presentation_runtime" {
			return nil, errors.New("presentation MCP provider conflicts with existing configuration; launch refused")
		}
	}
	value := `{command=` + strconv.Quote(python) + `,args=["-I","-B",` + strconv.Quote(e.Script) +
		`,"mcp","--runtime-root",` + strconv.Quote(e.Root) + `],enabled=true,enabled_tools=["load_workspace_dependencies"]}`
	return []string{"-c", "mcp_servers.tofa_presentation_runtime=" + value}, nil
}

func (a *App) evaluationContext(ctx context.Context, path string) (*App, context.Context, context.CancelFunc, error) {
	if path == "" {
		return a, ctx, func() {}, nil
	}
	info, err := os.Lstat(path)
	if err != nil || !info.Mode().IsRegular() || info.Mode().Perm()&0077 != 0 || info.Size() > 4096 {
		return nil, nil, nil, errors.New("evaluation observer requires a private regular configuration file")
	}
	file, err := os.Open(path)
	if err != nil {
		return nil, nil, nil, err
	}
	defer file.Close()
	var config evaluationObserver
	decoder := json.NewDecoder(io.LimitReader(file, 4097))
	decoder.DisallowUnknownFields()
	if decoder.Decode(&config) != nil || decoder.Decode(new(any)) != io.EOF {
		return nil, nil, nil, errors.New("invalid evaluation observer configuration")
	}
	u, err := url.Parse(config.Endpoint)
	if err != nil || u.Scheme != "http" || u.Hostname() != "127.0.0.1" || u.Port() == "" ||
		u.User != nil || u.Path != "" || u.RawQuery != "" || u.Fragment != "" ||
		(config.Version != 1 && config.Version != 2) || len(config.Secret) < 20 ||
		!((config.Version == 1 && (config.Seconds == 180 || config.Seconds == 900)) || (config.Version == 2 && (config.Seconds == 600 || config.Seconds == 900))) || runtime.GOOS != "darwin" {
		return nil, nil, nil, errors.New("unsupported evaluation observer contract")
	}
	launch := *a
	launch.evaluation = &config
	bounded, cancel := context.WithTimeout(ctx, time.Duration(config.Seconds)*time.Second)
	return &launch, bounded, cancel, nil
}

func (e *evaluationObserver) register(ctx context.Context, adapter *requestAdapter) error {
	registration := map[string]any{"endpoint": adapter.endpoint, "token": adapter.token}
	if e.Version == 2 {
		if adapter.inferenceToken == "" {
			return errors.New("native-account observer requires isolated inference authorization")
		}
		registration = map[string]any{"version": 2, "endpoint": adapter.endpoint, "control_token": adapter.token, "inference_token": adapter.inferenceToken}
	}
	body, _ := json.Marshal(registration)
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, e.Endpoint+"/register", bytes.NewReader(body))
	if err != nil {
		return err
	}
	request.Header.Set("Authorization", "Bearer "+e.Secret)
	request.Header.Set("Content-Type", "application/json")
	client := &http.Client{Timeout: 5 * time.Second, Transport: &http.Transport{Proxy: nil},
		CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }}
	defer client.CloseIdleConnections()
	response, err := client.Do(request)
	if err != nil {
		return errors.New("evaluation observer unavailable; launch refused")
	}
	defer response.Body.Close()
	var ack struct {
		Ready bool `json:"ready"`
	}
	if response.StatusCode != 200 || json.NewDecoder(io.LimitReader(response.Body, 1024)).Decode(&ack) != nil || !ack.Ready {
		return errors.New("evaluation observer did not accept this launch")
	}
	adapter.endpoint = e.Endpoint
	return nil
}
