# Windows desktop smoke acceptance — 2026-10-06

Issue #82 passed real Windows ARM64 desktop acceptance in a fresh clone through
the public operator CLI. [Attempt 6](evidence/windows-desktop-2026-10-06/native-attempt-6/report.json)
passed every stage and deleted its clone. This does not claim Guardian
qualification for #83–84. Implementation and evidence remain local.

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
  forwarding the synthetic prompt. Full access, network widening, models absent
  from the native catalog, unrelated workspace roots, and environment substitution
  are refused. Effective native settings must confirm the selected turn model.
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

The first two fresh-clone attempts failed before desktop model execution; neither is a
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

[Attempt 3](evidence/windows-desktop-2026-10-06/native-attempt-3/report.json)
failed `guest_task_incomplete` during engine discovery. Boot took 85.031 seconds,
readiness 96.703 seconds, and the package-engine hash checkpoint arrived at
69.302 seconds inside the limited task. The task deadline expired before engine
discovery completed; no desktop turn ran. The clone stopped normally and was
explicitly deleted after preserving the failure. An unchanged fresh-clone retry
was started after host regression work had finished to distinguish transient
resource contention from a reproducible deadline defect.

[Attempt 4](evidence/windows-desktop-2026-10-06/native-attempt-4/report.json)
passed native readiness in 41 seconds but failed the desktop smoke. Diagnostic
replays in that retained clone exposed helper/main bridge selection, renderer
permission selection, a schema-supported `guardian_subagent` reviewer alias,
and a trailing newline in the submitted synthetic prompt. These replays use
fresh synthetic workspaces but are not fresh-clone acceptance runs.

The desktop also attempts to write tool registrations into shared CLI settings.
An initial runtime-layer isolation approach failed its native verification:
`mcp_servers={}` merges with saved entries instead of clearing them. The final
bounded bridge explicitly rejects the narrowly recognized registration writes;
it does not claim that tools were registered or disabled. Unknown or mixed
shared writes remain fatal. Background title requests are refused before native
execution. Both expected restrictions have bounded counts in the durable report.
The synthetic command still requires independently verified native policy,
correlated execution and effects, normal quit, and unchanged CLI configuration.
A final audit checks fatal bridge events through owned-process shutdown.

A timed accessibility trace found a 13.843-second query exhausting the initial
15-second permission wait. Permission setup now has a 30-second bound, refreshes
the verified window handle, and remains inside the guest's 120-second task limit.
Subsequent replays selected automatic review and quit normally.

The desktop explicitly selects the built-in `local` environment. Its cwd and
runtime roots must match the synthetic workspace; configured remote environments
remain refused. The [native environment implementation](https://github.com/openai/codex/blob/main/codex-rs/exec-server/src/environment_toml.rs)
reserves the `local` identity. The desktop also requests one dated visualization
directory tied to the newly created native thread. Validation requires that exact
thread UUID, a valid date beneath the test profile's visualization directory,
no path redirection, and the limited user's ownership of the nearest existing directory.
The additional native writable scope is counted in the report; it is not described
as workspace-only access, and the runner does not clean unrelated visualization
storage. Negative tests cover another thread, shared directories, redirects,
and wrong ownership.

Native model selection can differ between thread startup and a collaboration-mode
turn. Only models advertised by the native catalog may change the initial model;
the effective native settings must confirm the selected identity before a pass.
Observed native rerouting fails qualification. The installed Windows engine's
schema was generated locally and retained as contract evidence. Native policy
notifications omit the cwd from their writable-root list because it is implicit;
the additional visualization root remains subject to the same ownership checks.
The original overly strict rejection and its fixture regression are preserved.

At this diagnostic checkpoint, native fresh-clone desktop acceptance was still
pending. The subsequent acceptance result is recorded below.

The [final diagnostic replay](evidence/windows-desktop-2026-10-06/native-attempt-4/tofa-run-2e76642dbaf54f0095d95166ddbfc1d0-desktop-replay.json)
passed the real desktop smoke in 52 seconds. Native effective identity was
`gpt-5.6-sol`, provider `openai`, reviewer `auto_review`. One correlated command
wrote and read the synthetic marker; normal quit, owned-child exit, final policy
audit, unchanged CLI settings, and preserved vendor service all passed. The
[bridge observations](evidence/windows-desktop-2026-10-06/native-attempt-4/tofa82-desktop-passed-bridge.json)
retain the native model and canonical policy confirmation. This reused diagnostic
clone does not satisfy the fresh-clone acceptance criterion.

The diagnostic clone was then [explicitly deleted](evidence/windows-desktop-2026-10-06/native-attempt-4/cleanup.json)
after preserving its attempts. Final Standards and Spec reviews found no new
implementation issues; both retained the fresh-clone acceptance requirement.

## Fresh-clone acceptance

[Attempt 5](evidence/windows-desktop-2026-10-06/native-attempt-5/report.json)
failed while pulling the protected staging result. Its retained clone contained
a successful staging result, and 20 repeated staging probes passed. The exact
original transport error was not captured, so its cause remains unconfirmed.
The clone was explicitly deleted after preserving the report and diagnostic results.

The unchanged implementation at `855cea9` then passed in a distinct fresh clone:
`tofa-run-faeec9194bea43ecb6a8379b1f36afa9`. A transparent UTM observer recorded
only sanitized error categories while forwarding the original transport results;
it did not retry or suppress errors. Source template and everyday VM were preserved.
Boot took 21.177 seconds, user-session checks 13.570, native smoke 45.367,
desktop smoke 70.972, and successful normal shutdown/deletion 5.774 seconds.

The native effective main was `gpt-5.6-sol`, provider `openai`, reviewer
`auto_review`. Desktop package was `OpenAI.Codex_26.930.7945.0_arm64__2p2nqsd0c76g0`;
the complete measured hashes, candidate identity, OS, and per-stage results are
in the report. No manual action was needed. A single correlated command wrote
and read the marker; all desktop policy, normal-exit, process cleanup, CLI-settings,
vendor-service, and diagnostic checks passed.

[Final regression validation](evidence/windows-desktop-2026-10-06/validation-final.json)
passed 344 tests with 80 platform-dependent skips in 532.316 seconds. Type checking
passed for the three changed Python production modules. Standards and Spec reviews
found no remaining implementation issues. The earlier failures remain preserved.
