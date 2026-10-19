# Routed history implementation and remaining ordinary-Desktop gap

Part of #134/#137. This is engine/launcher fixture evidence, **not Desktop
qualification or complete acceptance of #137**.

New conversations keep `tofa-native-router`; legacy `nebius-tofa` and native
`openai` histories retain their original identities. A launch inserts only an
exact owned, non-routable provider entry through the existing native
`config/batchWrite` ownership/version check. Active routing and defaults remain
process-scoped. A missing entry can be recreated; incompatible user-owned
entries and competing writes stop the launch.

The inactive router entry intentionally has no `env_key`. The real engine
requires a configured `env_key` even when native authentication is required, and
a populated synthetic key replaces the native bearer. Neither a provider-table
override nor an empty key clears this behavior. `env_http_headers` cannot act as
an unavailable-route sentinel: missing variables are silently omitted. These
measured contracts rule out copying the legacy inactive entry unchanged.

For an ordinary **saved bridge** invocation, TOFA reads effective native
configuration and adds the missing-variable sentinel as a process-only override
only for the exact owned inactive entry. Existing command-line configuration is
included in that check; user-owned providers are left unchanged. The native
error includes “Relaunch through tofa” and no inference reaches either service.
No shared provider toggling, credential extraction, restore-on-exit operation,
URL guidance encoding or inactive routing daemon is involved.

The fixture covers mixed-service resume under another launch default, ordered
history including a coding-tool result, direct-native and legacy compatibility,
repeated ordinary/TOFA launches, unavailable recorded models, stale inherited
credentials, missing metadata, provider ownership conflicts, version conflicts
and preservation of concurrent ordinary settings. See the
[sanitized evidence](evidence/native-account-routing-134/history-137.json).

## Unmet ordinary-Desktop criterion

When launched **directly through the bundled engine**, the same inactive router
history remains readable and does not reach an upstream, but a send reports
“Reconnecting... waiting for network” with `willRetry: true` despite both provider
retry limits being zero. The original probe reached the whole test's 90-second
deadline while awaiting this final turn. The final bounded observation cancels
that turn explicitly; cancellation does not count as actionable recovery.

Historical actual-Desktop evidence in
[retained MCP bridge verification](retained-mcp-bridge-verification.md) says that
ordinary Desktop reconciles executable references back to its bundled engine.
Therefore saved-bridge guidance must not be assumed to cover ordinary Desktop.
#141/#142 must establish the executable actually used and visible recovery
behavior. If ordinary Desktop bypasses the bridge and retains this reconnect
behavior, the ordinary-launch acceptance criterion remains unmet and needs a
supported fix or an explicit product decision. Keep the production guard and
release/adoption gates closed; do not silently substitute a weaker criterion.
