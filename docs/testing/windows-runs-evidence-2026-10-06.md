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
failed in existing macOS desktop tests, primarily because the host Codex app was
already running. Other failures included fixture-model metadata missing in
desktop subprocess tests and downstream startup assertions. No Go product or
test files changed, and the host app was not terminated. The scripts package
passed. Full Python and final targeted results are recorded in
[validation.json](evidence/windows-runs-2026-10-06/validation.json).
