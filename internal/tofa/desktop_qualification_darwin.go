package tofa

import (
	"archive/zip"
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/url"
	"os"
	"path/filepath"
	"reflect"
	"regexp"
	"strconv"
	"strings"
	"time"
)

type desktopQualificationProof struct {
	Schema   string                        `json:"schema"`
	Identity desktopAdmissionIdentity      `json:"identity"`
	Cases    map[string]desktopEvidenceRef `json:"cases"`
	Checks   desktopEvidenceRef            `json:"checks"`
}
type desktopQualificationChecks struct {
	Schema    string                   `json:"schema"`
	Identity  desktopAdmissionIdentity `json:"identity"`
	Baseline  string                   `json:"review_baseline"`
	Tests     []desktopCheckResult     `json:"tests"`
	Standards desktopReviewResult      `json:"standards"`
	Spec      desktopReviewResult      `json:"spec"`
}
type desktopCheckResult struct {
	Name     string             `json:"name"`
	ExitCode int                `json:"exit_code"`
	Log      desktopEvidenceRef `json:"log"`
}
type desktopReviewResult struct {
	Reviewer   string             `json:"reviewer"`
	Unresolved int                `json:"unresolved"`
	Report     desktopEvidenceRef `json:"report"`
}
type desktopQualificationCase struct {
	Schema      string                   `json:"schema"`
	Case        string                   `json:"case"`
	Declaration desktopEvidenceRef       `json:"declaration"`
	Start       desktopEvidenceRef       `json:"start"`
	Identity    desktopAdmissionIdentity `json:"identity"`
	Started     time.Time                `json:"started_utc"`
	Finished    time.Time                `json:"finished_utc"`
	Stop        string                   `json:"stop"`
	// Raw receipts stay private. They are immutable references, not provider secrets.
	Raw            []desktopEvidenceRef          `json:"raw"`
	BeforeSnapshot desktopEvidenceRef            `json:"before_snapshot"`
	AfterSnapshot  desktopEvidenceRef            `json:"after_snapshot"`
	ProcessReceipt desktopEvidenceRef            `json:"process_receipt"`
	FinishReceipt  desktopEvidenceRef            `json:"finish_receipt"`
	Requests       desktopEvidenceRef            `json:"requests"`
	RouteStop      *desktopEvidenceRef           `json:"route_stop,omitempty"`
	ExternalAction *desktopEvidenceRef           `json:"external_action,omitempty"`
	Before         map[string]string             `json:"protected_before"`
	After          map[string]string             `json:"protected_after"`
	HistoryBefore  map[string]string             `json:"history_before"`
	HistoryAfter   map[string]string             `json:"history_after"`
	Lifecycle      *desktopLifecycleObservation  `json:"lifecycle,omitempty"`
	Transport      []desktopTransportObservation `json:"transport,omitempty"`
	Observations   []desktopUIObservation        `json:"observations"`
	Runtime        *desktopRuntimeObservation    `json:"runtime,omitempty"`
}
type desktopLifecycleObservation struct {
	LauncherPID        int    `json:"launcher_pid"`
	NativePID          int    `json:"native_pid"`
	Owned              bool   `json:"owned"`
	InferenceAfterStop int    `json:"inference_after_stop_http"`
	ControlAfterStop   int    `json:"control_after_stop_http"`
	RouteSocketClosed  bool   `json:"route_socket_closed"`
	OrdinaryEngine     string `json:"ordinary_engine_sha256"`
	BridgeBefore       string `json:"bridge_before_sha256"`
	BridgeAfter        string `json:"bridge_after_sha256"`
}
type desktopTransportObservation struct {
	Number        int                 `json:"number"`
	Request       desktopEvidenceRef  `json:"request"`
	Inspection    *desktopEvidenceRef `json:"inspection,omitempty"`
	Role          string              `json:"role"`
	Service       string              `json:"service"`
	Model         string              `json:"model"`
	OriginalModel string              `json:"original_model"`
	Thread        string              `json:"thread"`
	Turn          string              `json:"turn"`
	ParentThread  string              `json:"parent_thread,omitempty"`
	ParentTurn    string              `json:"parent_turn,omitempty"`
	Route         string              `json:"route"`
	HTTP          int                 `json:"http_status"`
	Completed     bool                `json:"completed"`
	Credentials   string              `json:"credentials"`
	Source        string              `json:"source"`
	Decision      string              `json:"decision,omitempty"`
	Failure       string              `json:"failure,omitempty"`
	NamingContext string              `json:"naming_context,omitempty"`
}
type desktopUIObservation struct {
	Criterion string            `json:"criterion"`
	Operator  string            `json:"operator"`
	Method    string            `json:"method"`
	Observed  time.Time         `json:"observed_utc"`
	Outcome   string            `json:"outcome"`
	Artifacts map[string]string `json:"artifacts,omitempty"`
}
type desktopRuntimeObservation struct {
	LoaderRequest desktopEvidenceRef                   `json:"loader_request"`
	LoaderResult  desktopEvidenceRef                   `json:"loader_result"`
	Versions      map[string]desktopVersionObservation `json:"versions"`
	Artifacts     map[string]desktopEvidenceRef        `json:"artifacts"`
	Finalization  desktopEvidenceRef                   `json:"finalization"`
	FinalAnswer   desktopEvidenceRef                   `json:"final_answer"`
	Smoke         desktopEvidenceRef                   `json:"smoke"`
}
type desktopVersionObservation struct {
	Path    string `json:"path"`
	SHA256  string `json:"sha256"`
	Version string `json:"version"`
}

