# Local prerelease qualification

## Shared candidate coordination

The next shared candidate is tracked in
[#104](https://github.com/kreuzhofer/tofa-launcher/issues/104) and the
[rc15 report](v0.1.0-rc.15.md). Use its pinned version, source, assets and current
platform verdicts. Windows-local qualification is #105; the Mac coordinator's
combined readiness decision is #106. A published candidate is not automatically
qualified on either platform.

Routine Windows development uses a persistent Windows 11 ARM64 UTM environment.
Use new owned test state for lifecycle checks that need it; the disposable-VM
options below do not authorize treating the retained environment as disposable.

## Agent-operated rc14 procedure (historical, 2026-10-01)

Required targets are macOS ARM64 and Windows 11 ARM64 in UTM. Existing hosted
Windows CI remains supplementary by maintainer authorization. The agent operates
the lifecycle; only credentials and unavoidable OS/account consent require the
maintainer. Historical manual commands below remain available, but are not the
current #23 execution plan.

The historical candidate was `v0.1.0-rc.14`, commit
`14134d43df4cca00bcdf10e49b3dc5ef3122f8d7`. Download its assets without modifying
previous candidates. With `gh release download`, also save the exact release API
response as `release.json` and commit API response as `commit.json`. Transfer that
verified bundle to UTM; the runner rechecks all relevant SHA-256 entries locally.
`--downloaded-assets` accepts an explicitly trusted host download, not arbitrary
untrusted release metadata. This avoids transferring GitHub authentication.

Run the platform's existing runner with a **new**, nonexistent disposable state
directory (its parent must already exist):

```text
python scripts/qualify_macos.py --version v0.1.0-rc.14 --output REPORT.json
  --downloaded-assets ASSETS --agent-state-root NEW_STATE --codex CODEX
  --model deepseek-ai/DeepSeek-V4.1-Flash --guardian-model zai-org/GLM-5.3-Flash
  --check-pair
```

Use `qualify_windows.py` and native Python in UTM. Supply those arguments as one
command, with normal platform quoting. Agent mode retains normal HOME for native
vault access, isolates launcher configuration/installation and macOS shell files,
and refuses an existing state root. It authorizes purge only for the newly owned
state. The interactive login stage runs bare `tofa` through first-use onboarding
and launches the actual client with `--version`; drive its secret/project/app
prompts through a real PTY/ConPTY. Never put the key in command arguments or logs.
The saved-login lifecycle then runs live checks without another credential prompt.

The agent checks fresh process discovery directly, installs twice, preserves
login during uninstall, reinstalls the identical release, repeats the bounded
pair check, and purges only test state. Windows uses the installer's documented
session activation for a custom disposable installation when an ordinary tofa
already appears earlier in PATH; persistent entry counts and unrelated PATH
preservation are still checked independently. Final normal-account installation
and fresh-shell discovery are verified separately after test cleanup.

`--check-pair` requires an explicit Guardian and uses the existing capped observer:
one two-turn coding session plus one native allow/deny pair per lifecycle stage;
12 upstream requests, 1 MiB input/request, 4,096 output tokens/request, 180-second
coding turns and 120-second approval turns. Native Guardian/request deadlines
remain 90 seconds. A failed coding/approval stage stops acceptance. This is a
release sample, **not** the three-repeat support-promotion campaign in #75.
Models remain Experimental. Reports preserve numeric/category evidence only.

Native Windows fixture suites can be explicitly authorized in the owned VM with
`windows_lifecycle_test.ps1 -DisposableVM` and
`TOFA_TEST_DISPOSABLE_VM=1` for `qualify_windows_test.py`. These retain restoration
and synthetic-state checks; do not misrepresent the VM as GitHub Actions.

Final rc14 result: both required platforms passed the full CLI lifecycle on
2026-10-02, including Windows live inference using its already initialized native
sandbox. See the [final rc14 acceptance report](../evaluation/rc14-cli-2026-10-02.md)
for the original failures, corrections, exact evidence and preservation checks.
Those results qualify rc14 only. New sandbox account/policy setup still requires
OS consent; do not disable the sandbox to manufacture a pass.


These runners qualify the **Codex CLI** release lifecycle. They do not qualify the
shared desktop UI or ordinary desktop account continuity. The separate
[#50 shared-history qualification](desktop-shared-history-final-2026-09-24.md) records
the source candidate, passing desktop workflow checks and retained limitations
for [desktop prerelease tracking #35](https://github.com/kreuzhofer/tofa-launcher/issues/35).
The subsequent [#52 automatic-title qualification](../research/desktop-shared-title-generation.md)
records current-client generation, failed attempts and ordinary/tofa title
persistence. It supplements #50's original `not_observed` result without changing
that provenance or completing the broader #35 release qualification.

The macOS and Windows runners qualify the downloaded candidate in your **normal account**.
It installs the selected release, prompts for real login, checks Codex with
`moonshotai/Kimi-K3`, uninstalls preserving login, reinstalls and proves saved-login
reuse, then asks separately before purging local tofa state. It never uploads reports.

This is a maintainer qualification tool, not part of the published launcher bundle.
Use the runner from this repository checkout; candidate bytes and matching
installation scripts always come from the selected release. The runner does not
rebuild or replace published assets. Changed release files require a new candidate.

For `v0.1.0-rc.2`, use the [pinned two-machine handoff and evidence checklist](v0.1.0-rc.2.md#required-real-machine-qualification-handoff).

## Before running

Use macOS ARM64 with Python 3.9+, `curl`, the GitHub CLI (`gh`) and an installed
Codex CLI on PATH. Sign `gh` in using your existing authorized GitHub account.
The runner uses authenticated `gh` for both release metadata and downloads,
including private repository access, and never handles access tokens.
Normal launcher prerequisites, Keychain access and Token Factory connectivity
still apply. No extra OS account or self-hosted GitHub runner is required.

Close other launcher/Codex sessions to avoid concurrent changes. Before allowing
replacement or purge, arrange any backup, credential recovery or token reissue
**yourself**. The runner detects existing state but does not copy credentials.
Purging removes local saved credentials; it does not revoke Token Factory tokens.

From a checkout of the repository containing this runner:

```sh
python3 scripts/qualify_macos.py \
  --version v0.1.0-rc.2 \
  --timeout 600 \
  --output "$HOME/tofa-macos-rc2-$(date +%Y%m%d-%H%M%S).json"
```

If you need a checkout first, use `gh repo clone kreuzhofer/tofa-launcher` and
enter the resulting directory. Keep the runner checkout/commit recorded with your
attached report. The tag selects the candidate automatically; no commit copying
is needed. The runner resolves its commit via GitHub metadata, verifies all
selected binary/script checksums, and installs from that verified local download.

The human steps are deliberately explicit:

1. Type `READY` after preparing credential recovery and reviewing detected state.
2. Enter your real API key and project in the installed launcher's interactive
   login. Respond to any OS access prompts. Credentials are not runner arguments.
3. Open a **new terminal**, check `command -v tofa` and `tofa --version` against
   the path/version printed by the runner, then type `FOUND` in the runner.
4. After both live checks, type `PURGE` to remove local tofa state. Declining leaves
   state available for recovery and produces an incomplete report.

`--storage file` or `--storage keyring` explicitly selects a backend when needed.
The default leaves vault-first selection and existing saved backend choice to the
launcher. File storage is unencrypted; the launcher announces its location.
`--codex /absolute/path/to/codex` selects a client. Each command/live turn defaults
to 180 seconds (`--timeout`, maximum 600); each human/login step defaults to 900
seconds (`--human-timeout`, maximum 3600). OS prompts and signing blocks should be
recorded separately in the validation issue.

The command above allows ten minutes per live turn for variable Token Factory
latency. The observer uses the selected socket timeout, and the parent enforces
the total turn deadline across all requests and tools. After `FOUND`, two turns
create and extend a small JSON summary; both turns repeat after reinstall to
verify saved-login reuse. Client output is consumed privately, so the terminal
can remain quiet until a turn passes or fails. Four turns can take up to forty
minutes plus lifecycle steps. This harness timeout does not change Codex's
separate automatic-review deadline.

On a failed live turn, inspect `timed_out` and `elapsed_ms`, then its `streams`
entries for the last `stage`, HTTP `status`, `headers_ms` and `error_kind`.
Snapshots survive turn termination; unfinished requests remain failed/incomplete.
If transport and tools succeeded but `files_correct` is false, inspect the turn's
`file_checks`: output-file/JSON status, fixed expected-field match booleans, extra
field count and input preservation. These diagnostics export neither generated
values nor unexpected field names. A failed `saved_login_reuse` task does not by
itself mean authentication failed; inspect its request and task checks separately.

## Evidence and recovery

The command reserves a new JSON file and matching `.md` summary (mode 0600 on macOS;
the destination directory's Windows ACL on Windows),
before changing account state, and fills them with evidence when the run ends.
It rejects unwritable destinations and refuses to overwrite earlier evidence. Exit zero requires every lifecycle
stage, preservation assertion and final cleanup assertion to pass. Attach both
files to [the real-machine validation issue](https://github.com/kreuzhofer/tofa-launcher/issues/23)
yourself. A failed or interrupted run is evidence, too; retain it alongside reruns.

The live assertions reuse the [Codex compatibility harness](../prototype/LIVE-COMPATIBILITY.md):
incremental text deltas, successful shell-tool execution, independently checked
JSON results, and continuation of the exact conversation. Each check uses scratch
Codex configuration/authentication and a private workspace. The launcher retains
its normal account's saved credential access. Successful inference after reinstall,
without a second login, establishes saved-login reuse.

Reports contain only fixed stage names, counts/status/timing, public versions,
release identity and binary/script hashes. They exclude keys, credential-file
contents/hashes, private paths, project/session/credential identifiers and raw
conversation bodies. Normal Codex config/auth and unrelated files under tofa's
installation/config directories are compared in memory, including the contents of
symlinked files; no such hashes are
exported. Shell settings are compared after removing owned PATH blocks and trailing
newlines added by the installer. Only tofa's recorded Keychain references are
queried, without requesting secret values; unrelated vault entries are untouched.

On failure or Ctrl-C/SIGTERM, children are stopped and scratch directories are
removed; remaining installation/account state is reported rather than automatically
purged. Check the `cleanup` fields: `false` means state remains, `null` means a
check could not finish. Use the pinned standalone uninstaller from the release or
the remaining installed launcher's `uninstall` command to recover, after preparing
credentials. Unexplained failures cannot count as passes. A forced kill, power
loss or filesystem failure can prevent final reports/cleanup; inspect remaining
private temporary directories before rerunning. Reports stay local even on failure.

## Windows 11 amd64

Use Python 3.9+, authenticated `gh`, Windows PowerShell 5.1, the Windows .NET
Framework C# compiler, and an installed Codex CLI. The compiler comes with the
Windows .NET Framework; the runner compiles a temporary process helper without
building or modifying the candidate. No Go installation is needed. The helper
uses Windows Job Objects to contain the client tree and await asynchronous
uninstall helpers. Deadlines, Ctrl-C and Ctrl-Break terminate that tree.

From the checkout, run in your normal account:

```powershell
python scripts/qualify_windows.py --version v0.1.0-rc.2 `
  --output (Join-Path $env:USERPROFILE ('tofa-windows-rc2-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.json'))
```

The same `READY`, interactive login, `FOUND` and `PURGE` gates apply. At `FOUND`,
open a new terminal and run `Get-Command tofa` and `tofa --version`, comparing
the path and version with the runner's prompt. The runner independently reads
persistent user/machine PATH from the registry and launches a fresh process with
that environment. Existing terminals can retain stale PATH after cleanup.

Direct `codex.exe` installations and standard npm `codex.cmd` installations are
supported. The npm wrapper resolves to `node.exe` and the package's `codex.js`
entrypoint, so provider arguments never pass through `cmd.exe`. Use
`--codex C:\path\to\codex.exe` for an unfamiliar package-manager layout. The
observer shim is native `.exe`; the actual client receives scratch HOME,
USERPROFILE, APPDATA, LOCALAPPDATA, CODEX_HOME and temporary directories. The
launcher keeps its normal account's saved-credential access.

Downloads use authenticated `gh`. The exact matching PowerShell installer runs
with a child-scope download function that copies only the two expected verified
local assets. Published scripts and binaries remain unchanged. The runner never
changes execution policy. If policy or signing blocks a script/helper, retain the
failed report and record the block for investigation.

For its child processes, the runner removes inherited `PSModulePath` so Windows
PowerShell reconstructs its own module defaults. This addresses the documented
[PowerShell 7 → Python → Windows PowerShell inheritance behavior](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_psmodulepath#starting-windows-powershell-from-powershell-7),
which otherwise can make `Get-FileHash` unavailable. The parent/account environment
and published installer remain unchanged.

Preservation includes ordinary Codex config/auth, unrelated installation/config
files, unrelated user PATH entries and machine PATH. Credential Manager checks
address only tofa's recorded targets and free returned allocations without reading
credential blobs. Cleanup must include helper completion, owned executable/files,
PATH and saved file/vault credentials. A CLI exit before its helper finishes, a
failed helper, cancellation, or retained state cannot pass. Failure leaves account
state for deliberate recovery instead of automatically purging it.

## Reusing an initialized native Windows sandbox

For `--check-pair` on Windows, the explicit environment variable
`TOFA_NATIVE_WINDOWS_CODEX_HOME` may name the already-configured native Codex home.
This requires Python 3.11+ and a sandbox that is ready in that home. A newly
created `CODEX_HOME` does not inherit native sandbox setup; repeatedly creating
private homes can request administrator setup even when the normal home is ready.

```powershell
$env:TOFA_NATIVE_WINDOWS_CODEX_HOME = Join-Path $env:USERPROFILE '.codex'
# Run qualify_windows.py with --check-pair and the other pinned-candidate arguments.
```

This option shares existing sandbox runtime state; it does not initialize a
sandbox, copy credentials, or edit the native config/auth files. Test settings
are argv overrides. Unrelated MCP servers, plugins, hooks, memory and project
instructions are disabled for these test invocations. Log/SQLite state stays in
the disposable tree. Only session/snapshot files with IDs emitted by these test
invocations are removed afterward. The report records native config/auth
preservation, the number of owned sessions and cleanup; failures fail acceptance.
Ordinary Codex sessions and settings remain in place.

The disposable coding workspace explicitly grants its current user inheritable
Modify access. Python's private Windows temporary directories otherwise inherit
OWNER RIGHTS: files created by a sandbox account can be unreadable by the runner.
The rule applies only to the owned workspace and does not grant another user or
change sandbox policy. Expected output is still independently read and checked
by the ordinary account.

## Shared report v1

Windows qualification uses the same top-level fields and stage semantics. Platform
implementations may add evidence fields without changing these names:

| Field | Meaning |
| --- | --- |
| `schema_version` | `1` |
| `candidate.tag`, `.commit`, `.binary_sha256` | Requested prerelease, resolved commit, verified installed binary hash; unavailable values may be omitted on early failure |
| `candidate.scripts_sha256` | Verified matching installation/recovery-script hashes |
| `host.os`, `.arch`, `.release` | OS, native architecture and OS version |
| `client.version` | Validated Codex CLI version; omitted before successful preflight |
| `backend` | `keyring`, `file`, or `unknown` before successful login |
| `model` | `moonshotai/Kimi-K3` |
| `started_utc` | UTC timestamp |
| `existing_state` | Booleans for `installation`, `configuration`, `file_credentials`, `vault_references` |
| `stages` | Ordered `{name, status}` entries; statuses `pending`, `running`, `passed`, `failed`, `incomplete` |
| `preservation` | Named boolean checks; `null` means not established |
| `cleanup` | Named boolean checks; `null` means not established |
| `outcome` | `passed`, `failed`, or `incomplete` |
| `reason` | Fixed sanitized failure code, when applicable |
| `live`, `saved_login_reuse` | Sanitized live-harness assertions, when executed |

Shared stages: `preflight`, `recovery`, `download`, `install`, `login`,
`fresh_terminal`, `live`, `uninstall`, `reinstall`, `saved_login_reuse`, `purge`.
A `passed` human stage records the maintainer's explicit confirmation; synthetic
CI answers never establish real-machine acceptance. Full macOS and Windows reports
against the same final candidate remain required by #23.

## Offline development checks

```sh
python3 scripts/qualify_macos_test.py -v
python3 scripts/live_compat_test.py -v
```

The runner tests invoke its public CLI with temporary account directories, a
controlled `gh` executable, matching shell installers, a synthetic downloaded
launcher, synthetic Codex, and a synthetic Keychain command. They never access the
real account's saved credentials, native vault, GitHub or Token Factory. macOS and
Linux CI exercise offline orchestration; synthetic Keychain checks run on macOS.
Linux file-backend portability is not evidence of real Linux qualification.

Native Windows CI additionally runs `scripts/windows_process_test.py` and
`scripts/qualify_windows_test.py`. These use controlled GitHub downloads,
synthetic Codex/launcher boundaries, temporary account directories and unique
synthetic Credential Manager entries on disposable runners. They exercise
process-tree cancellation, shell-free npm discovery, persistent PATH, helper
failure/deadline handling, sanitized reports and the actual candidate's CLI
uninstaller. They do not establish either required human qualification result.
