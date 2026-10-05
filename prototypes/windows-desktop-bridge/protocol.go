package main

import (
	"bytes"
	"encoding/json"
	"sync"
)

// Metadata only. Keep opaque IDs in memory to correlate replies; never record them.
type protocol struct {
	mu      sync.Mutex
	pending map[string]string
	log     *evidence
}
type observer struct {
	protocol *protocol
	request  bool
	line     []byte
	dropping bool
}

func (o *observer) Write(p []byte) (int, error) {
	n := len(p)
	for len(p) > 0 {
		end := bytes.IndexByte(p, '\n')
		piece := p
		if end >= 0 {
			piece = p[:end]
		}
		if !o.dropping {
			if len(o.line)+len(piece) > 1024*1024 {
				o.line = nil
				o.dropping = true
			} else {
				o.line = append(o.line, piece...)
			}
		}
		if end < 0 {
			break
		}
		if !o.dropping {
			o.observe(o.line)
		}
		o.line = nil
		o.dropping = false
		p = p[end+1:]
	}
	return n, nil
}
func (o *observer) observe(line []byte) {
	var message struct {
		ID     json.RawMessage `json:"id"`
		Method string          `json:"method"`
		Result json.RawMessage `json:"result"`
		Error  json.RawMessage `json:"error"`
		Params json.RawMessage `json:"params"`
	}
	if json.Unmarshal(line, &message) != nil {
		return
	}
	t := o.protocol
	t.mu.Lock()
	defer t.mu.Unlock()
	if o.request {
		switch message.Method {
		case "initialize", "config/read":
			if len(message.ID) > 0 && len(t.pending) < 32 {
				t.pending[string(message.ID)] = message.Method
			}
			t.log.write(message.Method+"_request", map[string]any{})
		case "thread/start", "turn/start", "command/exec":
			t.log.write("action_request", map[string]any{"method": message.Method})
		}
		return
	}
	if message.Method == "item/autoApprovalReview/completed" {
		var params struct {
			Review struct {
				Status string `json:"status"`
			} `json:"review"`
		}
		status := "other"
		if json.Unmarshal(message.Params, &params) == nil {
			switch params.Review.Status {
			case "approved", "denied", "inProgress":
				status = params.Review.Status
			}
		}
		t.log.write("native_review", map[string]any{"status": status})
		return
	}
	method, ok := t.pending[string(message.ID)]
	if !ok || (len(message.Result) == 0 && len(message.Error) == 0) {
		return
	}
	delete(t.pending, string(message.ID))
	fields := map[string]any{"success": len(message.Result) > 0 && len(message.Error) == 0}
	if method == "config/read" && len(message.Result) > 0 {
		var result struct {
			Config map[string]json.RawMessage `json:"config"`
		}
		if json.Unmarshal(message.Result, &result) == nil {
			for _, key := range []string{"approval_policy", "approvals_reviewer", "sandbox_mode"} {
				raw, present := result.Config[key]
				if !present {
					fields[key] = "absent"
					continue
				}
				if bytes.Equal(bytes.TrimSpace(raw), []byte("null")) {
					fields[key] = "unset"
					continue
				}
				var value string
				if json.Unmarshal(result.Config[key], &value) == nil {
					switch value {
					case "untrusted", "on-failure", "on-request", "never", "user", "auto_review", "guardian_subagent", "read-only", "workspace-write", "danger-full-access":
						fields[key] = value
					default:
						fields[key] = "other"
					}
				}
			}
			var features map[string]bool
			if json.Unmarshal(result.Config["features"], &features) == nil {
				if value, ok := features["windows_sandbox_service"]; ok {
					fields["windows_sandbox_service"] = value
				}
			}
		}
	}
	name := method + "_response"
	if method == "initialize" {
		name = "initialize_response"
	}
	t.log.write(name, fields)
}
