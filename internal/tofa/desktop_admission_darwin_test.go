package tofa

import (
	"archive/zip"
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
	"time"
)

func TestDesktopAdmissionDeclarationIsBoundedAndSingleUse(t *testing.T) {
	os.MkdirAll("/tmp/tofa-presentation-validation", 0700)
	root, err := os.MkdirTemp("/tmp/tofa-presentation-validation", "admission-test-")
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { os.RemoveAll(root) })
	now := time.Now().UTC().Truncate(time.Second)
	id := desktopAdmissionIdentity{Source: strings.Repeat("a", 40), Home: "/owned/home", Profile: "/owned/profile", Runtime: "/owned/runtime", Harness: "/owned/harness", Hashes: map[string]string{"launcher": strings.Repeat("b", 64)}}
	decl := desktopCandidateDeclaration{Schema: desktopDeclarationSchema, Attempt: "attempt-one", Case: "clean-exit", Root: root, Identity: id, Issued: now, Expires: now.Add(600 * time.Second), Seconds: 600, Requests: 8}
	path := filepath.Join(root, "declaration.json")
	write := func(d desktopCandidateDeclaration) {
		raw, _ := json.Marshal(d)
		if err := os.WriteFile(path, raw, 0600); err != nil {
			t.Fatal(err)
		}
	}
	write(decl)
	for _, mutation := range []struct {
		name   string
		mutate func(*desktopCandidateDeclaration)
	}{
		{"expired", func(d *desktopCandidateDeclaration) { d.Expires = now.Add(-time.Second) }},
		{"short window", func(d *desktopCandidateDeclaration) { d.Seconds = 180 }},
		{"wrong identity", func(d *desktopCandidateDeclaration) { d.Identity.Home = "/other" }},
		{"unknown case", func(d *desktopCandidateDeclaration) { d.Case = "anything" }},
		{"wrong root", func(d *desktopCandidateDeclaration) { d.Root = filepath.Dir(root) }},
	} {
		t.Run(mutation.name, func(t *testing.T) {
			d := decl
			mutation.mutate(&d)
			write(d)
			if _, err := readDesktopDeclaration(path, id, 600, now); err == nil {
				t.Fatal("invalid declaration admitted")
			}
		})
	}
	write(decl)
	a, err := readDesktopDeclaration(path, id, 600, now)
	if err != nil {
		t.Fatal(err)
	}
	if err := a.consume(now); err != nil {
		t.Fatal(err)
	}
	if _, err := readDesktopDeclaration(path, id, 600, now); err == nil {
		t.Fatal("consumed declaration replayed")
	}
}

func TestDesktopAdmissionRejectsAmbiguousAndUnsafeEvidence(t *testing.T) {
	os.MkdirAll("/tmp/tofa-presentation-validation", 0700)
	root, err := os.MkdirTemp("/tmp/tofa-presentation-validation", "admission-test-")
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { os.RemoveAll(root) })
	path := filepath.Join(root, "record.json")
	for _, raw := range []string{`{"schema":"one","schema":"two"}`, `{"schema":"one","nested":{"key":1,"key":2}}`, `{"schema":"one","extra":true}`} {
		os.WriteFile(path, []byte(raw), 0600)
		var target struct {
			Schema string `json:"schema"`
		}
		if _, err := readDesktopEvidence(path, &target); err == nil {
			t.Fatal("ambiguous/unknown evidence admitted")
		}
	}
	os.WriteFile(path, []byte(`{"schema":"one"}`), 0644)
	os.Chmod(path, 0644)
	var target struct {
		Schema string `json:"schema"`
	}
	if _, err := readDesktopEvidence(path, &target); err == nil {
		t.Fatal("public evidence admitted")
	}
	os.Chmod(path, 0600)
	link := filepath.Join(root, "link.json")
	os.Symlink(path, link)
	if _, err := readDesktopEvidence(link, &target); err == nil {
		t.Fatal("symlink evidence admitted")
	}
}

func TestDesktopAdmissionFullEvidenceCannotBeAStatusBoolean(t *testing.T) {
	os.MkdirAll("/tmp/tofa-presentation-validation", 0700)
	root, err := os.MkdirTemp("/tmp/tofa-presentation-validation", "admission-test-")
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { os.RemoveAll(root) })
	path := filepath.Join(root, "proof.json")
	os.WriteFile(path, []byte(`{"schema":"tofa-native-account-proof-v1","status":"passed"}`), 0600)
	if _, err := readDesktopProof(path, desktopAdmissionIdentity{}); err == nil {
		t.Fatal("status-only proof admitted")
	}
}

