# Desktop admission slices #145 and #146

Implemented on the integration branch from `ba98f7a`. These are offline
compatibility/evidence changes; ordinary native-account route enablement remains
in #143. No native Desktop launch or new manual observation was made.

- #145 (`b8f6e41`) adds the public non-launch local compatibility diagnostic.
- #146 adds the [behaviour assessment](desktop-behaviour-assessment.md), retaining
  strict original receipt validation while allowing explicitly justified reuse
  across compatible candidate identities. Required coverage cannot be reduced by
  omitting entries. Automated mechanics and native UI observations stay distinct.

Both slices have public-boundary red/green regressions and separate Standards and
Spec reviews. Review findings were reproduced and corrected: unsafe profile/lease
and malformed policy acceptance, incomplete unknown-change accounting, and parent
passes masking filtered-out security/review subtests. Production protection,
service/credential separation and original receipts remain intact.

## Separate retained-evidence assessment

The November 10 audit checked 99 saved receipt bindings across these four runs.
Every available bound receipt matched; all four original candidate binaries still
matched their recorded hashes. Prior policy reassessments still link to their
original reviews. This is a new assessment, not an edit to an old verdict.

| Retained result | Applicability and limits |
| --- | --- |
| `3afa725` clean exit | Accepted scoped account/plugin/Code Review visibility, smoke/title and normal exit remain usable. The installed application executable, bundle metadata, archive, native transport and engine match that run. New source changes add diagnostics/validation, not UI or history rewriting. Current installed-engine compatibility and leak tests support scoped reuse; no UI repetition is justified solely by these source changes. |
| `efd74f8` repeat launch/history | Accepted historical readability remains retained. Current installed-engine history continuation and lifecycle tests pass across the newer engine. Reuse the unaffected functional observation with those checks and the recorded impact assessment; do not claim it was observed again on the current app. |
| `9928136` launcher crash | Accepted crash result remains retained. Current real launcher/engine fault tests establish recovery mechanics, including client crash, interruption and reinstall paths. They do not manufacture native recovery UI observations. |
| Ordinary recovery | Functional recovery remains accepted. Security-sensitive settings/skill differences remain unresolved; absent historical file detail stays unknown. This audit neither attributes those changes nor waives them as cache refreshes. |

Raw evidence, original reviews, hash inventories and execution logs remain in the
established durable private qualification archive. Ad-hoc historical reviews are
not silently imported as stronger machine qualification cases. When assembling
release coverage, link sufficient original receipts and explicit applicability
facts; missing machine facts must remain missing.

## Remaining release work

- #141: finish the semantic preservation decision for ordinary recovery and bind
  the accepted lifecycle/account/history scopes into release coverage. Do not
  restart unrelated cases because catalog, model or plugin-cache identities differ.
- #142: adequate actual service-label/switching, origin-bound review/approval,
  naming and history-continuation observations. Existing tool-free smoke cannot
  establish Guardian execution or switching.
- #143: actual supplied-runtime loader/artifact/native-preview coverage, final
  coverage review and normal-route enablement. No partial feature rollout.

The current-engine automated checks support reuse and fault mechanics; they do
not replace the remaining native UI requirements. Qualification is still
incomplete. The production guard and integration branch remain in place.

## Validation evidence

#145 passed the full Go race suite (core package 446.478 seconds), vet, public
compatibility regressions and installed-engine tool-turn/leak controls. The
installed-engine compatibility test passed without changing its synthetic
credentials/configuration/skills. Available CLI/Desktop engines currently have
identical bundled skill contents; the distinct-cache mixed-engine comparison
therefore skipped and is not claimed as executed coverage. Its regression remains
intact.

#146's public assessment regressions cover original identity/integrity, empty and
partial scope, full synthetic coverage, supported reuse, narrow invalidation,
collector-only changes, unknown identity changes, failed/skipped/filtered checks,
and the distinction between artifacts and native previews. Actual installed-engine
history continuation and every lifecycle fault subcase passed. These executions
are recorded separately from the default suite, which skips opt-in engine tests.
