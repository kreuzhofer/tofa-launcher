# Independent code review for #123

The fixed point is the maintainer-approved
`7a04fc2640cb58c6e7ca19d9e6d75b19972f94b0`. Reviewers inspected
`git diff 7a04fc2...HEAD` for prerequisite context and the staged
`git diff --cached a33358c` for the isolated #123 implementation. The source
worktree starts at qualified #118 revision `a33358c`; unrelated upstream changes
are not attributed to this task. Both axes were reviewed in parallel and the
correction/calibration records received focused follow-up reviews.

## Standards

Initial review: one P2 finding. Generated artifact checks omitted a symlinked
workspace root, allowing outside-run files to be hashed as present. This breached
AGENTS.md's Security-by-Default and Fail Fast requirements.

The shared check now includes the workspace itself and every descendant component
before frozen-input or generated-output hashing. A new evaluator-command test
first reproduced incorrectly passing input integrity, then verified failed input
integrity and unsafe outputs with no hashes. The reviewer independently repeated
the reproduction and confirmed both outputs were rejected.

Final Standards review: **0 remaining findings**. No other documented-rule
violations, ADR conflicts or actionable smell judgments were found. The production
adapter remains unchanged and the native approval failures stay explicit.

## Spec

Initial review: **0 actionable implementation defects**, with the required retained
real-client calibration pending in that snapshot.

Final Spec review: **0 new findings**. The installed CLI calibration satisfies the
retained real-client requirement using synthetic loopback responses and credentials.
Checks confirmed CLI 0.162.1, final harness hashes, method identity, completed main
requests with 4096-token caps, matching fixture hashes, protected settings
preservation and no environment drift. The recovery rule passes independently of
its still-pending semantic explanation; UI observations remain unobserved.

The separately versioned incident workflow, redacted rejection capture, reference
scoring and explicit regression classifications match the issue. The resume test's
initial Guardian turn fails before its second launch; this does not establish
successful resume approval. No production guidance, weakened permissions, hidden
retry, model substitution or promotion change was found.

Manual Desktop preview/title calibration remains pending. Native approval/resume
behavior remains unqualified, and the #119 campaign, comparison, held-out model
execution and adoption decision remain separate.

Final findings: Standards 0; Spec 0. Initial worst Standards finding was the
resolved workspace-symlink boundary; Spec had no implementation defect.

## Operator calibration follow-up

The preceding reviews describe the implementation snapshot committed as
`e01b7e28b640b75fc536f1762501f947483c4eac`. Two parallel reviewers then inspected
the evidence-only Desktop delta against that revision, retaining the same
maintainer-approved fixed point. No code changed in this follow-up.

### Standards

**0 findings.** The exact export is preserved. Request outcomes and usage,
operator observations, raw-text hash and reference syntax, unchanged harness and
fixture hashes, and published privacy checks agree with retained private evidence.
The documentation distinguishes completed negative calibration from successful
file handoff, records title visibility separately, and leaves native approval,
held-out execution, campaign and adoption gates incomplete. No documented-rule
violations, ADR conflicts or actionable smell judgments were found.

### Spec

**0 new findings.** The retained current-Desktop run satisfies the required
real-client calibration without requiring a passing model handoff. Exact paths in
inline code without Markdown destinations correctly receive
`failed / terminal_paths`. Preview failure and visible automatic title are
supported by separate operator observations; no specific preview-failure
mechanism is inferred. Settings and fixtures remained preserved, execution was
bounded, and naming routed independently.

The explicit approval/resume contract classifications remain valid; this run had
no Guardian requests and adds no approval qualification. The held-out contract is
implemented and tested, but this calibration is not held-out evidence, a
replacement matrix cell or a repeated-comparison attempt. Historical exports and
scores remain unchanged. The reviewers found no remaining method requirement and
confirmed #123 can close while #119's campaign and adoption gates and #122's
runtime work remain incomplete.

Both reviews were read-only and performed no inference, GUI or Windows actions.
Final follow-up findings: Standards 0; Spec 0.
