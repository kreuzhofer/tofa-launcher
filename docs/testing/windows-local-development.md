# Persistent Windows-local development

Use the retained `tofa77 Windows ARM64 bridge prototype` VM for ordinary
development, as agreed in [#103](https://github.com/kreuzhofer/tofa-launcher/issues/103).
Keep `Sabre Windows 11 ARM64` and both VMs' data. Routine editing and tests do not
require resetting, reinstalling, or cloning a VM.

## Start locally

1. Sign into the existing Windows `tofa-test` account and open the native workspace
   `C:\Users\tofa-test\src\tofa-launcher` in Codex or PowerShell.
2. Run `git status --short`, `git branch --show-current`, and `git rev-parse HEAD`.
   Use `main` for integration; preserve existing changes before changing branches
   or updating the checkout. Record the tested commit in the work's existing ticket.
3. Verify `go version`, `go env GOOS GOARCH`, `python3 --version`, `git --version`,
   `gh --version`, `bash --version`, and `codex --version`.
4. Use the existing Windows authentication. Do not copy credentials from macOS,
   another Windows account, or another VM. Missing authentication or Windows
   consent must be completed by the intended user in Windows.

For a terminal started before a user PATH update, refresh only that process:

```powershell
$env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' +
    [Environment]::GetEnvironmentVariable('Path', 'User')
```

Run that refresh in the ordinary Windows account. A Codex sandbox process can
have a different user registry view; restart the native terminal/agent to inherit
the updated environment rather than reading its sandbox user's PATH.

## Native baseline

The prepared VM has Go 1.27.1 ARM64 (matching the repository's CI version),
Python 3.13.15 ARM64, and Git Bash. Go is installed under
`%LOCALAPPDATA%\Programs\Go1.27.1\go`; its `bin` directory and
`C:\Program Files\Git\bin` are on the persistent user PATH. The installed
`C:\Python313ARM\python3.exe` is a byte-identical copy of that installation's
`python.exe`, so subprocesses can use the repository's `python3` command.
Recheck that alias after upgrading Python.

From the repository root in native PowerShell:

```powershell
$ErrorActionPreference = 'Stop'
$env:GOCACHE = Join-Path $PWD '.qualification\windows-local\go-cache'
$env:GOMODCACHE = Join-Path $PWD '.qualification\windows-local\go-mod'
go test -count=1 -timeout=120s ./...
if ($LASTEXITCODE -ne 0) { throw 'Go tests failed' }
go vet ./...
if ($LASTEXITCODE -ne 0) { throw 'Go vet failed' }
go build -o .qualification/windows-local/tofa.exe ./cmd/tofa
if ($LASTEXITCODE -ne 0) { throw 'Native build failed' }
python scripts/windows_process_test.py -v
if ($LASTEXITCODE -ne 0) { throw 'Windows process tests failed' }
```

Keep these caches between iterations. The first dependency download needs network
access; subsequent offline tests can use the populated cache. Go's race detector
does not support `windows/arm64`; run `go test -race ./...` on a supported CI
platform. Do not represent the native non-race pass as a race pass.

The bounded offline installer test uses temporary synthetic installation state,
checks unrelated-file preservation, and cleans up its own directory:

```powershell
python -c "import subprocess; subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File','scripts/windows_test.ps1'],check=True,timeout=120)"
```

This process-local execution-policy choice does not change saved policy. The
test's CIM hardware query requires ordinary native execution; the Codex sandbox
denied it in the recorded run, so a scoped execution approval was required.

## Codex sandbox setup failure

On engine 0.162.0, setup refresh failed with Windows error 32 while validating
access to the in-use `cua_node/.../bin/node_repl.exe`. Inspect the current dated
log under `%USERPROFILE%\.codex\.sandbox` and `codex doctor --summary`.
Restarting the verified JavaScript helpers temporarily restored sandboxed shell
execution, but restarting JavaScript tooling reproduced the failure. It is not
a durable fix or evidence that the sandbox needs broader permissions.

The earlier recovery used an explicit **managed-daemon pin to Codex 0.160.1**.
That vendor package passed the same probe with the JavaScript helpers active;
0.162.0 failed. The supported updater restarted the daemon, preserved sessions,
and the resumed native agent passed sandboxed reads, edits, boundary-denial
checks, the full Go suite, vet, and build after JavaScript helper startup. See
[#108](https://github.com/kreuzhofer/tofa-launcher/issues/108) and the
[recovery evidence](windows-codex-sandbox-recovery-2026-10-09.md).

Later #105 preflight found the managed daemon back at 0.162.0 and the same
sandbox failure recurring; the cause of pin replacement is unknown. Check the
actual version before relying on that recovery. The retained standalone 0.160.1
still passes the native loopback prerequisite. See the
[recurrence](windows-codex-sandbox-recovery-2026-10-09.md#recurrence-during-105).

The standalone CLI remains 0.162.0. From an ordinary native PowerShell window,
`codex app-server daemon version` should show managed/running daemon 0.160.1.
Use this explicit retained executable for standalone sandbox probes:

```powershell
$recoveryCodex = Join-Path $env:USERPROFILE '.codex/packages/standalone/releases/0.160.1-aarch64-pc-windows-msvc/bin/codex.exe'
& $recoveryCodex --version
& $recoveryCodex sandbox -P :workspace -- powershell.exe -NoProfile -Command Get-Location
```

If the pin needs to be reapplied, save work and use an independent native
PowerShell controller or terminal, outside the agent being restarted. Verify the
retained executable exists and reports 0.160.1, then run:

```powershell
& $recoveryCodex app-server daemon update --from-cli --yes
if ($LASTEXITCODE -ne 0) { throw 'Codex daemon pin failed' }
& $recoveryCodex app-server daemon version
```

This is a supported package pin, not a patched 0.162.0 binary. Do not silently
remove it: `codex app-server daemon update` returns the daemon to production
updates and may interrupt work. Test a future candidate with its JavaScript
helper active before switching, then repeat the read/edit/test and boundary
checks in a fresh native session. Confirm saved sessions remain available and
existing authentication still works. The standalone `codex update` command did
not offer a newer engine during recovery; the Store offered no desktop upgrade
even though doctor advertised one. A desktop update is not an established fix.

No UAC or new login was required for the measured recovery; other installations
may require OS consent. Do not delete sandbox accounts, credentials, or setup
state, weaken ACLs, add Defender exclusions, or disable the sandbox to conceal
this failure. The [earlier evidence](windows-local-evidence-2026-10-09.md)
records the original failure and temporary helper-stop experiment.

## Boundaries for release work

Local setup and offline tests do not qualify a model or enable the Windows
desktop target. [#102](https://github.com/kreuzhofer/tofa-launcher/issues/102)
still gates [#87](https://github.com/kreuzhofer/tofa-launcher/issues/87). Read the
[retained ownership prototype evidence](https://github.com/kreuzhofer/tofa-launcher/blob/e1cd869cf750042990666268caef6bdd350e74d1/docs/testing/windows-atomic-ownership-evidence-2026-10-08.md)
before ownership work. Its fixed-pipe result applies to the measured route.

For installation, recovery, and destructive tests, first establish task-owned
isolated state and check preservation afterwards. Never set
`TOFA_TEST_DISPOSABLE_VM=1` or impersonate CI on this retained development VM.
The disposable qualification tests remain separate. If a test stops the desktop
hosting the development agent, arrange an independent controller before running
it. Coordinate shared releases through GitHub tickets with the Mac developer;
claim subsequent platform work in its existing ticket.
