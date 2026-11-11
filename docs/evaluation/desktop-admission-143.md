# Normal Desktop admission and retained evidence (#143)

This change enables the previously qualified native-account route through normal
`tofa launch codex-desktop` in integration source builds. It does not publish a
release or certify a model. The public startup boundary requires current native
sign-in, supported policy/configuration contracts, exclusive ownership, isolated
inference/control authorization and verified routing overrides. Failed checks
refuse the launch; there is no fallback to the historical custom-provider route.

A launch records the current launcher, engine, app executable and bundle metadata,
then rechecks them and protected settings during startup. These checks bind this
startup to the installation it probed. They do not compare installations against a
maintainer's private source, home, runtime, harness, plugin cache or model catalog.
The model picker still checks current availability and required metadata. Active
routing and credentials stay process-scoped; inactive owned provider entries
support existing history. Shared settings are never restored from a snapshot.

Explicit historical candidate/proof commands retain their original receipt
validation. The explicit version-1 evaluation route retains its old plugin guard.
Neither historical proofs nor the behaviour assessor's output become a normal
user prerequisite. A diagnostic result alone cannot authorize a future launch.

## Behaviour-specific reuse

The change from `9c5d3bc` affects admission and disclosure, not service routing,
review dispatch, naming, bridge execution, tool transport, history storage, loader
invocation or native rendering. Retained observations apply to those unchanged
behaviours. Automated normal-entry-point tests exercise the newly admitted path;
installed-engine tests separately check actual protocol and tool behaviour.

