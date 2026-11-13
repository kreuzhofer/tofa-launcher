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
