# Ollama ChatGPT Desktop routing — 2026-10-14

## Finding

Ollama's current source offers a concrete alternative worth investigating before
concluding that TOFA requires a Desktop source change or an isolated profile.
It uses the ordinary ChatGPT profile and built-in provider, retains existing
account authentication, and redirects model traffic through a local router with
`openai_base_url`. It deliberately removes an explicit `model_provider` to
preserve native account controls. This is a different integration boundary from
selecting TOFA's custom provider with `requires_openai_auth=false`.
[Configuration source][config], [ordinary-profile entry point][regular].

This does **not** establish that the installed Desktop build preserves its
`code-review` plugin under Ollama's route. The inspected launcher/router contain
no plugin-lifecycle implementation or regression establishing that result.
They provide a source-backed hypothesis: retaining the native signed-in account
may avoid the eligibility transition observed in TOFA's custom-provider launch.
The hypothesis requires a bounded test; it is not a qualified fix.

## Provenance and scope

- Official repository: `ollama/ollama`, fetched read-only at main commit
  [`f5be23f42d5a0322f9e09a8f9da1fa9853d5ce0d`][commit], committed
  2026-10-14T10:09:14-05:00. Every upstream source link below pins that revision.
- This is a current **source snapshot**. Its presence in a released or locally
  installed Ollama binary was not established. The integration documentation
  advertises Ollama v0.34.0 or newer, which does not prove every main-branch detail
  shipped in that version. [Documentation][docs].
- Source and upstream tests were inspected; upstream tests were not executed.
  No Ollama/ChatGPT application was launched, real settings or credentials were
  changed, or model inference performed.
- This note refreshes the Desktop portion of
  [the September Ollama investigation](ollama-launchers.md). Its key built-in
  provider/ordinary-profile finding was already present in that earlier source.

## Which client and how it starts

This integration is explicitly ChatGPT Desktop's **Codex mode**. Ordinary Chat
and voice retain their usual connection. It is separate from `ollama launch
codex`, whose runner invokes terminal `codex` with the `ollama-launch` profile
and command-line provider overrides. [Desktop documentation][docs],
[CLI runner][cli].

The Desktop runner rejects extra arguments and calls its launch/restart helper.
On macOS it prefers `/Applications/ChatGPT.app`, then `/Applications/Codex.app`,
then their user Applications equivalents. It starts the discovered application
using `open`, adding `codex://threads/new?mode=codex` when configured. Its normal
launch does not inject a replacement engine executable, `CODEX_HOME`, or a
private Electron `--user-data-dir`. [Runner][run], [discovery][discovery],
[native open implementation][open].

The source still contains `chatgpt-ollama`, `electron-data`, singleton and PID
helpers. These names are **not evidence that current launches isolate the
profile**: the current desktop entry point explicitly stops the legacy separate
profile before applying settings to the regular profile. Its upstream test is
named `TestCodexAppDesktopUsesAndRestoresRegularProfile` and checks unchanged
existing auth. [Regular-profile flow][regular], [legacy stop][legacy],
[upstream profile test][profile-test].

For catalog discovery only, Ollama creates a scratch `CODEX_HOME`, copies
`auth.json` and `models_cache.json` if present, invokes `codex debug models`, and
removes the scratch directory. Cache and bundled-catalog fallbacks follow. Its
macOS executable lookup first checks `Contents/Resources/codex`, then PATH;
therefore this discovery helper is not evidence of support for the installed
nested `CodexCLI.app` engine layout. It does not replace the app's runtime engine.
[Catalog probe and executable lookup][probe].

## Configuration, authentication and routing

The regular configuration path is OS user home plus `.codex/config.toml`;
the helper does not consult `CODEX_HOME`. Configuration saves restore state,
writes a combined picker catalog plus a separate Ollama-only routing catalog,
then writes root model/catalog/base-URL settings. It removes the root profile
and explicit provider, while preserving unrelated TOML sections through its
editing helpers. Existing auth is retained; only if `auth.json` is absent does it
exclusively create the local sentinel `ollama-local-codex`. The sentinel is not
a ChatGPT login and is not evidence of native plugin eligibility for signed-out
users. [Home resolution][home], [configuration sequence][sequence],
[root settings][config], [auth creation/removal][auth].

