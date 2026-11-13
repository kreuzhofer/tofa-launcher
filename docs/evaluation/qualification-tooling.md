# Durable qualification tooling

These tools prepare and inspect evidence; they do not authorize a new launch or
change release requirements. ADR 0007 and `desktop-release-readiness.md` remain
the authority for behaviour coverage. Historical rc18 guides and receipts remain
unchanged. Use the maintained scripts for new work, not a rewritten frozen kit.

## Prepare or restore a guide

Store a new private kit outside `/tmp`, normally below
`.qualification/134-manual/candidates/`. Freeze the reviewed launcher, collector
source and dependencies, model-services document, and maintained guide scripts in
that kit. Keep their paths relative to the kit. A reviewed `kit.json` declares:

```json
{
  "schema": "tofa-qualification-kit-v1",
  "source_revision": "FULL_40_CHARACTER_REVISION",
  "launcher": "tofa",
  "collector": "source/scripts/desktop_qualification.py",
  "model_services": "model-services.json",
  "app_bundle": "/Applications/ChatGPT.app",
  "runtime_root": "/absolute/discovered/supplied/runtime",
  "durable_root": "/absolute/private/kit",
  "run_root": "/tmp/tofa-presentation-validation",
  "case": "clean-exit",
  "model": "explicit/main",
  "guardian": "explicit/reviewer",
  "seconds": 600,
  "requests": 8,
  "output_tokens": 4096,
  "automatic_retries": 0,
  "retain_credentials": true,
  "prompt": "Reply exactly: tofa-clean-exit-ok. Do not use tools or create files.",
  "files": {"RELATIVE_FILE": "SHA256_OF_FROZEN_FILE"}
}
```

Replace placeholders with verified identities and inventory **every file** under
the frozen collector's scripts directory, plus the launcher, model-services and
guide files. Use relative paths with no symlinks. The JSON is a reviewed private
input; model selections are provenance, not identity-equality release gates.
Never include credential files. The supplied runtime path is discovered for this
kit; no installed version directory is compiled into the guide.

Commands use the public maintained entry point:

```sh
python3 scripts/qualification_kit.py check --kit "$KIT"
python3 scripts/qualification_kit.py restore --kit "$KIT"
python3 scripts/qualification_kit.py status --kit "$KIT"
```

`check` verifies pinned bytes and collector imports. `restore` creates a fresh
copy under `/tmp/tofa-presentation-validation/guides/`, verifies it again and
reports its path. It never extracts over an existing attempt or edits old receipts.
The original durable kit is still the archive destination. Missing `/tmp` files
are recoverable; durable evidence is never reconstructed from guesses.

The existing `desktop_qualification_operator.sh --kit "$KIT" --check` also checks
the actual application/runtime prerequisites. Its normal invocation remains the
explicit, interactive launch boundary. It reads the kit's selections and bounds
instead of hard-coded candidate revisions. The operator currently supports the
clean-exit case; other behaviours require their own reviewed case guidance.

`qualification_kit.py prepare --kit "$KIT"` is separately available for agents.
It delegates only to the collector's `prepare --defer-snapshot` action, allocates a
fresh workspace and saves private preparation diagnostics durably. It does not
snapshot, launch, infer or grant a pass. The operator performs that preparation
itself, so do not run both preparation paths for the same intended handoff.
`status --run PATH` identifies consumed attempts and directs review, never retry.
Explicit finish/cancel and the existing collector cleanup still govern a launched
attempt. Archive the finished collector's evidence, not an in-progress copy.

A collector import failure, preparation failure, launch failure and provider
failure are separate outcomes. Keep the original receipt for each; fixing a guide
does not change an earlier attempt's result.

## Reconcile behaviour evidence

`scripts/qualification_reconcile.py --declaration PATH --output NEW_JSON` invokes
only the pinned launcher's `desktop-qualification assess` public interface. It
never runs an engine or Desktop, changes admission or grants a release verdict.
Use a declaration with these fields:

