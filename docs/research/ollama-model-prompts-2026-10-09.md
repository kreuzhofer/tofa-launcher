# Ollama model prompts and Codex compatibility levers

Research date: 2026-10-09. Requested alongside the capability evaluation prototype [#117](https://github.com/kreuzhofer/tofa-launcher/issues/117). This updates the prompt-related evidence in [the earlier launcher investigation](ollama-launchers.md); it does not replace that report's dated findings.

## Finding

Ollama does adapt Codex for other models, but the public implementation is **not a collection of bespoke agent system prompts for GLM, Kimi and DeepSeek**. The visible levers span catalog instruction selection, capability metadata, reasoning controls, message history, tool schemas, and protocol translation. Desktop borrows instructions from the native Codex catalog; CLI supplies an empty base-instruction field. Model-specific local renderers provide another, lower layer of formatting. [CLI catalog builder][cli], [Desktop catalog builder][desktop], [renderer registry][renderers].

There is an important visibility limit: ordinary explicit-cloud Responses requests are forwarded to Ollama's cloud before the local Responses-to-chat converter. The public client therefore does **not** establish the final prompts, renderers, inference settings, or additional adaptations deployed for cloud Kimi K3 or DeepSeek V4.1 Flash. The exception for requests containing web search uses local orchestration. We should borrow testable interface ideas, not assume source parity with their hosted service. [Route ordering][routes], [cloud passthrough][cloud].

## Evidence boundary and versions

- Main inspected source: public release **v0.40.2**, commit **`b061384d90ff455462bc32745dd0de479de717a3`**, matching the previously reported installed version. GitHub reports publication on 2026-10-08 at 16:53:47 UTC. All Ollama source links below pin this commit. [Release](https://github.com/ollama/ollama/releases/tag/v0.40.2).
- Main was **`c2b7368d4156656ddb9a23b43f721a841b9c23e0`** when inspected. Its single change beyond the release adds CLI `service_tier="default"`, with a test allowing an explicit later override. It adds no prompt policy. Do not attribute that setting to installed v0.40.2. [Pinned comparison](https://github.com/ollama/ollama/compare/b061384d90ff455462bc32745dd0de479de717a3...c2b7368d4156656ddb9a23b43f721a841b9c23e0).
- Public, unauthenticated model-recommendation metadata was fetched on this date. The response SHA-256 was `3d988432050d4377d19d7d541e449a1bc6eca468d5a6bc5b5d0df89d99ba78db`. Selected exact values appear below; the endpoint is mutable and is not a release-pinned artifact. [First-party endpoint][recommendations].
- Codex catalog compatibility was read at **rust-v0.162.0**, the CLI version in our pilot. This is not proof of identical behavior in the bundled Desktop engine. [Codex catalog deserialization][codex-models].
- Read-only public source/API investigation. No Ollama startup, model inference, native UI control, credential access, or user configuration writes. Upstream tests were inspected, not executed. No model-quality or end-to-end compatibility pass is claimed.

## What is public, and where instructions enter

| Layer | Public implementation | Consequence for our investigation |
| --- | --- | --- |
| CLI agent instructions | Catalog builder assigns `base_instructions` an empty string and does not supply model-specific behavioral prose. | Do not describe this as an elaborate Ollama coding prompt. |
| Desktop agent instructions | First nonempty native catalog base instructions, then cache/default fallback; narrow identity replacement; skills/plugins/apps flags enabled. | Compare the complete effective client input, including catalog flags, rather than one instruction paragraph. |
| Responses/chat compatibility | Message, tool, reasoning and streaming conversion is public. | Useful fixtures for preserving contracts; cloud-path applicability must be checked. |
| Local inference serialization | Named renderer/parser implementations and template support are public. | These control training-specific role/tool tokens, not merely agent tone. |
| Cloud final prompt/inference | Client forwards requests; exact hosted processing is not exposed by the inspected repository. | Unknown, not evidence of either no adaptation or a secret universal prompt. |

Sources: [CLI][cli], [Desktop][desktop], [Responses converter][responses], [renderers][renderers], [local prompt selection][local-prompt], [cloud boundary][cloud].

For CLI, Codex 0.162.0 promotes a present legacy `base_instructions` value into `model_messages.instructions_template` when the latter is absent; that code does not reject an empty string. This establishes catalog ingestion, **not** the absence of other client, permission, project or skill messages. A rendered-input capture is still the acceptance check. [Codex deserializer, lines 904–935][codex-models].

Desktop builds an entry with `model_messages: null`, skill/plugin/app instruction flags true, unified execution, and search/parallel-tool support derived from tool capability. The text comes from native catalog/cache data, not a versioned prompt in Ollama's repository. Only two legacy GPT-5 identity phrases receive replacement; a newer identity string can remain unchanged. Consequently a pinned Ollama binary alone does not pin the effective Desktop prompt. [Desktop catalog/instruction helpers, lines 1380–1480][desktop].

## Model-specific selection and exact pilot generations

The launcher combines per-run inventory, recommendation thinking descriptors and, for Codex, a bounded model-show lookup whose valid thinking descriptor takes precedence. Desktop falls back to family-based controls only when explicit metadata is unavailable. `glm5_next` and `glm_dsa_moe` share low/high/max with default max; name resemblance alone is insufficient. Other thinking-capable models without a richer descriptor receive a binary fallback. These are source policies, not verified Token Factory capabilities. [Model resolution][resolution], [thinking contract][thinking].

Public recommendation snapshot:

| Exact Ollama identifier | Advertised thinking values | Default | Evidence limit |
| --- | --- | --- | --- |
| `kimi-k3:cloud` | false, low, high, max | max | Exact generation is listed; final cloud renderer/prompt remains unknown. |
| `deepseek-v4.1-flash:cloud` | false, low, high, max | high | Exact generation is listed; not DeepSeek V3.1 or V4 Flash. |
| `glm-5.3-flash:cloud` | low, high, max | max | This is Flash, not the pilot main GLM 5.3. |
| `glm-5.3:cloud` | Not present in this recommendation response | Unknown from this response | Source tests cover GLM 5.3 with `glm_dsa_moe`; recommendation absence is not model unavailability. |

The snapshot advertises 1,048,576 context tokens for the three listed rows; these provider declarations must not be imported into Token Factory metadata. [Recommendation response][recommendations], [GLM family tests][thinking-tests].

For contrast, the public **GLM 4.7** renderer embeds tool-schema guidance, serializes tool calls in its XML-like format, preserves supplied thinking history and defaults thinking on. The public **DeepSeek V3.1** renderer uses different role/tool tokens and tool-format instructions, and defaults thinking off. These demonstrate why training-format adaptation matters; neither is evidence of GLM 5.3 or DeepSeek V4.1's deployed renderer. The named registry has no exact GLM 5.3, Kimi K3 or DeepSeek V4.1 renderer. [GLM 4.7 renderer][glm47], [DeepSeek V3.1 renderer][deepseek31], [registry][renderers].

Renderer selection comes from model configuration, with explicit variant logic such as Gemma 4 small/large selection. Local inference selects that renderer or the model's template. Modelfile `TEMPLATE` and `SYSTEM` are distinct controls; a behavioral instruction override is not a substitute for the correct serialization. Token Factory owns that lower layer for our remote models. We should not prepend Ollama's raw training tokens to its OpenAI-compatible API messages. [Renderer selection][renderer-selection], [prompt assembly][local-prompt], [Modelfile reference](https://docs.ollama.com/modelfile).

Metadata can change independently of the binary: the recommendation cache refreshes from a remote endpoint, starts with bundled defaults, and persists a snapshot. Its normal refresh interval is four hours. For capability evaluation, record the actual resolved controls and metadata hash alongside source/client versions; a release tag alone does not freeze this input. [Recommendation cache][recommendation-cache].

## What the proxy changes

The Desktop router promotes developer input messages to system messages for Ollama routing; preserves function calls/results; turns custom calls into function calls carrying an `input` argument; retains client tool-search control items; translates agent messages into an attributed user-message envelope; and filters provider-specific reasoning/compaction state. The role promotion is unconditional in this Ollama-route normalization function, despite its explanatory comment mentioning models without developer-role support. Unsupported input types can be silently dropped. That last behavior conflicts with this project's fail-fast principle and is not a policy to copy. [Desktop normalization][normalization].

On the local compatibility path, Responses `instructions` become a system message; pending reasoning is attached to assistant history; an assistant message between a tool call and its result is merged to retain ordering. Namespaces are flattened to qualified tool names and reconstructed in responses; client-executed tool search has explicit conversion. These are relevant test seams for apparent tool-discovery or continuation failures. They do not establish that a model read a presentation skill. [Responses converter and namespace helpers][responses], [conversion tests][responses-tests].

A narrowly gated Full Access normalization removes escalation-only properties from `exec_command` schemas, including namespace members, because those properties can provoke rejections when the client already runs without a sandbox. It uses declared sandbox metadata; it does not grant Full Access. **Recommendation:** retain our native approval contract and study this only if the same rejection is demonstrated. Do not remove security fields generally or weaken the Guardian. [Normalization, lines 51–193][normalization], [sandboxed/namespaced tests][normalization-tests].

## Skills, artifact delivery, loops and auxiliary work

**Skills and artifacts:** the Desktop catalog explicitly enables skill/plugin/app usage instructions. A search of the inspected Codex integration, proxy, Responses and renderer implementation files found no `codex-file-citation` rewrite, presentation handoff template, or `SKILL.md` discovery engine. This is scoped absence of evidence: native catalog text and client-injected instructions can still contain these conventions. We have no public basis to say Ollama fixed clickable artifact delivery by changing a model-family prompt. [Desktop catalog][desktop], [public integration sources][integration-tree].

**Loop recovery:** no general repeated-shell-command watchdog was found in those paths. Ollama does cap its own server-side web-search loop at ten iterations and tells the model when that budget is exhausted. That is not a cap on Codex's client-executed shell loop. Our independent repeated-action/time limit remains necessary. [Web-search limit][search-limit], [search orchestration][search-orchestration].

**Compaction:** a public system prompt asks for structured conversation handover through `create_summary`, retaining exact items when necessary. The handler permits one repair after invalid output and one context-overflow trimming retry, then surfaces failure without replacing the original conversation. This is a useful bounded repair pattern, not evidence of general loop recovery. [Summary request][summary], [compaction handler][compaction].

**Guardian and titles:** Ollama adds a decision tool and a short final-decision instruction for its native review alias, then transforms the result. Its selected-main policy has a configured fallback when parent-turn lookup fails. That differs from our explicit Guardian contract and must not be copied as automatic model substitution. No `thread_title`/Luna-specific naming route was found in the inspected Codex implementation; the generic router chooses native versus Ollama by catalog membership. Keep our independently qualified naming behavior separate. [Review adapter][review], [routing][router], [our ADR 0002](../adr/0002-guardian-selection-follows-launch-route.md), [our ADR 0003](../adr/0003-desktop-conversation-model-selection.md).

## Decisions and falsifiable experiments

These are proposed experiments, not implementation approval or support claims. Preserve the accepted three fresh runs per investigated variant, separate CLI/Desktop scores, frozen environment and raw attempt retention.

| Candidate | Decision | Small experiment and rejection criterion |
| --- | --- | --- |
| Native Desktop prompt/catalog flags | Investigate first | Record effective base text and skill/plugin/app instruction blocks for a fresh Desktop chat; change one demonstrated missing flag in an isolated catalog. Reject if the needed instructions already arrive or task/delivery scores do not improve. |
| Compact artifact handoff instruction | Continue existing pilot | Compare verified-file handoff with baseline while holding actual tool schema and skill visibility constant. Require real Desktop click/preview confirmation; a CLI citation string is insufficient. |
| Role handling | Inspect before changing | Synthetic sentinel developer/system messages through our adapter; check ordering and role preservation. Only test a provider-role variant after an exact-model contract failure is demonstrated. Reject if promotion changes authority or discards policy. |
| Tool/history translation | Add targeted fixtures when a gap appears | Replay namespace discovery, tool-search output, assistant commentary between call/result, and reasoning continuation. Require semantic round-trip and explicit errors for unsupported items. |
| Thinking controls | Record as an experimental dimension | Use Token Factory's verified exact-model controls, not Ollama's aliases/defaults. Compare small recovery case at two supported efforts; score latency, repetition and completion separately. |
| Repetition guard | Keep evaluator-owned bounds | Replay the recorded DeepSeek repetition plus healthy polling/workspace-progress fixtures. Require stopping unchanged actions without classifying normal polling as a loop. |
| Raw model renderer or broad fallback | Do not import | Provider-side serialization is outside the launcher's contract; no exact public hosted implementation was established. |

The broader implication is to measure **what input and tool contract reached the model**, then distinguish generation, client rendering, skill availability and adapter defects. Prompt changes remain one candidate explanation, not the presumed fix.

## Configuration ownership and reuse limits

Ollama's Desktop setup writes a root `openai_base_url`, which can affect ordinary Codex CLI using that shared config; its dedicated CLI launcher uses separate provider/profile overrides. This explains the *mechanism* behind the observed localhost dependency. It does not establish that the recent update wrote the setting or identify the writer. Preserve the user's corrected ordinary config and use scoped experimental catalogs. Copying the global override would conflict with ADR 0003's concurrent-CLI isolation rule. [Desktop config writer][config-writer], [CLI integration][cli], [ADR 0003](../adr/0003-desktop-conversation-model-selection.md).

The inspected Ollama repository is MIT licensed; substantial copied source requires its copyright and permission notice. That does not license native Codex Desktop binaries, hosted service internals, model weights, or every dependency. Prefer independently implemented small adapters and fixtures, preserving provenance for any copied code. No product code was changed by this research. [Ollama license][license], [dependency manifest][dependencies].

[cli]: https://github.com/ollama/ollama/blob/b061384d90ff455462bc32745dd0de479de717a3/cmd/launch/codex.go#L690-L765
[desktop]: https://github.com/ollama/ollama/blob/b061384d90ff455462bc32745dd0de479de717a3/cmd/launch/codex_app.go#L1380-L1480
[renderers]: https://github.com/ollama/ollama/blob/b061384d90ff455462bc32745dd0de479de717a3/model/renderers/renderer.go
[routes]: https://github.com/ollama/ollama/blob/b061384d90ff455462bc32745dd0de479de717a3/server/routes.go#L2342
[cloud]: https://github.com/ollama/ollama/blob/b061384d90ff455462bc32745dd0de479de717a3/server/cloud_proxy.go#L73-L136
[recommendations]: https://ollama.com/api/experimental/model-recommendations
[codex-models]: https://github.com/openai/codex/blob/rust-v0.162.0/codex-rs/protocol/src/openai_models.rs#L904-L935
[responses]: https://github.com/ollama/ollama/blob/b061384d90ff455462bc32745dd0de479de717a3/openai/responses.go#L557-L1050
[responses-tests]: https://github.com/ollama/ollama/blob/b061384d90ff455462bc32745dd0de479de717a3/openai/responses_test.go#L408-L480
[local-prompt]: https://github.com/ollama/ollama/blob/b061384d90ff455462bc32745dd0de479de717a3/server/prompt.go#L129-L155
[resolution]: https://github.com/ollama/ollama/blob/b061384d90ff455462bc32745dd0de479de717a3/cmd/launch/launch.go#L1456-L1489
[thinking]: https://github.com/ollama/ollama/blob/b061384d90ff455462bc32745dd0de479de717a3/cmd/launch/codex_app.go#L1262-L1343
[thinking-tests]: https://github.com/ollama/ollama/blob/b061384d90ff455462bc32745dd0de479de717a3/cmd/launch/codex_app_test.go#L2204-L2207
[glm47]: https://github.com/ollama/ollama/blob/b061384d90ff455462bc32745dd0de479de717a3/model/renderers/glm47.go
[deepseek31]: https://github.com/ollama/ollama/blob/b061384d90ff455462bc32745dd0de479de717a3/model/renderers/deepseek3.go
[renderer-selection]: https://github.com/ollama/ollama/blob/b061384d90ff455462bc32745dd0de479de717a3/server/renderer_resolution.go
[normalization]: https://github.com/ollama/ollama/blob/b061384d90ff455462bc32745dd0de479de717a3/internal/proxy/codex_desktop_normalize.go
[normalization-tests]: https://github.com/ollama/ollama/blob/b061384d90ff455462bc32745dd0de479de717a3/internal/proxy/codex_desktop_test.go#L378-L508
[integration-tree]: https://github.com/ollama/ollama/tree/b061384d90ff455462bc32745dd0de479de717a3/internal/proxy
[search-limit]: https://github.com/ollama/ollama/blob/b061384d90ff455462bc32745dd0de479de717a3/middleware/web_search.go#L9
[search-orchestration]: https://github.com/ollama/ollama/blob/b061384d90ff455462bc32745dd0de479de717a3/middleware/openai.go#L762-L914
[summary]: https://github.com/ollama/ollama/blob/b061384d90ff455462bc32745dd0de479de717a3/openai/responses_compact.go#L777-L819
[compaction]: https://github.com/ollama/ollama/blob/b061384d90ff455462bc32745dd0de479de717a3/server/responses_compact.go#L101-L151
[review]: https://github.com/ollama/ollama/blob/b061384d90ff455462bc32745dd0de479de717a3/internal/proxy/codex_desktop_autoreview.go
[router]: https://github.com/ollama/ollama/blob/b061384d90ff455462bc32745dd0de479de717a3/internal/proxy/codex_desktop.go#L194-L284
[config-writer]: https://github.com/ollama/ollama/blob/b061384d90ff455462bc32745dd0de479de717a3/cmd/launch/codex_app.go#L314-L388
[license]: https://github.com/ollama/ollama/blob/b061384d90ff455462bc32745dd0de479de717a3/LICENSE
[dependencies]: https://github.com/ollama/ollama/blob/b061384d90ff455462bc32745dd0de479de717a3/go.mod
[recommendation-cache]: https://github.com/ollama/ollama/blob/b061384d90ff455462bc32745dd0de479de717a3/server/model_recommendations.go#L23-L69