func readAdmissionReference(base string, ref desktopEvidenceRef, target any) error {
	if ref.Path == "" || filepath.IsAbs(ref.Path) || filepath.Clean(ref.Path) != ref.Path || strings.HasPrefix(ref.Path, "../") || !validDigest(ref.SHA256) {
		return admissionError("invalid evidence reference")
	}
	path := filepath.Join(base, ref.Path)
	if !withinPath(base, path) {
		return admissionError("evidence escapes its record")
	}
	if target != nil {
		digest, e := readDesktopEvidence(path, target)
		if e != nil {
			return e
		}
		if digest != ref.SHA256 {
			return admissionError("evidence digest changed")
		}
		return nil
	}
	path, e := privateEvidencePath(path, false)
	if e != nil {
		return e
	}
	hash, e := hashAdmissionFile(path)
	if e != nil || hash != ref.SHA256 {
		return admissionError("artifact digest changed")
	}
	return nil
}
func readDesktopProof(path string, id desktopAdmissionIdentity) (*desktopAdmission, error) {
	var proof desktopQualificationProof
	digest, e := readDesktopEvidence(path, &proof)
	if e != nil {
		return nil, e
	}
	if proof.Schema != desktopProofSchema || !reflect.DeepEqual(proof.Identity, id) || len(proof.Cases) != len(desktopQualificationCases) {
		return nil, admissionError("coverage or identity incomplete")
	}
	canonical, e := privateEvidencePath(path, false)
	if e != nil {
		return nil, e
	}
	base := filepath.Dir(canonical)
	if _, e := os.Lstat(filepath.Join(base, "revoked.json")); !errors.Is(e, os.ErrNotExist) {
		return nil, admissionError("evidence revoked")
	}
	attempts := map[string]bool{}
	for name := range desktopQualificationCases {
		ref, ok := proof.Cases[name]
		if !ok {
			return nil, admissionError("missing " + name)
		}
		var record desktopQualificationCase
		if e := readAdmissionReference(base, ref, &record); e != nil {
			return nil, e
		}
		if record.Case != name {
			return nil, admissionError("case reference mismatch")
		}
		if e := validateDesktopCase(filepath.Dir(filepath.Join(base, ref.Path)), record, id, attempts); e != nil {
			return nil, e
		}
	}
	var checks desktopQualificationChecks
	if e := readAdmissionReference(base, proof.Checks, &checks); e != nil {
		return nil, e
	}
	if checks.Schema != "tofa-native-account-checks-v1" || !reflect.DeepEqual(checks.Identity, id) || checks.Baseline != "a91477481ff5fe4f0823731e35302d3794806660" {
		return nil, admissionError("review identity incomplete")
	}
	checksBase := filepath.Dir(filepath.Join(base, proof.Checks.Path))
	required := map[string]bool{"go-race": false, "go-vet": false, "script-regressions": false, "platform-ci": false}
	for _, test := range checks.Tests {
		if _, ok := required[test.Name]; !ok || required[test.Name] || test.ExitCode != 0 {
			return nil, admissionError("required checks did not pass")
		}
		if e := readAdmissionReference(checksBase, test.Log, nil); e != nil {
			return nil, e
		}
		required[test.Name] = true
	}
	for _, passed := range required {
		if !passed {
			return nil, admissionError("required check missing")
		}
	}
	for _, review := range []desktopReviewResult{checks.Standards, checks.Spec} {
		if review.Reviewer == "" || review.Unresolved != 0 {
			return nil, admissionError("review findings unresolved")
		}
		if e := readAdmissionReference(checksBase, review.Report, nil); e != nil {
			return nil, e
		}
	}
	return &desktopAdmission{mode: "qualified", path: canonical, digest: digest, identity: id}, nil
}
func validateDesktopCase(base string, r desktopQualificationCase, id desktopAdmissionIdentity, attempts map[string]bool) error {
	criteria, known := desktopQualificationCases[r.Case]
	if r.Schema != desktopCaseSchema || !known || !reflect.DeepEqual(r.Identity, id) || r.Started.IsZero() || r.Finished.Before(r.Started) || r.Finished.After(time.Now().Add(time.Minute)) {
		return admissionError("case identity invalid")
	}
	var d desktopCandidateDeclaration
	if e := readAdmissionReference(base, r.Declaration, &d); e != nil {
		return e
	}
	if d.Schema != desktopDeclarationSchema || d.Case != r.Case || !reflect.DeepEqual(d.Identity, id) || d.Attempt == "" || attempts[d.Attempt] || (d.Seconds != 600 && d.Seconds != 900) || d.Requests < 1 || d.Requests > 80 || d.Expires.Sub(d.Issued) != time.Duration(d.Seconds)*time.Second || r.Started.Before(d.Issued) || r.Finished.After(d.Expires) {
		return admissionError("case declaration mismatch or reused attempt")
	}
	if e := validateAdmissionScope(base, d); e != nil {
		return e
	}
	declaredRoot, e := privateEvidencePath(d.Root, true)
	if e != nil || declaredRoot != base {
		return admissionError("case root mismatch")
	}
	attempts[d.Attempt] = true
	var start struct {
		Schema            string    `json:"schema"`
		Attempt           string    `json:"attempt"`
		DeclarationSHA256 string    `json:"declaration_sha256"`
		Started           time.Time `json:"started_utc"`
	}
	if e := readAdmissionReference(base, r.Start, &start); e != nil {
		return e
	}
	if start.Schema != "tofa-native-account-start-v1" || start.Attempt != d.Attempt || start.DeclarationSHA256 != r.Declaration.SHA256 || !start.Started.Equal(r.Started) {
		return admissionError("case start receipt mismatch")
	}
	expectedStop := "operator_finished"
	if r.Case == "launcher-crash" {
		expectedStop = "launcher_crash"
	}
	if r.Case == "native-crash" {
		expectedStop = "native_crash"
	}
	if r.Case == "bridge-update" {
		expectedStop = "bridge_update_interrupted"
	}
	if r.Case == "uninstall-reinstall" {
		expectedStop = "uninstall_reinstall"
	}
	if r.Stop != expectedStop {
		return admissionError("case did not finish its declared observation")
	}
	if e := validateDesktopReceipts(base, r); e != nil {
		return e
	}
	if len(r.Before) < 8 || !reflect.DeepEqual(r.Before, r.After) {
		return admissionError("case protected state changed")
	}
	for _, key := range []string{"config.toml", "auth.json", "managed_config.toml", "AGENTS.md", "AGENTS.override.md", "plugins", "skills", "runtime"} {
		if v, ok := r.Before[key]; !ok || v != "absent" && !validDigest(v) {
			return admissionError("protected category missing")
		}
	}
	for thread, history := range r.HistoryBefore {
		if !validDigest(history) || r.HistoryAfter[thread] != history {
			return admissionError("history preservation failed")
		}
	}
	if len(r.Raw) == 0 || len(r.Raw) > 64 {
		return admissionError("raw observation sources missing")
	}
	for _, ref := range r.Raw {
		if e := readAdmissionReference(base, ref, nil); e != nil {
			return e
		}
	}
	observed := map[string]bool{}
	for _, o := range r.Observations {
		if observed[o.Criterion] || o.Operator == "" || (o.Method != "human" && o.Method != "computer_use") || o.Outcome != "passed" || o.Observed.Before(r.Started) || o.Observed.After(r.Finished) {
			return admissionError("attributed native observation invalid")
		}
		observed[o.Criterion] = true
	}
	for _, criterion := range criteria {
		if !observed[criterion] {
			return admissionError("native observation missing: " + criterion)
		}
	}
	observerRequests := 0
	seenRequests := map[int]bool{}
	for _, event := range r.Transport {
		if event.Source == "owned_observer" {
			if seenRequests[event.Number] {
				return admissionError("observed request reused")
			}
			seenRequests[event.Number] = true
			observerRequests++
		}
	}
	if observerRequests > d.Requests {
		return admissionError("observed request budget exceeded")
	}
	for _, request := range r.Transport {
		if e := validateDesktopTransportReceipt(base, r, request); e != nil {
			return e
		}
		namingFailure := request.Role == "naming" && request.Failure != "" && !request.Completed && request.HTTP >= 0 && request.HTTP <= 599
		if request.Model == "" || (!namingFailure && (request.HTTP != 200 || !request.Completed || request.Failure != "")) || (request.Service != "native" && request.Service != "token_factory") || (request.Role != "main" && request.Role != "review" && request.Role != "naming") || (request.Source != "owned_observer" && request.Source != "native_relay") {
			return admissionError("transport observation incomplete")
		}
		if request.Source == "native_relay" && (request.Service != "native" || request.Route != "direct-native" || request.Credentials != "native_client_owned") {
			return admissionError("direct native boundary misrepresented")
		}
		if request.Source == "owned_observer" && (request.Route != "native-router" && request.Route != "legacy-token-factory" || request.Route == "legacy-token-factory" && request.Service != "token_factory") {
			return admissionError("observed route mismatch")
		}
		if request.Source == "owned_observer" && request.Credentials != "native_only_to_native_token_factory_only_to_token_factory_no_launch_capability_upstream" {
			return admissionError("credential separation unverified")
		}
	}
	if r.Lifecycle != nil {
		l := r.Lifecycle
		if l.LauncherPID <= 0 || l.NativePID <= 0 || !l.Owned || !((l.InferenceAfterStop == 401 && l.ControlAfterStop == 401) || (l.RouteSocketClosed && l.InferenceAfterStop == 0 && l.ControlAfterStop == 0)) || l.OrdinaryEngine != id.Hashes["engine"] || (l.BridgeBefore != "absent" && !validDigest(l.BridgeBefore)) || l.BridgeAfter != id.Hashes["launcher"] {
			return admissionError("lifecycle ownership or expiry unverified")
		}
	} else if r.Case == "clean-exit" || r.Case == "repeat-launch" || r.Case == "launcher-crash" || r.Case == "native-crash" || r.Case == "ordinary-launch" || r.Case == "bridge-update" || r.Case == "uninstall-reinstall" {
		return admissionError("lifecycle observation missing")
	}
	switch r.Case {
	case "service-switching":
		var main []desktopTransportObservation
		turns := map[[2]string]desktopTransportObservation{}
		for _, event := range r.Transport {
			if event.Role == "main" {
				key := [2]string{event.Thread, event.Turn}
				if previous, exists := turns[key]; exists {
					if previous.Service != event.Service || previous.Model != event.Model {
						return admissionError("service changed within a turn")
					}
					continue
				}
				turns[key] = event
				main = append(main, event)
			}
		}
		if len(main) < 3 || main[0].Service != "token_factory" || main[1].Service != "native" || main[2].Service != "token_factory" || main[0].Thread == "" || main[0].Thread != main[1].Thread || main[0].Thread != main[2].Thread || main[0].Turn == main[1].Turn || main[1].Turn == main[2].Turn {
			return admissionError("cross-service continuation unverified")
		}
	case "history-resume":
		if len(r.HistoryBefore) < 3 {
			return admissionError("native, legacy and routed histories unverified")
		}
		routes := map[string]bool{}
		for _, event := range r.Transport {
			if event.Role == "main" {
				routes[event.Route] = true
			}
		}
		for _, route := range []string{"direct-native", "legacy-token-factory", "native-router"} {
			if !routes[route] {
				return admissionError("resume route unverified")
			}
		}
	case "review-routing":
		mains := map[[2]string]string{}
		for _, event := range r.Transport {
			if event.Role == "main" {
				mains[[2]string{event.Thread, event.Turn}] = event.Service
			}
		}
		reviews := map[string]bool{}
		for _, event := range r.Transport {
			if event.Role == "review" {
				if event.ParentThread == "" || event.ParentTurn == "" || mains[[2]string{event.ParentThread, event.ParentTurn}] != event.Service || (event.Decision != "allow" && event.Decision != "deny") {
					return admissionError("review origin unverified")
				}
				reviews[event.Service] = true
			}
		}
		if !reviews["native"] || !reviews["token_factory"] {
			return admissionError("review services incomplete")
		}
	case "launch-naming":
		contexts := map[string]bool{}
		for _, event := range r.Transport {
			if event.Role == "naming" {
				if event.Service != "token_factory" || event.Model != desktopNamingModel {
					return admissionError("naming policy mismatch")
				}
				if event.NamingContext != "routed-native" && event.NamingContext != "routed-token-factory" && event.NamingContext != "existing-native" {
					return admissionError("naming context missing")
				}
				if event.Inspection == nil {
					return admissionError("title UI association missing")
				}
				var inspection desktopAttributedInspection
				if e := readAdmissionReference(base, *event.Inspection, &inspection); e != nil {
					return e
				}
				if e := validateDesktopInspection(base, r, inspection); e != nil {
					return e
				}
				// The native title protocol has no reliable parent IDs: association
				// is attributed UI inspection, never invented transport provenance.
				if inspection.Action != "title:"+event.NamingContext || inspection.Thread != event.Thread || event.Thread == "" || inspection.Model != desktopNamingModel {
					return admissionError("title UI association mismatch")
				}
				if event.Completed && event.Failure == "" {
					contexts[event.NamingContext] = true
				}
			}
		}
		if len(contexts) != 3 {
			return admissionError("launch naming incomplete")
		}
	case "runtime-preview":
		if r.Runtime == nil {
			return admissionError("runtime observations missing")
		}
		return validateDesktopRuntimeEvidence(base, r)
	}
	return nil
}

