# Codex CLI five-model refresh — 2026-10-02

Promote **DeepSeek V4.1 Flash, GLM 5.3 and Kimi K3**, each with explicit
**`zai-org/GLM-5.3-Flash` Guardian**, on the **adapted macOS ARM64 CLI route only**.
All three passed three independent two-turn coding sessions and three Guardian
allow/deny pairs. GLM Flash and Nemotron remain Experimental as mains. Windows
ARM64 passed the final synthetic installed-client tests, but live qualification
was blocked by missing saved launcher login. No Windows pair is promoted.

This is issue [#75](https://github.com/kreuzhofer/tofa-launcher/issues/75), separate
from the historical [#36 selected-pair campaign](selected-pairs-2026-09-23.md).
Those earlier reports remain unchanged. Model-specific support does not replace
published-candidate installation qualification under #23. These record changes
require a new published candidate before release acceptance; this campaign did
not publish a release.

## Frozen artifacts and conditions

The [pre-run freeze](evidence/cli-refresh-2026-10-02/freeze.json) records source
commit `374d137`, production launcher hashes, client hashes, metadata, route,
limits and price estimates. Live reports independently record the executable and
harness hashes. Both production launchers were built from that commit with
`-trimpath -ldflags '-X main.version=issue75-374d137'`. The subsequent support
publication changes admission and labels, not inference routing or the evaluator.

| Platform | Measured native client | Environment | Evidence |
| --- | --- | --- | --- |
| macOS ARM64 | Codex CLI 0.158.0 | macOS 26.6.2, build 25G83 | Five live attempts below |
| Windows ARM64 | Codex CLI 0.160.0 | Windows 11, build 10.0.26200, agent-operated UTM | Synthetic passes; five catalog-blocked attempts |

The evaluator accepts **0.155.1 and newer**. Actual versions and hashes identify
measured artifacts; they are not exact-version admission gates. Newer versions
are assumed compatible until a breaking change is found. Support records restrict
platforms to `darwin/arm64`; Windows, Linux and other architectures remain
Experimental. Existing desktop support records are independent and unchanged.

The [macOS catalog check](evidence/cli-refresh-2026-10-02/mac-catalog.json) found all
five IDs available. Each invocation rechecked availability before inference.
[Windows preflight](evidence/cli-refresh-2026-10-02/windows-synthetic/catalog-diagnostic.json)
reported `not logged in`; its availability booleans are unmeasured, not evidence
that the models are unavailable. No project identity or credentials are published.
Existing macOS authentication was reused; Windows credentials were not copied or
modified.

Each invocation retained the existing procedure: three independent two-turn
sessions and three independent approval pairs; a failed repeat stops only its own
lane. The explicit main/Guardian identities are deduplicated when identical. No
Guardian contest, direct-route qualification, substitution or live rerun occurred.
Limits were **48 upstream requests per pair/platform** (480 across ten planned
runs), **4,096 output tokens per request**, **1 MiB input**, **8 MiB response**,
**256 KiB SSE event**, **180 seconds per coding request and turn**, **90 seconds
per Guardian request**, and **120 seconds per outer approval turn**. Official
0.158.0 and 0.160.0 Guardian source both retain a 90-second native review deadline;
source URLs and hashes are in the freeze. No limits were raised after failure.

The retained 2026-09-23 approximate USD/M input/output rates are DeepSeek
0.30/1.20, GLM 1.40/4.40, GLM Flash 0.15/0.50, Kimi 3.00/15.00, Nemotron 1.00/3.00.
The pre-run informational maximum estimates per invocation were respectively
$15.335424, $71.329382, $7.648051, $153.944064 and $50.921472. These deliberately
conservative estimates assume input tokens do not exceed UTF-8 body bytes and
exclude unknown provider-added overhead. They are not billing guarantees or
currency caps. Actual observed usage is reported separately below.

## Results and explicit support decisions

Guardian is `zai-org/GLM-5.3-Flash` in every row. Main counts are **passed / attempted
/ planned sessions**; Guardian counts use the same convention for allow/deny pairs.
A failed session remains attempted, and unattempted sessions remain in the planned
denominator. Every measured Guardian case passed native decision and execution
gates; 3/3 pairs means six cases.

| Exact main ID | macOS main | macOS Guardian | Requests | Estimated main + Guardian USD | Decision |
| --- | --- | --- | ---: | --- | --- |
| `deepseek-ai/DeepSeek-V4.1-Flash` | 3 / 3 / 3 | 3 / 3 / 3 | 27 | 0.05661780 + 0.00825510 | Supported, macOS ARM64 only |
| `zai-org/GLM-5.3` | 3 / 3 / 3 | 3 / 3 / 3 | 27 | 0.23503520 + 0.00836115 | Supported, macOS ARM64 only |
| `zai-org/GLM-5.3-Flash` | 1 / 2 / 3 | 3 / 3 / 3 | 18 | 0.02326005 + 0.00827055 | Experimental: incorrect coding artifacts |
| `moonshotai/Kimi-K3` | 3 / 3 / 3 | 3 / 3 / 3 | 27 | 0.58363800 + 0.00834875 | Supported, macOS ARM64 only |
| `nvidia/Nemotron-3-Ultra-550b-a55b` | 0 / 1 / 3 | 3 / 3 / 3 | 8 | unknown (0.011218 known) + 0.00836940 | Experimental: SSE event limit |

Sanitized live reports: [DeepSeek](evidence/cli-refresh-2026-10-02/mac-live/deepseek.json),
[GLM](evidence/cli-refresh-2026-10-02/mac-live/glm.json),
[GLM Flash](evidence/cli-refresh-2026-10-02/mac-live/glm-flash.json),
[Kimi](evidence/cli-refresh-2026-10-02/mac-live/kimi.json),
[Nemotron](evidence/cli-refresh-2026-10-02/mac-live/nemotron.json).

Total measured upstream requests: **107**. Known estimated subtotal: **$0.951374**.
The total is **unknown**, because one Nemotron request lacks usage after the event
limit. This subtotal must not be presented as the complete bill. Windows made zero
inference requests. Requests for controlled synthetic approval proposals are
excluded from paid totals.

DeepSeek, GLM and Kimi each scored protocol 6/6 and coding 2/2 in every session.
GLM Flash's second session retained protocol 6/6 but coding 0/2: turn one produced
no summary artifact; continuation produced the initial fields but omitted the
required minimum and average. The third session was unattempted. Nemotron's first
session stopped after the observer's fixed 256 KiB event limit; this is a local
bounded-evaluation failure, not proof of provider protocol rejection or model
coding inability. Its remaining two sessions were unattempted. Guardian success
does not qualify either failed main.

Worst observed Guardian assessment intervals were DeepSeek 3,585.440 ms, GLM
6,076.639 ms, GLM Flash 2,601.040 ms, Kimi 3,917.560 ms and Nemotron 3,816.512 ms.
These include observer-visible adapter/provider time, not pure provider compute.
Reports retain per-request and per-turn timings, usage and native retry evidence.

All five macOS reports preserved ordinary settings and synthetic input files,
with no harness defect. Native main reasoning effort was omitted; Guardian effort
was `none` before the launcher adapter. Successful coding turns reported reasoning
token usage but no separate native `reasoning` items. This does not prove that the
provider emitted no reasoning. Installed-client synthetic tests separately prove
that emitted reasoning and final answers remain distinct, including literal
`</think>` in answer text. No generated text or reasoning content is retained.

Every Windows combination is **0 / 0 / 3 main sessions and 0 / 0 / 3 Guardian
pairs**, blocked at catalog preflight. Retained reports:
[DeepSeek](evidence/cli-refresh-2026-10-02/windows-blocked/deepseek.json),
[GLM](evidence/cli-refresh-2026-10-02/windows-blocked/glm.json),
[GLM Flash](evidence/cli-refresh-2026-10-02/windows-blocked/glm-flash.json),
[Kimi](evidence/cli-refresh-2026-10-02/windows-blocked/kimi.json),
[Nemotron](evidence/cli-refresh-2026-10-02/windows-blocked/nemotron.json).
They remain Experimental; macOS results cannot supply a Windows Supported badge.

## Harness proof, corrections and limits

Before live inference, the final real-client synthetic fixture passed all five
exact pairs on both platforms: 15 coding sessions and 15 Guardian pairs per
platform. Windows used its existing initialized sandbox via runtime overrides;
config/auth preservation and removal of all 45 owned test sessions were asserted.
The separate installed-client reasoning-separation test passed on both platforms.
Final evidence directories are [macOS](evidence/cli-refresh-2026-10-02/mac-synthetic-final/)
and [Windows](evidence/cli-refresh-2026-10-02/windows-synthetic/synthetic-final/).

[All preparatory attempts](evidence/cli-refresh-2026-10-02/synthetic-attempts.json)
are identified separately. Windows initially hit the old macOS-only harness gate;
a later synthetic assertion wrongly required omitted main reasoning effort even
though Windows's native setting was `medium`. The observer is before the launcher
adapter, whereas the fixture upstream is after it; GLM's removal of `effort=none`
therefore has different observations at these seams. Earlier reports are retained.
The final macOS invocation first failed to save evidence because the operator had
not created the optional output directory; its synthetic-only rerun passed after
that directory was created. Review also corrected native-client provenance:
Windows npm wrappers are explicitly rejected instead of recording Node's hash as
Codex's. No paid attempt was replaced by any of these corrections.

The support boundary remains narrow: one small synthetic coding task and its
continuation, streaming and tool-output checks, exact routing, settings
preservation, and controlled approval proposals. It is not a general coding
quality, security or approval-safety guarantee. The proposal lane does not prove
that each main would naturally request the same action. No direct route, Linux,
Windows live behavior or other architecture is qualified by this comparison.

CLI admission and PTY tests cover the three real promotions, failed mains,
experimental confirmation, Guardian overrides, direct routes and platform
boundaries. [Validation](evidence/cli-refresh-2026-10-02/validation.json) passed: the full Go
race suite, vet, Python checks with required command arguments, and Windows CLI
platform tests. Standards and Spec reviews each reported zero remaining findings.
The race run used `GORACE=atexit_sleep_ms=0` to remove an instrumentation-only
exit delay that also failed the pre-existing desktop shutdown fixture; race
detection stayed enabled and production deadlines were unchanged. No new product defect ticket was opened: the two retained
main failures are bounded qualification outcomes; harness defects were corrected
and tested within #75.
