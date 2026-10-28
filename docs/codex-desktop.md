# Experimental Codex desktop launch

Source-build feature for [#32](https://github.com/kreuzhofer/tofa-launcher/issues/32);
not included in v0.1.0-rc.2.

The production implementation uses **one ordinary desktop profile and history**.
The [reviewed qualification](releases/desktop-shared-history-final-2026-09-24.md)
records passing live streaming/tools, shared history, ordinary send refusal,
relaunch recovery, corrected shutdown and final ordinary-mode preservation for
the pinned combination. Automatic title generation was not observed; the feature
and auxiliary-operation limits below remain experimental.
Earlier isolated/prototype observations below are provenance, not qualification
of the combined workflow.

```sh
go build -o tofa ./cmd/tofa
# Choose Codex desktop, then its main model:
./tofa
# Skip app selection:
./tofa launch codex-desktop
# Explicit selection bypasses the picker:
./tofa launch codex-desktop --model deepseek-ai/DeepSeek-V4.1-Flash
```

Use an existing `tofa auth login`. Omit `--model` in a terminal to choose the main
with the shared arrow-key picker. Enter confirms; Escape or Ctrl-C restores the
terminal without starting the desktop or adapter. Saved preferences never bypass
confirmation. Scripts must supply `--model ID`; an explicit main bypasses the picker.
The selected model must be available in the saved project's catalog.
`--project-id ID` overrides that project.
Availability and bundled provider metadata do not certify a supported combination;
only the two [promoted desktop pairs](evaluation/desktop-comparison-2026-09-29.md)
are supported: DeepSeek V4.1 Flash or GLM 5.3 main with GLM 5.3 Flash Guardian.
Other eligible combinations are always enabled and labelled Experimental. The default Guardian is
`zai-org/GLM-5.3-Flash`; override it with `--guardian-model ID`. Both roles must be
available in the selected project and have compatible bundled metadata. There is
no Guardian picker or automatic substitution. The launcher displays the exact
main/Guardian pair, adapted route and support status before use.

The picker shows supported and experimental pairs together. Support requires
exact adapted main/Guardian evidence; CLI evidence cannot qualify a desktop pair.
Experimental selections launch without an extra flag or confirmation. Esc cancels.
`--allow-unverified` remains accepted for existing scripts but is unnecessary for desktop.
Incompatible metadata disables entries with reasons. Empty catalogs, unavailable
Guardians and provider errors stop before the picker starts.
See the [universal picker contract](model-picker.md).

For example, select DeepSeek with the default GLM Flash Guardian:

```sh
./tofa launch codex-desktop --model deepseek-ai/DeepSeek-V4.1-Flash
# Explicit alternative Guardian:
./tofa launch codex-desktop --model deepseek-ai/DeepSeek-V4.1-Flash --guardian-model moonshotai/Kimi-K3 --allow-unverified
```

Beyond the two supported pairs, metadata-compatible pairs among `zai-org/GLM-5.3-Flash`,
`deepseek-ai/DeepSeek-V4.1-Flash`, `zai-org/GLM-5.3`, `moonshotai/Kimi-K3`, and
`nvidia/Nemotron-3-Ultra-550b-a55b` are experimentally selectable. Each descriptor
uses its own dated provider metadata; text-only candidates do not inherit Kimi's
image capability. Offline routing tests do not qualify live model behavior.
Starting with [rc17](releases/v0.1.0-rc.17.md), naming uses one fixed model,
`nvidia/Nemotron-3_5-Lightning`, for recognized automatic title requests,
independently of launch main, conversation main and Guardian. Changing a main
does not change the naming model. [#111 qualification](research/independent-desktop-naming-2026-10-09.md)
observed generated titles with GLM and DeepSeek, persistence across relaunch and
manual-title preservation on the pinned Mac app. Naming took 6.3–28.2 seconds;
the provisional first-message title can remain visible while generation completes.
The measurements above are from the #111 development build; exact-artifact
checks are recorded separately in the rc17 report. rc16 retains the older route.
The [five-model comparison](evaluation/desktop-comparison-2026-09-29.md) records
main/Guardian outcomes, naming limits, timings, shared costs and promotion provenance.
Main/Guardian support labels cover the pinned headless bundled-engine baseline,
not comprehensive Electron UI or release qualification. See the [offline selection evidence](evaluation/desktop-selection-2026-09-28.md).

### Switching launch modes and recovering a conversation

1. Quit the ordinary desktop, then run the command above from your workspace.
   Keep that terminal open for the entire Token Factory session. Existing native
   conversations keep their provider; new default conversations use the launch main.
2. Quit the owned app and wait for the launcher to exit before opening the app
   normally. Both modes use the same history; no import or synchronization is
   needed. Opening the app while the launcher is active does not change modes.
3. Ordinary mode can display Token Factory history, but cannot send through Token
   Factory. An unavailable-provider or missing-launch-credential error requires
   a fresh tofa launch. Changing the picker to GPT/Astra does not migrate the
   conversation to OpenAI.
4. Quit the ordinary app, rerun the launch command, reopen the **same conversation**
   with any default main. Its recorded main is retained if available. Continue there;
   creating a replacement conversation is not the recovery procedure.

After an abrupt launcher exit, quit any surviving desktop manually before retrying.
Do not delete history, provider metadata, bridge directories or native lock files
to recover. For ownership conflicts or damaged artifacts, follow
[failure recovery](#failure-recovery-48) and
[installed lifecycle instructions](#installed-lifecycle-and-retained-history).

#### Per-conversation selection

Launch with DeepSeek as the initial/default model:

```sh
tofa launch codex-desktop --model deepseek-ai/DeepSeek-V4.1-Flash
```

The desktop picker offers every eligible model available in the selected project,
including GLM Flash, Kimi and Nemotron as Experimental choices. Experimental labels
describe qualification status; no opt-in is required. Models with missing or
incompatible metadata remain disabled with reasons in the launcher picker and
are omitted from the desktop catalog with an explicit terminal notice: the
installed model-list contract has no verified disabled-entry field.

A GLM Flash conversation can continue during this DeepSeek launch. Selecting a
new main within that conversation applies to subsequent turns without changing
its history, title, workspace association or provider. Other conversations retain
their own selections. Changes made during an active turn affect subsequent turns;
cancellation interrupts the current request. The engine retains its approval
policy and pending execution gates.

Desktop default-model, reasoning-effort and service-tier selections are scoped
to that desktop session. They do not overwrite the ordinary CLI defaults during
startup, selection or shutdown. The bridge recognizes the installed client's
model-setting writes, reads the native configuration version without writing,
and returns the explicit `okOverridden` result that makes the desktop retain its
selection locally for the next new conversation. Existing-thread model changes
remain native `thread/settings/update` calls. Other settings writes still go to
the native engine; mixed model/unrelated-setting batches fail without partial
writes. No saved configuration snapshot is restored on exit, so concurrent user
settings changes are retained.

The configured launch Guardian applies to all Token Factory conversations,
including when the same model is also selected for ordinary chat. Native
conversations keep their provider and reviewer descriptors. Choosing a GPT model
does not migrate a Token Factory conversation to OpenAI.

Availability and metadata are snapshotted at launch. Requests for an unavailable
model fail explicitly before provider inference. Check project availability and
relaunch to refresh, or explicitly select an eligible model on the same
conversation. There is no automatic fallback. Provider errors remain visible;
Experimental does not promise a successful live response.

Switching to a text-only model preserves saved image history. The engine replaces
images in that model's inference input with an explicit omission marker; the
launcher prints a context notice. Switching back to an image-capable model makes
the saved images available again. This does not convert or discard attachments.

DeepSeek V4.1 Flash image requests with no `max_output_tokens` receive an explicit
32,768-token limit, announced once in the launcher terminal. It covers reasoning
and answer output combined, including later requests that retain the image in
history. This is a launcher workaround for a reproduced provider default-handling
failure, not the provider's published maximum or the conversation context size.
Explicit limits (including null), text-only requests and other models are
preserved. Native incomplete/error responses remain unchanged. The
[diagnosis](research/deepseek-image-output-limit-2026-10-01.md) retains failed and
successful controls; rc11 does not contain this later correction.

If a smaller context window requires automatic compaction, the launcher rejects
the recognized compaction request before inference. The turn fails explicitly
and saved history remains intact. Select a model with enough context or start a
new conversation. There is no automatic summarization, model substitution or
history truncation to force a switch to succeed. The native configurable
compaction threshold is exercised with synthetic responses in the regression
suite; live behavior near each provider's actual limit is not qualified.

The bundled-engine checks cover model switching, independent conversations,
tool/result continuation, resume under a different default, cancellation and
unavailable-model recovery. The desktop UI still needs direct qualification of
the same interactions; synthetic routing tests do not establish live provider
compatibility for experimental choices.

### Compatibility

The launcher requires macOS **26.6.2 or newer on arm64**, ChatGPT desktop
**26.917.71314 or newer** with bundle ID `com.openai.codex`, and bundled engine
**0.155.0-alpha.16.4 or newer**. Desktop build numbers are not admission gates.
Versions are compared numerically, including engine prereleases. Newer versions
are accepted without a launcher update when the required integration contracts
still work; malformed or below-minimum versions fail with update guidance.

The target is the application's **Codex mode** and requires `/bin/zsh` as the
account's login shell. Discovery checks `/Applications` then `~/Applications`,
with ChatGPT/Codex bundle names. For another location, pass
`--app-bundle '/path/to/ChatGPT.app'`. Discovery supports the older flat engine
and the packaged `codex-cli/CodexCLI.app/Contents/MacOS/codex` layout. An incomplete
package fails explicitly. The native account catalog must match the selected
engine's cache version and freshness requirements.

Identity, executable, configuration, managed-policy, ownership and routing
checks still apply. Exact app/engine versions and hashes identify qualification
evidence; they do not form a fleet-wide version allowlist. Passing admission is
not a claim that every future client or experimental model has been qualified.
The current update investigation is recorded in
[minimum-version compatibility evidence](research/desktop-minimum-version-2026-09-30.md).
Windows and Intel desktop support require separate implementation and qualification.

When a compatible app update moves its engine between these layouts, an ordinary
saved launcher reference resolves the replacement in the same app bundle and
announces the move. Installer upgrades validate the current bundle before
refreshing those references. Their ownership records and shared history remain
intact, including after uninstall.

## Ownership and routing

Quit Codex before launching through tofa. The launcher uses the ordinary desktop
profile at `~/Library/Application Support/Codex` and the ordinary engine history
location resolved through the account's interactive login shell (`CODEX_HOME`,
or `~/.codex`), including startup rules conditional on the desktop's shell-query
environment. It keeps the existing credential store and account/onboarding
files in place. It does not copy credentials, import history, create another
conversation store, or change the current workspace.

An existing desktop causes a refusal with manual recovery instructions. Launcher
attempts serialize using a private lease. The qualified native shell also owns a
profile singleton; the launcher verifies that its newly spawned PID owns it and
receives an authenticated engine-wrapper acknowledgement before publishing live
routing or adding provider metadata. Missing or changed ownership cancels only
that launch. A process scan also refuses live desktops whose native lock is
missing. Native stale-lock recovery is allowed only when the local recorded PID
is demonstrably absent; the launcher never removes native lock/socket/cookie files.

Opening Codex normally while tofa is running reuses the existing app on the tested
client; it does not switch its mode. Quit the app and reopen it normally to return
to ordinary mode. No startup deep link is sent to a possible incumbent.
Unclaimed contenders have a three-second deadline, before the native hung-owner
notification timeout. See the exact-build [ownership evidence](research/desktop-profile-ownership.md)
for the observed collision behavior and limits.

Conflicting inherited Codex/OpenAI/Electron routing variables are removed.
An inherited, nonempty `CODEX_CLI_PATH` must already identify this launcher's
verified bridge; a user-managed executable override is rejected before launch.

The pinned desktop normally reloads an interactive login-shell environment after
startup. A private, per-launch `ZDOTDIR/.zshenv` handles only that exact environment
query, returning the launch-time variables before ordinary startup files can
replace the adapter credential or engine selection. The launcher announces this
behavior. Normal coding-shell commands restore the original `ZDOTDIR` (or its
unset state) and source the original `.zshenv`; normal startup then continues.
User shell files are never edited. This uses zsh's documented
[startup-file ordering](https://zsh.sourceforge.io/Doc/Release/Files.html), with
the environment query pinned to the inspected desktop source.

The bundled engine resolves ordinary configuration and enforced policy before
launch. Incompatible managed requirements and user-owned `nebius-tofa` entries
cause explicit refusal. After native ownership is established, effective live
routing is checked and the engine's version-checked `config/batchWrite` API adds
only the inactive provider entry. A competing edit is an error; cleanup never
restores a whole-file snapshot. Unrelated configuration and edits during the
launch remain intact. The original HOME remains available for native policy
discovery. The checks use the engine's public `config/read`,
`configRequirements/read`, and `config/batchWrite` APIs.

The durable `model_providers.nebius-tofa` entry contains a display name, Responses
wire format, loopback port zero and the deliberately absent
`TOFA_DESKTOP_INACTIVE` credential variable. It contains no live adapter address
or credential. Ordinary mode can hydrate recorded Token Factory history; sending
fails with guidance to relaunch through tofa with any default main. Existing owned
entries from older launches remain accepted unchanged and may still show their
historical original-main or Kimi-specific hint; these older hints are no longer
a model-routing restriction. The ordinary bridge removes both
stale launch and inactive credential variables. Even a directly invoked engine
with an artificially populated inactive variable cannot reach either inference
provider, although its port-zero connection failure may keep retrying until
interrupted. Choosing GPT does not migrate a conversation's provider.

### Native models and conversation routing

Each launch asks the qualified bundled engine for `debug models` **before**
applying Token Factory overrides, in the target engine home and workspace. The
launcher preserves complete native descriptors, including account-dependent
availability, reasoning choices, instructions and unknown fields. It appends every
eligible Token Factory main, displayed with `(Token Factory)` for supported
choices and `(TF Experimental)` for experimental choices. Nemotron uses the
short desktop name `Nemotron 3 Ultra`, retaining its full model ID. The launcher
neither reconstructs descriptors from the lossy `model/list` picker response nor ships a frozen native snapshot. Empty,
malformed, duplicate or conflicting model identities cancel the launch.

The qualified engine's export uses `OnlineIfUncached`: eligible signed-in accounts
use a cache with a **five-minute TTL**, scoped to client version and provider/auth
identity; a miss triggers native catalog discovery. Synthetic tests verify fresh
cache reuse and refresh after expiry, an identity mismatch or a version mismatch.
Unauthenticated and API-key exports use the engine's normal bundled metadata; this
version's debug command does not enable API-key remote discovery. Native picker
filtering still belongs to the engine and its current account.
[Export implementation](https://github.com/openai/codex/blob/4607249e430dac1c961df4dc615beae88e33cec8/codex-rs/cli/src/main.rs),
[cache contract](https://github.com/openai/codex/blob/4607249e430dac1c961df4dc615beae88e33cec8/codex-rs/models-manager/src/cache.rs).

A synthetic authenticated HTTP 401 demonstrated that `debug models` can return
bundled metadata with exit status zero and no stderr. The launcher therefore also
uses the engine's `login status` boundary. For a ChatGPT account, the export must
match a fresh, versioned native cache; missing, stale or inconsistent evidence
causes an explicit freshness error. A fresh cache belonging to a different account
can happen to match the engine's bundled fallback. Because the export API provides
no refresh-success attestation, signed-in exports identical to `debug models
--bundled` are also refused, even when an account genuinely receives that full
catalog. This conservative compatibility limit is reported explicitly.
The comparison accounts for the export-only
legacy `base_instructions` projection; the merged descriptor itself is unchanged.
Diagnostic-bearing exports and unrecognized login states also fail explicitly.
The launcher does not print native diagnostics, inspect credentials, or copy them.
A signed-in static custom catalog without matching fresh cache evidence is
currently refused; it must be qualified before shared-profile integration.

The resulting override is a **snapshot for this launch**. The engine's static
catalog manager does not hot-reload it or perform remote refresh while it is
active. Relaunch after account, entitlement or catalog changes; this limitation
is printed at startup. A later launch resolves native metadata again. Existing
account files and native provider settings remain the engine's responsibility.
[Static catalog selection](https://github.com/openai/codex/blob/4607249e430dac1c961df4dc615beae88e33cec8/codex-rs/model-provider/src/provider.rs).

Cold resume with null model/provider retains the recorded identity. A native Astra
thread continues through its native provider during a tofa launch; a new default
thread identifies `nebius-tofa` and the selected main. A Token Factory conversation
with a different recorded main continues on that model when it is eligible in the
current project. The picker changes a model, not its provider; it does not migrate
a conversation to OpenAI.

Every added main descriptor selects the launch Guardian via
`auto_review_model_override`. Recognized review requests must use that Guardian
and the verified review schema, tools and request options. Ordinary chat requests
may independently select any eligible main, including the Guardian model itself.
Native descriptors and reviewers are unchanged.
The launcher does not enable **Approve for me**, change managed policy, fabricate
assessments, or bypass the engine's decision parser and execution gates. Only Kimi
review requests receive the existing schema-to-instructions adaptation; other
Guardians retain the native schema unchanged.

Native auxiliary choices such as `codex-auto-review` remain unsupported on the
Token Factory route, with an HTTP error and terminal notice. Catalog visibility
does not expand auxiliary routing. Unknown title shapes and compaction remain
unsupported; provisional first-message titles are not generated-title success.

The engine retains its own retry and deadline behavior. Controlled tests observe
three review attempts for an invalid assessment and four for a 503 stream failure;
the adapter adds no retries, replay, fallback, or deadline extension. These native
attempts must be counted separately during later paid qualification.

The [#46](https://github.com/kreuzhofer/tofa-launcher/issues/46) catalog behavior
is integrated with the ordinary profile by
[#47](https://github.com/kreuzhofer/tofa-launcher/issues/47).
The [#50 qualification](releases/desktop-shared-history-final-2026-09-24.md)
records authorized live-account checks of native picker/full-descriptor parity,
fresh catalog resolution on relaunch, native continuation, account/onboarding
continuity and same-conversation recovery. No live entitlement change was induced;
synthetic account/cache/HTTP variations remain distinct from that evidence.
The [initial qualification attempt](releases/desktop-shared-history-2026-09-24.md)
found a signed-in ordinary profile with a static custom catalog and no matching
account-cache evidence. Such a profile remains outside the accepted launch
contract; refreshing models alone cannot qualify a static catalog. Review that
ordinary configuration explicitly before retrying, or use `launch codex`.
The launcher does not remove user catalog settings to make its checks pass.
The [follow-up diagnosis](research/desktop-native-catalog-diagnosis.md) reproduced
this refusal with the current engine: a static `model_catalog_json` override
bypasses native discovery. The freshness error now points to that setting.
To restore native discovery, explicitly review whether the ordinary override is
still wanted; removing it is a user configuration decision. Deleting the cache
alone does not resolve the static override.
After the maintainer authorized commenting out that one ordinary setting, the
[live native-account preflight passed](research/desktop-native-catalog-diagnosis.md#authorized-ordinary-profile-recovery--1322-utc).
The subsequent [#50 qualification](releases/desktop-shared-history-final-2026-09-24.md)
completed the required UI walkthrough and scoped production-path inference checks.

### Durable engine bridge

The desktop receives a stable `CODEX_CLI_PATH` under
`<tofa-config>/desktop-bridge-v2/<SHA-256-of-absolute-bundled-engine-path>/tofa-desktop-engine`.
The bridge is a private executable copy of the launcher, with a sibling
`owner.json` recording contract version 2, the absolute bundled engine path, and
the bridge executable's SHA-256. The record contains no credential or live route.
The executable dispatches to bridge mode by its fixed filename; it does not
depend on the original source-build executable remaining in place.

Normal launch cleanup retains this directory. Saved tool references therefore
remain executable. With no `TOFA_DESKTOP_CONTEXT`, the bridge executes the recorded
bundled engine with the caller's ordinary settings, arguments, and exit status.
It removes `TOFA_API_KEY` and `TOFA_DESKTOP_INACTIVE` from that ordinary invocation. Ordinary account
credentials and `HOME` are preserved.

During a launch, `TOFA_DESKTOP_CONTEXT` names the current loopback adapter and
`TOFA_API_KEY` authenticates the bridge's `GET /desktop-launch` request. The route
exists only in launcher memory, binds the bridge, engine, and ordinary
`CODEX_HOME`, and is served with `Cache-Control: no-store`. No on-disk capability
manifest is needed. Empty, malformed, unauthenticated, mismatched, or expired
context is an explicit error with relaunch guidance, even for `--version`;
it never selects ordinary mode. The client permits only IPv4 loopback HTTP,
disables proxy discovery and redirects, and bounds the request time and size.

For `app-server`, the bridge appends live routing overrides at the subcommand's
argument boundary, after desktop/plugin overrides and before any `--` separator.
Other arguments retain their order and values. Startup preflight asks the actual
engine for effective routing and managed policy while the bridge waits for
ownership qualification. Inference is refused until that qualification completes.
The real Token Factory key stays in the launcher. Only the temporary local bearer
reaches the owned desktop, and neither it nor the context is an argument or a
durable bridge setting. Each launch creates a new adapter and bearer.

Initial installation claims a new private directory. Existing records and
executables must match before reuse; missing, edited, or symlinked ownership is
an explicit conflict, never permission to overwrite another executable. A setup
write failure removes only the directory created by that attempt. A fully
installed bridge remains usable even if subsequent desktop setup fails.

Version 2 adds the startup ownership acknowledgement and installs alongside
version 1. New launches use version 2. Installation, supported upgrades and source
launches refresh verified helpers without changing their saved paths. Installed
upgrades also preserve version-1 references. Moving/removing the bundled application
causes an explicit execution error; a launch from a new bundle path gets a distinct
owned bridge. Do not delete bridge directories as ordinary session cleanup.

### Installed lifecycle and retained history

The macOS installer uses its checksum-verified candidate to coordinate existing
desktop integration. It checks every bridge and the qualified client version before
changing helpers, and installs the main executable only after helpers are usable.
Install, uninstall and purge hold the ordinary-profile launcher lease and refuse a
native desktop owner, an incumbent desktop process, a competing launcher, or an
unresolved runtime owner. Quit the owning desktop/launcher and retry; these operations
never signal another owner's process or change its singleton files.

Records with `LifecycleVersion: 1` identify helpers that can coordinate standalone
removal. The script verifies their recorded digest before executing them, including
when the main installed binary is broken. Legacy helpers can be upgraded by a
compatible installed launcher; if neither exists, reinstall a compatible release.

Bridge replacement uses a write-ahead `PendingSHA256` in `owner.json`, followed by
an atomic executable rename and a final ownership-record write. Either executable
is verifiable after an interrupted replacement. Retrying completes the transition;
a failed upgrade can leave an updated helper beside the previous main executable,
with ordinary delegation intact. Missing, edited, symlinked or unknown-version
artifacts stop the operation. Restore the matching executable/record from a trusted
copy, or inspect and move conflicting artifacts aside before reinstalling. An
interrupted first bridge installation has not published a saved reference yet;
its incomplete directory is likewise an explicit conflict, never automatically
claimed or deleted. Incompatible clients require restoring the qualified application
or uninstalling to detach integration before proceeding.

Normal uninstall and `--purge` **detach** verified bridges rather than deleting
paths that the desktop may have saved. The retained executable and ownership record
are self-contained: they do not depend on the removed main launcher. `Detached`
disables all launch-context routing, including stale or forged context, with
reinstallation guidance. Ordinary calls still delegate to the recorded bundled
engine, scrub both launcher credential environment variables, and preserve ordinary
arguments, settings and exit status. A retained bridge can coordinate repeated
standalone uninstall/purge after the main executable has gone. Reinstallation or a
qualified source launch refreshes and reattaches it. No live adapter, endpoint or
launch bearer is retained. Known abandoned launch directories are cleaned only after
their owners are proven dead; unknown artifacts stop removal for inspection.

Removal does not edit the ordinary engine configuration or desktop tool settings.
The retained non-secret `model_providers.nebius-tofa` definition supplies the provider
identity/name and `responses` wire protocol needed to hydrate existing history. Its
unusable `http://127.0.0.1:0` URL and missing `TOFA_DESKTOP_INACTIVE` credential prevent
inference; the explicit recovery instruction, disabled OpenAI auth/websockets and
zero retry limits keep unavailable inference bounded and observable. No former
adapter address, launch key, or ordinary account credential is in that definition.
User-edited provider settings remain user-owned and are retained unchanged.

Both removal modes preserve conversations, account credentials, onboarding, workspace
files and unrelated settings. Normal uninstall retains saved launcher preferences and
Token Factory credentials under the existing CLI contract; `--purge` removes those
saved launcher credentials, not ordinary account state. Retained bridge metadata and
inactive provider information are non-secret and survive purge for history access.

The real Token Factory key stays inside the launcher. The owned client gets only
a random per-launch bearer token for an authenticated IPv4 loopback adapter.
Only the selected model and `POST /responses` are accepted. Streaming and existing
history repair are retained. No auxiliary model is silently remapped. Rejected
auxiliary routes/models, schema failures and upstream HTTP errors are reported in
the terminal without request bodies or credentials.

Keep the terminal running. Closing the owned app, Ctrl-C/SIGTERM, adapter failure,
or loss of the owned app-server ends the launch and closes its listener. A stuck
owned process group receives a forced stop after two seconds. The startup deadline
for observing the bundled app-server is 15 seconds. Only that new process group
is signaled; ordinary desktop processes are not targeted.

Ordinary history, Electron state and workspace files remain in their original
locations after exit. Only private preflight/control files under
`<tofa-config>/desktop-launches/launch-*` and the temporary model catalog are
removed. The durable bridge and inactive provider remain; the old listener and
bearer become unusable. Prior isolated `desktop-sessions` are left untouched and
are not automatically imported.

The [#34 contract check](research/desktop-shared-history.md) established the
accepted limitation: Token Factory access lasts only while the launcher runs.
Shared-history engine and launcher tests pass, with
[scoped real-account UI qualification](releases/desktop-shared-history-final-2026-09-24.md)
recorded for #50. Abrupt-launch recovery and
installed lifecycle behavior are described below and above, respectively.

## Limitations and verification

The [#55 implementation checks](releases/desktop-model-routing-2026-09-30.md)
record per-conversation routing, capability changes, CLI-default isolation and
the remaining Electron UI qualification.

The naming route included in rc17 recognizes the captured `gpt-5.6-luna` and
`gpt-6-luna` title requests by both source markers, exact title schema and tool
inventory. It sends those requests to `nvidia/Nemotron-3_5-Lightning` as tool-free
naming, retaining the prompt and structured-output schema. Live qualification found
that Lightning rejects namespace tools, `include`, `reasoning` and `prompt_cache_key`.
The naming route omits those fields and uses provider-default reasoning; the
launcher announces this policy. Main, Guardian, native
catalog descriptors and CLI title routing remain unchanged. There is no naming
picker, configurable fallback, or automatic substitution.

The naming model must appear in the project's launch-time catalog and have
compatible dedicated provider metadata. If unavailable, naming fails explicitly
while main conversations remain usable. Changed title contracts and upstream
errors are surfaced; provisional first-message titles are not generated-title
successes. The desktop still validates and persists titles under its existing
rules, including manual-title protection. Client cancellation propagates upstream;
this work does not increase the desktop's naming deadline.

The [#111 qualification record](research/independent-desktop-naming-2026-10-09.md)
records passing live provider/engine and operator-confirmed Mac UI checks, including
persistence and manual-title preservation. The 28.2-second GLM naming result was
close to the unchanged native 30-second deadline; broader reliability is unqualified.
rc16 retains the older Kimi-only route.
The [#52 report](research/desktop-shared-title-generation.md) records historical
Kimi generation and persistence; it is not evidence of Lightning behavior.

The recognized non-strict automatic-review workaround remains unchanged. Native
auxiliary requests outside the captured title contract, compaction endpoints, web search, account-backed services, and
Chat/Work/voice are not qualified. The public `--guardian-model` selects the reviewer. No `--direct`, evaluation-only
flag alias, profile, or arbitrary desktop argument passthrough is exposed.

Offline executable/HTTP tests cover shared-state preservation, credential separation, selected
model streaming, auxiliary rejection, managed/effective routing conflicts, startup
and exit errors, engine loss, cancellation, adapter failure, and owned-worker cleanup.
They reproduce the desktop's zsh environment query, including conflicting shell
exports and normal coding-shell startup with default/custom `ZDOTDIR`.
The desktop executable tests run on the exact gated macOS/architecture combination;
other hosts skip them. Portable launcher/adapter regressions still run normally.
To additionally exercise the actual bundled engine against dummy offline settings:

```sh
TOFA_TEST_DESKTOP_ENGINE=/Applications/ChatGPT.app/Contents/Resources/codex \
  go test ./internal/tofa -run '^TestDesktop' -count=1
```

This optional test starts the real engine but a fixture desktop executable; it does
not perform paid inference. Its bridge regression completes a synthetic turn
through the authenticated request adapter and checks the upstream model and
credential, including conflicting app-server routing and unrelated plugin
overrides. This proves fixture routing, beyond merely avoiding paid inference.
The earlier human-operated streaming/tool/continuation
proof and its limitations remain in the [feasibility evidence](research/codex-desktop-feasibility.md).

An additional opt-in test starts the installed Electron app with dummy credentials,
synthetic conflicting shell exports and fresh state, checks the owned bundled
engine's temporary credential against a local fixture, then stops the owned app:

```sh
TOFA_TEST_DESKTOP_APP=/Applications/ChatGPT.app \
  go test ./internal/tofa -run '^TestDesktopInstalledAppShellIsolation$' -count=1 -v
```

This passed on the updated pinned combination on 2026-09-24. It uses disposable
HOME, Electron and engine state, a test-only mock keychain and disabled updater.
It uses no paid inference;
it verifies that shell-exported credentials and an engine override do not reach
the actual desktop engine. It does not claim another live-model coding session.

### Live source-build check, 2026-09-23

The user completed three turns in one isolated conversation using this launcher:
a real `exec_command` ran `printf tofa-desktop-32-ok`, a second turn recalled that
marker, and a third requested a longer prose response. The user reported that the
longer answer appeared to stream; streaming was unclear on the short answers.
The owned session record independently contains the tool call/result and three
completed turns. No live wire-event counts were recorded. Cumulative session usage
was 41,558 input tokens (including 30,976 cached) and 342 output tokens.
[Sanitized evidence](research/evidence/codex-desktop-launch-2026-09-23.json).

The first live attempt exposed a command-shape bug: the desktop places `-c`
options before the `app-server` subcommand. The launcher stopped its own instance
after failing to recognize it. An executable regression reproduced the issue;
the corrected detector accepted the live app and remained attached for all three
turns. Automatic title generation failed explicitly, as announced.

After interruption, all 12 observed owned processes exited, the adapter port
closed, and temporary routing/catalog files were removed. Conversation and
workspace files remained. The ordinary app/engine PIDs stayed alive; ordinary
`config.toml` content and metadata and `auth.json` stat metadata were unchanged.
Ordinary credential contents were not read. This preservation check does not
claim a separate functional test of ordinary account-backed inference.

Final validation passed: `go test -race ./...` (including the optional installed-engine
check), `go vet ./...`, Linux/Windows amd64 cross-compilation, and the two native
terminal smoke tests. Independent standards and spec reviews reported no findings.
The race suite found an output-writer race after the live check; a per-launch mutex
fixed it, and the full suite passed on rerun. The evidence pins the live binary
before that output-only correction.

### Bridge validation, 2026-09-24 (#45)

Before the fix, the saved-reference regression failed because the desktop had no
durable launcher-owned executable to save. The bundled-engine regression then
reproduced displaced live routing when app-server overrides selected `openai`.
After the fix, a saved bridge executes after cleanup; ordinary settings and exit
status survive; expired/malformed/mismatched contexts fail; relaunch preserves the
bridge while rotating credentials and endpoints. Ownership-conflict and actual
file-size-limit write-failure tests cover safe setup. The fixture's retained tool
settings, history, and bridge artifacts are checked for live capability leaks.

The local app auto-updated to engine `0.155.0-alpha.16.3` during this work. Engine
tests used a retained `0.155.0-alpha.9.2` executable from the earlier isolated
prototype's plugin directory. The production version gate remains unchanged.
This evidence qualifies the bridge at the executable/HTTP and bundled-engine
boundaries; it does not qualify the updated Electron app or ordinary-profile
history. All credentials and inference responses in these checks are synthetic.

Final checks passed: the complete `go test -race ./...` suite with the qualified
engine enabled, `go vet ./...`, and Linux/Windows amd64 builds. Separate standards
and spec reviews have no remaining findings after correcting argument-value
detection and removing duplicate test setup.

### Native catalog validation, 2026-09-24 (#46)

Regressions first reproduced the Token Factory-only catalog at the launcher and
actual-engine picker boundaries, then reproduced authenticated discovery silently
falling back after HTTP 401. Review found and reproduced the additional case of
a foreign-account cache containing bundled-equivalent descriptors. The corrected
launcher rejects both failures, with an explicit conservative refusal when even a
successful account catalog is indistinguishable from the bundled fallback.

Checks use synthetic credentials, temporary profiles and separate native and
Token Factory HTTP fixtures. The retained engine is **0.155.0-alpha.9.2**, SHA-256
`9280c0754e8f1f6b72f495d30c8c82a006dbc4995bf0492916fa0901f6bfd1f9`, on macOS
**26.6.2 arm64**, compiled with Go **1.27.1**. The installed app has since updated;
these checks do not change the production gate or qualify that newer app.

Native cold resume, new Token Factory identity, explicit Astra failure, same-thread
Kimi recovery, native auxiliary rejection, descriptor preservation and native
cache/account scenarios passed. Separate Standards and Spec reviews reported zero
remaining findings after the freshness correction. No installed Electron UI,
ordinary live account or paid inference was exercised for this ticket.

Final validation passed: `go test -race ./...` with `TOFA_TEST_DESKTOP_ENGINE`
pointing to that retained executable, `go vet ./...`, and Linux/Windows amd64
builds. The opt-in installed-Electron check was not enabled.

### Shared profile validation, 2026-09-24 (#47)

The missing-provider regression reproduced ordinary resume failing before inactive
metadata was added. The production launcher now completes ordinary → tofa →
ordinary → tofa and repeated relaunches through the actual alpha.16.4 engine.
Public APIs verify two unique identities, ordered messages and an executed
`printf` command/result, titles, workspace, native routing, inactive send failure,
and same-thread recovery with a fresh launch. The full tool-history test uses the
updated client's paginated history contract; legacy hydration omits those tool
items. Synthetic native and Token Factory HTTP fixtures verify which route is used.

Launcher regressions cover existing owners, missing native locks, competing
launchers, ownership loss or owner exit before integration, version-conflicting config edits,
and preservation of edits during a launch. An actual installed-desktop startup
check verifies the native ownership/bridge handshake and working local credential.
Five separate native diagnostics cover both launch directions, simultaneous
starts and native stale-state recovery. Run them separately from launcher tests:
ordinary diagnostic launches intentionally trigger the launcher's incumbent
refusal. The evidence also retains one concurrent native-quit timeout. [Build provenance and sanitized evidence](research/evidence/desktop-profile-ownership-2026-09-24.json).

These checks use synthetic credentials and disposable profiles. They do not claim
real-account onboarding continuity, an observed UI history walkthrough or paid
Token Factory inference on this combined implementation. Historical #32/#45/#46
results above retain their original versions and scope.

Final checks passed: `go test -race ./...` with both installed-engine and
installed-desktop opt-ins, `go vet ./...`, Linux/Windows amd64 builds, three
installed-engine history diagnostics and five installed-native ownership
diagnostics. The final Go and native suites ran sequentially. Independent
Standards and Spec reviews have no remaining confirmed findings.

## Failure recovery (#48)

Startup distinguishes native profile ownership from engine bridge readiness. An
unclaimed launch is still stopped after three seconds to avoid adopting or
displacing another app. If the launcher-created process already owns the native
profile, its bridge has up to 15 seconds total to authenticate. Ownership is
monitored during that wait; cancellation, ownership loss or a stalled bridge
stops the owned process group. See the [timeout diagnosis](research/desktop-handshake-timeout.md).

The adapter and its in-memory routing record belong to the launcher process.
Normal exit, cancellation, engine loss and adapter failure stop only the spawned
process group, close its listener, and remove its runtime directory. SIGKILL of
the launcher also closes the adapter at the OS boundary: an orphaned desktop
cannot keep using Token Factory. A present expired, empty or malformed launch
context is an error, including when invoking the saved durable engine bridge;
it never becomes an ordinary invocation.

After abrupt launcher death, **quit any surviving desktop manually**, then run
the same tofa launch command. The launcher refuses a surviving desktop, including
one whose native profile lock is missing. It does not signal a PID found in an
abandoned record or adopt that process. Once the desktop has exited, the qualified
native client handles its proven-stale singleton lock as before.

Each new runtime directory under `desktop-launches/` has a private, non-secret
`owner.json` containing its format version, launcher PID and ordinary profile
path. The model catalog now lives inside that directory alongside the shell and
preflight artifacts. While holding the ordinary-profile lease, relaunch removes
an abandoned directory only when its ownership record matches that profile and
the recorded launcher PID is demonstrably absent. A possibly live PID (including
PID reuse) retains the directory. Another profile's artifacts are retained.
Unknown, malformed, missing or symlinked ownership records and symlinked runtime
directories are retained with a diagnostic for manual inspection. This includes
older unmarked runtime directories; recovery does not guess ownership of old
catalog files in the system temporary directory. The native lock and durable
launcher lease are never deleted by recovery.

Recovery does not restore shared configuration snapshots or delete history,
ordinary credentials, workspace files, or the inactive provider definition.
Relaunch supplies a fresh bearer and endpoint; an old bearer cannot authenticate
to the new adapter. Runtime ownership records are never accepted as launch
capabilities.

The executable/HTTP regression first reproduced runtime-directory and catalog
leaks after SIGKILL, then verified recovery, repeated relaunch, stale-context
rejection, credential rotation, live-owner refusal, and preservation of unknown
artifacts and files outside the owned directory. The public installed-engine
history regression exercises normal exit, cancellation, engine loss, adapter
failure, startup failure and abrupt launcher death. It checks unique thread IDs,
ordered messages and tool results, titles, workspaces, ordinary inactive sends,
and continuation in the same thread after relaunch, with synthetic credentials
and inference only. Installed Electron UI, live accounts and paid inference
remain separate opt-in qualification; these tests do not establish those claims.

Validation on macOS 26.6.2 arm64 with Go 1.27.1: the full
`TOFA_TEST_DESKTOP_ENGINE=/Applications/ChatGPT.app/Contents/Resources/codex go test -race ./... -count=1`
run passed (225 test cases, 3 opt-in skips), as did `go vet ./...`, Linux amd64
and Windows amd64 cross-builds, offline installer tests, and native installation
lifecycle/terminal tests against a binary built from this change. The skipped Go
tests were the two opt-in installed Codex CLI tool/approval-review checks and
`TestDesktopInstalledAppShellIsolation`. Native Linux/Windows execution, installed
Electron UI, live-account and paid-inference qualification were not run.

### Installed lifecycle qualification (#49)

The local-release regression installs an actual compiled launcher into a temporary
home, upgrades saved version-1 and version-2 references, invokes CLI uninstall,
reinstalls, and runs standalone uninstall/purge repeatedly, including with a broken
main executable. It verifies ordinary argument/exit-status delegation, retained
reference usability, ordinary account and onboarding bytes, shared configuration,
tool settings and workspace preservation, plus removal of saved launcher credentials
on purge. It refuses native/launcher owners, another profile's runtime owner,
incompatible clients, missing/edited/unknown-version ownership, partial initial
installation, symlinked integration and user-edited recovery executables.

A real file-size-limited child reproduces executable replacement failure after the
ownership journal has been written. Saved references remain callable both then and
in the persisted state immediately after rename; retry completes removal. The public
bundled-engine history driver also verifies list/read/resume and unavailable sends
after normal uninstall and purge, preserving thread identities, ordered messages
and tool results, titles and workspaces. These checks use synthetic account and
inference fixtures only.

The standards and specification reviews found an unsupported lifecycle-version
acceptance bug. An executable-boundary regression reproduced it, and strict version
validation fixed it; both reviews then reported zero remaining findings.

An initial full race run hit the existing three-second installed-Electron ownership
handshake timeout while other build/check work was running. The same test then passed
four consecutive isolated runs, with the last three completing in approximately
1.7 seconds each. The cause of that timing-sensitive failure was not established;
the startup deadline was not changed. Native startup checks do not establish the
real-account/UI acceptance or paid-inference qualification tracked separately in #50.

Final validation passed on macOS 26.6.2 arm64 / Go 1.27.1 with ChatGPT
26.917.71314 (10954), bundled engine `0.155.0-alpha.16.4`:

- Full `go test -race ./... -count=1` with both `TOFA_TEST_DESKTOP_ENGINE` and
  `TOFA_TEST_DESKTOP_APP` set to that installed application, rerun without concurrent
  builds (232 seconds for the launcher package).
- `go vet ./...`, shell syntax validation and diff whitespace checks.
- Both offline installer tests and all four native local-release lifecycle checks.
- Linux amd64 and Windows amd64 cross-builds.

The two separate installed Codex CLI inference/tool-review opt-ins were not enabled.
Cross-builds do not establish native Linux/Windows runtime qualification.
