# Independent desktop naming: implementation evidence for #111

Status: offline implementation verified; live provider and Mac UI acceptance pending.
This is development work for [#111](https://github.com/kreuzhofer/tofa-launcher/issues/111),
not functionality shipped in rc16. Historical Kimi qualification does not qualify
Lightning or GLM chat naming.

## Fixed naming role

Recognized desktop title requests route to exactly
`nvidia/Nemotron-3_5-Lightning`, independently of the main and Guardian. Missing
project availability fails naming explicitly while main conversation requests
remain usable. There is no model fallback or naming picker. The desktop retains
its native title schema, validation, deadline, persistence and manual-title guard.
The launcher relocates the captured tool definitions without altering them.

The dedicated [metadata snapshot](../../internal/tofa/assets/desktop-naming.json)
records the exact entry from the unauthenticated Token Factory
[`models_info` endpoint](https://tokenfactory.nebius.com/api/public/models_info),
including source hash and retrieval date. Its `responses_api` and
`function_calling` flags justify testing this candidate; they do not prove that
the provider accepts the actual namespace tools together with structured output.
Authenticated project availability has not been checked in this campaign.

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
  Lightning, preserving schema and tool definitions.
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

## Remaining live acceptance

AGENTS.md requires asking before authenticated testing. Existing evaluation
fixtures use synthetic credentials; they do not authorize reuse of the saved
Token Factory login. Prepare a temporary candidate from this branch, then with
explicit authorization:

1. Reuse the saved login only in memory and check exact project availability.
   Apply a shared maximum of 12 paid requests and record sanitized model routing,
   durations, output validation and usage. Do not log tokens or private prompts.
2. First check the captured Lightning title request against the real provider,
   including its existing tools and structured output. Stop on incompatibility;
   do not introduce an unobserved fallback or remove the schema speculatively.
3. Coordinate a normal desktop quit/relaunch with the operator. Never bypass
   native profile ownership or terminate their unrelated running session.
4. Start a fresh synthetic GLM conversation. Observe a useful generated title
   distinct from the first message in the sidebar; confirm persistence after
   relaunch. Repeat with a different main and check main/Guardian routing.
5. Rename a synthetic conversation manually and verify the generated title cannot
   overwrite it. Preserve existing history/settings and leave the normal login
   unchanged. Record actual app/engine/launcher versions and sanitized evidence.

Keep #111 open until these checks pass. A new release candidate and affected Mac
qualification are required before shipping. Windows desktop is outside this scope.