func validateDesktopRuntimeEvidence(base string, r desktopQualificationCase) error {
	runtime := r.Runtime
	if len(runtime.Artifacts) != 3 || len(runtime.Versions) != 5 {
		return admissionError("runtime artifact/version coverage incomplete")
	}
	var request map[string]json.RawMessage
	if e := readAdmissionReference(base, runtime.LoaderRequest, &request); e != nil {
		return e
	}
	var loader any
	if e := readAdmissionReference(base, runtime.LoaderResult, &loader); e != nil {
		return e
	}
	var input []map[string]json.RawMessage
	if json.Unmarshal(request["input"], &input) != nil {
		return admissionError("loader trace missing")
	}
	matched := false
	for _, call := range input {
		var typ, name, id, args, namespace string
		json.Unmarshal(call["type"], &typ)
		json.Unmarshal(call["name"], &name)
		json.Unmarshal(call["call_id"], &id)
		json.Unmarshal(call["arguments"], &args)
		json.Unmarshal(call["namespace"], &namespace)
		var parsed map[string]any
		if typ != "function_call" || !(name == "mcp__codex_app__load_workspace_dependencies" && namespace == "" || name == "load_workspace_dependencies" && namespace == "mcp__codex_app") || id == "" || json.Unmarshal([]byte(args), &parsed) != nil || parsed == nil || len(parsed) != 0 {
			continue
		}
		for _, out := range input {
			var outputType, callID string
			json.Unmarshal(out["type"], &outputType)
			json.Unmarshal(out["call_id"], &callID)
			var value any
			json.Unmarshal(out["output"], &value)
			if outputType == "function_call_output" && callID == id && reflect.DeepEqual(value, loader) {
				matched = true
			}
		}
	}
	if !matched || !desktopLoaderAdvertised(request) {
		return admissionError("actual loader call/result/catalog unverified")
	}
	// The runtime root must occur in the actual loader result, not only an author summary.
	texts, _, e := desktopRuntimeTexts(loader, 0)
	if e != nil {
		return e
	}
	combined := strings.Join(texts, "\n")
	manifestBytes, e := os.ReadFile(filepath.Join(r.Identity.Runtime, "runtime.json"))
	if e != nil || len(manifestBytes) > 1<<20 {
		return admissionError("runtime manifest unavailable")
	}
	var manifest map[string]any
	if uniqueReviewJSON(manifestBytes, 0) != nil || json.Unmarshal(manifestBytes, &manifest) != nil || manifest["bundleFormatVersion"] != float64(2) || manifest["targetPlatform"] != "darwin" || manifest["targetArch"] != "arm64" {
		return admissionError("runtime manifest invalid")
	}
	for label, relative := range map[string]string{"Node.js executable": "dependencies/node/bin/node", "Node.js packages": "dependencies/node/node_modules", "Python executable": "dependencies/python/bin/python3", "Python packages": "dependencies/python", "Override binaries": "dependencies/bin/override"} {
		expression := regexp.MustCompile("(?m)^- " + regexp.QuoteMeta(label) + ": `([^`\\n]+)`")
		matches := expression.FindAllStringSubmatch(combined, -1)
		seen := map[string]bool{}
		for _, match := range matches {
			seen[match[1]] = true
		}
		if len(seen) != 1 || !seen[filepath.Join(r.Identity.Runtime, relative)] {
			return admissionError("loader paths mismatch")
		}
	}
	versions := regexp.MustCompile("(?m)^- Bundle version: `([^`\\n]+)`").FindAllStringSubmatch(combined, -1)
	if len(versions) == 0 {
		return admissionError("loader version absent")
	}
	for _, version := range versions {
		if version[1] != manifest["bundleVersion"] {
			return admissionError("loader bundle version mismatch")
		}
	}
	if runtime.Versions["node"].Version != manifest["nodeVersion"] || runtime.Versions["python"].Version != "Python "+fmt.Sprint(manifest["pythonVersion"]) {
		return admissionError("observed supplied version mismatch")
	}

	for _, name := range []string{"node", "python", "soffice", "pdfinfo", "pdftoppm"} {
		v, ok := runtime.Versions[name]
		expectedPath := filepath.Join(r.Identity.Runtime, "dependencies/bin/override", name)
		if name == "node" {
			expectedPath = filepath.Join(r.Identity.Runtime, "dependencies/node/bin/node")
		}
		if name == "python" {
			expectedPath = filepath.Join(r.Identity.Runtime, "dependencies/python/bin/python3")
		}
		if !ok || v.Version == "" || v.Path != expectedPath || !validDigest(v.SHA256) {
			return admissionError("supplied executable version missing")
		}
		hash, e := hashAdmissionFile(v.Path)
		if e != nil || hash != v.SHA256 {
			return admissionError("supplied executable drift")
		}
	}
	for _, name := range []string{"deck.pptx", "deck.pdf", "slide.png"} {
		ref, ok := runtime.Artifacts[name]
		if !ok || ref.Path != "workspace/output/"+name {
			return admissionError("owned artifacts missing")
		}
		if e := readAdmissionReference(base, ref, nil); e != nil {
			return e
		}
	}
	deck, e := zip.OpenReader(filepath.Join(base, "workspace/output/deck.pptx"))
	if e != nil {
		return admissionError("invalid PPTX")
	}
	defer deck.Close()
	slide := false
	if len(deck.File) > 4096 {
		return admissionError("PPTX entries exceed bound")
	}
	var total uint64
	for _, file := range deck.File {
		total += file.UncompressedSize64
		if total > 128<<20 {
			return admissionError("PPTX expanded size exceeds bound")
		}
		if file.Name == "ppt/slides/slide1.xml" {
			slide = true
		}
		if file.UncompressedSize64 > 32<<20 {
			return admissionError("PPTX entry too large")
		}
		reader, e := file.Open()
		if e != nil {
			return e
		}
		_, e = io.Copy(io.Discard, io.LimitReader(reader, 32<<20))
		reader.Close()
		if e != nil {
			return admissionError("PPTX integrity failed")
		}
	}
	if !slide {
		return admissionError("smoke slide missing")
	}
	for name, magic := range map[string][]byte{"deck.pdf": []byte("%PDF-"), "slide.png": {137, 80, 78, 71, 13, 10, 26, 10}} {
		f, e := os.Open(filepath.Join(base, "workspace/output/"+name))
		if e != nil {
			return e
		}
		prefix := make([]byte, len(magic))
		_, e = io.ReadFull(f, prefix)
		f.Close()
		if e != nil || !bytes.Equal(prefix, magic) {
			return admissionError("invalid runtime artifact")
		}
	}
	var receipt struct {
		FinalSHA256      string `json:"finalSha256"`
		PackageIntegrity struct {
			Status string `json:"status"`
		} `json:"packageIntegrity"`
		FirstPartyImport struct {
			Passed bool `json:"passed"`
		} `json:"firstPartyImport"`
		FontSelection struct {
			Passed bool `json:"passed"`
		} `json:"fontSelection"`
		PresentationLayout struct {
			ExitCode *int `json:"exitCode"`
		} `json:"presentationLayout"`
	}
	// Finalization has first-party diagnostic fields; validate required invariants
	// from the full bounded object rather than reject those native extra fields.
	var final map[string]json.RawMessage
	if e := readAdmissionReference(base, runtime.Finalization, &final); e != nil {
		return e
	}
	encoded, _ := json.Marshal(final)
	if json.Unmarshal(encoded, &receipt) != nil || receipt.FinalSHA256 != runtime.Artifacts["deck.pptx"].SHA256 || receipt.PackageIntegrity.Status != "pass" || !receipt.FirstPartyImport.Passed || !receipt.FontSelection.Passed || (receipt.PresentationLayout.ExitCode == nil || *receipt.PresentationLayout.ExitCode != 0) || final["presentationLayout"] == nil {
		return admissionError("runtime finalization failed")
	}
	if e := readAdmissionReference(base, runtime.FinalAnswer, nil); e != nil {
		return e
	}
	answer, e := os.ReadFile(filepath.Join(base, runtime.FinalAnswer.Path))
	if e != nil || len(answer) > 1<<20 {
		return admissionError("delivery unavailable")
	}
	for _, name := range []string{"deck.pptx", "deck.pdf"} {
		path := filepath.Join(base, "workspace/output/"+name)
		if !bytes.Contains(answer, []byte("]("+path+")")) && !bytes.Contains(answer, []byte("](<"+path+">)")) {
			return admissionError("native file reference missing")
		}
	}
	var smoke any
	if e := readAdmissionReference(base, runtime.Smoke, &smoke); e != nil {
		return e
	}
	smokeTexts, exits, e := desktopRuntimeTexts(smoke, 0)
	if e != nil {
		return e
	}
	text := strings.Join(smokeTexts, "\n")
	for _, match := range regexp.MustCompile("Process exited with code (-?[0-9]+)").FindAllStringSubmatch(text, -1) {
		code, e := strconv.Atoi(match[1])
		if e != nil {
			return admissionError("smoke exit invalid")
		}
		exits = append(exits, code)
	}
	if len(exits) == 0 {
		return admissionError("smoke completion missing")
	}
	for _, code := range exits {
		if code != 0 {
			return admissionError("smoke execution failed")
		}
	}
	markers := regexp.MustCompile(`(?m)^TOFA_PRESENTATION_SMOKE_PASS (\{[^\n]+\})$`).FindAllStringSubmatch(text, -1)
	var marker struct {
		Schema    string            `json:"schema"`
		Status    string            `json:"status"`
		Artifacts map[string]string `json:"artifacts"`
	}
	if len(markers) != 1 || strictAdmissionJSON([]byte(markers[0][1]), &marker) != nil || marker.Schema != "tofa-presentation-smoke-v1" || marker.Status != "passed" || len(marker.Artifacts) != 3 {
		return admissionError("artifact-bound smoke marker missing")
	}
	for name, ref := range runtime.Artifacts {
		if marker.Artifacts[name] != ref.SHA256 {
			return admissionError("smoke artifact mismatch")
		}
	}

	for _, o := range r.Observations {
		if o.Criterion == "native-pptx-preview" || o.Criterion == "native-pdf-preview" {
			if o.Artifacts["deck.pptx"] != runtime.Artifacts["deck.pptx"].SHA256 || o.Artifacts["deck.pdf"] != runtime.Artifacts["deck.pdf"].SHA256 {
				return admissionError("preview artifact association missing")
			}
		}
	}
	return nil
}

