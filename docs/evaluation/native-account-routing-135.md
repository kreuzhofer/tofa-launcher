# Authenticated Desktop candidate: #135

This is implementation evidence for the first slice of #134, not Desktop or
model-capability qualification. The ordinary launch and the code-review plugin
preservation guard remain in force. The installed launcher and native app are not
changed by this work.

## Candidate contract

`launch codex-desktop --native-account-candidate` is a qualification-only option.
It requires an explicit version-2 evaluation observer, with a 600- or 900-second
outer deadline. `--allow-unverified` does not enable it. The observer is a bounded
transport observer, not a qualification proof or permission to bypass the plugin
preservation or native profile ownership checks. Later slices must supply current,
identity-bound Desktop qualification before general admission.

The stable provider identifier for new candidate conversations is
`tofa-native-router`. Existing `openai` and `nebius-tofa` identities are unchanged.
A pre-existing definition of the new identifier is refused; the candidate does
not overwrite it. The candidate currently supports Token Factory inference only;
native switching and inactive-history registration are subsequent slices.

Before Desktop startup, the launcher uses native read-only configuration and
account RPCs, with token refresh disabled, to require an existing ChatGPT account
under the native-authenticated provider. It rejects unsupported managed routing
requirements and conflicting provider definitions. It neither creates credentials
nor changes authentication modes. Native engine discovery retains the existing
bundle resolver and compatibility checks, without version-directory literals.

The candidate provider requires native authentication and sends its independent
inference capability through an environment-backed `X-TOFA-Launch` header. The URL
contains no capability. Recorded legacy Token Factory histories receive the same
inference capability as their compatibility bearer. A distinct random control
capability authenticates bridge route discovery and evaluation shutdown. Native
credentials alone, inference access to control endpoints, duplicate/malformed
headers and mixed control/inference credentials are rejected. Existing exact
routes, body/header bounds, upstream credential reconstruction and redirect
refusal remain in force.

The Desktop bridge and settings relay retain control authorization. The engine
receives only the inference environment variable; the bridge removes control
variables before executing it. The native shell policy adds `TOFA_*` exclusions
without replacing user exclusions or other policy fields. Ordinary saved bridges
remove stale inference credentials. Active routes expire with their owning
launcher. This is not isolation from a privileged process or same-user memory
inspection.

Observer v2 registers exactly `version`, `endpoint`, `control_token` and
`inference_token`. Native bearer/account headers are carried only on the owned
local observer-to-adapter leg; the adapter rebuilds Token Factory headers with its
independent credential. Observer v1 remains unchanged for earlier runs. Existing
orchestration must explicitly select v2 for a candidate, preserving historical
run declarations.

## Verification boundary

The new regressions use the public launch entry point, owned Desktop executable
fixtures, the repository’s actual Python observer, the actual bundled engine and
local upstreams. The combined regression exercises version-2 registration and
header forwarding through the observer to the Go adapter, rather than relying
only on independently matching fixtures. The engine exercised was
`codex-cli 0.162.0-alpha.17.2`, SHA-256
`0d5ac7aae20c4eda6242428d5e218c55ba96d8763fda2a271088ff37104b9d28`.
This is a recorded test identity, not a production version pin.

Tests establish:

- Missing account, incompatible observer, conflicting provider and protected
  code-review installation stop before Desktop fixture startup.
- Native-account authorization is independent from native service credentials and
  launcher control. Valid inference reaches the owned Token Factory upstream
  without native account metadata or local authorization headers.
- A new actual-engine conversation uses `tofa-native-router`, completes a Token
  Factory turn and performs harmless login/non-login shell tool calls. Both
  control/inference variables and an existing user-excluded variable are absent
  from these actual children.
- A harmless actual engine-launched MCP stdio child reports control, context and
  inference variables absent. This does not qualify all native Desktop-hosted
  plugin subprocesses; their lifecycle remains actual-Desktop acceptance work.
- Actual engine failed-handshake and disconnect controls reproduce the URL-secret
  diagnostic defect. The header route delivers the capability while the same
  useful native errors omit it. Intentional negative-control diagnostics use an
  unrelated synthetic value and are sanitized. Candidate engine state and launch
  arguments are checked for inference-capability disclosure.
- Existing native-history, CLI, adapter and evaluation tests continue to pass in
  the affected race-tested set.

The transport fixture uses disposable fake credentials. Its account-preflight
fixture and engine inference checks do not establish real signed-in inference.
The [separate real-account read-only proof](evidence/native-account-135/account-readonly.json)
passed with the same engine: ordinary before/candidate/ordinary after all returned
ChatGPT account context, the candidate required native authentication, ordinary
before/after matched and protected hashes remained unchanged. Its child sandbox
denied protected writes and token refresh was disabled. It ran native engine RPCs,
not the production Launcher or a signed-in inference turn. An earlier probe
attempt failed locally before starting the engine because the host Python lacked
a hashing convenience function; that preflight failure remains in private evidence. Actual Desktop account/plugin preservation, rendered service labels,
native previews, crash/update qualification and model comparison remain later
acceptance gates. No qualification or release claim follows from this document.
