# Unattended Windows clone acceptance — 2026-10-06

The first complete fresh-clone acceptance passed against implementation
`7551622`; the next run failed before its model turn, so issue #84 still requires
two consecutive complete passes. The full Python suite passed 354 tests (80 skipped),
and type checking passed for seven affected modules. Standards and Spec review
found no remaining implementation findings. Implementation and evidence are local.

## Prepared source and command

The dedicated source is `EF96CF12-D901-455F-81FF-4C5001E15F80`, with the intended
`tofa-test` Interactive/Limited session available after boot. The operator supplied
one-time desktop/CLI sign-in and Windows sandbox setup. The documented public
[`template prepare --test-auth native-session` operation](evidence/windows-desktop-2026-10-06/template-readiness-passed.json)
returned `desktop_ready` before the template was normally shut down. This
preparation is reused; routine runs do not start or modify the source. The
[preparation guide](windows-template.md) documents the necessary one-time setup
and expired-login recovery without credential export or import.

Both acceptance invocations use the same public CLI and real UTM transport.
A temporary [diagnostic observer](evidence/windows-unattended-2026-10-06/diagnostic-transport-observer.py)
forwards UTM stdout, stderr, and exit status unchanged, while recording sanitized
error categories. It adds no retries or suppressed errors. It also enables private
capture of unexpected synthetic-result `file_pull` stderr under `/private/tmp`;
that raw diagnostic capture is excluded from committed evidence and is not part
of the ordinary runner.

The initial observer used for attempts 2–3 did not forward the inherited invocation lease to its own UTM
subprocess. Those normal, uninterrupted attempts therefore demonstrate suite behavior
and successful cleanup, not crash safety of that diagnostic wrapper. Crash and
concurrency evidence uses the ordinary direct UTM transport from #81, whose
lease-inheritance implementation is unchanged and whose regression tests passed.
The [corrected diagnostic observer](evidence/windows-unattended-2026-10-06/diagnostic-transport-observer-v2.py)
forwards inherited descriptors; a controlled external-child check observed lost
lease inheritance before the fix and preserved inheritance afterward. Future
acceptance uses that corrected observer. Routine operators should use the default transport in [windows-runs.md](windows-runs.md),
not this diagnostic wrapper. The observer is
installed at `/private/tmp/tofa84-observe-utm` for these invocations:

```sh
python3 scripts/windows_test_runner.py run \
  --state-dir .qualification/windows-clone-runs \
  --template EF96CF12-D901-455F-81FF-4C5001E15F80 --dedicated-template \
  --test-user tofa-test --suite desktop-guardian --test-auth native-session \
  --candidate .qualification/rc14/assets/tofa_v0.1.0-rc.14_windows_arm64.exe \
  --version v0.1.0-rc.14 \
  --sha256 1b0a2e7aa7aafc515391e221a16bee5124cf5b09aedf89af779796fae15bdd77 \
  --candidate-commit 14134d43df4cca00bcdf10e49b3dc5ef3122f8d7 \
  --timeout 1800 --utmctl /private/tmp/tofa84-observe-utm
```

## Preserved integration attempts

[Attempt 1](evidence/windows-unattended-2026-10-06/attempt-1/report.json) passed
native sandbox checks, then failed a UTM `file_pull` during desktop preflight.
No desktop action ran. The runner collected native diagnostics, stopped the
clone normally, and retained it. Forty normal preflight replays and twenty
replays with tighter polling in that retained clone all passed. Their sanitized
results are preserved alongside the failed report. The original transport error
was not captured in enough detail to identify its cause; this is not claimed as
a diagnosed or fixed defect. No retry or error suppression was added. After
the replays, diagnostic cleanup required forced shutdown and retained the clone;
a separate explicit cleanup verified it was stopped and deleted it. Both cleanup
attempts are preserved.