// Read-only collection entry point. No app launch, inference, installation or
// credential mutation. The catalog is read with the existing configured service.
func (a *App) desktopQualification(ctx context.Context, s Store, args []string) error {
	if len(args) == 0 || (args[0] != "snapshot" && args[0] != "verify") {
		return errors.New("use desktop-qualification snapshot --app-bundle PATH --runtime-root PATH --harness-root PATH --source-revision SHA")
	}
	flags := flags("desktop-qualification snapshot")
	bundlePath := flags.String("app-bundle", "", "")
	runtimeRoot := flags.String("runtime-root", "", "")
	harness := flags.String("harness-root", "", "")
	source := flags.String("source-revision", "", "")
	proofPath := flags.String("proof", "", "")
	if e := flags.Parse(args[1:]); e != nil {
		return e
	}
	if flags.NArg() != 0 {
		return errors.New("unexpected qualification argument")
	}
	bundle, e := discoverDesktop(ctx, *bundlePath)
	if e != nil {
		return e
	}
	home, e := desktopHome(ctx)
	if e != nil {
		return e
	}
	profile, e := ordinaryDesktopProfile()
	if e != nil {
		return e
	}
	c, key, e := s.Credentials()
	if e != nil {
		return e
	}
	models, e := a.models(c.ProjectID, key)
	if e != nil {
		return e
	}
	id, e := desktopCompatibilityIdentity(bundle, home, profile, desktopBridgePath(a.Dir, bundle.engine), *runtimeRoot, *harness, *source, models)
	if e != nil {
		return e
	}
	if args[0] == "verify" {
		if *proofPath == "" {
			return admissionError("proof path required")
		}
		if _, e := readDesktopProof(*proofPath, id); e != nil {
			return e
		}
		return json.NewEncoder(a.Out).Encode(map[string]any{"schema": "tofa-native-account-verification-v1", "identity": id, "evidence_complete": true, "desktop_launched": false})
	}
	state, e := desktopProtectedSnapshot(home, bundle.engine, desktopBridgePath(a.Dir, bundle.engine))
	if e != nil {
		return e
	}
	for _, name := range []string{"plugins", "skills", "runtime"} {
		state[name] = id.Hashes[name]
	}
	return json.NewEncoder(a.Out).Encode(map[string]any{"schema": "tofa-native-account-snapshot-v1", "identity": id, "protected": state})
}

