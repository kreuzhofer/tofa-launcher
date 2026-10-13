package tofa

import (
	"bufio"
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"mime"
	"net/http"
	"strings"
)

const namespaceAliasPrefix = "tofa_ns_"
const maxNamespaceEvent = 16 << 20

type namespaceContextKey struct{}
type toolAddress struct{ namespace, name string }
type namespaceTranslation struct {
	aliases map[string]toolAddress
	flat    map[string]string
}

func namespaceAlias(address toolAddress) string {
	// A fixed-size, deterministic name works across turns and catalog changes.
	sum := sha256.Sum256([]byte(address.namespace + "\x00" + address.name))
	return namespaceAliasPrefix + hex.EncodeToString(sum[:28])
}

func decodeToolObject(raw []byte) (map[string]any, error) {
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.UseNumber()
	var value map[string]any
	if decoder.Decode(&value) != nil || value == nil || decoder.Decode(new(any)) != io.EOF {
		return nil, errors.New("invalid namespace translation JSON")
	}
	return value, nil
}

func toolString(value any) string { text, _ := value.(string); return text }
func validToolPart(value string) bool {
	return value != "" && len(value) <= 1024 && !strings.ContainsAny(value, "\x00\r\n")
}

// Only the two model/provider combinations with a retained flat-vs-namespace
// diagnostic are adapted. The native client's definitions and call identities
// are restored on the response boundary; native execution/approval stays native.
func adaptNamespaces(body []byte) ([]byte, *namespaceTranslation, error) {
	payload, err := decodeToolObject(body)
	if err != nil {
		return nil, nil, err
	}
	model := toolString(payload["model"])
	if model != "moonshotai/Kimi-K3" && model != "zai-org/GLM-5.3" {
		return body, nil, nil
	}
	tools, _ := payload["tools"].([]any)
	input, _ := payload["input"].([]any)
	active := false
	for _, raw := range tools {
		if item, ok := raw.(map[string]any); ok && item["type"] == "namespace" {
			active = true
		}
	}
	for _, raw := range input {
		if item, ok := raw.(map[string]any); ok && item["type"] == "function_call" && item["namespace"] != nil {
			active = true
		}
	}
	if !active {
		return body, nil, nil
	}
	mapping := &namespaceTranslation{aliases: map[string]toolAddress{}, flat: map[string]string{}}
	known := map[string]toolAddress{}
	reserve := func(address toolAddress) (string, error) {
		if !validToolPart(address.namespace) || !validToolPart(address.name) {
			return "", errors.New("invalid native namespace or tool name")
		}
		alias := namespaceAlias(address)
		if old, exists := known[alias]; exists && old != address {
			return "", errors.New("namespace alias collision")
		}
		known[alias] = address
		return alias, nil
	}
	flat := []any{}
	namespaces := map[string]bool{}
	for _, raw := range tools {
		tool, ok := raw.(map[string]any)
		if !ok {
			return nil, nil, errors.New("invalid native tool definition")
		}
		kind, name := toolString(tool["type"]), toolString(tool["name"])
		if kind != "namespace" {
			if kind != "function" && kind != "custom" {
				return nil, nil, errors.New("unsupported tool definition alongside namespaces")
			}
			if !validToolPart(name) || strings.HasPrefix(name, namespaceAliasPrefix) || mapping.flat[name] != "" {
				return nil, nil, errors.New("duplicate or reserved flat tool name")
			}
			mapping.flat[name] = kind
			flat = append(flat, tool)
			continue
		}
		members, ok := tool["tools"].([]any)
		if !ok || len(members) == 0 || namespaces[name] || !validToolPart(name) {
			return nil, nil, errors.New("invalid or duplicate namespace definition")
		}
		for key := range tool {
			if key != "type" && key != "name" && key != "description" && key != "tools" {
				return nil, nil, errors.New("unsupported namespace definition field")
			}
		}
		if desc, exists := tool["description"]; exists {
			if _, ok := desc.(string); !ok {
				return nil, nil, errors.New("invalid namespace description")
			}
		}
		namespaces[name] = true
		for _, member := range members {
			function, ok := member.(map[string]any)
			if !ok || function["type"] != "function" || function["namespace"] != nil {
				return nil, nil, errors.New("unsupported namespaced tool; only functions are qualified")
			}
			address := toolAddress{name, toolString(function["name"])}
			alias, err := reserve(address)
			if err != nil {
				return nil, nil, err
			}
			if _, exists := mapping.aliases[alias]; exists {
				return nil, nil, errors.New("duplicate namespaced function")
			}
			mapping.aliases[alias] = address
			function["name"] = alias
			if description := toolString(tool["description"]); description != "" {
				if value, exists := function["description"]; exists {
					if _, ok := value.(string); !ok {
						return nil, nil, errors.New("invalid function description")
					}
				}
				function["description"] = description + "\n\n" + toolString(function["description"])
			}
			flat = append(flat, function)
		}
	}
	payload["tools"] = flat
	for _, raw := range input {
		item, ok := raw.(map[string]any)
		if !ok || item["type"] != "function_call" {
			continue
		}
		ns := item["namespace"]
		if ns == nil {
			if strings.HasPrefix(toolString(item["name"]), namespaceAliasPrefix) {
				return nil, nil, errors.New("provider alias in native history")
			}
			continue
		}
		alias, err := reserve(toolAddress{toolString(ns), toolString(item["name"])})
		if err != nil {
			return nil, nil, err
		}
		item["name"] = alias
		delete(item, "namespace")
	}
	if choice, ok := payload["tool_choice"].(map[string]any); ok {
		if choice["type"] == "allowed_tools" {
			allowed, ok := choice["tools"].([]any)
			if !ok {
				return nil, nil, errors.New("invalid allowed tool choice")
			}
			for _, raw := range allowed {
				item, ok := raw.(map[string]any)
				if !ok {
					return nil, nil, errors.New("invalid allowed tool choice")
				}
				if err := mapping.adaptChoice(item); err != nil {
					return nil, nil, err
				}
			}
		} else if err := mapping.adaptChoice(choice); err != nil {
			return nil, nil, err
		}
	}
	adjusted, err := json.Marshal(payload)
	return adjusted, mapping, err
}

