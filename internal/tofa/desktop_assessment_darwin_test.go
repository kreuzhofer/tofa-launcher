package tofa

import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

// Fixture builders write synthetic receipts; assertions exercise App.Run only.
func assessmentFixture(t *testing.T) (string, map[string]any) {
	t.Helper()
	proofPath, id := qualificationFixture(t)
	root := filepath.Dir(proofPath)
	compatibility := map[string]any{"schema": "tofa-desktop-compatibility-v1", "status": "compatible", "checked_utc": time.Now().UTC(), "release_qualified": false,
		"identity":   map[string]string{"engine_sha256": id.Hashes["engine"], "launcher_sha256": id.Hashes["launcher"], "application_sha256": id.Hashes["application"], "bundle_sha256": id.Hashes["application_info"]},
		"checks":     map[string]string{"platform-layout": "passed", "ownership": "passed", "account-policy": "passed", "provider-configuration": "passed", "secret-exclusion": "passed"},
		"unobserved": []string{"native-ui", "routing-turns", "model-availability", "release-qualification"}}
	ref := assessmentWrite(t, root, "compatibility.json", compatibility)
	return root, map[string]any{"schema": "tofa-desktop-assessment-plan-v1", "target": id, "compatibility": ref, "behaviours": map[string]any{}}
}
func assessmentWrite(t *testing.T, root, name string, value any) desktopEvidenceRef {
	t.Helper()
	raw, err := json.Marshal(value)
	if err != nil {
		t.Fatal(err)
	}
	if err = os.WriteFile(filepath.Join(root, name), raw, 0600); err != nil {
		t.Fatal(err)
	}
	return desktopEvidenceRef{Path: name, SHA256: digestBytes(raw)}
}
func runAssessment(t *testing.T, root string, plan map[string]any) (map[string]any, error) {
	t.Helper()
	assessmentWrite(t, root, "assessment.json", plan)
	var out bytes.Buffer
	app := App{Dir: t.TempDir(), Out: &out}
	err := app.Run([]string{"desktop-qualification", "assess", "--assessment", filepath.Join(root, "assessment.json")})
	result := map[string]any{}
	if out.Len() > 0 {
		if e := json.Unmarshal(out.Bytes(), &result); e != nil {
			t.Fatal(e)
		}
	}
	return result, err
}
func TestDesktopAssessmentEmptyCoverageIsIncomplete(t *testing.T) {
	root, plan := assessmentFixture(t)
	result, err := runAssessment(t, root, plan)
	if err != nil {
		t.Fatal(err)
	}
	if result["coverage_complete"] != false || result["release_qualified"] != false {
		t.Fatalf("false pass: %v", result)
	}
	rows, ok := result["behaviours"].(map[string]any)
	if !ok || len(rows) < 12 {
		t.Fatal("required behaviours omitted")
	}
	for name, raw := range rows {
		if raw.(map[string]any)["status"] != "missing" {
			t.Fatalf("%s falsely covered", name)
		}
	}
}

func TestDesktopAssessmentValidatesLegacyCaseInOriginalIdentity(t *testing.T) {
	root, plan := assessmentFixture(t)
	raw, err := os.ReadFile(filepath.Join(root, "clean-exit/case.json"))
	if err != nil {
		t.Fatal(err)
	}
	ref := desktopEvidenceRef{Path: "clean-exit/case.json", SHA256: digestBytes(raw)}
	plan["behaviours"] = map[string]any{"account-capabilities": map[string]any{"case": ref}}
	result, err := runAssessment(t, root, plan)
	if err != nil {
		t.Fatal(err)
	}
	row := result["behaviours"].(map[string]any)["account-capabilities"].(map[string]any)
	if row["status"] != "established" || result["coverage_complete"] != false {
		t.Fatalf("scoped result: %v", row)
	}
	// Tampering cannot be hidden by preserving the submitted case digest.
	if err = os.WriteFile(filepath.Join(root, "clean-exit/process.json"), []byte(`{"schema":"changed"}`), 0600); err != nil {
		t.Fatal(err)
	}
	result, err = runAssessment(t, root, plan)
	if err != nil {
		t.Fatal(err)
	}
	row = result["behaviours"].(map[string]any)["account-capabilities"].(map[string]any)
	if row["status"] != "failed" {
		t.Fatal("tampered original receipt accepted")
	}
}

