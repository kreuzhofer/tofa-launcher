# Throwaway capability evaluation prototype

This branch investigates whether a bounded evaluator can distinguish artifact
creation, delivery, workflow compliance and visible Desktop behavior, and whether
a scoped file-reference instruction change reaches a real client request.
It is not the reusable evaluator or a production prompt change.

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

Desktop preview checks remain operator-owned. The accompanying checklist is
manual UI calibration with a three-minute stop rule, not the bounded baseline:
the Desktop request/time supervision seam has not been implemented. Do not
infer preview success from link syntax or replace the refused UI control path.

Next specification: support actual Desktop and deck request contracts; capture
versions, effective instruction roles and tools; preserve independent criteria
and unique attempts; prove bounds and cancellation before the 24-run campaign.
Any proposed guidance adoption still needs three fresh runs per variant,
affected coding/approval/naming checks and a held-out task. No model promotion
or production instruction change follows from this prototype.
