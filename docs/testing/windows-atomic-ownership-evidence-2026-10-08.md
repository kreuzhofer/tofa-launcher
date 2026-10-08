# Windows desktop atomic ownership prototype — 2026-10-08

Prototype for [#102](https://github.com/kreuzhofer/tofa-launcher/issues/102),
following [the experiment plan](../research/windows-desktop-atomic-ownership-2026-10-08.md).
The question is whether the launcher can establish exclusive ownership of the
ordinary Windows desktop profile, its main engine and native IPC before protected
actions, including when ordinary or competing launches race it.

## Finding

The measured Windows desktop connects to a precreated `codex-ipc` server before
launcher admission, and reconnects after that synthetic server is replaced.
The first trial attributed the connection to the exact owned app PID, intended
user and session; the helper observed 180 queued bytes on each connection without
reading or retaining message bodies. The owned bridge observed one main
initialization and zero admitted turns.

This is a **negative ownership result** for the proposed native route. Delaying
inference at the bridge or checking the pipe owner afterward cannot prevent IPC
traffic that has already happened. A launcher-only lock also cannot serialize
ordinary app starts. Production Windows availability and #87 remain blocked.

This does not establish message contents, credential exposure or exploitability.
Zero recorded bridge admissions is not a measurement of all provider requests.
No acquisition protocol or admitted route was implemented or qualified.

## Exact installed source

The native package was `OpenAI.Codex_26.930.7945.0_arm64__2p2nqsd0c76g0`.
Its application SHA-256 was
`5474239dcfa9d1548d8bcd9219b8fd3474f1157f923555e9738f789dd4a81abe`,
engine SHA-256
`ce29231882a4b6c2cb5381f3ee311d29735fd63f45c432e2e704e12b0d31e78e`,
and `app.asar` SHA-256
`12c29fce16d17383c687f820b660ee4ee7e139b6b50184ae1d13d0a733b57bd6`.

Unlike the earlier Oct 5 source investigation, these fingerprints identify the
package actually measured here. The bounded source reader exports hashes,
source names and signal counts; vendor excerpts used for local inspection are
not committed. [Source offsets and fingerprints](evidence/windows-atomic-ownership-2026-10-08/installed-source-contract.json)
allow a subsequent inspection of the same archive.

- `bootstrap-C8gUBg5L.js`, SHA-256
  `1f726d0e3103d81501551546d3b6e70f1fc10646f9326e00fe68605f144c5f4f`:
  startup sets `userData`, requests the native single-instance lock and exits 0
  on failure. The successful instance queues second-instance arguments. At
  decoded character offset 1719844 the router handles `EADDRINUSE` by closing its
  attempted server and continuing with the same endpoint.
  `IpcClient` starts at offset 1720415: its connection path sends `initialize`
  with `clientType` and schedules another `connect` from the socket close handler
  using a timer. No launcher nonce or peer identity validation appears in this
  inspected path. Whole-file token counts are search signals, not counts of
  distinct handlers; the IPC reconnect uses this direct timer.
- `application-network-startup-BEAX-hka.js`, SHA-256
  `634382c7af55d0ff57eb028aa4dd904130215c44fb559ea90a4f4035a5419f6e`:
  `Mc` selects the fixed Windows pipe at offset 273506. `Lc` returns immediately
  on Windows instead of applying the Unix socket ownership check.
- Archive package metadata declares Electron `42.3.0`. That declaration is not
  a measured runtime identity or proof of the exact Chromium/libuv implementation;
  runtime-source mapping remains an explicit limitation.

## Native attempts and preservation

Attempt 1 ran through the public disposable runner, passed native sandbox
readiness, and captured pipe precreation/replacement plus ordinary-first,
launcher-first, simultaneous and two-launcher observations. The ordered trials
observed the respective first process owning the pipe; losing invocations had no
owned window. It reached ordinary recovery and final cleanup, but exhausted the
inherited 240-second guest-task budget. The host reported `guest_task_incomplete`,
stopped and retained its clone. Final preservation checks were absent and are
not credited as passed.

- [Original failed run](evidence/windows-atomic-ownership-2026-10-08/attempt-1-run.json)
- [Recovered native observations](evidence/windows-atomic-ownership-2026-10-08/attempt-1-observations.json)
- [Exact first probe fingerprint](evidence/windows-atomic-ownership-2026-10-08/attempt-1-source.json)

The owned clone was booted only to recover its saved observations and inspect
matching vendor source, then removed through the runner's explicit cleanup.
No source or everyday VM was started or stopped. A failed bulk archive transfer
timed out after 30 seconds; bounded guest-side source excerpts succeeded instead.

The follow-up uses a 600-second guest deadline and 900-second stage deadline,
inside the existing 1800-second run limit. Review corrections distinguish clean
singleton exits from failed startup, identify two launcher contenders accurately,
preserve the original failure stage separately from cleanup, and require final
preservation checks before classifying a completed negative experiment.

**Attempt 2 completed the bounded negative experiment.** It reproduced both
180-byte connections with the same app PID (4504), creation timestamp, intended
SID and session. The pipe-precreation trial observed one owned main-engine
initialization and zero admitted bridge turns. The final independent checks were
all true: owned apps exited, CLI defaults unchanged, vendor service preserved.
An unadapted native launch with a fresh synthetic engine home produced an owned
window afterward, establishing the measured ordinary-recovery boundary.

| Startup observation | Observed winner | Losing invocation |
| --- | --- | --- |
| Ordinary ready before launcher | Ordinary, PID 6036 | Clean exit 0 |
| Launcher ready before ordinary | Launcher, PID 12088 | Clean exit 0 |
| Simultaneous ordinary/launcher spawn barrier | Launcher, PID 1492 | Ordinary exit 0 |
| Two launcher spawn barrier | First launcher, PID 11648 | Second exit 0 |

UI quit attempts returned false in all cases; no graceful app-quit claim is made.
The existing owned supervisors terminated their trees, and final discovery found
no remaining app incumbent. The guest task completed and unregistered with exit
1, and the runner reported `atomic_ownership_blocked`, stopped and retained the
clone as designed. After archiving the evidence, explicit runner cleanup removed
it. Both source/everyday VM states and the unrelated retained clone are checked
in the final inventory.

- [Complete second run](evidence/windows-atomic-ownership-2026-10-08/attempt-2-run.json)
- [Final native observations](evidence/windows-atomic-ownership-2026-10-08/attempt-2-observations.json)
- [Final experiment source fingerprints](evidence/windows-atomic-ownership-2026-10-08/attempt-2-source-sha256.json)
- [Independent final VM inventory and cleanup](evidence/windows-atomic-ownership-2026-10-08/final-inventory.json)

## Scope of the observations

The prototype uses the existing limited-user task transport, native readiness
checks, process supervisor and disposable-clone ownership records. It creates
empty synthetic engine homes and never copies ordinary credentials. A synthetic
server reserves the fixed pipe with `FILE_FLAG_FIRST_PIPE_INSTANCE` before app
spawn; no vendor pipe ACL or service/package identity is changed. A retained
client process handle supports PID/user/session attribution. Only connection
identity and queued byte counts are collected.

Ordered starts wait for an observed first window; simultaneous contenders finish
their per-launch preparation before the shared spawn barrier. These are startup
observations, not an atomic acquisition algorithm or exhaustive interleaving
proof. No launcher adopts the winning ordinary app. Cleanup is restricted to the
supervised trees; unsuccessful UI quit attempts are recorded separately from
forced owned-process cleanup.

Pipe replacement follows an **unadmitted** connection. It demonstrates native
reconnection to the synthetic endpoint, not shutdown correctness after losing an
admitted route. Cross-user/session exclusion, synthetic-history preservation,
activation argument forwarding, provider-request counts, crash/update behavior
and precise during-startup/pre-admission winner schedules remain unqualified.
Only the already designated test user was used; no second account or credentials
were created.

## Reproduce

The throwaway prototype is on `prototype/windows-atomic-ownership-102`. Run from
that branch using the designated stopped template and previously selected
candidate:

```sh
python3 scripts/windows_test_runner.py run \
  --state-dir .qualification/windows-clone-runs \
  --template EF96CF12-D901-455F-81FF-4C5001E15F80 --dedicated-template \
  --test-user tofa-test --suite desktop-atomic-ownership \
  --test-auth native-session --timeout 1800 \
  --candidate .qualification/rc14/assets/tofa_v0.1.0-rc.14_windows_arm64.exe \
  --version v0.1.0-rc.14 \
  --sha256 1b0a2e7aa7aafc515391e221a16bee5124cf5b09aedf89af779796fae15bdd77 \
  --candidate-commit 14134d43df4cca00bcdf10e49b3dc5ef3122f8d7
```

Expected exit status is nonzero: this prototype never emits production admission.
A completed negative observation reports `atomic_ownership_blocked`; an
incomplete trial or failed preservation reports `atomic_ownership_observation_failed`.
The clone is stopped and retained for evidence review. Use the explicit cleanup
command reported by the runner after saving its evidence. The existing failed-clone
limit is enforced.

The standalone source fingerprint command is:

```sh
python3 scripts/windows_atomic_ownership_prototype.py --inspect-asar /path/to/app.asar
```

## Follow-up design decisions

On 2026-10-08, the maintainer confirmed that the next launcher release proceeds
independently of Windows desktop integration. Windows desktop remains disabled
until a safe route is demonstrated and the existing qualification gates are met;
#87 remains blocked. This release-priority decision does not change the accepted
ordinary-profile/history requirements or establish an alternative launch route.

The maintainer's preferred Windows development workflow uses one persistent
Windows environment. Resetting or reinstalling it is not the default for each
development iteration. The Windows developer runs locally inside Windows and
owns native implementation, debugging and qualification. Use isolated test state
only when a specific installation, recovery or destructive lifecycle test needs
it; preserve the normal development environment. A clean installation test needs
a verified initial state, not a routine OS reinstall.

This operating decision supersedes the routine clone-per-run workflow in #78
and the corresponding environment assumptions in #77/#102. Those tickets and
their historical evidence retain their product, identity, preservation and
qualification requirements. Existing disposable-runner infrastructure remains
available for tests that actually need it.

macOS and Windows development share one launcher version. Platform work and
release coordination use tickets, with the macOS side coordinating the final
release. The existing CI pipeline remains suitable for building the shared
artifacts; coordination does not require every artifact to be built on macOS.
Each platform owner records qualification of the exact release candidate in
their ticket, and the macOS coordinator records the combined release-readiness
decision. Shared-code changes require checks on both platforms; platform-specific
work stays with its owner. Publishing an experimental candidate and declaring
product qualification remain separate steps under the existing release workflow.

The maintainer authorized removal of disposable Windows test clones and chose
to keep both `Sabre Windows 11 ARM64` and `tofa77 Windows ARM64 bridge prototype`
for now. The remaining retained `tofa-run-021aba73795846689600b844b99dbbd1` clone
was removed through the public runner cleanup command; its local reports remain.

Confirmed follow-up work is tracked in:

- [#103: Persistent Windows-local development and baseline](https://github.com/kreuzhofer/tofa-launcher/issues/103).
- [#104: Shared candidate preparation and macOS qualification](https://github.com/kreuzhofer/tofa-launcher/issues/104).
- [#105: Windows qualification of that candidate](https://github.com/kreuzhofer/tofa-launcher/issues/105), blocked by #103 and #104.
- [#106: Combined release-readiness decision](https://github.com/kreuzhofer/tofa-launcher/issues/106), blocked by #104 and #105.

The first two tickets can start independently. No new candidate version or
stable-release promotion was selected by this operating-model decision.

## Required upstream contract — draft, not sent

Can the Windows desktop expose a supported acquisition and lifetime contract for
the intended ordinary user/profile that also serializes ordinary native starts?
Before any IPC traffic, can it either authenticate the exact owned server and
user/session, or use an isolated endpoint that cannot join an unrelated router?
The contract must cover pipe precreation, bind collision, replacement/reconnect,
crash and update behavior, with observable refusal and release. Alternatively,
can native IPC be disabled for an owned stdio-main-engine launch without breaking
the desktop's supported behavior?

Until that boundary is demonstrated or product scope is deliberately changed,
#87 stays blocked even if #102 is eventually closed with these negative findings.

## Validation and review

Public runner tests were written before the implementation slices. They cover
missing native evidence, retained negative findings, incomplete observations,
preservation failure and the bounded task budget. An executable source-reader
test uses an independently constructed ASAR fixture and checks that source text
is not exported.

All 124 targeted tests passed: 5 atomic ownership, 34 desktop, 41 disposable runner,
26 template and 18 catalog tests. Syntax parsing and `git diff --check` passed.
No Go production code changed. These host regressions do not substitute for
Windows observations. [Validation record](evidence/windows-atomic-ownership-2026-10-08/validation.json).

Standards review: three evidence/correctness findings resolved; no remaining
findings on recheck. Spec review: original failure retention resolved; no remaining
code defect for the scoped negative outcome. Positive acquisition qualification
and the explicitly listed native limits remain outstanding. The two reviews
were independent agents against starting commit
`28557a88ab46f00da4a936f644f7423658d9f70f`.
