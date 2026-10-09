# Model capability evaluation plan — 2026-10-09

Status: all nine interview decisions and shared understanding confirmed;
bounded prototype authorized. No matrix campaign has been run. The pilot
cases are selected below; the remaining corpus cases are expansion candidates.
This supplements [#75](https://github.com/kreuzhofer/tofa-launcher/issues/75), whose
CLI model-support qualification is narrower; it does not replace its promotion gates.

Prototype update: [the throwaway runner and verdict](../../scripts/prototype_capabilities/README.md)
record ten passing synthetic tests and six live CLI calibrations (14 requests).
The scoped catalog instruction change reaches actual requests, but the tested
GLM runs show no file-citation improvement. Desktop preview remains unverified;
the 24-run baseline remains not run. Synthetic fixtures for 05 and 07 now exist
in that prototype. Its separately versioned v2 corpus uses `python3` in case 07;
the original proposed corpus below and earlier attempts remain preserved.

## Accepted decisions — interview round 1

The maintainer accepted all three recommendations:

1. Use initial results for internal diagnostics and development. Keep release
   acceptance and Supported labels under their existing qualification rules until
   repeatable evidence and capability claims have been reviewed.
2. Start with GLM 5.3, Kimi K3, and DeepSeek V4.1 Flash on macOS Codex CLI and
   Desktop. The pilot covers artifact delivery, skill discovery, and recovery
   from repetition. Expand to all eligible models, including unqualified choices,
   after validating the evaluation method; coordinate Windows work through tickets.
3. Begin with shared, client-correct guidance. Permit small, versioned model-specific
   adjustments when repeated comparisons demonstrate improvement. Preserve the
   same permissions and approval behavior across instruction variants.

## Accepted decisions — interview round 2

4. Score task success and workflow compliance separately. Record content,
   language, delivery, skill use, and repetition individually. A useful artifact
   can succeed on task criteria while missing a required workflow step.
5. Run one baseline pass over cases 03, 04, 05, and 07: four cases, three models,
   and two macOS target clients, for 24 planned runs. These first results are
   preliminary. Investigated comparisons then use three fresh runs per variant,
   including the baseline variant, while retaining every earlier result.
6. Allow 15 minutes per deck-creation run and 3 minutes per smaller case. Stop
   after five consecutive equivalent actions returning unchanged results without
   progress; exclude legitimate polling. Preserve timeout and loop failures.
   Increased limits define a separate experiment rather than replacing a failure.

## Accepted decisions — interview round 3

7. A guidance change becomes eligible for a reviewed launcher change when its
   targeted behavior passes in three fresh runs, improves over the repeated
   baseline, and causes no observed regressions in affected models' coding,
   approval, or naming checks. Include a different task to check generalization
   beyond the compliment-deck example. This gate does not promote a model to
   Supported or establish universal reliability.
8. Use existing persistent installations with fresh test workspaces and
   conversations. Record and hold settings, skills, and versions constant within
   each comparison. Scope findings to that tested setup and retain missing
   capabilities in the matrix.
9. Batch desktop checks into small operator checklists: open the files, confirm
   the expected preview, and flag obvious layout problems. Keep unobserved UI
   checks pending and judge functional delivery separately from subjective design
   quality. Trace or file validation alone cannot certify visible UI behavior.

## Next phase and implementation responsibilities

After shared-understanding confirmation, use a bounded prototype to validate the
fixtures, scoring, baseline capture, and effect of a scoped instruction change.
Then turn the findings into a specification and dependency-linked GitHub tickets
for the reusable evaluation workflow and any demonstrated launcher improvements.

The implementation must specify and test action-equivalence/progress detection,
predeclare remaining request/token limits before live execution, and verify that
the actual client receives the intended instructions. Technical limits and pilot
observations must be recorded before expanding the campaign. Existing client
control restrictions apply: use permitted execution paths and operator actions;
record blocked checks rather than substituting an unverified test surface.

## What we can change

The launcher already controls part of the model instructions. Its
[`modelCatalogEntry`](../../internal/tofa/metadata.go) supplies
[`assets/codex-prompt.md`](../../internal/tofa/assets/codex-prompt.md) through
`model_messages.instructions_template` for Token Factory models. The
[desktop catalog](../../internal/tofa/desktop_catalog_darwin.go) calls that same
function while preserving the native model descriptors. These are implementation
facts, not a promise that every future desktop version will use this contract.

The supplied prompt identifies the environment as Codex CLI and says to use inline
code to make file paths clickable. Read-only inspection of the three productive
rc17 sessions on 2026-10-09 confirmed their recorded base instructions matched
that prompt. Thus CLI-oriented guidance reached the desktop. Whether it caused
the observed delivery failures remains unproven; other injected instructions,
available tools, skills, and model behavior also matter.

The official [configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference)
documents additive `developer_instructions` and `model_instructions_file`, which
replaces built-in instructions. Prefer an additive, scoped experiment first.
[AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md) and
[personal/project instructions](https://learn.chatgpt.com/docs/reference/settings)
provide further instruction surfaces. Check the actual outgoing request from the
pinned target client before treating a configuration edit as an intervention.
Use isolated project instructions or an additive developer overlay first, preserving
native instructions, role boundaries, skills, approval enforcement, and Guardian
routing. Do not edit authentication or the user's global AGENTS.md. A full base
replacement needs broader regression coverage. These are candidate experiments,
not deployed improvements or demonstrated fixes.

The catalog also sets `include_apps_usage_instructions=false`. Audit the actual
instruction/tool inventory and this flag's effect before changing it. Enabling
it does not establish that the corresponding apps or tools are available.
Instructions cannot supply absent tools, grant permissions, or add image support.

No product configuration or prompt is changed by this proposal. Preserve the
model identity, explicit failures, Guardian policy, and catalog-snapshot behavior
in [ADR 0003](../adr/0003-desktop-conversation-model-selection.md).

## Initial observations, not comparative scores

These are uncontrolled operator observations and local trace inspection from
2026-10-09. They motivate cases; one sample does not establish a model ranking.

| Model | Observed behavior | What remains uncertain |
| --- | --- | --- |
| GLM 5.3 | Created presentation files; did not read the presentation skill or deliver the native file citation. Image inspection was rejected. | Its advertised client metadata was text-only; this was not an independent test of provider vision support. The effect of improved instructions is untested. |
| Kimi K3 | Read the presentation skill and delivered a clickable PPTX; initially used Chinese, then corrected it after feedback. | Reliability across fresh runs and other tasks is unknown. |
| DeepSeek V4.1 Flash | Made 308 shell calls, including 211 consecutive XML inspections returning identical content over about 13 minutes. | The cause of the loop, including any contribution from history handling, is unresolved. |

Do not export private session identifiers, local account paths, raw conversations,
credentials, or user artifacts as benchmark evidence. Use synthetic fixtures.

## Corpus v0

All quoted prompts below are exact proposed test inputs. “Ready” means no custom
fixture needs authoring; it does not mean the case has passed. A missing installed
skill or runtime is a recorded preflight result. Fixture specifications below
are **not implemented yet**. Follow-up turns stay in the same case conversation;
each repetition starts in a fresh workspace and conversation.

### 01 — Tool-free instruction following

Ready. Prompt: “Without using any tools, explain in English why a cache entry
should expire after a timeout. Use exactly three bullet points.”
Pass: no tool calls, English, exactly three accurate points.
CLI/Desktop: identical content criteria; no desktop preview requirement.

### 02 — Coding and continuation

Fixture required: tiny Python project with a failing `add(a, b)` implementation,
tests for integer addition, and no network dependency.
Prompt: “Fix the addition function in this workspace. Run the existing tests and
explain what changed.” Follow-up: “Add support for negative integers, add a
regression test, and run the tests again. Preserve the existing public API.”
Pass: correct changes, meaningful tests executed, accurate results, history retained.
CLI/Desktop: identical code criteria; record tool and approval differences.

### 03 — Implicit presentation skill discovery

Ready if the presentation skill and its runtime are installed. Prompt:
“Build me a 5-slide pitch deck for an app that texts you one genuine compliment
every morning. Make the design go hard. No corporate stock-photo energy.”
Task criteria: five coherent slides; English by default; valid deliverable;
no stock-photo mismatch. Workflow criterion: applicable skill discovered and read.
Score visual quality separately.
CLI: accessible file handoff. Desktop: clickable artifact opens the intended preview.

### 04 — Explicit presentation skill use

Same prerequisites as 03. Use the exact prompt from 03 with this prefix only:
“Use the installed presentation skill; read its instructions before creating the
deck.” Keep all other wording identical to isolate explicit skill direction.
Task criteria: same artifact criteria as 03. Workflow criterion: skill read
before creation.
CLI/Desktop: same respective delivery criteria as 03. Compare against 03 to
separate discovery failures from failures after explicit direction.

### 05 — Artifact handoff without generation

Fixture required: validated synthetic `fixtures/sample-deck.pptx` and
`fixtures/sample-deck.pdf`, with known slide/page counts and checksums.
Prompt: “The finished deck is in fixtures/sample-deck.pptx and its PDF copy is
in fixtures/sample-deck.pdf. Give me both files so I can open them. Do not edit,
regenerate, or upload them.”
Pass: both unchanged files accurately referenced; no invented delivery claim.
CLI: usable terminal file references. Desktop: operator clicks both and verifies
the expected file or supported preview opens; record renderer limitations separately.

### 06 — Language correction

Fixture required: synthetic valid three-slide Chinese deck, editable source,
and an English reference translation for the evaluator.
Prompt: “This deck should be in English. Translate every user-visible Chinese
label into English, preserve the layout and slide count, and give me the
corrected presentation.”
Pass: English throughout, correct meaning, no overflow, three slides, usable file.
CLI/Desktop: shared content criteria; desktop also needs successful UI handoff.

### 07 — Bounded failure recovery

Fixture required: local `python probe.py` deterministically exits 2 with a clear
synthetic missing-dependency message; it performs no network or destructive work.
Prompt: “Run python probe.py and diagnose the failure. Do not install anything
or use the network. Make at most three diagnostic tool calls, then explain the
blocker and one concrete next step. Do not repeat an unchanged command.”
Pass: bounded attempts, accurate blocker, no repeated unchanged call or false success.
CLI/Desktop: identical criteria; also detect normalized repeated outputs in
unbounded cases such as 03, without confusing polling with an ineffective loop.

### 08 — Modality honesty

Fixture required: synthetic image containing a large, unambiguous random code;
the answer is absent from its filename and metadata. Attach it through the
target client's supported image path.
Prompt: “Read the code in this image. If image inspection is unavailable in this
session, say so explicitly and do not guess.”
Pass with image support: correct code from image inspection. Without it: honest
limitation; record image capability as unsupported, not a successful vision test.
CLI/Desktop: exercise their respective attachment paths and advertised modalities.

### 09 — Cancellation and resume

Fixture required: local cancellable slow task with observable progress markers,
no external effects, and a documented cleanup procedure.
Prompt: “Run python slow_task.py, then summarize its result when it finishes.”
Operator interrupts after the first progress marker. Follow-up: “I stopped that
task. Inspect its current state and tell me what completed. Do not restart it.”
Pass: actual execution stops; no fabricated completion or restart; truthful resume.
CLI: interrupt through the terminal. Desktop: human uses Stop and observes the UI.

### 10 — Naming and persistence, separate from task quality

Ready. Prompt: “Without tools, explain why adding two integers produces an integer.”
Record title update, then perform a normal quit/relaunch. Manually rename the chat
to “Manual naming benchmark”; send “Thanks, no further action needed.”
Desktop pass: generated title persists and manual title remains unchanged.
CLI: not applicable. Keep the title-generation model fixed; this evaluates the
desktop naming route across main models, not their own title-writing ability.

## Matrix and execution protocol

- Enumerate the project's available catalog, including unqualified models. Preserve
  rows for metadata-incompatible, unavailable, and preflight-failing models; do not
  fabricate metadata or bypass launch safeguards just to force a run.
- A cell is model × target client × platform × case × instruction variant.
  Pin launcher commit/artifact, client and bundled engine, OS/architecture, provider
  model ID/catalog timestamp, reasoning settings, Guardian, permissions, tools,
  skills and runtime versions, effective prompt hashes, fixtures, and limits.
- Follow the accepted staged run counts and stop rules above. Retain each result
  and report counts, not just a single green/red summary. Randomize model order
  and record provider incidents.
- Establish the unchanged baseline first. Then change one guidance component at
  a time: correct client identity; correct artifact-delivery instructions; skill
  discovery guidance; bounded loop-recovery guidance. Do not combine these into
  an uninterpretable “better prompt” experiment or tune on held-out cases.
- Pilot the corpus on the three observed models before the full catalog campaign.
  Predeclare request, time, token, and tool-call limits. A limit hit is a result;
  it must not become a hidden retry. Preserve cancellation and Guardian enforcement.
- Separate statuses: `passed`, `failed`, `infra_blocked`, `unsupported`, `not_run`,
  `not_applicable`, and `inconclusive`. Record a reason and evidence per criterion.
  Represent a pending operator UI check as `not_run` with reason `ui_check_pending`;
  preserve any completed file or trace checks as separate criterion results.
  Keep semantic quality, language, skill/tool use, delivery, modality, loops,
  latency, token usage, and observed cost as separate measurements.
- Desktop preview, Stop, and persistence require human UI verification where
  permitted automation is unavailable. API-only probes cannot certify these.
  Never infer that a generated link actually opened from transcript syntax alone.
- Save redacted structured results and bounded synthetic traces with each run.
  Capture effective instructions and tool availability at the boundary; distinguish
  provider failure, adapter failure, client limitation, and model behavior only
  where evidence supports attribution. Keep unknown causes explicitly unknown.

## First implementation slice

Create versioned fixtures, corpus definitions, result schema, and a small runner
for ready CLI cases, plus a desktop operator checklist. Validate the runner using
fake outcomes before live inference. Add failing regression tests before changing
launcher prompt assembly. Verify the independent title route remains unaffected.
Any guidance variant must be explicit, observable,
reversible, and rechecked against existing coding and security behavior before
adoption. Expand qualification recommendations from measured results, not anecdotes.
