# Separate Desktop app-server selection from persistent MCP executable settings

Local implementation-ticket draft. Not published, assigned, or implemented.
Blocks the preservation requirement of #127 (parent #119).

## Problem

Launching Desktop with the launcher's `CODEX_CLI_PATH` bridge causes Desktop to
persist that path into the Node and computer-use MCP definitions. A temporary
evaluation bridge can then disappear when its owned run ends. Ordinary startup
reconciles the references, but does not satisfy preservation during the run.

The installed Desktop functions reproduce both writes with only
`CODEX_CLI_PATH` changed. See the
[diagnosis and provenance](presentation-native-settings-diagnosis.md).

## Required implementation

In Desktop's local app-server executable selection, expose a supported
session-only command override separate from the runtime executable used to
generate persistent MCP definitions. Define and document its name, validation,
and precedence in the owning client source. Retain the existing `CODEX_CLI_PATH`
behavior for existing users. Absence of the new override must retain ordinary
startup. An invalid explicit override must fail clearly rather than fall back.

Use the new override only for app-server launch. Do not feed it into Node MCP
configuration, the computer-use plugin's `.mcp.json`, or persisted defaults.
Preserve the normal local host, ordinary home/profile, native signing checks,
and the app-server's existing stdio/ownership contract.

Once that capability exists in a usable client build, adapt the launcher at
`internal/tofa/desktop_darwin.go` to select its existing bridge through it.
Retain the bridge's engine `exec` and separate settings relay. Do not replace
the session-scoped model-default filter or change routing, Guardian, naming,
approval policy, or ownership enforcement. Establish version/capability support
before enabling the new route; do not assume an ignored environment variable
means the bridge ran.

## Test first and acceptance

- At the actual client selection/reconciliation boundary, start from ordinary
  MCP definitions, change only the session command, and assert the selected
  executable is the requested bridge while both persistent executable references
  retain their ordinary values. Exercise both the direct plugin write and the
  `config/batchWrite` payload. Observe failure before applying the fix.
- Cover absent and invalid overrides and the defined interaction with an
  existing `CODEX_CLI_PATH`; retain compatibility with existing behavior.
- At the launcher boundary, prove that the supported override launches and
  acknowledges the owned bridge and that missing/ignored capability is rejected.
- With the actual client build, verify native readiness and signed
  Desktop → bundled engine → bundled Node ancestry. Verify protected-state
  preservation on success, failure, and cancellation, with unrelated settings
  and concurrent edits preserved. No shared snapshot restoration.
- After those checks pass, finish #127's native loader invocation, delivered
  PPTX/PDF, native previews, and separate model calibrations. Keep the integration
  branch and existing qualification block until all required evidence passes.

## Implementation dependency

The available repository owns the launcher, not the installed Desktop selection
and reconciliation functions. No editable Desktop source checkout was found in
the inspected local GitHub repositories. The adjacent `nebius-agent-ide`
repository contains Cline/VS Code integrations. Source access or an upstream
Desktop change is required; modifying or re-signing the installed application
would not satisfy the current constraints.

No production changes or passing fix tests are claimed by this ticket draft.
