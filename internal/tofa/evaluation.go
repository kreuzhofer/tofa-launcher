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
	"runtime"
	"time"
)

type evaluationObserver struct {
	Version  int    `json:"version"`
	Endpoint string `json:"endpoint"`
	Secret   string `json:"secret"`
	Seconds  int    `json:"seconds"`
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
		config.Version != 1 || len(config.Secret) < 20 ||
		(config.Seconds != 180 && config.Seconds != 900) || runtime.GOOS != "darwin" {
		return nil, nil, nil, errors.New("unsupported evaluation observer contract")
	}
	launch := *a
	launch.evaluation = &config
	bounded, cancel := context.WithTimeout(ctx, time.Duration(config.Seconds)*time.Second)
	return &launch, bounded, cancel, nil
}

func (e *evaluationObserver) register(ctx context.Context, adapter *requestAdapter) error {
	body, _ := json.Marshal(map[string]string{"endpoint": adapter.endpoint, "token": adapter.token})
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
