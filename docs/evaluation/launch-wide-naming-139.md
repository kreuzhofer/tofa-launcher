# Launch-wide automatic naming (#139)

Desktop launches use the existing configured naming model,
`nvidia/Nemotron-3_5-Lightning`, for every recognized automatic title during a
TOFA launch. This includes native GPT title-generation context. Startup states
that destination explicitly on both legacy and candidate routes; no additional per-title prompt or naming option is
introduced. Main and Guardian remain independent of this naming choice.

The actual bundled-engine fixture replays Desktop's measured title helper:
a separate ephemeral Luna thread with `modelProvider: null`, source
`thread_title`, and turn trigger `thread_title`. Its provider is the launch's
`tofa-native-router` default. It does not supply the parent conversation identity.
The adapter does not infer that identity from text, timing, workspace, or the
latest selected Main. Saved native `openai` conversations keep their direct native
Main connection even while their separate title helper uses TOFA naming.

## Recognition and failures

The title route retains both source markers, the captured Luna model identity,
exact structured title schema, and exact additional-tool inventory. A matching
model name alone never selects naming. Conflicting subagent roles, compaction,
and unknown request kinds are refused. The observed title request kind may be
absent or `turn`. The existing tool-free transformation retains the title prompt
and schema; no new naming fallback or retry is added.

The configured naming model must remain available in the launch catalog with
compatible dedicated metadata. Missing availability is announced and title
requests fail explicitly while Main remains usable. Provider failure and client
cancellation retain their existing independent error paths. Desktop validates,
persists, and displays the title; an engine reply alone is not a UI visibility
or manual-title-preservation proof.

## Fixture evidence and remaining qualification

Public-launch tests drive the installed bundled engine against owned local
upstreams using synthetic credentials and disposable profiles. The four-category
matrix also uses the actual Python observer and Go adapter:

- New routed Token Factory and native conversations receive TOFA titles.
- Saved native and legacy conversations resume in a new engine process with
  unchanged provider, identity, and history; both receive TOFA titles.
- Direct native Main and routed native Main reach distinct owned native fixtures;
  naming reaches only Token Factory with its own credential. Native account and
  launch-capability headers are absent from the naming upstream.
- Native Main and actual automatic TF Guardian remain pending while naming
  completes or fails with HTTP 503. Main work then completes, the denied command
  does not execute, and no naming retry or service/model substitution occurs.
- Changed-title, missing-model, provider-error, cancellation, Guardian, and saved
  native-history regressions remain required.

The fixture's direct-native server rejects unsupported WebSocket upgrades and
serves HTTP Responses, matching the repository's existing direct-history tests.
This is an owned test endpoint, not a production native-endpoint override.

The ordinary-profile preservation guard remains active. Actual renderer helper
invocation, generated-title visibility, manual-title protection, signed-in native
inference, and plugin/account lifecycle remain later #142/#143 qualification.
