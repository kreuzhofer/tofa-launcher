# Review of presentation runtime integration

Reviewed against `2c8df027232a7d5b1a6da2f6c46c9ad4ccee32c9` (#122), through
`c4524f0`, with a focused follow-up at `7366ad7`, on
`feat/126-127-presentation-runtime`. Two independent reviewers evaluated Standards
and Spec. Follow-up reviews checked the corrected findings and computer-use amendment.
The implementation remains on the integration branch; neither ticket is closed.

## Standards

No remaining implementation findings. The final review confirmed that native
metadata parsing validates the plist shape and required nonempty string fields,
and converts parsing failures to `ValueError`. The final calibration probe catches
that error and retains a blocked qualification result. Four boundary tests passed.

Earlier findings about failed smoke execution, malformed evidence records and
duplicated tool-catalog handling were corrected. Qualification requires a
successful command result and matching artifact hashes; object-only evidence
reads fail explicitly; provider/schema recognition uses a shared validator.

The computer-use follow-up found no concrete Standards defects. The default human
workflow remains intact, agent observations are separately attributed, and the
evidence distinguishes modification-time candidates from proven content changes.
Eight preview/evidence tests passed in the reviewer's check.

## Spec

No remaining concrete implementation defects were found in the follow-up review.
Qualification now revalidates protected policy/instruction files before forwarding,
rejects contradictory or unknown structured loader content, binds the selected
client path, and requires successful execution, finalization and actual delivery.
The CLI synthetic workflow passed through the installed client. The two separately
declared model calibrations remain negative and retain their original outcomes.

One acceptance gate remains: #127 requires the successful native Desktop loader
call, artifact workflow, native previews of both delivered files and two separately
declared model calibrations. The maintainer authorized computer use after initially
deferring the operator step. The tool refused access to the application; the
retained attempt observed no loader or previews and detected protected-state drift.
Asset checks and the prepared handoff cannot satisfy that native qualification gate.
The branch will remain unmerged and both tickets open until qualification is complete.

Standards: 0 remaining findings. Spec: 0 implementation defects; 1 deferred native
qualification gate. The outstanding Spec gate prevents completion.

The Spec follow-up at `7366ad7` found no new defects or misclaims. It confirmed that
the blocked native attempt does not claim a preview pass and that the fresh CLI
proof cannot qualify Desktop.

## Native ancestry follow-up — 3cc3487

Original review baseline: `2c8df02`; focused follow-up: `807601c...3cc3487`.
The maintainer confirmed launcher/app-server and actual Desktop startup test boundaries.

### Standards

No concrete Standards violation or baseline smell found. The engine retains the
original Desktop child PID through `exec`. Pipe transfers and closure are
consistent; relay startup failures kill and reap the child. Protocol errors check
parent ownership before signalling the engine. Existing cancellation and ownership
monitoring remain tied to the acknowledged engine PID. Fixture dispatch avoids
allocating a credential store whose deferred cleanup would be lost during `exec`.
ADR 0003's settings isolation remains intact without restoring shared snapshots.
The reviewer did not repeat the reported Go/native checks; its sandboxed temporary
file test could not start the loopback listener. The outside-sandbox run passed.

### Spec

No concrete new spec implementation defects found. The separate relay retains the
model-default filter and acknowledges the actual engine PID without weakening
routing, Guardian, naming, approval or ownership contracts. Temporary-file scoping
and fixture cleanup support removal of owned resources.

Qualification remains incomplete: #127 requires a successful native loader call,
a delivered deck and native previews. Startup readiness establishes none of
these. The two `CODEX_CLI_PATH` rewrites remain a preservation blocker under the
requirement to block on background drift without restoring shared snapshots.

Findings: Standards 0; Spec implementation defects 0; native qualification incomplete.

## Production synthetic observer follow-up — baseline c48eae4

Standards review found one concurrent audit persistence race in the new synthetic
observer. A parallel HTTP regression reproduced the failure. The final record
update and persistence now hold the observer lock; the regression and both other
synthetic boundary tests pass. Follow-up Standards review found zero remaining
findings. Spec review found zero new implementation defects.

The observer uses the existing authenticated evaluation boundary, preserves native
launch-control forwarding, rejects synthetic Guardian decisions and does not
change the live model evaluator. A fresh real CLI runtime/deck check passed with
the production launcher after the fix. Production lifecycle and installed-asset
preflight passed separately. Actual production native conversation/previews and
two declared model calibrations remain acceptance work; these reviews do not
claim that startup or synthetic inference satisfies those gates.
