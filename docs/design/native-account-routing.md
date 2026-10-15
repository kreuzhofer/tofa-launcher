# Desktop native-account routing design interview

Work in progress, started 2026-10-15. Related: #133 prototype and #130 evaluation.
The maintainer confirmed shared understanding after round 3 and authorized the
next local engine experiment. This records design decisions and evidence, not
production implementation approval or Desktop qualification. The existing launch
guard remains active.

## Evidence

The [Ollama investigation](../research/ollama-desktop-provider-routing-2026-10-14.md)
and [#133 result](https://github.com/kreuzhofer/tofa-launcher/blob/b0d9fd7/internal/tofa/prototypes/native-provider/RESULT.md)
establish engine account preservation and synthetic outbound credential separation.
They do not establish actual thread routing, inbound authorization, Desktop plugin
lifecycle, or presentation previews.

## Settled constraints

- Existing shared settings, credentials, skills and conversation history must be
  preserved. Desktop defaults remain process-scoped; no shared snapshot restore.
- ADR 0002 retains native approval enforcement and explicit Guardian failures.
- ADR 0003 describes the current provider-bound conversation behavior. Round 2
  deliberately revised the desired behavior for new conversations under the
  proposed route: explicit model selection may switch inference services while
  retaining identity/history. See [ADR 0006](../adr/0006-explicit-model-selection-may-switch-inference-service.md).
  This is a product decision, not proof of technical feasibility or authorization
  to migrate existing conversations automatically.
- Round 1: the user accepted an existing, verifiable ChatGPT sign-in as the first
  version's prerequisite, with a prelaunch stop otherwise. See
  [ADR 0005](../adr/0005-native-account-routing-requires-chatgpt-sign-in.md).
- Round 3: the user accepted a clear destination service alongside the model
  choice, without another confirmation dialog. Review/title requests follow the
  service of the work that triggered them; already-running requests retain their
  original routing. See ADR 0006. Actual UI support and request provenance remain
  evidence requirements, not assumed client capabilities.

## Decision tree

1. Account scope — settled: existing ChatGPT sign-in only.
2. Conversation routing contract — desired behavior settled: explicit selection
   may switch inference services in new conversations, with no silent fallback.
   Existing conversations must retain identity and history.
   - Depends on this decision: new-thread provider assignment, resumed-thread
     compatibility, behavior on ordinary launches, and model-picker errors.
   - Settled product choices: destination service is clear at model selection,
     without a repeated confirmation; supporting requests follow the originating
     work's service and are unaffected by later selections.
3. Native/Token Factory request separation — engine main switching and review
   selection/provenance passed a synthetic fixture. Native automatic title
   requests omit the parent conversation; service-specific naming remains blocked
   at that boundary. Unsupported auxiliaries cannot silently change service.
4. Local request authorization — delivery of a secret URL path passed, but its
   diagnostic exposure leaves production authorization unresolved. Retain a proven
   launch-specific access boundary and isolate launch/evaluation control endpoints.
   Loopback binding or an arbitrary bearer header alone is insufficient.
5. Qualification and release — guard stays active until separately qualified;
   detailed lifecycle and release criteria remain to be specified after routing
   contracts and technical prerequisites are settled.

## Code findings to carry into the spec

- The current bridge supplies app-server overrides but does not assign providers
  through `thread/start`. A native-provider default alone would change the normal
  provider identity of new Token Factory model conversations.
- Existing `nebius-tofa` conversations have an inactive provider entry that gives
  an actionable relaunch error outside TOFA. Preserve this compatibility contract.
- The adapter currently authenticates inference and control endpoints using a
  per-launch bearer. The prototype did not implement inbound authorization.
- Native requests currently bypass the Token Factory adapter. Its Luna-title
  recognition must not be applied globally to native conversation titles.

## Feasibility findings after round 3

- `desktop_catalog_darwin_test.go` already exercises one engine thread switching
  Kimi to GPT and back. GPT currently fails under the recorded `nebius-tofa`
  provider. This fixture is a useful basis for a built-in-provider routing probe;
  it is not evidence of successful cross-service inference.
- Token Factory model metadata supplies a Guardian override while native model
  descriptors are retained. This is a candidate for correct review selection,
  pending actual mixed-service request observations.
- The native title fixture starts a separate ephemeral Luna thread. Its recorded
  shape does not establish a link to the parent conversation's service. The
  accepted title policy therefore needs a proven correlation mechanism; guessing
  from the latest main selection would misroute concurrent or delayed requests.
- A launch-specific secret URL path or additional header could authenticate the
  inference route independently of native credentials. Actual bundled-engine
  delivery has not been tested. Control endpoints retain independent protection.

## Completed bounded evidence step

The [#133 follow-up result](https://github.com/kreuzhofer/tofa-launcher/blob/7037b05/internal/tofa/prototypes/native-provider/THREAD-RESULT.md)
records five retained local attempts. The final bundled-engine run passed 12 scoped
checks with 16 requests to loopback fixture upstreams. New-thread Kimi → GPT → Kimi
switching preserved identity and passed context to the next selected service.
Both new and legacy fixture threads resumed without provider migration. Guardian
requests followed the selected main's metadata and included parent-thread/turn
linkage; denied commands did not execute. Review switches were between completed
turns, not while review was pending.

This used fake API-key auth in disposable state, not a real signed-in inference
turn. It did not launch Desktop or call external inference. The earlier real
ChatGPT account preservation proof remains separate. Temporary artifacts stay
under `/tmp/tofa-presentation-validation`; only sanitized summaries were published.

The installed engine rejects `model_providers.openai.http_headers` because built-in
provider IDs are reserved. Secret-path delivery works but URL-bearing engine
diagnostics require an explicit production treatment. Production control endpoints
and the Go adapter were not qualified by this Python fixture.

Native-source inspection confirms the title caller omits parent identity even
though the generic helper supports it. The replay's metadata likewise lacks it.
Catalog display names/descriptions provide an existing service-label mechanism;
actual rendered labels still require qualification.

## Reopened decision and remaining evidence

The maintainer was asked whether to choose a launch-wide TOFA naming model, native
naming for all titles, or retain service-specific naming pending another supported
boundary. That answer is pending; the agreed service-specific policy has not been
silently replaced. Each launch-wide option changes where some title-generation
context goes and therefore requires an explicit choice.

Still needed: production launch authorization and diagnostic treatment, pending
review switch behavior, ordinary-launch behavior of new mixed-service histories,
actual signed-in inference transport and native Desktop lifecycle/preview
qualification. Keep these as explicit acceptance work in the implementation spec.

If a mechanism cannot meet the agreed behavior, return with the concrete evidence
and the affected product choice. Do not silently narrow the behavior or claim
qualification. The complete implementation spec remains pending those findings.