Seven recent independent reviews and 267 original receipt bindings were rechecked
without changing the originals. Earlier account/lifecycle evidence remains bound
by the November 10 assessment in [#141's evidence report](desktop-evidence-141.md).
The following is a release assessment, not a rewritten historical case result or
an invented complete machine qualification file.

| Behaviour | Evidence reused and reason | Limits |
| --- | --- | --- |
| Native account, plugins, Code Review eligibility, normal exit | Accepted `3afa725` clean exit and current startup/ownership/policy tests; admission now selects the same native-account route | Fixture sign-in responses do not establish account UI; the retained human observation does |
| Repeat launch, history readability and crashes | Accepted `efd74f8` and `9928136` scopes, supplemented by real-engine lifecycle/history tests; storage and bridge lifecycle unchanged | Does not claim every historical fault was manually repeated |
| Visible service selection and same-thread context | `service-switching.81a930919206127f`: TF → native → TF, three completed turns and visible selection; dispatcher unchanged | No review execution inferred from these smoke turns |
| Routed cross-launch history/tool continuation | `history-resume.e2506ffd3acb779b`: recorded TF selection survives another launch default, context retained, bounded tool completes | Existing title visibility is not a new naming execution |
| Existing native history | `native-history-seed.91atr_ph` recovered native turn and `history-resume.d011310d5cb3424f` continuation; provider stays native under TF launch default | Original seed collection remains incomplete; independent transcript evidence establishes only its recorded scope |
| Review destination and execution | `review-routing.915fd65e00347bff`: native and Guardian origins bound to allow decisions before tool execution; real-engine negative controls cover deny, cancellation, unknown origins and pending service changes | Smoke answers alone do not prove review; native policy/execution gates remain authoritative |
| Naming | Human-visible new TF/native titles in switching/review attempts, plus installed-engine naming across conversation categories | Title transport does not invent an unavailable parent association; errors remain independent of Main |
| Ordinary native use and routed recovery | Recovered ordinary native seed/continuation; `ordinary-recovery.pre9innp` preserves protected state and history; documented relaunch workaround | Reconnect guidance observation remains failed, accepted as a limitation. No new native turn is claimed from its unchanged transcript |
| Runtime and native previews | `runtime-preview.5f5c33f6763b5750`: actual loader, supplied versions, validated synthetic PPTX/PDF and both human-opened previews | Not deck quality, implicit skill discovery or live naming qualification |
| Preservation | Original semantic reviews retain exact authorized workspace-trust changes and captured native-generated skill contracts; new local checks and negative controls retain security gates | Old unexplained differences in `ordinary-recovery.a9vi4y_n` remain unexplained. They are not attributed to a specific file or waived as cache churn |

Catalog/model/plugin-cache identities remain provenance. Credentials, routing,
permissions, personal settings and history remain required checks. Current
sufficient observations establish current behaviour independently of older
incomplete attempts; they do not convert those attempts into passes.

## Ordinary Desktop limitation

Opening Desktop directly may bypass the bridge and reconnect forever to the
inactive route without a TOFA-specific message. The maintainer accepted that
limitation for the experimental prerelease. TOFA now prints the recovery steps:
stop reconnecting, quit Desktop, launch through TOFA and reopen the same
conversation. Do not change models to migrate providers. No app patch, persistent
credential or recovery daemon is introduced.

## Comparison decision

**Revise #130's declaration before resuming.** Do not reuse its old exact-catalog
or exact-installation admission gates or automatically replay failed attempts.
Keep all previous outcomes. The next declaration should name the reviewed source
candidate, record current client/runtime identities, select available models
explicitly, retain implicit-discovery case 03 and explicit-skill case 04 as
separate cells, and record runtime/artifact/native-preview/naming outcomes
independently. Keep the separately agreed 900-second, 80-request, 8192-output-token
limits for each comparison cell, no automatic retries or substitutions, and the
established temporary and durable evidence locations.

This document proposes the next declaration; it launches nothing. #130 remains
open, as do campaign/adoption decisions #119/#120 and wider release #106. A new
model comparison is not required to repeat accepted integration observations.

### Proposed next declaration (draft, not executed)

| Field | Proposed value |
| --- | --- |
| Campaign / attempt set | `130-native-admission-01`; preserve all preceding attempts separately |
| Candidate | Integration branch `fix/134-plugin-inventory`, admission commit `9a99ad3` plus its reviewed corrections; final SHA and binary digest pending freeze after tests/review |
| Client / platform | Actual host ChatGPT Desktop Codex mode, macOS ARM64; capture discovered app/engine identities at preparation |
| Ordered cells | 1: Kimi-K3 / case 03; 2: Kimi-K3 / case 04; 3: GLM-5.3 / case 03; 4: GLM-5.3 / case 04 |
| Main IDs | `moonshotai/Kimi-K3`, `zai-org/GLM-5.3`; availability pending non-launch catalog check; unavailable selection blocks its cell, no substitute |
| Guardian / naming | `zai-org/GLM-5.3-Flash` / `nvidia/Nemotron-3_5-Lightning`, checked independently |
| Prompts | Existing case 03 implicit pitch-deck request; existing case 04 same request with explicit installed-skill instruction; record corpus and prompt digests at freeze |
| Limits per cell | 900 seconds including setup; 80 requests; 8192 output tokens per request; no automatic retries or substitutions |
| Finish / cancel | Explicit operator finish after Main and preview check, or cancel; deadline is a stop, never a pass; naming scored independently |
| Stop campaign | Credential/routing/preservation violation, unavailable required contract, collector failure or unsafe lifecycle state; retain evidence and diagnose before another cell |
| Storage | `/tmp/tofa-presentation-validation/runs/130-native-admission-01`; durable private copy under `.qualification/134-manual/evidence/130-native-admission-01` |
| Scores | Task/skill use, actual loader/runtime, owned file integrity, reference syntax, visible PPTX/PDF previews, repetition/recovery and independent naming outcome |
| Start prerequisite | Reviewed/frozen candidate and non-launch preflights, then a separately issued human guide; this draft does not start any attempt |

## Compatibility correction discovered during execution

The installed engine's API-key `login status` diagnostic now uses two lines:
`API key configured - …` followed by `Authentication is checked when you send a
request.` The catalog freshness check previously recognized only the older
`Logged in using an API key…` form. A public-launch regression reproduced the
refusal; the parser now accepts the complete observed new form as well as the
old one, rejecting incomplete or changed diagnostics. This applies to catalog
semantics, including legacy evaluation tests. It does not relax normal Desktop's
separate `account/read` ChatGPT sign-in requirement or add API-key native admission.

The legacy engine-loss regression also had a conflicting deadline: its
five-second process-exit assertion expired at the end of the launcher's existing
five-second native-quit grace, before the two-second termination allowance. Only
that assertion now allows ten seconds, including polling. Both installed-engine
cases pass with shutdown, stale-route rejection, history preservation and resumed
tool execution still asserted. Production shutdown timing is unchanged.

## Executed validation and review

The installed Desktop engine was `codex-cli 0.166.0-alpha.5.1`; the mixed-engine
checks also used the discovered standalone `codex-cli 0.167.1` executable. All
engine work used disposable profiles and owned local upstreams, without launching
the actual Desktop application or performing paid inference.

- The normal/candidate installed-engine race selection passed 149 test/subtest
  events. The subsequent broad installed-engine race run passed 840 events and
  exposed stale authenticated-catalog setup and two signed-out legacy fixtures.
  That failed run remains retained. Corrective race reruns passed all 18 selected
  events, including authentication/freshness controls and both legacy fixtures.
- The catalog fixture now signs its synthetic profile in before the preservation
  baseline. Discovery cannot create credentials or settings. Legacy tests select
  the historical route explicitly; normal signed-in coverage remains separate.
- All five actual mixed-engine preflight scenarios passed. The generated-skill
  receipt test initially rejected a symlink entry point; resolving the discovered
  executable, as the real generator does, made it pass alongside the unchanged
  nonregular-source rejection control. Production receipt validation is unchanged.
- 81 offline skill-contract, collector, guidance, scope and synthetic-response
  tests passed, plus eight workflow/publication tests. Skill-contract tests now
  run through explicit unittest discovery in CI. Direct file execution ran zero
  tests and is excluded from the pass counts. Vet and diff checks passed.
- Independent Standards and Spec reviews of the unpublished integration diff
  from `2c1de54`, and each subsequent correction, found no blocking issue.

The ordinary full race suite and platform CI remain required merge gates; their
final results are recorded on [PR #144](https://github.com/kreuzhofer/tofa-launcher/pull/144).
Installed-engine checks are reported separately from default-suite opt-in skips.
The broader run's ten skipped events included actual Desktop/CLI opt-ins and the
separate mixed-engine selection subsequently executed above. No skipped case is
reported as passed, and no automated result manufactures a human UI observation.