func assessmentChecks(t *testing.T, root string, id desktopAdmissionIdentity, tests ...string) desktopEvidenceRef {
	t.Helper()
	now := time.Now().UTC().Add(-time.Minute)
	var log bytes.Buffer
	for _, name := range tests {
		for _, action := range []string{"run", "pass"} {
			json.NewEncoder(&log).Encode(map[string]any{"Time": now, "Action": action, "Package": "github.com/kreuzhofer/tofa-launcher/internal/tofa", "Test": name})
		}
	}
	json.NewEncoder(&log).Encode(map[string]any{"Time": now, "Action": "pass", "Package": "github.com/kreuzhofer/tofa-launcher/internal/tofa"})
	if err := os.WriteFile(filepath.Join(root, "executed.jsonl"), log.Bytes(), 0600); err != nil {
		t.Fatal(err)
	}
	return assessmentWrite(t, root, "executed-checks.json", map[string]any{"schema": "tofa-desktop-executed-checks-v1", "identity": id, "started_utc": now, "finished_utc": now.Add(time.Second), "exit_code": 0, "command": []string{"go", "test", "-json", "./internal/tofa"}, "log": desktopEvidenceRef{Path: "executed.jsonl", SHA256: digestBytes(log.Bytes())}})
}
func TestDesktopAssessmentReusesOnlyExplicitlySupportedBehaviour(t *testing.T) {
	root, plan := assessmentFixture(t)
	id := plan["target"].(desktopAdmissionIdentity)
	id.Hashes["engine"] = strings.Repeat("f", 64)
	plan["target"] = id
	var compatibility map[string]any
	raw, err := os.ReadFile(filepath.Join(root, "compatibility.json"))
	if err != nil {
		t.Fatal(err)
	}
	if err = json.Unmarshal(raw, &compatibility); err != nil {
		t.Fatal(err)
	}
	compatibility["identity"].(map[string]any)["engine_sha256"] = id.Hashes["engine"]
	plan["compatibility"] = assessmentWrite(t, root, "compatibility.json", compatibility)
	raw, err = os.ReadFile(filepath.Join(root, "clean-exit/case.json"))
	if err != nil {
		t.Fatal(err)
	}
	entry := map[string]any{"case": desktopEvidenceRef{Path: "clean-exit/case.json", SHA256: digestBytes(raw)}}
	plan["behaviours"] = map[string]any{"account-capabilities": entry}
	result, err := runAssessment(t, root, plan)
	if err != nil {
		t.Fatal(err)
	}
	row := result["behaviours"].(map[string]any)["account-capabilities"].(map[string]any)
	if row["status"] != "missing" || row["original_status"] != "established" {
		t.Fatal("changed target silently reused or original result discarded")
	}
	checks := assessmentChecks(t, root, id, "TestDesktopNativePreflightPreservesOtherEngineSkills/compatibility")
	entry["checks"] = []desktopEvidenceRef{checks}
	entry["reuse"] = map[string]any{"reviewer": "fixture-maintainer", "reason": "Account UI unchanged; compatible engine contract checked separately.", "changes": map[string]string{"engine": "Protocol-only compatible update; account surface unaffected."}, "impact": "unaffected"}
	result, err = runAssessment(t, root, plan)
	if err != nil {
		t.Fatal(err)
	}
	rows := result["behaviours"].(map[string]any)
	row = rows["account-capabilities"].(map[string]any)
	if row["status"] != "reused" || rows["runtime-previews"].(map[string]any)["status"] != "missing" || result["coverage_complete"] != false {
		t.Fatalf("wrong reuse scope: %v", result)
	}
}

