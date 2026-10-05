# Windows ARM64 CLI qualification — 2026-10-05

This continues [issue #75](https://github.com/kreuzhofer/tofa-launcher/issues/75)
after the maintainer completed Windows launcher login. The
[2026-10-02 comparison](cli-refresh-2026-10-02.md) and its five zero-inference
Windows blocked attempts remain unchanged. This run supplies Windows evidence;
it does not rerun or replace the macOS results.

## Frozen conditions

[Preflight](evidence/cli-windows-2026-10-05/preflight.json) confirmed all five model
IDs available through the saved login. The [continuation freeze](evidence/cli-windows-2026-10-05/freeze.json)
records the unchanged source, artifacts, metadata, prices and limits before live
inference. Production launcher source is `374d137`, binary version
`issue75-374d137`; Windows 11 build 10.0.26200 runs natively as ARM64 in
agent-operated UTM. The installed native Codex CLI is 0.160.0. The production launcher
hash matches the prior production freeze. Client, harness and candidate snapshot
hashes match the final Windows [synthetic installed-client proof](evidence/cli-refresh-2026-10-02/windows-synthetic/synthetic-final/).
That proof used a separate `evaluation-fixture` launcher with the same launcher
implementation, rather than the production executable. It passed all five exact
pairs, native approval gates and cleanup; the separate native reasoning-separation
test also passed. The implementation and harness are unchanged, so that proof was
reused. The only prerequisite change was saved launcher
login, supplied by the maintainer without exporting credentials.

Main identities are DeepSeek V4.1 Flash, GLM 5.3, GLM 5.3 Flash, Kimi K3 and
Nemotron 3 Ultra. Every run explicitly selects `zai-org/GLM-5.3-Flash` Guardian
on the adapted CLI route. Identical role identities are deduplicated. Three
independent two-turn coding sessions and three allow/deny pairs are planned per
combination. The existing evaluator stops each lane independently after a failed
repeat. No substitute model, route switch, increased limit or paid retry is used.

Limits remain 48 upstream requests per pair (240 for this continuation), 4,096
output tokens per request, 1 MiB input, 8 MiB response, 256 KiB SSE event, 180-second
coding request/turn deadlines, 90-second Guardian requests and 120-second outer
approval turns. Codex 0.160.0's native Guardian deadline is also 90 seconds.
Existing initialized Windows sandbox state is reused through runtime overrides;
ordinary settings are checked and only evaluation-owned sessions are removed.

The retained approximate 2026-09-23 input/output USD/M rates are DeepSeek
0.30/1.20, GLM 1.40/4.40, GLM Flash 0.15/0.50, Kimi 3.00/15.00, Nemotron 1.00/3.00.
Predeclared conservative maximum estimates per pair are respectively $15.335424,
$71.329382, $7.648051, $153.944064 and $50.921472, assuming input tokens do not
exceed UTF-8 request bytes and excluding unknown provider-added overhead. These
are informational estimates, not currency caps or billing guarantees. Missing
usage remains unknown; synthetic approval proposals are excluded from paid totals.

Client versions are measured baselines, not exact-version admission gates. The
evaluator accepts 0.155.1 and newer until an actual breaking change is found.

## Results and support decisions

Promote **DeepSeek V4.1 Flash and Kimi K3 with GLM 5.3 Flash Guardian on Windows
ARM64**. Both passed the complete defined boundary. GLM 5.3, GLM Flash and
Nemotron remain Experimental on Windows. The macOS decisions are unchanged:
DeepSeek, GLM 5.3 and Kimi are Supported there; GLM Flash and Nemotron are not.
No Linux, amd64, direct-route or other Guardian combination inherits these results.

Counts below are **passed / attempted / planned**. Main counts are two-turn
sessions; Guardian counts are allow/deny pairs. All planned denominators remain
three. Locally blocked attempts count as attempts even when no inference occurred.

| Exact main ID | Windows main | Windows Guardian | Upstream requests | Estimated main + Guardian USD | Windows decision |
| --- | --- | --- | ---: | --- | --- |
| `deepseek-ai/DeepSeek-V4.1-Flash` | 3 / 3 / 3 | 3 / 3 / 3 | 36 | 0.0995787 + 0.0085066 | Supported |
| `zai-org/GLM-5.3` | 1 / 2 / 3 | 0 / 1 / 3 | 48 | 1.1851190 + unmeasured (0 paid requests) | Experimental: shared request budget exhausted |
| `zai-org/GLM-5.3-Flash` | 0 / 1 / 3 | 3 / 3 / 3 | 22 | unknown (0.0419672 known) + 0.0084945 | Experimental: coding deadline |
| `moonshotai/Kimi-K3` | 3 / 3 / 3 | 3 / 3 / 3 | 33 | 0.7976670 + 0.0085567 | Supported |
| `nvidia/Nemotron-3-Ultra-550b-a55b` | 0 / 1 / 3 | 3 / 3 / 3 | 7 | unknown (no main usage returned) + 0.0083892 | Experimental: SSE event limit |

Retained reports: [DeepSeek](evidence/cli-windows-2026-10-05/deepseek.json),
[GLM](evidence/cli-windows-2026-10-05/glm.json),
[GLM Flash](evidence/cli-windows-2026-10-05/glm-flash.json),
[Kimi](evidence/cli-windows-2026-10-05/kimi.json),
[Nemotron](evidence/cli-windows-2026-10-05/nemotron.json).

There were **146 paid upstream requests**, with usage returned for 144. The
**known estimated subtotal is $2.1582789; the complete total is unknown**.
One GLM Flash request and the sole Nemotron main request lacked usage. No usage
or cost is fabricated for them. GLM's Guardian role has no measurement because
it sent zero paid requests after the shared budget was exhausted.

DeepSeek and Kimi scored protocol 6/6 and coding 2/2 in every session, and passed
all six native Guardian decision/execution cases each. GLM's first session passed,
but its second exhausted the shared 48-request budget; its third session was
unattempted. Both cases in its first Guardian pair then hit that same local stop,
and the remaining pairs were unattempted. The secondary protocol/model-mismatch
categories in those blocked cases are not evidence of provider routing or approval
behavior: no Guardian inference occurred. The budget was not reset between lanes.

GLM Flash's first coding turn reached the fixed 180-second deadline. Nemotron's
first main request reached the fixed 256 KiB SSE event limit. Each coding lane
stopped after that first attempted session, with two sessions unattempted; their
independent Guardian lanes passed all three pairs. A local evaluation limit does
not prove general model incapability or provider protocol rejection. Guardian
success alone does not qualify a main.

Worst measured Guardian assessment intervals were DeepSeek 38,742.571 ms,
GLM Flash 19,675.634 ms, Kimi 24,063.590 ms and Nemotron 9,520.369 ms. GLM's is
unmeasured. These observer intervals include adapter/provider waits and any native
review retries; they are not pure compute latency or a service-level guarantee.

All five reports show normal settings preserved, native config/auth preserved,
no harness defect, and successful removal of evaluation-owned sessions. Removed
session counts are 9, 4, 7, 9 and 7 respectively: **36 total**. The maintainer's
saved launcher login remains in place.

Windows main reasoning effort was observed as `medium`, inherited from native
settings; the macOS campaign omitted it. Measured Guardian requests used native
`none` before adapter processing; GLM's unmeasured Guardian lane has an empty
observed list. This is a difference in measured environments, not a controlled
platform-only comparison. No default was changed to produce a pass, and no raw
conversation, generated answer, reasoning text, key or project identity is exported.
The unchanged synthetic proof verifies separation when reasoning is emitted.

## Scope and validation

Support remains specific to the exact main/Guardian pair, adapted CLI route and
listed ARM64 platforms. These small synthetic coding and continuation tasks,
stream/tool checks and controlled approval proposals are not broad coding-quality,
security or approval-safety guarantees. The proposal fixture does not establish
that each main would naturally request the same action. Published-candidate
installation acceptance under #23 remains separate; no release was published.

Public CLI tests were first run in Windows with the new admission expectations
and the old records: DeepSeek and then Kimi failed as expected. Updating each
reviewed record removes experimental consent only for the qualifying platform and
pair. GLM remains Experimental on Windows; Guardian overrides, direct routes and
unverified platforms continue to require consent. Existing macOS picker behavior
and desktop support are retained.

[Final validation](evidence/cli-windows-2026-10-05/validation.json) passed: the full
Go race suite (`GORACE=atexit_sleep_ms=0`), vet, all 252 discovered Python tests
(172 passed, 80 optional/platform skips), and native Windows CLI policy tests.
The race setting only removes the instrumentation exit delay documented in the
previous validation; production deadlines are unchanged. Standards and Spec
reviews each have zero remaining findings. Review corrected a provenance wording
error distinguishing the production launcher from the synthetic fixture; no
artifact hash, limit or live outcome changed. Temporary scheduled tasks were
removed, and Windows remains running with the saved login intact.
