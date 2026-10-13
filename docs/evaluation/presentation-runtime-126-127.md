# Presentation runtime integration (#126 / #127)

The implementation remains on `feat/126-127-presentation-runtime`, based on
`2c8df02`. The maintainer chose to retain an integration branch until qualification
is complete. Neither ticket is closed or merged into the main branch.

## Implemented CLI lane

The optional evaluation observer configuration can register the launcher-owned
`tofa_presentation_runtime` STDIO MCP server for one CLI process. Its only tool,
`load_workspace_dependencies`, takes an empty object and reads the existing
format-2 Darwin/arm64 bundle. It does not install, update, fetch or execute commands.
The launcher checks existing MCP registrations and refuses a provider-name
conflict before credentials or inference. Its public routing-override filter is
unchanged. Ordinary Codex home, skills and plugins remain in use.

The actual CLI advertises a namespace named `mcp__tofa_presentation_runtime`,
containing the function `load_workspace_dependencies`. Its qualified name is
`mcp__tofa_presentation_runtime__load_workspace_dependencies`. Current CLI wraps
the successful structured MCP output in a textual executor envelope. The private
archive retains that unedited output and the subsequent actual request pairing
the loader call with its result; qualification parses and verifies the contents.

`--presentation-qualification` accepts retained actual-client evidence rather
than a tool-presence switch. The evaluator and observer independently validate
the client identity, owning provider/schema/call, bundle metadata, returned paths,
executable/package hashes, observed executable versions, harness identity,
protected-file preservation, artifacts and finalization receipt. A changed
environment or invalid live loader result remains infrastructure-blocked.
Unqualified CLI and Desktop combinations retain #122's original gate.

The [sanitized CLI evidence](evidence/presentation-runtime-126-127/cli-synthetic.json)
records the exact client and dependency versions, hashes and artifact checks.
The current combination is CLI 0.162.1 on macOS arm64, Presentations and dependency
bundle 26.1011.11113, Node v24.19.0, Python 3.12.14 and artifact-tool 2.8.93.
This is an added runtime-provider treatment, distinct from stock CLI behavior.

A real CLI call created an editable one-slide PPTX, passed the installed
finalizer's package/import/font checks, rendered a PNG and delivered PPTX/PDF
references. Artifact-tool's PDF export failed to resolve
`#standard-fonts/Helvetica`; that attempt remains retained. The declared PDF route
uses the bundle's `soffice` wrapper and its native LibreOffice executable, with
an owned `UserInstallation` profile. No package was installed or changed.
The wrapper reports LibreOfficeDev 26.8.0.0.alpha0; the manifest separately
declares `25.2-headless-codex.1`. These observations are recorded separately.
The Poppler wrappers and their native executables also stay inside the bundle.

## Separate model calibrations

One implicit-discovery case 03 and one explicit-skill case 04 were declared before
execution, with unchanged v3 prompts, fresh workspaces/conversations, Kimi K3 main,
GLM 5.3 Flash Guardian and 900-second/80-request/8192-output-token ceilings.
They are excluded from the original #119 matrix and repeated comparisons.
The [independent assessment](evidence/presentation-runtime-126-127/cli-model-calibrations.json)
preserves their outcomes and source identities; later harness checks do not
rewrite them or make their older qualification files reusable after drift.

Case 03 stopped at `unsupported_request_contract / guardian` after 38 forwarded
main requests; no Guardian inference was forwarded. This is the existing native
review contract block documented in #123. Case 04 exhausted its 80 main requests.
Both read installed presentation instructions, but neither invoked the advertised
loader or delivered a deck. Settings stayed preserved, and neither reported
environment drift. These runs do not establish reliable model skill use,
presentation quality, language reliability or supported-model status.

## Desktop qualification remains pending

The calibration command has a separate native Desktop path. It launches the actual
ChatGPT application with its bundled engine and normal local host. It supplies
no CLI MCP override, pipe identity or fabricated thread metadata. The native
provider must advertise and successfully handle
`mcp__codex_app__load_workspace_dependencies`; effective readiness is observed
through that call. Local asset checks alone do not qualify the host.