// Only concrete native content containers are traversed. Error flags are fatal;
// nested serialized envelopes remain bounded and cannot invent an exit result.
func desktopRuntimeTexts(value any, depth int) ([]string, []int, error) {
	if depth > 32 {
		return nil, nil, admissionError("runtime envelope too deep")
	}
	var texts []string
	var exits []int
	collect := func(item any) error {
		nested, codes, e := desktopRuntimeTexts(item, depth+1)
		texts = append(texts, nested...)
		exits = append(exits, codes...)
		return e
	}
	switch v := value.(type) {
	case string:
		texts = append(texts, v)
		var decoded any
		candidate := v
		if strings.HasPrefix(v, "Wall time:") {
			if _, rest, ok := strings.Cut(v, "\nOutput:\n"); ok {
				candidate = rest
			}
		}
		if json.Unmarshal([]byte(candidate), &decoded) == nil {
			if _, isString := decoded.(string); !isString {
				if e := collect(decoded); e != nil {
					return nil, nil, e
				}
			}
		}
	case []any:
		for _, item := range v {
			if e := collect(item); e != nil {
				return nil, nil, e
			}
		}
	case map[string]any:
		if v["isError"] == true || v["success"] == false {
			return nil, nil, admissionError("runtime tool execution failed")
		}
		for _, key := range []string{"exit_code", "exitCode"} {
			if raw, ok := v[key]; ok {
				number, ok := raw.(float64)
				if !ok || number != float64(int(number)) {
					return nil, nil, admissionError("runtime exit invalid")
				}
				exits = append(exits, int(number))
			}
		}
		for _, key := range []string{"content", "contentItems", "text", "output", "structuredContent"} {
			if item, ok := v[key]; ok {
				if e := collect(item); e != nil {
					return nil, nil, e
				}
			}
		}
	}
	return texts, exits, nil
}

