package tofa

import (
	"bytes"
	"encoding/json"
	"errors"
	"io"
	"os"
	"path/filepath"
	"strings"
	"time"
)

type desktopExecutedChecks struct {
	Schema   string                   `json:"schema"`
	Identity desktopAdmissionIdentity `json:"identity"`
	Started  time.Time                `json:"started_utc"`
	Finished time.Time                `json:"finished_utc"`
	ExitCode *int                     `json:"exit_code"`
	Command  []string                 `json:"command"`
	Log      desktopEvidenceRef       `json:"log"`
}

// Consume actual go test -json events. A test name, zero exit flag, package pass
// with no tests, or skipped opt-in test does not establish the named contract.
func validateDesktopExecutedChecks(base string, refs []desktopEvidenceRef, target desktopAdmissionIdentity, required []string) error {
	required = desktopExecutedScope(required)
	passed := map[string]bool{}
	if len(refs) == 0 || len(refs) > 16 {
		return errors.New("executed target checks missing")
	}
	for _, ref := range refs {
		var receipt desktopExecutedChecks
		if e := readAdmissionReference(base, ref, &receipt); e != nil {
			return e
		}
		if receipt.Schema != "tofa-desktop-executed-checks-v1" || !desktopIntegrationIdentityEqual(receipt.Identity, target) || receipt.ExitCode == nil || *receipt.ExitCode != 0 || receipt.Started.IsZero() || receipt.Finished.Before(receipt.Started) || receipt.Finished.After(time.Now().Add(time.Minute)) {
			return errors.New("executed checks failed or target identity mismatched")
		}
		if len(receipt.Command) < 4 || filepath.Base(receipt.Command[0]) != "go" || receipt.Command[1] != "test" {
			return errors.New("unsupported check execution contract")
		}
		jsonOutput := false
		for _, arg := range receipt.Command[2:] {
			if arg == "-json" {
				jsonOutput = true
			}
		}
		if !jsonOutput {
			return errors.New("check execution requires go test JSON events")
		}
		checkBase := filepath.Dir(filepath.Join(base, ref.Path))
		if e := readAdmissionReference(checkBase, receipt.Log, nil); e != nil {
			return e
		}
		path := filepath.Join(checkBase, receipt.Log.Path)
		f, e := os.Open(path)
		if e != nil {
			return errors.New("executed check log unavailable")
		}
		raw, e := io.ReadAll(io.LimitReader(f, (32<<20)+1))
		f.Close()
		if e != nil || len(raw) > 32<<20 || digestBytes(raw) != receipt.Log.SHA256 {
			return errors.New("executed check log integrity invalid")
		}
		dec := json.NewDecoder(bytes.NewReader(raw))
		ran, finished, skipped := map[string]bool{}, map[string]bool{}, map[string]bool{}
		packagePassed := false
		for {
			var event struct {
				Action  string
				Package string
				Test    string
				Time    time.Time
			}
			e := dec.Decode(&event)
			if e == io.EOF {
				break
			}
			if e != nil {
				return errors.New("invalid check event log")
			}
			if event.Action == "fail" {
				return errors.New("executed checks contain a failure")
			}
			if event.Package != "github.com/kreuzhofer/tofa-launcher/internal/tofa" {
				continue
			}
			if event.Time.Before(receipt.Started) || event.Time.After(receipt.Finished) {
				return errors.New("check event outside execution receipt")
			}
			switch event.Action {
			case "run":
				ran[event.Test] = true
			case "skip":
				skipped[event.Test] = true
			case "pass":
				if event.Test == "" {
					packagePassed = true
				} else {
					finished[event.Test] = ran[event.Test]
				}
			}
		}
		if !packagePassed {
			return errors.New("check package did not complete")
		}
		for _, name := range required {
			if !finished[name] {
				continue
			}
			skip := false
			for test := range skipped {
				if test == name || strings.HasPrefix(test, name+"/") {
					skip = true
				}
			}
			if !skip {
				passed[name] = true
			}
		}
	}
	for _, name := range required {
		if !passed[name] {
			return errors.New("required executed check missing or skipped: " + name)
		}
	}
	return nil
}

// Go emits a passing parent even when -run selects only one subtest. These
// contract-bearing descendants must have actually run too. This is the versioned
// coverage contract, not a count inferred from whichever events happened to arrive.
func desktopExecutedScope(required []string) []string {
	descendants := map[string][]string{
		"TestDesktopNativeCandidateBundledEngineTurn":           {"handshake/url-path-probe", "handshake/header", "handshake/stderr-leak-control", "disconnect/url-path-probe", "disconnect/header", "disconnect/stderr-leak-control"},
		"TestDesktopNativeCandidateIsolatesInferenceAndControl": {"native_credentials_alone", "control_cannot_infer", "missing", "wrong", "malformed_native_bearer", "duplicate", "comma", "inference_cannot_read_control", "inference_cannot_stop", "inference_cannot_cancel_review", "legacy_inference_cannot_cancel_review", "wrong_method", "query", "authorized"},
		"TestDesktopNativeCandidateReviewOrigin":                {"TF_allow_through_observer", "TF_deny_through_observer", "native_deny_through_observer", "native_allow_after_inspection", "TF_explicit_Guardian_override", "TF_pending_cancellation", "native_pending_cancellation"},
		"TestDesktopNativeCandidateReviewRejectsUnknownOrigin":  {"missing_parent_turn", "unknown_parent_turn", "conflicting_encoded_parent", "changed_policy", "missing_Main_provenance", "duplicate_parent", "duplicate_schema", "native_changed_inventory", "native_wrong_service_reviewer", "review_transport_failure", "native_review_transport_failure", "unavailable_Guardian", "native_conflicting_review_role", "native_conflicting_review_source", "invalid_lifecycle_metadata"},
		"TestDesktopBundledEngineAutomaticApproval":             {"allow", "default_Guardian_for_Kimi", "distinct_Kimi_Guardian", "allow_after_inspection", "deny", "invalid_assessment", "provider_failure", "cancel_review", "native_review_deadline"},
	}
	result := append([]string(nil), required...)
	for _, name := range required {
		for _, sub := range descendants[name] {
			result = append(result, name+"/"+sub)
		}
	}
	return result
}
