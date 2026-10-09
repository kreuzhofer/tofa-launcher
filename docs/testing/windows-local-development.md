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

Save work before a coordinated Codex runtime restart/update and repeat both a
sandboxed shell command and a JavaScript-helper-then-shell check. An independent
controller is required if stopping the agent's own desktop/server. An available
desktop update has not been tested as a remedy. Do not delete sandbox accounts,
credentials, or setup state, weaken ACLs, or disable the sandbox to conceal this
failure. See the [measured evidence](windows-local-evidence-2026-10-09.md).
Track durable recovery in [#108](https://github.com/kreuzhofer/tofa-launcher/issues/108).

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
