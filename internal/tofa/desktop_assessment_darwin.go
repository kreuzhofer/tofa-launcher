package tofa

import (
	"encoding/hex"
	"encoding/json"
	"errors"
	"path/filepath"
	"strings"
	"time"
)

// This maintainer assessment never grants admission, invokes a supplied engine,
// rewrites a receipt, or substitutes a fixture observation for a native one.
type desktopAssessmentPlan struct {
	Schema        string                              `json:"schema"`
	Target        desktopAdmissionIdentity            `json:"target"`
	Compatibility desktopEvidenceRef                  `json:"compatibility"`
	Behaviours    map[string]desktopBehaviourEvidence `json:"behaviours"`
}
type desktopBehaviourEvidence struct {
	Case   *desktopEvidenceRef   `json:"case,omitempty"`
	Checks []desktopEvidenceRef  `json:"checks,omitempty"`
	Reuse  *desktopEvidenceReuse `json:"reuse,omitempty"`
}
type desktopEvidenceReuse struct {
	Reviewer string            `json:"reviewer"`
	Reason   string            `json:"reason"`
	Changes  map[string]string `json:"changes"`
	Impact   string            `json:"impact"`
}
type desktopBehaviourResult struct {
	Status         string                `json:"status"`
	Reason         string                `json:"reason"`
	OriginalStatus string                `json:"original_status,omitempty"`
	Reuse          *desktopEvidenceReuse `json:"reuse,omitempty"`
	Checks         []desktopEvidenceRef  `json:"checks,omitempty"`
	Evidence       *desktopEvidenceRef   `json:"evidence,omitempty"`
}
type desktopAssessmentResult struct {
	Schema           string                            `json:"schema"`
	Target           desktopAdmissionIdentity          `json:"target"`
	Compatibility    desktopEvidenceRef                `json:"compatibility"`
	CoverageComplete bool                              `json:"coverage_complete"`
	ReleaseQualified bool                              `json:"release_qualified"`
	Behaviours       map[string]desktopBehaviourResult `json:"behaviours"`
}

// Required coverage is fixed by the release matrix, never selected by a plan.
var desktopBehaviourCases = map[string]string{
	"account-capabilities": "clean-exit", "clean-exit": "clean-exit",
	"repeat-launch-history": "repeat-launch", "ordinary-recovery": "ordinary-launch",
	"launcher-crash": "launcher-crash", "native-crash": "native-crash",
	"bridge-update": "bridge-update", "uninstall-reinstall": "uninstall-reinstall",
	"service-switching": "service-switching", "history-continuation": "history-resume",
	"review-routing": "review-routing", "naming": "launch-naming",
	"runtime-previews": "runtime-preview", "routing-tools-credentials": "",
}

// These rows may be established by real-path fault tests; visible recovery,
// account usability and readable history remain separate mandatory UI rows.
var desktopAutomatedBehaviours = map[string][]string{
	"launcher-crash":            {"TestDesktopNativeCandidateHistoryLifecycle/launcher_crash", "TestDesktopNativeCandidateCrashRecoveryPreservesStateAndExpiresRoute"},
	"native-crash":              {"TestDesktopNativeCandidateHistoryLifecycle/client_crash"},
	"bridge-update":             {"TestDesktopNativeCandidateHistoryLifecycle/interrupted_replacement", "TestDesktopNativeCandidateLifecycleInterruptedReplacementRemainsCallable"},
	"uninstall-reinstall":       {"TestDesktopNativeCandidateHistoryLifecycle/uninstall_and_reinstall", "TestDesktopNativeCandidateUninstallDetachesSavedReference"},
	"routing-tools-credentials": {"TestDesktopNativeCandidateBundledEngineTurn", "TestDesktopNativeCandidateIsolatesInferenceAndControl"},
}
var desktopBehaviourRegressions = map[string][]string{
	"service-switching":    {"TestDesktopNativeCandidateHistoryAcrossLaunches"},
	"history-continuation": {"TestDesktopNativeCandidateHistoryAcrossLaunches"},
	"review-routing":       {"TestDesktopNativeCandidateReviewOrigin", "TestDesktopNativeCandidateReviewRejectsUnknownOrigin", "TestDesktopBundledEngineAutomaticApproval", "TestDesktopNativeCandidateDirectNativeHistoryInterrupt"},
	"naming":               {"TestDesktopLightningUsesToolFreeStructuredNaming", "TestDesktopUnavailableNamingDoesNotFallBackOrBlockMain", "TestDesktopNamingCompletesWhileMainStreams"},
}