func TestDesktopAdmissionSettingsPreserveUnrelatedTypesAndTables(t *testing.T) {
	for _, pair := range [][2]string{
		{"extra = 1\n", "extra = 1.0\n"},
		{"extra = 2026-10-19\n", `extra = "2026-10-19"`},
		{"[profiles.unused]\ncustom = true\n", "[profiles.unused]\ncustom = false\n"},
		{"custom = [1,2]\n", "custom = [1,3]\n"},
		{"[plugins.disabled]\nenabled = false\n", "[plugins.disabled]\nenabled = true\n"},
	} {
		left, e := normalizeDesktopConfig([]byte(pair[0]), "/engine", "/bridge")
		if e != nil {
			t.Fatal(e)
		}
		right, e := normalizeDesktopConfig([]byte(pair[1]), "/engine", "/bridge")
		if e != nil {
			t.Fatal(e)
		}
		if string(left) == string(right) {
			t.Fatalf("unrelated settings aliased: %q %q", pair[0], pair[1])
		}
	}
	raw := []byte("[model_providers.tofa-native-router]\nname='user'\nbase_url='http://127.0.0.1:0'\ncustom=true\n")
	if _, e := normalizeDesktopConfig(raw, "/engine", "/bridge"); e == nil {
		t.Fatal("user-owned provider normalized")
	}
	for _, raw := range []string{
		"[mcp_servers.node_repl.env]\nCODEX_CLI_PATH='/other'\n",
		"[mcp_servers.node_repl.env]\nCODEX_CLI_PATH='/engine'\nCODEX_CLI_PATH='/bridge'\n",
	} {
		if _, e := normalizeDesktopConfig([]byte(raw), "/engine", "/bridge"); e == nil {
			t.Fatal("invalid MCP reference normalized")
		}
	}
}

