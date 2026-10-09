# Windows-local development evidence — 2026-10-09

For [#103](https://github.com/kreuzhofer/tofa-launcher/issues/103).
The native build/test baseline passes. Development-tool repairs are persistent;
the Codex JavaScript-runtime/sandbox interaction remains reproducible and needs
a separate repair. This is setup evidence, not model or desktop qualification.

## Environment and preservation

- VM: `tofa77 Windows ARM64 bridge prototype`, confirmed by the operator and
  independently by `Win32_ComputerSystemProduct.UUID`:
  `EF96CF12-D901-455F-81FF-4C5001E15F80`.
- Guest: `WIN-NT3N6IPH111`, QEMU, Windows 11 Pro 10.0.26200, ARM64.
  `Win32_Processor.Architecture` returned 12; Python reported ARM64 and Go
  reported `windows/arm64`.
- Workspace: `C:\Users\tofa-test\src\tofa-launcher`, owned by the existing
  `tofa-test` user. Branch `main`, source commit
  `28557a88ab46f00da4a936f644f7423658d9f70f`, also verified as remote `main`.
  The ownership prototype branch was not merged or selected for development.
- Existing `skills-lock.json` edits were retained. Its SHA-256 before and after
  the environment repair was
  `f95d4aade147fa5d35590b4c4efdbc20831518f99f5c62b041a7e78a8e73804b`.
- No VM lifecycle operation, account/password change, credential copying,
  production launcher installation, or desktop launch/termination was performed.
  Sabre was not accessed. No host-side VM inventory was available in this local
  task; preservation claims describe the operations performed, not a new host
  inventory measurement.

## Tools and repairs

| Tool | Measured version / change |
| --- | --- |
| Go | Missing initially; installed official Go 1.27.1 Windows ARM64 archive in `%LOCALAPPDATA%\Programs\Go1.27.1` |
| Python | Existing 3.13.15 ARM64; repaired `python3` resolution by copying its interpreter executable alongside `python.exe` |
| Git | 2.55.0.windows.5; exposed existing Git Bash 5.3.15 on user PATH (Bash itself is x86-64) |
| GitHub CLI | 2.102.0; existing authorization successfully read repository issues |
| Node | v24.21.0 |
| Codex CLI / daemon | 0.162.0, Windows aarch64 |
| Installed Codex desktop package | 26.930.7945.0, ARM64; no new desktop qualification performed |

Go matches `.github/workflows/prototype.yml`. The archive was obtained from
[the official download endpoint](https://go.dev/dl/go1.27.1.windows-arm64.zip),
and its SHA-256 was checked against [official metadata](https://go.dev/dl/?mode=json&include=all):
`13b69b87bb0e83f96bc68560a8cace7f0343b1e03469f1110ea18d17e3234069`.
No existing Go installation was replaced. Existing user PATH entries were
preserved while adding Go and Git Bash. A fresh PowerShell process using the
saved machine/user PATH resolved all three commands correctly.

Both Python executables had SHA-256
`7944f73d1dc202232cd0f615d14f909603af1cd00d6a3ff98dac51c49259c44b`.
The original `python3` Store alias did not launch Python. The replacement command
now returns Python 3.13.15 and imports the native ARM64 runtime successfully.

The first commit attempt also exposed missing Git author settings. Repository-local
identity was configured as Daniel Kreuzhofer with the authenticated GitHub
account's noreply address `1763467+kreuzhofer@users.noreply.github.com`; global
Git configuration was not changed.

## Agent-operated checks

The local agent read repository instructions, created and edited the task-owned
`windows-local-development.md` through the patch tool, and independently read it
back through native PowerShell and Python assertions. No extra model login was
needed: this existing local agent session and existing GitHub authorization were
reused. No credentials were read or transferred.

| Check | Observed result |
| --- | --- |
| `python scripts/windows_process_test.py -v` | 10 tests passed, 6.580 seconds |
| `go test -count=1 -timeout=120s ./internal/tofa -run '^TestWindows'` | Passed, 1.725 seconds |
| `go test -count=1 -timeout=120s ./...` | All packages passed; overall command also bounded by a 300-second Python subprocess timeout |
| `go vet ./...` | Exit 0 |
| `go build -o .qualification/windows-local/tofa.exe ./cmd/tofa` | Exit 0 |
| `go version -m` on the built executable | Go 1.27.1, GOOS=windows, GOARCH=arm64, source revision above, modified worktree explicitly recorded |
| Built executable `--version` | `tofa dev-prototype`, exit 0 |
| PowerShell parser over `scripts/*.ps1` | Passed |
| Offline `scripts/windows_test.ps1` through a 120-second subprocess | Passed, including synthetic preservation checks and owned temporary-directory cleanup |
| `python scripts/qualify_windows_test.py -v` | Skipped: retained VM is neither disposable CI nor explicitly disposable state |
| `go test -race ./...` | Explicit limitation: `-race is not supported on windows/arm64` |

Full Go suite output:

```text
?    github.com/kreuzhofer/tofa-launcher/cmd/tofa [no test files]
ok   github.com/kreuzhofer/tofa-launcher/internal/tofa 5.305s
ok   github.com/kreuzhofer/tofa-launcher/scripts 1.968s
?    github.com/kreuzhofer/tofa-launcher/scripts/fixtures/evaluation_launcher [no test files]
?    github.com/kreuzhofer/tofa-launcher/scripts/fixtures/picker_launcher [no test files]
```

Unix-only suites, native desktop/model trials, and disposable installation/recovery
qualification were not run. No disposable-VM flags were asserted. The local
executable and dependency/build caches remain in ignored
`.qualification/windows-local` for continued use.

## Failures, approvals, and remaining blocker

Durable sandbox recovery is tracked in
[#108](https://github.com/kreuzhofer/tofa-launcher/issues/108).
The operator requested restarting Codex after this session; no desktop/server
restart or update was performed during it.

1. The initial sandbox command failed before PowerShell started:
   `helper_unknown_error: setup refresh had errors`. The dated vendor log pinned
   this to read/execute validation of `node_repl.exe`, Windows sharing violation
   32. The file already granted the sandbox group ReadAndExecute. No ACL edit or
   security-policy change was made.
2. Resetting the JavaScript tool kernels did not release the file lock. Stopping
   only the verified helper processes restored ordinary sandboxed shell commands;
   the subsequent build, vet, and documentation read-back succeeded there.
3. Restarting JavaScript tooling reproduced the same error; the tool also
   returned `Transport closed`. Clearing the verified helpers again is temporary
   mitigation, not a completed durable repair. `codex doctor --summary` confirmed
   the structured provisioning failure. It advertised desktop build 26.1007.2314.0;
   that update was not installed or established as a fix.
   Both independent review sessions subsequently reproduced the shell startup
   failure without explicitly invoking JavaScript tools, so routine helper
   activity can also reintroduce it. Their approved read-only commands succeeded.
4. While the sandbox was unavailable, scoped external execution approvals were
   required. Tool installation and the initial Go module download also required
   scoped approval. The sandbox rejected dependency network access as expected.
5. The offline installer test initially failed inside the sandbox at
   `Get-CimInstance Win32_Processor` with access denied (`0x80041003`). The same
   bounded command passed with approved ordinary native execution. This is an
   execution-boundary requirement, not a failed installer baseline.

The initial sandbox repair did not invoke UAC or reinitialize accounts. Durable
runtime recovery must be independently controlled if it stops the active agent;
repeat helper startup plus sandbox execution afterwards. The setup does not
promise that “Approve for me” suppresses every external execution request.

Use the [Windows-local start procedure](windows-local-development.md) for future
work. Windows desktop availability remains disabled, with #102 still gating #87.

## Review

Independent Standards and Spec reviews compared this documentation change with
the starting source commit above. Both reported zero findings. No product code
changed. The separately linked runtime repair and deferred restart remain open.
