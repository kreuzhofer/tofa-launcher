# Independent Desktop naming diagnosis (#128)

Status: diagnostic implementation reviewed; bounded native naming and visible
title checks passed. Original intermittent failure remains unexplained.
Starting revision: `29e2983`, retained integration branch. No naming model, request
adapter, approval, settings or client behavior has been changed. The launcher
binary remains the lifecycle/native-qualified namespace candidate `deb5ac9`, SHA-256
`11d28bf933f5230bc9c06744d98726b51d096504e9e683471f21b9c369fbea1e`.

## Reproduction and evidence

The original native failures show `stream_failure` without an HTTP status. Their
exceptions were discarded, so the old records cannot distinguish connection loss,
header parsing, provider failure or client cancellation. They remain unchanged.

A loopback HTTP regression at the observer's public boundary recreates that lost
diagnostic: an upstream closing before headers returned no category or exception.
The test failed before the change and passes now:

```sh
cd scripts
python3 -m unittest capability_observer_test.BoundaryTests.test_naming_disconnect_before_headers_retains_private_exception
```

The observer now exports only fixed stage/category/exception-type values. Original
exception tracebacks are retained in private `transport-error-N.json` files, mode
0600, bounded to the final 65,536 characters. Explicit provider error events are
retained separately in private `provider-error-N.json`, bounded to the first 65,536
characters. HTTP rejection, provider terminal errors and incomplete streams remain
separate. Existing aggregate verdicts and routing are preserved. Tests also
verify that private malformed-header text stays out of exported records.

One explicitly approved replay of the exact native Kimi naming request through the
actual adapter and instrumented observer returned HTTP 200 and a completed Lightning
response in about 1.5 seconds. No tool ran and no Desktop session was launched.
Local replay with both the pre-namespace adapter (`c6e508f`) and current adapter
produced the same provider request and preserved that response, with race detection.
This excludes deterministic rejection of this captured shape and a deterministic
namespace-change regression at this boundary. It does not establish reliability,
exclude an intermittent provider/lifecycle fault, or qualify native title visibility.

Initial hypothesis order after the red diagnostic was: (1) adapter/connection loss
before headers, (2) provider rejection/interruption, (3) native client cancellation.
The missing header status motivated that order; it did not identify the cause.
After successful live/local replay, intermittent adapter/connection, provider and
native lifecycle causes are tied at rank 1 because the old exceptions cannot
distinguish them. Deterministic rejection of this captured shape is contradicted
by the replay. A fresh native failure's stage/category or explicit provider event
will distinguish these predictions; a successful run only delimits intermittency.

See [sanitized evidence](evidence/presentation-runtime-126-127/naming-128-diagnostic.json).
Private files and scripts are under `/tmp/tofa-presentation-validation/checks/naming-128`.

## Completed native attempt

The maintainer ran `/tmp/tofa-presentation-validation/run-naming-diagnostic.sh`
in an interactive Terminal. It predeclared one fresh actual Desktop conversation, Kimi K3 main,
GLM-5.3-Flash Guardian and unchanged independent Lightning naming. The synthetic
one-sentence lighthouse prompt asks for no tools/files. This is a separate naming
corpus, not a presentation case or a replacement of historical outcomes.

Bounds: 600 seconds including manual setup, six requests, 4096 output tokens per
request, no automatic retries; launcher outer guard 900 seconds. Preflight passed.
The observer records any transport exception privately. After the main answer,
the wizard waits only for pending naming to reach a terminal state within the same
deadline; it does not retry or wait on an already failed title. The operator records
visible generated title separately as passed/failed/not observed, including whether
the run had already ended. Main completion does not wait for a failed title.

The diagnostic uses the ordinary profile and protected-settings comparisons. It
uses no presentation qualification override and does not execute a deck workflow.
The observer/handoff source changes alter the harness hash; existing presentation
proofs remain historical and are not rewritten to bypass qualification checks.

## Disposition

Native run `32dee8c7142b41ef968da5677a04af5e`, started 2026-10-13T19:28:29Z,
completed one Lightning naming response (HTTP 200, 6.886 seconds) and one Kimi
main response (HTTP 200, 1.970 seconds). The maintainer independently recorded a
visible generated title before finishing the run. Total duration including setup
was 69.031 seconds. Protected settings hashes matched and no environment drift
was detected. No tools or Guardian requests ran. The harness and launcher hashes
match the predeclared identities. See [native evidence](evidence/presentation-runtime-126-127/naming-128-native.json).

The raw child exit code is 1 after operator finish; the existing evaluator accepts
that stopping condition after completed responses and records status `completed`.
Its generic case-05 reference criterion remains `failed/missing_references` in the
original report. The distinct naming-only prompt requested no artifact references;
this assessment makes no presentation or reference-syntax pass claim.

The bounded diagnostic now has a supported evaluation disposition: retain the
instrumentation and score naming separately in #130. A failed title must retain
its failure and private diagnostic without forcing an automatic retry or delaying
operator finish. The original failure was not reproduced; its responsible layer
and whether it was a runtime regression remain unestablished. The successful
synthetic native attempt is not a matched native baseline comparison. Intermittent
adapter, provider and client lifecycle hypotheses remain unresolved.

Keep #128 open pending integration publication/merge disposition, alongside #129.
Next resolve those prerequisite tickets, freeze identities and requalify changed
harness bytes before predeclaring #130's four fresh deck attempts. Historical
outcomes remain unchanged. No naming fix, repeated reliability, support or release
readiness is claimed.

## Verification checkpoint

Implementation `cf6cbec` passed Standards and Spec review (zero remaining findings),
the full Go race suite and `go vet`. Python discovery with the pinned Go toolchain
ran 495 tests: 85 skipped and six argument-related errors in lifecycle/terminal
tests. All six passed through their documented standalone entry points, yielding
410 passed and 85 skipped across the combined checks. Generic discovery itself
exited nonzero; its original log is retained. An earlier unrelated Windows lease
timing failure passed both an isolated check and the later full run; it remains
recorded. See [verification evidence](evidence/presentation-runtime-126-127/naming-128-verification.json)
for invocation limitations, log hashes and the exact native handoff hashes.