func qualificationFixture(t *testing.T) (string, desktopAdmissionIdentity) {
	t.Helper()
	os.MkdirAll("/tmp/tofa-presentation-validation", 0700)
	root, e := os.MkdirTemp("/tmp/tofa-presentation-validation", "proof-test-")
	if e != nil {
		t.Fatal(e)
	}
	root, _ = filepath.EvalSymlinks(root)
	t.Cleanup(func() { os.RemoveAll(root) })
	id := desktopAdmissionIdentity{Source: strings.Repeat("a", 40), Home: "/owned/home", Profile: "/owned/profile", Runtime: filepath.Join(root, "runtime"), Harness: "/owned/harness", Hashes: map[string]string{"launcher": strings.Repeat("b", 64), "engine": strings.Repeat("c", 64)}}
	os.Mkdir(id.Runtime, 0700)
	write := func(base, name string, value any) desktopEvidenceRef {
		raw, _ := json.Marshal(value)
		path := filepath.Join(base, name)
		os.MkdirAll(filepath.Dir(path), 0700)
		if e := os.WriteFile(path, raw, 0600); e != nil {
			t.Fatal(e)
		}
		return desktopEvidenceRef{Path: name, SHA256: digestBytes(raw)}
	}
	write(id.Runtime, "runtime.json", map[string]any{"bundleFormatVersion": 2, "targetPlatform": "darwin", "targetArch": "arm64", "bundleVersion": "fixture", "nodeVersion": "v1", "pythonVersion": "1"})
	proof := desktopQualificationProof{Schema: desktopProofSchema, Identity: id, Cases: map[string]desktopEvidenceRef{}}
	now := time.Now().UTC().Add(-24 * time.Hour).Truncate(time.Second)
	event := func(role, service, thread, turn string) desktopTransportObservation {
		return desktopTransportObservation{Role: role, Service: service, Model: "owned-model", OriginalModel: "owned-model", Thread: thread, Turn: turn, Route: "native-router", HTTP: 200, Completed: true, Credentials: "native_only_to_native_token_factory_only_to_token_factory_no_launch_capability_upstream", Source: "owned_observer"}
	}
	for name, criteria := range desktopQualificationCases {
		base := filepath.Join(root, name)
		os.Mkdir(base, 0700)
		d := desktopCandidateDeclaration{Schema: desktopDeclarationSchema, Attempt: name, Case: name, Root: base, Identity: id, Issued: now, Expires: now.Add(600 * time.Second), Seconds: 600, Requests: 12}
		scope := write(base, "scope.json", map[string]any{"schema": "tofa-observer-scope-v1", "attempt": name, "root": base, "threads": []any{}})
		d.ScopeSHA256 = scope.SHA256
		declaration := write(base, "declaration.json", d)
		start := write(base, "start.json", map[string]any{"schema": "tofa-native-account-start-v1", "attempt": name, "declaration_sha256": declaration.SHA256, "started_utc": now})
		r := desktopQualificationCase{Schema: desktopCaseSchema, Case: name, Declaration: declaration, Start: start, Identity: id, Started: now, Finished: now.Add(time.Second), Stop: "operator_finished", Before: map[string]string{}, HistoryBefore: map[string]string{}, HistoryAfter: map[string]string{}}
		for _, key := range []string{"config.toml", "auth.json", "managed_config.toml", "AGENTS.md", "AGENTS.override.md", "plugins", "skills", "runtime"} {
			r.Before[key] = strings.Repeat("d", 64)
		}
		r.After = r.Before
		r.Raw = []desktopEvidenceRef{write(base, "raw.json", map[string]any{"fixture_only": true})}
		for _, criterion := range criteria {
			r.Observations = append(r.Observations, desktopUIObservation{Criterion: criterion, Operator: "fixture", Method: "human", Observed: now, Outcome: "passed"})
		}
		switch name {
		case "launcher-crash":
			r.Stop = "launcher_crash"
		case "native-crash":
			r.Stop = "native_crash"
		case "bridge-update":
			r.Stop = "bridge_update_interrupted"
		case "uninstall-reinstall":
			r.Stop = "uninstall_reinstall"
		}
		r.Lifecycle = &desktopLifecycleObservation{LauncherPID: 10, NativePID: 11, Owned: true, InferenceAfterStop: 401, ControlAfterStop: 401, OrdinaryEngine: id.Hashes["engine"], BridgeBefore: "absent", BridgeAfter: id.Hashes["launcher"]}
		switch name {
		case "service-switching":
			r.Transport = []desktopTransportObservation{event("main", "token_factory", "thread", "turn1"), event("main", "token_factory", "thread", "turn1"), event("main", "native", "thread", "turn2"), event("main", "token_factory", "thread", "turn3")}
		case "history-resume":
			for _, route := range []string{"direct-native", "legacy-token-factory", "native-router"} {
				e := event("main", "native", route, "turn")
				e.Route = route
				if route == "legacy-token-factory" {
					e.Service = "token_factory"
				}
				if route == "direct-native" {
					e.Source = "native_relay"
					e.Credentials = "native_client_owned"
				}
				r.Transport = append(r.Transport, e)
				r.HistoryBefore[route] = strings.Repeat("e", 64)
				r.HistoryAfter[route] = strings.Repeat("e", 64)
			}
		case "review-routing":
			for _, service := range []string{"native", "token_factory"} {
				main := event("main", service, service, "turn")
				review := event("review", service, service, "review")
				review.ParentThread = service
				review.ParentTurn = "turn"
				review.Decision = "allow"
				r.Transport = append(r.Transport, main, review)
			}
		case "launch-naming":
			for i := range 4 {
				e := event("naming", "token_factory", "", "")
				e.Model = desktopNamingModel
				e.OriginalModel = "gpt-6-luna"
				e.NamingContext = []string{"routed-native", "routed-token-factory", "existing-native", "routed-native"}[i]
				e.Thread = "intended-" + e.NamingContext
				if i == 3 {
					e.HTTP = 502
					e.Completed = false
					e.Failure = "upstream_status"
				}
				r.Transport = append(r.Transport, e)
			}
		case "runtime-preview":
			r.Runtime = runtimeProofFixture(t, base, id.Runtime)
			for i := range r.Observations {
				r.Observations[i].Artifacts = map[string]string{"deck.pptx": r.Runtime.Artifacts["deck.pptx"].SHA256, "deck.pdf": r.Runtime.Artifacts["deck.pdf"].SHA256}
			}
		}
		r.BeforeSnapshot = write(base, "before.json", map[string]any{"schema": "tofa-native-account-snapshot-v1", "identity": id, "protected": r.Before})
		r.AfterSnapshot = write(base, "after.json", map[string]any{"schema": "tofa-native-account-snapshot-v1", "identity": id, "protected": r.After})
		stopRef := write(base, "route-stop.json", map[string]any{"schema": "tofa-native-account-route-stop-v1", "attempt": name, "launcher_pid": 10, "endpoint": "http://127.0.0.1:4321", "observed_utc": now, "inference": map[string]any{"http_status": 401, "socket_closed": false}, "control": map[string]any{"http_status": 401, "socket_closed": false}})
		r.RouteStop = &stopRef
		r.ProcessReceipt = write(base, "process.json", map[string]any{"schema": "tofa-native-account-process-v1", "launcher_pid": 10, "native_pid": 11, "launcher_sha256": id.Hashes["launcher"], "started_utc": now})
		r.FinishReceipt = write(base, "finish.json", map[string]any{"schema": "tofa-native-account-finish-v1", "stop": r.Stop, "finished_utc": r.Finished, "exit_code": 0, "observer_stop": r.Stop, "observer_requests": len(r.Transport), "scope": "owned fixture only", "qualified": false})
		if name == "native-crash" || name == "bridge-update" || name == "uninstall-reinstall" {
			ref := write(base, "external.json", desktopAttributedInspection{Schema: "tofa-native-account-inspection-v1", Attempt: name, Operator: "fixture", Method: "retained_trace_review", Observed: now, Sources: r.Raw, Action: r.Stop, NativePID: 11, Outcome: "observed"})
			r.ExternalAction = &ref
		}
		var requests []any
		for i := range r.Transport {
			event := &r.Transport[i]
			event.Number = i + 1
			if event.Source == "native_relay" {
				ref := write(base, "native-inspection.json", desktopAttributedInspection{Schema: "tofa-native-account-inspection-v1", Attempt: name, Operator: "fixture", Method: "retained_trace_review", Observed: now, Sources: r.Raw, Provider: "openai", Thread: event.Thread, Turn: event.Turn, Model: event.Model, Outcome: "observed"})
				event.Inspection = &ref
				continue
			}
			role := event.Role
			if role == "review" {
				role = "guardian"
			}
			if role == "naming" {
				role = "auxiliary_title"
			}
			metadata := map[string]any{"thread_id": event.Thread, "turn_id": event.Turn}
			if event.Role == "review" {
				metadata["x-codex-parent-thread-id"] = event.ParentThread
				metadata["parent_turn_id"] = event.ParentTurn
			}
			if event.Role == "naming" {
				metadata = map[string]any{"x-codex-turn-metadata": `{"thread_source":"thread_title","turn_trigger":"thread_title"}`}
			}
			if event.Role == "naming" {
				ref := write(base, "title-inspection-"+strconv.Itoa(event.Number)+".json", desktopAttributedInspection{Schema: "tofa-native-account-inspection-v1", Attempt: name, Operator: "fixture", Method: "human", Observed: now, Sources: r.Raw, Action: "title:" + event.NamingContext, Thread: event.Thread, Model: event.Model, Outcome: "observed"})
				event.Inspection = &ref
			}
			event.Request = write(base, "request-"+strconv.Itoa(event.Number)+".json", map[string]any{"model": event.OriginalModel, "client_metadata": metadata})
			requests = append(requests, map[string]any{"number": event.Number, "role": role, "service": event.Service, "routed_model": event.Model, "model": event.OriginalModel, "status": event.HTTP, "completed": event.Completed, "forwarded": true, "failure": event.Failure})
		}
		r.FinishReceipt = write(base, "finish.json", map[string]any{"schema": "tofa-native-account-finish-v1", "stop": r.Stop, "finished_utc": r.Finished, "exit_code": 0, "observer_stop": r.Stop, "observer_requests": len(requests), "scope": "owned fixture only", "qualified": false})
		r.Requests = write(base, "requests.json", requests)
		ref := write(base, "case.json", r)
		ref.Path = name + "/" + ref.Path
		proof.Cases[name] = ref
	}
	log := write(root, "check-log.json", map[string]any{"fixture": true})
	checks := desktopQualificationChecks{Schema: "tofa-native-account-checks-v1", Identity: id, Baseline: "a91477481ff5fe4f0823731e35302d3794806660", Standards: desktopReviewResult{Reviewer: "fixture-standards", Report: log}, Spec: desktopReviewResult{Reviewer: "fixture-spec", Report: log}}
	for _, name := range []string{"go-race", "go-vet", "script-regressions", "platform-ci"} {
		checks.Tests = append(checks.Tests, desktopCheckResult{Name: name, Log: log})
	}
	proof.Checks = write(root, "checks.json", checks)
	write(root, "proof.json", proof)
	return filepath.Join(root, "proof.json"), id
}

