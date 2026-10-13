# Retained MCP bridge lifecycle verification

The maintainer authorized verification of a narrower preservation requirement:
the two host-written MCP executable references may point to a verified retained
bridge. Other protected settings remain unchanged. This replaces the need for
zero persistent executable-reference changes in this verification; it does not
automatically qualify #127 or change its existing evidence validator.

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
loader call. The existing strict preservation validator remains unchanged.

Before resuming presentation qualification, encode the exact two-field exception
with bridge ownership/lifetime checks in the evaluator, and use the retained
fixture for native runs. Then complete the native loader/deck/preview and model
calibration gates. Keep the integration branch unmerged until those pass.
