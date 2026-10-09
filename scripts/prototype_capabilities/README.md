# Throwaway capability evaluation prototype

This branch investigates whether a bounded evaluator can distinguish artifact
creation, delivery, workflow compliance and visible Desktop behavior, and whether
a scoped file-reference instruction change reaches a real client request.
It is not the reusable evaluator or a production prompt change.

**Experimental source build:** this branch now includes a Desktop-only
`desktop-markdown-links-v1` candidate in `desktop_catalog_darwin.go`. Building
this branch changes the file-reference section for GLM 5.3, Kimi K3 and DeepSeek
V4.1 Flash, except any model selected as Guardian. The shared CLI prompt, native
descriptors, other catalog flags and independent naming policy are unchanged.
The guidance explicitly gives document Markdown links precedence over the generic
monospace instruction. Keep this binary distinct from published rc17; do not
merge or publish it as release guidance before the agreed comparison gates pass.

The new public-launch fixture test failed for all three mains before the change
and passed afterward. Existing native catalog, history, concurrent config, CLI
metadata, Guardian and naming tests also passed. These synthetic checks establish
candidate scope, not live model compliance or preview success. A fresh three-model
manual UI calibration is prepared; its result is pending and has no enforced
request counter.

## Result so far

- Ten synthetic command-boundary tests pass. They exercise replay, stopping an
  owned child process on five unchanged actions, the deadline, independent
  scores, scoped catalog changes and both native instruction request formats.
- Six live CLI calibrations used 14 requests in total. Every attempt is retained
  in `docs/evaluation/evidence/capability-prototype-2026-10-09/`; none counts as a
  cell in the planned 24-run baseline.
- The final GLM pair proves that the catalog variant reaches the request sent to
  the launcher adapter. Baseline has the inline-code instruction; the variant
  has the native file-citation instruction and lacks that inline-code instruction.
  Both expose 29 tools. Both completed in two requests with unchanged fixtures
  and protected configuration. The audit records hashes and fixed markers only.
- Both exploratory GLM variant attempts returned backticked relative paths,
  as did the baselines. There is no demonstrated delivery improvement. CLI
  output does not establish whether Desktop would render an artifact preview.
- The first request auditor checked only top-level `instructions`, but the real
  CLI sends these instructions in developer messages. Its empty hashes do not
  show missing instructions. A failing synthetic test reproduced this gap;
  the corrected audit includes system/developer text and excludes user text.
- The recovery calibration exposed two fixture/scoring limitations: this Mac
  has `python3`, not `python`; and a shell wrapper can exit zero after the probe
  exits two. The earlier result remains inconclusive. Corpus v2 uses `python3`;
  validating the probe's own outcome remains a reusable-evaluator requirement.

## Desktop UI calibration result

The maintainer completed the three-model file-handoff checklist. Kimi produced
clickable links and both files opened in the side panel. DeepSeek returned only
backticked absolute paths; GLM returned only backticked relative paths. Both missed
clickable document delivery. All six fixture copies still match their original
checksums. This is one manual observation per model, not a reliability claim or
part of the bounded 24-run baseline.

Read-only inspection of those synthetic sessions confirms the same 20,751-character
base instructions in all three, including the inline-code file-path guidance.
Kimi's successful output used ordinary Markdown links with absolute local paths,
not `:codex-file-citation` directives. This is a concrete renderer-supported format
for the next delivery experiment; it does not imply a missing artifact tool.
The evidence files `desktop-handoff-ui-calibration.json` and
`desktop-handoff-recorded-inputs.json` keep user-observed previews, file integrity,
recorded instruction hashes and response syntax distinct.

The [Ollama research](../../docs/research/ollama-model-prompts-2026-10-09.md)
finds native Desktop prompt reuse and enabled skill/plugin/app instruction flags,
plus protocol adaptations. Exact hosted-model prompt processing remains unknown.
Compare full effective Desktop inputs before changing flags; do not import
model-training templates or assume Ollama has a special artifact-delivery prompt.

The JSON filenames identify individual attempts. Earlier calibration `id` fields
are not all unique; do not merge results by those IDs. The reusable evaluator
must allocate unique run IDs and separate cell IDs from attempts.

## Run locally

From the repository root:

```sh
python3 -m unittest discover -s scripts/prototype_capabilities -p 'test_*.py'
python3 scripts/prototype_capabilities/pilot.py plan
python3 scripts/prototype_capabilities/pilot.py replay /path/to/private-trace.jsonl
```

Tests use a local synthetic HTTP server and disposable subprocesses. `plan` and
`replay` make no inference requests. Replay prints only classifications/counts;
it never executes recorded commands. Its XML-window equivalence rule is narrowly
specific to the observed loop, not a general semantic loop detector.

Optional paid, explicitly live calibration (an existing launcher login is needed):

```sh
python3 scripts/prototype_capabilities/small_run.py --live \
  --case 05 --model zai-org/GLM-5.3 --variant baseline \
  --launcher "$(command -v tofa)" --codex "$(command -v codex)" \
  --output /tmp/new-capability-result.json
```

Use a new output filename for every attempt. `file-citations-v1` changes only
the selected main model's file-reference section in a temporary catalog.
It targets Desktop syntax through the CLI transport for calibration; it is not
a CLI product recommendation. The original catalog, Guardian and global
instructions stay unchanged. The runner preserves the persistent client
environment and uses a fresh workspace. Raw responses and commands remain in
private temporary directories outside Git; inspect them locally when scoring.

Each small live case has a 180-second deadline, 12-request cap, 4096 output-token
cap per request and five-action repetition stop. The supervisor owns only its
new subprocess group. Existing proxy tests separately cover request caps,
unexpected role rejection and streaming deadlines.

## Remaining boundaries

The reused observer is text/coding-only and has a maximum 360-second request
deadline. It rejects image and auxiliary contracts. Do not run the 15-minute
deck cases through it or classify its rejections as model failures. Native
Guardian enforcement remains enabled; a Guardian interaction unsupported by
this observer is an infrastructure limitation.

Desktop preview checks remain operator-owned. The completed checklist is
manual UI calibration with a three-minute stop rule, not the bounded baseline:
the Desktop request/time supervision seam has not been implemented. Do not
infer preview success from link syntax or replace the refused UI control path.

Next specification: support actual Desktop and deck request contracts; capture
versions, effective instruction roles and tools; preserve independent criteria
and unique attempts; prove bounds and cancellation before the 24-run campaign.
Any proposed guidance adoption still needs three fresh runs per variant,
affected coding/approval/naming checks and a held-out task. No model promotion
or production instruction change follows from this prototype.