func TestDesktopAssessmentFaultChecksDoNotInventUIObservations(t *testing.T) {
	root, plan := assessmentFixture(t)
	id := plan["target"].(desktopAdmissionIdentity)
	check := assessmentChecks(t, root, id, "TestDesktopNativeCandidateHistoryLifecycle/client_crash")
	plan["behaviours"] = map[string]any{"native-crash": map[string]any{"checks": []desktopEvidenceRef{check}}, "account-capabilities": map[string]any{"checks": []desktopEvidenceRef{check}}}
	result, err := runAssessment(t, root, plan)
	if err != nil {
		t.Fatal(err)
	}
	rows := result["behaviours"].(map[string]any)
	if rows["native-crash"].(map[string]any)["status"] != "established" {
		t.Fatal("executed real-path fault coverage ignored")
	}
	if rows["account-capabilities"].(map[string]any)["status"] != "missing" {
		t.Fatal("automated checks invented native account observation")
	}
	// A parent test pass with a skipped required opt-in subtest is not evidence.
	log, err := os.ReadFile(filepath.Join(root, "executed.jsonl"))
	if err != nil {
		t.Fatal(err)
	}
	log = bytes.Replace(log, []byte(`"Action":"pass"`), []byte(`"Action":"skip"`), 1)
	if err = os.WriteFile(filepath.Join(root, "executed.jsonl"), log, 0600); err != nil {
		t.Fatal(err)
	}
	var receipt map[string]any
	raw, err := os.ReadFile(filepath.Join(root, "executed-checks.json"))
	if err != nil {
		t.Fatal(err)
	}
	if err = json.Unmarshal(raw, &receipt); err != nil {
		t.Fatal(err)
	}
	receipt["log"] = desktopEvidenceRef{Path: "executed.jsonl", SHA256: digestBytes(log)}
	check = assessmentWrite(t, root, "executed-checks.json", receipt)
	plan["behaviours"] = map[string]any{"native-crash": map[string]any{"checks": []desktopEvidenceRef{check}}}
	result, err = runAssessment(t, root, plan)
	if err != nil {
		t.Fatal(err)
	}
	if result["behaviours"].(map[string]any)["native-crash"].(map[string]any)["status"] != "failed" {
		t.Fatal("skipped opt-in test counted as pass")
	}
}

