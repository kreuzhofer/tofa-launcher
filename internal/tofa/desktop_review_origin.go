package tofa

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"strings"
	"sync"
)

// Origins are immutable for a launch. Retain completed/cancelled turns so a
// delayed inspection continuation cannot acquire another turn's reviewer.
// Saturation fails closed instead of evicting provenance still in flight.
type reviewOrigins struct {
	mu     sync.Mutex
	turns  map[[2]string]*reviewOrigin
	parent context.Context
}

type reviewOrigin struct {
	service   inferenceService
	context   context.Context
	cancel    context.CancelFunc
	cancelled bool
}

func provenanceID(value json.RawMessage) (string, bool) {
	var id string
	if json.Unmarshal(value, &id) != nil || len(id) == 0 || len(id) > 256 || strings.TrimSpace(id) != id || strings.ContainsAny(id, "\r\n\t") {
		return "", false
	}
	return id, true
}

func (o *reviewOrigins) route(body []byte, route *desktopRoute, authenticated bool) (bool, error) {
	if route == nil || route.services == nil || !authenticated {
		return nativeMainRequest(body, route)
	}
	payload, err := routingObject(body)
	if err != nil {
		return false, err
	}
	var metadata map[string]json.RawMessage
	if raw := payload["client_metadata"]; len(raw) > 0 && string(raw) != "null" {
		metadata, err = routingObject(raw)
		if err != nil {
			return false, errors.New("invalid or ambiguous originating-work metadata")
		}
	}
	var subagent string
	if raw, exists := metadata["x-openai-subagent"]; exists && json.Unmarshal(raw, &subagent) != nil {
		return false, errors.New("invalid originating-work role")
	}
	_, _, _, review := approvalReviewFormat(payload)
	if subagent == "guardian" || review || isApprovalReviewCandidate(payload) {
		if err := uniqueReviewJSON(body, 0); err != nil {
			return false, err
		}
		if subagent != "guardian" {
			return false, errors.New("approval review requires the verified originating-work contract")
		}
		thread, threadOK := provenanceID(metadata["x-codex-parent-thread-id"])
		turn, turnOK := provenanceID(metadata["parent_turn_id"])
		if !threadOK || !turnOK {
			return false, errors.New("approval review originating thread/turn is missing or invalid")
		}
		// A review's own thread/turn IDs are distinct; only parent fields identify work.
		o.mu.Lock()
		origin, found := o.turns[[2]string{thread, turn}]
		var service inferenceService
		cancelled := false
		if found {
			service = origin.service
			cancelled = origin.cancelled
		}
		o.mu.Unlock()
		if cancelled {
			return false, errors.New("originating turn was cancelled; review cannot authorize its action")
		}
		if !found {
			return false, errors.New("approval review originating work is unavailable; action remains subject to native approval")
		}
		if service == nativeInferenceService {
			var model string
			if json.Unmarshal(payload["model"], &model) != nil || route.services[model] != nativeInferenceService || (!review && !nativeApprovalReviewFormat(payload)) {
				return false, errors.New("unsupported native approval review contract or reviewer selection")
			}
		} else if !review {
			return false, errors.New("unsupported Token Factory approval review contract")
		}
		if raw, exists := metadata["x-codex-turn-metadata"]; exists {
			var encoded string
			if json.Unmarshal(raw, &encoded) != nil {
				return false, errors.New("invalid review provenance")
			}
			nested, err := routingObject([]byte(encoded))
			if err != nil {
				return false, err
			}
			for key, want := range map[string]string{"parent_thread_id": thread, "parent_turn_id": turn, "subagent_kind": "guardian", "thread_source": "guardian_review", "turn_trigger": "guardian_review", "request_kind": "turn"} {
				if raw, exists := nested[key]; exists {
					var got string
					if json.Unmarshal(raw, &got) != nil || got != want {
						return false, errors.New("conflicting review provenance")
					}
				}
			}
		}
		var stream bool
		var input []json.RawMessage
		if json.Unmarshal(payload["stream"], &stream) != nil || !stream || json.Unmarshal(payload["input"], &input) != nil || input == nil {
			return false, errors.New("unsupported approval review streaming/history contract")
		}
		for _, key := range []string{"previous_response_id", "conversation", "prompt"} {
			if raw, ok := payload[key]; ok && string(raw) != "null" {
				return false, errors.New("approval review requires explicit full-history context")
			}
		}
		return service == nativeInferenceService, nil
	}
	native, err := nativeMainRequest(body, route)
	if err != nil {
		return false, err
	}
	if isDesktopTitle(payload["client_metadata"]) {
		return native, nil
	}
	thread, threadOK := provenanceID(metadata["thread_id"])
	turn, turnOK := provenanceID(metadata["turn_id"])
	// Main without origin may infer, but can never authorize a review later.
	if !threadOK || !turnOK {
		return native, nil
	}
	var model string
	json.Unmarshal(payload["model"], &model)
	if raw, ok := metadata["x-codex-turn-metadata"]; ok {
		var encoded string
		json.Unmarshal(raw, &encoded)
		nested, err := routingObject([]byte(encoded))
		if err != nil {
			return false, err
		}
		for key, want := range map[string]string{"thread_id": thread, "turn_id": turn, "model": model} {
			if raw, exists := nested[key]; exists {
				var got string
				if json.Unmarshal(raw, &got) != nil || got != want {
					return false, errors.New("conflicting originating-work metadata")
				}
			}
		}
	}
	service := route.services[model]
	key := [2]string{thread, turn}
	o.mu.Lock()
	defer o.mu.Unlock()
	if existing, ok := o.turns[key]; ok {
		if existing.cancelled {
			return false, errors.New("originating turn was cancelled")
		}
		if existing.service != service {
			return false, errors.New("originating turn cannot change inference service")
		}
		return native, nil
	}
	if len(o.turns) >= 4096 {
		return false, errors.New("originating-work capacity reached; relaunch before starting further work")
	}
	if o.turns == nil {
		o.turns = make(map[[2]string]*reviewOrigin)
	}
	parent := o.parent
	if parent == nil {
		parent = context.Background()
	}
	ctx, cancel := context.WithCancel(parent)
	o.turns[key] = &reviewOrigin{service: service, context: ctx, cancel: cancel}
	return native, nil
}

