# Manual native-account qualification (#141)

**Current status (2026-10-28): qualification remains open.** The guided
`fb91537` GLM run completed the smoke response and normal exit, collected complete
logs and closed both owned endpoints. Human account/plugin/review observations
passed; identities and existing history bytes were preserved. Naming failed
locally with HTTP 400. The protected configuration differed only by the new
workspace's trust entry. Neither outcome is converted into a qualification pass.

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

## Declared lifecycle sequence

Each case requires its own bounded declaration and explicit operator handoff.
Only clean-exit is executable in this wizard. No crash, bridge installation,
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
