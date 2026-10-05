# Windows template implementation evidence — 2026-10-05

This records implementation checks for #79, not completed native qualification.
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

## Bootstrap still required

The public preparation CLI sent the documented `windowsSandbox/setupStart`
request with `mode: elevated`. The engine accepted it, but no completion
notification arrived within the 60-second setup window. The latest captured
[attempt 11](evidence/windows-template-2026-10-05/attempt-11.json) records
`setup_status: awaiting_completion`. The template window showed no pending UAC
prompt when inspected after the attempt. Native helper executables were present.
The cause of the stalled setup is not established. It is not evidence that the
newer engine version is incompatible.

The maintainer was asked to complete the app's normal native sandbox bootstrap,
using explicitly chosen sign-in only if the app requires it to reach setup, and
then quit Codex. No response completing that step has been recorded yet.
Desktop trust, Guardian behavior, and live authentication remain unverified.

To finish #79's native acceptance after bootstrap, run the public CLI first with
`--workspace-fixture acl-unmanageable` and verify the native ACL failure despite
ordinary write access. Then run the default user-owned fixture and require both
native workspace write/read and genuine outside-write denial. Preserve both
reports. Neither native acceptance case has passed in this fresh account yet.

## Preserved attempts and implementation corrections

All eleven public CLI attempts are retained in
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
as implementation inputs and left unchanged. This new implementation has not
reclassified their prior native success as a success for the fresh `tofa-test`
account, and does not claim the parent's fresh-clone or desktop/Guardian gates.
