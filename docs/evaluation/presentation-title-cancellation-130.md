# Title cancellation and evaluator-owned Desktop shutdown

Status: evaluator correction passes local regressions; review, native requalification and any new
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
