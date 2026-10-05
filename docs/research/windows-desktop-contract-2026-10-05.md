# Windows ARM64 desktop contract — 2026-10-05

Research outcome for [#76](https://github.com/kreuzhofer/tofa-launcher/issues/76):
the installed desktop and its selected engine are ARM64 and ordinary native
activation works. A Windows tofa desktop route is **not yet qualified or ready
for production implementation**. The installed source offers an engine override,
but that route changes the Windows packaged-sandbox context. Profile ownership,
bridge execution, approval enforcement and recovery still need a bounded prototype.
Keep [#77](https://github.com/kreuzhofer/tofa-launcher/issues/77) gated on those
observations and retain the current explicit Windows desktop rejection.

This is a research change, not a port. No support record, launcher behavior,
credential, managed policy or installation was deliberately changed. The normal
app was opened; its own startup may write native state. No claim of byte-for-byte
native-state preservation is made. No private conversation was opened, and no
screenshots, chat bodies or ChatGPT account identifiers are included in the evidence.

## Frozen environment and evidence

Repository baseline: `f84e6e4550199a707d1f6149a01308e8deb0a7ba`.
UTM 4.7.5 operated the existing running Windows 11 Pro ARM64 guest, build
`10.0.26200` (CIM CPU architecture 12). No restart, clone, snapshot replacement,
package installation or destructive qualification was performed.
[Inventory](evidence/windows-desktop-2026-10-05/inventory.json).

| Identity | Observed value |
| --- | --- |
| Interactive-user package | `OpenAI.Codex_26.930.2377.0_arm64__2p2nqsd0c76g0`, status OK/0 |
| Other all-users package | `26.930.6422.0`, numeric status 1024; not selected by the user's package query |
| Manifest display / activation | ChatGPT; `OpenAI.Codex_2p2nqsd0c76g0!App`; `app/ChatGPT.exe` |
| Manifest OS floor | `10.0.19041.0`; not a tofa minimum-version decision |
| Packaged JavaScript version | `openai-codex-electron` `26.930.21537` |
| Bundled and selected engine | `codex-cli 0.159.0-alpha.12.1` |
| PE machine | `0xAA64` for app launcher, bundled engine and sandbox service |
| Engine selected by ordinary app | `%LOCALAPPDATA%\OpenAI\Codex\bin\5c1982dfef3b03a5\codex.exe` |
| Selected-engine SHA-256 | `fcdd6134ddd030fa4ec05779513a94290c7317796f0641add72c5e8ad978f8b4`, identical to bundled engine |
| Native service | `CodexSandboxService.OpenAI.Codex`, LocalSystem, separate from the interactive app |

Sources: [user-context registration](evidence/windows-desktop-2026-10-05/user-probe.json),
[PE types and hashes](evidence/windows-desktop-2026-10-05/narrow.json),
[process topology](evidence/windows-desktop-2026-10-05/tasks.json),
[version/protocol result](evidence/windows-desktop-2026-10-05/engine-probe.json),
[relocated-engine hash](evidence/windows-desktop-2026-10-05/cleanup.json).
The app executable's `154.0.8037.93` file version is not the package or engine
version. None of these observations is an emulated amd64 qualification.

The inspected vendor-code and manifest bytes are identified by
[SHA-256](evidence/windows-desktop-2026-10-05/installed-source-hashes.json).
Vendor code is retained only in local scratch `/tmp/tofa76`, not redistributed.
The separate [official-source audit](windows-desktop-primary-sources-2026-10-05.md)
records dated documentation hashes, the currently offered Arm64 MSIX route,
entitlements and managed configuration. Current documentation redirects to
ChatGPT Learn; those pages do not prove behavior of this installed build.

## Documented, source-observed and runtime-observed contracts

**Discovery and launch (observed).** Query package registration for the interactive
user, not the highest all-users version. `utmctl exec` runs as SYSTEM; an
Interactive/Limited scheduled task queried the actual user's registration.
Normal AppsFolder activation opened the Codex surface in ChatGPT, with an existing
signed-in account, local-computer target and ordinary conversation titles visible.
The account menu was inspected without changing login. This proves an existing
login can open this UI; it does not prove paid model entitlement, first-use login,
managed-workspace permissions or a Token Factory desktop conversation.
The activation task itself returned 1 despite the visible app/process result;
submission or task status alone must not decide UI success.
[Observations](evidence/windows-desktop-2026-10-05/observations.json).

**Engine discovery and override (installed source).** In
`application-network-startup-DN7Ktmlk.js`, `Zs`/`Qs` select an explicit
`CODEX_CLI_PATH` or configured command before normal engine discovery. `$t`/`Gt`
resolve a registered core or relocate WindowsApps executables to a versioned
user-local directory. The observed app used that relocated engine, rather than
executing the package path directly. Overrides are a build-observed contract,
not a public stable API promise. Windows filename casing, `.exe` handling,
package identity and update relocation require explicit tests.

**Sandbox and Guardian (blocking source finding).** `Gs` in the same module
removes `CODEX_WINDOWS_REGISTERED_CORE` for an override and removes
`CODEX_WINDOWS_SANDBOX_PACKAGE_FAMILY` for an override/nonmatching engine.
It only adds `features.windows_sandbox_service=true` for the recognized core
route. A bridge cannot assume the sandbox-service path survives the override.
This does not prove the override is prohibited or unsafe: it establishes a
contract that must be measured. Do not manufacture package identity, reinsert
private service markers, disable sandboxing, or weaken approval policy to pass.
The service's existence is not evidence that this launch used it. Native
allow/deny execution tests must precede any Guardian support claim.

**Engine protocol and provider (runtime).** A limited user task ran the exact
selected engine in an empty temporary `CODEX_HOME`, ephemeral credential mode,
and a synthetic Responses provider at a non-listening loopback port. No turn or
inference request was sent. Version exited 0; initialize reported Windows/aarch64;
`config/read` reflected the requested main/provider; `configRequirements/read`
returned no requirements; `account/read` returned no account and did not require
OpenAI authentication. EOF shut the engine down with exit 0.
The **attempt as a whole failed** because Windows held `stderr.txt` during
immediate temporary-directory cleanup. A later scoped cleanup removed the exact
failed home successfully. This is headless configuration evidence, not streaming,
catalog, Guardian, tool, desktop-bridge or clean-lifecycle qualification.
[Exact probe](evidence/windows-desktop-2026-10-05/engine-probe-attempt.py),
[result](evidence/windows-desktop-2026-10-05/engine-probe.json).

**Catalog, model writes and reviewer flow (installed source/schema).** The same
hashed `bootstrap-CYu4H4X5.js` supplies `listModels` (character offset 1401626),
which sends native `model/list` and surfaces protocol errors. Its service-tier
lookup (868796) requests hidden models and matches the current model against
`model` or `id`. The generated `v2/ModelListResponse.json` describes `hidden`,
`isDefault` and `supportedReasoningEfforts`. The app-server list is a picker
projection, not the full descriptor needed to construct a static catalog.
The launcher's existing macOS catalog injection uses engine `debug models`,
merges descriptors and passes `model_catalog_json`; that implementation is a
Windows probe hypothesis, not inherited support.

The installed bootstrap `loe.writeModel` (869791) sends `config/batchWrite`
with paired `model` and `model_reasoning_effort` upserts, optionally prefixed
with `profiles.<name>.`, and `filePath=null`, `expectedVersion=null`,
`reloadUserConfig=true`. This is a durable-config write boundary; it must be
contained for tofa desktop defaults. The exact engine's generated
`ConfigBatchWriteParams` says reload does not refresh session-static model and
reasoning defaults. That does not prevent a persisted change affecting a later
CLI session. Its thread settings schema separately exposes per-thread changes;
bootstrap's `updateThreadSettingsForNextTurn` callers use model/effort for the
conversation. Therefore intercepting default writes and retaining thread-specific
choices remain separate obligations under ADR 0003. No ordinary config write
was sent in this investigation.

For Guardian, installed `main-Dn18kdv3.js` `Ol` (around 187500) computes an
approval mode from native config and allowed policies/reviewers; its automation thread-start
request (198215) carries `approvalsReviewer` and sandbox policy. Bootstrap
`eoe` (866623) filters approval/sandbox/Guardian keys from a copied config path,
so injecting those fields into arbitrary conversation config is not a reliable
routing contract. Generated thread start/resume, turn start and settings-update
schemas expose `approvalsReviewer`; active-turn changes explicitly leave already
captured steps/pending approvals with their original reviewer. Notifications
carry `automaticApprovalReview` items that the bootstrap surfaces. These trace
the native reviewer selection and display flow, **not** the Nebius review payload
or execution decision. Tofa's existing descriptor `auto_review_model_override`
and adapter review recognition still need installed-engine allow/deny execution
proof, together with the Windows sandbox-context checks above.

[Version-specific schema observation](evidence/windows-desktop-2026-10-05/schema-probe.json)
was generated successfully by this exact engine in an isolated SYSTEM home,
without account/inference, and temporary cleanup passed. It establishes schema
shape, not interactive-account authorization. Offsets above index the decoded
UTF-8 JavaScript strings; source hashes disambiguate minified symbols.

A subsequent [limited-user static catalog probe](evidence/windows-desktop-2026-10-05/catalog-final-probe.json)
passed with engine exit 0 and successful temporary-home cleanup. It exported 10
bundled descriptors with `debug models --bundled`, copied one into two synthetic
identities, and supplied them through runtime `model_catalog_json`.
`model/list` returned exactly those identities and their display/reasoning
metadata; `config/read` reflected `approvals_reviewer="auto_review"`.
The input descriptor contained `auto_review_model_override="probe-guardian"`;
no review was triggered, so this does not prove that override's routing effect.
No renderer or ordinary catalog was changed.
[Earlier attempts](evidence/windows-desktop-2026-10-05/catalog-failed-attempts.json)
are retained: default Windows text decoding produced no usable JSON, explicit
UTF-8 advanced to an initialization timeout, and captured diagnostics identified
an invalid `guardian` enum. The engine accepts `user`, `auto_review` or
`guardian_subagent`; the successful retry used the existing launcher's
`auto_review` contract. These were synthetic fixture corrections, not native
approval-policy changes. The original cleanup failure above remains a failed
attempt, independent of this successful probe.

**Policy (limited observation).** The inventory found no
`%ProgramData%\OpenAI\Codex\requirements.toml`. The isolated unauthenticated
engine returned no effective requirements. Neither observation rules out native
account/cloud policy. The ordinary account's effective requirements and model
entitlements remain unverified. Credentials were not read or exported.
[Official authentication and policy sources](windows-desktop-primary-sources-2026-10-05.md#account-entitlement-and-policy).

**Profile/history and defaults (source plus limited UI observation).**
`bootstrap-CYu4H4X5.js` `Owe` resolves an explicit
`CODEX_ELECTRON_USER_DATA_PATH`, otherwise a build-flavor-dependent directory
under Electron `appData`. `Ewe` requests Electron's singleton lock for packaged
Windows; second-instance handling can activate an incumbent and exit. The
ordinary UI displayed existing conversation titles, but no conversation was
opened or resumed. `.codex` exists; the simplistic `%APPDATA%\Codex` probe did
not find the actual profile. Resolve the real profile in package context before
claiming ownership or changing it. Do not infer absence of history from that
negative directory check. Per-conversation provider identity, picker/default
write containment and concurrent CLI isolation remain untested on Windows.

**Environment and IPC (installed source).** The startup-requirements module
hydrates a Windows shell environment; `application-network-startup` `mt`/`xt`
select PowerShell, cmd or POSIX-specific commands. It is not the macOS zsh/ZDOTDIR
contract. `Hs.spawnProcess` uses stdio pipes for the engine. Separately, `Mc`
returns the Windows named pipe `\\.\pipe\codex-ipc`; macOS filesystem socket
ownership cannot be reused. The local-daemon selection condition excludes
Windows. Pipe ACLs, connection authentication, per-user isolation and collisions
between isolated profiles are not established by the name alone. A separate
Electron profile does not prove complete IPC isolation.

**Install/update/uninstall and recovery (documented/source).** MSIX owns the
native app and its system service. The source includes native package update
handling and user-local engine relocation. Tofa should own only its bridge,
route state and install records. It must re-resolve the selected package/core
after updates and preserve native data and detached history references on
uninstall. No native uninstall, purge, interrupted update, abrupt termination,
or detached-bridge recovery was attempted in this non-disposable running guest.
Alt+F4 did not visibly close the ordinary app, so normal quit is also unqualified;
the app was left open. No process-wide force kill was used for native recovery.

## Minimal scope and public seams for #77

Start with a bounded contract prototype while the public Windows desktop command
continues to fail explicitly. Do not remove all Darwin build constraints.

| Seam / implementation slice | Reuse after proof | Windows-specific work |
| --- | --- | --- |
| Public discovery and launch | Model/route admission and capability checks | Interactive-user package selection, publisher/status/layout validation, architecture, registered-core/relocated-engine resolution and verified activation/environment |
| App → executable bridge → engine | Override assembly and JSON-RPC protocol transformations | `.exe` argv/stdin/stdout/stderr/exit transport; main initialize versus startup helpers; preserve sandbox-service semantics through a vendor-compatible route |
| Profile ownership and supervision | Versioned ownership-record semantics | Native singleton recognition, private ACLs, reparse-point rejection, case-insensitive identities and process handles; assess Job Objects after observing app/service topology |
| Catalog and settings boundary | Descriptor merge, provider validation, model-write recognition and current `desktop_route.go`/adapter behavior | Installed-engine catalog contract; intercepted default writes; native picker and concurrent CLI observations |
| Installer/ordinary recovery | Preserve-versus-purge intent and inactive-provider behavior | Windows executable locks, atomic bridge replacement, package updates, detached saved-engine references and scoped cleanup |

Use the existing [conversation-selection ADR](../adr/0003-desktop-conversation-model-selection.md)
and [Guardian ADR](../adr/0002-guardian-selection-follows-launch-route.md).
There is no proposed ADR exception. Agree public test seams before new
implementation tests: launcher invocation, installed engine protocol, visible
native app behavior, and real installer/uninstaller. The first critical proof is
app → owned bridge → recognized main initialize **with native sandbox enforcement
preserved**, plus refusal to adopt an already-running ordinary instance.

## Automation and acceptance matrix

The [repeatable runbook](windows-desktop-automation-2026-10-05.md) includes the
actual scripts, guest completion assertions and task cleanup. UTM file operations
and limited interactive tasks work. Computer use can inspect the native UI;
input capture and fresh screenshots are necessary, and not every attempted key
sequence worked. No reset is needed or authorized merely because input is slow.

| Scenario | Current evidence | Required #77 acceptance |
| --- | --- | --- |
| Existing login / first use | Existing login opens ordinary UI; first use untested | Reuse login without edits; first-use consent remains with user where required; classify account/policy failures |
| Install/reinstall/uninstall | No lifecycle attempt | Immutable candidate, real installer, hash/ARM64/PATH checks, repeat install, preserve-uninstall, saved-login reuse; purge only owned disposable state |
| Ordinary history | Titles visible; no content exported | Same conversation/provider across launches, no migration; preserved native and detached references |
| Model select/switch/resume | Headless static synthetic catalog/default accepted; UI untested | All eligible choices/labels, independent chats, same-chat switch, resume under different default; explicit unavailable-model errors |
| Guardian | Source identifies sandbox-context difference | Allow/deny/malformed/unavailable/cancelled reviewer; denied action never executes; native policy unchanged |
| Reasoning and media | Not attempted | Separate reasoning, supported image/text-only behavior and explicit auxiliary/compaction limitations |
| Cancellation / exits | Engine EOF exit 0; immediate cleanup failed | Turn interruption, normal quit, startup failure, owned-child loss, abrupt exit, stale lease recovery; no lingering route or service termination |
| CLI isolation | No desktop selection changes attempted | Concurrent CLI default/reasoning before/during/after desktop writes; no shared-settings snapshot restoration |
| Native recovery | Ordinary native launch observed | Ordinary relaunch after every adapted failure/lifecycle case with retained account/history |

All Windows acceptance uses this Windows 11 ARM64 UTM target. Existing amd64
build/CI evidence is supplementary; there is no separate amd64 qualification gate.
Do not promote a model from headless or macOS results.

## Precise blockers and unsent questions

1. **Launcher gap:** non-Darwin desktop launch, bridge and lifecycle are explicitly
   rejected; Windows package/profile/process implementation does not exist.
2. **Contract gap:** source-observed override changes packaged-sandbox context.
   No app-to-bridge/Guardian execution proof exists. This is not a demonstrated
   vendor prohibition. Ask the vendor, if needed: which supported custom-engine
   route preserves Windows sandbox service and package identity?
3. **Ownership gap:** actual native profile, named-pipe ACL/isolation and singleton
   ownership are unproven. Ask: is there a supported per-user/profile IPC namespace
   and an ownership signal a launcher can verify without taking over an incumbent?
4. **Validation gap:** first-use entitlement/policy, catalog/UI routing, concurrent
   defaults and full recovery matrix remain unmeasured. A logged-in home screen
   is not a model entitlement or provider compatibility test.
5. **Experiment limitation:** immediate engine temporary cleanup failed; later
   cleanup succeeded. Future harnesses must bound and report cleanup, not hide it.

No external questions were sent. No vendor restriction was worked around.
#77's readiness must reflect these gaps before implementation begins.

## Repository validation and review

[Validation](evidence/windows-desktop-2026-10-05/validation.json): Go vet and the
full Go race suite passed; all 252 Python tests ran, with 172 passing and 80
platform/optional-client skips. The first sandboxed race run could not bind local
test servers; the permitted rerun passed. Research JSON and local Markdown links
were checked. No production implementation or new runtime unit-test seam was added.
The failed engine experiment is separate from these repository results.

Issue #77 was refined with the findings and explicit prototype/acceptance gates
before production implementation; the saved body was read back and verified.
Standards and Spec reviews each have zero remaining findings. Review resolved
the missing catalog/default-write/reviewer source trace and clarified automation
versus interactive thread routing. No release or push was performed.
