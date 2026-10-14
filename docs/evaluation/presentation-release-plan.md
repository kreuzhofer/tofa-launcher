# Presentation evaluation to release

Status: runtime and namespace implementations merged; #126–#129 are closed.
The latest #130 attempt stopped when a title timeout was followed by a client
disconnect. A local reproduction exposes an evaluator bug: title cancellation
stopped concurrent main work and closed the owned Desktop. The scoped correction
passes local regressions; native requalification and remaining comparison work
are pending. See [the current diagnosis](presentation-title-cancellation-130.md).
The accepted build-20398 baseline passed clean/crash/repeat-launch checks, but
ordinary restart restored a plugin excluded during adapted startup. Native
provider-dependent plugin reconciliation now blocks protected-state preservation;
the manual smoke and comparison wrappers remain stopped. See the
[preservation evidence](evidence/presentation-runtime-126-127/desktop-plugin-preservation-20398.json).
Model capability and release readiness remain unqualified.
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
qualification checkout. It remains retained after merge. Current implementation
is `2fd66e4`; the unchanged namespace launcher uses Go source `deb5ac9`. Earlier
production code `630f523` and checkpoint `c5431df` remain historical. The binary
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

The title-cancellation correction has zero Standards/Spec findings at `472bba0`.
The latest smoke run passed previews but failed identity preservation because the
Desktop app updated mid-run. Startup of build20398 then explicitly removed the
old bundled code-review plugin. Await the maintainer’s baseline decision before
continuing lifecycle/native qualification or another model comparison.
The comparison command is paused; preserve the interrupted attempt and all prior
outcomes. Any further model retry needs its own explicit declaration. The original
three remaining cells stay pending. No release is published.

## Earlier checkpoints

PR #131 merged as `de74659b4f0b458236fc0e4ffc6b59db65029645` after all
macOS/Linux/Windows and artifact checks passed. The maintainer explicitly approved
public branch publication, merge and closure; #126/#127 are closed. The integration
branch is retained. No release was published. #128/#129 remain diagnosis work;
#130 retains its remaining native blockers.

The first #129 feedback check has run against the retained captures: the qualified
synthetic native run passes with one valid loader call/result; both live Kimi runs
fail with an advertised loader and zero invocations. The read-only check and its
three-control result are retained beneath the fixed root in
`checks/release-planning/check-loader-call.py` and `loader-feedback-loop.json`.
This establishes a fast observable signal; it does not yet locate a provider-side
or model-selection cause. Controlled replay subsequently preserved the advertised
loader through the real adapter for all captured main inputs; naming remains
independent and unresolved.

The focused native diagnostic now has a maintainer-requested 600-second observer
deadline, including workspace setup (10 requests, 4096 output tokens). The
synthetic qualification also allows 600 seconds (8 requests, 4096 output tokens).
The unchanged, lifecycle-qualified production launcher accepts only 180/900-second
outer guards, so 600-second runs explicitly use its 900-second guard while the
observer enforces the declared 600-second deadline. Both values are recorded.
Those initial attempts used the unchanged production launcher and retained bridge.

An initial native requalification failed before launch because its control file
sent 600 directly to the launcher. Its unedited evidence remains at private run
`manual.1eergT/runs/6c1981469984486cb18961814fd7aa84`. The wizard now surfaces
the launch error and stops before requesting previews. Regression tests first
reproduced both the rejected contract and the misleading handoff, then passed.
The affected suite ran 59 tests: 57 passed, 2 installed-CLI opt-ins skipped.
A separate real bundled-CLI synthetic calibration using the unchanged production
launcher passed with the corrected contract, observed the loader, delivered all
three artifacts and preserved settings; no paid inference was used. Private run:
`timeout-compatibility-cli/f5bde76a4cc14c0ead521df52bcf9cbb`.

Fresh native qualification now passes against the current installed Pages plugin
and harness revision `afbf6e0`, including maintainer-observed native PPTX/PDF
previews and independent proof validation. The sanitized checkpoint is
`evidence/presentation-runtime-126-127/native-requalification-after-update.json`.
Historical proofs and failed attempts remain unchanged. Both focused model
preflights pass and `run-loader-diagnostic.sh` now references the new proof.

Both focused native attempts are now retained in
`evidence/presentation-runtime-126-127/focused-native-loader-diagnostics.json`.
The exact diagnostic prompt was observed in both initial main requests. Kimi
completed four main requests, probed resource listing and claimed loader absence;
GLM completed one main request and claimed absence without any tool call. Neither
invoked the advertised loader or checked returned executable versions. Both
preserved settings without environment drift. GLM's harness status `completed`
means transport completion, not success at the loader task.

The current native positive control passes the same call/result checker. Five
controlled replays of the new Kimi/GLM main and title inputs passed through the
real adapter with the race detector: main tool inventories survived unchanged;
title requests stayed independent and tool-free. Live provider receipt or
interpretation is not established by that local replay. Kimi naming had a stream
failure while GLM naming completed; #128 remains unresolved.