The prepared [operator handoff](../../scripts/presentation_operator.sh) checks
assets, waits for human readiness, starts one bounded synthetic attempt, prints
its fresh workspace/prompt and records a separately attributed native preview
observation. It requires both exact delivered files and hashes. Missing or
unobserved previews cannot produce a pass.

The maintainer subsequently authorized Codex computer use while away. A bounded
native attempt launched the actual application, but the computer-use tool refused
access to `com.openai.codex` for safety reasons. The
[retained attempt](evidence/presentation-runtime-126-127/native-computer-use.json)
made zero model requests, produced no artifacts and observed no previews. The
owned evaluator was cancelled and the application inventory confirmed it stopped.
The observation recorder now attributes `computer_use` separately from human
review; this attempt contains no preview pass.

The attempt also detected protected-state drift: the before/after file counts
were both 27,451, but content fingerprints differed. Modification-time candidates
include `config.toml`, the computer-use plugin's `.mcp.json`, and twelve remote
plugin installation metadata files. These candidates do not establish an exact
content diff. No shared snapshot was restored. Earlier qualification files fail
the current gate after this drift. There is still no successful native Desktop
loader/artifact/preview qualification; its model calibrations remain blocked.

The 2026-10-13 [manual attempt](evidence/presentation-runtime-126-127/native-manual.json)
reached the actual Desktop conversation but failed with
`required_actual_client_loader_missing`. Both the raw and adapted main-request
catalogs contained 238 tools and no native loader. No artifact or preview existed;
the synthetic attempt used no paid inference. The native host log records
`missing-code-signing-identity` peer rejections followed by
`Codex app tools pipe closed` during `codex_app` startup. This localizes the failure
to native tool startup; the exact rejected peer executable is not established.
Both installed Node candidates pass read-only signature verification outside the
agent sandbox. Initial sandboxed failures do not establish damaged installations.

This attempt also failed protected-state preservation. A separate per-file hash
comparison against the earlier manual baseline found changes to `config.toml` and
the unified-computer-use plugin's `.mcp.json`, with no baseline files missing.
That comparison does not establish changed content or causation and does not
check added files. No shared snapshot was restored. Next diagnosis needs helper
executable/parent provenance during startup and a controlled ordinary-versus-launcher
comparison, retaining native peer authorization. Repeating the same deck prompt
cannot qualify this combination while native tool startup remains blocked.

A subsequent [startup comparison](evidence/presentation-runtime-126-127/native-startup-comparison.json)
localized the incompatibility to launcher process ancestry. In ordinary startup,
bundled Node runs under the bundled engine directly under Desktop: three native
`codex_app` ready events, no startup failure or peer rejection. Under the launcher,
the ad-hoc-signed settings bridge remains between Desktop and the engine: seven
peer rejections, one native startup failure, no ready event. Both attempts used
30-second startup traces without submitting a prompt. The installed native
component examines peer, parent and grandparent signing identities. No native
authorization behavior was modified.

The correction in `3cc3487` replaces the original Desktop child process with
the bundled engine. A separate child relay retains the existing model-default
filter, protocol forwarding and main-engine acknowledgement. The signed native
ancestry is now Desktop → bundled engine → bundled Node. Native authorization
is unchanged. The [post-change verification](evidence/presentation-runtime-126-127/native-relay.json)
records native `codex_app` readiness, zero peer rejections and no leftover fixture
credential stores with the final build. A separate repeat failed the existing
15-second ordinary-engine preflight before Desktop launched; that failed attempt
remains retained and its cause is not established.

Regression tests failed before the fixes for engine ancestry, inherited temporary
directories and fixture credential stores orphaned by `exec`; all passed afterward.
The installed-engine settings and lifecycle checks passed with race detection,
as did the full Go race suite, `go vet`, and 16 affected Python tests including a
fresh actual CLI deck run. Independent standards and spec reviews found no new
implementation defects. These checks establish the process-layout fix, not full
native presentation qualification.