The configured base URL is the connectable Ollama host plus
`/api/codex/v1`. The router accepts loopback requests, reads the request model
against its separate routing catalog, and routes listed models to Ollama.
Requests outside that catalog retain their native route: the
`ChatGPT-Account-ID` header selects ChatGPT; other requests select OpenAI's API.
A local sentinel cannot be forwarded to a native upstream. The router handles
WebSocket upgrade requests with HTTP 426 so the client uses HTTP routing.
[Base URL][base-url], [routing and transport][routing].

For Ollama-bound requests, the router replaces the outbound header map and
copies only `Accept`, `Content-Type`, `OpenAI-Beta`, and `User-Agent`.
Consequently ChatGPT/OpenAI authorization and account headers do not reach
Ollama. Native-bound requests retain their authentication headers through the
reverse proxy. Upstream tests explicitly exercise credential stripping and
native credential retention with synthetic tokens. [Header boundary][headers],
[allow-list][header-list], [stripping test][strip-test],
[native-routing test][native-test].

This is an authentication-preserving routing design, not account spoofing or a
plugin eligibility override. The local router necessarily receives the native
request credentials before stripping them for the alternate provider. Any TOFA
implementation must ensure they never enter Token Factory requests, logs, or
exported evidence; Token Factory authentication must be attached independently.

## Persistence and restoration

Ollama persists the regular profile's routing configuration. Launch returns
after opening the application; it does not restore settings when the app exits.
Disconnect/`--restore` explicitly restores managed values from saved state,
removes owned catalogs where unused, and removes auth only if it matches the
exact sentinel. Restoration avoids overwriting a root configuration that is no
longer managed and preserves a native model the user selected while connected.
It is not an automatic crash-safe temporary overlay.
[Launch][open], [restore implementation][restore],
[conditional restoration][restore-values], [restore-state path][restore-path].

Copying these persistent writes would conflict with TOFA's documented requirement
that Desktop launch defaults not alter concurrent CLI settings and that shutdown
not restore a shared settings snapshot. Ollama is a reference for retaining the
native provider and separating routing/authentication, not approval to copy its
configuration lifecycle unchanged. [TOFA ADR 0003](../adr/0003-desktop-conversation-model-selection.md).

## Next evidence before implementation or another manual run

