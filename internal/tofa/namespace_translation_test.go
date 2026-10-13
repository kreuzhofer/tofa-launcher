package tofa

import (
	"encoding/json"
	"io"
	"net/http"
	"strings"
	"testing"
)

func TestNamespaceMappingCatalogChangesAndChoices(t *testing.T) {
	function := func(name string) any {
		return map[string]any{"type": "function", "name": name, "parameters": map[string]any{"type": "object"}}
	}
	ns := func(name string) any {
		return map[string]any{"type": "namespace", "name": name, "tools": []any{function("same")}}
	}
	input := []any{map[string]any{"type": "function_call", "namespace": "removed_namespace", "name": "same", "arguments": "{}", "call_id": "old"}, map[string]any{"type": "function_call_output", "call_id": "old", "output": "preserve"}}
	aliases := map[string]string{}
	for _, order := range [][]any{{ns("a"), function("same"), ns(strings.Repeat("b", 200))}, {ns(strings.Repeat("b", 200)), function("same"), ns("a")}} {
		payload := map[string]any{"model": "zai-org/GLM-5.3", "tools": order, "input": input, "tool_choice": map[string]any{"type": "allowed_tools", "mode": "required", "tools": []any{map[string]any{"type": "function", "namespace": "a", "name": "same"}, map[string]any{"type": "function", "name": "same"}}}}
		raw, _ := json.Marshal(payload)
		adjusted, mapping, err := adaptNamespaces(raw)
		if err != nil {
			t.Fatal(err)
		}
		got, _ := decodeToolObject(adjusted)
		for alias, address := range mapping.aliases {
			if old := aliases[address.namespace]; old != "" && old != alias {
				t.Fatal("catalog order changed alias")
			}
			aliases[address.namespace] = alias
			if len(alias) > 64 {
				t.Fatal("provider name limit exceeded")
			}
		}
		if aliases["a"] == aliases[strings.Repeat("b", 200)] {
			t.Fatal("duplicate leaves collided")
		}
		history := got["input"].([]any)[0].(map[string]any)
		if history["name"] != namespaceAlias(toolAddress{"removed_namespace", "same"}) || history["namespace"] != nil {
			t.Fatal("historical tool lost after catalog change")
		}
		choice := got["tool_choice"].(map[string]any)["tools"].([]any)[0].(map[string]any)
		if choice["name"] != aliases["a"] || choice["namespace"] != nil {
			t.Fatal("allowed tool selector was not translated")
		}
		if err := mapping.restoreItem(map[string]any{"type": "function_call", "name": history["name"]}); err == nil {
			t.Fatal("removed historical tool became executable")
		}
	}
}

func TestNamespaceMappingPassThroughScopeAndFlatTools(t *testing.T) {
	for _, raw := range []string{
		`{"model":"moonshotai/Kimi-K3","tools":[{"type":"function","name":"ordinary"}],"input":[]}`,
		`{"model":"zai-org/GLM-5.3-Flash","tools":[{"type":"namespace","name":"guardian","tools":[]}],"input":[]}`,
		`{"model":"nvidia/Nemotron-3_5-Lightning","tools":[],"input":[]}`,
	} {
		adjusted, mapping, err := adaptNamespaces([]byte(raw))
		if err != nil || mapping != nil || string(adjusted) != raw {
			t.Fatal("unaffected request changed")
		}
	}
}

func TestNamespaceResponsePreservesNonCallsAndRejectsMalformedFrames(t *testing.T) {
	mapping := &namespaceTranslation{aliases: map[string]toolAddress{"alias": {"ns", "fn"}}, flat: map[string]string{"shell": "function", "patch": "custom"}}
	for _, raw := range []string{
		`{"output":[{"type":"function_call","name":"shell","arguments":"{\"future\":9007199254740993}"}]}`,
		`{"type":"response.reasoning_text.delta","delta":"alias is plain reasoning","future":9007199254740993}`,
		`{"type":"response.function_call_arguments.delta","delta":"{\"x\":","item_id":"id"}`,
		`{"output":[{"type":"custom_tool_call","name":"patch","input":"unchanged"}]}`,
	} {
		out, err := mapping.restoreJSON([]byte(raw))
		if err != nil {
			t.Fatal(err)
		}
		var before, after any
		json.Unmarshal([]byte(raw), &before)
		json.Unmarshal(out, &after)
		a, _ := json.Marshal(before)
		b, _ := json.Marshal(after)
		if string(a) != string(b) {
			t.Fatalf("unrelated data changed: %s", out)
		}
	}
	for _, raw := range []string{
		`{"output":[{"type":"function_call","name":"unknown"}]}`,
		`{"output":[{"type":"function_call","name":"alias","namespace":"injected"}]}`,
		`{"output":[{"type":"custom_tool_call","name":"alias"}]}`,
		`{"output":{}}`, `null`, `{"output":[]} {}`, `{"item":null}`,
	} {
		if _, err := mapping.restoreJSON([]byte(raw)); err == nil {
			t.Fatalf("malformed response accepted: %s", raw)
		}
	}
	frame := []byte("event: response.output_item.done\r\ndata: {\"item\":\r\ndata: {\"type\":\"function_call\",\"name\":\"alias\"}}\r\n\r\n")
	restored, err := mapping.restoreSSE(frame)
	if err != nil || !strings.Contains(string(restored), `"namespace":"ns"`) {
		t.Fatalf("multiline SSE failed: %v", err)
	}
	response := &http.Response{StatusCode: 200, Header: http.Header{"Content-Type": []string{"text/event-stream"}}, Body: io.NopCloser(strings.NewReader("data: {}\n"))}
	if err := mapping.restoreResponse(response); err != nil {
		t.Fatal(err)
	}
	defer response.Body.Close()
	if _, err := io.ReadAll(response.Body); err == nil {
		t.Fatal("truncated stream accepted")
	}
	oversized := &http.Response{StatusCode: 200, Header: http.Header{"Content-Type": []string{"application/json"}}, Body: io.NopCloser(strings.NewReader(strings.Repeat(" ", maxNamespaceEvent+1)))}
	if err := mapping.restoreResponse(oversized); err == nil {
		t.Fatal("oversized JSON accepted")
	}
}