Native preservation remains blocked. The subsequent
[settings diagnosis](presentation-native-settings-diagnosis.md) reproduces the
two writes with exact installed functions and identifies the Desktop command
selection/reconciliation boundary required for a fix. No supported launcher-only
separation was found in the inspected build; the preservation repro remains red.
A semantic before/after comparison identified
two host-written fields: `mcp_servers.node_repl.env.CODEX_CLI_PATH` in `config.toml`
and `mcpServers.cua_repl.env.CODEX_CLI_PATH` in the unified-computer-use plugin's
`.mcp.json`. Desktop persists the temporary evaluation bridge into both. Ordinary
startup also rewrites these fields. The qualification gate still rejects drift;
no shared snapshot is restored and no preservation exception was added. Resolving
this launch-integration issue precedes native loader/deck/preview qualification
and the separately declared model calibrations. Subsequent Desktop drift also
invalidates reuse of the otherwise successful fresh CLI proof.

The calibration harness now scopes `TMPDIR`, `TMP`, and `TEMP` to a private `tmp`
directory inside its run. The fixture dispatches saved engine references directly,
avoiding a new synthetic credential store whose deferred cleanup would be lost
on `exec`. Three leftover stores from the initial relay prototype were removed;
all final-build fixture stores were cleaned up normally. Historical run evidence
was retained. A final ordinary Desktop startup reconciled both stored MCP executable
references back to the existing bundled engine. Both paths were verified afterward;
this cleanup does not retroactively satisfy the failed preservation gate.

All new presentation validation material uses the fixed root
`/tmp/tofa-presentation-validation`. The manual wizard creates a fresh owned
subdirectory under `runs/` for each attempt and ignores the inherited `TMPDIR`.
Launcher shortcuts, baseline snapshots and the legacy-location inventory belong
under this root too. On macOS, `/tmp` and `/private/tmp` name the same directory.
Historical evidence remains at its recorded locations until an explicit retention
decision; moving those files would invalidate qualification records bound to their
original absolute paths.

Run from an interactive Terminal when ready, using already-built local assets:

```sh
bash scripts/presentation_operator.sh \
  --launcher /absolute/path/to/evaluation-fixture-launcher \
  --codex /Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex \
  --app-bundle /Applications/ChatGPT.app \
  --runtime-root "$HOME/.cache/codex-runtimes/codex-primary-runtime" \
  --skill "$HOME/.codex/plugins/cache/openai-primary-runtime/presentations/26.1011.11113/skills/presentations"
```

The fixture launcher is built from `scripts/fixtures/evaluation_launcher` and uses
synthetic credentials and loopback inference. It is separate from the production
launcher used for the declared model calibrations. Raw requests, client logs,
responses, credential comparisons and native operator records stay outside Git.
Only owned processes/resources are stopped; shared snapshots are never restored.

## Verification and completion gate

Behavioral tests cover the launch overlay, provider conflicts, malformed/missing
metadata, wrong-host/outside paths, native-result completeness, package identity,
tool identity, failed live results, malformed evidence and cancellation preservation.
The [verification record](evidence/presentation-runtime-126-127/validation.json)
records actual commands and limitations.

The full Go race suite passed with the repository's documented
`GORACE=atexit_sleep_ms=0` setting. The earlier default-delay run and baseline
shutdown reproduction remain retained. Race detection and production ownership
deadlines are unchanged. The full Python suite passed, with real-client/UI opt-ins
disabled; the opt-in actual CLI checks ran separately.

The [two-axis review](evidence/presentation-runtime-126-127/review.md) found no
remaining implementation defects after the fixes. The final metadata boundary
tests and refreshed actual CLI proof passed after the full suite.

Remaining gates are the actual native Desktop call/workflow and human previews,
its two fresh model calibrations and final qualification. The
broader #119 matrix, approval/resume qualification, guidance adoption, releases,
Windows and supported-model promotion remain outside these runtime tickets.
