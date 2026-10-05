# Repeatable Windows desktop investigation

Companion to the [contract report](windows-desktop-contract-2026-10-05.md).
These are research probes, not a supported desktop launcher or a release gate.
Run from the repository root on the maintainer's Mac. The checked-in scripts
record the exact historical attempt, including its cleanup failure. For a new
attempt, copy them to scratch, replace `tofa76-` with a unique run identifier,
and retain the originals/results unchanged. Never accept a stale completion file.

## Transport and identity

```sh
UTMCTL=/Applications/UTM.app/Contents/MacOS/utmctl
VM=545C23DD-356D-434A-B2AE-48277320BF34
"$UTMCTL" version
"$UTMCTL" list
"$UTMCTL" exec "$VM" --cmd cmd.exe /c 'exit 23'
```

Observed UTM version: 4.7.5. The last command returned host exit 0, not 23,
with no output. A separate `cmd /c echo` to an owned temporary file worked and
could be pulled. File-pull errors also sometimes returned host exit 0; inspect
stderr and require valid expected content. Do not infer guest success from an
empty host result. `exec` ran as SYSTEM in session 0, not the signed-in user.

Read-only SYSTEM inventory can run using an encoded PowerShell command, avoiding
shell quoting and policy changes. This Python snippet executes the historical
[inventory](evidence/windows-desktop-2026-10-05/inventory.ps1):

```python
import base64, pathlib, subprocess
utm = '/Applications/UTM.app/Contents/MacOS/utmctl'
vm = '545C23DD-356D-434A-B2AE-48277320BF34'
source = pathlib.Path('docs/research/evidence/windows-desktop-2026-10-05/inventory.ps1')
encoded = base64.b64encode(source.read_text().encode('utf-16-le')).decode()
submission = subprocess.run([utm, 'exec', vm, '--cmd', 'powershell.exe',
    '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded],
    capture_output=True, timeout=20)
# Submission is not completion. Pull C:\Windows\Temp\tofa76-inventory.json
# separately; require fresh timestamps, status="completed", exit_code=0.
```

Use `utmctl file pull "$VM" 'C:\Windows\Temp\tofa76-inventory.json'` to collect
the guest envelope. Allow at most 45 seconds for inventory, polling once per
second; stop and record a timeout if there is no valid completion record.
The [four-file probe](evidence/windows-desktop-2026-10-05/package-files.ps1)
uses the same mechanism. Reconfirm its pinned package path against the current
interactive-user registration before executing it. Do not recursively hash both
large installed versions or pull the entire 549 MB archive: those attempts did
not produce usable completion evidence in this run.

## Signed-in-user execution

An Interactive/Limited Task Scheduler action proved a deterministic command path
without passwords or elevation of the user's process. Run this registration
through the SYSTEM encoded-command transport above. `$encodedProbe` is the
UTF-16LE/base64 encoding of
[user-probe.ps1](evidence/windows-desktop-2026-10-05/user-probe.ps1).
Use a fresh task name; do not overwrite someone else's task.

```powershell
$ErrorActionPreference = 'Stop'
$name = 'tofa76-user-probe-20261005' # choose a new owned name for replay
if (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) {
    throw 'Task name already exists'
}
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument (
    '-NoProfile -NonInteractive -EncodedCommand ' + $encodedProbe)
$principal = New-ScheduledTaskPrincipal -UserId 'SabreTest' `
    -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Seconds 45)
Register-ScheduledTask -TaskName $name -Action $action `
    -Principal $principal -Settings $settings | Out-Null
Start-ScheduledTask -TaskName $name
```

Require `Get-ScheduledTaskInfo` last-run/result and the fresh JSON envelope to
agree. This query selected only version `26.930.2377.0`, unlike SYSTEM's all-users
inventory. A registered package is not enough to claim a UI pass.

The native activation action was:

```powershell
New-ScheduledTaskAction -Execute 'explorer.exe' -Argument `
    'shell:AppsFolder\OpenAI.Codex_2p2nqsd0c76g0!App'
```

The resulting task returned 1, but the exact native app and child engine were
observed running in session 1, and computer use observed the signed-in Codex home
screen. Retain both results; an activation task's status is not a desktop health
check. Never run native desktop qualification as SYSTEM.

## Bounded engine probe

The [exact attempted Python probe](evidence/windows-desktop-2026-10-05/engine-probe-attempt.py)
uses the observed user-local engine, empty temporary home, ephemeral credentials,
and a non-listening loopback provider. It sends initialize/config/requirements/
account reads only, with 15-second operation deadlines. It sends no conversation
turn and makes no model inference request. It does not override native sandbox
or approval policy. Confirm the engine hash still matches the pinned evidence.

Copy the script to a new, user-readable investigation path, using UTM file push:

```sh
"$UTMCTL" file push "$VM" 'C:\Users\Public\tofa76-engine-probe.py' \
  < docs/research/evidence/windows-desktop-2026-10-05/engine-probe-attempt.py
