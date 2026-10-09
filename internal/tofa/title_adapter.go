package tofa

import (
	"encoding/json"
	"errors"
	"reflect"
)

// Captured from desktop 26.915.31945 / engine 0.155.0-alpha.9.2.
// The desktop independently parses JSON and validates title and description.
const desktopTitleSchema = `{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object","properties":{"title":{"type":"string","minLength":1,"maxLength":36},"description":{"type":"string","minLength":1}},"required":["title","description"],"additionalProperties":false}`

const desktopNamingModel = "nvidia/Nemotron-3_5-Lightning"

func isDesktopTitle(metadataJSON json.RawMessage) bool {
	var metadata map[string]json.RawMessage
	var turnJSON string
	var turn struct {
		Source  string `json:"thread_source"`
		Trigger string `json:"turn_trigger"`
	}
	json.Unmarshal(metadataJSON, &metadata)
	json.Unmarshal(metadata["x-codex-turn-metadata"], &turnJSON)
	return json.Unmarshal([]byte(turnJSON), &turn) == nil && turn.Source == "thread_title" && turn.Trigger == "thread_title"
}

// The current shared-profile desktop retains Luna in its native catalog. This
// explicit launcher policy translates its captured code-mode title request. It
// does not change the catalog or the engine's thread settings.
func routeDesktopTitle(body []byte) ([]byte, bool, error) {
	var payload map[string]json.RawMessage
	if err := json.Unmarshal(body, &payload); err != nil {
		return nil, false, err
	}
	var model string
	json.Unmarshal(payload["model"], &model)
	if (model != "gpt-5.6-luna" && model != "gpt-6-luna") || !isDesktopTitle(payload["client_metadata"]) {
		return body, false, nil
	}
	_, _, valid := desktopTitleFormat(payload)
	unsupported := errors.New("automatic title generation is unavailable: unsupported desktop title contract; request was not sent upstream")
	if !valid || len(payload["tools"]) != 0 || len(payload["instructions"]) != 0 {
		return nil, false, unsupported
	}
	var input []json.RawMessage
	if json.Unmarshal(payload["input"], &input) != nil || len(input) == 0 {
		return nil, false, unsupported
	}
	var additional struct {
		Type  string          `json:"type"`
		Role  string          `json:"role"`
		ID    string          `json:"id"`
		Tools json.RawMessage `json:"tools"`
	}
	var fields map[string]json.RawMessage
	if json.Unmarshal(input[0], &additional) != nil || json.Unmarshal(input[0], &fields) != nil || len(fields) != 4 || additional.Type != "additional_tools" || additional.Role != "developer" || additional.ID == "" || !desktopTitleCodeTools(additional.Tools, model) {
		return nil, false, unsupported
	}
	for _, item := range input[1:] {
		var entry struct{ Type string }
		if json.Unmarshal(item, &entry) != nil || entry.Type == "additional_tools" {
			return nil, false, unsupported
		}
	}
	// Lightning's Responses endpoint rejects namespace tools, include, reasoning
	// and prompt_cache_key (live engine replay, #111). Naming is explicitly
	// tool-free and uses provider-default reasoning. Retain the native prompt
	// and output schema; the desktop still validates and persists the result.
	delete(payload, "include")
	delete(payload, "reasoning")
	delete(payload, "prompt_cache_key")
	payload["input"], _ = json.Marshal(input[1:])
	payload["model"], _ = json.Marshal(desktopNamingModel)
	result, err := json.Marshal(payload)
	return result, true, err
}

func desktopTitleCodeTools(raw json.RawMessage, model string) bool {
	var namespaces []struct {
		Type  string `json:"type"`
		Name  string `json:"name"`
		Tools []struct {
			Type string `json:"type"`
			Name string `json:"name"`
		} `json:"tools"`
	}
	allowed := map[string]map[string]string{
		"functions": {"exec": "custom", "wait": "function", "request_user_input": "function"},
	}
	if model == "gpt-6-luna" {
		allowed["functions"]["request_user_input_async"] = "function"
		allowed["clock"] = map[string]string{"sleep": "function"}
		allowed["collaboration"] = map[string]string{
			"followup_task": "function", "interrupt_agent": "function", "list_agents": "function",
			"send_message": "function", "spawn_agent": "function", "wait_agent": "function",
		}
	}
	if json.Unmarshal(raw, &namespaces) != nil || len(namespaces) != len(allowed) {
		return false
	}
	for _, namespace := range namespaces {
		tools, found := allowed[namespace.Name]
		if !found || namespace.Type != "namespace" || len(namespace.Tools) != len(tools) {
			return false
		}
		for _, tool := range namespace.Tools {
			kind, found := tools[tool.Name]
			if !found || tool.Type != kind {
				return false
			}
			delete(tools, tool.Name)
		}
		delete(allowed, namespace.Name)
	}
	return true
}

