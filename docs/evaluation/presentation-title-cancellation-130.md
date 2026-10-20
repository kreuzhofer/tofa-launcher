# Title cancellation and evaluator-owned Desktop shutdown

Status: evaluator correction passes local regressions and both reviews; native requalification and any new
model attempt remain pending. No release or model-support claim.

## Retained native outcome

The first selected-model comparison attempt, run
`393df9ac3043419da1ac5142a437f19b`, ended with `cancelled/client_disconnected`.
Four main Kimi requests completed without a final answer. One additional main
request and the independent title request were interrupted. No workspace files
were produced. Protected settings were preserved, with no catalog or runtime
drift. The remaining three predeclared cells did not start.

The actual Desktop process log records its title service timing out at
`2026-10-14T10:32:55.887Z`: “Timed out waiting for structured result.”
The evaluator's stop record was written at `10:32:55.901649Z`, followed by
macOS reporting the Desktop process exit at `10:32:55.907Z`. The launcher logged
`context canceled`. No matching ChatGPT crash report was found in the user or
system DiagnosticReports directories. Raw logs and captures stay private.

This sequence strongly supports title cancellation triggering evaluator shutdown.
The historical observer did not record which request first disconnected, so the
native request identity is inferred from the timing and reproduced mechanism;
it is not recovered directly from the original trace. The reason the naming
request failed to finish before Desktop's timeout remains unknown.

## Reproduction and correction

An unattended local HTTP reproduction starts concurrent title and main requests,
then closes only the title connection. On `d4e5d08`, the observer sets the global
`client_disconnected` reason and cancels main work. The regression fails in under
one second. The launcher then closes its owned Desktop when the evaluator stops,
which explains why this defect can look like an application crash.

The observer now cancels only the upstream request for an interrupted title,
records its failure and a value-free disconnect source/time, and lets the main
turn continue under the same limits. Cancellation before or after title response
headers is covered. Main/Guardian disconnects, explicit cancellation and the
fixed deadline retain their run-wide stop behavior. No retry, substitution,
additional request authorization, settings change or launcher modification is
introduced. The cancelled request still consumes its budget.

A completed main answer does not hide naming failure. The command-level regression
retains successful main completion and failed title cancellation independently,
while the aggregate result remains `infra_blocked`. The existing campaign gate
therefore stops after observations for inspection rather than advancing silently.

## Qualification and handoff

The prior native proof and amended predeclaration remain historical. Changing the
observer/evaluator invalidates their recorded harness identity; none of their
hashes or outcomes are rewritten. The stable comparison wrapper now stops with a
short explanation; its previous bytes are archived under the fixed temporary
root. Before another model comparison, qualify the corrected native harness,
record fresh human PPTX/PDF previews, and explicitly predeclare any further retry.
The 10-minute qualification and 15-minute comparison limits remain unchanged.

Validation: all 57 observer/evaluator tests pass. Related runtime, operator,
preservation and proxy suites ran 56 tests: 54 passed, two explicit installed-runtime
opt-ins skipped. No native launch or provider request was made for this diagnosis.
See [the sanitized evidence](evidence/presentation-runtime-126-127/title-cancellation-130.json).

The original reproduction also passes unchanged against the corrected harness.
Standards and Spec reviews of `d4e5d08...472bba0` each reported zero findings.

## Installed Desktop update interrupted requalification

Fresh synthetic run `5ed46b9a46c54449be418077461a592a` recorded passed human
PPTX/PDF previews and preserved protected settings, but failed qualification with
`native_application_drift`. The installed app changed during the run from build
20156 / version26.1007.30912 to build20398 / version26.1007.71326. The bundled
engine and native tool transport hashes were unchanged; the app executable and
resources changed. The original proof remains unqualified and unmodified.

An ordinary startup initialized the new bundled-plugin cache. Its archived
snapshot helper referenced the removed old plugin path, so that bootstrap
diagnostic is incomplete and receives no qualification credit. The helper was
corrected to discover the current version. A subsequent clean-launch check found
a protected-state change beyond the two permitted MCP references: the enabled
`code-review@openai-bundled` entry disappeared and the plugin cache changed.
The native startup log explicitly records the app requesting and completing its
uninstall because it is no longer in the bundled marketplace. Launcher settings
and credentials remained unchanged. Remaining lifecycle checks were stopped.

See [the retained update assessment](evidence/presentation-runtime-126-127/desktop-update-20398.json).
The maintainer accepted the updated app/plugin set as a new qualification baseline.
Fresh clean exit, forced launcher crash and repeat launch preserved protected files
byte-for-byte. Node and CUA MCP arithmetic passed after clean exit and crash.
All 11 preservation/operator regression tests passed.

Ordinary Desktop restart then restored `code-review@openai-bundled` and its enabled
setting. Protected file count rose from 27,442 to 27,451. The two permitted MCP
references also changed back to the bundled engine, but plugin restoration is
outside that exception. Launcher settings and credentials remained unchanged.
Remaining lifecycle checks stopped; no new qualification was issued.

This is a recurring launch-path difference, not just a one-time app migration.
Native logs advertise nine bundled plugins during adapted startup and ten,
including `code-review`, during ordinary startup. A read-only bundled-engine
`account/read` check reports a ChatGPT account for ordinary routing and no account
for an otherwise identical provider configuration with `requires_openai_auth=false`.
Refresh was disabled and no provider request was made. Replaying the exact installed
eligibility and uninstall functions with mock IO reproduces the mechanism: with
other eligibility inputs allowed, non-ChatGPT authentication excludes the plugin,
and reconciliation requests its uninstall. Native renderer feature values were
not directly intercepted, so the causal account-state link combines logs, engine
observations and the isolated replay.

See [the new preservation diagnosis](evidence/presentation-runtime-126-127/desktop-plugin-preservation-20398.json).
The manual smoke wrapper now exits before launch with this explanation; its prior
bytes and all historical results remain retained. No app modification, settings
snapshot restore, credential change or eligibility override was made. The native
restart left the plugin installed. Reaccepting another baseline would conceal
the alternating behavior rather than qualify preservation.

The next implementation needs to preserve installed bundled plugins when provider
authentication changes, while leaving their native authentication/eligibility
checks intact. First establish a supported launcher-side preservation boundary or
an editable native reconciliation implementation. Add a failing test for the
ordinary → adapted → ordinary transition, then a minimal correction and complete
lifecycle/native qualification. If no preservation boundary is available, fail
before launching a session that would remove the installed plugin. Do not widen
the two-reference exception or silently isolate/restore the user's profile.

Native qualification and subsequent comparison remain blocked on that correction;
the title-cancellation fix and its regression evidence remain intact.
