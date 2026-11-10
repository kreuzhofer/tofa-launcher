# #141 retained evidence assessment

Offline assessment of candidate `b839fc4781fda3bf0b71eaef39e1a76b98afed5e`
on November 10, 2026. This applies [ADR 0007](../adr/0007-qualify-desktop-behaviour-across-compatible-updates.md)
and the [release matrix](desktop-release-readiness.md). No Desktop UI launch,
manual rerun or paid inference took place. No production code or admission guard
changes are needed for this evidence-assembly step.

**The account/lifecycle baseline is adequate to prepare #142's targeted
qualification. #141 remains open, and release qualification remains incomplete.**
The later accepted clean exit, matching installed app/engine, successful current
local compatibility check and real-engine lifecycle/security checks support this
decision. The older ordinary-recovery preservation uncertainty remains a specific
release gap; it neither becomes a pass nor invalidates later accepted observations.
This assessment does not authorize a Desktop launch.

## Evidence and reuse decisions

All 99 receipt bindings from the four original reviews/reassessments match. All
four frozen candidate binaries match their recorded hashes. Both prior policy
reassessments still bind their original review. Originals and verdicts were not
edited. Copies, new assessments and original identities are retained separately.

| Behaviour | Evidence and current disposition | Limits |
| --- | --- | --- |
| Account and capabilities; normal exit | Reuse scoped `clean-exit.e84b8bc112ba9506` (`3afa725`): account/plugin/Code Review eligibility observations, smoke/title, normal exit, closed owned routes, unchanged protected non-cache state and history prefixes. Installed app, metadata, archive, transport and engine match. | Visibility/eligibility is not review execution or service switching. |
| Repeat launch and readable history | Reuse scoped `repeat-launch.5fdfe556d4edba09` (`efd74f8`), with current installed-engine cross-launch continuation and lifecycle checks. | The app/engine changed since the observation. This is historical UI evidence supported by current mechanics, not a new UI observation. |
| Launcher crash | Retain scoped `launcher-crash.cbfecaaa8a046312` (`9928136`): owned launcher failure, surviving Desktop, expiry and preservation. Current real-path fault tests establish mechanics. | Does not supply unobserved ordinary-use or recovery-preservation facts. |
| Native crash, interrupted bridge replacement, uninstall/reinstall | Current installed-engine history fault tests plus the public lifecycle/expiry/detachment checks establish mechanics. | No requirement to repeat every fault manually; separate account/history/recovery UI requirements remain. |
| Routing, tools and credentials | Current bundled-engine tool turn, leak controls and inference/control separation checks pass. | Owned local upstreams and disposable profiles; not signed-in switching/Guardian UI evidence. |
| Ordinary recovery | `ordinary-recovery.a9vi4y_n` retains its five positive account/plugin/Code Review/history observations and functional recovery result. | Preservation unresolved; no native inference or unavailable-service relaunch guidance was observed. |

The recorded reuse reviewer is the Codex offline assessment, applying the
maintainer's accepted policy; it does not claim a new human observation or
maintainer sign-off. Since the accepted candidates, changes include collection,
catalog/cache policy, stricter shared preflight/configuration validation,
non-launch diagnostics and the behaviour assessor. Current compatibility and
public-launch/real-engine regressions cover those relevant shared paths. Routing
and stored-history writing are not changed by this evidence-only commit.

The assessment target records the built launcher, source, app executable,
metadata, archive, native transport and engine. It makes no new runtime/skill
inventory claim. Different catalog/model/cache identities do not invalidate these
scopes. A future actual attempt must capture its own current preservation baseline;
no historical snapshot authorizes skipping live safety checks.

## Machine assessment and historical observations

The unchanged public `desktop-qualification assess` command was executed against
the frozen candidate with a real `desktop-compatibility` receipt and newly executed
target-bound test receipts. It establishes five automated rows: launcher crash,
native crash, bridge update, uninstall/reinstall, and routing/tools/credentials.
`coverage_complete` and `release_qualified` are both false.

