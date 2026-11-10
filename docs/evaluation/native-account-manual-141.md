# Manual native-account qualification (#141)

**Current status (2026-11-10): integration qualification remains open.** The
retained clean-exit, repeat-launch and scoped launcher-crash observations remain
accepted for their recorded candidates. Ordinary recovery on November 9 worked
functionally, but settings, plugin and skill preservation remain unqualified.
The offline correction below adds skill-file evidence for future collection; it
does not qualify a new candidate or change any historical receipt.

## November 9 ordinary recovery: offline preservation diagnosis

`ordinary-recovery.a9vi4y_n` recorded five positive human observations: account,
plugins, Code Review eligibility, crash-run history and older history. The actual
app and descendant bundled engine were identified, normal departure was observed,
and the old route port refused connections before and after. Collection finished
within 600 seconds. Credential hashes and existing history-prefix bytes matched.
These functional results remain accepted; socket refusal does not establish
credential rejection by a listening server.

The November 10 offline assessment verified all 25 durable receipts against the
prior review's digest inventory and against the original temporary copy. It
recomputed these differences from the retained inventories:

- Config leaf hashes changed only for
  `mcp_servers.node_repl.env.BROWSER_USE_CODEX_APP_VERSION` and
  `mcp_servers.node_repl.env.NODE_REPL_TRUSTED_SERVICES`.
- Bundled browser, chrome, unified-computer-use and codex-app-tools cache entries
  moved from `26.1027.30824` to `26.1027.61615`; the chrome `latest` link changed.
  Curated Visualize `1.0.89` and its installation receipt appeared.
- The local skills aggregate changed. Neither snapshot retained the per-file
  skill entries. A later live tree cannot establish what changed during this run.

The config/plugin changes are consistent with a native plugin refresh. This is
an interpretation of recorded paths and hashes, **not attribution to a process**
or proof that every change was harmless. All three preservation differences
remain reported. Catalog changes remain provenance only. No generated-field,
plugin-version or skill drift exclusion has been added. Recovery used an updated
client; it does not retrospectively qualify the October 30 client binary.

The separate private diagnosis is retained in the main checkout under
`.qualification/134-manual/diagnostics/skill-evidence-141-20261110/`. Original run
receipts, previous reviews, accepted outcomes and frozen candidates are unchanged.

### Correction and compatibility

The public `desktop-qualification snapshot` command now includes additive
`skill_files` maps for `skills` (`<home>/skills`) and `agent_skills`
(`dirname(<home>)/.agents/skills`). Entries are relative paths with file hashes,
symlink metadata or the existing absent-root marker, never skill file contents.
They are the exact entries used to compute each aggregate in the same traversal;
there is no second scan that could silently disagree with that aggregate. This
is still a sequential filesystem observation, not an atomic filesystem snapshot
or evidence identifying the process responsible for a change.

Existing hashing rules, including the existing bytecode/cache handling and
symlink restrictions, remain unchanged. Plugin-packaged skills remain covered by
the plugin inventory; these maps describe the two separate skill roots only.
The collector already saves the entire snapshot in its immutable before/after
receipts. The guide now reports added, removed and modified paths from those
retained maps. Missing old inventories report `not_recorded`, never an empty
proven difference or data reconstructed from the live machine. Summaries continue
to say `qualified: false`.

The updated proof reader accepts old aggregate-only receipts and validates any
new skill detail against its recorded identity hashes. Older strict readers may
reject the additive field: use the matching reviewed collector and candidate for
new runs; do not rewrite old receipts or patch frozen binaries. Admission,
credential isolation, routing, history, lifecycle, catalog/model provenance and
the production guard retain their existing rules. No Desktop launch, manual
rerun, provider request or shared settings/skill mutation was performed here.

### Offline correction validation

The public snapshot regression first failed with missing skill evidence; the
retained-summary regression first failed with missing file-change reporting.
Both pass after the correction. Focused Go admission/snapshot/qualification tests,
all 40 Python collector/guide tests, the full `go test -race ./...` suite,
`go vet ./...`, and operator Bash syntax passed. The default full Go suite skips
installed-engine tests without their opt-in; those were checked separately below.
Initial sandbox-only loopback bind failures were resolved by running the
owned local fixtures with loopback permission. Standards and Spec reviews against
`9928136` reported zero findings on each axis.

