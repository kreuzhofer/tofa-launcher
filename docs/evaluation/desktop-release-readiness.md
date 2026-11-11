# Desktop integration release readiness

Agreed November 10, 2026, against source baseline `eff3ce5`. The maintainer
accepted Q1–Q3 with “yes to all” and Q4–Q5 with “all recommended”. This is the
acceptance policy for the next experimental macOS Desktop prerelease. It does
not claim that implementation or qualification is complete, authorize a release,
or change unrelated packaging/installation release requirements.

## Scope and meaning

Keep #134's full advertised integration: ordinary native account and installed
capabilities, explicit service switching, origin-bound reviews, the accepted
launch-wide naming policy, preserved history and recovery, and the supplied
presentation runtime with native PPTX/PDF previews. No feature is silently dropped.

Keep the existing signed-in macOS ARM64 compatibility boundary. Compatible newer
clients are supported through required contracts, not an exact-build allowlist;
this does not promise every historical client or Windows/Intel Desktop support.
The existing documented minimum versions remain until an evidence-backed change.

Maintainers qualify release behaviour. Ordinary users launch through the normal
entry point with automatic local sign-in, ownership, protocol and routing checks;
they do not need a private campaign, harness checkout or proof bound to another
person's home directory. Essential contract failures stop the affected operation
with actionable guidance. This is a required admission change, not removal of the
current production guard before its replacement is implemented and validated.

Preservation means no unintended TOFA changes to user-managed settings,
credentials, instructions, history or capabilities. Identified native-generated
refreshes may change bytes when their ownership and relevant contracts are
established; retain the differences. Do not exclude everything called generated,
or treat permission/routing changes as harmless metadata. Unknown or
security-relevant differences need investigation. The mixed-engine startup
regression must remain detectable. Never restore a shared settings snapshot or
invent historical attribution to obtain a pass.

## Required behavioural matrix

| Behaviour | Passing requirement | Evidence boundary |
| --- | --- | --- |
| Launch, account and capabilities | Normal TOFA launch retains the signed-in account, enabled plugins and Code Review eligibility | Public-launch tests plus actual Desktop observation |
| Service selection and credentials | Picker identifies service; native/Token Factory requests use the intended service and credentials; capabilities remain local; invalid/expired authorization rejected; no silent fallback | Installed-engine routing and leak controls plus actual selection and continuation |
| Conversations, tools and approvals | Turns and tool continuations work; Guardian/native reviews follow originating work; allow/deny/cancel decisions are enforced; switching does not redirect pending work | Public-launch/real-engine tests plus representative actual Desktop workflow |
| Naming | Agreed launch-wide TOFA policy and disclosure work; title failure remains separate from main work | Engine contract and error tests plus actual generated title visibility |
| History and recovery | Existing history remains readable; resume preserves context/selection; ordinary launch retains native use; TOFA documents relaunch guidance for unavailable routed work (accepted in-app reconnect limitation below) | Automated history/lifecycle tests plus actual history and ordinary recovery observations |
| Shutdown and faults | Clean exit, launcher/native failure, bridge replacement interruption and uninstall leave recoverable owned state without unintended user-state changes | Automated real launcher/engine fault coverage where sufficient; actual Desktop checks only for recovery behaviour it cannot establish |
| Presentation integration | Installed skill discovers and calls the actual loader; supplied runtime produces valid owned synthetic artifacts; both correct native previews open | Runtime/engine tests plus actual loader evidence and PPTX/PDF preview observations |
| Updated clients | Required contracts work; affected behaviours are checked; unaffected evidence is reused with a recorded reason | Installed-engine compatibility checks and targeted actual Desktop observation |

A successful ordinary path is required; the policy does not demand that upstream
services never fail. Errors must be explicit, isolated where appropriate, and
must not bypass approvals, leak credentials, lose history or silently reroute.
A provider outage or unavailable selected model is not by itself evidence of a
TOFA defect; retain the failed attempt and its attribution. Missing critical
coverage is not a pass.

## Accepted ordinary-Desktop limitation — November 11, 2026

The maintainer explicitly accepted the observed reconnect limitation for the next
experimental prerelease. Opening Desktop directly can select its bundled engine
rather than TOFA's bridge. A routed conversation then retries its inactive local
endpoint without displaying TOFA-specific relaunch guidance. This is a known
limitation, not a passing actionable-error observation, and it does not by itself
block this prerelease or require another identical recovery run.

