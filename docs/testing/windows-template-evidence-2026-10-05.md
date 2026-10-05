# Windows template implementation evidence — 2026-10-05

This records implementation checks and completed native qualification for #79.
The maintainer explicitly designated the existing `tofa77 Windows ARM64 bridge
prototype` VM, UUID `EF96CF12-D901-455F-81FF-4C5001E15F80`, as the test template,
created the `tofa-test` account, and signed in. The account belongs to
Administrators, but the actual probe verified its effective Limited token.
No everyday VM lifecycle operations were performed.

## Measured prerequisites

The public `template prepare` / `template status` CLI discovered Windows 11 ARM64
10.0.26200, native Python 3.13.15, Codex package 26.930.6422.0, and engine 0.160.0.
The user-local engine SHA-256 matched the selected package's bundled engine.
Preparation registered the existing package for `tofa-test`; the maintainer
opened Codex once to initialize its user-local engine and then fully quit it.
No credentials were supplied to the runner, copied, or exported.

The real Limited task proved all of the following in
[attempt 10](evidence/windows-template-2026-10-05/attempt-10.json):

- The task ran as the selected SID in session 2 without elevation.
- The limited user could neither write nor manage ACLs on protected harness inputs.
- A fresh workspace created by that user was owned by that user.
- The user could manage the workspace ACL and write an ordinary marker.
- The effective engine configuration retained elevated native sandbox mode and
  workspace-write restrictions; Full access was disabled.
- Test markers were removed and the completed task was unregistered.

These prerequisite assertions **do not establish native readiness**. The sandboxed
command did not complete. The engine was terminated after its shutdown deadline,
and the CLI correctly returned failure. An additional local diagnostic showed
that native execution was waiting on a missing/incompatible sandbox setup marker.

## Initial bootstrap failure

The public preparation CLI sent the documented `windowsSandbox/setupStart`
request with `mode: elevated`. The engine accepted it, but no completion
notification arrived within the 60-second setup window. The latest captured
[attempt 11](evidence/windows-template-2026-10-05/attempt-11.json) records
`setup_status: awaiting_completion`. The template window showed no pending UAC
prompt when inspected after the attempt. Native helper executables were present.
The cause of the stalled setup is not established. It is not evidence that the
newer engine version is incompatible.

The initial request to complete app-driven setup was superseded by the diagnosis
and native checks below. Desktop trust, Guardian behavior, and live authentication
remain unverified; they are outside this native slice.

## Consent and completed native acceptance

A diagnostic copy changed only the scheduled task's window style from Hidden to
Normal. The VM then displayed Windows consent for `codex-windows-sandbox-setup.exe`,
verified publisher OpenAI OpCo, LLC. The maintainer approved it without completing
desktop sign-in. This observation supports making explicit initialization visible;
it does not establish that every previous hidden launch suppressed consent.
The [visible setup attempt](evidence/windows-template-2026-10-05/attempt-12-visible-setup.json)
reached its 60-second deadline around approval, so its failure is preserved.
Subsequent probes establish that native setup completed afterward.

The public CLI's [negative fixture](evidence/windows-template-2026-10-05/attempt-13-negative.json)
ran as the Limited test user. Ordinary writes succeeded, while owner and WRITE_DAC
checks were false and the actual sandboxed workspace command failed. The engine
returned a setup-refresh error without the word `ACL`, so the CLI conservatively
reported `native_workspace_execution_failed`. A
[diagnostic repeat](evidence/windows-template-2026-10-05/attempt-15-negative-diagnostic.json)
confirmed the same failure. Its
[allowlisted signals](evidence/windows-template-2026-10-05/negative-diagnostic-signals.json)
record `helper_unknown_error` and `setup refresh had errors`; the
[correlated sandbox-log check](evidence/windows-template-2026-10-05/negative-acl-log-signal.json)
confirms `write ACE grant failed` for that run's `acl-fixture` with
`open ACL target for update`. No unrelated log lines or raw engine output were
exported. No ownership or permission repair was applied to the fixture.

The public CLI's [user-owned fixture](evidence/windows-template-2026-10-05/attempt-14-positive.json)
returned `native_ready` with the same installed package and engine. Native
workspace write/read succeeded; the outside write returned exit code 1 and
`GetContentWriterUnauthorizedAccessError`, and the outside marker was absent.
Full access stayed disabled. Both runs removed their markers, exited their owned
engine, and unregistered their completed task. These results satisfy the actual
ARM64 native ownership and permission-boundary acceptance cases.
A [final `template prepare` run](evidence/windows-template-2026-10-05/attempt-16-final-prepare.json)
with the follow-up code also returned `native_ready` without further consent.

The final runner makes only explicit initialization tasks visible, announces the
60-second consent window before launching, and directs late approval to a fresh
status check. A public CLI regression first failed on the hidden task and then
passed with this change. The [follow-up validation record](evidence/windows-template-2026-10-05/followup-validation.json)
records the final checks; the original validation record remains historical.

## Preserved attempts and implementation corrections

The original eleven public CLI attempts and follow-up native evidence are retained in
[`evidence/windows-template-2026-10-05`](evidence/windows-template-2026-10-05).
Earlier reports reflect earlier implementation revisions and are not silently
rewritten after fixes. They include initial malformed/missing transport results,
package registration and first-launch prerequisites, busy-client refusals, and
native setup timeouts. Their bootstrap-required verdict does not prove a visible
consent prompt existed. The final implementation reports a missing setup API
completion as `native_setup_incomplete` rather than asserting consent was declined.

Native integration established that UTM guest exec can return before a result
exists and without stdout. The runner now awaits fresh correlated result files,
retrying only the observed missing-file/path condition. PowerShell in the guest
agent reports AMD64 even on this ARM64 OS; discovery uses native processor
architecture and separately verifies the native Python process.

Standards review found unsafe same-volume moves from Public staging and malformed
prerequisite/failure fields that could leave empty reports. Staging now starts in
a SYSTEM-protected directory before upload, and the real limited user verified
the harness cannot be changed. External-boundary tests reproduce malformed
responses and verify durable failures. The reviewer confirmed all findings fixed.
The separate spec review found no additional implementation findings and kept
actual ARM64 acceptance as an outstanding gate.

## Checks

The full available Python script checks, including build/install/lifecycle,
passed; platform-specific and opt-in native suites retain their declared skips.
The new public CLI integration tests passed. Python typechecking and `go vet ./...`
passed. See the [validation record](evidence/windows-template-2026-10-05/validation.json).

`go test -race ./...` was run in full. The scripts package passed, but existing
macOS desktop tests failed because the host Codex desktop was already running.
The tests refused to interfere with it. No Go product code was changed for #79,
and the host desktop was not stopped to make those tests pass.

The existing ownership investigation and original diagnostic evidence were used
as implementation inputs and left unchanged. The new successful measurements
belong to the fresh `tofa-test` account. They do not claim the parent's fresh-clone
or desktop/Guardian gates.
