# tofa — Token Factory launcher

A standalone launcher that connects an **already installed Codex CLI or the tested
macOS Codex desktop app** to Nebius Token Factory. It does not run models locally
or install the target client.

The current release is [v0.1.0-rc.14](https://github.com/kreuzhofer/tofa-launcher/releases/tag/v0.1.0-rc.14),
an experimental prerelease with the macOS desktop integration. Release downloads
are public; no GitHub account is needed to install.

- The desktop qualification covers ChatGPT 26.928.21956 (12404), Codex mode,
  bundled engine 0.159.2 on macOS 26.6.2 ARM64. Compatible newer clients are
  accepted above documented minimums, subject to protocol and ownership checks.
- Conversations keep their own Token Factory model and history. Eligible choices
  remain available, using `(Token Factory)` or `(TF Experimental)` labels.
  Desktop model/reasoning defaults remain isolated from concurrent CLI sessions.
- Release CI checks native installation and execution on macOS ARM64, Linux amd64
  and Windows amd64 using synthetic state. Windows desktop and the separate
  real-account CLI platform qualification in #23 are not established by those checks.

See the [rc14 release report](docs/releases/v0.1.0-rc.14.md) for published artifacts,
first-use verification on macOS and Windows ARM64, and remaining CLI acceptance gates. [Desktop setup](docs/codex-desktop.md) explains the
supported boundary, including explicit naming and compaction limitations.
Historical CLI evidence remains in the [rc2 report](docs/releases/v0.1.0-rc.2.md).
Claude, other desktop modes and browser OAuth remain outside the current scope.

## Installation

Use the version-pinned commands below to install **v0.1.0-rc.14** directly from
GitHub. The installer downloads only the binary matching your operating system
and CPU.

Installation is per user and needs no administrator privileges. The installer
verifies the binary's SHA-256 checksum, updates your PATH and prints the exact
command to activate tofa in your current terminal. An already installed target client
and a Token Factory API key and project ID are required to launch it.

### macOS and Linux

```sh
version=v0.1.0-rc.14
curl -fsSL "https://github.com/kreuzhofer/tofa-launcher/releases/download/$version/install.sh" -o install.sh &&
  sh install.sh --version "$version"
```

Installs into `~/.local/share/tofa/bin`. Follow the printed PATH activation command
or open a new terminal. Bash, zsh and fish receive shell-specific instructions.

Use the same tag for the script download and `--version`. Prereleases must be
selected explicitly: the installer's default `latest` looks for a stable release
and does not select a prerelease. Add `--no-modify-path` for manual setup instructions.
Rerun the installer to upgrade; saved preferences and credentials are retained.

### Windows PowerShell

Requires Windows 10 version 1709 or later. The installer detects the native
AMD64 or ARM64 host, including when PowerShell runs under emulation.

```powershell
$Version = 'v0.1.0-rc.14'
$Installer = Invoke-RestMethod "https://github.com/kreuzhofer/tofa-launcher/releases/download/$Version/install.ps1" -ErrorAction Stop
& ([scriptblock]::Create($Installer)) -Version $Version
```

Installs into `%LOCALAPPDATA%\tofa\install\bin`. Follow the printed PowerShell PATH
activation command or open a new terminal.

Use the same tag for the script download and `-Version`; `latest` does not select
prereleases. Add `-NoModifyPath` for manual PATH setup.
Rerun the installer to upgrade; saved preferences and credentials are retained.

### First launch and upgrades

After installing and activating PATH:

```sh
tofa --version
tofa auth login
tofa launch codex --model 'moonshotai/Kimi-K3' --allow-unverified
```

`tofa --version` should print `tofa v0.1.0-rc.14`. Login is needed for first setup;
when upgrading, rerun the installer and reuse your saved login.

To exercise automatic approval review, select **Approve for me** in Codex's
`/permissions` menu. The launcher preserves the approval gate; it does not select a review
mode for you. See the [automatic-review limitations](#automatic-approval-review)
below before interpreting a timeout as a request-format failure.

<a id="download-from-the-private-repository"></a>

### Optional GitHub CLI downloads

If you prefer `gh`, the following commands download and verify release assets
before installation or standalone use. They require a configured GitHub CLI
(`gh auth login`); the direct installers above do not. GitHub authentication is
separate from `tofa auth login` for Token Factory. Keep the release pinned;
`latest` does not select a prerelease.

On macOS/Linux, download the complete bundle, verify it, then use the matching
installer with the downloaded assets:

```sh
version=v0.1.0-rc.14
release_dir=$(mktemp -d)
gh release download "$version" --repo kreuzhofer/tofa-launcher --dir "$release_dir" &&
  (cd "$release_dir" && shasum -a 256 -c SHA256SUMS) &&
  TOFA_RELEASE_BASE_URL="file://$release_dir" sh "$release_dir/install.sh" --version "$version"
```

On Windows amd64, download and verify the standalone executable, then launch it
directly. This path needs no installer or PATH changes. Keep `$Download` until you
are finished using this executable; replace `amd64` with `arm64` for Windows ARM64
(cross-build evidence only).

```powershell
$Version = 'v0.1.0-rc.14'
$Asset = "tofa_${Version}_windows_amd64.exe"
$Download = Join-Path $env:TEMP ([guid]::NewGuid().ToString('N'))
gh release download $Version --repo kreuzhofer/tofa-launcher --dir $Download --pattern $Asset --pattern SHA256SUMS
if ($LASTEXITCODE -ne 0) { throw 'Release download failed' }
$Lines = @(Select-String -Path (Join-Path $Download 'SHA256SUMS') -Pattern ('^[0-9a-f]{64}  ' + [regex]::Escape($Asset) + '$'))
if ($Lines.Count -ne 1) { throw 'Missing or ambiguous checksum' }
$Binary = Join-Path $Download $Asset
if ((Get-FileHash -LiteralPath $Binary -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Lines[0].Line.Split(' ')[0]) { throw 'Checksum mismatch' }
& $Binary --version
& $Binary auth login
& $Binary launch codex --model 'moonshotai/Kimi-K3' --allow-unverified
```

Both paths require an already installed Codex CLI. Release downloads and checksums
are verified separately from live Token Factory qualification.

### Building a distribution

```sh
sh scripts/build.sh v0.1.0-dev.1
```

An explicit version is required. A successful build replaces the generated
`dist/` directory with one complete distribution; old artifacts are removed.
A failed compilation leaves the previous distribution intact and exits with an
error. The directory contains:

- `tofa_TAG_darwin_amd64`, `tofa_TAG_darwin_arm64`, `tofa_TAG_linux_amd64`,
  `tofa_TAG_linux_arm64`, `tofa_TAG_windows_amd64.exe`, and `tofa_TAG_windows_arm64.exe`.
- Matching `install.sh`, `install.ps1`, `uninstall.sh`, and `uninstall.ps1`.
- `LICENSE` (project MIT license), `THIRD_PARTY_NOTICES.txt`, `LICENSE-GO.txt`,
  `PATENTS-GO.txt`, `LICENSE-CODEX.txt`, `NOTICE-CODEX.txt`, and this `README.md`.
- `SHA256SUMS`, covering every other file in the distribution.

Retain the license and notice files when redistributing standalone binaries.
The local build creates files only. Cross-compilation does not establish native
execution or real-machine qualification on every target.

### Publishing a prerelease

Push a new explicit prerelease tag such as `v0.1.0-rc.14` to the intended source
commit. Tags must use `vMAJOR.MINOR.PATCH-PRERELEASE`; stable tags and malformed
versions fail validation. Ordinary branch pushes and manual CI runs never publish.

The workflow builds one candidate bundle, then runs native race tests, vet and
actual-binary installation lifecycle checks on macOS, Linux and Windows. Every
required job must pass. Native jobs and publication download the same bundle;
publication never rebuilds the tested executables. Release CI uses synthetic state
and needs no real inference credential.

Publication uploads a private draft, downloads and compares every asset with the
checked bundle, verifies the tag still names the checked commit, then publishes it
explicitly as a prerelease. An existing release (including a partial draft) makes a
retry fail without overwriting assets or repointing the tag. Use a new candidate
version for changed release files; investigate an interrupted draft before taking
any manual recovery action. The publication job alone has `contents: write`.

All six OS/CPU artifacts have cross-build evidence. Native lifecycle execution
covers macOS ARM64, Linux amd64 and Windows amd64. Maintainer qualification with
real credential vaults and live Codex is recorded separately; native CI is not
real-machine acceptance. Apple signing/notarization and Windows publisher signing
are deferred, so record any platform prompts or blocks during qualification.

## Try the local build

Developers need Go 1.26 or newer. Users of a compiled artifact need no Go, Python,
Node or other language runtime **for tofa itself**. Codex retains its own requirements.

```sh
go build -o tofa ./cmd/tofa
./tofa --help
./tofa doctor
./tofa auth login
./tofa models
./tofa launch codex --model '<catalog-model-id>' --allow-unverified
```

On a fresh interactive launch, `tofa` announces first-use setup before the app
picker. The same setup runs for explicit `launch codex` and supported
`launch codex-desktop` commands. It asks for an API key (displayed as `*` while typing or pasting), followed
by the project ID, using the same vault-first storage flow as `auth login`.
After saving locally, onboarding checks the selected project’s remote catalog and
continues the original launch with its arguments intact. Saved credentials alone
do not establish successful authentication. A rejected catalog check stops setup;
use `tofa auth login` explicitly to replace incorrect credentials.

Existing logins skip setup. Locked or denied vault access, missing saved keys, and
malformed or interrupted storage require explicit recovery; they never trigger a
new login or a silent storage switch. Ctrl-C or EOF during credential entry stops
without saving credentials. Noninteractive launches never prompt: run
`tofa auth login` in a terminal first and supply `--model ID` when scripting.
Standalone `auth login` saves locally without testing remote authentication;
`models` checks the remote catalog. Launching Codex can incur inference charges.

Use `./tofa` for interactive selection, `--project-id ID` for a one-session override,
and `--` to pass Codex arguments. Routing flags such as `--config`, `--profile` and
`--model` cannot override tofa's provider via passthrough. Examples:

```sh
./tofa launch codex --model '<id>' --allow-unverified --project-id '<project>' -- --no-alt-screen
./tofa launch codex --model '<id>' --allow-unverified --direct
./tofa auth logout
```

In a terminal, `tofa` and `tofa --allow-unverified` show **Codex CLI** and
**Codex desktop**. Choose the app with Up/Down and Enter, then choose its main
model. Fresh setup and its catalog authentication happen before app selection;
with a saved login, catalog discovery happens after app selection;
Escape/Ctrl-C cancels either stage. Desktop requires the [minimum compatible macOS ARM64 app and engine](docs/codex-desktop.md#compatibility).

Explicit `tofa launch codex [OPTIONS]` and `tofa launch codex-desktop [OPTIONS]`
skip app selection. Omitting `--model` opens the shared model picker. Its screen
highlights the current model, with its exact ID, compatibility status and
Guardian below. Up/Down moves between ready models; Enter selects. Type to filter
by model name or provider, Backspace edits, and Ctrl-U clears the filter. Page
Up/Down and Home/End navigate longer lists.

Tab switches between **Ready** and **Unavailable** models, retaining your filter.
Unavailable models can be inspected but never launched. Press **?** for complete
model details and disabled reasons; arrows or Page Up/Down scroll long details.
Press **?** again to return. Escape or Ctrl-C cancels without starting the target
client or an adapter.

The picker resizes with your terminal, retains the highlighted choice and restores
the previous shell screen, cursor and terminal settings on exit. It requires at
least 40 columns and 18 rows; smaller terminals receive instructions to enlarge
the window or use an explicit `launch TARGET --model ID` command. `NO_COLOR=1` disables styling while retaining the
leading selection indicator. Guardian uses its default or explicit override
without another prompt.

Supported and experimental models appear together, labelled for the exact target,
route, Guardian and verified platform. On macOS ARM64, the adapted CLI pairs for
DeepSeek V4.1 Flash, GLM 5.3 and Kimi K3 with GLM 5.3 Flash Guardian are Supported.
Windows ARM64 supports the DeepSeek V4.1 Flash and Kimi K3 pairs with that Guardian.
Other CLI combinations remain Experimental. Choosing an experimental CLI entry asks for
confirmation: **Y** launches once, **N/Enter** returns to the list, and **Esc**
cancels. `--allow-unverified` skips this extra confirmation. Explicit or scripted
experimental CLI `--model ID` launches still require the flag. Desktop experimental
choices are enabled without extra confirmation and labelled Experimental. Entries without
compatible bundled metadata remain disabled with reasons. Empty catalogs,
failed discovery and unavailable Guardians stop the launch.

**Script migration:** use an explicit target and `--model ID`, for example
`tofa launch codex --model moonshotai/Kimi-K3 --allow-unverified`. An omitted model
in noninteractive use now fails with these instructions, even if `config.yml`
contains a saved `model`. Noninteractive bare launches with an explicit model
retain the existing Codex CLI behavior. Saved preferences never bypass the picker. Selection
does not change saved preferences or credentials; explicit `--model` bypasses the
model picker in both terminal and scripted use.

For the tested macOS desktop application, source builds offer:

```sh
./tofa launch codex-desktop
# Explicit selection also works without a terminal:
./tofa launch codex-desktop --model deepseek-ai/DeepSeek-V4.1-Flash
```

Quit Codex first. This launches ChatGPT desktop **Codex** with ordinary history
and profile state. Keep the terminal open; Ctrl-C stops that instance. Token Factory
history stays readable in ordinary mode; relaunch through tofa to continue it.
Desktop launches default to GLM-5.3-Flash Guardian; `--guardian-model ID` overrides
it. The picker marks **DeepSeek V4.1 Flash and GLM 5.3** with that Guardian
as supported when available. Their [five-model comparison](docs/evaluation/desktop-comparison-2026-09-29.md)
pins headless bundled-engine support to the tested macOS desktop configuration;
the [rc13 release report](docs/releases/v0.1.0-rc.13.md) records the Electron and
release qualification. Other eligible desktop
pairs are always enabled and marked Experimental. The launcher sets the default;
the desktop picker offers all eligible available models, and each conversation
keeps its own selected main across relaunches. The configured Guardian applies
to every Token Factory main. Automatic titles retain the captured Kimi launch-default
route; other mains report unsupported naming explicitly. See
[tested versions, lifecycle, and limitations](docs/codex-desktop.md).
The [shared-history qualification](docs/releases/desktop-shared-history-final-2026-09-24.md)
records passing live workflow, shutdown and preservation checks for the pinned
combination. That run did not observe automatic title generation. The subsequent
[#52 qualification](docs/research/desktop-shared-title-generation.md) demonstrates
a generated title and its preservation across ordinary/tofa relaunches. This
remains experimental.

The default route is announced before launch. Each launch binds its own
`127.0.0.1` port and gives Codex a random local bearer token through `TOFA_API_KEY`.
The saved Nebius key stays in the launcher, which forwards only to the fixed Token
Factory endpoint and selected project. The adapter accepts only `POST /responses`,
limits bodies to 16 MiB, streams responses, propagates cancellation and does not
retry requests or follow redirects. The launcher sets provider request/stream
retry limits to zero; Codex automatic review can still retry failed review
sessions and requests independently.
Unsupported routes and oversized or encoded requests fail explicitly.
The adapter supplies missing assistant-message `id`, `status` and output-text
`annotations` in conversation history, preserving existing values so Codex can
continue a conversation through Token Factory. Repaired IDs remain stable for
identical retries and appended turns; stored conversation history is unchanged.

For GLM 5.3, the adapter uses provider-managed thinking when Codex supplies
reasoning effort `none`: that value produces incorrectly classified reasoning
in the observed provider stream. A one-time terminal notice explains the change.
Other explicit effort settings and models remain unchanged. Reasoning, summaries,
answers and tool calls retain their native event channels; response text is never
stripped. Codex retains its normal controls for displaying raw reasoning.

For DeepSeek V4.1 Flash requests containing images, the adapter supplies
`max_output_tokens: 32768` only when that field is absent. Token Factory currently
fails these requests when the limit is omitted. This announced launcher default
covers reasoning and answer tokens combined; it is not a provider maximum or a
context-window limit. Explicit values, including null, remain unchanged, as do
text-only requests and other models. Provider incomplete/error responses remain
native and are not retried. See the [image-request diagnosis](docs/research/deepseek-image-output-limit-2026-10-01.md).

### Automatic approval review

For Kimi-K3, the adapter also handles the exact non-strict automatic approval
review format observed in Codex 0.155.1. Nebius rejects tools combined with
constrained JSON generation. When the request has the recognized decision schema,
`strict: false`, `tool_choice: auto`, and exactly the reviewer function tools
`exec_command`, `write_stdin`, and `view_image`, the adapter appends the complete
schema as a final-answer instruction and removes `text.format`. It preserves
existing instructions, approval policy, context, tool definitions/results, other
text options, and response bytes. This adaptation is announced once when used.
Other Kimi tools-plus-schema shapes fail locally, including strict schemas;
other models and requests without schema/tool conflicts retain their options,
including requests that explicitly disable tool calls with `tool_choice: none`.

Codex still parses the assessment and controls execution. Installed-client tests
show that valid allow decisions execute a harmless action, while deny, malformed
JSON, missing outcomes, invalid enums, upstream failures, and cancellation leave
it blocked. Optional assessment fields can be absent, as Codex's schema permits.
The adapter adds no retries or fallback decisions and does not change Codex policy.

On 2026-09-22, the maintainer confirmed that a new rc.2 test session built a working
app with **Approve for me**, including dependency installation and dev-server
startup without approval errors or manual intervention. This is a user-reported
live success; no request trace was enabled for that session.

Codex 0.155.1 still has a fixed 90-second total review deadline. In the earlier
live diagnostic, the adapted request reached HTTP 200 only after about 242
seconds, after Codex had already stopped waiting; no complete assessment was
observed in that diagnostic. The format adjustment does not extend that deadline
or resolve slow provider responses. Separate CLI platform qualification in #23
remains open.
See [the rc.2 evidence](docs/releases/v0.1.0-rc.2.md).

### Connection and client settings

`--direct` explicitly bypasses the adapter for diagnosis; this route passes the
Nebius key in the child environment and leaves history unchanged. Routes never
switch automatically. The child and its tools can read their environment; the
local token permits requests during that launch and is not an isolation boundary
against other software running under the same OS account.

The launcher supplies settings through child-process arguments and does not edit
Codex's configuration or login files. On exit it cancels active upstream requests
and closes its endpoint. Interrupts and adapter failures cancel the child; Unix
allows two seconds before killing an unresponsive child, while Windows terminates
the direct child immediately. Detached descendants are not guaranteed to terminate.
Existing Codex
skills, hooks and policy still apply. Web search is disabled for this unverified
provider. `doctor` is local only and does not read a key or trigger inference.

For the [five evaluation candidates](docs/evaluation/README.md#candidate-selection),
a launch-scoped catalog supplies each model's provider-advertised context and
input modalities, alongside the pinned Codex coding prompt. Optional Responses
reasoning effort, summary and verbosity controls are omitted until their contracts
are established. Catalog files are removed after launch; forced termination can
leave a `tofa-model-catalog-*.json` file in the OS temporary directory. Unknown
model IDs without bundled model-specific metadata now fail explicitly, even with
`--allow-unverified`. Both roles must appear in the current selected project's catalog.
The bundled metadata remains the dated 2026-09-23 snapshot; availability is refreshed
on every launch.

Adapted Codex CLI launches default to `zai-org/GLM-5.3-Flash` as Guardian, without a
second prompt. Override it explicitly when needed:

```sh
./tofa launch codex --model deepseek-ai/DeepSeek-V4.1-Flash --allow-unverified
./tofa launch codex --model moonshotai/Kimi-K3 --guardian-model moonshotai/Kimi-K3 --allow-unverified
```

An unavailable or incompatible main or Guardian is an error, including the default
Guardian. Nothing is substituted. The launcher displays the effective main,
Guardian, route and experimental status before starting the client. The diagnostic
`--direct` route preserves native reviewer selection, announces that exception and
rejects `--guardian-model` (including the retained internal
`--evaluation-guardian-model` alias). Passing both aliases is an error. Native
approval policies and routing-override protections still apply.

Support decisions use [recorded combination statuses](internal/tofa/assets/model-verification.json)
for the exact target, route, main/Guardian roles and recorded platform scope. The
[2026-10-02 CLI refresh](docs/evaluation/cli-refresh-2026-10-02.md) promotes DeepSeek
V4.1 Flash, GLM 5.3 and Kimi K3 with GLM 5.3 Flash Guardian on macOS ARM64. The
[2026-10-05 Windows continuation](docs/evaluation/cli-windows-2026-10-05.md) also
qualifies DeepSeek and Kimi on Windows ARM64 after saved login was supplied.
GLM 5.3 remains Experimental on Windows; GLM Flash and Nemotron remain
Experimental as mains on both platforms. Other
combinations require interactive experimental consent or explicit
`--allow-unverified`. Changing a role, route or platform does not inherit support.
Recorded client versions are measured baselines; newer versions are accepted until
a breaking change is found. Historical campaign evidence remains unchanged.
Evaluation tools retain their explicit same-model default and the internal flag.
The desktop picker uses desktop evidence; CLI qualification never becomes desktop
support by inference. See the [universal picker contract](docs/model-picker.md)
for future target integrations.
See [the metadata research](https://github.com/kreuzhofer/tofa-launcher/blob/03d47a502c09debc36a2072c3aa3a929beb6c38d/docs/research/kimi-provider-metadata.md)
for the provider snapshot and remaining gaps.

## Credentials and preferences

- macOS/Linux: `$XDG_CONFIG_HOME/tofa/config.yml`, default `~/.config/tofa/config.yml`.
  An XDG override must be absolute. macOS deliberately uses the same CLI convention.
- Windows: `%LOCALAPPDATA%\tofa\config.yml`.
- Fresh logins prefer macOS Keychain, Windows Credential Manager, or Linux Secret
  Service. A read-only lookup of a fresh probe reference checks availability; it
  does not save a test credential. The vault may request access or unlocking.
- Automatic file storage is selected only when the vault facility is confirmed
  absent or unsupported (for example, D-Bus reports no Secret Service, the macOS
  keychain helper is missing, or the keyring library does not support the platform).
  Before requesting the key, the launcher announces the choice, the path to
  `credentials.yml` beside configuration, and that the key is **unencrypted**.
  Private Unix modes / Windows ACLs restrict access; they do not encrypt the key.
- Locked vaults, denied access, uncertain availability, and failed operations are
  errors. A missing or broken Linux session bus does not prove Secret Service is
  absent; restore the bus/store or explicitly use `tofa auth login --storage file`.
  A Linux vault also needs a usable login collection.
- Re-login reuses the saved backend unless `--storage keyring` or `--storage file`
  overrides it. Explicit keyring selection fails if the vault is unavailable and
  never falls back to files. Normal launches use the saved backend without probing
  availability or migrating credentials as the environment changes.
- `auth logout` removes saved local keys and retains preferences. It does not revoke
  your Nebius API key. Failed native-store cleanup retains recovery references.

Configuration is strict, versioned YAML. Example after logout:

```yaml
version: 1
project_id: your-project-id
model: optional-preferred-model-id
```

`keyring-refs/` contains nonsecret recovery identifiers so an interrupted login can
be cleaned up. Do not delete it before logout/purge. Concurrent auth changes are
rejected using `.auth-lock`. If a process was forcibly terminated, ensure no other
auth operation is running, then remove that **empty** lock directory and retry.

## Review and validation

Read [the Go walkthrough](docs/prototype/REVIEW.md) and
[the evidence and limitations](docs/prototype/VALIDATION.md).

```sh
go test -race ./...
go vet ./...
sh scripts/build.sh v0.0.0-prototype
python3 scripts/build_test.py
python3 scripts/release_test.py -v
python3 scripts/install_test.py
# Native macOS/Linux lifecycle against the bundle built above:
python3 scripts/lifecycle_test.py dist v0.0.0-prototype -v
# Unix only, against a compiled local binary:
python3 scripts/terminal_test.py ./tofa
python3 scripts/picker_test.py -v
# Optional: installed Codex, scratch config, synthetic local responses only:
TOFA_TEST_CODEX="$(command -v codex)" go test ./internal/tofa -run TestInstalledCodex -v
# Unix only, offline validation of the live-test harness:
python3 scripts/live_compat_test.py
# Unix only, offline validation of the request-tracing harness:
python3 scripts/trace_codex_test.py -v
# Mac-side Windows template preparation, with controlled external UTM fixtures:
python3 scripts/windows_template_test.py -v
```

Python is a **development test tool**, not a runtime or installer dependency.

For dedicated Windows 11 ARM64 UTM test templates, see
[template preparation and native readiness](docs/testing/windows-template.md).
The picker checks compile the public launcher with a loopback provider and a fake
Codex process, then send actual keys through a pseudo-terminal. They verify the
upstream model identity, route/Guardian support filtering using test-only records,
blocked entries, cancellation, errors, terminal restoration and unchanged saved
credentials. These checks have run locally on macOS ARM64 and are wired into
macOS/Linux CI; Linux execution still needs a CI result. Windows console/ConPTY
key handling and restoration have no native picker coverage yet. Cross-building
does not establish that coverage, and these offline fixtures do not qualify live
Codex/model combinations.
`TestDesktopPicker` runs the same PTY driver through the executable desktop
boundary on the gated macOS version. With `TOFA_TEST_DESKTOP_ENGINE` set, it also
checks selected main/Guardian routing and actual approval allow/deny execution
through the installed engine and a loopback provider. It uses temporary native
history, settings and credentials; it does not start the installed Electron UI.
The build tests require Go and run on macOS/Linux. They inspect all six targets'
embedded versions and build metadata, execute the native binary, verify every
checksum and bundled notice, and install from a controlled local release source.
The native lifecycle checks install the actual candidate using its bundled script
and check fresh interactive zsh (macOS) or bash (Linux) discovery, version/help,
repeated installation, CLI uninstall, reinstall and explicit purge. They also
verify that corrupt downloads and failed cleanup report errors, retain retryable
state, and preserve unrelated files. These checks run in the native CI jobs;
fish startup and other shell modes remain outside this coverage.
Run `./scripts/windows_test.ps1` in native Windows PowerShell for the offline
installer and recovery-script tests. Its `-InstallerOnly` switch checks downloads
and checksum rejection without running the Windows recovery script.
Windows CI also builds the versioned bundle and runs
`./scripts/windows_lifecycle_test.ps1 -Dist dist -Version v0.0.0-ci` against the
actual executable through its matching installer. It checks persistent user PATH
and fresh-process discovery, repeated install, real asynchronous CLI uninstall,
retained-state reinstall and purge. It waits for helper completion with a deadline
and checks cleanup results; launcher exit alone is not success. Failed purge,
helper cancellation, timeout and corrupt downloads must remain observable.
This check is restricted to disposable GitHub Actions Windows runners because it
temporarily changes user PATH. It restores PATH and removes its synthetic state
in `finally`, stops outstanding helpers, and never changes execution policy.
The tests use synthetic credentials, temporary directories and local HTTP servers.
They never contact Token Factory or access native credential stores. The workflow
also tests on native runners; test results must be checked before claiming coverage.

For the complete pinned macOS and Windows prerelease lifecycle, including interactive login,
saved-login reuse and sanitized local reports, see the
[local qualification runners for macOS and Windows](docs/releases/qualification.md). Their offline tests
use synthetic releases and clients. Windows qualification tests use uniquely named
synthetic vault entries only on disposable CI runners; maintainer results remain separate.

For opt-in real inference using saved credentials, see the
[live compatibility harness](docs/prototype/LIVE-COMPATIBILITY.md). It runs three
isolated Kimi sessions and records streaming, tools, checked file changes and
continuation evidence. Live runs are separate from the offline commands above.

For separate coding/protocol scores, controlled automatic-review allow/deny cases,
and a dated five-model candidate selection, use the bounded
[model evaluation workflow](docs/evaluation/README.md). Reports do not change the
launcher's supported-model policy. The [2026-09-23 final comparison](docs/evaluation/selected-pairs-2026-09-23.md)
links all five individual evaluations, selected-pair qualification and campaign cost totals.

For opt-in request diagnosis, see [Codex request tracing](docs/codex-tracing.md).
The standalone harness records sanitized request metadata, status and timing;
the released executable has no `--debug` flag. Traces must be enabled for a new
run and cannot reconstruct earlier conversations.

Design decisions: [Wayfinder map](https://github.com/kreuzhofer/tofa-launcher/issues/1).
Dependencies and reuse: [third-party notices](docs/prototype/THIRD_PARTY.md).

## Uninstallation

Uninstall preserves saved preferences and credentials by default. It removes only
tofa's installation and owned PATH changes; Codex and unrelated files are retained.
If unrelated files keep the install directory nonempty, ordinary
uninstall retains its ownership marker so a later install can reuse that directory.
Explicit purge removes that marker as well. To reinstall after purge, select an
empty install directory or move the unrelated files out of the old one first.

For the experimental macOS desktop integration, quit the desktop and any launcher
before upgrading or removing tofa. Uninstall and purge retain verified, detached
engine bridges and inactive provider metadata so saved references and shared history
remain readable. They retain no live launch access. See the [desktop lifecycle and
recovery contract](docs/codex-desktop.md#installed-lifecycle-and-retained-history).

### Using the CLI

For an installed copy:

```sh
tofa uninstall
```

To also remove saved preferences and credentials, use `tofa uninstall --purge`
instead. Windows starts a helper that waits for tofa to exit; watch its output for
the completion result or cleanup errors.

### macOS and Linux recovery script

This works even if the installed binary is broken:

```sh
version=v0.1.0-rc.14 # use the installed version, shown by tofa --version
curl -fsSL "https://github.com/kreuzhofer/tofa-launcher/releases/download/$version/uninstall.sh" -o uninstall.sh &&
  sh uninstall.sh
```

To also remove saved preferences and credentials, run `sh uninstall.sh --purge`.
Linux native-store cleanup needs `secret-tool`; if it or the service is unavailable,
the script retains recovery references and reports incomplete cleanup.

### Windows PowerShell recovery script

This works even if the installed binary is broken:

```powershell
$Version = 'v0.1.0-rc.14' # use the installed version, shown by tofa --version
$Uninstaller = Invoke-RestMethod "https://github.com/kreuzhofer/tofa-launcher/releases/download/$Version/uninstall.ps1" -ErrorAction Stop
& ([scriptblock]::Create($Uninstaller))
```

Append `-Purge` to also remove saved preferences and credentials. Failed native-store
cleanup is reported rather than treated as successful deletion.
