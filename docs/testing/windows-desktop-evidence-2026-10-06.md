# Windows desktop implementation checkpoint — 2026-10-06

Issue #82 has an implemented bounded desktop harness and operator-CLI fixture
coverage. **Real Windows ARM64 desktop acceptance is pending.** This checkpoint
must not be used to close #82 or claim Guardian qualification for #83–84.

The operator completed native app/CLI sign-in and sandbox setup under
`tofa-test`, then closed the apps. The template was normally shut down before
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

The Windows accessibility script has now executed in a disposable ARM64 clone,
including a successful semantic File → Quit action and clean owned-process exit.
The workflow also includes the script in its Windows parser check. Fixture success does not establish inherited sign-in, usable desktop
controls, a live model command, or a Guardian decision.

## Native attempts after sign-in

Two fresh-clone attempts failed before desktop model execution; neither is a
qualification pass. The source and everyday VM were not changed by either run.

1. [Attempt 1](evidence/windows-desktop-2026-10-06/native-attempt-1/report.json)
   found no unique healthy package while a pending app update was registering.
   AppX events and the post-reboot inventory establish the update transition.
   Readiness now reports the specific prerequisite and waits at most 30 seconds
   for registration. Distinct poll filenames prevent stale async UTM results.
2. [Attempt 2](evidence/windows-desktop-2026-10-06/native-attempt-2/report.json)
   passed that bounded registration wait, then found no user-local engine matching
   the new package. Installed package `26.930.7945.0` bundles engine `0.160.1`,
   SHA-256 `ce29231882a4b6c2cb5381f3ee311d29735fd63f45c432e2e704e12b0d31e78e`.
   The standalone CLI has the same version but a different hash; it was correctly
   rejected as a substitute. A real desktop launch initialized the matching cache.

Bounded diagnostic launches in the retained second clone exposed two harness
bugs: first-use PowerShell progress on stderr was mistaken for failure, and the
native Quit accessibility name includes its `Ctrl+Q` shortcut. Progress is now
suppressed while errors remain fatal; menu actions wait within a fixed deadline
and recognize the observed exact Quit label. The original failures and the
[successful bootstrap](evidence/windows-desktop-2026-10-06/native-attempt-2/bootstrap-passed.json)
are retained. The successful diagnostic made no model request and does not count
as a fresh-clone smoke or Guardian pass.

Public CLI checks after readiness fixes: 40 runner tests, 26 template tests, and
12 desktop tests passed. Type checking passed for the changed runner, transport,
and desktop runtime. The three readiness regressions were observed failing
before their fixes. The PowerShell and Quit fixes were exercised against their
recorded native failures; fixture tests alone cannot reproduce Windows UI behavior.

Template preparation after that bootstrap passed native sandbox and login checks
but caught a runtime trust override error: the engine's dotted override parser
retained quotation marks in the project path. The
[model-free diagnostic](evidence/windows-desktop-2026-10-06/trust-override-failure.json)
records only synthetic project entries, and the
[failed preparation](evidence/windows-desktop-2026-10-06/template-readiness-failed.json)
remains preserved. Readiness and the bridge now pass the synthetic project's
trust via a TOML inline table in the process-local configuration layer.

The corrected [public template preparation](evidence/windows-desktop-2026-10-06/template-readiness-passed.json)
returned `desktop_ready`: limited-user sandbox write/read, outside-write denial,
existing ChatGPT authentication, effective synthetic workspace trust, automatic
review, disabled Full access, and clean readiness-engine exit all passed. The
dedicated template then shut down normally. Both review axes found no issues
in the readiness, progress, menu-control, and trust-override fixes.
