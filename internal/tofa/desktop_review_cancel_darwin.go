package tofa

import (
	"bytes"
	"encoding/hex"
	"encoding/json"
	"errors"
	"net/http"
	"net/url"
	"strconv"
	"time"
)

func cancelDesktopReview(endpoint, token string, params json.RawMessage) error {
	failure := errors.New("authenticated desktop review cancellation failed")
	u, err := url.Parse(endpoint)
	if err != nil || u.Scheme != "http" || u.Hostname() != "127.0.0.1" || u.User != nil || u.Path != "" || u.RawQuery != "" || u.Fragment != "" {
		return failure
	}
	port, err := strconv.Atoi(u.Port())
	if err != nil || port < 1 || port > 65535 {
		return failure
	}
	credential, err := hex.DecodeString(token)
	if err != nil || len(credential) != 32 {
		return failure
	}
	fields, err := routingObject(params)
	if err != nil || len(fields) != 2 {
		return failure
	}
	thread, okThread := provenanceID(fields["threadId"])
	turn, okTurn := provenanceID(fields["turnId"])
	if !okThread || !okTurn {
		return failure
	}
	body, _ := json.Marshal(map[string]string{"thread_id": thread, "turn_id": turn})
	request, err := http.NewRequest(http.MethodPost, endpoint+"/desktop-review-cancel", bytes.NewReader(body))
	if err != nil {
		return failure
	}
	request.Header.Set("Authorization", "Bearer "+token)
	request.Header.Set("Content-Type", "application/json")
	transport := &http.Transport{Proxy: nil}
	defer transport.CloseIdleConnections()
	client := &http.Client{Transport: transport, Timeout: 3 * time.Second, CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }}
	response, err := client.Do(request)
	if err != nil {
		return failure
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusNoContent {
		return failure
	}
	return nil
}
