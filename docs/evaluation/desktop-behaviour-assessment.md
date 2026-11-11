# Assess Desktop integration evidence

`tofa desktop-qualification assess --assessment PATH` is an offline maintainer
operation. It reads evidence and writes its assessment as JSON to stdout. It does
not launch Desktop, contact a provider, execute an engine named by evidence,
modify receipts, grant runtime authorization or enable the production route.
The existing `snapshot`, `verify` and candidate admission contracts stay intact.

Keep the plan and linked private evidence under `/tmp/tofa-presentation-validation`
using the existing owner-only evidence rules. Keep durable copies outside `/tmp`.
References use the existing `{ "path": "relative/file", "sha256": "..." }`
format; each path is relative to the containing record. No absolute references,
parent traversal, symlinks or unchecked receipt replacement are accepted.

## Plan and result

A `tofa-desktop-assessment-plan-v1` plan contains:

- `target`: the candidate's recorded `desktopAdmissionIdentity` (the same identity
  structure as a qualification snapshot), including source and component hashes.
- `compatibility`: reference to #145's `tofa-desktop-compatibility-v1` result for
  that target. The required checks must have passed and executable identities
  must match. A historical result is point-in-time evidence, never authorization
  to skip fresh checks at a subsequent launch.
- `behaviours`: entries from the fixed matrix below. Omitted entries are missing;
  a caller cannot reduce required coverage by supplying a smaller list.

Each entry can contain a `case` reference to an existing
`tofa-native-account-case-v1` record and `checks` references to executed checks.
The assessor first runs the existing case validator against the record's **own
original identity**, including declaration/start/process/snapshot/request/artifact
bindings and attributed observations. It then assesses applicability to `target`.
A failed original record cannot be rescued by a reuse explanation.

Results use `established`, `reused`, `failed`, or `missing`, retain the original
case reference and separately identify an established historical result where
current coverage remains missing or failed. `coverage_complete` requires every
row. `release_qualified` remains false: review, release decisions and production
route enablement belong to #143, not this evaluator. Invalid plan/compatibility
bindings return a nonzero exit; valid assessments may contain failed or missing
rows, so automation must inspect `coverage_complete` and individual statuses.

| Required behaviour | Native evidence | Additional executed checks / automated alternative |
| --- | --- | --- |
| Account and capabilities | clean-exit | Actual account/plugin/Code Review observations |
| Clean exit | clean-exit | Existing lifecycle receipt checks |
| Repeat launch and readable history | repeat-launch | Actual history observation |
| Ordinary recovery | ordinary-launch | Actual native use/history/relaunch guidance; preservation |
| Launcher crash | launcher-crash | Real-engine history fault plus public launcher expiry/recovery tests may establish mechanics |
| Native crash | native-crash | Real-engine history client-crash test may establish mechanics |
| Bridge update | bridge-update | Real-engine interrupted-replacement and public lifecycle tests may establish mechanics |
| Uninstall/reinstall | uninstall-reinstall | Real-engine history and uninstall-detachment tests may establish mechanics |
| Service switching | service-switching | Installed-engine cross-launch continuation |
| History continuation | history-resume | Installed-engine cross-launch continuation |
| Review routing | review-routing | Origin binding, unknown-origin rejection, actual approval and native-history interruption |
| Naming | launch-naming | Structured tool-free naming, isolated failure and independent main streaming |
| Runtime and previews | runtime-preview | Existing loader/version/artifact bindings and both actual native previews |
| Routing, tools and credentials | — | Actual bundled-engine tool turn/leak controls and authorization separation |

Automated fault rows establish mechanics only. They do not supply the separate
mandatory native account, readable-history or ordinary-recovery observations.
A tool-free smoke turn cannot establish reviews; owned artifact files cannot
establish native previews. The precise check names are versioned with the
assessment implementation in `desktop_assessment_darwin.go`.

## Executed checks

A `tofa-desktop-executed-checks-v1` receipt contains `identity`, `started_utc`,
`finished_utc`, integer `exit_code`, the actual `command` argument list and a
`log` reference. Use `go test -json` output from the public-launch/real-engine
regressions. Retain the original log and exit status even on failure. Installed
engine tests must be opted into explicitly with disposable state and owned
upstreams; the default suite skips them and cannot establish their coverage.

The assessor requires successful target-bound execution, a completed package,
required test and contract-bearing subtest run/pass events within the execution
window and no failed events. A passing parent after a filtered subtest run does
not establish the omitted cases.
A skipped required test or subtest is not a pass. A test name, a zero exit flag
without matching events, an empty test scope or a modified log is insufficient.
Receipts are auditable same-user maintainer evidence, not cryptographic proof
that the author is honest; preserve command/environment provenance with the
private check archive. The evaluator never executes a command from a receipt.

## Reuse and updates

An entry with a changed relevant identity needs `reuse`:

- `reviewer`: the maintainer attributing the assessment;
- `reason`: why the existing UI observation remains sufficient;
- `changes`: an explanation for every changed category reported by the existing
  identity comparison (`source`, `engine`, `runtime`, `skills`, `harness`, etc.);
- `impact`: `unaffected` to propose reuse, or `affected` to retain the old result
  while requiring targeted new evidence.

Attach actually executed target compatibility checks and behaviour-specific
regressions. There is no automatic approval based solely on a version number or
hash. Catalog/model/plugin-cache identity churn remains diagnostic. Other changes
require explicit impact reasoning for the individual behaviour. Collector-only
changes can reuse adequate observations after checks; gaps revealed by the new
collector stay gaps. Neither a failed essential contract nor unknown historical
preservation can be waived with a blanket generated-file exclusion.

Legacy ad-hoc private review summaries are retained as scoped historical findings;
they are not silently converted into machine qualification cases. Preserve their
original verdicts and receipts when preparing linked case facts. #141 owns any
remaining preservation classification. This command does not reconstruct missing
old per-file data or attribute a native update to an actor without evidence.
