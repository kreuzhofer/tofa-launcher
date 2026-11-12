# Shared candidate plan after native-account integration (#106)

Decision recorded November 12, 2026: **combined release readiness is incomplete**.
The macOS Desktop integration is accepted for its recorded behaviours. A new
shared published candidate and its Mac/Windows CLI lifecycle verdicts are still
needed. This plan does not publish a release, launch Desktop, authorize live
inference, or promote an Experimental model combination to Supported.

## Candidate and scope

The product baseline is merged `b2135469a26337e40ad91caf76f926e34327e646`
([PR #144](https://github.com/kreuzhofer/tofa-launcher/pull/144)). Its tree equals
reviewed integration head `1fbee5a3e14f7dce27a8a22493665ccc1fa0d863`. Preserve
`fix/134-plugin-inventory` and its frozen development candidate; that local binary
is not a published release artifact.

Proposed next version: **v0.1.0-rc.18**, subject to checking that the tag and release
are still unused at publication approval. No tag is reserved or created here.
Freeze the final source SHA and runner revision before publication; a later
document-only descendant may carry this plan, with the product diff recorded.
Any product correction requires renewed impact assessment and fresh immutable
candidate bytes. Never replace an existing candidate or relabel its evidence.

Included scope: the rc17 baseline plus presentation tool namespace/runtime
integration (#126/#127), naming corrections (#128), and signed-in native-account
Desktop integration (#134–#143, including admission #145/#146). The source diff
from rc17, not this issue list, defines all included changes. Mac Desktop remains
experimental within its signed-in ARM64 compatibility boundary. Windows Desktop
remains disabled under [ADR 0004](../adr/0004-windows-desktop-awaits-supported-ownership.md).
Windows CLI is part of the shared release; Windows Desktop is not a prerequisite.
No new platform or model support promotion is implied.

Compared with rc17 source `b293f1e0d49d53ca410b786ac28cb055f5ce5e20`, the
installation/uninstallation scripts, `qualify_macos.py`, `qualify_windows.py`,
`live_compat.py` and `evaluation_proxy.py` are unchanged. Shared adapter and request
handling did change, including namespace translation, authorization separation
and review-origin handling; this is why native CLI checks on both platforms still
matter. A Mac Desktop-only verdict or hosted Windows amd64 result cannot replace
Windows ARM64 CLI execution.

## Evidence ledger and reuse

Original reports, receipts, failures and incomplete observations keep their
original identities. Current assessment is separate from historical outcomes.

| Evidence | Current use | What it does not establish |
| --- | --- | --- |
| rc14 accepted Mac/Windows CLI lifecycle in [#23](https://github.com/kreuzhofer/tofa-launcher/issues/23) | Historical lifecycle baseline and established runner boundary | Qualification of a later binary |
| rc15 completion in [#104](https://github.com/kreuzhofer/tofa-launcher/issues/104) | Completed historical candidate preparation/Mac result; leave ticket closed | Current candidate identity |
| rc16 Windows failure and cleanup in [report](v0.1.0-rc.16-windows.md) / [#110](https://github.com/kreuzhofer/tofa-launcher/issues/110) | Retained failure, diagnosis and regression requirements | Windows acceptance; local diagnostic rebuilds are not release assets |
| rc17 Mac CLI lifecycle and transient provider recovery in [#106's report](https://github.com/kreuzhofer/tofa-launcher/issues/106#issuecomment-6080122102) and [recovery](https://github.com/kreuzhofer/tofa-launcher/issues/106#issuecomment-6081379985) | Accepted scoped historical run; provider disappearance alone does not invalidate it | Current binary qualification or an uninterrupted provider success |
| rc17 evidence [PR #115](https://github.com/kreuzhofer/tofa-launcher/pull/115) | Still-open historical evidence PR, linked at its recorded revisions | Merged current evidence; do not silently incorporate or rewrite it |
| [#143 admission assessment](../evaluation/desktop-admission-143.md) | Behaviour-specific accepted Desktop observations and installed-engine compatibility results; seven recent reviews bind 267 unchanged receipts | New actual-Desktop observations or an exact-artifact installer verdict |
| [Post-merge CI 43075794191](https://github.com/kreuzhofer/tofa-launcher/actions/runs/43075794191) | Success at `b213546` for artifacts, macOS, Windows and Linux; publication skipped | Published candidate or native Windows ARM64 acceptance |

Reuse follows [ADR 0007](../adr/0007-qualify-desktop-behaviour-across-compatible-updates.md)
and the [acceptance matrix](../evaluation/desktop-release-readiness.md). The
following rows carry the originals and reasons from the admission assessment:

| Accepted behaviour | Original scope | Reuse reason / condition |
| --- | --- | --- |
| Account, enabled capabilities, clean exit | `3afa725` clean exit | Same native-account path; current public startup/ownership/policy tests cover admission changes |
| Repeat launch, history and launcher crash | `efd74f8`, `9928136`, retained lifecycle tests | Storage and bridge behaviour unchanged by final admission; keep original scope limits |
| Visible TF → native → TF and context | `service-switching.81a930919206127f` | Dispatcher unchanged; no smoke-response inference about approvals |
| Routed resume/tool and native history | `history-resume.e2506ffd3acb779b`, `native-history-seed.91atr_ph`, `history-resume.d011310d5cb3424f` | Selection/storage unchanged; seed collector stays incomplete, recovered transcript evidence remains separate |
| Native/Guardian reviews, title visibility | `review-routing.915fd65e00347bff`, switching titles, real-engine negative controls | Review/naming paths unchanged; allow, deny, cancel and pending-switch coverage stays independently recorded |
| Ordinary recovery | `ordinary-recovery.pre9innp` and native continuation | Protected state/history preserved; endless reconnect without TOFA wording is an accepted limitation, not a passing guidance observation |
| Runtime and native previews | `runtime-preview.5f5c33f6763b5750` | Actual loader, owned synthetic artifacts and both human-opened previews already observed; packaging alone does not require a repeat |

Reuse is conditional on no later material change to the behaviour. Native app or
engine updates require affected compatibility tests first, not blanket manual
requalification. Catalog/model/plugin-cache identities remain diagnostic;
selected roles must still be available and satisfy the contract. Credentials,
authorization, routing, permissions, personal settings, history and ownership
remain gates. Unknown old preservation differences remain unknown; they are not
excused as cache changes or attributed to files without evidence.

Ordinary Desktop can reconnect indefinitely to inactive routed work. Retain the
accepted workaround: stop the turn, quit Desktop, launch through TOFA and reopen
the same conversation. Do not change models to migrate providers. No new manual
run is required just to repeat this known limitation.

## Remaining checks, in execution order

These are planned checks, not results. No live run is authorized by this document.

| Work / owner | Smallest remaining scope | Completion evidence |
| --- | --- | --- |
| Freeze and canonical build / #106 Mac coordinator | Approve version/source; use existing tag workflow to build once, test and publish the same checked bundle; no local replacement builds | Source/runner SHA, CI run, release metadata, manifest and downloaded asset digests |
| macOS ARM64 CLI lifecycle / #106 Mac coordinator | Published-asset install/repeat/fresh-shell discovery, first-use onboarding, two-turn coding/tool output and Guardian allow/deny; preserve-uninstall/reinstall and saved-login reuse; owned-state cleanup | Exact binary/installer hashes, native versions, Keychain backend, stage results and preservation/cleanup verdict |
| Windows 11 ARM64 CLI lifecycle / #105 Windows owner | Same published candidate through native installer, saved-login, coding/tool/Guardian and recovery stages; verify helper completion and Windows Desktop refusal | Native OS/executable architecture, hashes and runner revision; actual ARM64 results, not hosted amd64 substitutes |
| Current Desktop compatibility / #106 Mac coordinator | Reuse recorded real-engine/admission results if unchanged; run affected opt-ins if installed app/engine or relevant source changed; check installed release path/identity via non-launch checks | Explicit impact/reuse assessment; any failed essential contract blocks its affected path |
| Actual Desktop observation / conditional | Only a specifically affected or unproven visible behaviour that automation cannot establish | Scoped guide with at least ten minutes, explicit finish/cancel and no automatic retry; otherwise no new manual Desktop case |
| Combined verdict / #106 | Match both platform manifests/version/source; account for failures and Desktop reuse/limitations | Qualified, blocked or incomplete with exact scope; stable promotion remains a separate decision |

The two platform lifecycle runs use the existing runners and #23's contract,
including their bounded coding and approval checks before and after reinstall.
Record explicit Main/Guardian choices and current availability during preparation;
no model is a permanent integration gate and no automatic substitution is allowed.
Do not copy an old model identity into a run without checking its current contract.
Retain runner deadlines, resource caps, request counts and failures; no automatic
retries. A human setup/observation step must retain at least ten minutes including
setup. This does not silently extend individual engine/provider request deadlines.

The agent handles deterministic preparation, commands and collection. Only secrets,
OS/account consent or inaccessible UI require human action. Use owned test state;
never purge ordinary credentials or reset the persistent Windows VM. Verify guest
readiness and output collection before any Windows attempt. Any required new
credential/state mutation needs its explicit authorization at execution time.

Use `/tmp/tofa-presentation-validation/runs/release-106/` for active Mac runs and
`.qualification/134-manual/evidence/release-106/` for durable private copies.
Each attempt gets a new owned subdirectory; preserve all previous attempts.
Windows keeps guest-local owned paths and copies sanitized results/durable private
receipts back through the established workflow. Do not depend on `/tmp` surviving
reboot. Publish only sanitized evidence, never raw account/chat/credential data.

## Ticket reconciliation and next authorized step

- **#106 stays open, incomplete.** It owns this next candidate's preparation and
  Mac qualification as well as the final combined verdict; completed #104 remains
  historical, not a new blocker to reopen.
- **#105 stays open.** Its active next run awaits the new immutable handoff, not an
  automatic rc17 rerun. Keep rc16/rc17 results and comments unchanged.
- **#110 stays open pending actual Windows artifact verification.** Its fix is
  already integrated; verify the affected stream/reasoning continuation within
  #105's lifecycle, not a duplicate paid diagnostic campaign.
- **#116's same-session recovery was already confirmed.** Keep the provider
  incident diagnostic and its original failed/recovered requests; it is not a
  separate integration release gate. Recurrence requires attribution, not fallback.
- **#134–#143 remain complete.** #130/#119 model/capability work, #120 guidance
  adoption and Windows Desktop qualification are separate. No duplicate tickets.

The next release-changing step requires approval of the concrete version/source
and immutable publication through `.github/workflows/prototype.yml`. Then consume
those actual assets on both required platforms. This planning task stops before
publication, live qualification and Desktop launch. It cannot close #106 as
qualified or infer authorization to publish a stable release.

## Validation of this planning change

No product, runner or workflow behaviour changes. Existing offline publication
checks (`python3 scripts/release_test.py -v`: eight passing tests) and the workflow
contract (`go test ./scripts -count=1`: passing) were executed on November 12.
The full product race suite and platform CI at the merged baseline are retained
as historical executed evidence, not claimed as new runs of this document-only
change. No new tests mirror prose; link, source-identity and diff checks validate
the plan, followed by independent Standards and Spec reviews.