Follow-up: the maintainer-authorized [#133 prototype](https://github.com/kreuzhofer/tofa-launcher/issues/133)
now supplies positive headless evidence. The installed engine retained its
`chatgpt` account with a process-scoped built-in-provider/base-URL override,
including Kimi model selection; the custom-provider control returned no account.
The return to ordinary configuration matched the baseline, and protected-file
checks passed. A fake-credential router caught its deliberately unsafe control
and passed all eight checks in the safe variant. The native account probe needed
normal account-discovery connectivity; no inference RPC or Desktop launch ran.
See the [exact prototype result](https://github.com/kreuzhofer/tofa-launcher/blob/b0d9fd7/internal/tofa/prototypes/native-provider/RESULT.md).
This validates the account-context hypothesis at the engine boundary, not native
plugin lifecycle preservation or a production routing implementation. The guard
stays active; the steps below record the original experimental boundaries.

1. Probe the installed engine's account/configuration behavior using a
   process-scoped native-provider base-URL override. Confirm the actual account
   type remains native without editing auth, persistent settings or eligibility.
   If the installed engine does not accept this boundary, report that directly.
2. Exercise a synthetic router with fake credentials: alternate-provider
   requests must lose native authorization/account headers, native routes must
   retain their correct destination, and errors must not leak credentials.
3. Resolve compatibility with existing `nebius-tofa` conversation provider
   identities, per-conversation selection, Guardian and naming routes. Do not
   silently migrate old conversations to the built-in provider.
4. Only after those checks, design a bounded actual Desktop lifecycle test for
   plugin preservation. Existing guard and paused evaluation scripts remain in
   force until that separate qualification succeeds.

These are proposed verification boundaries, not work performed by this research.
No isolated profile or production routing change is approved by the source facts
alone.

[commit]: https://github.com/ollama/ollama/commit/f5be23f42d5a0322f9e09a8f9da1fa9853d5ce0d
[docs]: https://github.com/ollama/ollama/blob/f5be23f42d5a0322f9e09a8f9da1fa9853d5ce0d/docs/integrations/chatgpt.mdx#L6-L34
[config]: https://github.com/ollama/ollama/blob/f5be23f42d5a0322f9e09a8f9da1fa9853d5ce0d/cmd/launch/codex_app.go#L312-L368
[regular]: https://github.com/ollama/ollama/blob/f5be23f42d5a0322f9e09a8f9da1fa9853d5ce0d/cmd/launch/codex_app.go#L683-L722
[cli]: https://github.com/ollama/ollama/blob/f5be23f42d5a0322f9e09a8f9da1fa9853d5ce0d/cmd/launch/codex.go#L38-L81
[run]: https://github.com/ollama/ollama/blob/f5be23f42d5a0322f9e09a8f9da1fa9853d5ce0d/cmd/launch/codex_app.go#L653-L660
[discovery]: https://github.com/ollama/ollama/blob/f5be23f42d5a0322f9e09a8f9da1fa9853d5ce0d/cmd/launch/codex_app.go#L1657-L1665
[open]: https://github.com/ollama/ollama/blob/f5be23f42d5a0322f9e09a8f9da1fa9853d5ce0d/cmd/launch/codex_app.go#L2079-L2134
[legacy]: https://github.com/ollama/ollama/blob/f5be23f42d5a0322f9e09a8f9da1fa9853d5ce0d/cmd/launch/codex_app.go#L792-L799
[profile-test]: https://github.com/ollama/ollama/blob/f5be23f42d5a0322f9e09a8f9da1fa9853d5ce0d/cmd/launch/codex_app_test.go#L511-L569
[probe]: https://github.com/ollama/ollama/blob/f5be23f42d5a0322f9e09a8f9da1fa9853d5ce0d/cmd/launch/codex_app.go#L1480-L1622
[home]: https://github.com/ollama/ollama/blob/f5be23f42d5a0322f9e09a8f9da1fa9853d5ce0d/cmd/launch/codex.go#L235-L240
[sequence]: https://github.com/ollama/ollama/blob/f5be23f42d5a0322f9e09a8f9da1fa9853d5ce0d/cmd/launch/codex_app.go#L101-L146
[auth]: https://github.com/ollama/ollama/blob/f5be23f42d5a0322f9e09a8f9da1fa9853d5ce0d/cmd/launch/codex_app.go#L566-L630
[base-url]: https://github.com/ollama/ollama/blob/f5be23f42d5a0322f9e09a8f9da1fa9853d5ce0d/cmd/launch/codex_app.go#L557-L558
[routing]: https://github.com/ollama/ollama/blob/f5be23f42d5a0322f9e09a8f9da1fa9853d5ce0d/internal/proxy/codex_desktop.go#L157-L264
[headers]: https://github.com/ollama/ollama/blob/f5be23f42d5a0322f9e09a8f9da1fa9853d5ce0d/internal/proxy/codex_desktop.go#L359-L375
[header-list]: https://github.com/ollama/ollama/blob/f5be23f42d5a0322f9e09a8f9da1fa9853d5ce0d/internal/proxy/codex_desktop.go#L671-L685
[strip-test]: https://github.com/ollama/ollama/blob/f5be23f42d5a0322f9e09a8f9da1fa9853d5ce0d/internal/proxy/codex_desktop_test.go#L26-L90
[native-test]: https://github.com/ollama/ollama/blob/f5be23f42d5a0322f9e09a8f9da1fa9853d5ce0d/internal/proxy/codex_desktop_test.go#L1249-L1297
[restore]: https://github.com/ollama/ollama/blob/f5be23f42d5a0322f9e09a8f9da1fa9853d5ce0d/cmd/launch/codex_app.go#L802-L872
[restore-values]: https://github.com/ollama/ollama/blob/f5be23f42d5a0322f9e09a8f9da1fa9853d5ce0d/cmd/launch/codex_app.go#L2431-L2453
[restore-path]: https://github.com/ollama/ollama/blob/f5be23f42d5a0322f9e09a8f9da1fa9853d5ce0d/cmd/launch/codex_app.go#L2648-L2653
