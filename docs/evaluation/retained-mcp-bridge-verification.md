# Retained MCP bridge lifecycle verification

The maintainer authorized verification of a narrower preservation requirement:
the two host-written MCP executable references may point to a verified retained
bridge. Other protected settings remain unchanged. This replaces the need for
zero persistent executable-reference changes in this verification; it does not
automatically qualify #127. The subsequently authorized evaluator exception is described below.

## Results

Verified against installed ChatGPT 26.1007.30912 (20156), bundled engine
0.162.0-alpha.17.2, and standalone CLI 0.162.1. Baseline: `2212cc1`, with the
evaluation-fixture retention change. See the
[sanitized evidence](evidence/presentation-runtime-126-127/retained-mcp-lifecycle.json).

| Check | Observation |
| --- | --- |
| Clean launcher cancellation | Bridge remained installed; both saved MCP definitions initialized and executed arithmetic before ordinary Desktop reconciliation. Synthetic credential removed. |
| Abrupt launcher death | Killed only the owned launcher with SIGKILL; no launcher defer could run. After closing its surviving owned Desktop, both MCP servers initialized and executed arithmetic. Protected-state fingerprint was unchanged. |
| Owned test uninstall/purge | Removed the test installation and synthetic credential, retained and detached the bridge, and preserved shared state. Bridge executed the actual bundled engine successfully; both MCP arithmetic calls still passed. |
| Clean repeat at retained path | Complete raw protected-state fingerprint unchanged. |
| Ordinary Desktop restart | Three native `codex_app` ready events, zero observed failed events or missing-signature rejections. Desktop reconciled both executable references to its bundled engine. Protected state matched after normalizing only the two allowed fields. |
| Ordinary engine configuration | Read-only `config/read` through the retained bridge matched direct bundled-engine configuration exactly, without a Token Factory launch context. |
| Standalone CLI | Read the saved Node MCP configuration successfully after test uninstall. A real ephemeral CLI turn invoked Node MCP arithmetic successfully using the retained bridge in session-only configuration and a synthetic loopback provider. |

The bridge is retained at
`/tmp/tofa-presentation-validation/retained-install/config/tofa/desktop-bridge-v2/…/tofa-desktop-engine`.
All newly created verification material stays under the agreed fixed root.
No installed app was patched, re-signed, updated, or reinstalled. No shared
configuration snapshot was restored. Uninstall targeted only the owned test
installation, never the maintainer's launcher installation.

The current two MCP references were rechecked after all probes: both point to
the existing bundled engine. The protected-state fingerprint still matched the
ordinary restart's final capture. The retained helper remains available for later
verification and the manual launcher wrapper now selects the retained fixture.

## Fixture correction and checks

The old evaluation fixture deleted its entire temporary store, including a bridge
that Desktop could persist in MCP configuration. `FIXTURE_RETAINED_DIR` now
explicitly selects a retained fixture store. It must be absolute, private, and a
real directory; an existing store must have the matching private ownership
marker. Unowned, public, or symlinked paths are rejected. A clean fixture exit
removes its synthetic credential while retaining the bridge. Abrupt death can
leave that synthetic credential until subsequent owned cleanup; uninstall/purge
removed it in this run. Ordinary fixture invocations still use temporary stores.

The public fixture-command retention regression failed before implementation and
passed afterward. The fixture race tests passed, including refusal cases and
saved-bridge dispatch. Existing clean-exit, crash-recovery, interrupted replacement,
and uninstall race tests passed. Installed-engine tests passed for CLI default
isolation, rejection of partial/stale default writes, and history after removal.
`go vet` passed for the changed fixture. The full repository suite was not repeated
for this fixture-only implementation change.

## Evidence limits

Direct MCP arithmetic also succeeds with a nonexistent engine path. Those calls
prove that saved definitions remain loadable and execute simple REPL code; they
do not by themselves exercise the engine reference. The real CLI success and
direct bridge engine/configuration checks provide separate evidence.

The missing-path real CLI control was inconclusive: automatic approval review
returned invalid JSON, so the action was not executed. No approval policy was
changed or bypassed. An earlier attempt to send a session `-c` flag through the
launcher was rejected by its routing-flag guard; the successful CLI probe used
the standalone client's supported configuration interface directly. These failed
diagnostic attempts remain retained and are not counted as passes.

