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
unobserved previews cannot produce a pass. The maintainer deferred this step.
There is no actual Desktop loader/artifact/preview qualification evidence yet;
its implicit and explicit model calibrations also remain pending.

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