func TestDesktopAssessmentCompleteCoverageRetainsAllBoundaries(t *testing.T) {
	root, plan := assessmentFixture(t)
	id := plan["target"].(desktopAdmissionIdentity)
	// Explicit spec examples, not computed from the evaluator's required map.
	names := []string{"TestDesktopNativeCandidateBundledEngineTurn", "TestDesktopNativeCandidateIsolatesInferenceAndControl", "TestDesktopNativeCandidateHistoryAcrossLaunches", "TestDesktopNativeCandidateReviewOrigin", "TestDesktopNativeCandidateReviewRejectsUnknownOrigin", "TestDesktopBundledEngineAutomaticApproval", "TestDesktopNativeCandidateDirectNativeHistoryInterrupt", "TestDesktopLightningUsesToolFreeStructuredNaming", "TestDesktopUnavailableNamingDoesNotFallBackOrBlockMain", "TestDesktopNamingCompletesWhileMainStreams"}
	for parent, leaves := range map[string][]string{
		"TestDesktopNativeCandidateBundledEngineTurn":           {"handshake/url-path-probe", "handshake/header", "handshake/stderr-leak-control", "disconnect/url-path-probe", "disconnect/header", "disconnect/stderr-leak-control"},
		"TestDesktopNativeCandidateIsolatesInferenceAndControl": {"native_credentials_alone", "control_cannot_infer", "missing", "wrong", "malformed_native_bearer", "duplicate", "comma", "inference_cannot_read_control", "inference_cannot_stop", "inference_cannot_cancel_review", "legacy_inference_cannot_cancel_review", "wrong_method", "query", "authorized"},
		"TestDesktopNativeCandidateReviewOrigin":                {"TF_allow_through_observer", "TF_deny_through_observer", "native_deny_through_observer", "native_allow_after_inspection", "TF_explicit_Guardian_override", "TF_pending_cancellation", "native_pending_cancellation"},
		"TestDesktopNativeCandidateReviewRejectsUnknownOrigin":  {"missing_parent_turn", "unknown_parent_turn", "conflicting_encoded_parent", "changed_policy", "missing_Main_provenance", "duplicate_parent", "duplicate_schema", "native_changed_inventory", "native_wrong_service_reviewer", "review_transport_failure", "native_review_transport_failure", "unavailable_Guardian", "native_conflicting_review_role", "native_conflicting_review_source", "invalid_lifecycle_metadata"},
		"TestDesktopBundledEngineAutomaticApproval":             {"allow", "default_Guardian_for_Kimi", "distinct_Kimi_Guardian", "allow_after_inspection", "deny", "invalid_assessment", "provider_failure", "cancel_review", "native_review_deadline"},
	} {
		for _, leaf := range leaves {
			names = append(names, parent+"/"+leaf)
		}
	}
	check := assessmentChecks(t, root, id, names...)
	cases := map[string]string{"account-capabilities": "clean-exit", "clean-exit": "clean-exit", "repeat-launch-history": "repeat-launch", "ordinary-recovery": "ordinary-launch", "launcher-crash": "launcher-crash", "native-crash": "native-crash", "bridge-update": "bridge-update", "uninstall-reinstall": "uninstall-reinstall", "service-switching": "service-switching", "history-continuation": "history-resume", "review-routing": "review-routing", "naming": "launch-naming", "runtime-previews": "runtime-preview"}
	entries := map[string]any{"routing-tools-credentials": map[string]any{"checks": []desktopEvidenceRef{check}}}
	for behaviour, name := range cases {
		raw, err := os.ReadFile(filepath.Join(root, name, "case.json"))
		if err != nil {
			t.Fatal(err)
		}
		entries[behaviour] = map[string]any{"case": desktopEvidenceRef{Path: name + "/case.json", SHA256: digestBytes(raw)}, "checks": []desktopEvidenceRef{check}}
	}
	plan["behaviours"] = entries
	result, err := runAssessment(t, root, plan)
	if err != nil {
		t.Fatal(err)
	}
	if result["coverage_complete"] != true || result["release_qualified"] != false {
		t.Fatalf("full scoped assessment wrong: %v", result)
	}
	// Raw artifact files without both native preview observations cannot complete coverage.
	var preview desktopQualificationCase
	raw, err := os.ReadFile(filepath.Join(root, "runtime-preview/case.json"))
	if err != nil {
		t.Fatal(err)
	}
	if err = json.Unmarshal(raw, &preview); err != nil {
		t.Fatal(err)
	}
	preview.Observations = nil
	ref := assessmentWrite(t, filepath.Join(root, "runtime-preview"), "case.json", preview)
	ref.Path = "runtime-preview/case.json"
	entries["runtime-previews"] = map[string]any{"case": ref}
	result, err = runAssessment(t, root, plan)
	if err != nil {
		t.Fatal(err)
	}
	if result["coverage_complete"] != false || result["behaviours"].(map[string]any)["runtime-previews"].(map[string]any)["status"] != "failed" {
		t.Fatal("artifact existence replaced native previews")
	}
}

func TestDesktopAssessmentRejectsBrokenCompatibilityBindings(t *testing.T) {
	for _, scenario := range []string{"tampered", "failed", "identity", "missing-check", "unknown-behaviour"} {
		t.Run(scenario, func(t *testing.T) {
			root, plan := assessmentFixture(t)
			var compatibility map[string]any
			raw, err := os.ReadFile(filepath.Join(root, "compatibility.json"))
			if err != nil {
				t.Fatal(err)
			}
			if err = json.Unmarshal(raw, &compatibility); err != nil {
				t.Fatal(err)
			}
			switch scenario {
			case "tampered":
				if err = os.WriteFile(filepath.Join(root, "compatibility.json"), []byte(`{}`), 0600); err != nil {
					t.Fatal(err)
				}
			case "failed":
				compatibility["status"] = "incompatible"
			case "identity":
				compatibility["identity"].(map[string]any)["engine_sha256"] = strings.Repeat("f", 64)
			case "missing-check":
				delete(compatibility["checks"].(map[string]any), "ownership")
			case "unknown-behaviour":
				plan["behaviours"] = map[string]any{"made-up-pass": map[string]any{}}
			}
			if scenario != "tampered" {
				plan["compatibility"] = assessmentWrite(t, root, "compatibility.json", compatibility)
			}
			if _, err = runAssessment(t, root, plan); err == nil {
				t.Fatal("invalid assessment accepted")
			}
		})
	}
}