func runtimeProofFixture(t *testing.T, base, root string) *desktopRuntimeObservation {
	t.Helper()
	r := &desktopRuntimeObservation{Artifacts: map[string]desktopEvidenceRef{}, Versions: map[string]desktopVersionObservation{}}
	save := func(name string, raw []byte) desktopEvidenceRef {
		path := filepath.Join(base, name)
		os.MkdirAll(filepath.Dir(path), 0700)
		os.WriteFile(path, raw, 0600)
		return desktopEvidenceRef{Path: name, SHA256: digestBytes(raw)}
	}
	write := func(name string, v any) desktopEvidenceRef { raw, _ := json.Marshal(v); return save(name, raw) }
	var buffer bytes.Buffer
	z := zip.NewWriter(&buffer)
	slide, _ := z.Create("ppt/slides/slide1.xml")
	slide.Write([]byte("<p:sld/>"))
	z.Close()
	r.Artifacts["deck.pptx"] = save("workspace/output/deck.pptx", buffer.Bytes())
	r.Artifacts["deck.pdf"] = save("workspace/output/deck.pdf", []byte("%PDF-1.7\n"))
	r.Artifacts["slide.png"] = save("workspace/output/slide.png", []byte{137, 80, 78, 71, 13, 10, 26, 10})
	text := "- Bundle version: `fixture`\n"
	for label, path := range map[string]string{"Node.js executable": "dependencies/node/bin/node", "Node.js packages": "dependencies/node/node_modules", "Python executable": "dependencies/python/bin/python3", "Python packages": "dependencies/python", "Override binaries": "dependencies/bin/override"} {
		text += "- " + label + ": `" + filepath.Join(root, path) + "`\n"
	}
	r.LoaderResult = write("loader-result.json", text)
	r.LoaderRequest = write("loader-request.json", map[string]any{"tools": []any{map[string]any{"type": "function", "name": "mcp__codex_app__load_workspace_dependencies", "parameters": map[string]any{"type": "object", "properties": map[string]any{}, "additionalProperties": false}}}, "input": []any{map[string]any{"type": "function_call", "name": "mcp__codex_app__load_workspace_dependencies", "call_id": "fixture-call", "arguments": "{}"}, map[string]any{"type": "function_call_output", "call_id": "fixture-call", "output": text}}})
	for _, name := range []string{"node", "python", "soffice", "pdfinfo", "pdftoppm"} {
		path := filepath.Join(root, "dependencies/bin/override", name)
		if name == "node" {
			path = filepath.Join(root, "dependencies/node/bin/node")
		}
		if name == "python" {
			path = filepath.Join(root, "dependencies/python/bin/python3")
		}
		os.MkdirAll(filepath.Dir(path), 0700)
		os.WriteFile(path, []byte(name), 0700)
		version := "fixture"
		if name == "node" {
			version = "v1"
		}
		if name == "python" {
			version = "Python 1"
		}
		r.Versions[name] = desktopVersionObservation{Path: path, SHA256: digestBytes([]byte(name)), Version: version}
	}
	r.Finalization = write("workspace/build/finalization.json", map[string]any{"finalSha256": r.Artifacts["deck.pptx"].SHA256, "packageIntegrity": map[string]any{"status": "pass"}, "firstPartyImport": map[string]any{"passed": true}, "fontSelection": map[string]any{"passed": true}, "presentationLayout": map[string]any{"exitCode": 0}})
	r.FinalAnswer = save("final.txt", []byte("[PPTX]("+filepath.Join(base, "workspace/output/deck.pptx")+")\n[PDF]("+filepath.Join(base, "workspace/output/deck.pdf")+")"))
	artifacts := map[string]string{}
	for name, ref := range r.Artifacts {
		artifacts[name] = ref.SHA256
	}
	marker, _ := json.Marshal(map[string]any{"schema": "tofa-presentation-smoke-v1", "status": "passed", "artifacts": artifacts})
	r.Smoke = write("smoke-result.json", map[string]any{"exit_code": 0, "output": "TOFA_PRESENTATION_SMOKE_PASS " + string(marker)})
	return r
}