TOFA's launch disclosure and troubleshooting documentation must explain: routed
conversations require launching through TOFA. In ordinary Desktop, stop the
reconnecting turn, quit Desktop, launch through TOFA and reopen the same
conversation. Do not change models to attempt provider migration. Automatic
TOFA-specific wording inside directly opened Desktop is no longer required.

Native use and readable history remain required. No silent service fallback,
credential leakage, unintended user-state change or history damage is permitted.
Preserve route-expiry and authorization checks. Do not patch Desktop, persist
credentials, introduce a recovery daemon or use shared-config restoration to
avoid this limitation. Failed and incomplete receipts remain unchanged; review
accepted facts separately without manufacturing a successful finish or new turn.
Historical preservation differences remain unknown where evidence is absent.
The production guard, preview qualification and remaining release work are
unchanged. The launch-disclosure implementation must be checked before enablement.

## Diagnostic evidence and separate work

Catalog/model identities and plugin-cache hashes/deltas are diagnostic provenance,
not equality gates. Selected models still need to be available and satisfy the
required contract; use explicit selections with no automatic substitution.
Plugin enablement and actual usability remain checks.

Exact app/engine/runtime/launcher identities, timing and logs identify what was
tested. Receipt/archive/declaration/artifact integrity hashes still bind evidence
to its original run. A changed identity triggers compatibility/impact assessment,
not a verdict that all old results failed. Reuse never relabels an old observation
as a new observation.

Model-quality certification, deck-design benchmarks, exhaustive model pairings,
the #130 comparison and #120 guidance adoption are separate work. They are not
substitutes for integration tests and do not become prerequisites merely because
a different model or cache version appeared. Completion here does not silently
close campaign parents or establish the broader #106 release decision.

## Update and retest rules

For each reused result, record the original evidence, what changed, the behaviour
it covers, the compatibility checks run and the reason no new UI observation is
needed. If the required behaviour was never observed, reuse cannot supply it.

| Change or signal | Automated work | Actual Desktop work |
| --- | --- | --- |
| Catalog/model/cache churn alone | Availability and required-contract checks; retain identities/deltas | No campaign repeat solely for changed hashes |
| App or bundled-engine update | Discover current executable/layout; run affected installed-engine protocol, account/ownership, routing and lifecycle checks | Retest affected or unproven account/UI/history/preview behaviour, not every case by default |
| TOFA routing, authorization, review or naming change | Corresponding public-launch/real-engine regressions, including negative controls | Targeted visible selection/continuation/title or review behaviour if affected |
| TOFA lifecycle/preflight/bridge/install change | Ownership, preservation, fault/recovery and competing-state tests on the real path where applicable | Targeted ordinary recovery/history/account check when automated evidence is insufficient |
| Runtime/skill update | Discovery/loader/version and synthetic artifact checks | Relevant previews when their behaviour is affected or unproven; not an unrelated routing campaign |
| Collector, documentation or test-only change | Check affected collection/assertion behaviour and receipt integrity | No repeat unless the change reveals a material gap in what prior evidence established |
| Observed defect or failed essential contract | Reproduce and diagnose; refuse the affected unsafe/incompatible path | Targeted confirmation after correction, only where needed |

Do not count fixture account replies as actual account usability, file existence
as native preview success, or a tool-free response as Guardian execution. Merely
having a test in the repository is not an executed result: installed-engine tests
are opt-in and must be recorded separately from the default full suite.

## Accepted evidence and remaining work

### November 11 runtime and native-preview observation

The scoped synthetic runtime check on executable candidate `9c5d3bc` is accepted.
The actual Desktop trace contains the namespaced `codex_app` loader call with
empty arguments, its returned supplied-runtime paths, and the completed artifact
command in the same conversation turn. Node reported `v24.22.1` for package
`24.22.1-cua.1`; Python reported `3.12.14`. The one-slide PPTX and one-page PDF
passed artifact validation, and the maintainer recorded opening both correct
native previews. Desktop quit normally and both owned route sockets closed.

