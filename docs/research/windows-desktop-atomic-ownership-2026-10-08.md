# Windows desktop atomic ownership — 2026-10-08

Research and test plan for [#102](https://github.com/kreuzhofer/tofa-launcher/issues/102),
following the completed negative experiment in #85. **Retained target source is
from Oct 5; it does not identify the Oct 7 measured binary's behavior.**

The next ownership experiment must distinguish **native singleton ownership,
owned engine transport, and native IPC ownership**. None implies the other two.
An additional launcher lock can serialize cooperating launchers, but cannot
exclude ordinary app starts that do not participate in it. Production ownership
remains blocked by the [#85 observations](../testing/windows-ownership-evidence-2026-10-07.md).
This note adds source research and a proposed experiment; it contains no new
native execution result.

## Evidence already established

The Oct 7 Windows package `OpenAI.Codex_26.930.7945.0_arm64__2p2nqsd0c76g0`
retained its ordinary process and pipe owner when a second invocation used a
different Electron profile. That invocation exited without an owned window.
Two concurrent guards refused an incumbent; they did not test acquisition
against an unguarded racing start. The pipe descriptor was measurable, but
cross-user duplex access and authentication were not tested.
[Native results and exact identities](../testing/windows-ownership-evidence-2026-10-07.md).

The [guided catalog proof](../testing/windows-catalog-guided-evidence-2026-10-07.md)
establishes the bounded native bridge/catalog route. It does not supply an
atomic acquisition contract for the ordinary profile or pipe. No exception to
[Guardian enforcement](../adr/0002-guardian-selection-follows-launch-route.md) or
[conversation identity/default isolation](../adr/0003-desktop-conversation-model-selection.md)
is proposed.

## Retained Windows source: useful but an older package

Reinspection used the retained `/private/tmp/tofa76` copies from Windows package
`26.930.2377.0`, not the installed macOS app. Their SHA-256 values match the
[recorded manifest](evidence/windows-desktop-2026-10-05/installed-source-hashes.json).
These are **Oct 5 source observations**, not proof of the Oct 7 binary:

- In `bootstrap-CYu4H4X5.js` (SHA-256
  `9b9d3c9e8312dba970daf31fd3950b3f2bd760a89e1d7bf480c4efefb3d2b102`),
  `Owe` resolves `CODEX_ELECTRON_USER_DATA_PATH`. Startup sets Electron `userData`
  before `requestSingleInstanceLock`; packaged Windows requests that lock and
  exits 0 when acquisition fails. Decoded UTF-8 character offsets: `Owe`
  2174023; startup `setPath` 2203717; lock call 2204123.
- In `application-network-startup-DN7Ktmlk.js` (SHA-256
  `3c2ebf430f24e55975f81e95b33e0f71470d04886f229b935939a7e32c587cf0`),
  `Mc` at 273433 selects the fixed Windows pipe `\\.\pipe\codex-ipc`.
  The filesystem ownership/mode enforcement in `Lc` returns immediately on
  Windows.
- In the same bootstrap, `IpcRouterManager` attempts a server and treats
  `EADDRINUSE` as another active router, closing the attempted server. It still
  returns the endpoint. `IpcClient` connects and sends `initialize` containing
  `clientType`; its close handler schedules reconnection. Relevant offsets are
  approximately 1718–1723 thousand. The inspected client/router path has no
  launcher nonce, Windows peer-PID check, or launcher-specific authentication.

The [original Windows contract report](windows-desktop-contract-2026-10-05.md)
identifies the package and provenance. Vendor bytes are not redistributed.
**Inference:** the older source makes pipe precreation/reconnection an essential
test. It does not establish exploitability or the behavior of the newer package.
Before native trials, collect matching package/source hashes and runtime
Electron/Node/libuv identities from the disposable account without reading
credentials. If versions cannot be mapped, retain that uncertainty explicitly.

## What upstream contracts do and do not provide

Electron documents `requestSingleInstanceLock` as acquisition **or notification
of an existing primary**; failure can already have forwarded arguments. It is
therefore not a passive incumbent probe.
[Electron API](https://www.electronjs.org/docs/latest/api/app#apprequestsingleinstancelockadditionaldata).

Current Electron source reads `DIR_USER_DATA` and passes it, with the application
name on Windows, to `ProcessSingleton`. Chromium's Windows implementation finds
a message window by profile path, uses a startup mutex, rechecks under that mutex,
and acquires the profile lock file before creating its message window. These
are implementation details of the native app, not an external launcher lease.
[Electron implementation](https://raw.githubusercontent.com/electron/electron/main/shell/browser/api/electron_api_app.cc),
[Chromium implementation](https://chromium.googlesource.com/chromium/src/+/refs/heads/main/chrome/browser/process_singleton_win.cc).

Chromium also contains hung-incumbent termination behavior, including a branch
without a visible window. Electron's patch makes its visible-window confirmation
callback refuse and makes the startup mutex name application-specific. **Unknown:**
the exact branches present in the installed target runtime. Do not infer that
starting another native instance is always harmless, particularly during early
startup or a hang.
[Chromium implementation](https://chromium.googlesource.com/chromium/src/+/refs/heads/main/chrome/browser/process_singleton_win.cc),
[Electron patch](https://raw.githubusercontent.com/electron/electron/main/patches/chromium/process_singleton.patch).

Windows `FILE_FLAG_FIRST_PIPE_INSTANCE` makes a subsequent creation using that
flag fail if the name already exists. Current libuv's initial Windows pipe bind
uses the flag and maps access-denied failure to `UV_EADDRINUSE`. This protects
the **bind attempt**, not a client's subsequent decision to join an existing
endpoint. The retained app's collision handling matters separately.
[CreateNamedPipe](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-createnamedpipea),
[libuv Windows pipe implementation](https://raw.githubusercontent.com/libuv/libuv/v1.x/src/win/pipe.c).

A pipe DACL governs access to client and server handles. Default pipe security
can include Everyone/Anonymous read access; generic write also includes the
right to create another pipe instance. Microsoft recommends a logon SID when
excluding other logon sessions. Thus neither a familiar pipe name nor the
observed owner SID establishes launcher authentication. Do not alter the
vendor's DACL to manufacture a passing result.
[Microsoft pipe security](https://learn.microsoft.com/en-us/windows/win32/ipc/named-pipe-security-and-access-rights).

Windows exposes server and client PID queries on pipe handles. These can identify
the particular connection inspected. Correlate a server PID with a retained
process handle, creation time, executable identity, user and session; failure to
obtain the required evidence must refuse admission. A separate observation
connection does not authenticate a different connection opened later by the
app, and polling cannot eliminate replacement between polls. This last point
is a concurrency inference, not a Windows API guarantee.
[Server PID](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-getnamedpipeserverprocessid),
[Client PID](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-getnamedpipeclientprocessid),
[Process handle rights](https://learn.microsoft.com/en-us/windows/win32/procthread/process-security-and-access-rights).

Upstream `main`/`v1.x` URLs above were inspected on this date. They describe
current source, not a version-pinned guarantee for the installed application.

## Minimal native experiment

Use an owned disposable clone, synthetic workspace/history and a loopback
provider. Automate preparation, barriers, timestamps, evidence and owned cleanup;
retain guided review for setup consent and visible build checks. Do not read
ordinary conversation content, copy credentials, change private service markers,
terminate an unrelated incumbent, or enable production Windows support.

Define admission before starting: no inference forwarding until the exact
launched app, owned bridge/main initialize, matching engine and native IPC owner
are established. Record whether native IPC traffic occurs *before* this admission;
delaying inference alone cannot prevent such traffic. A launcher-side readiness
check is insufficient if the native client already joined an unrelated router.

| Trial | Controlled ordering | Required observation / rejection |
| --- | --- | --- |
| Ordinary incumbent | Ordinary app ready, then launcher request | Refuse before another native invocation or shared-state change; original process, pipe and service survive unchanged. |
| Ordinary startup race | Pause launcher after absence check; release ordinary start before launcher spawn, during startup, and before bridge admission; repeat both winner orders | Identify actual winning process, profile, bridge and pipe. Losing launch must never be admitted, send inference, adopt the winner, or terminate it. Record activation/argument forwarding as a side effect, not passive refusal. |
| Two launchers | Both wait at the same acquisition barrier; also race different private state directories | One cooperating lease winner at most, bound to canonical user/profile identity. Separately verify native ownership; do not count a launcher lock as proof against ordinary starts. |
| Pipe precreated | A synthetic helper creates the fixed pipe before native start; separately insert it after discovery and before bind | Record native bind result and whether it connects or writes to the helper. Helper records connection PID, byte count and bounded message categories only; no secrets or message bodies. Unexpected connection/adoption blocks the candidate route even with zero inference requests. |
| Pipe ownership lost | After initial admission, close only the synthetic/owned server in the test case and let a synthetic replacement bind | Observe native reconnect behavior and route shutdown. No inference after ownership loss; any unauthenticated native reconnection is a separate failed isolation condition. Do not replace or stop an ordinary user's server. |
| Owner process/bridge loss | End the owned test app or bridge through the supervisor; retain a stale run record and retry | Close adapter/owned children, retain explicit failure, and verify process identity before cleanup/recovery. A live PID alone cannot validate stale ownership. Ordinary relaunch must work afterward. |
| Cross-user/session limits | Two explicitly provisioned disposable test identities/sessions, no credential changes; or record unavailable | Measure pipe creation and read/duplex connection separately, with PID/SID/session attribution. Failure to arrange a second identity is untested, not passed. Do not generalize one user's ACL query to isolation. |

Use event barriers rather than sleeps as the race specification. Preserve exact
package/app/engine hashes, launch activation route, observed profile, retained
process identities, pipe-handle observations, admission events, provider request
counts, original failures and independent cleanup results. Finite successful
races support the implementation argument; they do not prove all interleavings.
The contract still needs an atomic native mechanism, including crash and update
behavior, whose ownership can be attributed before protected actions.

## Decision boundary

The smallest plausible route to investigate is native singleton acquisition plus
the already-owned stdio bridge, with native IPC ownership demonstrated separately.
This is a hypothesis. If the matching target joins an unrelated pipe before it
can be authenticated, or loses ownership and reconnects without an enforceable
boundary, a later launcher check cannot repair the gap. Seek a supported
authenticated/profile-scoped target contract; keep production launch blocked
instead of adding retries, profile tricks, or a lock that ordinary starts ignore.

This research changed documentation only. Source fingerprints and relative
Markdown links were checked locally; no runtime tests or VM operations were run
for this note.