func TestDesktopAdmissionFullEvidenceRequiresEveryBoundObservation(t *testing.T) {
	path, id := qualificationFixture(t)
	if _, e := readDesktopProof(path, id); e != nil {
		t.Fatal(e)
	}
	for _, name := range []string{"clean-exit", "review-routing", "runtime-preview"} {
		t.Run(name, func(t *testing.T) {
			raw, _ := os.ReadFile(path)
			var proof desktopQualificationProof
			json.Unmarshal(raw, &proof)
			delete(proof.Cases, name)
			changed, _ := json.Marshal(proof)
			os.WriteFile(path, changed, 0600)
			defer os.WriteFile(path, raw, 0600)
			if _, e := readDesktopProof(path, id); e == nil {
				t.Fatal("incomplete evidence admitted")
			}
		})
	}
	os.WriteFile(filepath.Join(filepath.Dir(path), "runtime-preview/workspace/output/deck.pdf"), []byte("changed"), 0600)
	if _, e := readDesktopProof(path, id); e == nil {
		t.Fatal("changed preview artifact admitted")
	}
}

func TestDesktopAdmissionRejectsUnlinkedClaims(t *testing.T) {
	mutations := []struct {
		name, caseName string
		change         func(*desktopQualificationCase)
	}{
		{"request outcome", "service-switching", func(r *desktopQualificationCase) { r.Transport[0].HTTP = 201 }},
		{"original naming model", "launch-naming", func(r *desktopQualificationCase) { r.Transport[0].OriginalModel = desktopNamingModel }},
		{"naming failure counted as success", "launch-naming", func(r *desktopQualificationCase) { r.Transport = r.Transport[1:] }},
		{"turn provenance", "service-switching", func(r *desktopQualificationCase) { r.Transport[1].Turn = "another" }},
		{"review origin", "review-routing", func(r *desktopQualificationCase) { r.Transport[1].ParentTurn = "unrelated" }},
		{"process ownership", "clean-exit", func(r *desktopQualificationCase) { r.Lifecycle.NativePID++ }},
		{"route receipt", "launcher-crash", func(r *desktopQualificationCase) { r.RouteStop = nil }},
		{"external action", "native-crash", func(r *desktopQualificationCase) { r.ExternalAction = nil }},
		{"preview association", "runtime-preview", func(r *desktopQualificationCase) { r.Observations[0].Artifacts["deck.pdf"] = strings.Repeat("0", 64) }},
	}
	for _, test := range mutations {
		t.Run(test.name, func(t *testing.T) {
			path, id := qualificationFixture(t)
			base := filepath.Dir(path)
			raw, _ := os.ReadFile(path)
			var proof desktopQualificationProof
			json.Unmarshal(raw, &proof)
			ref := proof.Cases[test.caseName]
			casePath := filepath.Join(base, ref.Path)
			raw, _ = os.ReadFile(casePath)
			var record desktopQualificationCase
			json.Unmarshal(raw, &record)
			test.change(&record)
			raw, _ = json.Marshal(record)
			os.WriteFile(casePath, raw, 0600)
			ref.SHA256 = digestBytes(raw)
			proof.Cases[test.caseName] = ref
			raw, _ = json.Marshal(proof)
			os.WriteFile(path, raw, 0600)
			if _, e := readDesktopProof(path, id); e == nil {
				t.Fatal("unlinked claim admitted")
			}
		})
	}
}

