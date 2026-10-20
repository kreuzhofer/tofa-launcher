# Native service routing contract (#136)

This implementation is a qualification candidate behind `--native-account-candidate`.
The ordinary-profile preservation guard remains active. Fixture results establish
public launcher / bundled-engine behavior using synthetic credentials and owned
upstreams; they do not establish signed-in inference or actual Desktop labels,
plugin lifecycle, native previews, or release eligibility.

## Selection and destination

The authenticated native catalog and available eligible Token Factory catalog
are resolved once per launch. Conflicting/duplicate identities fail before
handoff. The resulting immutable map uses explicit `native` / `token_factory`
service identities, not model-name prefixes or a process-wide latest selection.
Catalog display names identify ChatGPT or Token Factory. Existing Token Factory
support/Experimental metadata is retained; availability is not certification of
this candidate route. Native capability and reviewer descriptors are unchanged.
Native account entries without a display name use their exact model identity as
the display label. Rendered labels require the later actual-Desktop gate.

A new `tofa-native-router` conversation follows explicit per-thread selection;
its ID, recorded provider and history remain intact across services. Subsequent
requests carry the context required by the selected model. A pending request
keeps its original destination; another conversation cannot change it. Errors
never select a different model or service. Existing `openai` conversations stay
direct-native; existing `nebius-tofa` bearer-only histories cannot enter the native
branch merely by selecting a GPT name.

## Admitted native transport

The native destination is fixed at
`https://chatgpt.com/backend-api/codex/responses`. There is no CLI, environment or
provider-supplied override. The existing injected HTTP transport is used only by
owned fixture tests to map that exact URL to a loopback server.

The engine provider disables WebSockets. Native inference admits streaming HTTP
Responses with explicit full input history. `previous_response_id`, `conversation`
and remote `prompt` references are refused. Main request metadata has absent or
`turn` request kind, absent or `user` source, and absent or `composer` trigger.
Unknown auxiliary roles, compaction and native reviews without originating-work
provenance fail explicitly. Strict existing title classification stays separate;
review provenance and final naming qualification belong to #138/#139.

Input items admit messages, function/custom calls and their outputs, reasoning,
and additional tools. Message roles admit user/assistant/developer/system. Unknown
roles/types and duplicate top-level or input-item keys are rejected before
forwarding. Routing metadata also rejects duplicate fields. Native request bytes,
namespace tools, media, reasoning, saved history and successful stream events are
forwarded intact before any Token Factory repair or transformation runs.

Only native Authorization, ChatGPT-Account-Id and the explicitly admitted native
protocol headers cross the native upstream boundary: OpenAI-Beta, Originator,
Session-Id, Thread-Id, User-Agent, X-Client-Request-Id, X-Codex-Turn-State,
X-Codex-Turn-Metadata, X-Codex-Beta-Features, X-Codex-Window-Id and
X-Openai-Internal-Codex-Responses-Lite. Duplicated or oversized protocol header
values are refused.
Cookies, arbitrary headers and the local launch capability do not. Token Factory
continues rebuilding its own credentials/project query and does not receive
native auth/account headers. Local launch authorization remains independent of
native credentials and control authorization.

Redirects are refused without following their targets. Native HTTP error bodies
and headers are replaced with bounded status-class diagnostics, preventing echoed
account credentials from reaching engine logs. Network errors are generic and do
not include URLs or credentials. Successful model output remains native payload;
this is not a general content-redaction claim.

## Evaluation limits

The optional observer `model_services` declaration admits a bounded explicit set
of model/service pairs. Existing single-model evaluations remain strict. Native
payloads and parallel-tool settings are not rewritten into Token Factory controls.
Time, requests and bytes remain bounded. An explicit native output-token request
must fit the declared budget; absent that field, output enforcement uses reported
response usage and is not an upstream hard cap. Missing/over-limit native usage
stops the run. The actual qualification declaration must disclose this distinction.

The #136 fixture covers Kimi → GPT → Kimi with prior context, native custom-tool
continuation and image retention, streamed deltas, concurrent threads, selection
during a pending native request, explicit cancellation, unavailable models,
credential separation, ambiguous input, unknown roles, redirects and error echoes.
The authoritative test command and results are recorded in the integration handoff.