func TestDesktopAssessmentFailedChecksCannotHideBehindOldSuccess(t *testing.T) {
	for _, scenario := range []string{"failed-exit", "failed-event", "no-tests", "wrong-identity", "tampered-log"} {
		t.Run(scenario, func(t *testing.T) {
			root, plan := assessmentFixture(t)
			id := plan["target"].(desktopAdmissionIdentity)
			check := assessmentChecks(t, root, id, "TestDesktopNativePreflightPreservesOtherEngineSkills/compatibility")
			raw, err := os.ReadFile(filepath.Join(root, "executed-checks.json"))
			if err != nil {
				t.Fatal(err)
			}
			var receipt map[string]any
			if err = json.Unmarshal(raw, &receipt); err != nil {
				t.Fatal(err)
			}
			switch scenario {
			case "failed-exit":
				receipt["exit_code"] = 1
			case "wrong-identity":
				receipt["identity"].(map[string]any)["hashes"].(map[string]any)["engine"] = strings.Repeat("f", 64)
			case "failed-event", "no-tests", "tampered-log":
				log, err := os.ReadFile(filepath.Join(root, "executed.jsonl"))
				if err != nil {
					t.Fatal(err)
				}
				if scenario == "failed-event" {
					log = bytes.Replace(log, []byte(`"Action":"pass"`), []byte(`"Action":"fail"`), 1)
				} else {
					log = []byte("{}\n")
				}
				if err = os.WriteFile(filepath.Join(root, "executed.jsonl"), log, 0600); err != nil {
					t.Fatal(err)
				}
				if scenario != "tampered-log" {
					receipt["log"] = desktopEvidenceRef{Path: "executed.jsonl", SHA256: digestBytes(log)}
				}
			}
			check = assessmentWrite(t, root, "executed-checks.json", receipt)
			raw, err = os.ReadFile(filepath.Join(root, "clean-exit/case.json"))
			if err != nil {
				t.Fatal(err)
			}
			plan["behaviours"] = map[string]any{"clean-exit": map[string]any{"case": desktopEvidenceRef{Path: "clean-exit/case.json", SHA256: digestBytes(raw)}, "checks": []desktopEvidenceRef{check}}}
			result, err := runAssessment(t, root, plan)
			if err != nil {
				t.Fatal(err)
			}
			row := result["behaviours"].(map[string]any)["clean-exit"].(map[string]any)
			if row["status"] != "failed" || row["original_status"] != "established" {
				t.Fatalf("failed contract hidden or history rewritten: %v", row)
			}
		})
	}
}