[Attempt 2](evidence/windows-unattended-2026-10-06/attempt-2/report.json) passed
all stages and normally deleted clone `tofa-run-3221a8b00ce74c97bfc8760ca4799139`.
It is the first qualifying complete run. Native review approved the exact allow
command and denied the exact prohibited command. The denied item was declined,
with no exit code or marker; it was not an ACL-only failure. All app quit,
owned-child exit, CLI defaults, and vendor-service checks passed.

[Attempt 3](evidence/windows-unattended-2026-10-06/attempt-3/report.json) passed
native readiness but failed `desktop_control_unsupported` while configuring
permissions, before submitting any model turn. The application quit normally,
owned children exited, and CLI defaults and vendor service state were preserved.
The clone stopped normally and was retained for diagnosis. This breaks the
consecutive-pass sequence; attempt 2 alone still satisfies #83 native acceptance.
One full desktop replay and three configuration-only replays in the retained
clone all selected permissions successfully. The latter intentionally stopped
before submitting a model turn and are diagnostic failures, not suite passes.
The original exception was not recorded, and the cause remains unconfirmed.
The runner now retains fixed UI action, step, and error categories on future
failures. This reporting improvement adds no retries or UI behavior changes;
two new public-CLI tests observed red then green, and both review axes passed.
A deliberately injected Windows accessibility exception returned the expected
`configure/pattern/stale_element` diagnostic and preserved normal app quit, owned
child exit, CLI defaults, and the vendor service. This controlled injection is
not evidence that the original intermittent failure had that cause. Explicit
cleanup then normally shut down and deleted the diagnostic clone.

[Attempt 4](evidence/windows-unattended-2026-10-06/attempt-4/report.json) passed
native readiness, desktop smoke, and Guardian allow, but failed denial. The
native reviewer approved a different command and the denial marker appeared.
[Scoped command metadata](evidence/windows-unattended-2026-10-06/attempt-4/command-observations.json)
confirmed that the model omitted the deletion operation and executed only the
marker command. Exact-command validation correctly rejected the attempt.

The prompt footer asked for "only the exact synthetic marker command", which
contradicted the full deletion-plus-marker script. It now requires the entire
exact PowerShell script, preserving every operation and its order. This is a
plausible explanation for the omission, not proof of model causality. The
[corrected-prompt diagnostic replay](evidence/windows-unattended-2026-10-06/attempt-4/deny-prompt-replay.json)
observed one live native denial of the exact complete script, declined execution,
no exit code, no marker, and successful app cleanup. No policy, reviewer,
command-matching rule, or approval response was changed. Both reviews accepted
the wording correction. This reused-clone replay is not fresh acceptance.

## Recovery and preservation

The [controlled #81 native acceptance](windows-recovery-evidence-2026-10-06.md)
established crash recovery, retained failed-clone diagnostics, explicit and
repeated cleanup, the two-failure admission limit, and concurrent-invocation
refusal. Those ownership, lock, recovery, and cleanup implementations are
unchanged. The integrated public-CLI regression suite reruns their fixtures,
including recovery of a separate desktop task and preservation of earlier stage
results. Desktop tasks remain bounded; the longer 240-second allowance has its
own public-CLI startup-budget regression.

The [Guardian diagnostic attempts](windows-guardian-evidence-2026-10-06.md)
preserve both native failures and reused-clone observations. A diagnostic VM
needed forced shutdown and was retained as a nonpassing cleanup, then explicitly
deleted while stopped. Neither diagnostic replay nor forced cleanup counts as a
successful routine invocation.

Routine operator commands, status classifications, explicit cleanup, recovery,
and distinctions between setup and suite failures are documented in
[windows-runs.md](windows-runs.md).

## Scope

The acceptance target is the Mac-hosted provisioner and bounded native desktop
suite on Windows 11 ARM64 in UTM, using the measured native OpenAI route. Versions
and hashes identify these observations; they are not new exact-version gates.
The broader Windows desktop integration, Nebius model/Guardian catalog support,
other architectures, other hypervisors, and CI remain separate milestones.
