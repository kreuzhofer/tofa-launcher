# Windows ARM64 desktop bridge — throwaway prototype

Question: can the installed Windows desktop launch an owned executable bridge
while retaining native sandbox and Guardian enforcement?

**Verdict: desktop → bridge → engine initialization works. Qualification is
blocked by a native sandbox setup failure that also reproduces without the
bridge, including registered Windows activation. Guardian allow/deny remains
unmeasured.**
This is not Windows desktop support and does not unblock #77.

This directory exists only on `prototype/windows-desktop-bridge`, based on
`b7196a6`. Production launcher code is unchanged. The governing contract and
remaining acceptance gates are [issue #77](https://github.com/kreuzhofer/tofa-launcher/issues/77)
and the [research report](../../docs/research/windows-desktop-contract-2026-10-05.md).

## Tested state

The maintainer approved normal shutdown → clone → original restart. That sequence
completed; the original was restarted. Subsequent desktop experiments use only
the owned clone `EF96CF12-D901-455F-81FF-4C5001E15F80`, named
`tofa77 Windows ARM64 bridge prototype`. See [DECISIONS.md](DECISIONS.md).

After reboot, the interactive user's selected package changed from the #76
baseline to `OpenAI.Codex_26.930.6422.0_arm64__2p2nqsd0c76g0` (status OK).
The newly selected package's JavaScript version is `26.930.51102` and its engine
reports `0.160.0` in initialization. The actual native engine path is
`%LOCALAPPDATA%\OpenAI\Codex\bin\adbebd79223f9e27\codex.exe`, SHA-256
`c98b873f74c4c2ae392c9b90474d9d4a17405a1d893951b4893305002bb7582a`, matching
the selected package's bundled engine. The old relocated engine was subsequently
removed by native lifecycle. Registration and matching executable identity must
be rediscovered; old research identity is not a durable runtime contract.

Final recorder binary SHA-256:
`1fea5156a7db94b35d4e26d6224f55dca8995dde30b44a28881ce83b10c06718`.
Build tools: Go 1.27.1, Windows ARM64 with CGO disabled. Source fingerprints for
the changed native package are in `evidence/updated-package-source.json`; vendor
source, credentials and conversation bodies are not included.

## Established observations

- The transparent bridge preserves argv, inherited environment, opaque stdio,
  stderr and nonzero child exit status. Hash mismatch refuses with exit 125.
  Evidence contains whitelisted metadata only. Four executable-boundary tests
  pass on the host with the race detector and on Windows ARM64.
- An Interactive/Limited isolated engine probe passed initialize/config read,
  EOF exit 0, engine-hash refusal and removal of its synthetic temporary home.
  It submits no model turns and never reads the user's credentials.
- The conservative preflight returns 41 while the native app is running without
  launching, adopting or terminating it. With no incumbent it returns 42; it
  intentionally does not grant launch ownership.
- Ordinary clone startup showed the signed-in Codex home. The bridge-backed
  desktop also reached that surface. No preexisting conversation was opened.
- The actual main chain was observed separately from a short-lived startup helper:
  `ChatGPT.exe (5828) → bridge.exe (9740) → codex.exe (2628)`. Both initialized.
  This is actual native desktop startup, not just a standalone engine probe.
- The override removed registered-core/package-family environment markers and
  supplied no sandbox-service argument. Nevertheless, native startup changed
  reported `features.windows_sandbox_service` from false to true. The prototype
  did not inject private identities or rewrite native settings. Missing markers
  alone therefore do **not** establish a vendor prohibition or sandbox failure.
  A true feature flag still does not prove effective tool isolation.
- Native configuration's null policy values are reported as `unset`, not as an
  effective thread policy. Older evidence used `other` for null; those historical
  fields cannot establish policy. A regression test covers the correction.
- Normal quit through the native File → Quit ChatGPT action left no observed
  app/bridge/engine processes while `CodexSandboxService.OpenAI.Codex` remained
  running. No force termination or vendor-service cleanup was used.
- Both ordinary and packaged profile-directory candidates exist. Their existence
  does not establish actual profile ownership, named-pipe ACLs or singleton
  isolation. Those production gates remain open.

## Run the bounded checks

From the repository root, with Go and Python 3 available:

```sh
python3 prototypes/windows-desktop-bridge/test_bridge.py
GOOS=windows GOARCH=arm64 CGO_ENABLED=0 go build -trimpath -buildvcs=false -o /tmp/tofa77-bridge.exe ./prototypes/windows-desktop-bridge
python3 prototypes/windows-desktop-bridge/run-guest.py --vm EF96CF12-D901-455F-81FF-4C5001E15F80 --bridge /tmp/tofa77-bridge.exe
python3 prototypes/windows-desktop-bridge/desktop-stage.py observe
```

The guest runner requires the owned clone to be running, an interactive user,
`C:\Python313ARM\python.exe`, the pinned engine and a native app instance already
open for the refusal assertion. It stages a unique Public directory, runs a
Limited task and requires fresh result/task envelopes. It unregisters the exact
completed task. Scratch scripts, binaries and sanitized evidence remain for
inspection. Only the synthetic probe home is removed.

`desktop-stage.py baseline` directly starts the selected executable without
an override; `desktop-stage.py registered` uses the discovered StartApps identity
and Windows AppsFolder activation;
`desktop-stage.py bridge --bridge /tmp/tofa77-bridge.exe` starts it with the bridge
override. All launch modes refuse if an app is already running. Quit the clone app normally
before either launch; `observe` is read-only. The desktop runner hardcodes the
owned clone identity, verifies a single interactive-user ARM64 registration and
matches the relocated and bundled engine hashes. These are qualification pins,
not a proposed exact-version production allowlist.

The bridge has no production ACL policy, authenticated ownership record, singleton
protocol, Job Object supervision or robust abrupt-exit cleanup. A timeout is a
failed experiment; normal EOF and the observed normal desktop quit are the only
established cleanup paths. Evidence-write failure exits 125 but has no guaranteed
child cleanup. Do not deploy this bridge as a launcher.

## Evidence index and retained failures

Each attempted run remains in `evidence/`; successful task reports require
`last_result=0` and `unregistered=true`.

- `clone-attempt.json`: UTM refused cloning a running VM despite host exit 0.
- `clone-created.json`: approved shutdown/clone/restart completed.
- `tofa77-20261005T114728Z`: staging race failed; added fresh readiness envelope.
- `tofa77-20261005T114800Z`: guest passed but task-evidence retrieval failed due
  to a backslash escape. The whole attempt remains failed.
- `tofa77-20261005T114846Z` and `114950Z`: early no-turn and native fixture passes.
- `tofa77-desktop-20261005T122231Z`: ordinary new-package baseline. Its
  `engine_sha256` field still refers to the old preflight engine, whereas its
  observed native process path selects the new engine. This mismatch was caught
  and corrected before the bridge launch; do not treat that field as the app's
  actual engine identity.
- `tofa77-desktop-20261005T122713Z`: task submission exceeded argument size;
  no app launch. Subsequent runs stage a script file.
- `tofa77-desktop-20261005T122826Z` and `123334Z`: first desktop bridge main
  initialization and follow-up process/config observation.
- `tofa77-20261005T123415Z`: stale old engine path failed after native removal;
  the failure is preserved. New selected-engine pins are used afterward.
- `tofa77-20261005T123559Z`: corrected pins, three native tests and no-turn pass.
- `tofa77-desktop-20261005T125451Z`: normal quit cleanup; vendor service running.
- `tofa77-desktop-20261005T125527Z`: recorder reload launched, but reporting
  failed on unavailable process path metadata. Task result 1 is retained.
- `tofa77-desktop-20261005T125839Z`: follow-up observation passed after making
  unavailable process metadata explicit; actual main chain initialized.
- `tofa77-20261005T125806Z`: final recorder, four native tests, no-turn engine
  initialization, EOF cleanup and hash-refusal assertions passed.

Tests were written first at the public executable/protocol boundary. The native
review recorder's fixture proves sanitized notification recording, not a live
Guardian decision. Historical `inference_requests=0` fields describe no-turn
stages at collection time; later stages use `turns_submitted_by_stage` to avoid
claiming that observation measures all app activity.

## Remaining qualification

Three bounded native shell trials failed before executing the command:

| Route | Trial | Observed result |
| --- | --- | --- |
| Desktop → bridge → engine | Write/read a workspace marker | Setup failure; marker absent |
| Direct executable, no bridge | Identical write/read request | Same setup failure; marker absent |
| Registered AppsFolder, no bridge | Print `TOFA77` only | Same setup failure |

All three returned:

```text
exec_command failed: CreateProcess { message: "Rejected(\"Failed to create unified exec process: helper_unknown_error: setup refresh had errors\")" }
```

The mode was visibly “Approve for me”, selected manually by the maintainer after
explicit permission. Each prompt required the normal sandbox and stopping on
failure without escalation. Three shell-attempt turns and one no-tool error
formatting turn were submitted, using the native selected main model. No Token
Factory adapter or Guardian override was installed. No live review completion
was recorded. A setup rejection is **not** a Guardian-denial pass. The planned
external-file allow/deny trials were not run after this prerequisite failed.

Exact errors were extracted only from sessions whose metadata cwd matched the
owned scratch workspace, and agree with visible UI results. The first extractor
looked only for function-call outputs and missed native custom-tool output
arrays; earlier empty error arrays must not be interpreted as successful tools.
`tofa77-desktop-20261005T131207Z` captures the first two errors;
`131436Z` and `131554Z` capture all three.

The next investigation is the **ordinary native sandbox setup/refresh failure
in the clone**, before trying to qualify the bridge again. Removing the bridge,
using registered activation, and removing the file write did not remove the
failure. The underlying cause remains unknown. This bounded prototype stops at
that reproducible prerequisite failure; it does not change sandbox accounts,
credentials, private package identity, policy or native vendor code to proceed.

Normal final quit was observed in `131554Z`: no app/bridge/engine processes,
vendor sandbox service still running, no other prototype scheduled tasks. Final
UTM inventory showed both original and clone running. The clone retains its
scratch workspace, synthetic test chats and authorized test-mode preference for
inspection, with the test app closed and no further turns running. Original VM
settings were not changed by these clone trials.

Additional retained attempts:

- `130237Z` / `130419Z`: bridge trial observation and marker absence.
- `130457Z`: successful direct ordinary recovery; `130718Z` / `130916Z`:
  ordinary trial and refinement of the narrow error extractor.
- `131058Z`: registered activation preparation refused an assumed manifest
  executable match. No app launched. The next attempt resolved the registered
  StartApps identity instead and passed startup.
- `131436Z` / `131554Z`: guest reports succeeded, but the host runner treated
  PowerShell CLIXML progress on stderr as a transport failure during task-envelope
  collection. Both failed host attempts are retained. Separate read-only pulls
  recovered `last_result=0`, `unregistered=true` envelopes in
  `recovered-task.json`; no guest task was rerun for recovery.

The full #77 matrix remains gated: actual profile/pipe ownership and ACLs,
entitlement/policy failures, Token Factory main/Guardian routing, picker and
history behavior, concurrent CLI defaults, installation lifecycle, abrupt exit,
updates, uninstall and ordinary recovery. No Windows production support claim
follows from the initialization result.