func validateDesktopReceipts(base string, r desktopQualificationCase) error {
	for _, item := range []struct {
		ref      desktopEvidenceRef
		expected map[string]string
	}{{r.BeforeSnapshot, r.Before}, {r.AfterSnapshot, r.After}} {
		var snapshot struct {
			Schema    string                   `json:"schema"`
			Identity  desktopAdmissionIdentity `json:"identity"`
			Protected map[string]string        `json:"protected"`
		}
		if e := readAdmissionReference(base, item.ref, &snapshot); e != nil {
			return e
		}
		if snapshot.Schema != "tofa-native-account-snapshot-v1" || !reflect.DeepEqual(snapshot.Identity, r.Identity) || !reflect.DeepEqual(snapshot.Protected, item.expected) {
			return admissionError("protected snapshot linkage mismatch")
		}
	}
	var process struct {
		Schema      string    `json:"schema"`
		LauncherPID int       `json:"launcher_pid"`
		NativePID   int       `json:"native_pid"`
		LauncherSHA string    `json:"launcher_sha256"`
		Started     time.Time `json:"started_utc"`
	}
	if e := readAdmissionReference(base, r.ProcessReceipt, &process); e != nil {
		return e
	}
	if process.Schema != "tofa-native-account-process-v1" || process.LauncherPID <= 0 || process.NativePID <= 0 || process.LauncherSHA != r.Identity.Hashes["launcher"] || process.Started.After(r.Started) {
		return admissionError("owned process receipt mismatch")
	}
	var finish struct {
		Schema           string    `json:"schema"`
		Stop             string    `json:"stop"`
		Finished         time.Time `json:"finished_utc"`
		ExitCode         int       `json:"exit_code"`
		ObserverStop     string    `json:"observer_stop"`
		ObserverRequests int       `json:"observer_requests"`
		Scope            string    `json:"scope"`
		Qualified        bool      `json:"qualified"`
	}
	if e := readAdmissionReference(base, r.FinishReceipt, &finish); e != nil {
		return e
	}
	if finish.Schema != "tofa-native-account-finish-v1" || finish.Stop != r.Stop || !finish.Finished.Equal(r.Finished) || finish.Qualified || finish.ObserverRequests < 0 {
		return admissionError("finish receipt mismatch")
	}
	var requests []json.RawMessage
	if e := readAdmissionReference(base, r.Requests, &requests); e != nil {
		return e
	}
	if len(requests) != finish.ObserverRequests {
		return admissionError("finish request count mismatch")
	}
	if r.Lifecycle != nil {
		if r.RouteStop == nil {
			return admissionError("owned route stop receipt missing")
		}
		type outcome struct {
			HTTP   int  `json:"http_status"`
			Closed bool `json:"socket_closed"`
		}
		var receipt struct {
			Schema      string    `json:"schema"`
			Attempt     string    `json:"attempt"`
			LauncherPID int       `json:"launcher_pid"`
			Endpoint    string    `json:"endpoint"`
			Observed    time.Time `json:"observed_utc"`
			Inference   outcome   `json:"inference"`
			Control     outcome   `json:"control"`
		}
		if e := readAdmissionReference(base, *r.RouteStop, &receipt); e != nil {
			return e
		}
		var d desktopCandidateDeclaration
		if e := readAdmissionReference(base, r.Declaration, &d); e != nil {
			return e
		}
		endpoint, e := url.Parse(receipt.Endpoint)
		if e != nil || endpoint.Scheme != "http" || endpoint.Hostname() != "127.0.0.1" || endpoint.Port() == "" || endpoint.User != nil || receipt.Schema != "tofa-native-account-route-stop-v1" || receipt.Attempt != d.Attempt || receipt.LauncherPID != process.LauncherPID || receipt.Observed.Before(r.Started) || receipt.Observed.After(r.Finished) || receipt.Inference.HTTP != r.Lifecycle.InferenceAfterStop || receipt.Control.HTTP != r.Lifecycle.ControlAfterStop || (receipt.Inference.Closed && receipt.Control.Closed) != r.Lifecycle.RouteSocketClosed {
			return admissionError("owned route stop linkage mismatch")
		}
	}
	if r.Lifecycle != nil && (r.Lifecycle.LauncherPID != process.LauncherPID || r.Lifecycle.NativePID != process.NativePID) {
		return admissionError("lifecycle PID mismatch")
	}
	if r.Case == "native-crash" || r.Case == "bridge-update" || r.Case == "uninstall-reinstall" {
		if r.ExternalAction == nil {
			return admissionError("external lifecycle action receipt missing")
		}
		var action desktopAttributedInspection
		if e := readAdmissionReference(base, *r.ExternalAction, &action); e != nil {
			return e
		}
		if e := validateDesktopInspection(base, r, action); e != nil {
			return e
		}
		if action.Action != r.Stop || action.NativePID != process.NativePID {
			return admissionError("external lifecycle action mismatch")
		}
	}
	return nil
}

