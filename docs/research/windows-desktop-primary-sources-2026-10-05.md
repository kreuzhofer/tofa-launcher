# Windows desktop: official-source findings, 2026-10-05

Research for [#76](https://github.com/kreuzhofer/tofa-launcher/issues/76).
The companion [guest contract report](windows-desktop-contract-2026-10-05.md)
records the installed versions and runtime results.
This note records documentation and repository-source evidence, not a successful
Windows guest qualification. It does not establish a supported model combination
or unblock [#77](https://github.com/kreuzhofer/tofa-launcher/issues/77) by itself.

## Source identity and limits

On 2026-10-05, the official URLs `developers.openai.com/codex/app/windows`,
`developers.openai.com/codex/app`, and
`developers.openai.com/codex/app-server` redirected to the corresponding
ChatGPT Learn pages below. They now describe the **ChatGPT desktop app** and
Codex functionality. That naming/redirect is documentation evidence; it does
not identify an installed Windows executable or prove that an older Codex
package has the same contracts. [Windows page](https://learn.chatgpt.com/docs/windows/windows-app),
[app page](https://learn.chatgpt.com/docs/app),
[app-server page](https://learn.chatgpt.com/docs/app-server).

The Markdown documents were fetched from each page's `.md` URL. The responses
provided no `Last-Modified` value. These are dated content fingerprints, not
upstream release versions. Inspection copies and `index.json` are in private
scratch at `/private/tmp/tofa76-official-docs`; that directory is not a delivered
artifact. The content hashes allow comparison with a later fetch, but the
mutable public URLs do not guarantee retrieval of these exact bytes.

| Document | SHA-256 of fetched Markdown |
| --- | --- |
| [Windows app](https://learn.chatgpt.com/docs/windows/windows-app) | `5bbae21f535849b2ab51ec9472d43e2f1ade4f954b3d5241bcec4674e7761ad7` |
| [Windows deployment](https://learn.chatgpt.com/docs/enterprise/windows-deployment) | `9c35fbcafee6303e79a3c064c1dcfd142fe46326b8a61eb10d498ade95d271af` |
| [Authentication](https://learn.chatgpt.com/docs/auth) | `3d2f0ed91fa09de11cabe38cb37a76e0833f71205cae6589c46c7f5ae9ad62f0` |
| [App Server](https://learn.chatgpt.com/docs/app-server) | `14c29f997cffff66125e710c1746425c53262eb4e636eb0bbcd5c8b4ec7e4464` |
| [Managed configuration](https://learn.chatgpt.com/docs/enterprise/managed-configuration) | `7af4d6e961d34486abed562e8418471133c68fa6de86c5ed0ef1d5856f310912` |
| [Manage updates](https://learn.chatgpt.com/docs/enterprise/manage-app-updates) | `d287f362a6808ce7d9fd01a9c3df52a801aef99dc32992f0cde9562e6bbeed29` |
| [Roles and permissions](https://learn.chatgpt.com/docs/enterprise/roles-and-workspace-permissions) | `7c0eb5401d996a07ccbafac355147abee92a6f3cddd1a531a2f387d963c28111` |
| [Environment variables](https://learn.chatgpt.com/docs/config-file/environment-variables) | `af767b8d7892d11d0554d9ea5c0d60d7bb463cb64b2a3a51e2ba0efadbc86ba8` |
| [Configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference) | `73242945d7891bc09bf95a39d83117025abd8eca61ae5707db38fda40db16d62` |
| [Gateway rollout](https://learn.chatgpt.com/docs/enterprise/roll-out-a-gateway) | `25b9f9dc62c7ed5b362b71762324434c4a8daff67204cac92a6d56622e83424c` |

## Installation and architecture

**Documented:** Windows deployment offers separate x64 and Arm64 Store-signed
MSIX downloads. Its detection example uses package identity `OpenAI.Codex`;
the Store product ID is `9PLM9XGG6VKS`. The page links
`https://persistent.oaistatic.com/codex-app-prod/ChatGPT-arm64.msix` and an
offline license, describes administrator/device-context installation, and says
standalone MSI/non-Store EXE packages are unavailable. Offline package install
does not confer offline product access. The URLs serve the latest packages,
not a pinned release. Its uninstall example removes both provisioning and
registrations for all users; that is a destructive deployment operation, not
a launcher cleanup procedure. [Deployment source](https://learn.chatgpt.com/docs/enterprise/windows-deployment).

**Unknown here:** MSIX manifest version, publisher, minimum OS, actual package
signature, executable layout, bundled engine version, and PE machine types.
An Arm64 package link establishes an offered architecture; it cannot prove
that every bundled executable is ARM64 or that a guest launched natively.
Record the manifest and hashes of the actual downloaded/installed package,
app, selected engine, and helpers before claiming a version-pinned contract.

**Documented:** The Windows app defaults to a Windows-native agent using
PowerShell and supports an alternative WSL2 agent setting. The integrated
terminal is configured separately. Native app state uses
`%USERPROFILE%\.codex`; a WSL CLI instead uses its Linux home by default.
Native Windows filesystem projects are the recommended arrangement when
using the native agent. [Windows source](https://learn.chatgpt.com/docs/windows/windows-app).

## Account, entitlement, and policy

**Documented:** Local desktop workflows support ChatGPT sign-in and OpenAI
API-key sign-in. These select different billing and governance contexts.
Provider-specific environment authentication is separately configurable.
`forced_login_method` and `forced_chatgpt_workspace_id` can restrict sign-in;
mismatched credentials cause logout/exit. Credential storage can be a file,
OS keyring, automatic selection, or ephemeral storage. These docs do not
establish that a Nebius key gives access to native account services or a
particular Windows desktop feature. [Authentication source](https://learn.chatgpt.com/docs/auth).

**Documented:** Membership, seat/plan eligibility, workspace feature access,
local execution permissions, and external-service permissions are independent
boundaries. Local Codex access can have its own workspace control; some
workspaces expose a combined Codex/Work control. A permission profile does not
grant a model entitlement. Therefore, an installed package, successful login,
catalog entry, and successful inference are distinct evidence items.
[Roles source](https://learn.chatgpt.com/docs/enterprise/roles-and-workspace-permissions).

**Documented:** Windows system requirements are read from
`%ProgramData%\OpenAI\Codex\requirements.toml`. Cloud requirements and legacy
managed settings can also apply. Requirements can constrain the approval
reviewer; `guardian_policy_config` affects automatic-review policy while
the runtime retains its reviewer template/output contract. Managed
permission-profile allowlists require Codex 0.138.0 or later. These facts
do not establish the launcher's Nebius Guardian payload compatibility.
[Managed configuration source](https://learn.chatgpt.com/docs/enterprise/managed-configuration).

**Recommendation:** Query effective requirements without dumping credentials;
record whether the tested account is personal/managed and whether policy
permits the required reviewer/provider. Do not change workspace controls,
authentication files, or sandbox policy to make a probe pass. A policy failure
is a separate blocker from missing architecture or process integration.

## Integration contracts and unproven desktop behavior

**Documented:** App-server supports newline-delimited JSON over stdio using
JSON-RPC-shaped messages without the `jsonrpc` header. Clients initialize
once and send `initialized` before other operations. Thread start/resume,
turn start/interrupt, model listing, configuration operations, and incremental
notifications are documented. Schema generation is specific to the executable
version that produced it; experimental fields need matching opt-in.
This supports an isolated engine protocol probe, not a claim that a particular
desktop launches that engine through an override. [App-server source](https://learn.chatgpt.com/docs/app-server).

**Documented:** `CODEX_HOME` controls engine state and must refer to an existing
directory. `CODEX_SQLITE_HOME` redirects SQLite state, with `sqlite_home`
configuration taking precedence. The public environment-variable page says
it lists stable public variables and omits internal/development variables;
it does **not** list `CODEX_CLI_PATH` or
`CODEX_ELECTRON_USER_DATA_PATH`. Their omission does not prove those variables
are absent from an installed app. It means this reference cannot qualify
them as stable public override contracts. [Environment source](https://learn.chatgpt.com/docs/config-file/environment-variables).

**Documented:** Gateway model catalogs should match the selected engine
version, including the bundled CLI for desktop deployments. Catalog changes
require restart. Model listing alone does not establish request compatibility;
the rollout guide calls for actual streaming, tool-loop, continuation, and
error checks on the intended client surface. [Gateway source](https://learn.chatgpt.com/docs/enterprise/roll-out-a-gateway).

**Still unproven on Windows in this note:** app discovery and activation;
environment inheritance into the selected engine; override precedence;
native singleton/profile ownership; startup helper versus conversation-engine
lifetime; ordinary-mode recovery; shared history; picker and reasoning-default
containment; catalog augmentation; Guardian routing and native execution
enforcement; cancellation and child-process cleanup. These need exact
Windows package/source and runtime evidence. Existing macOS findings in
[the minimum-version note](desktop-minimum-version-2026-09-30.md) are useful
probe hypotheses, not Windows observations.

## Updates, uninstall, and recovery boundaries

**Documented:** Supported desktop builds allow disabling the built-in updater
using `features.in_app_updates = false` in enforced requirements, followed by
restart. This does not stop Microsoft Store or management-tool updates and
does not create an OpenAI-supported release pin or guarantee service
compatibility for older builds. [Update source](https://learn.chatgpt.com/docs/enterprise/manage-app-updates).

**Recommendation:** Qualify against captured app/engine identities. Re-read
identity after update, and refuse changed or incompatible layouts with an
actionable message. Launcher uninstall should remove only launcher-owned
integration; native package uninstall is separate. Test interrupted bridge
replacement and recovery in a disposable Windows profile/snapshot. Keep
provider/history state and native account credentials intact. Successful
offline installation, update suppression, and rollback are three separate
checks; none was performed by this research agent.

## Minimal candidate seams for #77

Repository inspection is pinned to
`f84e6e4550199a707d1f6149a01308e8deb0a7ba`. The non-Darwin implementation
explicitly refuses desktop launch, bridge operation, and desktop lifecycle
operations. [Current boundary](../../internal/tofa/desktop_other.go).
The macOS implementation uses `syscall.Exec`, POSIX process groups/signals,
`flock`, and a macOS profile path.
[Bridge](../../internal/tofa/desktop_bridge_darwin.go),
[launch/process handling](../../internal/tofa/desktop_darwin.go),
[profile ownership](../../internal/tofa/desktop_profile_darwin.go).

These are proposed seams, subject to guest findings:

| Seam | Windows evidence needed before implementation |
| --- | --- |
| Installation discovery | Package identity/publisher/version, manifest executable, selected engine and PE architecture; explicit handling of missing/ambiguous installs |
| Native launch | A reversible app launch with exact argv and scoped environment reaching the intended bridge/engine; ordinary instance must be detected without taking ownership |
| Ownership and supervision | Windows-specific private storage/ACLs, exclusive lease and process identity; cancellation and bounded child cleanup without POSIX signal assumptions |
| Bridge installation | `.exe` ownership/version records and interruption-safe replacement under Windows file-sharing/locking behavior; detached recovery |
| Shared engine protocol | Retain model/provider/catalog and Guardian logic only after matching generated schemas and runtime tests pass |
| Profile/history containment | Discover actual native profile separately from Codex state; verify picker writes cannot change concurrent CLI defaults |

Do not rename all Darwin files or introduce a broad platform abstraction
before those observations. Keep Windows unsupported until the required
contracts are demonstrated; a compile-only port cannot qualify them.

## Repeatable qualification matrix

This is a proposed matrix, not recorded passing evidence. Use a disposable
workspace/profile and restoreable guest snapshot; retain sanitized app and
engine versions, hashes, exit statuses, and observations for every row.

| Stage | Required observation | Classification if unavailable |
| --- | --- | --- |
| Inventory | Windows edition/build/ARM64, package manifest/signature, app/engine PE architecture and versions | Guest/package availability blocker |
| Isolated engine | Version/schema generation; initialize, effective requirements, model/config reads using synthetic auth only | Engine contract blocker |
| Native app launch | Bridge selection, argument/environment preservation, native singleton refusal, main handshake ownership | Desktop launch blocker |
| Provider and catalog | Native and Token Factory options coexist; incompatible/unavailable catalog choices fail explicitly | Catalog/provider blocker |
| Conversation selection | Per-thread model change/resume retains provider/history; new defaults stay out of concurrent CLI | Isolation blocker |
| Main model | Streaming, local tool result, same-thread follow-up, invalid-model/auth error | Model qualification gap |
| Guardian | Allow, deny, malformed/unavailable reviewer, cancellation; denied action never executes | Approval-enforcement blocker |
| Lifecycle | Quit, crash, engine loss, stale ownership, interrupted update, relaunch and ordinary-mode recovery | Ownership/recovery blocker |
| Installation lifecycle | Install/update/uninstall of launcher integration preserves native app, history and credentials | Distribution blocker |

The exact package/build and guest observations belong in the accompanying
feasibility evidence. This source audit neither mutates the guest nor reads
credentials. It changes no runtime implementation and runs no behavioral
tests; parent validation must report its own test and probe results separately.
