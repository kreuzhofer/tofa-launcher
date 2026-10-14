# #133 result: native account context retained

The installed bundled engine preserves its real signed-in account with a
process-only built-in-provider/base-URL override, including when the selected
model is `moonshotai/Kimi-K3`. The current custom-provider control loses that
account context. The experiment therefore supports investigating a launcher-side
routing correction before requiring Desktop source changes or profile isolation.

This answers an account/configuration question. It does not prove native plugin
preservation or qualify a production routing implementation.

## Actual engine observations

Client: `codex-cli 0.162.0-alpha.17.2`, SHA-256
`0d5ac7aae20c4eda6242428d5e218c55ba96d8763fda2a271088ff37104b9d28`.
Installed Desktop metadata: `26.1007.71326`, build `20398`; Desktop itself was
not started. Exact identities are in [account run 8](evidence/account-run-8.json).

| Process configuration | Account type | Requires native auth | Override observed |
| --- | --- | --- | --- |
| Ordinary before | `chatgpt` | true | No routing override |
| Current custom-provider control | null | false | Custom provider selected |
| Built-in `openai` + loopback base URL | `chatgpt` | true | Provider and loopback URL |
| Same + Kimi model selection | `chatgpt` | true | Provider, loopback URL and Kimi |
| Ordinary after | `chatgpt` | true | Original ordinary configuration |

All five account assertions passed. Protected-file snapshots matched between
every case and after completion, including checked settings/auth files, plugins,
skills, supplied runtime and launcher/bridge files. The code-review configuration
entry remained present. Native account result objects were never serialized;
only type and the relevant configuration facts were exported.

The engine received five `account/read` RPCs with `refreshToken=false` and five
`config/read` RPCs, each after initialization. No inference RPC, user prompt,
Desktop launch, persistent config/auth edit, eligibility override or guard removal
was performed. The Kimi selection was configuration-only; no Kimi request ran.

## Earlier attempts and connectivity limitation

All attempts remain in `evidence/account-run-1.json` through `account-run-8.json`.
Raw stderr and engine state remain private under the fixed validation root.

- Runs 1–3 used a blanket write denial outside the evidence directory. The
  engine exited before initialization with `Operation not permitted`; the probe
  initially labelled the missing response a timeout. Diagnostic changes did not
  change that outcome. This restriction prevented engine startup IO.
- Runs 4–6 allowed ephemeral engine startup IO while denying writes to protected
  settings/auth/plugins/runtime/launcher/native app/profile paths. Initialization
  succeeded, but account lookup returned `workspace routing discovery failed`
  while all networking was denied.
- Run 7 allowed HTTPS/DNS and retained protected-write denial. It still failed
  at the same account discovery. The exact additional transport requirement was
  not isolated.
- Run 8 retained protected-write denial but used normal native account
  connectivity. All five configurations passed. Native workspace-account service
  requests were not captured or counted; **this is not a zero-network run**.
  No model/inference RPC was submitted and token refresh remained disabled.

Protected-state checks passed in every retained attempt. Failures above are
experimental sandbox restrictions, not negative evidence about model capability
or successful Desktop plugin preservation.

## Synthetic routing observations

The [deliberate negative control](evidence/router-negative.json) exited 1 and
caught both native-credential leakage and loss of the independent alternate
credential. The [safe variant](evidence/router-positive.json) exited 0: all eight
checks passed against owned loopback services using fake credentials only.

Checks cover alternate routing, independent alternate credentials, stripping
native authorization/account/private headers, signed-in native routing, native
API routing, unknown-model refusal, redacted upstream errors without fallback,
and unavailable-service errors without fallback. Each variant made four upstream
fixture requests. No external service or production adapter was exercised.

The self-contained `walkthrough.html` demonstrates the proposed state model and
embeds these measured results separately from its simulations. Python sources
and inline JavaScript passed syntax checks. No production test suite was run:
production code did not change, and these are bounded executable experiments.

## Decision and next boundary

Proceed to design a scoped production routing implementation. Keep the ordinary
signed-in context, process-scoped defaults, independent Token Factory credentials
and explicit routing errors. Preserve existing `nebius-tofa` conversation provider
identities; main, Guardian and naming requests need explicit routing contracts.
Do not copy Ollama's persistent shared-config/restore lifecycle or auth sentinel.

Retain the current launch guard until actual-client plugin lifecycle preservation
is qualified. After that, requalify the actual runtime loader and native previews
before resuming the separately declared comparison. #130/#119 and release/support
promotion remain incomplete. The prototype branch is evidence, not a mergeable
production feature.
