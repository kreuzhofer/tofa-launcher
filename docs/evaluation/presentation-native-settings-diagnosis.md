# Native Desktop settings drift diagnosis

Status: cause reproduced; no production fix applied. #126/#127 remain on the
integration branch and unqualified. Investigation baseline: `4b01ca1`.

## Cause and boundary

The installed Desktop uses `CODEX_CLI_PATH` both to select its app-server
executable and to generate persistent MCP executable references. The launcher
sets this variable to its owned settings bridge. Desktop consequently writes
that bridge path into:

- `config.toml`: `mcp_servers.node_repl.env.CODEX_CLI_PATH`.
- The unified-computer-use plugin's `.mcp.json`:
  `mcpServers.cua_repl.env.CODEX_CLI_PATH`.

The earlier native startup capture observed both changes. A minimized replay of
the installed functions reproduced them twice by changing only this environment
variable. No engine or launcher process is needed for this replay. The ordinary
control selects the bundled engine for both references; the bridge case selects
the bridge for both. This establishes host-side configuration generation as the
cause of these two writes, independently of engine behavior.

The relevant installed path is `aa` (runtime selection), shared `E` (Node MCP
configuration), then `hc` (reconciliation). `hc` calls `rne`, which writes plugin
JSON directly, before sending the `gc` edits through `config/batchWrite`.
Filtering app-server configuration writes alone therefore cannot protect both
files. The launcher's provider integration writes only its provider definition;
it is not responsible for these two field updates.

## Reproduction and provenance

Private diagnostic command, run twice with exit status 1:

```sh
/Applications/ChatGPT.app/Contents/Resources/cua_node/bin/node \
  /tmp/tofa-presentation-validation/checks/replay-native-config.cjs
```

```text
FAIL: native functions persist the launcher override into both MCP definitions
persistent_references_preserved: false
```

The script evaluates exact installed function bodies in isolated Node VM contexts,
with deterministic path resolvers and plugin file IO redirected to owned fixtures.
The ordinary control assertions pass. It checks the generated config-write payload
and actual fixture plugin JSON. It does not execute the full Desktop reconciliation,
engine persistence, native authorization, loader, or deck workflow. Those limits
prevent treating it as end-to-end qualification or a passing regression test.

Both successful diagnostic executions completed in less than one second. The
earlier harness setup error (missing injected `c.at` resolver) was corrected before
these executions; it was not a reproduction of the product bug. Fixtures and
results remain under the fixed `/tmp/tofa-presentation-validation/checks` root.

Desktop: ChatGPT 26.1007.30912, build 20156. Installed `app.asar` SHA-256:
`75e397e2280dde93b70a85aa926f4282c728eacc84dfeb15ba7fb6ddd84628af`.
All three inspected extracted JavaScript files were compared byte-for-byte with
the current installed archive. File and replay-function hashes are retained in
[the evidence record](evidence/presentation-runtime-126-127/native-settings-diagnosis.json).
No installed code, shared settings, skills, plugins, or credentials were modified
during this diagnosis. A final read confirmed both current references equal the
existing bundled engine path.

## Fix boundary and next implementation

No supported launcher-side boundary that separates these two uses was found in
the inspected build. An internal `hostConfig.codex_cli_command` can select the
app-server command separately, but inspected call sites did not establish an
exposed setter for the normal local Desktop host. This is a bounded negative
finding, not proof that no alternative can exist. Neither identifier appears in
the [official configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference)
checked on 2026-10-13.

A stable bridge path still changes ordinary MCP configuration. Changing the home,
disabling existing capabilities, restoring shared snapshots, or patching the
installed client does not meet the agreed preservation contract. WebSocket/daemon
transport alternatives have not been qualified for native ancestry and the normal
local host; they are not established fixes.

The minimal client integration requirement is a supported, session-only
app-server command override independent of the executable selected for persistent
MCP definitions. A fix belongs at the Desktop selection/reconciliation boundary,
where a regression can exercise both configuration-write paths. No launcher-only
passing test would establish that property today.

Acceptance for that change: vary only the session app-server command; both MCP
references retain their ordinary values; the selected bridge still launches;
signed native ancestry and the existing model-default isolation remain intact.
Then rerun real Desktop startup with protected-state comparisons on success,
failure, and cancellation before attempting the native loader, deck, previews,
and separately declared model calibrations. Keep the current preservation gate
and integration branch until that evidence exists.

No production code changed, so the full Go/Python suites were not repeated for
this documentation-only diagnosis. The previously recorded passing suites remain
valid for their original revision and scope; the new preservation repro remains
red. No merge, issue closure, or public publication was performed.
