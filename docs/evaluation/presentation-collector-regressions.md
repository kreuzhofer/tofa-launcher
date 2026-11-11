# Presentation collector regressions (#143)

The synthetic response implementation lives in
[`scripts/presentation_responder.py`](../../scripts/presentation_responder.py).
The tracked calibration entry point imports it. New qualification kits should
copy the tested module from their declared source revision and bind its hash,
or import it from their frozen checkout. A generated human guide supplies paths
and observations; it must not carry an independently reimplemented responder.

The executable candidate and the collector revision are separate provenance.
Promoting a collector correction does not change a frozen launcher, rewrite an
old attempt, qualify an unobserved preview, or remove production admission gates.
Existing issued guides remain immutable snapshots; refresh them explicitly for
a future attempt instead of changing an active run.

## Recorded failures and regression coverage

| Mistake | Correction | Permanent check |
| --- | --- | --- |
| Assuming a request with `functions.exec` represented every main request; a later main request advertised direct MCP and command tools | Select the actual advertised representation; preserve exact provider ownership and loader schema validation | Direct namespace, flat CLI, nested discovery, missing/foreign/duplicate loader tests |
| Treating a Node bundle package revision such as `24.22.1-cua.1` as the literal `node --version` output | Compare the Node core version while retaining the complete package revision in provenance | Version probe accepts the observed package form and rejects a different core version or unknown suffix |
| Treating a running command's null exit status as a completed failure, or interpreting direct textual output as a structured nested result | Parse the actual execution envelope; poll only the same session; validate the final artifact-bound marker | Direct/nested polling, changed-session rejection, failed execution and artifact-tampering tests |
| Reusing a custom-tool poll in the direct-tool path | Keep the advertised tool representation throughout the turn | Direct poll returns the actual `write_stdin` function and stays within the polling wait limit |
| Saving raw partial results where the legacy verifier expects completed execution evidence | Retain raw outputs separately and save a normalized execution record without null intermediate exit statuses | Re-read the saved smoke receipt through the existing artifact verifier |

These are collector failures, not model-quality failures. Their original private
receipts remain retained outside the repository. Tests reconstruct only the
necessary catalog and output shapes; they contain no captured conversations,
credentials, account identifiers, installation paths or private evidence paths.

## Automated checks and remaining boundary

The existing prototype CI workflow runs:

```sh
python3 scripts/presentation_responder_test.py -v
python3 scripts/presentation_synthetic_test.py -v
python3 scripts/presentation_runtime_test.py -v
```

The transport suite independently checks that synthetic inference does not reach
an upstream model and cannot fabricate Guardian approval. The responder validates
loader results and artifact hashes but never executes tools itself. These tests
need no Desktop launch or paid inference; installed-client checks remain explicit
opt-ins. Native preview visibility still requires an actual Desktop observation.

The older `capability_runtime.qualify` proof validator still requires a directly
observed MCP call in its retained request trace. Supporting orchestration for
execution does not silently relax that legacy proof contract: nested execution
receipts require the behaviour-specific assessment used by the current Desktop
qualification path. Do not infer release qualification from responder success.

The frozen private guide issued before this promotion remains unchanged. Future
kits should use the tracked implementation above; previous accepted evidence and
the failed attempt are not relabelled by this change.
