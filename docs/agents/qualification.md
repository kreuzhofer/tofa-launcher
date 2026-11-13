# Qualification and release workflow

Read this when preparing/restoring a guide, resuming a campaign, reconciling
qualification evidence, or monitoring release CI. The maintained command contract
is in [qualification tooling](../evaluation/qualification-tooling.md); release
behaviours and reuse policy remain in [ADR 0007](../adr/0007-qualify-desktop-behaviour-across-compatible-updates.md)
and the [acceptance matrix](../evaluation/desktop-release-readiness.md).

## Resume from evidence

1. Read the active private campaign index and the current conversation's authority.
   Locate the exact integration checkout, candidate, original receipts, accepted
   behaviours, remaining gaps and next action. A summary is not a replacement for
   its referenced evidence. Complete when the next action has a recorded basis.
2. At a clean checkpoint run `qualification_workflow.py preflight --campaign PATH`.
   It verifies branch/revision, tracked state, tools, author availability and bound
   evidence. Use the returned Git argv prefix or explicit `git -C` thereafter.
   Treat a failed prerequisite as a stop for dependent commands; inspect each exit
   status. Preserve unrelated edits/untracked files. Completion means a successful
   preflight against the intended checkout, not an incidental root checkout.
3. Use the read-only assessor/reconciliation before proposing new qualification.
   For a manual observation record the affected behaviour, material change or
   missing observation, and why existing evidence cannot cover it. Catalog/model/
   plugin-cache churn is diagnostic. Completion means a justified targeted gap or
   explicit reuse; an update alone does not restart the campaign.
4. Continue authorized preparation, offline tests, review, commits and bounded CI
   observation without repeated permission questions. Preserve active login and
   configuration. Human input is needed for local login/OS consent, an unobserved
   UI outcome, a new destructive action or authority not already granted. A prior
   bounded attempt/retry does not authorize unlimited repeats or substitutions.
5. Retain the new result and write a new campaign-index revision at each handoff.
   Preserve original receipts and the prior index. Record exactly what completed,
   what is still unknown and the next authorized action; completion is checkable
   from referenced logs and hashes. Local completion never implies publication,
   a new qualification pass or stable promotion.

## Private campaign index

Keep revisioned `campaign-NNN.json` files outside `/tmp`, normally under
`.qualification/134-manual/`. Use schema `tofa-qualification-campaign-v1` with:

- `repository` (absolute checkout), `branch`, `head` (full SHA), `candidate`.
- Optional `author: {name, email}`: already established author identity applied
  only to Git's process argv. Without it preflight checks existing Git identity.
- `tools`: absolute executable paths required for the next action.
- `accepted_evidence`: `{path, sha256}` references, relative to this index or
  absolute. Include the reviewed behaviour matrix and original receipt bindings.
- `next_action`, `authorized_actions`: explicit scoped authority from the current
  conversation, with an additional prose authority reference when useful.
- `retain_credentials: true`, `automatic_retries: 0`, `human_step_seconds: 600`.
- Current attempt path, limitations and unresolved observations as needed. Store
  receipt references, never credential values. Keep active credentials in their
  normal installed stores.

`may_continue` from preflight applies only to listed offline actions; it does not
execute them or grant launch/publication authority. Keep a mutable convenience
pointer to the current index if needed, while retaining every index revision.
Restore missing temporary guidance from a verified durable kit. Allocate a fresh
attempt only when authorized; consumed attempts stay consumed.

For CI, use the bounded `watch-ci` command and preserve the first failure. It
reports state changes and retains snapshots. Diagnose an actual failing phase
before requesting an authorized failed-job rerun after the workflow completes.
A changed candidate needs its own CI; an unchanged passing rerun does not erase
the original outcome. CI timings and tool failures are not evidence of model or
provider capability. None of these workflow improvements adds an rc18 release gate.