The predeclared headless comparison is complete: four direct provider requests,
one per model/format, identical synthetic prompt/function definition within each
pair. Both flat functions produced the expected call with `{}`; both namespace
forms produced no call. All four had HTTP 200 and completed Responses. The Kimi
namespace case emitted tool-like control text as ordinary text; GLM claimed no
tools were available. No calls were executed. Protected state remained unchanged.
See `evidence/presentation-runtime-126-127/provider-namespace-diagnostic.json`.

This isolates a model/provider namespace compatibility gap without Desktop,
the adapter, native runtime or the large native catalog. The provider's internal
mechanism remains unobserved and one sample per cell is not a reliability claim.

The approved [minimal adapter follow-up](presentation-namespace-followup.md) is
implemented on the retained integration branch at `deb5ac9`. Kimi K3 and GLM 5.3
main requests now receive flat aliases for namespaced functions; returned calls
recover their original namespace/name. History, selectors and streaming events
use the same mapping. Unsupported definitions and unmapped calls fail explicitly.
Title and Guardian request contracts remain independently routed.

Both live synthetic provider checks through the candidate adapter returned the
expected original function identity; neither executed a tool. See
`evidence/presentation-runtime-126-127/adapted-namespace-diagnostic.json` for the
exact tested revision and limits. Captured native catalogs (271 definitions each)
also pass controlled replay. Final targeted race tests pass, and independent
standards/spec reviews report zero remaining findings at `deb5ac9`.

The isolated candidate is `checks/tofa-namespace-candidate`, SHA-256
`11d28bf933f5230bc9c06744d98726b51d096504e9e683471f21b9c369fbea1e`.
The prior qualified binary and evidence remain retained. The final full race suite
passes (`go test -race ./...`, adapter package 315.164 seconds). Clean exit, forced
launcher crash and repeat launch preserve protected files byte-for-byte. Ordinary
Desktop restart passes with three native MCP ready events and no failures or peer
rejections; only the two approved executable references change back to the bundled
engine. Node/CUA arithmetic, a real CLI tool call, ordinary effective-configuration
comparison and owned temporary uninstall all pass. Normal launcher credentials
remain unchanged. Evidence:
`evidence/presentation-runtime-126-127/namespace-mcp-lifecycle.json` and
`evidence/presentation-runtime-126-127/namespace-implementation-checks.json`.

Fresh native synthetic qualification now passes for this exact candidate, including
independent proof validation, the actual loader call/result, executable identities,
artifacts, maintainer-observed native PPTX/PDF previews and settings preservation.
See `evidence/presentation-runtime-126-127/namespace-native-requalification.json`.
The preceding attempt timed out without preview observation and remains unchanged;
the maintainer confirmed they had not inspected its previews.

The existing `/tmp/tofa-presentation-validation/run-loader-diagnostic.sh` now pins
this candidate and the fresh proof. Both network-enabled preflights pass. The
predeclared fresh native Kimi and GLM attempts now pass the focused loader/version
checks: one actual loader call/result each, followed by successful execution of
the returned Node/Python paths and correct observed versions in the final answer.
Each completed three main requests. Protected files stayed byte-identical, with
no environment drift. The native loader returned no manifest path; neither model
reported one, so that diagnostic request component remains unavailable.

Both independent naming requests failed with `stream_failure`; the original
aggregate `infra_blocked` records remain intact. Their main tool workflows passed.
See `evidence/presentation-runtime-126-127/namespace-native-loader-diagnostics.json`.
Controlled namespace/flat comparisons and the candidate's native results support
the scoped namespace compatibility correction. Successful execution contradicts
missing runtime/registration or a need for dependency installation. Provider
internals and reliability across repeated tasks remain unestablished.

#129 now has its native implementation evidence and remains open pending
publication/merge disposition. Retain the integration branch. Next is #128's
captured-request naming diagnosis before fresh #130 deck comparisons; this result
does not promote support or release status, or change historical deck outcomes.

#128 diagnostic implementation is now committed at `cf6cbec`, reviewed against
`29e2983` with zero remaining Standards/Spec findings. The observer exports safe
transport stages and categories and retains original exceptions/provider errors
privately. Operator instructions distinguish completed main work from failed or
pending naming. One explicitly approved headless replay of the captured naming
request completed successfully; both local baseline/current adapter replays passed.
This does not explain the intermittent native failure. The predeclared instrumented
native attempt now passes both provider completion and maintainer-observed title
visibility: run `32dee8c7142b41ef968da5677a04af5e`, 69.031 seconds including setup,
unchanged launcher, protected settings preserved and no environment drift. Main
and naming each completed one HTTP 200 response; no tools or Guardian requests ran.
See [the #128 handoff](desktop-naming-128.md) and
`evidence/presentation-runtime-126-127/naming-128-native.json`.

The evaluation disposition is to retain instrumentation and independent naming
outcomes in #130 without automatic retries or waiting on failed titles. The
original intermittent cause and native runtime-regression status remain unknown;
this success is not a naming fix or repeated-reliability claim. #128 and #129
remain open pending integration publication/merge disposition. Resolve prerequisite
tickets, freeze identities and requalify the changed harness before predeclaring
#130's four fresh deck attempts. Retain the integration branch and historical proofs.
