# Fresh Windows ARM64 clone acceptance — 2026-10-06

Issue #80's public CLI completed a real unattended native-smoke run from the
prepared stopped template `EF96CF12-D901-455F-81FF-4C5001E15F80`.
The operator shut down the template before acceptance; the routine invocation
did not change it, supply credentials, request consent, or require manual sign-in.

The [successful report](evidence/windows-runs-2026-10-06/04-native-pass.json)
records run `tofa-run-56e432507b104e749cedf9a1a10f0e4e` and fresh clone
`6EF997C5-6E57-43F6-AB40-1E8A1417DD94`. Its unique inventory identity was bound
to durable ownership before boot. The run used `--timeout 1800` and the selected
suite `native-smoke`.

## Measured result

- Candidate: `v0.1.0-rc.14`, supplied source commit
  `14134d43df4cca00bcdf10e49b3dc5ef3122f8d7`, measured ARM64 PE architecture,
  SHA-256 `1b0a2e7aa7aafc515391e221a16bee5124cf5b09aedf89af779796fae15bdd77`,
  and matching `tofa --version`. Candidate bytes were compressed for transfer,
  expanded in protected staging, then checked and executed as the limited user.
- Guest: Windows 11 ARM64 `10.0.26200`, native Python `3.13.15`, intended test
  user in session 1 with a Limited token.
- Installed client: Codex `26.930.6422.0`, engine `0.160.0`; actual user-local
  executable SHA-256 matched its selected installed package.
- Native readiness: read-only harness, user-owned and ACL-manageable workspace,
  successful sandbox write/read, and denied outside write with exit 1,
  `GetContentWriterUnauthorizedAccessError`, and no outside marker.
- Full access stayed disabled. The engine exited, markers were removed, the
  scheduled task completed with result 0 in Ready state, and it was unregistered.
- Results were saved before normal clone shutdown and verified deletion. The
  CLI returned zero only after successful cleanup and the final durable report.

The [final inventory assertions](evidence/windows-runs-2026-10-06/final-state.json)
confirm that the template remained stopped, the everyday VM remained started,
the successful clone was absent, and the earlier failed native clone remained
stopped for diagnosis. These are lifecycle observations, not claims that all
unrelated disk contents were inspected.

This proves one real fresh-clone native-smoke path. It does not establish the
parent ticket's later two-run desktop/Guardian qualification.

## Preserved failures and corrections

1. [UUID case failure](evidence/windows-runs-2026-10-06/01-uuid-case-failure.json):
   UTM lookup rejected normalized lowercase UUID spelling. The runner now preserves
   the inventory's exact spelling while comparing UUID identity case-insensitively.
   No clone was created in that attempt.
2. [Empty clone response](evidence/windows-runs-2026-10-06/02-empty-clone-response.json):
   UTM created the clone but printed no UUID. The runner stopped without booting
   or deleting an unverified target. The implementation now explicitly supports
   an empty response only when the returned inventory has exactly one new UUID
   with the unique requested name. Other ambiguous responses remain errors and
   leave the mutation lock in place.
   This early development clone was [reconciled from observed inventories](evidence/windows-runs-2026-10-06/02-ownership-reconciliation.json)
   and [explicitly cleaned up through the public CLI](evidence/windows-runs-2026-10-06/02-explicit-cleanup.json).
   Its original failed report was not rewritten. That manual reconciliation was
   separate from the later successful unattended invocation.
3. [Native timeout](evidence/windows-runs-2026-10-06/03-native-timeout.json):
   the clone reached the intended user session but timed out during staging/native
   measurement. It was shut down and retained. The original evidence does not
   identify the exact transport operation, so it does not prove that transfer size
   was the sole cause. Subsequent reports record the failing operation category.
   Candidate transfer was reduced from 11,508,224 to 6,378,413 bytes by gzip, and
   the successful fresh run used an explicit larger finite deadline.

The retained timeout clone belongs to
`tofa-run-021aba73795846689600b844b99dbbd1`. Its optional explicit cleanup is:

```sh
python3 scripts/windows_test_runner.py cleanup \
  --state-dir .qualification/windows-clone-runs \
  --run tofa-run-021aba73795846689600b844b99dbbd1
```

## Verification and review

Public CLI regressions were written before each new behavior or correction,
including the native-discovered UUID and empty-response contracts. Controlled
fixtures exercise actual external resource effects and reports, including
misleading host success, stale/malformed envelopes, candidate integrity, retained
failure limits, unsafe cleanup, deletion failure, concurrency, and interruption.