// Native reviewers may expose their inspection tools through the engine's
// functions namespace in a leading additional_tools item. Validate that measured
// contract independently; never flatten or rewrite its native wire payload.
func nativeApprovalReviewFormat(payload map[string]json.RawMessage) bool {
	if raw := payload["tools"]; len(raw) > 0 && string(raw) != "null" {
		return false
	}
	if raw := payload["instructions"]; len(raw) > 0 && string(raw) != "null" {
		return false
	}
	var input []json.RawMessage
	if json.Unmarshal(payload["input"], &input) != nil || len(input) < 2 {
		return false
	}
	var inventory struct {
		Type, Role string
		Tools      []struct {
			Type, Name string
			Tools      []struct {
				Type, Name string
				Format     struct{ Type, Syntax string }
			}
		}
	}
	if json.Unmarshal(input[0], &inventory) != nil || inventory.Type != "additional_tools" || inventory.Role != "developer" || len(inventory.Tools) != 1 {
		return false
	}
	namespace := inventory.Tools[0]
	if namespace.Type != "namespace" || namespace.Name != "functions" || len(namespace.Tools) != 2 {
		return false
	}
	seen := map[string]bool{}
	for _, tool := range namespace.Tools {
		if seen[tool.Name] {
			return false
		}
		seen[tool.Name] = true
		switch tool.Name {
		case "exec":
			if tool.Type != "custom" || tool.Format.Type != "grammar" || tool.Format.Syntax != "lark" {
				return false
			}
		case "wait":
			if tool.Type != "function" {
				return false
			}
		default:
			return false
		}
	}
	// Reuse exact assessment-schema and developer-policy validation, with the
	// independently verified inventory represented as its inspection-tool roles.
	validation := make(map[string]json.RawMessage, len(payload))
	for key, value := range payload {
		validation[key] = value
	}
	validation["input"], _ = json.Marshal(input[1:])
	validation["tools"] = json.RawMessage(`[{"type":"function","name":"exec_command"},{"type":"function","name":"write_stdin"},{"type":"function","name":"view_image"}]`)
	_, _, _, valid := approvalReviewFormat(validation)
	return valid
}

