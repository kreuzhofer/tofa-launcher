# Independent desktop naming: implementation evidence for #111

Status: live provider/engine naming and operator-confirmed Mac UI acceptance passed.
Release qualification and publication are separate from this development check.
This is development work for [#111](https://github.com/kreuzhofer/tofa-launcher/issues/111),
not functionality shipped in rc16. Historical Kimi qualification does not qualify
Lightning or GLM chat naming.

## Fixed naming role

Recognized desktop title requests route to exactly
`nvidia/Nemotron-3_5-Lightning`, independently of the main and Guardian. Missing
project availability fails naming explicitly while main conversation requests
remain usable. There is no model fallback or naming picker. The desktop retains
its native title schema, validation, deadline, persistence and manual-title guard.
Live testing found that Lightning rejects the captured namespace tools and native
`include`, `reasoning`, and `prompt_cache_key` fields. The naming route now omits
these fields, retains the prompt and native schema, and announces tool-free naming
with provider-default reasoning. Main and Guardian tools remain unchanged.

The dedicated [metadata snapshot](../../internal/tofa/assets/desktop-naming.json)
records the exact entry from the unauthenticated Token Factory
[`models_info` endpoint](https://tokenfactory.nebius.com/api/public/models_info),
including source hash and retrieval date. Its `responses_api` and
`function_calling` flags justify testing this candidate; they do not prove that
the provider accepts the actual namespace tools together with structured output.
The authenticated project catalog was checked and contains the exact Lightning ID.

## Current installed contract

Read-only inspection on 2026-10-09 found desktop version `26.930.51102`, build
`13100`, bundle `com.openai.codex`, at `/Applications/ChatGPT.app`. The bundled
engine at `Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex` reports
`0.160.0`. Exact engine/archive/member hashes are in
[the source manifest](evidence/independent-desktop-naming-2026-10-09-source.json).

Only packaged JavaScript was extracted, without execution. No account state,
conversation history, remote service configuration or credentials were read.
Locators below are searchable identifiers in minified first-party bundle members:

| Member | Locators and source findings |
| --- | --- |
| `.vite/build/main-C7cfj__D.js` | `ThreadMetadataGenerationService`, `async generateTitle`: chooses the service-configured `ephemeralGenerationModel`; no user naming-model parameter. Errors log and return null. |
| `.vite/build/bootstrap-CXJAEjVI.js` | `VJ`, `GJ`, `ZB`: `thread_title`, low effort, ephemeral thread, provider null, provider model fallback enabled, approval policy never, read-only permissions and empty workspace roots. `ZB` forwards the feature as the turn trigger. |
| Same bootstrap member | `kJ=3e4`, `NJ`, `PJ`: native 30-second title timeout and structured title/description schema; title length 1–36, nonempty description. The client validates the response and normalizes the title. |
| `webview/assets/app-shared-9d148924be0b.js` | `zKr`, `VKr`, `HKr`, `expectedProvisionalTitle`: computes a provisional first-message title, calls title generation and replaces it with an `expectedTitle` guard. Failure retains/persists the provisional title. Existing unrelated titles skip generation. |

These are static source findings, not proof of a successful UI session. The
service's current remote model value was not fetched. The adapter recognizes the
captured `gpt-5.6-luna` and `gpt-6-luna` contracts and rejects changed contracts.
Native catalog descriptors are preserved; naming is routed at the request boundary.

## Observed tests

- Red: a GLM 5.3 launch rejected a captured naming request with HTTP 400 and no
  provider call. Green: all five existing main selections route that request to
  Lightning, preserving the native schema.
- Red: missing Lightning availability initially still reached the provider.
  Green: it now returns an explicit naming error with no fallback; an ordinary
  GLM request still succeeds.
- Targeted request/response and role-separation tests passed, including malformed
  responses, changed contracts, upstream errors, concurrent main streaming and
  cancellation. A 500 ms caller deadline cancels upstream; this does not establish
  success within the native UI's 30-second deadline.
- Installed-engine replay passed for both captured Luna IDs with GLM as the launch
  main (`TestDesktopBundledEngineRoutesAutomaticTitleToLightning`, 6.87 seconds).
  It used a synthetic profile and local provider, not the Electron UI or paid
  inference.
- Independent Standards and Spec reviews of `5b3ab33` found no actionable defects.
  The Spec reviewer independently passed targeted offline tests in 42.247 seconds.
- `go vet ./...` and `git diff --check` passed. The first full race run exposed an
  obsolete picker expectation for the former unsupported-naming notice. That
  assertion was updated; final full-suite outcome is recorded in the issue/PR.

## Live provider and engine results

The unmodified branch received provider HTTP 400 before generation. Isolated
probes removed one demonstrated incompatibility at a time: `include`, then
`reasoning`, then `prompt_cache_key`; the next error was `Unsupported Responses
tool type namespace`. Removing the captured tools while retaining the schema
produced a valid title. This justified the explicit tool-free naming policy.
No production fallback, automatic retry, schema removal or change to main/Guardian
requests was introduced.

The public-launcher regression first failed with HTTP 400 for `include`, then
passed after the scoped adaptation. Targeted offline regressions and installed-engine
replay passed in 39.826 seconds. With the current app's complete naming prompt,
both native contracts then generated **Explain Python integer addition** using
Lightning. End-to-end fixture times were 13.506 seconds for `gpt-5.6-luna` and
8.603 seconds for `gpt-6-luna`, including setup, under the native 30-second limit.
[Sanitized live results and usage](evidence/independent-desktop-naming-2026-10-09-live.json)
record the model identities, title, descriptions and response IDs. Those requests
used synthetic prompts and isolated engine profiles. They establish provider/engine
compatibility, not actual UI acceptance. The observer buffered each provider response
before feeding it to the engine; streaming UI behavior is not established by this check.

## Actual Mac UI acceptance

The maintainer explicitly authorized saved-login reuse on 2026-10-09 with no
request-count restriction. The login was reused in memory without modification.
Computer Use refused control of `com.openai.codex`; the maintainer operated the UI
and reported the observations directly. A temporary diagnostic launcher called
the production `App` with a streaming HTTP observer that recorded only routing,
usage and generated synthetic titles, not credentials or ordinary answer text.
The same pinned app and engine used the ordinary profile; no application patch,
ownership bypass or forced termination was used.

1. With GLM 5.3 main and GLM 5.3 Flash Guardian, the synthetic integer-addition
   conversation completed its main request in 5.600 seconds. Lightning generated
   **Explain Python integer addition** in 28.245 seconds. The operator initially
   reported the provisional first-message title, then confirmed the generated
   title appeared. Only the latter observation is counted as success.
2. A new conversation selected DeepSeek V4.1 Flash in the desktop picker while
   the launch default remained GLM. Main used DeepSeek and completed in 5.374
   seconds; naming still used Lightning and generated **Explain cache timeout**
   in 6.258 seconds. The operator confirmed that exact title.
3. The operator quit normally; the observed launcher exited with status 0. The
   production candidate `dev-111-d492de9` relaunched the ordinary profile without
   the diagnostic observer. The operator confirmed both generated titles persisted.
4. The operator renamed the Python chat to **Manual naming check 111**, sent a
   follow-up, and confirmed the manual title remained unchanged.

[Sanitized UI evidence](evidence/independent-desktop-naming-2026-10-09-ui.json)
records routing, provider request/response IDs, reported usage, binary identities
and operator confirmations. The main/Guardian security and tool-routing checks
remain covered by the unchanged public-boundary regression suite; no new live
Guardian tool action was needed for these no-tools synthetic prompts.

The corrected implementation passed targeted regressions (39.826 seconds),
`go test -race ./...` (internal/tofa 303.405 seconds; scripts 2.212 seconds),
`go vet ./...`, and independent Standards and Spec follow-up reviews. CI results
are linked from PR #112.

Limitations: the first observed title took nearly the full native 30-second
budget. These two UI successes do not establish a latency/reliability guarantee;
the provisional title remains visible until generation completes, and timeout or
provider failure can leave it in place. No deadline increase, response truncation,
retry or alternate-model fallback was introduced. Native non-title auxiliary
operations remain unsupported; the production relaunch/manual-rename sequence
also logged an unsupported-model rejection, whose exact auxiliary source was not
captured. App-backed title lookup remains unqualified. rc16 is unchanged; shipping
requires a new release candidate and affected release qualification. Windows
desktop remains outside this scope.
