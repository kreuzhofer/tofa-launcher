# Windows desktop catalog and default-write experiment — 2026-10-07

The later [guided human review](windows-catalog-guided-evidence-2026-10-07.md)
establishes the selected B/high native request and policy that were missing here.
This document retains the original unattended failures and their scope.

Issue [#86](https://github.com/kreuzhofer/tofa-launcher/issues/86), under
[#77](https://github.com/kreuzhofer/tofa-launcher/issues/77).

This is a bounded experiment using the existing owned test bridge, the registered
Windows desktop and its matching native engine. It does not enable a production
Windows launcher route or qualify Token Factory support. Ordinary profile/IPC
ownership and history recovery remain separate unresolved contracts from #85.

## Reproduction

The prepared source must already be stopped. The command uses the existing
runner state directory, serialization, native readiness, guest task limits and
ownership-checked cleanup. The everyday VM and source are never stopped or
modified by this operation.

```sh
python3 scripts/windows_test_runner.py run \
  --state-dir .qualification/windows-clone-runs \
  --template EF96CF12-D901-455F-81FF-4C5001E15F80 --dedicated-template \
  --test-user tofa-test --suite desktop-catalog --test-auth native-session \
  --candidate .qualification/rc14/assets/tofa_v0.1.0-rc.14_windows_arm64.exe \
  --version v0.1.0-rc.14 \
  --sha256 1b0a2e7aa7aafc515391e221a16bee5124cf5b09aedf89af779796fae15bdd77 \
  --candidate-commit 14134d43df4cca00bcdf10e49b3dc5ef3122f8d7 \
  --timeout 1800
```

The candidate is measured provenance, not a Windows desktop implementation.
The Python/PowerShell experiment is the changed artifact. After native readiness
and the existing native OpenAI desktop smoke, it creates a separate synthetic
engine home and Electron profile under the owned clone workspace. No ordinary
credentials are copied. A two-model static catalog and a loopback Responses
provider are process overrides. The concurrent native CLI engine shares only
that synthetic configuration. The bridge retains native sandbox and automatic
review policy; the synthetic provider never proposes tools or approval decisions.

The desktop must advertise and visibly offer `tofa-catalog-a` and
`tofa-catalog-b`. The experiment selects B and high reasoning, submits one bounded
synthetic prompt, and checks the native turn plus the actual provider request.
It also exercises mixed and unrelated writes through the executable bridge and
matching native engine while checking the concurrent CLI defaults.

## Native result and decision

The experiment is **negative for selected-request execution**. The real desktop
visibly offered both synthetic models and emitted separate `config/batchWrite`
requests for B/low and B/high after explicit UI selection. The settings envelope
and containment below are demonstrated. No synthetic provider request or completed
synthetic turn was observed. Production routing remains blocked.

[Diagnostic replay 7](evidence/windows-catalog-2026-10-07/replay-7.json) completed
the UI interaction and settings checks in the owned clone. Its native selected
thread used `tofa-catalog-b` with provider `tofa-catalog`, but the returned policy
did not satisfy the bridge: the reviewer was `user`, not `auto_review`, and the
sandbox check failed. The synthetic turn was explicitly refused. The isolated
home displayed “Finish Windows setup to continue” in preceding UI diagnostics.
That is an observed setup gap, not proof that setup is the only cause of the
policy mismatch. We did not click through native setup, copy sandbox state or
credentials, rewrite native policy responses, or relax the turn guard.

The smallest demonstrated-compatible settings behavior is a narrow interception
of global model/reasoning writes with an explicit `okOverridden` result and
session metadata. This envelope allows the renderer to continue through its
picker. **It does not yet establish a compatible inference route.** Preserve this
boundary as an experiment until a properly initialized owned synthetic home can
create the selected thread under native automatic review and workspace-write
policy, then deliver exactly B/high to the controlled provider.

The [final fresh public-runner attempt 4](evidence/windows-catalog-2026-10-07/attempt-4.json)
reproduced this negative result with the frozen scripts: native baseline smoke
passed; the picker selected B/high; every catalog containment and cleanup check
passed except `selected_request` and `native_turn_completed`. Its selected-thread
sandbox was explicitly `readOnly` and automatic-review verification failed.
The bridge refused the synthetic turn; the provider received zero requests.
The runner returned `catalog_observation_failed` and retained the stopped clone.
After saving this report, explicit [cleanup](evidence/windows-catalog-2026-10-07/attempt-4-cleanup.json)
deleted only that owned clone. Frozen script hashes were rechecked unchanged.

## Protocol and containment

The renderer sent `config/batchWrite` with `reloadUserConfig: true`, no expected
version, and accepted edits for `model` and `model_reasoning_effort`. The bridge
accepts `replace`/`upsert`; retained events do not distinguish those strategies. Selecting B
first wrote B/low; the Power control then wrote B/high. The menu remains open after
model selection. Power is a keyboard control; focusing it and sending Right,
Enter and Escape produced the high-effort write. Every key is guarded by the
owned app's foreground process identity.

The bridge follows ADR 0003: a recognized global default write becomes native
`config/read` with layers. The user layer must refer to the owned synthetic
configuration file and expose a version. Only after successful native validation
does the bridge return `okOverridden` with explicit session metadata. A pending
or refused request never counts as successful containment. It never writes these
defaults or restores a settings snapshot.

In replay 7 the concurrent native CLI began with `synthetic-cli`/low, then wrote
`synthetic-cli-concurrent` while the desktop remained open. It retained that value
through submission, settings probes, and desktop shutdown. A mixed model plus
`tui.animations` batch was refused atomically. The unrelated boolean animation
write reached the native engine and was visible to the CLI. These two probes use
the same executable bridge and matching native engine in a separate app-server
connection; they are deliberately submitted protocol probes, not claims that the
renderer naturally issued those exact batches. The ordinary config bytes and
vendor service inventory were unchanged, the provider closed, and owned app and
engine processes exited. Stale versions, profile writes, malformed requests and
native error/layer failures are additionally covered by executable fixtures.

Model-list success alone cannot satisfy the public runner. Missing picker or
protocol evidence, wrong HTTP request identity, changed CLI defaults, mismatched
native engine identity, and failed cleanup all fail. Even a fully successful
synthetic run can only record `experiment-complete`, with production blocked.

## Background traffic and restrictions

| Observed traffic | Classification and measured disposition |
| --- | --- |
| Desktop tool-registration writes | Explicit test-bridge restriction; refused without writing CLI settings. Browser/computer tools are not qualified. |
| `remote_control`, `features.remote_control`, `desktop.followUpQueueMode` writes | Unrelated renderer defaults, explicitly refused by this bounded bridge. Their product functionality is not demonstrated. |
| Native `gpt-5.5` identity outside the injected catalog | Recorded and excluded from admitted synthetic turns; not silently mapped to a synthetic model. |
| Separate helper thread and nonmatching turn input | Background traffic, refused. The retained trace classifies its purpose as `unclassified`; title/summary generation is not qualified. |
| Main B/high synthetic turn | Refused because the native thread did not meet the existing policy contract. No HTTP request reached the provider. |

The classifier recognizes fixed title/summary metadata when present and otherwise
records `unclassified`; it does not guess a successful title flow from a refusal.
Resolving tool registration and title/background behavior remains necessary for
production. This isolated profile does not prove named-pipe isolation,
ordinary-history recovery, or live Token Factory support.

## Retained attempts

All reports remain available, including failed automation and setup attempts.
The native app was `OpenAI.Codex_26.930.7945.0_arm64__2p2nqsd0c76g0`, with matching
engine 0.160.1. Measured app SHA-256:
`5474239dcfa9d1548d8bcd9219b8fd3474f1157f923555e9738f789dd4a81abe`;
engine SHA-256:
`ce29231882a4b6c2cb5381f3ee311d29735fd63f45c432e2e704e12b0d31e78e`.

| Attempt | Result |
| --- | --- |
| [1](evidence/windows-catalog-2026-10-07/attempt-1.json) | Native baseline passed; model-choice automation failed. The picker showed A/Light; no HTTP request. [Protocol](evidence/windows-catalog-2026-10-07/attempt-1-protocol.json) retained. Owned clone stopped and deleted after collection. |
| [2](evidence/windows-catalog-2026-10-07/attempt-2.json) | Slow native readiness followed by existing desktop-smoke startup failure; catalog was not run. Owned clone explicitly deleted. |
| [3](evidence/windows-catalog-2026-10-07/attempt-3.json) | Baseline passed; model-button automation failed. [Protocol](evidence/windows-catalog-2026-10-07/attempt-3-protocol.json) retained. Diagnostic collection needed a [forced stop](evidence/windows-catalog-2026-10-07/attempt-3-diagnostic-cleanup.json) of this owned clone. |
| [Replay preparation](evidence/windows-catalog-2026-10-07/replay-preparation-failure.json) | Host SID lookup error; no guest catalog task submitted. |
| [Replay 1](evidence/windows-catalog-2026-10-07/replay-1.json) | UI process timeout; app required bounded termination, other cleanup checks passed. |
| [Replay 2](evidence/windows-catalog-2026-10-07/replay-2.json) | Model-button failure after treating the setup Continue button as onboarding. The final driver does not click it. |
| [Replay 3](evidence/windows-catalog-2026-10-07/replay-3.json) | Both models visible; real B/low write observed, but overly strict native layer matching refused it. |
| [Replay 4](evidence/windows-catalog-2026-10-07/replay-4.json) | Native layer/file identity validation and session override passed; reasoning trigger lookup failed. |
| [Replay 5](evidence/windows-catalog-2026-10-07/replay-5.json) | Waiting for a closed-menu B trigger failed while the menu remained open as Select effort. |
| [Replay 6](evidence/windows-catalog-2026-10-07/replay-6.json) | Located Power, but incorrectly treated it as a submenu. |
| [Replay 7](evidence/windows-catalog-2026-10-07/replay-7.json) | Both selections and settings containment passed; native selected-thread policy failed, no inference. |
| [4: final fresh run](evidence/windows-catalog-2026-10-07/attempt-4.json) | Frozen-source run reproduced successful picker/settings checks and a negative selected-thread policy result (`readOnly`, reviewer check false). No inference. Evidence saved; owned clone explicitly deleted. |
| [Final-run preflight](evidence/windows-catalog-2026-10-07/retained-limit-preflight.json) | Retained-clone limit refused a new run before creation. After saving diagnostics, only this task's replay clone was deleted. The earlier unrelated retained clone was preserved. |

Replays 1–7 reused only attempt 3's owned clone. Each ran a fresh limited-user
catalog task with fresh synthetic state through the existing transport and
serialization lease; each stopped the clone normally afterward. They reused the
already-measured smoke wrapper and did not repeat full baseline qualification.
The [diagnostic driver](evidence/windows-catalog-2026-10-07/diagnostic-replay-driver.py)
is retained as an artifact of that run; its clone identifiers are historical.
Use the public command above for reproduction in a new clone.

The [attempt 3 host-start snapshot](evidence/windows-catalog-2026-10-07/attempt-3-host-start-source.json)
is not an immutable guest-source attestation: implementation evolved while early
attempts were being staged. The final fresh attempt uses the
[frozen host-source hashes](evidence/windows-catalog-2026-10-07/attempt-4-source.json).

## Validation and final state

- [Full Python suite](evidence/windows-catalog-2026-10-07/full-python.txt): 381 tests, 80 expected platform/live-fixture skips, passed in 695.9 seconds. The [driver](evidence/windows-catalog-2026-10-07/full-python-driver.py) supplies the lifecycle distribution and terminal binary required by those tests.
- [Final catalog suite](evidence/windows-catalog-2026-10-07/catalog-tests.txt): 13 tests passed, including the HTTP-input regression added after full-suite discovery.
- [Go race suite](evidence/windows-catalog-2026-10-07/go-race.txt): `go test -race ./...` passed; `go vet ./...` passed.
- Scoped Pyright with `--pythonplatform Windows` reported zero errors or warnings across changed catalog/bridge/probe modules; `git diff --check` passed.
- The real Windows task executed the final PowerShell picker successfully. CI now includes both catalog tests and parsing of that script.

[Validation metadata](evidence/windows-catalog-2026-10-07/validation.json) lists
skip reasons. Live desktop fixtures and native-Windows-only tests skipped on the
macOS host; the bounded ARM64 run above is separate native evidence. The first
full-suite invocation lacked Go on PATH and was interrupted after build failures;
the successful rerun used the existing `/private/tmp/tofa75-oct05/go/bin` toolchain.
The full-suite driver uses the existing `v0.0.0-prototype` distribution for
installer/terminal checks; this is not the rc.14 native candidate provenance.

The [final VM inventory](evidence/windows-catalog-2026-10-07/final-inventory.json)
matched the initial source/everyday/unrelated/pre-existing-retained identities and
states. All clones created for this task were deleted after saving evidence; the
runner reported idle and unlocked. No ordinary credentials or vendor service
settings were modified.

## Standards

Malformed write inputs, independent cleanup failure handling, and malformed HTTP
request accounting were found during review and fixed with executable/HTTP
regressions. The owned-app keyboard focus boundary passed review. Final code
recheck: no remaining Standards findings.

## Spec

A premature successful-override evidence event was found and fixed: only a valid
native layer/version response now permits it. Final implementation recheck found
no remaining code findings. A prose claim about an unrecorded merge strategy was
softened to match the evidence. Native selected-request execution is incomplete;
the negative result and production blockers above remain explicit.

Review totals: Standards 0 remaining; Spec 0 remaining implementation findings,
with native acceptance blocked by the measured selected-thread policy failure.