func desktopTitleFormat(payload map[string]json.RawMessage) (map[string]json.RawMessage, any, bool) {
	var textOptions, format map[string]json.RawMessage
	if json.Unmarshal(payload["text"], &textOptions) != nil || json.Unmarshal(textOptions["format"], &format) != nil {
		return nil, nil, false
	}
	var schema, expected any
	json.Unmarshal(format["schema"], &schema)
	json.Unmarshal([]byte(desktopTitleSchema), &expected)
	var kind, name, choice string
	var strict *bool
	json.Unmarshal(format["type"], &kind)
	json.Unmarshal(format["name"], &name)
	json.Unmarshal(payload["tool_choice"], &choice)
	valid := reflect.DeepEqual(schema, expected) && len(format) == 4 && kind == "json_schema" && name == "codex_output_schema" && json.Unmarshal(format["strict"], &strict) == nil && strict != nil && *strict && choice == "auto"
	return textOptions, schema, valid
}

func adaptDesktopTitle(body []byte) ([]byte, bool, error) {
	var payload map[string]json.RawMessage
	if err := json.Unmarshal(body, &payload); err != nil {
		return nil, false, err
	}
	var model string
	json.Unmarshal(payload["model"], &model)
	if model != "moonshotai/Kimi-K3" || !isDesktopTitle(payload["client_metadata"]) {
		return body, false, nil
	}
	unsupported := errors.New("unsupported Kimi-K3 desktop title contract; request was not sent upstream")
	textOptions, schema, valid := desktopTitleFormat(payload)
	if !valid {
		return nil, false, unsupported
	}
	var tools []struct {
		Type  string          `json:"type"`
		Name  string          `json:"name"`
		Tools json.RawMessage `json:"tools"`
	}
	allowed := map[string]bool{
		"exec_command": true, "write_stdin": true, "list_mcp_resources": true,
		"list_mcp_resource_templates": true, "read_mcp_resource": true,
		"request_user_input": true, "view_image": true, "mcp__node_repl": true,
		"get_goal": true, "create_goal": true, "update_goal": true,
	}
	if json.Unmarshal(payload["tools"], &tools) != nil || len(tools) != len(allowed) {
		return nil, false, unsupported
	}
	for _, tool := range tools {
		if !allowed[tool.Name] {
			return nil, false, unsupported
		}
		delete(allowed, tool.Name)
		if tool.Name == "mcp__node_repl" {
			var members []struct {
				Type string `json:"type"`
				Name string `json:"name"`
			}
			names := map[string]bool{"js": true, "js_add_node_module_dir": true, "js_reset": true}
			if tool.Type != "namespace" || json.Unmarshal(tool.Tools, &members) != nil || len(members) != len(names) {
				return nil, false, unsupported
			}
			for _, member := range members {
				if member.Type != "function" || !names[member.Name] {
					return nil, false, unsupported
				}
				delete(names, member.Name)
			}
		} else if tool.Type != "function" || len(tool.Tools) != 0 {
			return nil, false, unsupported
		}
	}
	var instructions *string
	if json.Unmarshal(payload["instructions"], &instructions) != nil || instructions == nil {
		return nil, false, unsupported
	}
	// Preserve tools: title generation can require read-only app lookups. Only
	// the constrained-decoding location changes; the full schema remains guidance.
	canonicalSchema, _ := json.Marshal(schema)
	*instructions += "\n\nFor this desktop thread title, return your final answer as JSON matching this complete schema (no markdown or extra text):\n" + string(canonicalSchema)
	payload["instructions"], _ = json.Marshal(instructions)
	delete(textOptions, "format")
	payload["text"], _ = json.Marshal(textOptions)
	result, err := json.Marshal(payload)
	return result, true, err
}
