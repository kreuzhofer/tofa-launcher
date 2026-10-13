# Presentation evaluation to release

Status: runtime qualification and final integration review are complete. The
maintainer explicitly approved public branch publication, PR merge and closure of
#126/#127 on 2026-10-13; integration is proceeding. Model capability and release
readiness remain unqualified.
The maintainer approved the three phases below on 2026-10-13. Cost is not a
constraint; experimental bounds and separate outcomes remain part of the method.

## Execution order and completion gates

| Phase | Work | Done when |
| --- | --- | --- |
| 1. Runtime integration | #126 CLI and #127 native Desktop | Actual-client qualification and both separately declared model outcomes are retained; Standards/Spec findings are resolved; tests pass; the validated integration is merged and ticket closure states its exact scope. Model calibration success is not an acceptance requirement. |
| 2a. Naming diagnosis | [#128](https://github.com/kreuzhofer/tofa-launcher/issues/128): independent title stream failure | A red-capable replay distinguishes connection, adapter, provider and client failure; fix plus regression or a precise external blocker is recorded; bounded native validation and operator handoff reflect separate naming status. |
| 2b. Loader diagnosis | [#129](https://github.com/kreuzhofer/tofa-launcher/issues/129): advertised loader never called | Request adaptation is checked, focused explicit-loader Kimi and GLM controls are retained, native call/result stages are distinguished, and the next treatment is declared. |
| 3. Fresh model comparison | [#130](https://github.com/kreuzhofer/tofa-launcher/issues/130): post-diagnosis 03/04 on Kimi and GLM | Candidate identities and four attempts are predeclared; original prompts/limits remain; separate observations and failures are retained; #119 records the next campaign decision. |
| Campaign and release | Existing #119, #120 and #106 | The remaining matrix, repeated guidance comparison, held-out task and applicable regressions are assessed; existing platform owners qualify the same immutable release candidate; promotion follows its separate release gate. |

Phases 2a and 2b are independent. Diagnosis can start against the pinned integration
revision while merge review finishes. Phase 3 depends on both diagnosis dispositions
and reviewed runtime integration. A failed control is retained, not replaced by
an unplanned model. Broader campaign work is not silently reduced to these four runs.

## Evidence and current findings

- [Runtime implementation and chronology](presentation-runtime-126-127.md) is the
  feature record. [Review](evidence/presentation-runtime-126-127/review.md) keeps
  Standards and Spec separate. The fixed review baseline is `2c8df02` (#122).
- [Production native qualification](evidence/presentation-runtime-126-127/production-native-success.json)
  passed with the genuine loader, finalized PPTX/PDF and maintainer previews.
  [Lifecycle checks](evidence/presentation-runtime-126-127/production-mcp-lifecycle.json)
  bind the exact production bridge and native identities.
- [Native model calibrations](evidence/presentation-runtime-126-127/native-model-calibrations.json)
  retain both negative runs, model/case identities, source hashes and human preview
  observations. Case 03 made 70 main requests, produced a five-slide German PPTX
  but no PDF, and ended at the deadline. Case 04 made 79 main requests, produced
  no deck and reached the request ceiling. Both read the skill, never called the
  loader, failed independent naming, and preserved protected state without drift.
- CLI calibration outcomes remain in their [separate record](evidence/presentation-runtime-126-127/cli-model-calibrations.json).
  These runs are calibrations; none replace #119's original matrix or repeated comparison.
- Loader exposure in captured client requests is established; provider-side receipt
  is not established by that capture alone. Unsupported `resources/list` does not
  establish absence of an advertised callable tool. Title root cause is unresolved.
- Language and varied-command stalls stay linked to #124 and #125. Native
  approval/resume, guidance adoption, supported-model status and Windows remain
  outside the runtime tickets. #106 retains the combined release decision and
  its native platform dependencies; this effort does not operate Windows.

## Continuity rules

The integration branch is `feat/126-127-presentation-runtime` in the existing
qualification checkout. Retain it until the review gate passes. Latest qualified
production code is `630f523`; evidence checkpoint `c5431df`. The production binary
hash is recorded in the native and lifecycle evidence; documentation-only commits
do not imply a different binary. New executable or harness bytes require checking
which proofs have become stale before launch.

GitHub issues are the status/dependency source. This document is the execution and
evidence index. At each phase boundary, update the ticket with the exact revision,
commands/tests, outcome, evidence references, unresolved questions and next action.
Continue this session while useful; use compact at a phase boundary if needed.
A handoff file is for moving to another directory, harness or colleague, not a
second competing project plan. Every implementation ticket must be independently
understandable without reconstructing this chat.

All new private runs and temporary diagnostics remain under the fixed
`/tmp/tofa-presentation-validation` root (`/private/tmp` is its macOS alias).
Keep raw captures in their original locations: proof identities bind paths and
hashes. Commit sanitized decisions, per-attempt provenance and assessments before
changing phase. The temporary root is not permanent archival storage; do not
silently delete or relocate it. Any later raw-evidence archival policy needs an
explicit retention decision that preserves historical identity.

Preserve ordinary profiles, credentials, skills, plugins and runtime dependencies.
The only authorized shared-setting exception is the two verified MCP executable
references. No settings snapshots are restored. Do not modify or reinstall the
native application, reuse private pipe identities, or bypass refused UI control.
Human native previews stay separately attributed; computer-generated claims do
not substitute for them.

Merge, evidence publication, experimental candidate publication, qualification and
stable release are distinct actions. User authorization to implement/merge these
runtime tickets is not a waiver of #119/#120/#106 or native-platform release gates.

## Current next action

The runtime branch is reviewed and ready at the recorded integration checkpoint.
Automatic approval review rejected publishing the full branch to the public GitHub
repository because merge/closure authorization did not explicitly authorize that
public egress. The maintainer subsequently explicitly approved publishing this branch to the
public repository, opening/merging its PR and closing #126/#127. That approval
resolves the publication blocker; raw private runs and credentials stay local.
The local PR body is prepared under the fixed validation root. #128 and #129 can
proceed with local diagnosis while integration completes. #130 retains
its native blockers. No raw private run data is part of the proposed push.

The first #129 feedback check has run against the retained captures: the qualified
synthetic native run passes with one valid loader call/result; both live Kimi runs
fail with an advertised loader and zero invocations. The read-only check and its
three-control result are retained beneath the fixed root in
`checks/release-planning/check-loader-call.py` and `loader-feedback-loop.json`.
This establishes a fast observable signal; it does not yet locate a provider-side
or model-selection cause. Next: replay request adaptation locally, then use the
separately declared actual-native diagnostic contract in #129.