func TestDesktopAdmissionResourceInventoryPreservesBrokenLinks(t *testing.T) {
	root := t.TempDir()
	path := filepath.Join(root, "metadata")
	os.Symlink("/unavailable-supplier-build/python.pc", path)
	first, e := admissionTree(root, "engine", "bridge", "")
	if e != nil {
		t.Fatal(e)
	}
	os.Remove(path)
	os.Symlink("/different-unavailable-build/python.pc", path)
	second, e := admissionTree(root, "engine", "bridge", "")
	if e != nil || first == second {
		t.Fatal("broken target identity lost")
	}
	os.Remove(path)
	os.Symlink(os.Args[0], path)
	if _, e := admissionTree(root, "engine", "bridge", ""); e == nil {
		t.Fatal("live external resource admitted")
	}
}

func TestDesktopAdmissionTOMLBoundsAndSpecialFloats(t *testing.T) {
	if _, e := normalizeDesktopConfig([]byte("unused=inf\nnegative=-inf\nnot_a_number=nan\n"), "engine", ""); e != nil {
		t.Fatal(e)
	}
	raw := "unused=" + strings.Repeat("[", 70) + "0" + strings.Repeat("]", 70)
	if _, e := normalizeDesktopConfig([]byte(raw), "engine", ""); e == nil {
		t.Fatal("excessive nesting admitted")
	}
}
