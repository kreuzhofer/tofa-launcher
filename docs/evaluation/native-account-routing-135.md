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

Before Desktop startup, the launcher uses native configuration and
account read RPCs, with token refresh disabled, to require an existing ChatGPT account
under the native-authenticated provider. It rejects unsupported managed routing
requirements and conflicting provider definitions. It neither creates credentials
nor changes authentication modes. Native engine discovery retains the existing
bundle resolver and compatibility checks, without version-directory literals.
Read RPCs do not imply side-effect-free process startup; the 26 October correction
below records the native generated-skill behavior and its helper-only control.

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

## 2026-10-26: preserve system skills during configuration preflight

Starting revision: `784c0b0663940cdca240b7a6738790d7d722c1c6` on the existing
integration worktree. This correction does not rebuild the previously implemented
authorization route or repeat the earlier real-account probe.

The previous manual refusal occurred before inference. The retained diagnosis
found that native account/config startup replaced the generated system-skill
cache when the standalone CLI and Desktop engine embedded different versions.
The new public-launch regression uses disposable homes and actual engine startup:
standalone CLI `0.164.0` seeds the cache, and bundled engine
`0.163.0-alpha.11.2` performs the launcher checks. Engine paths are explicit test
inputs; production discovery remains unchanged. The test skips with an explicit
reason if the selected engines embed identical skills.

The original failure was reproduced twice in 0.64 and 0.53 seconds: the marker
and two generated openai-docs scripts changed. Configuration, fixture credentials
and a personal skill are also checked. A normal target-engine control still
installs its own skills, confirming both the distinct cache versions and the
absence of a global skill-disable setting.

### Minimal correction and upstream comparison

The native `skills.bundled.enabled=false` override prevents system-skill
installation in the **short-lived configuration helpers only**. It is applied
in `openDesktopConfig` and the later routing-validation helper. The latter had
its own red public-launch regression (2.42 seconds) after the first helper was
fixed, demonstrating that fixing only the initial account check was insufficient.
Neither helper runs a conversation. The override is not persisted, placed in
the live route, or passed to Desktop's conversation engine.

This retains the real home, account lookup, configuration layers and managed
policy resolution. It needs no credential copy, replacement profile, system-cache
warm-up, snapshot restoration or preservation-check exclusion. Prerequisite and
provider-conflict refusals remain active. Exact bundled-engine discovery is retained.

Ollama's [isolated catalog probe](https://github.com/ollama/ollama/blob/66ab8482e08035a3238dff04a5739c4371c61bfe/cmd/launch/codex_app.go#L1480-L1622)
was inspected. That path copies auth/cache files and does not establish equivalent
ordinary-home account/managed-policy semantics. The narrower process-only native
control was tested first and reproduced the required preservation, so no separate
home projection or credential-copy mechanism was added. This is a tested local
alternative, not a claim that an isolated signed-in probe is impossible.

The native [skills configuration parser](https://github.com/openai/codex/blob/970111f6cb62cc02fe36a82ea7d71b37a2889c97/codex-rs/config/src/skills_config.rs)
and [host skills service](https://github.com/openai/codex/blob/970111f6cb62cc02fe36a82ea7d71b37a2889c97/codex-rs/ext/skills/src/host_service.rs)
corroborate the control. These sources do not establish the exact installed
binary's provenance; the installed-engine regressions establish its observed behavior.

Declaration diagnostics now distinguish expiration/invalid time windows from
identity mismatches and name fixed categories such as `skills`. Paths, hash
values and user-supplied field names are not emitted. Unknown identity fields
still fail closed, with a generic identity-metadata category.

### Reproduction and limits

With Go and both test engine paths configured, the focused command is:

```sh
go test ./internal/tofa -run '^(TestDesktopNativePreflightPreservesOtherEngineSkills|TestDesktopDeclaredCandidateExplainsPreflightRefusal|TestDesktopNativeCandidateIsolatesInferenceAndControl)$' -count=1 -v
```

Set `TOFA_TEST_DESKTOP_ENGINE` to the discovered bundled executable and
`TOFA_TEST_OTHER_ENGINE` to an installed engine with distinct embedded skills.
The tests never use the operator's account: account fixtures use synthetic tokens,
file-only storage and owned local HTTP services. The signed-in-shaped fixture
demonstrates native account parsing and prerequisite success, not real signed-in
inference. The existing managed-policy fixture checks remain required; an attempted
home-local `requirements.toml` experiment was not recognized as a managed source
by this installed engine and was not retained as a purported passing policy test.

The later-routing regression uses a fake Desktop/worker and real native
configuration helpers. It does not launch the installed Desktop UI. Normal
Desktop conversation startup can still refresh its generated cache; this fix
does not disable that behavior or grant a preservation exception. #141 must
retain and evaluate any such transition, along with its separate prelaunch
collection repair. No manual run, live account test, installation change or
production admission is part of this correction.

### Validation of the corrective slice

Implementation commit: `fc33cfa425e94d01aebef2c2f12c43d826c9c8a9`.

- Full `go test -race ./...` passed; the main package completed in 560.727
  seconds. Tests requiring explicit installed-engine inputs are skipped in this
  default suite and were exercised separately.
- The installed mixed-engine regression passed under the race detector in 8.982
  seconds, covering prerequisite refusal, account verification, provider conflict
  and the later routing check. Both actual engines operated on disposable homes.
- The focused authorization, managed-policy, declaration, control/inference
  isolation and bundled-engine transport tests passed. `go vet ./...` passed.
- All 24 qualification collector/guide Python tests passed. The collector needed
  a rerun outside the filesystem sandbox to bind its owned loopback fixture;
  the initial sandbox denial is retained separately from the passing result.
- Independent Standards and Spec reviews reported no findings against baseline
  `784c0b0663940cdca240b7a6738790d7d722c1c6`. Formatting and whitespace checks passed.

Private logs remain in the durable qualification directory. These automated
results do not qualify native Desktop account/plugin preservation or authorize
a manual retry; the remaining #141 collection and startup-transition checks
remain separate.