- `schema`: `tofa-release-reconciliation-v1`.
- `candidate`: descriptive release identity; `target`: the assessor plan's exact
  target object, including source revision and component hashes.
- `assessor` and `assessment`: `{ "path": "...", "sha256": "..." }` references to
  the reviewed executable and existing assessor plan. Paths may be absolute or
  relative to the declaration. The assessor verifies its nested evidence bindings.
- `provenance`: diagnostic catalog, selected model and plugin-cache information.
  This object supplies no acceptance conditions.
- Optional `retained_reviews`: entries with a hash-bound `review`, `evidence_root`,
  `reviewer` and `reason`. The tool verifies every `original_receipts_sha256` binding
  in each review and retains its original status. These records accompany the
  matrix; they do not silently fill a missing assessor row. Reuse decisions belong
  in the existing assessor plan, with its required attribution and impact analysis.

Output preserves the authoritative assessor result and maps its rows to accepted,
reused, targeted-evidence-needed or investigate-failed-contract. A failed current
security check cannot be repaired by appending an older successful review. Output
is private and exclusive-created; retain failed reconciliation attempts separately.
Review its content before publishing a sanitized summary.

Before proposing any manual rerun, identify the specific affected behaviour, the
material change or missing observation, and why retained evidence plus automated
checks cannot establish it. Routine catalog/model/plugin-cache changes are not
sufficient. A Desktop update needs contract checks and impact review, then only
observations for affected or unproven behaviours. CLI platform scope and the final
combined release decision remain separate reviewed records; this tool does not
reinterpret a historical purge omission or broaden experimental client support.

## CI failure diagnostics

The native Windows lifecycle check uses `lifecycle_process.py` for its bounded
probe/uninstall processes. It preserves the ten-second deadline and existing
asynchronous-helper ownership/cleanup checks. Python is required for this CI
check (already present on Actions runners). Arguments cross the PowerShell
boundary through an owned JSON job file, not a shell command string.

Failures retain a `tofa-ci-process-failure-v1` receipt outside the scratch tree:
phase, executable digest, deadline/elapsed time, exit code, direct-process cleanup
and bounded stdout/stderr byte counts plus fixed diagnostic markers. Raw output,
arguments, paths and environment values are excluded. This does not prove that
an asynchronous helper finished; the lifecycle check separately waits for and
stops its owned helpers. Default diagnostics are `.ci-diagnostics/windows-lifecycle/`;
`-Diagnostics` can select a private destination for an explicitly authorized
synthetic run. CI uploads only those JSON receipts, on Windows failure, retaining
the workflow attempt identity. It never uploads the raw scratch tree.

A timeout is an observed outcome, not a root-cause diagnosis. Preserve the first
failed job's evidence. Check the complete workflow state before requesting one
specifically authorized failed-job rerun; an in-progress workflow cannot be
rerun. A passing rerun does not relabel the original failure or justify dropping
coverage, increasing deadlines or retrying paid inference.

## Campaign preflight and CI observation

`qualification_workflow.py preflight --campaign PRIVATE_JSON` checks the explicit
checkout, integration branch, full HEAD, clean tracked state, required tools,
process-only Git author identity and accepted receipt hashes. Untracked files are
reported by count and retained. It returns a Git argv prefix and a scoped next
action without executing it. The private index format and handoff procedure are
in [the agent workflow](../agents/qualification.md).

```sh
python3 scripts/qualification_workflow.py watch-ci \
  --repository OWNER/REPO --run-id RUN_ID --head FULL_SHA \
  --output NEW_DURABLE_DIRECTORY --seconds 600 --poll-seconds 10
```

The watcher makes read-only `gh api` calls for the pinned run and its jobs. It
stores observations exclusively, prints state changes and stops at completion or
its deadline. A failed workflow remains failed in the snapshots even when the
watcher itself completes successfully. Failed job IDs become eligible for a
separately authorized rerun only after workflow completion. The watcher never
reruns jobs, retries inference, publishes artifacts or modifies credentials.