type desktopAttributedInspection struct {
	Schema    string               `json:"schema"`
	Attempt   string               `json:"attempt"`
	Operator  string               `json:"operator"`
	Method    string               `json:"method"`
	Observed  time.Time            `json:"observed_utc"`
	Sources   []desktopEvidenceRef `json:"sources"`
	Action    string               `json:"action,omitempty"`
	NativePID int                  `json:"native_pid,omitempty"`
	Thread    string               `json:"thread,omitempty"`
	Turn      string               `json:"turn,omitempty"`
	Model     string               `json:"model,omitempty"`
	Provider  string               `json:"provider,omitempty"`
	Outcome   string               `json:"outcome"`
}

func validateDesktopInspection(base string, r desktopQualificationCase, i desktopAttributedInspection) error {
	var d desktopCandidateDeclaration
	if e := readAdmissionReference(base, r.Declaration, &d); e != nil {
		return e
	}
	if i.Schema != "tofa-native-account-inspection-v1" || i.Attempt != d.Attempt || i.Operator == "" || (i.Method != "human" && i.Method != "computer_use" && i.Method != "retained_trace_review") || i.Observed.Before(r.Started) || i.Observed.After(r.Finished) || i.Outcome != "observed" || len(i.Sources) == 0 || len(i.Sources) > 16 {
		return admissionError("attributed inspection incomplete")
	}
	for _, ref := range i.Sources {
		if e := readAdmissionReference(base, ref, nil); e != nil {
			return e
		}
	}
	return nil
}
func validateDesktopTransportReceipt(base string, r desktopQualificationCase, event desktopTransportObservation) error {
	if event.Source == "native_relay" {
		if event.Inspection == nil {
			return admissionError("direct native inspection missing")
		}
		var inspection desktopAttributedInspection
		if e := readAdmissionReference(base, *event.Inspection, &inspection); e != nil {
			return e
		}
		if e := validateDesktopInspection(base, r, inspection); e != nil {
			return e
		}
		if inspection.Provider != "openai" || inspection.Model != event.Model || inspection.Thread != event.Thread || inspection.Turn != event.Turn || event.HTTP != 200 {
			return admissionError("direct native inspection mismatch")
		}
		return nil
	}
	var records []map[string]json.RawMessage
	if e := readAdmissionReference(base, r.Requests, &records); e != nil {
		return e
	}
	var found map[string]json.RawMessage
	for _, record := range records {
		var number int
		json.Unmarshal(record["number"], &number)
		if number == event.Number {
			if found != nil {
				return admissionError("duplicate observed request")
			}
			found = record
		}
	}
	if event.Number <= 0 || found == nil {
		return admissionError("observed request missing")
	}
	var role, service, model, original, failure string
	var status int
	var completed, forwarded bool
	json.Unmarshal(found["role"], &role)
	json.Unmarshal(found["service"], &service)
	json.Unmarshal(found["routed_model"], &model)
	json.Unmarshal(found["model"], &original)
	json.Unmarshal(found["status"], &status)
	json.Unmarshal(found["completed"], &completed)
	json.Unmarshal(found["forwarded"], &forwarded)
	json.Unmarshal(found["failure"], &failure)
	expectedRole := event.Role
	if expectedRole == "review" {
		expectedRole = "guardian"
	}
	if expectedRole == "naming" {
		expectedRole = "auxiliary_title"
	}
	if role != expectedRole || service != event.Service || model != event.Model || original != event.OriginalModel || original == "" || status != event.HTTP || completed != event.Completed || failure != event.Failure || !forwarded || string(found["transport"]) == `"synthetic_observer"` {
		return admissionError("request outcome linkage mismatch")
	}
	if event.Request.Path != "request-"+strconv.Itoa(event.Number)+".json" {
		return admissionError("request trace association mismatch")
	}
	var request map[string]json.RawMessage
	if e := readAdmissionReference(base, event.Request, &request); e != nil {
		return e
	}
	var rawModel string
	json.Unmarshal(request["model"], &rawModel)
	if rawModel != event.OriginalModel {
		return admissionError("original request model mismatch")
	}
	var metadata map[string]json.RawMessage
	json.Unmarshal(request["client_metadata"], &metadata)
	if event.Role == "main" {
		thread, okThread := provenanceID(metadata["thread_id"])
		turn, okTurn := provenanceID(metadata["turn_id"])
		if !okThread || !okTurn || thread != event.Thread || turn != event.Turn {
			return admissionError("Main provenance linkage mismatch")
		}
	}
	if event.Role == "review" {
		thread, okThread := provenanceID(metadata["x-codex-parent-thread-id"])
		turn, okTurn := provenanceID(metadata["parent_turn_id"])
		if !okThread || !okTurn || thread != event.ParentThread || turn != event.ParentTurn {
			return admissionError("review provenance linkage mismatch")
		}
	}
	if event.Role == "naming" && !isDesktopTitle(request["client_metadata"]) {
		return admissionError("title contract linkage mismatch")
	}
	return nil
}

