# Windows test-template preparation

`scripts/windows_test_runner.py` is the Mac-side operator CLI for the first
slice of [#78](https://github.com/kreuzhofer/tofa-launcher/issues/78), implemented
for [#79](https://github.com/kreuzhofer/tofa-launcher/issues/79). It prepares and
measures a designated Windows 11 ARM64 UTM template. Fresh-clone native smoke,
retention, status, and cleanup are documented in [windows-runs.md](windows-runs.md).
Desktop/Guardian suites remain separate work.

## Select the template explicitly

Use `utmctl list` to find the dedicated template's exact UUID. Supply that UUID
and `--dedicated-template` on every invocation. The flag explicitly designates
that VM for preparation; never point it at an everyday VM. Display names,
missing/duplicate UUIDs, stopped VMs, unsupported guests, and missing test-user
sessions fail before workspace provisioning. The runner does not start, stop,
clone, or delete any VM. Start the dedicated template yourself for preparation.

```sh
python3 scripts/windows_test_runner.py template prepare \
  --template YOUR-DEDICATED-TEMPLATE-UUID --dedicated-template \
  --test-user tofa-test --test-auth none \
  --output /tmp/template-prepare-1.json
```

The account may be specified as a local name or `MACHINE\name`. It must resolve
to an enabled local user with exactly one interactive desktop session. Guest
transport runs as SYSTEM; provisioning and native commands run in an
Interactive/Limited scheduled task for the verified user SID and session.
The probe checks the effective token and rejects elevation. A filtered
administrator account can therefore pass; an elevated process cannot.

## One-time bootstrap

1. Install Windows 11 ARM64 and UTM's working guest-agent/file transport in the
   dedicated template. Install a machine-registered native ARM64 Python 3.11+
   runtime and the native ARM64 Codex package. Ambiguous runtime/package
   installations must be resolved explicitly; the runner does not guess.
2. Create the dedicated local test account and sign in. Choose its credentials
   in Windows; the runner never sets passwords or changes account memberships.
3. Run `template prepare`. If the installed Codex package has no registration
   for this account, preparation registers the uniquely discovered installation
   for that user. `template status` reports the missing registration instead.
4. Open Codex once to initialize its user-local engine, then fully quit it,
   including its tray process. The model-free probe does not need desktop
   sign-in. An existing client in the test session is reported as busy and is
   not terminated.
5. Request native sandbox initialization explicitly, accepting any Windows
   administrator consent in the template:

   ```sh
   python3 scripts/windows_test_runner.py template prepare \
     --template YOUR-DEDICATED-TEMPLATE-UUID --dedicated-template \
     --test-user tofa-test --test-auth none --initialize-sandbox \
     --output /tmp/template-native-setup-1.json
   ```

   This uses the installed engine's documented
   [`windowsSandbox/setupStart`](https://learn.chatgpt.com/docs/app-server#windows-sandbox-setup-windowssandboxsetupstart)
   interface with `mode: elevated`, and requires its successful completion
   notification before measurement. It never switches to the unelevated sandbox
   or Full access. Vendor-managed sandbox setup state is retained for subsequent
   checks. Setup consent is a template-bootstrap step, not an unattended-run step.
   Keep the designated VM visible: this initialization task opens visibly and
   waits up to 60 seconds for setup, including your response to Windows consent.
   If you approve near the deadline and preparation reports a timeout, run
   `template status` with a fresh report path to check whether setup completed.

`--test-auth none` is the explicit authentication choice for this slice. It makes
no model turns and does not import, inspect, or copy account credentials. Live
model authentication, desktop trust, and Guardian provisioning remain
unverified and belong to the later desktop slice. A native pass does not imply
readiness for those suites. The native setup request and permission checks were
validated without completing desktop sign-in. The runner neither provisions
authentication nor claims that existing authentication is absent.

## Unattended readiness checks

Once bootstrapped and signed into the Windows test account, use a new report path
for each check:

```sh
python3 scripts/windows_test_runner.py template status \
  --template YOUR-DEDICATED-TEMPLATE-UUID --dedicated-template \
  --test-user tofa-test --test-auth none \
  --output /tmp/template-status-1.json
```

Status actively measures the native sandbox: it creates uniquely named synthetic
state and a temporary scheduled task, but does not register packages or initialize
the sandbox. It is not a read-only inventory command. A failed prerequisite
prevents the native probe, and no operation in this slice starts product trials.

The limited user creates the workspace. The probe verifies its owner, effective
ACL-management permission, and ordinary write access. Through the actual native
engine it then writes and reads a marker in that workspace, and attempts a write
to a separate synthetic directory. Denial requires a nonzero native command
exit code, `GetContentWriterUnauthorizedAccessError`, and an absent outside
marker. A missing executable, arbitrary nonzero exit, or missing marker alone
cannot pass. Both commands use workspace-write policy with no network access.

To preserve the ownership regression, run the negative case on disposable state:

```sh
python3 scripts/windows_test_runner.py template prepare \
  --template YOUR-DEDICATED-TEMPLATE-UUID --dedicated-template \
  --test-user tofa-test --test-auth none --workspace-fixture acl-unmanageable \
  --output /tmp/template-ownership-negative-1.json
```

This intentionally creates one SYSTEM/Administrators-owned fixture with user
Modify permission, but no permission to manage its ACL. **The expected result is
failure**, even though ordinary file writes work. A subsequent default
`user-owned` check must pass. The runner never repairs ownership recursively or
changes unrelated directories to make this check pass.

## Reports and limits

Exit 0 means `native_ready`: all native assertions and correlated task completion
passed. Nonzero reports distinguish `missing_prerequisites`, `bootstrap_required`,
and other failures, with a stable reason and concrete bootstrap instructions where
applicable. Desktop trust, Guardian behavior, and authentication remain separate
capabilities. CLI progress names the current stage.

Reports record the actual OS/architecture, selected package/version, engine
version and package-matching SHA-256, runtime version, user SID/session, assertions,
task completion, requested changes, and diagnostic locations. The existing
desktop minimums (26.917.71314 and engine 0.155.0-alpha.16.4) remain floors. Newer
working versions and changed hashes are accepted; the executable must match its
currently selected installed package, not a historical hash allowlist.

SYSTEM creates and protects the unique staging root before uploading any harness
or request. The limited-user probe verifies that it cannot write or manage the
ACL of either file. User-writable output is separate from those protected inputs.

Reports contain only validated protocol fields, never raw engine output,
authentication files, unrelated content, or ordinary account paths. Keep reports
local. An existing report is never overwritten, including after a failed attempt.
Fresh run IDs bind discovery, task completion, and native results. PowerShell
progress-only CLIXML is classified explicitly; other stderr fails transport.
Only UTM's known missing-file/path result is retried while awaiting a fresh
envelope. Guest script execution policy is not changed.

The default host deadline is 600 seconds, configurable with `--timeout` (1–600).
Preparation completes before task execution. The host requires 180 seconds
remaining before starting the 120-second Limited task, with a 125-second
controller wait and a 150-second transport cap. A shorter remaining budget fails
explicitly before starting the task. This replaces the former 180-second default,
which left no reliable provisioning margin. Diagnostic checkpoint collection has
its own read-only budget of at most 15 seconds.
Guest tasks have a 120-second execution limit. Completed tasks are unregistered;
markers are removed and the owned engine is allowed to exit normally. A timeout
or forced engine exit cannot pass. Failed/incomplete tasks and synthetic guest
artifacts may remain for diagnosis. No VM cleanup is attempted. Host reports
identify the unique `C:\Users\Public\tofa-template-<run>` staging directory and
the test user's `tofa-template-<run>` workspace. Do not run template preparation
concurrently with clone runs. Clone runs use an exclusive lock and conservative
crash refusal; automated recovery remains a later slice of #78.

## Implementation evidence and checks

The ownership experiment documented in #78 and the local
`docs/research/windows-sandbox-workspace-2026-10-05.md` investigation are the
implementation inputs. Their original diagnostic harness and failed/successful
attempts remain unchanged. The production CLI removes the diagnostic's hardcoded
VM identity, discovers the test user/runtime/package, creates user-owned
workspaces, and retains a failing native regression fixture.

Run `python3 scripts/windows_template_test.py -v` for fast integration coverage
through the public CLI and a controlled external UTM executable. Fixture passes
are not native evidence. Native results and remaining limitations are recorded
separately in the implementation evidence report.
See [the 2026-10-05 implementation checks and outstanding native gate](windows-template-evidence-2026-10-05.md).