Additional tests with the installed real bundled engine passed service switching,
protocol/admission, naming independence and the observed title-schema contract.
`TestDesktopNativeCandidateBundledEngineTurn` failed its two synthetic
`path-negative-control` assertions: the engine did not expose the synthetic URL
path token in websocket diagnostics, although the test expected disclosure.
Both header-capability subtests passed. The same failures reproduce against an
unchanged `9928136` archive with the same engine. That run remains a failed baseline/test-engine compatibility result, never
rewritten as a pass or attributed to the skill-evidence correction. The separate
follow-up below resolves its diagnostic assumption. No claim of complete installed-engine qualification
is made. Private comparison logs and the engine digest accompany the diagnosis.

### Offline WebSocket diagnostic follow-up (November 10)

The five-second failing subtest still exercised the intended error path. Owned
server probes confirmed the synthetic-token URL and WebSocket upgrade for both
handshake rejection and disconnect. Both initial and 500 ms delayed stderr reads
showed `failed to connect to Responses WebSocket stage=Unknown`, with no URL or
path token. The installed engine digest still matched the retained baseline
comparison. The failure was the test's requirement that this engine echo a URL
path token; it was not evidence of a lost request path or a leaked header token.
We have not established which upstream release changed diagnostic formatting.

The test-only correction retains URL logging as an observed property. Its new
negative control uses an owned wrapper that writes the synthetic capability to
child stderr before executing the same real engine. That establishes detector
sensitivity through the actual stderr capture without depending on an upstream
information leak. Ordinary header-token cases must still deliver the capability
to the local server without exposing it in diagnostics. Every case now verifies
the exact request path and WebSocket upgrade, waits for an actual connection-error
message, reads the final capture after process termination and redacts synthetic
tokens before outcome assertions. No sleep-based workaround remains.

The new stderr control failed before the wrapper was added. All six corrected
fault/control cases then passed. A separate mutation deliberately enabled the
leaky wrapper in the normal header case: the test rejected it with `leaked=true`.
The exact source bytes were restored afterward. Three repetitions of the full
real-engine test under `-race` passed (six fault/control cases each), and
`go vet ./internal/tofa` passed. The unrelated full suite was not repeated for
this test-only change; its earlier result belongs to `8e36267`. Diagnostic
instrumentation was removed. Results and mutation evidence are retained privately under
`.qualification/134-manual/diagnostics/ws-diagnostic-control-141-20261110/`.

Only tests and this report changed. Existing baseline failure logs and all #141
receipts remain intact. No production guards, preservation gates, credential or
routing behavior changed, and no actual Desktop launch or manual rerun occurred.
Passing these isolated engine checks does not complete the lifecycle matrix.

### Remaining qualification matrix

| Case | Retained result | Remaining work |
| --- | --- | --- |
| Clean exit | Scoped integration observation accepted for `efd74f8` (`clean-exit.124b34ac7d787f8d`); smoke punctuation remains separately recorded | Affected qualification for the next frozen candidate/client |
| Repeat launch and history readability | Scoped integration observation accepted for `efd74f8` (`repeat-launch.5fdfe556d4edba09`) | Affected qualification for the next frozen candidate/client |
| Launcher crash | Scoped observation accepted for `9928136` (`launcher-crash.cbfecaaa8a046312`); owned routes closed, Desktop survived, preservation checks passed | Reassess reuse against the next candidate/client; no automatic transfer |
| Subsequent ordinary launch | November 9 functional recovery accepted, preservation unqualified (`ordinary-recovery.a9vi4y_n`) | Review the retained config/plugin deltas; historical skill detail is irrecoverable from these receipts. A future declared run can collect new evidence, not repair this run |
| Native-client crash | Not qualified | Separate declared case |
| Bridge update/interruption | Not qualified | Separate declared case |
| Uninstall recovery | Not qualified | Separate declared case |

