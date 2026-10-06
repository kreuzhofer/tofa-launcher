# Windows desktop implementation checkpoint — 2026-10-06

Issue #82 has an implemented bounded desktop harness and operator-CLI fixture
coverage. **Real Windows ARM64 desktop acceptance is pending.** This checkpoint
must not be used to close #82 or claim Guardian qualification for #83–84.

The existing dedicated template was started for the operator's one-time Codex
sign-in under `tofa-test`. It must be fully quit and Windows shut down before
fresh-clone acceptance. No credential file was read, exported, imported, or
changed by this work. The everyday Windows VM and previously retained failed
clone were left unchanged.

## Implemented boundary

- Explicit `--test-auth native-session` preparation verifies native account
  metadata, runtime workspace trust, automatic review, and workspace-write
  policy without starting a model turn.
- `run --suite desktop-smoke --test-auth native-session` first passes native
  readiness, then launches the installed desktop through an owned bridge and
  attempts one synthetic workspace write/read with semantic UI Automation.
- The bridge checks the returned thread policy and turn overrides before
  forwarding the synthetic prompt. Full access, network widening, changed
  models, unrelated workspace roots, and environment substitution are refused.
- Bridge-local thread and turn ordinals correlate admission, command success,
  and turn completion. Unrelated completion cannot qualify the filesystem effect.
- Normal quit, owned-child exit, unchanged CLI configuration, vendor-service
  preservation, complete diagnostics, and successful clone deletion are required.
  Diagnostic-write failures cannot bypass process cleanup.
- Interrupted runs collect the separate desktop task's correlated progress and
  result before stopping the verified owned clone.

The installed Mac engine `codex-cli 0.160.0` generated its ordinary and
experimental app-server schemas into disposable local directories. These
confirmed the thread/turn policy fields and Guardian review lifecycle event
shapes. They are implementation inputs; Windows package behavior still needs
measurement. No model, authentication, or inference request was made by schema
generation.

## Checks

Validation results are recorded in the adjacent
[evidence directory](evidence/windows-desktop-2026-10-06/validation.json).
The desktop tests use the public operator CLI and external VM/guest fixtures.
Policy regressions additionally execute the actual bridge against a controlled
native-engine subprocess. Red-to-green cases covered false completion,
diagnostic failure, crash recovery, and unsafe policy/identity overrides.

Standards review: no remaining findings after cleanup and correlation fixes.
Spec review: no remaining implementation findings after pre-execution policy
and identity checks. Both reviews explicitly leave native acceptance pending.

PowerShell parsing and actual Windows UI behavior have not yet been checked for
this desktop slice. The workflow includes the new script in its Windows parser
check. Fixture success does not establish inherited sign-in, usable desktop
controls, a live model command, or a Guardian decision.
