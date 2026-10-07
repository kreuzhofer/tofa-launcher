# Guided Windows catalog review — 2026-10-07

Follow-up for [#86](https://github.com/kreuzhofer/tofa-launcher/issues/86).
The maintainer chose automated environment preparation with a guided human build
review after the [unattended experiment](windows-catalog-evidence-2026-10-07.md).
The earlier failures remain recorded. The guided workflow does not relax the
native policy, provider-request, configuration-isolation, or cleanup checks.

## Reproduction

Run `bash .qualification/review-86.sh` in the maintainer's Mac terminal for this
prepared candidate, or use the generic
[review script](../../scripts/review_windows_catalog.sh) with the arguments in the
[runbook](windows-runs.md#guided-catalog-review). The local convenience script
pins the stopped source `EF96CF12-D901-455F-81FF-4C5001E15F80`, user `tofa-test`,
candidate `v0.1.0-rc.14`, candidate commit
`14134d43df4cca00bcdf10e49b3dc5ef3122f8d7`, and executable SHA-256
`1b0a2e7aa7aafc515391e221a16bee5124cf5b09aedf89af779796fae15bdd77`.

The host script opens UTM and invokes the public runner with `--guided-catalog`,
`--suite desktop-catalog`, `--test-auth native-session`, and `--timeout 1800`.
After automated preparation and native smoke, an owned supervised Windows console
guides setup, confirms both catalog choices, and asks the reviewer to select B/high
and submit exactly one synthetic prompt. The reviewer supplies no secrets to the
script. Human observations are explicitly marked `picker.mode: guided`.

The human console has 900 seconds within a 1200-second guest task, 1500-second
desktop stage, and 1800-second overall run. On cancellation, failed evidence or
timeout the runner stops and retains its owned clone. No timeout can become a
pass. The existing native bridge still refuses unverified policy and background
turns. Title classification now recognizes native camel-case `turnTrigger` and
`threadSource` metadata without enabling title execution.

## Native result and original failure

The maintainer completed the guided review in the disposable clone. The
[original report](evidence/windows-catalog-guided-2026-10-07/attempt-1.json) records
run `tofa-run-9ecfc526289644598f44ab035f906114`, clone
`4287E6FF-A80A-482F-A060-B12B0A39DB74`, desktop package
`OpenAI.Codex_26.930.7945.0_arm64__2p2nqsd0c76g0`, and engine 0.160.1.
The app and engine hashes match the preceding experiment. The
[host source hashes](evidence/windows-catalog-guided-2026-10-07/source.json)
identify the scripts used for this attempt.

The final native report contains all of these observations:

- Both synthetic picker choices were confirmed by the human reviewer; real
  B/low and B/high configuration writes received explicit session overrides.
- Exactly one HTTP `/responses` request reached the controlled provider with
  `model: tofa-catalog-b` and `reasoning.effort: high`.
- The selected native thread and updated settings passed policy verification:
  workspace-write sandboxing, on-request approval, and automatic review.
- The admitted native turn completed successfully. The provider intentionally
  returned an empty completion; no tool execution or generated answer text is
  claimed by this experiment.
- Concurrent synthetic CLI defaults survived before, during and after selection,
  mixed/unrelated probes, and shutdown. The mixed batch was refused atomically;
  the unrelated setting reached the native engine. Ordinary configuration and
  vendor service preservation checks passed.
- Normal app quit, owned app/engine exit, provider closure and diagnostic
  collection passed. No ordinary credentials were copied or inspected.

The runner nevertheless returned **`catalog_observation_failed`**. Its
`selected_request` and `native_turn_completed` booleans were measured before the
request/completion became visible. The final report then included the successful
request and native completion but retained those two stale false values. The
exact arrival time during later work/cleanup was not timestamped; only completion
after the early snapshot is established. The original failed report is retained
unchanged and is not relabeled as a passing runner invocation.

The [separate reconciliation](evidence/windows-catalog-guided-2026-10-07/attempt-1-reconciliation.json)
binds that original report by SHA-256. After confirming its shutdown and
collection checks, it recomputes only the two completion predicates from the
saved final request/events, checks matching app/engine identity, and runs the
catalog contract validator. The validator passes. Both independent reviewers
reproduced this result. This is retrospective validation of actual native evidence,
**not a fresh passing invocation of the fixed harness**.

The implementation now measures both predicates after shutdown and final event
collection. Its regression proves late final evidence replaces the early snapshot
and that a wrong/extra request or missing completion still fails. The
[post-fix source hashes](evidence/windows-catalog-guided-2026-10-07/source-after-finalization-fix.json)
are separate from the native attempt's source identity. The maintainer did not
repeat the human review solely to remeasure already-retained evidence.

## Demonstrated decision and production limits

A bounded static catalog plus process-local synthetic provider overrides is
compatible with the measured real Windows desktop and its matching engine when
native setup/permissions are completed by the reviewer. Explicit model/reasoning
selection reaches the selected B/high HTTP route. The narrow global-default
write interception with an explicit session override preserves concurrent CLI
defaults; unrelated native writes can be forwarded. Snapshot restoration is
neither required nor used.

| Background traffic | Measured disposition and product implication |
| --- | --- |
| Tool-registration writes | Explicitly refused by the bounded bridge; desktop browser/computer tools are not qualified. |
| Title turn | Native camel-case metadata now identifies it as `title`; it was refused. Title generation is not demonstrated. |
| Other auxiliary turn | Recorded as `unclassified` and refused. Its purpose and product behavior remain unresolved. |
| Other configuration writes | Explicit bridge restrictions remain; only the bounded unrelated animation-setting probe demonstrates native forwarding. |
| Outside-catalog native identity | Recorded and excluded from admitted synthetic requests; no silent substitution route was enabled. |

These observations complete the bounded catalog/default-write experiment. They
leave production routing gated on ordinary profile/IPC ownership, history,
background/tool contracts, and actual Token Factory qualification. No Windows
support label, named-pipe isolation, ordinary-history recovery, Guardian model
routing, or live Token Factory claim follows from this synthetic result.

## Cleanup and monitoring

The runner stopped and retained the owned clone after its original failure.
The maintainer ran explicit cleanup through their terminal; the saved
[cleanup result](evidence/windows-catalog-guided-2026-10-07/attempt-1-cleanup.json)
confirms deletion of that owned clone, and the lifecycle record is no longer retained.
The agent's separate UTM monitoring connection was denied by macOS Automation
(`OSStatus -1743`); the terminal runner's persisted report supplies the evidence.
No additional remote-control permission was requested. The source and everyday
VM were not lifecycle targets.

## Validation

- [Full Python suite](evidence/windows-catalog-guided-2026-10-07/full-python.txt): 386 tests passed, 80 expected platform/live-fixture skips, before the final completion-snapshot fix.
- [Final catalog suite](evidence/windows-catalog-guided-2026-10-07/catalog-tests.txt): 18 tests passed, including the completion-snapshot regression after the fix.
- [Go race suite](evidence/windows-catalog-guided-2026-10-07/go-race.txt) and `go vet ./...`: passed.
- Scoped Windows Pyright: zero errors/warnings in changed catalog/transport modules. The Mac-only clone runner reproduces the same nine optional-value diagnostics as baseline `a5f1959`; no new diagnostics.
- `bash -n`: passed for the wizard and local invocation. ShellCheck was unavailable.
- The real Windows guided console completed successfully; CI now also parses its PowerShell syntax.

[Validation metadata](evidence/windows-catalog-guided-2026-10-07/validation.json)
records scopes and skip reasons. The copied wizard library is unchanged from
[the wizard skill template](../../.agents/skills/wizard/template.sh).

## Standards

No remaining findings. Review covered app identity, owned Job Object cleanup,
human input, bounded deadlines, and final completion evidence after shutdown.
The original report hash and explicit retrospective reconciliation were verified.

## Spec

No remaining implementation findings. Independent review confirmed that the
retained native evidence establishes the bounded experiment without another human
review. The original failed runner outcome and absence of a fresh post-fix native
run remain explicit. Background refusals are production restrictions, not
successful product functionality. Owned-clone deletion is confirmed by the saved cleanup result.

Review totals: Standards 0; Spec 0 implementation findings. Native experiment
contracts established by the retained evidence and disclosed reconciliation.