func TestDesktopAssessmentCollectorChangeAndNarrowInvalidation(t *testing.T) {
	root, plan := assessmentFixture(t)
	id := plan["target"].(desktopAdmissionIdentity)
	id.Source = strings.Repeat("f", 40)
	id.Hashes["harness/desktop_qualification.py"] = strings.Repeat("1", 64)
	plan["target"] = id
	check := assessmentChecks(t, root, id, "TestDesktopNativePreflightPreservesOtherEngineSkills/compatibility")
	raw, err := os.ReadFile(filepath.Join(root, "clean-exit/case.json"))
	if err != nil {
		t.Fatal(err)
	}
	changes := map[string]string{"source": "Collector-only source change; launch path unchanged.", "harness": "New evidence reporting only; original raw bindings validate."}
	entries := map[string]any{}
	for _, name := range []string{"clean-exit", "account-capabilities"} {
		entries[name] = map[string]any{"case": desktopEvidenceRef{Path: "clean-exit/case.json", SHA256: digestBytes(raw)}, "checks": []desktopEvidenceRef{check}, "reuse": map[string]any{"reviewer": "fixture-maintainer", "reason": "Existing observation sufficient; new checks reveal no gap.", "changes": changes, "impact": "unaffected"}}
	}
	plan["behaviours"] = entries
	result, err := runAssessment(t, root, plan)
	if err != nil {
		t.Fatal(err)
	}
	if result["behaviours"].(map[string]any)["clean-exit"].(map[string]any)["status"] != "reused" {
		t.Fatal("collector change demanded UI repetition")
	}
	entries["account-capabilities"].(map[string]any)["reuse"].(map[string]any)["impact"] = "affected"
	result, err = runAssessment(t, root, plan)
	if err != nil {
		t.Fatal(err)
	}
	rows := result["behaviours"].(map[string]any)
	if rows["clean-exit"].(map[string]any)["status"] != "reused" || rows["account-capabilities"].(map[string]any)["status"] != "missing" {
		t.Fatal("one affected behaviour invalidated unrelated evidence")
	}
	delete(changes, "harness")
	result, err = runAssessment(t, root, plan)
	if err != nil {
		t.Fatal(err)
	}
	if result["behaviours"].(map[string]any)["clean-exit"].(map[string]any)["status"] != "failed" {
		t.Fatal("incomplete change justification accepted")
	}
}

func TestDesktopAssessmentRequiresUnknownChangesAlongsideKnownOnes(t *testing.T) {
	root, plan := assessmentFixture(t)
	id := plan["target"].(desktopAdmissionIdentity)
	id.Source = strings.Repeat("f", 40)
	id.Hashes["new-security-contract"] = strings.Repeat("1", 64)
	plan["target"] = id
	check := assessmentChecks(t, root, id, "TestDesktopNativePreflightPreservesOtherEngineSkills/compatibility")
	raw, err := os.ReadFile(filepath.Join(root, "clean-exit/case.json"))
	if err != nil {
		t.Fatal(err)
	}
	entry := map[string]any{"case": desktopEvidenceRef{Path: "clean-exit/case.json", SHA256: digestBytes(raw)}, "checks": []desktopEvidenceRef{check}, "reuse": map[string]any{"reviewer": "fixture-maintainer", "reason": "Only source explained.", "changes": map[string]string{"source": "Compatible source update."}, "impact": "unaffected"}}
	plan["behaviours"] = map[string]any{"clean-exit": entry}
	result, err := runAssessment(t, root, plan)
	if err != nil {
		t.Fatal(err)
	}
	if result["behaviours"].(map[string]any)["clean-exit"].(map[string]any)["status"] != "failed" {
		t.Fatal("unknown security change silently omitted")
	}
}

func TestDesktopAssessmentRejectsFilteredParentCoverage(t *testing.T) {
	root, plan := assessmentFixture(t)
	id := plan["target"].(desktopAdmissionIdentity)
	check := assessmentChecks(t, root, id, "TestDesktopNativeCandidateBundledEngineTurn", "TestDesktopNativeCandidateIsolatesInferenceAndControl")
	var receipt map[string]any
	raw, err := os.ReadFile(filepath.Join(root, "executed-checks.json"))
	if err != nil {
		t.Fatal(err)
	}
	if err = json.Unmarshal(raw, &receipt); err != nil {
		t.Fatal(err)
	}
	receipt["command"] = []string{"go", "test", "-json", "./internal/tofa", "-run", "^(TestDesktopNativeCandidateBundledEngineTurn|TestDesktopNativeCandidateIsolatesInferenceAndControl)$/authorized"}
	check = assessmentWrite(t, root, "executed-checks.json", receipt)
	plan["behaviours"] = map[string]any{"routing-tools-credentials": map[string]any{"checks": []desktopEvidenceRef{check}}}
	result, err := runAssessment(t, root, plan)
	if err != nil {
		t.Fatal(err)
	}
	if result["behaviours"].(map[string]any)["routing-tools-credentials"].(map[string]any)["status"] != "failed" {
		t.Fatal("partial run counted as full security coverage")
	}
}

