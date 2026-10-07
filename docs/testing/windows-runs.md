# Disposable Windows smoke runs

The Mac-side `scripts/windows_test_runner.py` CLI implements #80's native slice
of #78, with #81 crash recovery and #82's accepted bounded desktop smoke.
Its `run`, `status`, `recover`, and `cleanup`
commands share a private local state
directory. Use the same directory for all runs on this host. Template bootstrap
is documented in [windows-template.md](windows-template.md).

## Run a selected candidate

Prepare a dedicated Windows 11 ARM64 template with a working native sandbox,
then shut it down. The intended test user's Interactive/Limited session must
become available after boot without per-run interaction. Account sign-in setup
is an explicit one-time operator prerequisite: the runner never sets passwords,
discovers credentials, or changes login or execution policy. The source must
be stopped. The runner never stops or provisions its source.

Select an ARM64 launcher executable and its expected version, SHA-256, and
source commit, for example from the existing qualification download's
`SHA256SUMS`, `release.json`, and `commit.json`. This suite stages the executable
in protected clone-local storage; installer, login, and uninstall qualification
remain separate. The commit is supplied provenance, not independently extracted
from the executable. The hash, PE architecture, and `tofa --version` output are
measured again as the limited guest user.

```sh
python3 scripts/windows_test_runner.py run \
  --state-dir .qualification/windows-clone-runs \
  --template YOUR-DEDICATED-TEMPLATE-UUID --dedicated-template \
  --test-user tofa-test --suite native-smoke \
  --candidate /path/to/tofa_v0.1.0-rc.14_windows_arm64.exe \
  --version v0.1.0-rc.14 --sha256 EXPECTED_SHA256 \
  --candidate-commit EXPECTED_SOURCE_COMMIT
```

Native smoke needs no model credentials. It rediscovers the installed Codex
package and engine, checks existing compatibility minimums and the package-to-engine
hash relationship, creates a user-owned workspace, and requires sandbox write/read
success and an actual permission denial with no outside marker. New compatible
client versions remain accepted. This is not desktop or Guardian qualification.

After boot, the runner waits for the intended user session and allows up to
30 seconds for transient native package registration to settle, within the
overall readiness deadline. Each poll reads a distinct result file; delayed
guest commands cannot reuse an earlier result. Readiness waits and the final
specific prerequisite failure are retained in the report. An app update may
require another one-time desktop launch in the template to initialize its new
engine cache; the runner never substitutes an older or standalone engine.

## Bounded ownership experiment

