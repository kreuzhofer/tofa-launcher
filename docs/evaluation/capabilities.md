# Bounded macOS capability evaluator

Issue [#118](https://github.com/kreuzhofer/tofa-launcher/issues/118) implements the
03/04/05/07 pilot agreed in [#117](https://github.com/kreuzhofer/tofa-launcher/issues/117).
This is an explicitly invoked development tool, not release qualification or a
Supported-model claim. The 24-cell campaign belongs to #119. No production prompt
change is included.

## Commands

Build the launcher from this revision. An older installed launcher cannot enforce
this evaluator's contract and is a preflight blocker. Python 3.9+ is required only
for the evaluator. Keep the client's existing installation, configuration and
skills; every invocation allocates a new private workspace and run ID.

```sh
go build -o /tmp/tofa-capability-launcher ./cmd/tofa
private_root=$(mktemp -d /tmp/tofa-capabilities.XXXXXX)
python3 scripts/capability_evaluation.py preflight \
  --private-root "$private_root" --case 05 --client cli \
  --model moonshotai/Kimi-K3 \
  --launcher /tmp/tofa-capability-launcher --codex "$(command -v codex)"
```

Preflight performs version, inventory, launcher-protocol and available-catalog
checks; it performs no inference. Its JSON includes a unique `run_id`, a stable
matrix `cell_id`, declared limits, provenance and explicit blockers. Even blocked
attempts remain under `$private_root/RUN_ID`. Private roots must be outside Git
and have mode 0700. The root contains sensitive request bodies and client logs;
share only the export.

Replace `preflight` with `run --live` to authorize one bounded attempt. A `run`
without `--live` retains a zero-inference blocked attempt. There is no batch,
automatic retry, model fallback or limit-increase option. Repeating the command
always creates another retained attempt, including after cancellation or failure.
Use `--compare-with /private/path/to/earlier/RUN_ID` to refuse detected environment
drift before inference. The recorded request audits also allow comparisons of
actual instruction ordering and tool schemas after execution.

For Desktop, use `--client desktop --app-bundle /Applications/ChatGPT.app` and
`--codex /Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex`.
The legacy flat bundle layout is supported only when the package directory is
absent, matching the launcher. The evaluator checks that this is the bundle's
engine. Native version and incumbent-owner refusal checks run during preflight
and again at launch. A successful preflight snapshot is not an ownership lease.

The operator creates a **new conversation in the printed fresh workspace** and
submits the exact contents of the run's `prompt.txt`. Do not open another task
through the evaluation launch. Requests outside the declared workspace/task, or
an initial main request with existing tool/assistant history, are refused. Later
requests must retain the initial user messages unchanged; a new user turn needs
a new attempt. This
workflow does not automate the Desktop UI or control another app-server session.
Keep the terminal running. After the turn and its naming request finish:

```sh
python3 scripts/capability_evaluation.py finish "$private_root/RUN_ID"
# Or cancel an unfinished run:
python3 scripts/capability_evaluation.py cancel "$private_root/RUN_ID"
```

The deadline, Ctrl-C, native request disconnection and cancellation stop only
the owned experiment. Desktop shutdown stays with the launcher's native ownership
and process-group checks; no process-name kill or incumbent takeover is added.
Native model routing, Guardian decisions and approval enforcement remain intact.
Automatic naming retains its independent Lightning route and shares the budget.

## Evidence and observations

```sh
python3 scripts/capability_evaluation.py observe "$private_root/RUN_ID" \
  --operator maintainer --criterion visible_preview --status passed \
  --reason both_previews_opened
python3 scripts/capability_evaluation.py export "$private_root/RUN_ID" \
  --output /tmp/new-capability-result.json
```

Observations are append-only and separately attributed; they do not overwrite the
original result. Use short categorical operator/reason codes, not private text.
Exports refuse existing output files. Content, language, skill use, file integrity,
reference syntax, visible preview, repetition and recovery have separate criteria.
Latency, usage completeness and request counts by role are separate measurements.
Missing token counters remain `null`, with usage completeness `false`, even when
the task response completes successfully.
`completed` describes an executed run, not an aggregate passing task score.

Unobserved preview is always `not_run / ui_check_pending`. A Markdown link or a
headless engine response never establishes UI success. The operator must open the
files and check the intended preview and obvious layout problems. Content,
language and skill-workflow judgments also require separately attributed inspection
when the automatic observations do not establish them. The private request/tool
history and output are retained for that inspection; missing evidence is not a pass.

Provenance records exact executable hashes/versions, Desktop application and
bundled engine, OS, catalog hash/check time, main and Guardian, settings hashes,
skill instruction/resource inventory, Python/Node/shell, harness, corpus, fixture
and prompt identities. Settings and inventory are checked again after a run;
drift is an infrastructure block, with original observations retained. Credential
contents are never copied or exported. No ordinary credential or global routing
settings are edited by the evaluator. Ordinary launcher integration rules remain
in force; an observed protected-settings change is reported, not restored from
a snapshot over concurrent user edits.

The request observer is registered by a new launch using an ephemeral authenticated
loopback handshake. It captures ordered instruction-role summaries and tool-schema
hashes **before** launcher adaptations. Raw requests stay in the private run
directory. System, developer and user messages are hashed in order, including
workspace or skill instructions delivered in user messages. Image inputs,
function/custom/namespace tools, native Guardian review
and the captured Desktop title contract are supported. Unknown input/server-tool,
server-side-history, auxiliary or compaction contracts fail explicitly as observer
limitations. Provider/adapter errors are not evidence of model task failure.
Server-hosted tools with independent unbounded inference are not supported.

An instruction experiment must provide both `--variant NAME` and
`--instructions /path/to/versioned-guidance.txt`. Its bytes are copied only into
that run's workspace `AGENTS.md`, hashed, and checked for delivery in the outgoing
main request. Baseline has no added instructions. An inventory `--skill-root`
does not install or enable a skill. `--codex-home` selects an existing persistent
home; the default is the ordinary client home.

## Bounds and conservative loop rule

| Cases | Whole-run deadline | All inference attempts | Output tokens/request |
| --- | ---: | ---: | ---: |
| 05, 07 | 180 seconds | 12 | 4096 |
| 03, 04 | 900 seconds | 80 | 8192 |

The deadline includes launch and operator startup time. The observer reserves a
shared request slot atomically before contacting the adapter, counts native
Guardian retries and title requests, and applies an explicit output cap without
raising a lower caller cap. Parallel tool calls are disabled for the experiment.
Socket shutdown bounds stalled and trickling streams; the launcher also has an
independent deadline. Request/event/response/workspace byte caps are recorded in
the result. Missing or partial usage remains incomplete. No currency cap
or estimated billing claim is implied.

An action is a completed model tool call/result observed at the request boundary.
Equivalence uses tool identity, canonical JSON arguments, conservative unquoted
spacing in single-line shell commands, and result content. Quoting, escapes,
multiline programs, exit codes and substantive output are retained. Only recognized
executor timing/chunk envelopes are removed. Polling with no input is excluded;
real workspace byte changes or a still-running process break the no-progress
streak. Five equivalent no-progress actions stop further inference. This is not
semantic detection of differently written programs, expanding XML windows, or
inner operations hidden inside a custom tool call. The recorded rule is scoped
to the observable client tool boundary.

Case 07 uses `python3`. Its own deterministic failure marker is recognized even
when a surrounding shell exits zero. The observer withholds a fourth diagnostic
tool proposal, and records completed calls, repeated unchanged actions and fixture
integrity separately. Diagnostic-rule success does not certify the explanation's
semantic correctness.

## Corpus and validation

The [v3 manifest](../../scripts/fixtures/capabilities/v3/manifest.json) fixes the
four prompts, per-case limits, fixture checksums and one-slide/one-page handoff
identity. Cases 03/04 start empty; 05 gets only the PPTX/PDF; 07 gets only the probe.
V3 adds an unambiguous recovery marker. The unchanged deck fixtures originate in
the retained prototype. [V1](https://github.com/kreuzhofer/tofa-launcher/tree/63898d1/scripts/prototype_capabilities)
and [V2](https://github.com/kreuzhofer/tofa-launcher/tree/3c66976/scripts/prototype_capabilities),
their earlier failures, calibrations and results remain preserved on their branch.

```sh
python3 scripts/capability_evaluation_test.py -v
python3 scripts/capability_observer_test.py -v
go test ./internal/tofa -run 'Test(Evaluation|DesktopEvaluation)' -count=1
TOFA_TEST_CODEX="$(command -v codex)" python3 scripts/capability_client_test.py -v
```

The optional installed-client calibration uses synthetic loopback responses and
synthetic launcher credentials while retaining the installed CLI and skills.
Every calibration attempt is retained privately and has zero paid inference.
The [#118 calibration record](evidence/capabilities-118/calibrations.json) indexes
all five development attempts and links the two final redacted exports. Installed
CLI 0.162.0 passed case 05 handoff and case 07 recovery against synthetic responses
with persistent skills/settings preserved. These checks validate observation and
supervision, not the named model's ability to perform the tasks.
The [validation record](evidence/capabilities-118/validation.json) includes all
28 Python suites, review-fix reruns, cross-builds and Go checks. Two existing
Desktop startup tests failed in the full race run and passed unchanged in an
isolated retry; both outcomes are recorded.
The Desktop executable fixtures test the native launch/ownership and naming
boundaries without claiming UI qualification. Real Desktop previews remain an
operator check. No 24-cell campaign, release or Supported promotion is performed.