func TestDesktopAssessmentRetainsGeneratedSkillsAfterSourceUpdate(t *testing.T) {
	root, plan := assessmentFixture(t)
	base := filepath.Join(root, "clean-exit")
	raw, _ := os.ReadFile(filepath.Join(base, "case.json"))
	var record desktopQualificationCase
	json.Unmarshal(raw, &record)
	files := map[string]map[string]string{"skills": {"example/SKILL.md": strings.Repeat("d", 64), ".system/.codex-system-skills.marker": strings.Repeat("1", 64), ".system/SKILL.md": strings.Repeat("2", 64)}, "agent_skills": {".": "absent"}}
	engine := filepath.Join(root, "source-engine")
	os.WriteFile(engine, []byte("original engine"), 0700)
	contract := map[string]any{"schema": "tofa-generated-system-skills-v1", "sources": []any{map[string]any{"engine": engine, "engine_sha256": digestBytes([]byte("original engine")), "version": "original", "files": map[string]string{".system/.codex-system-skills.marker": strings.Repeat("1", 64), ".system/SKILL.md": strings.Repeat("2", 64)}}}}
	ref := assessmentWrite(t, base, "system-skills.json", contract)
	record.SystemSkillsContract = &ref
	id := record.Identity
	raw, _ = json.Marshal(files["skills"])
	id.Hashes["skills"] = digestBytes(raw)
	if e := bindDesktopSystemSkills(&id, &desktopSystemSkills{Path: filepath.Join(base, ref.Path)}, files["skills"]); e != nil {
		t.Fatal(e)
	}
	record.Identity = id
	record.Before["skills"] = id.Hashes["skills"]
	record.After["skills"] = id.Hashes["skills"]
	var declaration map[string]any
	raw, _ = os.ReadFile(filepath.Join(base, record.Declaration.Path))
	json.Unmarshal(raw, &declaration)
	declaration["identity"] = id
	record.Declaration = assessmentWrite(t, base, record.Declaration.Path, declaration)
	var start map[string]any
	raw, _ = os.ReadFile(filepath.Join(base, record.Start.Path))
	json.Unmarshal(raw, &start)
	start["declaration_sha256"] = record.Declaration.SHA256
	record.Start = assessmentWrite(t, base, record.Start.Path, start)
	for _, pair := range []struct {
		ref   *desktopEvidenceRef
		state map[string]string
	}{{&record.BeforeSnapshot, record.Before}, {&record.AfterSnapshot, record.After}} {
		var snapshot map[string]any
		raw, _ = os.ReadFile(filepath.Join(base, pair.ref.Path))
		json.Unmarshal(raw, &snapshot)
		snapshot["identity"] = id
		snapshot["skill_files"] = files
		snapshot["protected"] = pair.state
		*pair.ref = assessmentWrite(t, base, pair.ref.Path, snapshot)
	}
	caseRef := assessmentWrite(t, root, "clean-exit/case.json", record)
	plan["target"] = id
	plan["behaviours"] = map[string]any{"account-capabilities": map[string]any{"case": caseRef}}
	os.WriteFile(engine, []byte("updated engine"), 0700)
	result, e := runAssessment(t, root, plan)
	if e != nil {
		t.Fatal(e)
	}
	row := result["behaviours"].(map[string]any)["account-capabilities"].(map[string]any)
	if row["status"] != "established" {
		t.Fatalf("intact original evidence failed after engine update: %v", row)
	}
	os.WriteFile(filepath.Join(base, ref.Path), []byte("tampered contract"), 0600)
	result, e = runAssessment(t, root, plan)
	if e != nil {
		t.Fatal(e)
	}
	if result["behaviours"].(map[string]any)["account-capabilities"].(map[string]any)["status"] != "failed" {
		t.Fatal("changed historical contract accepted")
	}
}