No real browser/OS action was requested from computer use. No native presentation
loader call, deck generation, preview, or model calibration was performed. The
startup-only calibration runs correctly remain unqualified with no observed
loader call. The lifecycle record is historical evidence, not a presentation pass.

## Authorized evaluator exception

`presentation_calibration.py --retained-mcp-bridge /absolute/path/to/tofa-desktop-engine`
now opts the Desktop lane into a narrowly bound preservation policy. The bridge
must already exist, be private and executable, match its versioned owner record,
and match the binary hash in the completed lifecycle evidence. The record must
include clean exit, crash, uninstall, ordinary restart, real CLI and ordinary
engine checks for the same Desktop version/build and tested engine/native hashes. The policy binds the engine
hash, native application identity, exact bridge path/hash and evidence hash.
A changed or missing bridge, engine, owner or evidence fails revalidation. The
policy never installs a bridge or repairs settings.

Only `mcp_servers.node_repl.env.CODEX_CLI_PATH` in `config.toml` and
`mcpServers.cua_repl.env.CODEX_CLI_PATH` in the exact versioned computer-use
plugin `.mcp.json` can switch between the bundled engine and that bridge. Both
files are compared as parsed settings with just those leaves normalized;
formatting changes in those two files are consequently immaterial. Every other
setting in them remains compared, and every other protected file keeps its byte
hash. Missing leaves/files, duplicate JSON keys and any other executable path
are rejected. Raw and normalized preservation fingerprints are retained.

The exception is Desktop-only and opt-in; ordinary CLI and non-presentation
checks remain strict. Qualification reuse and the live observer revalidate the
policy. Live evaluation inherits it only from fully qualified presentation
evidence, preserves raw config diagnostics, and still blocks all other drift.
A different launcher bridge requires its own matching lifecycle evidence and
fresh qualification; a synthetic fixture proof cannot silently authorize it.

Regression tests ran red before implementation for the preservation interface,
calibration command, live evaluator boundary and duplicate-key rejection. The
54-test evaluator/observer run passed, as did the 12 runtime tests (two installed
CLI opt-ins skipped there) and the two separately enabled real CLI tests. The
latter created fresh PPTX/PDF/PNG artifacts through the installed loader and
exercised qualification/observer tamper rejection. Additional bridge ownership
and incomplete-evidence refusal checks passed. No Go implementation changed in
this follow-up; the existing lifecycle race evidence remains applicable.

The fixed manual wrapper now selects Python 3.12, the retained fixture store and
the exact verified bridge. Its installed Desktop asset preflight passes. The
native loader, deck, two previews and separate model calibrations still need to
pass before merge or issue closure. Computer use's prior refusal to control
ChatGPT Desktop remains respected; the wrapper requests a human observation.

Independent review found two preservation defects in the initial exception:
a TOML date could alias a literal table, and new policy creation did not compare
the engine/native hashes with historical lifecycle evidence. Both received
failing regressions and fixes. Canonical settings now tag every value type; the
lifecycle record includes identical engine/native identities extracted from all
three retained launcher captures (clean, crash, clean repeat), with source hashes.
Those captures remain startup-only, unqualified presentation attempts. Ten scoped
policy tests pass after the fixes. Native acceptance remains pending.

The final affected suite ran 69 tests (two installed-client opt-ins skipped),
and both installed CLI opt-ins passed separately against the corrected harness.
The fresh CLI evidence is qualified with settings preserved and PPTX/PDF/PNG
artifacts. Final Desktop asset preflight passes. Independent re-review reports
zero remaining Standards findings and zero remaining Spec implementation findings.
See the [sanitized follow-up record](evidence/presentation-runtime-126-127/retained-mcp-evaluator.json).
Native acceptance is still pending, so neither ticket is closed or merged.

The subsequent [native manual run](evidence/presentation-runtime-126-127/native-success.json)
now passes loader, artifact, preservation and human PPTX/PDF preview qualification,
including independent proof revalidation. This qualifies the exact retained
fixture bridge; native model calibrations and the production route remain pending.
