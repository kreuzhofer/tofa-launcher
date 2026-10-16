# Launch authorization diagnosis — 2026-10-16

**Cause:** the native WebSocket error formatter includes the endpoint URL. A launch
capability in that URL therefore becomes diagnostic content on connection errors.
Fixing the fixture's HTTP version only hides one trigger; an interrupted handshake
discloses the same secret.

**Validated candidate fix:** use a separately named routing provider with
`requires_openai_auth=true` and an `env_http_headers` launch header. Keep the URL
free of secrets, retain the native credential independently, reject missing/wrong
launch headers, and strip the launch header before either upstream. This avoids
the built-in `openai` provider override restriction without disabling native auth.
It is validated at the engine/prototype boundary, not shipped in the launcher.

## Feedback loop and hypotheses

The minimized actual-engine regression runs in about one second. It initializes
a disposable engine, starts one synthetic turn against a loopback failure server,
and asserts that the generated launch secret is absent from diagnostics. It needs
no model response or tool execution. Every invocation requires a fresh directory
under the fixed validation root. Secrets are generated in memory; the header
variant passes its value through a child environment variable, not CLI arguments.

```sh
python3 -B internal/tofa/prototypes/native-provider/authorization_probe.py \
  --secret-location path \
  --engine /Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex \
  --out /tmp/tofa-presentation-validation/checks/prototype-133/auth-red-new
```

The red control exited 1 twice (2.17s and 0.85s), with the exact signal:

```text
secret_in_stderr=true
WebSocket protocol error ... url: ws://127.0.0.1:<port>/<REDACTED>/v1/responses
```

Predictions were recorded before testing:

1. Removing the URL secret while keeping the same failure should remove the leak.
   Confirmed (`auth-absent-1`). This is a diagnostic control, not an authorized
   production route: removing authentication alone is not a fix.
2. If only HTTP/1.0 formatting caused disclosure, a disconnected socket should not
   disclose it. Falsified (`auth-disconnect-1`): the complete URL was logged again.
3. If the leak is confined to stderr, other generated artifacts should not contain
   it. No other secret-bearing artifact was found in these minimized runs. This is
   not a guarantee covering every engine error/log path and does not justify
   relying solely on a stderr filter.

The subsequent carrier hypothesis was explicit: a separately named provider that
requires native authentication may accept an environment-backed header even though
overriding the built-in provider is prohibited. The engine confirmed both native
authentication and the distinct header on the actual outgoing fixture request.

## Regression and original-scenario verification

Run the same regression with `--secret-location header`. It exits 0 only when a
request occurs, native auth is still required, the native credential and launch
header both arrive, and the launch secret is absent from stderr and other retained
engine artifacts. `--failure disconnect` verifies the alternate trigger.

Both header cases passed (0.79s/0.82s). Diagnostic errors remained visible, with a
secret-free URL; no log-level suppression or native error-filter patch was used.
The final regression revision also requires the diagnostic error itself to be
observed, preventing a missing trigger from passing. Its final red/header/
header-disconnect runs returned 1/0/0 in 0.81s/0.88s/0.82s respectively, with the
same final probe source hash retained in all three summaries.

The original switching/resume/review experiment was then rerun with:

```sh
python3 -B internal/tofa/prototypes/native-provider/thread_probe.py \
  --auth-mode authenticated-header \
  --engine /Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex \
  --out /tmp/tofa-presentation-validation/checks/prototype-133/auth-thread-new
```

Final run `auth-thread-header-3`: **16 scoped checks passed**, 16 routed engine
requests and 18 fixture-upstream requests (two existing-native turns bypassed
the router). Evidence establishes:

- Missing/wrong launch headers and a control-like path are denied before upstream.
- New routed conversations switch Kimi → GPT → Kimi with retained context.
- Legacy `nebius-tofa` conversations resume without migration.
- Existing `openai` conversations retain their native direct route and resume
  unchanged. Production should not globally point those histories at a local
  endpoint that requires a header the built-in provider cannot supply. The fixture
  uses an owned native upstream to observe this behavior without external traffic.
- Review selection/provenance and deny enforcement survive the carrier change.
- Native/Token Factory credentials remain separated. The launch header is removed
  before either upstream, and the secret is absent from retained engine artifacts.

The fixture's native title replay still inspects request shape; it does not yet
implement the newly accepted launch-wide TOFA naming policy.

## Actual signed-in account check

`auth-account-1` used only initialize, account/read (`refreshToken=false`) and
config/read in the real home, with protected writes denied and protected hashes
checked between cases and afterward. Normal native account-discovery connectivity
was allowed; no inference RPC, prompt or Desktop launch was submitted.

The authenticated custom router returned `account_type=chatgpt` and
`requires_openai_auth=true`; the original unauthenticated custom-provider control
returned no account. Ordinary before/after matched, and protected-state checks
passed. All six account assertions passed. The header environment mapping was
declared in this read-only account probe, but no launch-secret value was needed or
sent; actual header transport is established separately by the synthetic fixture.

This corrects the earlier assumption that only the built-in provider identity
could preserve native account context. Requiring native authentication on a custom
provider also preserves it in this installed engine. Actual Desktop handling of
that provider remains unqualified.

## Provenance, cleanup and remaining scope

Engine: `codex-cli 0.162.0-alpha.17.2`, SHA-256
`0d5ac7aae20c4eda6242428d5e218c55ba96d8763fda2a271088ff37104b9d28`.
Desktop identity observed by the account probe: version `26.1007.71326`, build
`20398`. Each retained result carries its probe source hash. The scripts in this
revision include the final candidate; earlier result hashes describe earlier
probe iterations. Original and failed evidence was not overwritten.

The minimal regression existed and failed before the header change. This is the
correct native-engine seam for the observed URL diagnostic bug. No production
native-account route exists yet, so claiming a production Go regression/fix would
be misleading; carry the mechanism and fault cases into its implementation tests.
The ordinary launcher guard is unchanged, and no production Go suite was run.

All instrumentation is confined to this clearly marked debug/prototype directory.
No production debug logging was added. Python/JSON syntax and `git diff --check`
are checked alongside the actual engine runs. Stderr is redacted before being
shown; raw account diagnostics and disposable homes remain private and untracked.
The published summaries contain no credential or launch-secret values.

Still required: production constant-time capability validation and bounded input,
independent control-endpoint authorization, redacted diagnostics/export coverage,
environment inheritance review, provider identity on ordinary launches, concurrent
turn/review behavior, actual signed-in inference transport, and actual Desktop
account/plugin lifecycle, picker and presentation-preview qualification. Do not
remove the guard or promote model support based on these probes.