The new source/harness requires review and a newly frozen kit before any future
operator handoff. There is no manual rerun in this correction. Keep #141 open,
retain the integration branch and production guard. Service switching, Guardian
execution and naming coverage (#142), and runtime/native previews (#143), remain
separate gates; this evidence does not establish them.

## Maintainer scope decision: integration, not model qualification

The maintainer clarified on 2026-10-28 that #141 tests the overall integration into
ChatGPT Desktop. Catalog churn and the identity of a particular main, Guardian or
naming model are not independent qualification gates. Do not replace the full
catalog gate with a selected-model fingerprint gate. Catalog/model information is
provenance for interpreting a run, not a requirement that an external provider's
inventory remain frozen.

Judge the observed path: authorized launch, correct request-role/service routing,
credential separation, functioning main/naming paths, native account and plugin
eligibility, settings/skills/runtime/history preservation, and owned-process
lifecycle/recovery. Keep these checks and the production guard intact. Model
selection remains explicit; normal request validation and availability checks
still apply when launching or submitting work. This decision does not authorize
silent substitutions, ignored transport errors, incorrect routing, or fabricated
observations. Guardian execution and other unexercised paths remain unproven.

A model-specific delay, response-quality issue or punctuation discrepancy must be
recorded separately and attributed from evidence; it is not automatically a
Desktop preservation failure. This suite is not a model-capability benchmark.
The clean-exit response's trailing period remains in its original evidence.

The evaluator now compares integration identities with only `catalog` and
`native_catalog` omitted from the comparison. Raw identities and their hashes
remain in declarations, snapshots, checks and case records. This applies at
candidate admission, installation monitoring, linked proof validation, collector
prelaunch checks and recording. Unknown identity fields/hash categories remain
strict. Request model identities are still checked against their actual receipts
and declared routes; that is evidence integrity, not a fixed-model requirement
across runs. No selected-model fingerprint gate has been introduced.

Guidance summaries retain the original `identity_equal` and `identity_drift`
fields and add `integration_identity_equal`, `integration_identity_drift` and
`catalog_drift`. Repeat-launch predecessor checks should use the shared
`identity_comparison` result's `integration_identity_equal`; full predecessor
file digest bindings must still be checked. Protected-state and history checks
remain separate and mandatory. Summaries never grant qualification.

### Separate retained-evidence reassessment

The immutable `efd74f8` clean-exit and repeat-launch receipts were reread under
this scope. Their existing review digest bindings and source-file inventories
were verified. New reports, with those inventories and evaluator source hashes,
are stored privately outside `/tmp` at
`.qualification/134-manual/reassessments/integration-scope-141-20261028/` in the
main checkout. Neither the original receipts nor their reviews were rewritten.

| Retained case | Integration observation | Separate provenance/output observation |
| --- | --- | --- |
| `clean-exit.124b34ac7d787f8d` | Observed pass for the recorded path | Exact smoke text still differs by a trailing period |
| `repeat-launch.5fdfe556d4edba09` | Observed pass for the recorded path | Provider catalog changed; original blocking verdict retained |

Both runs have completed main and naming requests, attributed account/plugin/
review-eligibility observations, normal exit, closed owned routes, unchanged
protected state and preserved existing history bytes. Repeat-launch also has a
human history-readability observation and matching predecessor integration
identity. Model IDs remain recorded. Catalog lists were not retained, so the
exact added/removed IDs remain unknown; this does not block this assessment.
Credential hashes match, but these smoke traces do not independently establish
every credential-routing lane. Guardian execution, service switching, crash and
recovery, ordinary-launch recovery, bridge update/uninstall and native previews
remain unproven. These reports keep `qualified: false`.

The reports describe the actual `efd74f8` runs; they do not transfer Desktop
qualification to a newly built evaluator/launcher. The production guard and full
lifecycle admission remain unchanged. Historical frozen binaries, collectors,
private guides and invocation manifests are retained unchanged. Before any
future wizard is offered, freeze the reviewed new candidate and generate a new
versioned guide using the integration comparison for repeat baselines. Do not
reuse the old guide's blanket identity check or patch its pinned candidate.
No manual rerun is needed solely because the catalog changed, and no Desktop
launch or manual rerun was performed for this correction.

### Regression coverage

The public-launch catalog regression first failed with declaration identity
mismatch. Collector prelaunch and case-record regressions also failed on the
old blanket comparisons. They now allow catalog churn while retaining both
snapshots. Tests cover provider inventory changes with an explicit different
available main selection, exact native-catalog numeric provenance, linked proof
receipts across catalog changes, and rejection of engine/runtime/plugin/skill/
harness/unknown identity drift. Existing credential, role/service routing,
request-linkage, protected-state, history and lifecycle tests remain required.

Validation of implementation commit `154ac98`: `go test -race ./...` and
`go vet ./...` passed. Race-enabled public-launch/bundled-engine service switching,
protocol/admission and naming-independence checks passed against owned local
upstreams. All 104 focused Python qualification, guidance, observer, scope and
shutdown tests passed; Bash syntax passed. An extra broad Python discovery run
was interrupted because unrelated test scripts require command-line inputs; it
is not counted as a pass. Standards and Spec reviews against `efd74f8` each
reported zero findings. Durable validation logs and review summaries accompany
the separate private reassessments. No actual Desktop UI launch, provider
inference or manual rerun was performed.


## Earlier fb91537 clean-exit observation

The guided `fb91537` GLM run completed its smoke response and normal exit, but
naming failed locally with HTTP 400 and the configuration differed by the new
workspace trust entry. The following corrections produced `efd74f8`.

## Corrections after the clean-exit observation

Baseline: `fb91537` on `fix/134-plugin-inventory`. An offline replay of the retained
title request failed with `unsupported desktop title contract; request was not
sent upstream`. Changing only `title.maxLength` from 60 to 36 restored routing.
Desktop 26.1023.50603 now sends the 60-character schema. The adapter accepts that
exact additional schema only for `gpt-6-luna`, retains the earlier schema and
passes the native schema through unchanged. Unknown schemas, tool inventories
and auxiliary-role contracts remain rejected; no model/service fallback is added.
A synthetic regression through the public launch and actual bundled engine failed
in 4.55 seconds before correction and passed after it. Owned local upstreams
receive synthetic context only; no private provider replay or Desktop UI launch
is needed for that check. Native title visibility still needs a manual observation.

The configuration diagnosis used the candidate's production normalizer. Removing
only the exact current workspace's `trust_level=trusted` entry **in memory** made
the after-state hash equal the before-state hash. No user configuration was edited.
The guide had captured its baseline before instructing the human to select/trust
the fresh workspace, so ordinary setup necessarily appeared as run-time drift.

The collector now offers `prepare --defer-snapshot` followed by one `freeze`.
Preparation allocates a fresh private workspace but captures no preservation
baseline and starts no process. The human opens ordinary Desktop, selects that
exact folder, starts an empty conversation, completes any trust prompt, sends
no message, and quits. Only then does `freeze` capture the immutable baseline.
The candidate still gets ten minutes from launch. The same folder is selected
inside the candidate for a new smoke conversation. Setup is outside the measured
candidate interval; it is not represented as a successful preservation test.

Default `prepare` behavior remains unchanged for existing callers. A second
freeze, freeze after a consumed attempt, launch without a baseline, and drift
after freeze are rejected. Full protected-state equality remains required; no
trust entries are excluded, no settings are restored, and no snapshots from
failed runs are replaced. The wizard requires explicit setup completion and
stops on a failed baseline capture. `--check` also verifies that the frozen
collector supports `freeze`, rejecting older kits before interactive work.

The checked-in wizard's historical candidate pins must be replaced in the next
private frozen kit before use. Existing candidates, guides and failed evidence
remain retained. This correction does not close #141, enable production admission,
or qualify the remaining lifecycle, service-switching or runtime-preview matrix.

## Collector repair before another qualification attempt

Baseline: `cb7fdd7` on `fix/134-plugin-inventory`. The retained incomplete run
`clean-exit.1c913081dad1d33a` contained an ordinary-profile ownership refusal,
`launch_failed`, a launcher PID receipt and an empty request ledger, but neither
a finish receipt nor an after-snapshot. Its original files remain unchanged.

A disposable launcher fixture reproduced the same collector path in 0.884
seconds: finalization raised `owned_route_not_registered` before writing the
finish receipt. A refusal before route registration now finalizes without a
route-stop receipt. A start receipt without a registered endpoint still fails;
no missing-route shutdown proof is invented or accepted by admission.

The collector now retains the observed launch outcome in `launch-outcome.json`
independently of `collection.json`, whose failure entries contain fixed phase
and reason codes. Raw exceptions remain in the private, exclusively created
`collection-error.log`. Observer drain, route-stop probing and the after-snapshot
retain their own outcomes. A collection failure never creates a successful
finish receipt. A drain failure leaves the final request count unknown. The
existing finish schema and production qualification validator are unchanged.

A second red regression showed that an after-snapshot failure erased the known
launcher refusal and exit code. The repaired summary reports both launch and
collection outcomes, while unavailable preservation comparisons stay unknown.
Prelaunch drift retains the comparison snapshot and consumes the attempt; it
cannot be silently retried. Historical incomplete runs expose only available
facts: for the retained run, zero observed requests and a prelaunch refusal are
known, but the exit code and preservation outcome remain unknown.

The guide keeps the actionable profile refusal even when finalization succeeds,
retains its no-pass summary, and includes the durable evidence location. A CLI
regression verifies byte-for-byte copying of the original private receipts and
logs without displaying arbitrary private diagnostics. Normal completion,
cancellation, collector failure before process creation, observer-drain failure,
snapshot failure and missing-route failure are covered by owned fixtures.

Focused validation: all 16 collector and 17 guide tests passed. These tests
exercise actual local observer servers, disposable launcher subprocesses and
the guide CLI; none launches the installed Desktop or uses the real account.

Implementation commits: `0ca05a4` and `366201a`. Full `go test -race ./...`
passed (main package: 517.059 seconds), as did `go vet ./...`, 47 observer tests,
six build tests, Python syntax, shell syntax and whitespace checks. The final
guide correction was followed by both collector and guide tests. The evaluation
suite ran 26 tests; two cases of one test failed because the test PATH omitted
installed Node. That test passed with Node restored to the test PATH. An extra
broad Python discovery invocation was stopped and is not counted as a passing
suite; its initial build failures were reproduced as missing Go on PATH, then
all six build tests passed with the existing pinned toolchain. Failed invocation
logs remain in the durable private diagnosis directory.

Standards review: no findings. Spec review found missing top-level identity
differences; a red regression reproduced the omission and disclosure of unknown
hash keys. The correction reports fixed categories, including a generic category
for unknown metadata. Both reviews were repeated for that correction and have
no remaining findings against baseline `cb7fdd7`.

No actual Desktop lifecycle qualification follows from these automated results.
The production guard, installed settings, account credentials, skills and private
wizard candidate were not changed. Nothing was published or merged by this slice.

## Earlier candidate and guide

This is a staged actual-Desktop qualification, not a release or model-capability
claim. The first prepared case is clean launch/normal exit, using the reviewed
candidate `372255f639db639b7ebb6f0077ca127981c1e0f1`. Its full Go race suite and
`go vet` passed after the #140 lifecycle fix. Standards and Spec reviews of that
fix passed against `0262178`. Earlier #134 implementation evidence and remaining
ordinary-client limitations remain separate; this guide does not supersede them.

## Run the first case

The maintainer's private durable kit contains `candidates/372255f/tofa`, its
`source.tar`, extracted `source/scripts`, and `model-services.json`. The script
verifies the pinned binary/archive hashes and compares extracted scripts with
the archive. Runtime paths are discovered; no installed skill version is pinned.
The guide code has separate per-invocation hashes in `guide.json`, so its revision
is not falsely attributed to the frozen candidate's collector.

```bash
bash scripts/desktop_qualification_operator.sh --kit /absolute/path/to/private-kit --check
bash scripts/desktop_qualification_operator.sh --kit /absolute/path/to/private-kit
```

`--check` reads local assets and imports the collector; it does not launch Desktop,
read the provider catalog, or perform inference. Do not run the interactive
wizard unattended. The human performs every UI action:

1. Save work and quit host ChatGPT Desktop; confirm readiness. The guide captures
   fresh source/app/engine/catalog/account/settings/plugin/skill/runtime hashes
   and existing session-history bytes before launch. It does not reuse a previous
   attempt's snapshot. A second collector snapshot rejects prelaunch drift.
2. In Settings → Account, confirm the usual signed-in account. Inspect unchanged
   installed/enabled plugins and Code Review availability. Record `p`, `f`, or
   `u` for each observation; never change settings merely to obtain a pass.
3. Select the exact new workspace and Kimi-K3, submit the printed tool-free smoke
   prompt once, and record the main answer and automatic title independently.
   Do not select Default/native GPT or another main in this case; the observer
   ends requests outside the declared scope. Switching belongs to #142.
4. Quit normally with Cmd-Q, then return to Terminal. The guide observes the owned
   app and launcher exiting, finishes collection, checks preserved history, and
   retains a private durable evidence copy. Ctrl-C requests cancellation of the
   owned attempt; it never signals an unrelated/global application.

One attempt allows 600 seconds from launch including UI setup, eight requests and
4,096 output tokens per request. Main: Kimi-K3. Guardian: GLM-5.3-Flash. Naming:
Nemotron-3_5-Lightning. These are independently routed; a tool-free smoke turn
does not prove Guardian execution. The higher declared output cap addresses the
previous title attempt exhausting 1,024 tokens on reasoning, but does not promise
title success. No automatic retry or model substitution is performed.

## Evidence and review

All active attempts remain under `/tmp/tofa-presentation-validation`; macOS may
display its equivalent `/private/tmp` path. The kit, invocation logs and durable
copies live outside `/tmp`. Do not publish private requests, settings-adjacent
snapshots, history file paths, or credentials. No secret entry is requested.

The summary always records `qualified: false`, even with positive human reports.
The agent reviews Main/naming requests, process receipts, actual exit status,
expired inference/control routes, attributed observations and protected-state
comparisons. Drift is retained and reported by category, never normalized away
or repaired by restoring a shared settings snapshot. Snapshot failures stop
before handoff and expose a private diagnostic path.

History evidence hashes the original byte prefixes of existing regular files in
`sessions` and `archived_sessions`. Appends and new files are allowed; truncation,
rewrites, disappearance and symlink substitution are reported as preservation
failures. No raw history is copied into these ledgers. This proves retention of
the observed file bytes, not SQLite metadata consistency, history UI readability,
or provider-routing semantics; those require the separate lifecycle/history
checks. If collection is incomplete, missing evidence cannot become a pass.

## Historical initial lifecycle plan

The following table records the initial `372255f` preparation, not current
qualification status; use the November 10 matrix above. Each case requires its
own bounded declaration and explicit operator handoff. Only clean-exit was
executable in this wizard. No crash, bridge installation,
uninstall or automatic chained launch is authorized by running it.

| Case | Status / prerequisite |
| --- | --- |
| Clean launch and normal exit | Prepared for candidate 372255f; native result pending |
| Repeated launch | Pending successful clean-exit evidence |
| Launcher interruption/crash | Pending clean-exit; separate owned-process fault declaration |
| Native-client crash | Pending clean-exit; separate owned-process fault declaration |
| Subsequent ordinary launch | Pending recovery checks; #137 direct-engine limitation retained |
| Bridge update/interruption | Pending recovery checks; explicit update/recovery handoff |
| Uninstall/reinstall recovery | Pending bridge checks; explicit scoped install handoff |

Relevant candidate or environment changes invalidate affected earlier cases.
Keep #141 open and the integration branch/production guard in place until its
full preservation matrix is supported by evidence. #142 covers signed-in
service switching/review/titles; #143 covers runtime/native preview admission.