func (a *App) desktopAssessment(args []string) error {
	fs := flags("desktop-qualification assess")
	path := fs.String("assessment", "", "")
	if e := fs.Parse(args); e != nil {
		return e
	}
	if *path == "" || fs.NArg() != 0 {
		return errors.New("use desktop-qualification assess --assessment PATH")
	}
	var plan desktopAssessmentPlan
	if _, e := readDesktopEvidence(*path, &plan); e != nil {
		return e
	}
	if plan.Schema != "tofa-desktop-assessment-plan-v1" {
		return errors.New("unsupported Desktop assessment schema")
	}
	base := filepath.Dir(*path)
	var compatibility desktopCompatibilityReport
	if e := readAdmissionReference(base, plan.Compatibility, &compatibility); e != nil {
		return e
	}
	if e := validateAssessmentCompatibility(compatibility, plan.Target); e != nil {
		return e
	}
	for name, entry := range plan.Behaviours {
		if entry.Reuse != nil && entry.Case == nil {
			return errors.New("reuse requires original case evidence")
		}
		if _, ok := desktopBehaviourCases[name]; !ok {
			return errors.New("unknown required Desktop behaviour")
		}
	}
	result := desktopAssessmentResult{Schema: "tofa-desktop-assessment-v1", Target: plan.Target, Compatibility: plan.Compatibility, Behaviours: map[string]desktopBehaviourResult{}}
	result.CoverageComplete = true
	for name, caseName := range desktopBehaviourCases {
		row := desktopBehaviourResult{Status: "missing", Reason: "required evidence not supplied"}
		if entry, ok := plan.Behaviours[name]; ok {
			if entry.Case != nil {
				row = assessDesktopCase(base, entry, caseName, plan.Target)
			} else if required, automated := desktopAutomatedBehaviours[name]; automated && len(entry.Checks) > 0 {
				row = desktopBehaviourResult{Status: "established", Reason: "executed real-path checks establish mechanics only; UI coverage remains separate", Checks: entry.Checks}
				if e := validateDesktopExecutedChecks(base, entry.Checks, plan.Target, required); e != nil {
					row.Status = "failed"
					row.Reason = e.Error()
				}
			}
			if row.Status == "established" || row.Status == "reused" {
				if required := desktopBehaviourRegressions[name]; len(required) > 0 {
					row.Checks = entry.Checks
					if e := validateDesktopExecutedChecks(base, entry.Checks, plan.Target, required); e != nil {
						row.Status = "failed"
						row.Reason = e.Error()
					}
				}
			}
		}
		result.Behaviours[name] = row
		if row.Status != "established" && row.Status != "reused" {
			result.CoverageComplete = false
		}
	}
	return json.NewEncoder(a.Out).Encode(result)
}
func validateAssessmentCompatibility(r desktopCompatibilityReport, id desktopAdmissionIdentity) error {
	source, err := hex.DecodeString(id.Source)
	if err != nil || len(source) != 20 || id.Source != strings.ToLower(id.Source) {
		return errors.New("assessment target source identity missing or invalid")
	}
	for _, value := range id.Hashes {
		if value != "absent" && !validDigest(value) {
			return errors.New("assessment target component identity invalid")
		}
	}
	if r.Schema != "tofa-desktop-compatibility-v1" || r.Status != "compatible" || r.ReleaseQualified || r.Checked.IsZero() || r.Checked.After(time.Now().Add(time.Minute)) {
		return errors.New("local compatibility is missing or failed; do not enable the route")
	}
	for _, name := range []string{"platform-layout", "ownership", "account-policy", "provider-configuration", "secret-exclusion"} {
		if r.Checks[name] != "passed" {
			return errors.New("local compatibility contract incomplete")
		}
	}
	for key, target := range map[string]string{"engine_sha256": "engine", "launcher_sha256": "launcher", "application_sha256": "application", "bundle_sha256": "application_info"} {
		if !validDigest(r.Identity[key]) || r.Identity[key] != id.Hashes[target] {
			return errors.New("local compatibility identity is not the assessment target")
		}
	}
	return nil
}

func assessDesktopCase(base string, entry desktopBehaviourEvidence, requiredCase string, target desktopAdmissionIdentity) desktopBehaviourResult {
	ref := *entry.Case
	row := desktopBehaviourResult{Status: "failed", Reason: "invalid original evidence", Evidence: &ref}
	var record desktopQualificationCase
	if err := readAdmissionReference(base, ref, &record); err != nil {
		row.Reason = err.Error()
		return row
	}
	if requiredCase == "" || record.Case != requiredCase {
		row.Reason = "evidence does not cover the required behaviour"
		return row
	}
	// Validate the declaration, process/binary bindings, snapshots and observations
	// using their original identity BEFORE considering the target installation.
	if err := validateDesktopCase(filepath.Dir(filepath.Join(base, ref.Path)), record, record.Identity, map[string]bool{}); err != nil {
		row.Reason = err.Error()
		return row
	}
	row.OriginalStatus = "established"
	if len(entry.Checks) > 0 {
		row.Checks = entry.Checks
		if err := validateDesktopExecutedChecks(base, entry.Checks, target, nil); err != nil {
			row.Reason = err.Error()
			return row
		}
	}
	row.Status = "established"
	row.Reason = "original case establishes this behaviour for the target"
	if !desktopIntegrationIdentityEqual(record.Identity, target) {
		row.Status = "missing"
		row.Reason = "original behaviour established; target changes require a reuse assessment"
		if entry.Reuse == nil {
			return row
		}
		row.Reuse = entry.Reuse
		row.Checks = entry.Checks
		reuse := entry.Reuse
		changes := strings.Split(desktopIdentityChanges(record.Identity, target), ", ")
		if strings.TrimSpace(reuse.Reviewer) == "" || strings.TrimSpace(reuse.Reason) == "" || len(reuse.Changes) != len(changes) {
			row.Status = "failed"
			row.Reason = "reuse needs attributed reasoning for every changed category"
			return row
		}
		for _, name := range changes {
			if strings.TrimSpace(reuse.Changes[name]) == "" {
				row.Status = "failed"
				row.Reason = "reuse omits a changed category"
				return row
			}
		}
		if reuse.Impact == "affected" {
			row.Reason = "affected behaviour needs new evidence; original result retained"
			return row
		}
		if reuse.Impact != "unaffected" {
			row.Status = "failed"
			row.Reason = "unsupported impact assessment"
			return row
		}
		if err := validateDesktopExecutedChecks(base, entry.Checks, target, []string{"TestDesktopNativePreflightPreservesOtherEngineSkills/compatibility"}); err != nil {
			row.Status = "failed"
			row.Reason = err.Error()
			return row
		}
		row.Status = "reused"
		row.Reason = "original evidence validated; attributed impact assessment and executed target checks support reuse"
	}
	return row
}