func desktopLoaderAdvertised(request map[string]json.RawMessage) bool {
	var tools []map[string]json.RawMessage
	json.Unmarshal(request["tools"], &tools)
	var input []map[string]json.RawMessage
	json.Unmarshal(request["input"], &input)
	for _, item := range input {
		var nested []map[string]json.RawMessage
		json.Unmarshal(item["tools"], &nested)
		tools = append(tools, nested...)
	}
	for _, tool := range tools {
		var typ, name string
		json.Unmarshal(tool["type"], &typ)
		json.Unmarshal(tool["name"], &name)
		if typ == "namespace" && name == "mcp__codex_app" {
			var nested []map[string]json.RawMessage
			json.Unmarshal(tool["tools"], &nested)
			for _, leaf := range nested {
				var leafName string
				json.Unmarshal(leaf["name"], &leafName)
				if leafName == "load_workspace_dependencies" {
					leaf["name"] = json.RawMessage(`"mcp__codex_app__load_workspace_dependencies"`)
					tools = append(tools, leaf)
				}
			}
		}
	}
	for _, tool := range tools {
		var typ, name string
		json.Unmarshal(tool["type"], &typ)
		json.Unmarshal(tool["name"], &name)
		if typ != "function" || name != "mcp__codex_app__load_workspace_dependencies" {
			continue
		}
		var schema map[string]json.RawMessage
		json.Unmarshal(tool["parameters"], &schema)
		var kind string
		json.Unmarshal(schema["type"], &kind)
		var props map[string]any
		json.Unmarshal(schema["properties"], &props)
		var required []any
		json.Unmarshal(schema["required"], &required)
		if kind == "object" && props != nil && len(props) == 0 && string(schema["additionalProperties"]) == "false" && len(required) == 0 {
			return true
		}
	}
	return false
}
