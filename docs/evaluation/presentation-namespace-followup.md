# Implementation scope: preserve native tools through flat provider schemas

Part of #119; diagnosis evidence in #129. Implementation is retained at `deb5ac9`;
live synthetic provider checks pass. Native qualification remains a separate gate.

## Problem and evidence

Actual native Kimi K3 and GLM 5.3 conversations advertised the presentation loader
but neither model invoked it. The native synthetic control invoked it successfully.
Controlled replay preserves the tool inventory through the existing adapter.

A four-request headless provider comparison then held the prompt and function
definition constant, changing only whether the function was namespace-wrapped or
flat. Both flat cases returned the correct function call with `{}`. Neither
namespace case returned a function call, despite HTTP 200 and completed Responses.
The provider's internal handling is unobserved; these outcomes demonstrate a
compatibility gap for the tested combinations, not a missing native runtime.
See [sanitized evidence](evidence/presentation-runtime-126-127/provider-namespace-diagnostic.json).

## Smallest useful change

Add reversible tool-name/schema translation at the existing optional request
adapter boundary for the demonstrated model/provider combinations. Present native
namespaced function definitions as flat provider functions, and restore the native
namespace/name on returned calls. Apply the same mapping to replayed call history.
Keep the client's native tool catalog and approval enforcement intact.

## Acceptance criteria

- Write a failing adapter-boundary regression using a controlled upstream that
  accepts flat functions and does not select namespace-wrapped functions. Verify
  the returned call reaches the client under its original namespace and name.
- Use deterministic, collision-safe aliases. Test duplicate leaf names across
  namespaces, collisions with existing flat functions, and provider name limits.
  Do not derive executable behavior from model-supplied names or arguments.
- Preserve call IDs, arguments, tool outputs, ordering, and model identity across
  a complete call/result/follow-up round trip. Translate all relevant streamed
  output-item events and final response envelopes consistently.
- Preserve ordinary flat tools and independent naming/Guardian routing. Test mixed
  catalogs and unknown/unsupported tool definitions; fail explicitly rather than
  dropping tools or executing an unmapped response. Scope behavior to demonstrated
  compatibility needs and leave direct connections unchanged.
- Run affected adapter/stream/history tests with the race detector. Review against
  the originating spec and repository standards before qualifying the candidate.
- Retain the existing production binary and evidence. A new binary changes the
  retained bridge identity: revalidate affected lifecycle/preservation contracts
  before native qualification, without restoring settings snapshots.
- Predeclare a fresh bounded native Kimi/GLM loader check on the reviewed candidate.
  Require the actual loader call/result and returned executable version checks.
  Preserve failures and score naming separately. Only then resume deck comparisons
  once #128 also has a disposition.

## Exclusions and limits

No prompt-only claim that the tool exists, fake loader, dependency installation,
application patch, fabricated native transport, dropped tool catalog, or automatic
tool execution in the headless probe. No changes to ordinary skills/settings or
the established two-field retained-MCP exception. This ticket does not resolve
naming, qualify arbitrary models, or complete the full #119 release campaign.

The four provider observations are one sample per model/format; they justify the
focused regression and adapter experiment, not a reliability estimate. A provider
fix could eventually make this translation unnecessary.