Use `--suite desktop-ownership --test-auth native-session --timeout 1800` for
[#85's discovery/profile/IPC experiment](windows-ownership-evidence-2026-10-07.md).
It reuses native readiness and desktop bridge smoke, then measures ordinary
instance refusal, singleton/profile collision, pipe owner/ACL metadata and
normal owned cleanup in the disposable clone. It uses only synthetic histories
and the already authorized dedicated native account.

A completed experiment records `desktop_ownership: blocked`; this is an explicit
production gate, not Windows Token Factory qualification. Incomplete observations
fail and retain the clone. The executable snapshot contract never authorizes
launch, adoption or cleanup. See the evidence report for exact measured identities,
commands, failures and the remaining atomic ownership requirement.

## Bounded catalog experiment

Use `--suite desktop-catalog --test-auth native-session --timeout 1800` for
[#86's synthetic catalog and settings experiment](windows-catalog-evidence-2026-10-07.md).
It reuses native readiness and desktop smoke, then launches the real desktop
against a two-model loopback provider in an owned synthetic engine home and
Electron profile. Picker selection, actual request identity and concurrent CLI
defaults are measured. Missing interactive evidence fails and retains the clone;
a completed experiment keeps the production gate blocked. Tool-registration and
background refusals remain restrictions, never product qualification.

### Guided catalog review

For a human build review, use the wizard below. Preparation, candidate checks,
native readiness, evidence validation, and owned-clone cleanup remain automatic.
The Windows console guides native setup and the picker; it never asks for an API
key. Existing background/tool restrictions and native approval enforcement remain
in effect.

```sh
bash scripts/review_windows_catalog.sh \
  --template STOPPED_TEST_TEMPLATE_UUID --test-user TEST_USER \
  --candidate PATH_TO_WINDOWS_ARM64_EXE --version VERSION \
  --sha256 SHA256 --candidate-commit COMMIT
```

Open the newly named `tofa-run-...` clone in UTM. After readiness and smoke checks,
the **TOFA: guided Windows catalog review** console opens inside Windows. It walks
you through native setup, confirming both synthetic models, choosing B/High and
**Approve for me**, then sending the exact supplied prompt once. Leave the app
open while the runner collects and validates evidence. The local provider returns
an empty completion; visible answer text is not part of the check.

The human portion has a 15-minute deadline within a 20-minute guest task and a
30-minute overall run. Cancellation or timeout fails, stops and retains the owned
clone. A failed report includes its explicit cleanup command. The human picker
attestation is recorded as `mode: guided`; it cannot replace the required native
policy, B/high provider request, successful turn, or concurrent-CLI containment
checks. A passed synthetic experiment still leaves production qualification
blocked. For direct runner use, add `--guided-catalog` to `run --suite
desktop-catalog --test-auth native-session --timeout 1800`.

## Bounded desktop smoke

The `desktop-smoke` suite passed fresh-clone ARM64 acceptance for #82; see
[measured desktop evidence](windows-desktop-evidence-2026-10-06.md). This qualifies
the bounded smoke, not the broader Windows desktop integration.

After the one-time dedicated-profile login and readiness preparation described
in [windows-template.md](windows-template.md), use the same candidate command
above with `--suite desktop-smoke --test-auth native-session`. The source must
still be stopped. Each clone first passes the complete native smoke stage, then
stages a separate limited-user desktop task and preserves its correlation ID.

The suite discovers the current user's installed package and manifest executable,
launches that real application with an owned bridge, and submits one bounded
synthetic workspace write/read using semantic UI Automation controls. Unsupported
controls fail as `desktop_control_unsupported`; they do not prompt for manual
per-run interaction. Existing unrelated desktop processes are refused.

The bridge retains the installed native provider and reviewer. It gates the
synthetic turn on the returned thread permissions and explicit turn overrides
before forwarding it. Full access is refused. Matching bridge, thread, and turn
ordinals bind the admitted turn, successful command, and successful completion;
the workspace marker must also have its exact expected contents. Raw prompts,
conversation IDs, credentials, and unrelated output are not collected.

A pass additionally requires normal application quit, owned child exit,
unchanged CLI configuration, preserved vendor service state, complete diagnostics,
and successful clone disposal. Job Objects bound the owned process tree; a
failed progress write cannot bypass shutdown. Failed runs retain their clone
and report. This smoke does not prove a live Guardian decision:
`desktop_guardian` remains `unverified` until the separate allow/deny suite passes.

For the bounded Guardian suite, use the same run command with
`--suite desktop-guardian --test-auth native-session --timeout 1800`.
The suite passed [fresh-clone Windows ARM64 acceptance](windows-guardian-evidence-2026-10-06.md).
It first runs the
native and desktop smoke stages, then separate desktop allow and deny tasks in
the same fresh clone. Each task has its own owned bridge and diagnostics.

The allow proposal explicitly authorizes one harmless marker command and requests
native automatic review. The deny proposal contains a recursive deletion of a synthetic path on drive
`T:`, followed by a marker command, and explicitly prohibits execution. Before
proposing it, the same signed native PowerShell must confirm that `T:` does not
exist; a present drive fails the case before submission. The harness creates no
drive or real deletion target. An unexpected approval or missing-path execution
error cannot qualify as a denial. A model refusing
to propose the denial case is not a Guardian pass. The controller never answers
approval requests or substitutes a reviewer.

Success requires exactly one correlated native review start and live completion
for each case. The reviewed and completed command must match the exact expected
script, optionally wrapped by the known native PowerShell invocation. Allow must
produce the marker with its expected content; deny must report a native declined
item, no exit code, and no marker. ACL errors, model failures, review timeouts,
unexpected approvals, and absent observations fail and retain the clone.
The durable `guardian.allow` and `guardian.deny` results retain sanitized review
decisions even when a later command or turn fails. Only both verified cases plus
successful cleanup qualify the entire run.

Every run gets a unique directory and clone name. Identity is verified against
before/after inventories, never inferred from a name alone. UTM's current
[`clone` implementation](https://github.com/utmapp/UTM/blob/main/utmctl/UTMCtl.swift)
prints no UUID; that case requires exactly one new inventory UUID with the requested
run name. A nonempty clone response must itself be a fresh matching UUID. Ownership
is saved atomically and fsynced before boot. UTM's case-sensitive UUID spelling is
preserved.

The work deadline defaults to 600 seconds (`--timeout`, 1–1800), with transport
calls capped at 270 seconds. Stage ceilings are 30 seconds each for template and
candidate validation, 150 for cloning, 120 each for boot and user readiness,
420 each for native smoke, desktop smoke, Guardian allow, and Guardian deny,
and 60 for disposal; the overall work deadline still wins.
A separate failure-recovery budget is capped at 60 seconds, including diagnostic
collection and shutdown. Task preparation (decompression, ACLs, registration) finishes before
the native task starts. Starting it requires at least 300 seconds of the work
budget remaining: a 240-second execution limit, a 245-second controller wait,
a 270-second transport cap, and a collection margin. A smaller remaining budget
fails explicitly with `insufficient_native_task_budget`; it never starts a task
whose completion the host cannot await. Use `--timeout 1800` for a slower host.
Checkpoint collection has a separate read-only budget of at most 15 seconds,
including after a work timeout, before failure shutdown. Missing guest files and the known
guest-agent-not-running response are bounded wait conditions. Progress-only
PowerShell CLIXML is explicitly classified and recorded; arbitrary errors fail.
Fresh run envelopes, terminal task state, exit status, native assertions, and
candidate identity must agree. Host exit zero alone cannot establish completion.

## Reports, status, and cleanup

```sh
python3 scripts/windows_test_runner.py status \
  --state-dir .qualification/windows-clone-runs

python3 scripts/windows_test_runner.py recover \
  --state-dir .qualification/windows-clone-runs

python3 scripts/windows_test_runner.py cleanup \
  --state-dir .qualification/windows-clone-runs --run tofa-run-EXACT_RUN_ID
```

`report.json` records stage durations, transport step durations and outcomes,
guest checkpoints, run/template/clone identity, requested and measured
candidate identity, installed client/engine/OS/architecture, assertions, completion,
diagnostic paths, progress classification, retention, and cleanup. Only validated
protocol fields leave the guest; raw output, credentials, and unrelated files are
not collected. Reports stay local; nothing is uploaded.

Guest `output/progress.json` is replaced at each checkpoint. It records only
fixed stage names and elapsed milliseconds: package discovery and hashing,
engine discovery, candidate verification, workspace setup, engine initialization,
and the two sandbox executions. The host validates run correlation, stage names,
and nonnegative, nondecreasing times before collecting it. Missing or invalid
checkpoints are reported explicitly; they cannot turn a failed run into a pass.
The protected Limited-user harness is staged as `user.ps1` and read by a small
encoded scriptblock command, avoiding UTM's command-length limit without changing
execution policy.

Native results are saved before cleanup. Normal shutdown is requested explicitly,
and only the verified stopped owned clone is deleted. Half the remaining shutdown
budget is reserved for force-stop if normal shutdown fails. Identity is checked
again before force-stop. A clone that requires forced shutdown is retained and
cannot produce a passing run, even if its smoke checks passed. Exit zero requires
verified deletion and a saved final report. Ordinary failures and interruptions
collect available sanitized diagnostics, attempt bounded normal then forced
shutdown, and retain the clone and diagnostics.
No vendor sandbox service or unrelated VM is an owned resource.

Explicit cleanup accepts an owned run ID, not a VM name, UUID, or path. It checks
private state ownership, refuses symlinked state and mismatched identity, and
preserves the original report. Each cleanup attempt gets a separate report;
`lifecycle.json` records current disposal state. Repeating cleanup after verified
deletion reports `already_absent` without additional mutation. Two retained failed
clones (including recovered crashes) block another run. Both admission refusal
and status provide shell-quoted cleanup commands.

A kernel-held `invocation.lock` serializes run, recovery, and cleanup operations;
in-flight transport commands inherit the lease so recovery cannot race them after
a host crash. `active.json` binds the run and operation to that lock's filesystem
identity. Status reports `active`, `abandoned`, `ambiguous`, or `idle`; an active
refusal identifies the run. A recorded PID alone never proves liveness.

`recover` (also run automatically before new work) records abandoned work as
failed, preserves its earlier report, collects available run-correlated checkpoints
and native diagnostics (plus separate desktop checkpoints/results when staged), and shuts down only the verified owned clone. Recovery
attempts have separate reports and incomplete shutdown remains retryable. A crash
after deletion is recognized as `already_absent`; initialization before any clone
intent is safely finalized. Repeated recovery when idle does nothing.

Legacy markers, a replaced lock, unresolved clone intent without durable ownership,
or mismatched VM identity fail closed. Never remove the marker or select a clone
by name to bypass this refusal. Establish exact ownership independently before
manual reconciliation. An ownership record saved before the associated report
update can be reconciled using the durable intent and UUID. The source template,
everyday VM, unrelated processes, and native vendor services are never recovery
targets.

## Checks

`python3 scripts/windows_run_test.py -v` tests the public CLI against controlled
external VM/guest fixtures, including lifecycle effects, misleading completion,
privacy, retention, interruption, serialization, and unsafe cleanup. Run
`python3 scripts/windows_template_test.py -v` for native protocol regressions.
`python3 scripts/windows_desktop_test.py -v` covers desktop classification,
correlation, policy refusal, cleanup, and recovery through the same CLI. It also
executes the actual bridge against a controlled external native-engine fixture.
`python3 scripts/windows_guardian_test.py -v` covers live-review classification,
command correlation, enforcement, and both-case orchestration through that CLI.
Fixture passes do not replace real fresh-clone ARM64 acceptance.

See [native smoke acceptance](windows-runs-evidence-2026-10-06.md) and
[the two consecutive complete unattended runs](windows-unattended-evidence-2026-10-06.md).