func (mapping *namespaceTranslation) adaptChoice(choice map[string]any) error {
	kind, name := toolString(choice["type"]), toolString(choice["name"])
	if ns, exists := choice["namespace"]; exists {
		address := toolAddress{toolString(ns), name}
		alias := namespaceAlias(address)
		if mapping.aliases[alias] != address || !validToolPart(address.namespace) || kind != "function" {
			return errors.New("unmapped namespaced tool choice")
		}
		choice["name"] = alias
		delete(choice, "namespace")
		return nil
	}
	if mapping.flat[name] != kind || name == "" {
		return errors.New("unmapped flat tool choice")
	}
	return nil
}

func (mapping *namespaceTranslation) restoreItem(raw any) error {
	item, ok := raw.(map[string]any)
	if !ok {
		return errors.New("invalid response output item")
	}
	kind := toolString(item["type"])
	if kind != "function_call" && kind != "custom_tool_call" {
		return nil
	}
	name := toolString(item["name"])
	if item["namespace"] != nil {
		return errors.New("unexpected provider namespace")
	}
	if address, ok := mapping.aliases[name]; ok && kind == "function_call" {
		item["name"] = address.name
		item["namespace"] = address.namespace
		return nil
	}
	if (kind == "function_call" && mapping.flat[name] == "function") || (kind == "custom_tool_call" && mapping.flat[name] == "custom") {
		return nil
	}
	return errors.New("unmapped provider tool call")
}

func (mapping *namespaceTranslation) restoreJSON(raw []byte) ([]byte, error) {
	value, err := decodeToolObject(raw)
	if err != nil {
		return nil, err
	}
	if value["type"] == "response.function_call_arguments.done" && value["name"] != nil {
		call := map[string]any{"type": "function_call", "name": value["name"], "namespace": value["namespace"]}
		if err := mapping.restoreItem(call); err != nil {
			return nil, err
		}
		value["name"] = call["name"]
		if call["namespace"] != nil {
			value["namespace"] = call["namespace"]
		}
	}
	if item, exists := value["item"]; exists {
		if err = mapping.restoreItem(item); err != nil {
			return nil, err
		}
	}
	envelope := value
	if response, exists := value["response"]; exists {
		var ok bool
		envelope, ok = response.(map[string]any)
		if !ok {
			return nil, errors.New("invalid response envelope")
		}
	}
	if output, exists := envelope["output"]; exists {
		items, ok := output.([]any)
		if !ok {
			return nil, errors.New("invalid response output")
		}
		for _, item := range items {
			if err = mapping.restoreItem(item); err != nil {
				return nil, err
			}
		}
	}
	return json.Marshal(value)
}

