# Windows Codex sandbox recovery evidence - 2026-10-09

For [#108](https://github.com/kreuzhofer/tofa-launcher/issues/108), starting on
`main` at `1fa0aecb8cea6fa323c0eb387de99d1e55816376`.
This concerns the local development runtime, not launcher desktop qualification.

**Result:** native agent development recovered by explicitly pinning the managed
daemon to the retained vendor-distributed Codex 0.160.1 package. JavaScript helper
startup followed by sandboxed read/edit/test commands passed after the daemon
restart. The 0.162.0 defect was not patched; the pin is the measured local remedy.

## Reproduction and version comparison

The active native agent and standalone CLI used Codex 0.162.0. With
`cua_node/7fd62bce4099ba73/bin/node_repl.exe` running, both the agent shell and
the following standalone command failed before PowerShell started:

```powershell
codex sandbox -P :workspace -- powershell.exe -NoProfile -Command Get-Location
```

The standalone command returned exit 1 and
`windows sandbox failed: helper_unknown_error: setup refresh had errors`.
The dated sandbox log identified `runtime read/execute validation failed` on
that executable, with Windows sharing violation 32. Its existing ACL granted
`CodexSandboxUsers` ReadAndExecute and Synchronize; no manual ACL edit was made.

The supported `codex update` command succeeded but resolved 0.162.0 again.
Doctor reported CLI, installed daemon, and running daemon versions of 0.162.0.
It advertised desktop 26.1007.2314.0, whereas the installed ARM64 package was
`OpenAI.Codex` 26.930.7945.0, displayed as ChatGPT in WinGet. A scoped Store
upgrade for `ChatGPT`, ID `9PLM9XGG6VKS`, reported no available upgrade. Store
source terms were accepted for that query; no desktop upgrade occurred.

The JavaScript tool's bundled engine at
`%LOCALAPPDATA%/OpenAI/Codex/bin/2c64dcfa86419e1c/codex.exe` identified itself as
0.160.1 and passed the same sandbox command with the same helpers still running.
The retained standalone vendor package at
`%USERPROFILE%/.codex/packages/standalone/releases/0.160.1-aarch64-pc-windows-msvc`
also passed.

A task-local probe under `.qualification/windows-local/issue-108/probe.ps1`
then verified, through that retained engine's `sandbox -P :workspace`:

- Reading `go.mod`, creating a workspace marker, editing it, and reading it back.
- `UnauthorizedAccessException` for new sentinel writes directly under the
  ordinary user's profile and inside the repository's `.git` directory.
- `go test -count=1 -timeout=120s ./internal/tofa -run '^TestWindows'` passed
  in 0.377 seconds with cached dependencies and `GOPROXY=off`.

The active 0.162.0 agent shell still failed immediately afterwards. This is
evidence of different behavior between engines, not proof of the precise
upstream code defect. No helpers were stopped for this comparison.

## Independently controlled recovery

The 0.160.1 CLI advertises
`app-server daemon update --from-cli --yes` as copying and pinning its package.
Its doctor check can read the existing databases: integrity checks passed,
all seven active rollout files matched the thread inventory, and existing
ChatGPT authentication was configured. No credentials were read or copied.

An independent hidden native PowerShell controller was started and verified alive
after its parent command shell exited. It waited for a separate start marker,
then ran the retained 0.160.1 executable with
`app-server daemon update --from-cli --yes`. The supported updater reported
`installedVersion: 0.160.1`, `runningVersion: 0.160.1`, and an explicit package pin.
The managed daemon changed from PID 2260 to PID 3116 at 01:22:20 local time.
Its package is now a `local-28133e6461b7eae47df1c5e1d06d5b02388417a6f0c05f24c2193279ff84ef1a-aarch64-pc-windows-msvc`
copy made by the supported updater. The controller verified all seven pre-existing
session files remained and the user's `config.toml` hash was unchanged.

The controller's post-pin sandbox probe passed, including targeted tests in
0.439 seconds. Its extra attempt to queue continuation failed because it combined
mutually exclusive `--sandbox` and `--approve-for-me` flags. That failure did not
undo the completed pin. Native daemon recovery restored this same conversation
automatically; no new login or manual session reconstruction was needed. The
one-shot controller exited and is not an ongoing service. Local transcripts and
the probe remain under ignored `.qualification/windows-local/issue-108`.

No Windows UAC prompt or new authentication consent was required in this run.
Scoped tool-execution approvals were used for the updater and ordinary-account
diagnostics. PowerShell execution-policy overrides were process-local. This does
not promise that another Windows installation will not require OS consent.

## Verification after restart

`cua.getState()` succeeded in the restored native session. Newly started
`node_repl.exe` processes 11904 and 12200 were observed after the daemon restart,
using the same runtime path as before. With those helpers active, the normal
agent shell, without external execution approval, passed the following checks:

| Check | Observed result |
| --- | --- |
| Workspace read, marker creation/edit/read-back | Passed |
| New sentinel writes outside the workspace and inside `.git` | Both denied with `UnauthorizedAccessException` |
| Targeted `go test -count=1 -timeout=120s ./internal/tofa -run '^TestWindows'` | Passed, 0.154 seconds |
| Full `go test -count=1 -timeout=120s ./...` | All packages passed; `internal/tofa` 3.091 seconds, `scripts` 0.739 seconds |
| `go vet ./...` | Exit 0 |
| `go build -o .qualification/windows-local/tofa.exe ./cmd/tofa` | Exit 0 |
| `python scripts/windows_process_test.py -v` | 10 tests passed, 5.173 seconds |

An independent reviewer then repeated the same probe in a fresh agent session
through a normal sandboxed shell, without execution escalation. Workspace
read/edit/read-back passed, both sentinel writes were denied, and targeted
Windows tests passed in 0.134 seconds while the JavaScript helpers remained
active. This extends the resumed-conversation checks to a fresh session.

Tests used Go 1.27.1 `windows/arm64`, the existing workspace caches, and
`GOPROXY=off`. The Go race detector is unsupported on `windows/arm64`; race
coverage remains on supported CI platforms. No disposable VM, installation
lifecycle, desktop/model qualification, or Unix-only suite was run for this
runtime recovery. No launcher product code changed; the real external runtime
probe was the failing-before/passing-after test seam.

Ordinary-account `codex app-server daemon version` now reports CLI 0.162.0 and
managed/running daemon 0.160.1. Doctor reports sandbox provisioning complete,
restricted filesystem and network policies, existing authentication configured,
and matching rollout/database inventories with no missing or stale rows. Running
the management CLI *inside* a restricted shell can instead report that it cannot
resolve `CODEX_HOME`; use the ordinary account for these management checks.

The standalone CLI remains 0.162.0, so its direct `codex sandbox` path is not
repaired by the daemon pin. Use the explicitly versioned 0.160.1 executable for
standalone sandbox probes. Normal native agent tools use the pinned daemon.
The [local development procedure](windows-local-development.md#codex-sandbox-setup-failure)
records the pin command, verification steps, and deliberate return to production
updates. Requalify any future engine before removing this pin.

The existing `skills-lock.json` modification is outside this task; its SHA-256
is `f95d4aade147fa5d35590b4c4efdbc20831518f99f5c62b041a7e78a8e73804b`.
No sandbox account deletion, agent-authored credential change, Defender exclusion,
sandbox disablement, or manual broad ACL grant was performed. Vendor sandbox
setup continued to manage its own ordinary ACL provisioning. No upstream vendor
message was sent.

## Review

Two independent reviews compared the task with starting commit
`1fa0aecb8cea6fa323c0eb387de99d1e55816376`.

### Standards

Zero documented-standard violations and zero baseline heuristic findings.
The documentation scopes the remedy, distinguishes the pin from fixing 0.162.0,
records failed attempts and test limitations, and preserves security boundaries.
The controller output corroborates the pin, session/config preservation,
boundary denials, and targeted test pass. Normal sandboxed reads also succeeded
in the review session. The review did not repeat the runtime change or full suite.

### Spec

Zero findings. The recovery meets #108's required outcomes and stays within its
local development scope. The fresh-session probe above independently passed.
The explicit limitations remain: daemon 0.160.1 is pinned and standalone CLI
0.162.0 remains affected. The review did not repeat the runtime change or full
suite.

Total findings: Standards 0; Spec 0.

## Recurrence during #105

Later on 2026-10-09, the #105 preflight found the managed/running daemon back at
0.162.0 and the `auto-update-version` marker present again. Ordinary agent shell
setup reproduced `helper_unknown_error`; the dated sandbox log again identified
sharing violation 32 on the active `cua_node/.../bin/node_repl.exe`. The cause
of the pin replacement has not been established. The earlier measured recovery
and fresh-session passes remain historical evidence, not the current daemon state.

The retained explicit standalone 0.160.1 client still passed the pinned rc16
loopback qualification prerequisite, including native tools, Guardian allow/deny,
config/auth preservation and cleanup of its three owned sessions. The daemon was
not repinned by #105. See the [rc16 Windows report](../releases/v0.1.0-rc.16-windows.md)
for the separate, incomplete release qualification and remaining login requirement.

## Sources

- Local versioned `codex help sandbox`, `codex update --help`, and
  `codex app-server daemon update --help` establish the commands used above.
- [Official Windows app documentation](https://learn.chatgpt.com/docs/windows/windows-app)
  identifies the Store package and native PowerShell/sandbox support.
- [Official troubleshooting guidance](https://learn.chatgpt.com/docs/reference/troubleshooting)
  distinguishes CLI and desktop versions and recommends preserving policy
  boundaries when diagnosing execution failures.
