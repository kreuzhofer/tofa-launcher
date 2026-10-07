# Windows desktop discovery and ownership experiment — 2026-10-07

Issue [#85](https://github.com/kreuzhofer/tofa-launcher/issues/85), under
[#77](https://github.com/kreuzhofer/tofa-launcher/issues/77).

**Production ownership remains blocked.** Discovery, a process snapshot, and a
separate Electron profile do not authorize adoption of the ordinary desktop or
its IPC endpoint. Closing this experiment cannot satisfy the missing production
ownership contract. Windows desktop support stays disabled; native OpenAI and
fixture results do not qualify Token Factory support.

## Runnable experiment

The existing disposable runner now accepts `desktop-ownership`. It first runs
native sandbox readiness and the existing bounded desktop bridge smoke. It then
launches an ordinary native instance, observes the actual profile and pipe,
executes two concurrent refusal guards, tries the native same-profile singleton,
and tries a separate Electron profile with the bounded bridge. Only the owned
clone's dedicated account, synthetic workspace and synthetic conversation are
used. No account setup, credential copying, private service identity injection,
or vendor-service termination is performed.

```sh
python3 scripts/windows_test_runner.py run \
  --state-dir .qualification/windows-clone-runs \
  --template EF96CF12-D901-455F-81FF-4C5001E15F80 --dedicated-template \
  --test-user tofa-test --suite desktop-ownership --test-auth native-session \
  --candidate .qualification/rc14/assets/tofa_v0.1.0-rc.14_windows_arm64.exe \
  --version v0.1.0-rc.14 \
  --sha256 1b0a2e7aa7aafc515391e221a16bee5124cf5b09aedf89af779796fae15bdd77 \
  --candidate-commit 14134d43df4cca00bcdf10e49b3dc5ef3122f8d7 \
  --timeout 1800
```

The same existing private state directory preserves runner serialization and
retained-clone limits. Work is bounded by the runner's 420-second desktop stage
and 240-second guest task; individual launches, queries and quits have shorter
bounds. The immutable rc.14 candidate is measured by the runner but is not a
Windows desktop implementation. These Python/PowerShell sources are the runnable
prototype; production Go launcher and installer behavior are unchanged.

The executable discovery/refusal contract can also replay an inventory snapshot:

```sh
python3 scripts/windows_ownership_contract.py --inventory inventory.json
python3 scripts/windows_ownership_test.py -v
```

Its input is the OS-boundary snapshot emitted by
[`windows_ownership_inspect.ps1`](../../scripts/windows_ownership_inspect.ps1).
Exit 40 means invalid/ambiguous discovery, 41 means incumbent refusal, and 42
means matching discovery with **ownership still unproven**. Every result has
`may_launch: false`. This executable never starts or terminates a target client;
its snapshot is deliberately not a lease. The concurrent guard trial proves
refusal, not atomic acquisition against a racing ordinary launch.

## Measured identities and ordinary state

The first fresh clone selected the interactive test user's single healthy
`OpenAI.Codex_26.930.7945.0_arm64__2p2nqsd0c76g0` registration. The manifest selects
`app\ChatGPT.exe`, SHA-256
`5474239dcfa9d1548d8bcd9219b8fd3474f1157f923555e9738f789dd4a81abe`.
The relocated ARM64 engine is
`C:\Users\tofa-test\AppData\Local\OpenAI\Codex\bin\2c64dcfa86419e1c\codex.exe`,
SHA-256 `ce29231882a4b6c2cb5381f3ee311d29735fd63f45c432e2e704e12b0d31e78e`,
matching the registered package's bundled engine. These identities identify
observations, not an exact-version production allowlist.

The independently resolved PATH command is
`C:\Users\tofa-test\AppData\Local\Programs\OpenAI\Codex\bin\codex.exe`.
It is not substituted for the matching relocated package engine. Multiple
registrations, unhealthy/incomplete updates, duplicate matching engines, wrong
PE architecture, standalone CLI identity, hash mismatch, unsafe paths and
incomplete process inventory have executable-boundary refusal tests. Those
negative package/update cases are fixtures; no installed package was corrupted
or another user's registration modified to manufacture a native failure.

Chromium child argv observed the ordinary desktop's actual user-data directory:
`C:\Users\tofa-test\AppData\Roaming\Codex\web\Codex`. This is stronger than
checking which candidate directories happen to exist. For freshly created threads
in the owned synthetic workspace only, the bridge recorded the native returned
rollout path under `C:\Users\tofa-test\.codex\sessions\2026\10\07`. One allocated
path had no file; the submitted synthetic conversation's file existed after
shutdown. No history contents, ordinary conversation IDs, or credentials were
read. Full history continuation and provider identity qualification remain #77
work.

## Preserved attempts

[Attempt 1](evidence/windows-ownership-2026-10-07/attempt-1.json) is a failed
experiment, with a completed/unregistered guest task and exit 1. Native sandbox
and desktop smoke passed, including normal quit, shared CLI config preservation,
and vendor service preservation. The ownership observations established:

- Windows argv (including empty, spaces, quotes, trailing slash, Unicode), scoped
  environment, stdin and exit 17 survived the existing native supervisor.
- A synthetic junction was rejected; differently cased access to the ordinary
  synthetic directory was accepted. This is not proof against every reparse race.
- Two concurrent guards refused the live ordinary app. Its PID/start time stayed
  unchanged. No guard adopted it, sent an activation message, or terminated it.
- A separate *native* same-profile invocation exited 0 while the incumbent stayed
  alive. Native singleton activation is not launcher ownership.
- `\\.\pipe\codex-ipc` appeared while the ordinary app ran, with server PID matching
  that app, and disappeared after normal quit. The vendor service kept the same
  PID and Running state throughout.
- The separate-profile attempt produced no owned window, causing the original
  probe to report `ownership_startup_failed`. It was not relabelled as a pass.
- The first ACL query returned Win32 87 because the probe supplied the wrong
  securable-object type. This is a probe defect, not an upstream access refusal.
  The second attempt uses `SE_KERNEL_OBJECT` with `GetSecurityInfo`.

The first clone was normally stopped by failure recovery. Its sanitized report
was saved before ownership-checked `cleanup` deleted that stopped clone. The
pre-existing retained failed clone was untouched.

Microsoft documents `GetSecurityInfo` for named-pipe security descriptors and
explains the pipe access checks in
[Named Pipe Security and Access Rights](https://learn.microsoft.com/en-us/windows/win32/ipc/named-pipe-security-and-access-rights).
The probe opens only the fixed pipe name with `READ_CONTROL`, reads owner/DACL
and server PID, and closes its handle. It sends no pipe protocol messages and
never changes an ACL.

[Attempt 2](evidence/windows-ownership-2026-10-07/attempt-2.json) completed the
bounded experiment, with a completed/unregistered guest task, exit 0, normal
ordinary quit and successful clone deletion. It measured the same package and
engine relationship. The corrected ACL query succeeded. The ordinary pipe's
server was PID 10952, matching the ordinary application; the vendor service
remained PID 4192, Running. The pipe was absent before startup and after quit.

The observed descriptor was:

```text
O:S-1-5-21-1299817968-325600504-2357610402-1005D:(A;;FA;;;SY)(A;;FA;;;BA)(A;;FA;;;S-1-5-21-1299817968-325600504-2357610402-1005)(A;;FR;;;WD)(A;;FR;;;AN)
```

It grants full access to SYSTEM, Administrators and the test user, and file-read
rights to Everyone and Anonymous. **Inference:** this DACL alone cannot establish
per-user exclusion or authenticate a launcher. No other user's native account
was opened, and cross-user duplex protocol behavior was not tested. No inference
about provider authentication follows from filesystem/pipe rights.

With `CODEX_ELECTRON_USER_DATA_PATH` pointing at a fresh owned directory, the
second process exited 0 without a new window. The ordinary profile, incumbent
PID/start time, pipe server PID and DACL remained the same. This directly fails
the proposed *separate profile provides an independent concurrent desktop*
route for this package/activation path. It does not identify whether the
profile override was ignored or an earlier singleton prevented initialization;
changing a directory is therefore not a proven isolation mechanism.

Both helper (`main: false`) and conversation (`main: true`) bridge initialization
were observed separately. The actual bridge/engine process IDs and correlated
synthetic turn are retained in the desktop report. Process-tree membership and
main initialization are useful ownership signals for that launched stdio route;
they do not authorize adopting the ordinary pipe. The final report explicitly
records `desktop_ownership: blocked`, `desktop_guardian: unverified`.

[Attempt 3](evidence/windows-ownership-2026-10-07/attempt-3-final.json) repeated
fresh-clone acceptance after both review fixes, using the fingerprinted final
prototype. It passed all 13 ownership checks, repeated the separate-profile
`exited_without_window` result, completed/unregistered the guest task and deleted
the clone. The discovery contract was enforced **before** ordinary activation.
The [final inventory](evidence/windows-ownership-2026-10-07/final-inventory.json)
confirms all three experiment clones absent, source still stopped, everyday VM
still running, and the earlier unrelated retained clone still stopped.

## Minimum implementation decision

1. Discover the intended interactive user's healthy registration and manifest;
   verify the matching relocated native engine and all relevant path components.
   Recompute the relationship after updates. Never select an all-users maximum
   version or substitute the PATH CLI based on a matching version string.
2. Refuse existing ordinary instances and competing owners before shared-state
   changes. An absence snapshot alone cannot eliminate the startup race. The
   prototype therefore never emits permission to launch.
3. Keep inference on the verified owned bridge's stdio route. The existing
   supervisor owns the process tree; the main initialize handshake distinguishes
   the conversation engine from startup helpers. A pipe's name or a process PID
   alone is not authenticated launch ownership.
4. Require a separately proved atomic profile/IPC acquisition contract before
   production changes. A different Electron directory does not establish a
   different singleton/pipe namespace, and a machine-visible pipe requires
   explicit user/owner checks. Cross-user exclusion and resistance to pipe
   precreation or a racing ordinary launch are not established here.
5. Preserve the native service, ordinary account and conversations. Do not repair
   uncertainty by copying credentials, creating private package/service identity,
   killing incumbents, migrating history or silently choosing another profile.

A feasible production route must either prove the native singleton plus owned
main-handshake/pipe-owner checks safely prevent all these races, or obtain a
supported authenticated IPC namespace from the target client. Until then,
`desktop_ownership: blocked` remains binding even if this experiment completes.


## Standards

No remaining Standards findings after recheck. Review found and resolved two
boundary defects: nested ownership metadata now has explicit object validation,
and fresh discovery must satisfy the executable contract before the bounded
native launch. The malformed-object public-runner regression covers package,
engine, incumbent, service and pipe values, including retained-clone cleanup.
No material smell-baseline findings or ADR conflicts remain.

## Spec

No remaining Spec findings after recheck. The prelaunch discovery check resolves
the identified P2: unsafe/ambiguous discovery fails before activation, incumbents
are refused, and the synthetic experiment never emits production permission.
Cross-user exclusion and atomic ownership remain explicit blockers rather than
being represented as passing qualification.

Review totals: Standards 0 remaining (2 resolved); Spec 0 remaining (1 resolved,
shared with Standards). Reviews used the staged diff against
`1d40521219ce49d8387b678fcbfee2a62d2c1ae2` in two independent agents.


## Validation and limits

Tests were added before implementation at the existing public operator CLI and
executable/engine boundaries. Red-to-green cases include missing ownership
evidence, the permanent production block, missing checks, malformed/private
metadata and an unmeasured pipe ACL. The public executable contract covers
ambiguous registrations, incomplete updates, independent CLI identity, engine
integrity/architecture/cardinality, incumbent refusal and unsafe inventory.

- `go test -race ./...` and `go vet ./...`: passed. The initial sandboxed race
  invocation failed because loopback listening was prohibited; the unrestricted
  rerun passed.
- Full Python discovery: 368 cases, 282 passed, 80 skipped, and six invocation
  errors because generic discovery cannot supply lifecycle `DIST/VERSION` or the
  terminal binary argument. All six passed through the documented script entry
  points (four rc.14 lifecycle cases, two terminal cases against a fresh build).
  Thus all 288 runnable cases passed through the appropriate entry points; the
  review regression added afterward passed separately. No assertion failures
  remained. The initial sandboxed invocation also hit loopback/cache restrictions.
- Targeted desktop fixtures: 33 passed before review; the additional review
  regression passed all five malformed-object subcases after the fix. The seven
  executable contract tests passed repeatedly through implementation.
- Scoped Pyright over the new prototype and changed bridge/probe/result/transport
  code: zero errors. Including the existing clone runner and desktop runtime
  reports 17 errors (optional-value narrowing and possibly unbound loop values);
  the same 17 reproduce from the starting commit. No claim of a clean repository
  wide Python typecheck is made.
- Native measurements are owned Windows 11 ARM64 clone evidence. Host Windows
  Job Object and installed-client skips are not passes. Of the 80 Python skips,
  21 picker cases are instead invoked by the passing Go suite.
  This experiment did not run another user's native session, adversarial pipe
  precreation, a racing unguarded ordinary startup, updates during startup,
  installer replacement or the full Token Factory desktop product matrix.

[Source fingerprints](evidence/windows-ownership-2026-10-07/source-sha256.json)
identify the hardened prototype used for the final native trial. The earlier
native report's [snapshot replay](evidence/windows-ownership-2026-10-07/discovery-replay.json)
returns 42 before launch and 41 with an ordinary incumbent; neither returns
production permission. The final VM inventory is recorded separately, so app
shutdown, clone deletion and preservation of the source/everyday VM are not
conflated with a guest success flag.

The compact [validation record](evidence/windows-ownership-2026-10-07/validation.json)
records commands, counts, corrected invocation errors, skips and review outcomes.