The other nine machine rows remain missing. This is deliberately distinct from
the accepted scoped observations above. The older private reviews are not full
`tofa-native-account-case-v1` records: the combined case contract asks for more
facts than those reviews establish, including complete transport credential
assertions and ordinary native-use/relaunch-guidance observations. No assertion,
observation timestamp, declaration or process attribution was invented to turn
them into passing machine cases. The full matrix and each original identity are
linked in the separate private coverage assessment.

Final #143 evidence assembly must reconcile these scoped findings with its
required coverage without strengthening old claims. Missing record packaging is
not itself a reason to repeat an accepted human observation. An unobserved
behaviour or unresolved preservation fact still needs evidence.

## Ordinary recovery: precise remaining gap

The retained before/after config inventories identify two changed leaves:
`mcp_servers.node_repl.env.BROWSER_USE_CODEX_APP_VERSION` and
`mcp_servers.node_repl.env.NODE_REPL_TRUSTED_SERVICES`. They store hashes, not
values or writer identity. A version-related key name does not prove an expected
refresh. Trusted services are security-relevant; neither their semantic change
nor its responsible process can be established from these receipts.

The local-skills aggregate also changed, without historical per-file entries.
Later files cannot reconstruct that interval. Plugin-cache changes are diagnostic
under the agreed policy and need no equality exemption or further release gate.
There is no evidence-backed production fix to make from these hashes alone.
The historical preservation verdict stays unresolved.

The smallest new observation is **one ordinary Desktop launch and normal exit**,
separately declared, with current collection of per-file skill inventories, bound
config-leaf differences, credential/settings hashes and existing history prefixes.
It should also cover the still-unobserved ordinary native turn and actionable
guidance for unavailable routed work, with account/capability/history visibility.
No additional injected crash, reinstall, clean-exit campaign or repeat-launch
campaign is required merely to obtain this evidence.

If user-managed/security-sensitive differences recur, retain the exact private
semantic difference and contemporaneous evidence needed to identify and check
its writer/contract. Investigate that specific change; do not exclude generated
fields wholesale, reconstruct old values, or restore shared settings. A clean
new observation establishes present behaviour; it does not rewrite the old verdict.

## #142 prerequisite and remaining matrix

#142 may proceed to preparation using this scoped baseline. Before an actual
attempt, recheck live ownership, sign-in and policy, capture a fresh protected-state
and history baseline, and stop on a failed essential contract. Retain the ordinary
profile, explicit service choice, at least 600 seconds, explicit finish/cancel,
fixed temporary/durable locations and no automatic retry. Any newly observed
security/preservation failure stops the affected work; this is not a drift waiver.

- #141: retain accepted account/history/lifecycle scopes; obtain the narrowly
  missing current ordinary-use/guidance and preservation evidence above.
- #142: actual service labels/switching, signed-in continuation, origin-bound
  review/approval workflow, representative title visibility and history resume.
- #143: supplied-runtime loader/artifact/native-preview coverage, reconciliation
  of machine and scoped evidence, final coverage review and normal-route enablement.

Keep all three qualification tickets open, the integration branch intact and the
production guard in place. No merge, release or model-comparison rerun follows
from this assessment.

## Validation and private artifacts

Active work is under
`/tmp/tofa-presentation-validation/checks/evidence-141-20261110`; the durable copy is
`.qualification/134-manual/diagnostics/evidence-141-20261110/` in the main checkout.
`retained-index.json` binds old receipts, `ordinary-recovery-assessment.json`
classifies the unresolved differences, and `coverage.json` records scope/reuse
and the #142 decision. `assessment-plan.json`, `assessment-verified.json` and
the executed-check receipts/logs retain the actual assessor inputs and output.

The installed-engine run passed, including cross-launch history, all five
history lifecycle subcases, tool/leak controls, public fault/expiry/detachment
checks and assessor regressions. A separate explicit two-engine run passed its
compatibility subtest; four distinct-skill-cache scenarios skipped because the
available engines carry the same system skills. Skips are not passes. The first
run omitted the second-engine variable and its preflight skips are retained.
A wrong receipt digest in a copied assessment plan produced a failed row and
incomplete coverage, confirming integrity failures are not silently accepted.

Full race-suite/vet results and independent Standards/Spec review are recorded
with the final validation receipt. Private artifacts are not published with this
document. This evidence-only change adds no new production behaviour or duplicate
test seam; it runs the existing agreed public boundaries.
