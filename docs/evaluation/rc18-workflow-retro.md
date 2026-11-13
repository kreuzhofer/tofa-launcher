# rc18 qualification and PR #149 workflow improvements

The five follow-ups were implemented in order on the existing integration branch.
They improve future tooling; they do not reopen the accepted
[rc18 readiness decision](../releases/v0.1.0-rc.18-readiness.md), broaden client
support, rebuild the candidate or introduce a stable-promotion gate.

| Priority | Observed problem | Implemented safeguard |
| --- | --- | --- |
| 1 | Mac lifecycle guidance still ended in purge | Retain installation/config/login by default, reuse an existing complete login, report purge as unrun, require explicit purge selection; preserve state on failure |
| 2 | Candidate-specific guidance and missing temporary files required reconstruction | Verified kit declaration, dependency/permission checks, fresh restore/prepare, durable preparation and invocation logs, consumed-attempt status without retry |
| 3 | Combined reconciliation used candidate-specific private scripts | Read-only command around the existing behaviour assessor, bound legacy-review receipt verification, explicit reuse/missing/failure dispositions; diagnostic identities do not add gates |
| 4 | Windows timeout lost its scratch diagnostics | Unchanged ten-second child deadline, allowlisted failure receipt retained before cleanup, failure-only CI upload including the hidden diagnostic directory |
| 5 | Handoffs and CI observation required repeated agent decisions | Explicit checkout/branch/revision/author/tool preflight, private campaign-index contract, scoped authority guidance, bounded read-only CI watcher |

Usage and migration are documented in [qualification tooling](qualification-tooling.md)
and [agent handoffs](../agents/qualification.md). Frozen historical guides and
receipts remain unchanged. A temporary guide restored from a durable kit keeps
its invocation diagnostics in the original durable root, including failures before
a run directory is assigned.

## Review and validation

Independent Standards and Spec reviews found missing lazy-import checks, temporary
invocation logs, missing timeout diagnostics and stale banner identities. Standards
review additionally caught the artifact uploader's hidden-file default. All were
corrected and re-reviewed with no remaining material findings. Executable
permission and failed self-removal also have regressions: binary identity is
captured before the child can delete itself.

The affected Python suites pass 119 tests across Mac lifecycle, live-harness
fixtures, Desktop collector/guide, kit/reconciliation/workflow tools, process
diagnostics and release automation. All use owned fixtures; they do not establish
new native qualification. Shell syntax and the existing Go assessment/workflow
checks pass. `go test -race ./...` and `go vet ./...` pass; the final workflow
regressions also pass with the race detector. Detailed logs and the original
fixture failure are retained in the durable local validation receipt.

The PowerShell-to-Python integration is wired into the existing native Windows CI
lifecycle. It has not been executed natively on this Mac. The process runner's
argument, timeout, exit, cleanup and redaction behaviour is tested locally; native
Windows CI remains the validation boundary for the PowerShell call site. This is
a tooling validation limit, not a reason to repeat accepted rc18 live checks.

No Desktop or VM was launched. No new qualification campaign, paid inference,
ordinary credential/configuration change, release publication or promotion was performed.
Product code and installer/uninstaller bytes are unchanged from the reviewed
baseline. Local test failures and their corrected follow-ups are retained
separately; historical acceptance receipts were not rewritten.
