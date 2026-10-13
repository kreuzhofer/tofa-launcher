# Independent Desktop naming diagnosis (#128)

Status: diagnostic implementation ready; instrumented native validation pending.
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
0600, bounded to the final 65,536 characters. HTTP rejection and incomplete streams
remain separate. Existing aggregate verdicts and routing are preserved. Tests also
verify that private malformed-header text stays out of exported records.

One explicitly approved replay of the exact native Kimi naming request through the
actual adapter and instrumented observer returned HTTP 200 and a completed Lightning
response in about 1.5 seconds. No tool ran and no Desktop session was launched.
Local replay with both the pre-namespace adapter (`c6e508f`) and current adapter
produced the same provider request and preserved that response, with race detection.
This excludes deterministic rejection of this captured shape and a deterministic
namespace-change regression at this boundary. It does not establish reliability,
exclude an intermittent provider/lifecycle fault, or qualify native title visibility.

See [sanitized evidence](evidence/presentation-runtime-126-127/naming-128-diagnostic.json).
Private files and scripts are under `/tmp/tofa-presentation-validation/checks/naming-128`.

## Next native attempt

Run `/tmp/tofa-presentation-validation/run-naming-diagnostic.sh` in an interactive
Terminal. It predeclares one fresh actual Desktop conversation, Kimi K3 main,
GLM-5.3-Flash Guardian and unchanged independent Lightning naming. The synthetic
one-sentence lighthouse prompt asks for no tools/files. This is a separate naming
corpus, not a presentation case or a replacement of historical outcomes.

Bounds: 600 seconds including manual setup, six requests, 4096 output tokens per
request, no automatic retries; launcher outer guard 900 seconds. Preflight passed.
The observer will record any transport exception privately. The operator records
visible generated title separately as passed/failed/not observed, including whether
the run had already ended. Main completion does not wait for a failed title.

The diagnostic uses the ordinary profile and protected-settings comparisons. It
uses no presentation qualification override and does not execute a deck workflow.
The observer/handoff source changes alter the harness hash; existing presentation
proofs remain historical and are not rewritten to bypass qualification checks.

## Disposition

Do not close #128 or claim naming fixed yet. The native run must distinguish the
remaining hypotheses: adapter/connection failure, provider failure, and native
client cancellation. If it succeeds, record that success alongside the earlier
failures and delimit the unresolved intermittent condition. Record human-visible
title outcome independently of provider completion. #130 stays gated on disposition.
