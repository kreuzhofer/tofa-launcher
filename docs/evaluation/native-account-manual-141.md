# Manual native-account qualification (#141)

**Current status (2026-10-27): do not rerun the old wizard.** The integration
branch has the #135 preflight correction and the collector repair below. The
private kit and checked-in wizard still name the older candidate; neither has
been repinned or launched for this repair. Review and freeze the new candidate
before a separately declared actual-Desktop clean-exit check. #141 remains open.

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

Focused validation: all 16 collector and 16 guide tests passed. These tests
exercise actual local observer servers, disposable launcher subprocesses and
the guide CLI; none launches the installed Desktop or uses the real account.
The full repository race suite and independent review results are recorded
separately when completed. No actual Desktop lifecycle qualification follows
from these automated results.

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
