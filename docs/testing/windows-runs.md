# Disposable Windows native smoke runs

The Mac-side `scripts/windows_test_runner.py` CLI implements #80's native slice
of #78, with #81 crash recovery. Its `run`, `status`, `recover`, and `cleanup`
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

Every run gets a unique directory and clone name. Identity is verified against
before/after inventories, never inferred from a name alone. UTM's current
[`clone` implementation](https://github.com/utmapp/UTM/blob/main/utmctl/UTMCtl.swift)
prints no UUID; that case requires exactly one new inventory UUID with the requested
run name. A nonempty clone response must itself be a fresh matching UUID. Ownership
is saved atomically and fsynced before boot. UTM's case-sensitive UUID spelling is
preserved.

The work deadline defaults to 600 seconds (`--timeout`, 1–1800), with transport
calls capped at 150 seconds. Stage ceilings are 30 seconds each for template and
candidate validation, 150 for cloning, 120 each for boot and user readiness,
360 for native smoke, and 60 for disposal; the overall work deadline still wins.
A separate failure-recovery budget is capped at 60 seconds, including diagnostic
collection and shutdown. Task preparation (decompression, ACLs, registration) finishes before
the native task starts. Starting it requires at least 180 seconds of the work
budget remaining: a 120-second execution limit, a 125-second controller wait,
a 150-second transport cap, and a collection margin. A smaller remaining budget
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
and native diagnostics, and shuts down only the verified owned clone. Recovery
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
Fixture passes do not replace real fresh-clone ARM64 acceptance.

See [the real ARM64 acceptance and preserved attempts](windows-runs-evidence-2026-10-06.md).