// Each complete SSE event is validated before forwarding; argument deltas,
// reasoning, comments and unknown fields stay intact. Buffering is bounded per
// event, not per response. Closing the downstream body also closes upstream.
func (mapping *namespaceTranslation) restoreSSE(event []byte) ([]byte, error) {
	lines := bytes.Split(event, []byte("\n"))
	data := []string{}
	for _, line := range lines {
		line = bytes.TrimSuffix(line, []byte("\r"))
		if bytes.HasPrefix(line, []byte("data:")) {
			data = append(data, strings.TrimPrefix(string(line[5:]), " "))
		}
	}
	if len(data) == 0 || strings.Join(data, "\n") == "[DONE]" {
		return event, nil
	}
	restored, err := mapping.restoreJSON([]byte(strings.Join(data, "\n")))
	if err != nil {
		return nil, err
	}
	output := [][]byte{}
	written := false
	for _, line := range lines {
		if bytes.HasPrefix(line, []byte("data:")) {
			if !written {
				output = append(output, append([]byte("data: "), restored...))
				written = true
			}
		} else {
			output = append(output, line)
		}
	}
	return bytes.Join(output, []byte("\n")), nil
}

type translatedBody struct {
	*io.PipeReader
	upstream io.ReadCloser
}

func (body *translatedBody) Close() error { body.upstream.Close(); return body.PipeReader.Close() }

func (mapping *namespaceTranslation) restoreResponse(response *http.Response) error {
	if response.StatusCode >= 300 {
		return nil
	}
	media, _, err := mime.ParseMediaType(response.Header.Get("Content-Type"))
	if err != nil {
		return errors.New("namespace response content type unavailable")
	}
	if media == "application/json" {
		raw, err := io.ReadAll(io.LimitReader(response.Body, maxNamespaceEvent+1))
		response.Body.Close()
		if err != nil || len(raw) > maxNamespaceEvent {
			return errors.New("namespace response exceeds buffer or is unreadable")
		}
		adjusted, err := mapping.restoreJSON(raw)
		if err != nil {
			return err
		}
		response.Body = io.NopCloser(bytes.NewReader(adjusted))
	} else if media == "text/event-stream" {
		upstream := response.Body
		reader, writer := io.Pipe()
		response.Body = &translatedBody{reader, upstream}
		go func() {
			defer upstream.Close()
			scanner := bufio.NewScanner(upstream)
			scanner.Buffer(make([]byte, 4096), maxNamespaceEvent)
			event := []byte{}
			for scanner.Scan() {
				line := scanner.Bytes()
				if len(event)+len(line)+1 > maxNamespaceEvent {
					writer.CloseWithError(errors.New("namespace stream event too large"))
					return
				}
				event = append(event, line...)
				event = append(event, '\n')
				if len(bytes.TrimSuffix(line, []byte("\r"))) == 0 {
					adjusted, err := mapping.restoreSSE(event)
					if err != nil {
						// Only a fixed diagnostic reaches the client; never forward the
						// rejected provider call or its arguments.
						io.WriteString(writer, "event: error\ndata: {\"type\":\"error\",\"code\":\"namespace_translation_failed\",\"message\":\"Request adapter rejected an invalid or unmapped tool response.\"}\n\n")
						writer.CloseWithError(err)
						return
					}
					if _, err = writer.Write(adjusted); err != nil {
						return
					}
					event = event[:0]
				}
			}
			err := scanner.Err()
			if err == nil && len(event) != 0 {
				err = errors.New("incomplete namespace stream event")
			}
			writer.CloseWithError(err)
		}()
	} else {
		return errors.New("unsupported namespace response content type")
	}
	response.ContentLength = -1
	response.Header.Del("Content-Length")
	response.Header.Del("ETag")
	return nil
}