```

Use an Interactive/Limited task action with executable
`C:\Python313ARM\python.exe` and argument
`C:\Users\Public\tofa76-engine-probe.py`, and a two-minute execution limit.
Python's path was discovered in the user-context probe. Do not assume it on
another guest. The earlier attempt from a SYSTEM-created Windows Temp script
exited 2 with no report; the Public-path retry reached the engine protocol.
The cause of the first exit was not independently established.

Pull `C:\Windows\Temp\tofa76-engine-probe.json`. Its overall `exit_code=1` is a
**failed attempt**, despite successful protocol reads and engine exit 0:
immediate temporary cleanup encountered a sharing violation on `stderr.txt`.
Do not edit that historical outcome into a pass. Subsequent scoped removal
succeeded. A future harness needs bounded cleanup retries and child ownership
checks, retaining failures as evidence. This script is an executable reproduction
of the experiment, not a claim that its cleanup is release-ready.

## Schema and catalog follow-up

[Schema probe](evidence/windows-desktop-2026-10-05/schema-probe.py) runs
`app-server generate-json-schema --experimental --out <temporary-directory>`
against the same engine with an isolated SYSTEM home. Its generation and cleanup
passed; this is schema evidence only.

The [final catalog probe](evidence/windows-desktop-2026-10-05/catalog-final-probe.py)
uses the same Interactive/Limited Python task mechanism as above, a distinct
user-readable `C:\Users\Public\tofa76-catalog-final-probe.py`, and output
`C:\Windows\Temp\tofa76-catalog-final-probe.json`. It exports bundled descriptors,
adds two synthetic identities, injects the static catalog, requests `model/list`,
and asserts the identities and `auto_review` reviewer default. Explicit UTF-8
handles engine JSON. The test creates no turn and changes no native configuration.
The final attempt exited 0 and temporary cleanup succeeded. Unregister its exact
task name after checking completion, as for the original probes.

Earlier [failed attempts](evidence/windows-desktop-2026-10-05/catalog-failed-attempts.json)
are retained. The initial fixture incorrectly used `guardian`, while the engine's
accepted enum includes `auto_review`; capturing stderr exposed the rejection.
The final fixture preserves diagnostics and uses the repository's established
`auto_review` value. A successful configuration assertion still cannot establish
actual Guardian execution, renderer picker behavior or ordinary-account policy.

## Visible app and preservation checks

Use computer use on the UTM app, select the guest window, and observe each result
before the next action. Initial text entry dropped characters and clipboard paste
timed out. UTM input capture followed by Alt+Tab exposed the native app; Escape
dismissed the account menu. Other key sequences, including Alt+F4, did not prove
the intended result. Release capture afterwards (`Ctrl+Option`, or the tested
`Ctrl+Option+Escape`) and verify the Capture Input checkbox is off.

Observe only the needed UI: login status, local/native versus WSL mode, picker,
conversation continuity, approval outcome and ordinary recovery. Do not open
private chats for evidence or export account/history screenshots. This run used
written sanitized observations. The app's local Windows child path established
native mode; future tests must explicitly detect and reject an unintended WSL
route rather than changing the user's default.

No destructive test ran. Before purge/crash/update-recovery tests, establish
ownership of a disposable VM clone/snapshot without resetting a running guest
or overwriting an existing snapshot. Never reuse the ordinary native service as
a disposable child. Authentication, workspace consent and OS approval gates
remain native; inability to automate a gate is a reported blocker.

## Completion and cleanup

For each uniquely owned task, inspect state, then unregister only that exact
name. If still running, record the timeout and stop only that task after checking
its action identity. Remove only the exact synthetic home created by the probe;
do not wildcard-delete user state. Native app and sandbox-service processes are
not cleanup targets. Never restore a native settings snapshot over concurrent
user changes.

```powershell
Get-ScheduledTaskInfo -TaskName $name
$task = Get-ScheduledTask -TaskName $name
if ($task.State -eq 'Running') { throw 'Probe still running; inspect ownership' }
Unregister-ScheduledTask -TaskName $name -Confirm:$false
```

The recorded [cleanup](evidence/windows-desktop-2026-10-05/cleanup.json) removed
all three investigation tasks, stopped the identified stalled SYSTEM wrapper,
removed the failed synthetic home and verified the relocated engine hash.
Read-only probe/code extracts remain in the guest's `tofa76-*` scratch files for
inspection. Ordinary native login/history were not rewritten by the probes;
the ordinary app remains open. No VM restart or snapshot operation was used.
The later [final cleanup](evidence/windows-desktop-2026-10-05/final-cleanup.json)
records the successful catalog task result and zero remaining investigation tasks.
Use the full [acceptance matrix](windows-desktop-contract-2026-10-05.md#automation-and-acceptance-matrix)
before claiming any Windows desktop support.