// Both the native client and adapter must interpret the same assessment/policy
// fields. Reject duplicate keys at every nested review boundary before proxying.
func uniqueReviewJSON(raw []byte, depth int) error {
	if depth > 64 {
		return errors.New("approval review nesting limit exceeded")
	}
	raw = bytes.TrimSpace(raw)
	if len(raw) == 0 {
		return errors.New("invalid approval review JSON")
	}
	switch raw[0] {
	case '{':
		object, err := routingObject(raw)
		if err != nil {
			return err
		}
		for _, value := range object {
			if err := uniqueReviewJSON(value, depth+1); err != nil {
				return err
			}
		}
	case '[':
		var values []json.RawMessage
		if json.Unmarshal(raw, &values) != nil {
			return errors.New("invalid approval review array")
		}
		for _, value := range values {
			if err := uniqueReviewJSON(value, depth+1); err != nil {
				return err
			}
		}
	}
	return nil
}

// Cancellation arrives only through the relay's independent control capability,
// before it forwards the exact native turn/interrupt request. Tombstones also
// cover an interruption preceding the turn's first inference request.
func (o *reviewOrigins) cancelTurn(body []byte) error {
	fields, err := routingObject(body)
	if err != nil || len(fields) != 2 {
		return errors.New("invalid review cancellation")
	}
	thread, okThread := provenanceID(fields["thread_id"])
	turn, okTurn := provenanceID(fields["turn_id"])
	if !okThread || !okTurn {
		return errors.New("invalid review cancellation provenance")
	}
	o.mu.Lock()
	defer o.mu.Unlock()
	key := [2]string{thread, turn}
	origin := o.turns[key]
	if origin == nil {
		if len(o.turns) >= 4096 {
			return errors.New("review cancellation capacity reached")
		}
		if o.turns == nil {
			o.turns = make(map[[2]string]*reviewOrigin)
		}
		origin = &reviewOrigin{}
		o.turns[key] = origin
	}
	origin.cancelled = true
	if origin.cancel != nil {
		origin.cancel()
	}
	return nil
}

func (o *reviewOrigins) bindReview(body []byte, request *http.Request) (*http.Request, func(), error) {
	var payload struct {
		Metadata map[string]string `json:"client_metadata"`
	}
	if json.Unmarshal(body, &payload) != nil {
		return nil, nil, errors.New("invalid review lifecycle metadata")
	}
	if payload.Metadata["x-openai-subagent"] != "guardian" {
		return request, func() {}, nil
	}
	key := [2]string{payload.Metadata["x-codex-parent-thread-id"], payload.Metadata["parent_turn_id"]}
	o.mu.Lock()
	origin := o.turns[key]
	if origin == nil || origin.cancelled {
		o.mu.Unlock()
		return nil, nil, errors.New("originating review was cancelled or unavailable")
	}
	originContext := origin.context
	o.mu.Unlock()
	// Make the origin the cancellation parent: its control acknowledgment follows
	// synchronous cancellation of each review context, not a scheduled callback.
	ctx, cancel := context.WithCancel(originContext)
	stop := context.AfterFunc(request.Context(), cancel)
	return request.WithContext(ctx), func() { stop(); cancel() }, nil
}