Standards review found that empty inventory output could falsely confirm deletion.
A failing regression reproduced it. Inventory now requires a valid header, and
shared disposal requires the source's continued presence and the clone's absence.
The reviewer confirmed the fix; both Standards and Spec reviews had no remaining
implementation findings, including the later compressed-staging change.

Go vet and host/guest Python typechecking passed. The full Go race suite ran and
failed in existing macOS desktop tests because their process guard matched the
host app despite the tests' isolated profiles. The fixture-model metadata line
was a nonfatal catalog warning, not a separate cause; see the follow-up below.
No Go product or
test files changed, and the host app was not terminated. The scripts package
passed. Full Python and final targeted results are recorded in
[validation.json](evidence/windows-runs-2026-10-06/validation.json).

## Follow-up diagnosis

Two representative original Go failures reproduced twice in about three seconds:
`TestDesktopShellReloadPreservesAdapterCredential` and
`TestDesktopBridgePartialInstallationCleansUp`. `refuseDesktopProcesses` in
`internal/tofa/desktop_profile_darwin.go` scans all host command lines for app
executables named `ChatGPT` or `Codex`. A matching process without an explicit
different `--user-data-dir` blocks launch even when the fixture has isolated
`HOME`, `CODEX_HOME`, and its native profile.

The matched host process was `/Applications/ChatGPT.app/Contents/MacOS/ChatGPT`,
plus its embedded Codex helpers. The filename is misleading: its bundle declares
`CFBundleIdentifier=com.openai.codex`. This is an environmental test-isolation
problem, not evidence that the launcher should discard its production ownership
guard. The running host app was left untouched.

In a disposable checkout, excluding only `/Applications/ChatGPT.app/` from the
process snapshot made five representative tests pass twice, including the
partial-installation, crash-recovery, executable-override, and competing-edit
cases. The **full Go race suite then passed** in that disposable checkout
(internal package: 285.813 seconds). Synthetic fixture processes remained visible,
including the test requiring refusal of a real synthetic incumbent. The diagnostic
copies were removed afterward; the production checkout was unchanged.
The `fixture-model` warning simply skips an ineligible catalog
entry; the selected main was `moonshotai/Kimi-K3`. Early launch refusal prevented
the expected files, copy failure, and startup markers, producing misleading
downstream assertions.

The retained Windows clone yielded more precise evidence:

- The [original guest artifacts](evidence/windows-runs-2026-10-06/diagnosis-guest-artifacts.json)
  show a complete 11,508,224-byte candidate. Transfer took **121.357 seconds**;
  the [measured hash](evidence/windows-runs-2026-10-06/diagnosis-task-history.json)
  matches the selected release exactly. Transfer corruption is ruled out.
- Durable clone ownership was recorded at 07:01:55 UTC. Staging appeared at
  07:05:48, prerequisites at 07:07:07, transfer finished at 07:09:10, and the
  Limited task started at 07:09:57. Its completion envelope appeared at 07:12:06,
  after the original 600-second run budget. It reported incomplete execution.
- The task's two-minute execution limit was present. Its last result was
  `0x41306`, which Microsoft identifies as
  [task termination](https://learn.microsoft.com/en-us/windows/win32/taskschd/task-scheduler-error-and-success-constants).
  Neither user identity output nor a native result was produced. This establishes
  timeout/termination before any measured sandbox assertion; it does not establish
  a native engine or permission failure. The status code alone cannot distinguish
  its execution limit from termination during the host's recovery shutdown.
- Task Scheduler history was disabled. There were no original step checkpoints,
  so the exact slow instruction cannot be reconstructed from retained evidence.
- A [checkpoint-instrumented replay](evidence/windows-runs-2026-10-06/diagnosis-native-replay.json)
  in fresh synthetic state on the same retained clone passed in **46.75 seconds**,
  including native write/read and outside denial. Client discovery consumed about
  14 seconds after PowerShell entry. The original failure was preserved, and the
  clone was returned to its stopped retained state.

During diagnostic cleanup, UTM's normal shutdown request did not stop the clone
within 90 seconds. A direct guest `shutdown.exe /s /t 0` then completed without
forced power-off. The [final state record](evidence/windows-runs-2026-10-06/diagnosis-final-state.json)
records this separately from the original run's successful retention shutdown.

The supported explanation is cumulative provisioning/transport delay exhausting
the original bounded wait, with no completed native verdict. The later successful
run changed both transfer compression and the total deadline, so it cannot by
itself establish which change resolved that earlier timing failure.
