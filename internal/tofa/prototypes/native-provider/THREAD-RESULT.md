# Native-provider conversation routing experiment — 2026-10-15

Question: can the actual bundled engine switch a new conversation between Token
Factory and native models, preserve context and legacy histories, authenticate a
launch-local route independently of native credentials, and select the correct
reviewer/title service?

## Verdict

**Switching, context continuity, legacy resumption and model-based review selection
passed the local engine fixture. Production authorization and per-service naming
remain unresolved.** This extends #133; it does not qualify Desktop or lift its
preservation guard.

The final run passed 12 scoped assertions using 16 engine requests to an owned
loopback router and 16 corresponding loopback upstream requests. All model
responses were synthetic. Real credentials, external inference and Desktop were
not used. The engine used a disposable fixture home and fake API-key auth, with
real profile/config reads denied, protected shared writes denied, and external
network access denied by its sandbox. This synthetic transport result is separate
from the earlier actual signed-in ChatGPT account/configuration proof.

## Observed behavior

- One new `openai`-provider thread completed Kimi → GPT → Kimi. Its ID and three
  completed turns were retained; prior assistant responses appeared in requests
  to the next explicitly selected service.
- A new native-provider thread and a legacy `nebius-tofa` fixture thread resumed
  across engine restart with their recorded provider and identity. Both completed
  another turn. Existing legacy conversations were not converted into cross-service
  conversations by this experiment.
- A random launch secret in the base-URL path arrived at the router. Missing and
  incorrect paths were rejected before upstream, including a control-like path.
  The router exposes no actual launcher/evaluation control endpoint; their
  production authorization is not tested here.
- Native fake credentials reached only the native fixture. Token Factory fixture
  requests received a separate fake credential. The prototype's outbound header
  allowlist also discards the launch path and any native request metadata.
- Automatic review followed Kimi → GPT → Kimi as GLM-5.3-Flash → GPT → GLM-5.3-Flash.
  The bundled native GPT descriptor has no reviewer override; the engine selected
  GPT itself. We preserved that native behavior instead of assigning
  `codex-auto-review`. Review requests contained parent-thread and parent-turn
  metadata. Synthetic deny assessments were enforced; no proposed command ran.
- Review selections were tested between completed turns. Switching during a
  pending review remains a separate acceptance case.
- A replay of the native automatic-title helper created a separate ephemeral
  Luna thread. Its request contained its own thread/session IDs, but no parent
  thread/turn linkage. The fixture sent it to the native synthetic upstream only
  to inspect its shape; this is not adoption of a launch-wide native naming policy.

## Two remaining constraints

**Authorization:** secret-path delivery is established, but URLs can appear in
native engine diagnostics (observed during the HTTP/1.0 fixture error). A proposed
`model_providers.openai.http_headers` override was rejected before initialization:
the installed engine reserves built-in provider IDs. Do not ship secret-path
authorization without addressing diagnostic exposure and the production threat
model. Neither this probe nor native bearer presence establishes that production
inference/control isolation is qualified.

**Naming:** the currently inspected title caller omits the source conversation
even though the generic helper supports it. Timing, cwd, prompt similarity and
the most recent model selection cannot reliably recover the source. A launch-wide
naming policy needs a product decision; retaining per-service naming needs a
different proven boundary. No policy was silently substituted. The design choice
was returned to the maintainer after these findings.

## Native source and picker evidence

Installed ChatGPT version `26.1007.71326`, build `20398`; `app.asar` SHA-256:
`2f231a64e6dd30111bcd09e03c149cd06c8679b25914842772423251c4608ded`.
Private extracted source remains outside this branch; only identifiers and
findings are recorded here.

- `app-shared-8340f229c2b3.js`, character offset 5474124: the title caller knows
  the parent ID but forwards host, prompt, cwd, tool allowlist and optional service
  name without that ID. It uses the parent afterward when applying the title.
- `main-CwxgTOle.js`, offset 3207887: title generation likewise omits the parent;
  adjacent description generation supplies `sourceThreadId`.
- `.vite/build/src-DCNiwad_.js`, SHA-256
  `86fb2066bbc2f7428864b76b46ef570b09eb1e92e81e9d6f089f5b048a66df25`:
  helpers at offsets 1557071/1558687 accept source identity. The generic helper at
  1416455 forks when it is supplied, otherwise starts an unrelated ephemeral
  thread. Generic capability does not imply that the title caller supplies it.
- Picker functions in `app-initial-1ab6fbe93c4f.js`, offsets 4808873 and 4809987,
  retain `model/list` metadata and admit configured nonhidden models under the
  built-in provider, subject to native eligibility checks. Existing TOFA catalog
  display names/descriptions can identify the service. Visible UI behavior still
  needs qualification; no separate service-badge API was established.

## Retained attempts and limitations

| Attempt | Outcome |
| --- | --- |
| 1 | Setup failed: invalid sandbox loopback syntax. No engine inference. |
| 2 | Main/resume checks passed; incorrect fixture expectation for native reviewer caused failure. Native malformed review responses were denied. HTTP/1.0 caused WebSocket retries before HTTP fallback. |
| 3 | Corrected HTTP/1.1 and native reviewer expectation; 11 scoped checks passed. |
| 4 | Header authorization alternative rejected: built-in provider override prohibited. No inference. |
| 5 | Final path-mode probe; 12 scoped checks passed, including native auth requirement. |

Every attempt is retained. Sanitized result files are under `evidence/`; private
fixture homes, raw engine logs and synthetic transcripts remain under the fixed
temporary validation root. Earlier result files retain their source hashes;
`thread_probe.py` is the final run-5 source. `thread-request-shapes.json` contains
field names and booleans only, without auth values, request bodies or thread IDs.

Engine: `codex-cli 0.162.0-alpha.17.2`, SHA-256
`0d5ac7aae20c4eda6242428d5e218c55ba96d8763fda2a271088ff37104b9d28`.
The probe is throwaway Python, not the production Go adapter. No production suite
was run for it. Validation consists of actual bounded engine runs, negative
authorization controls, Python/HTML-script syntax checks and `git diff --check`.
No paid model quality, real signed-in inference transport, native plugin lifecycle,
presentation preview, release, or support claim follows.