Independent review verified 79 retained files against their originals and 1,925
existing history prefixes. The only semantic configuration change was the new
test workspace trust entry, explicitly accepted by the maintainer in the guide;
removing that entry in memory reproduced the exact pre-run normalized digest.
Other managed settings and credentials were preserved. Plugin-cache and captured
native-generated skill refreshes follow the existing policy.

The preceding collector failure remains failed. Its correction is covered by
[permanent collector regressions](presentation-collector-regressions.md), committed
separately as `7da020a`; that source promotion did not change this run's frozen
executable or guide. Private raw receipts remain outside tracked documents.

This accepts actual-loader execution, synthetic artifact generation and native
preview visibility only. It does not certify model quality, implicit skill
discovery, live naming or approval execution. Those retain separate evidence.
Do not repeat this observation solely to package the release. Final admission,
behaviour-specific evidence reuse and release review remain required; the
production guard is unchanged.

### Earlier baseline and retained obligations

- `3afa725` clean exit is accepted under the revised plugin-cache policy: exact
  smoke response, normal exit, account/plugin/Code Review observations, main and
  title success, and remaining preservation checks passed.
- `efd74f8` repeat-launch/history and `9928136` launcher-crash results remain
  accepted scoped observations. Assess their reuse by behaviour; do not erase
  them or automatically transfer them to every changed path.
- Ordinary recovery worked functionally. Its historical config/skill differences
  remain unresolved. Missing old skill detail cannot be reconstructed, and the
  security-relevant trusted-services difference is not automatically harmless.
  Apply the agreed preservation meaning in a separate evidence assessment.
- Current clean-exit smoke does not prove Guardian execution, service switching
  or presentation previews. Those require their own adequate evidence.
- `eff3ce5` passed the full Go race suite, vet, 42 Python tests and both reviews.
  Selected installed-engine tests have separate November 10 evidence; the default
  full suite does not execute all installed-engine paths.

The subsequent [#143 admission and reuse assessment](desktop-admission-143.md)
records normal-user enablement and the accepted scopes without rewriting receipts.

At the earlier policy baseline, production admission required all 12 cases against one
installation identity, including local source/harness/home/profile paths. Normal
launch still uses the legacy guarded route unless candidate/proof activation is
provided. Removing those coupling requirements is implementation work, not an
accomplishment of this policy document. Keep the integration branch and current
production guard until the replacement passes the relevant requirements.

## Ticket responsibilities and order

- [#134](https://github.com/kreuzhofer/tofa-launcher/issues/134) owns the amended
  spec: behaviour-based readiness, ordinary-user admission separate from
  maintainer qualification, preservation meaning and unchanged routing/security
  contracts. [ADR 0007](../adr/0007-qualify-desktop-behaviour-across-compatible-updates.md)
  records the boundary decision.
- [#141](https://github.com/kreuzhofer/tofa-launcher/issues/141) owns account,
  preservation and lifecycle evidence, truthful collection, semantic assessment
  of native-managed refreshes and the automated/manual evidence split. Update
  stale blockers; retain original receipts and accepted results.
- [#142](https://github.com/kreuzhofer/tofa-launcher/issues/142) owns switching,
  review, naming and history-continuation evidence. Its actual Desktop attempts
  require the relevant safe account/lifecycle baseline, not mechanically repeated
  unrelated fault cases. Do not claim these behaviours from clean-exit smoke.
- [#143](https://github.com/kreuzhofer/tofa-launcher/issues/143) owns actual
  runtime/previews and the final admission change: normal-user checks, explicit
  reuse decisions, rejection of failed contracts, and removal of private
  per-user proof prerequisites. All required #141/#142 behaviours still need
  adequate evidence before route enablement; no partial feature mode is implied.

The subsequent implementation and validation are tracked in the
[#143 admission assessment](desktop-admission-143.md). Remaining release packaging
and the revised #130 comparison declaration are separate decisions.

## Operator and evidence constraints

Human checks retain at least 600 seconds including setup, explicit finish/cancel,
no automatic retry or model substitution, `/tmp/tofa-presentation-validation` for
runs and durable copies outside `/tmp`. Separately declared 900-second comparison
budgets remain separate. Preserve failed/incomplete attempts and raw private
receipts; publish only sanitized findings. This interview launches no Desktop,
runs no inference and changes no shared account/settings/skill state.

Collector maintenance and regression coverage are recorded in
[presentation collector regressions](presentation-collector-regressions.md).
