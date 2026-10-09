# rc16 stream failure diagnosis (#110)

**Latest result:** the bounded envelope fix passes live streaming. It exposed a
second defect: Codex 0.160.1 replays reasoning items without the ID required by
Token Factory. A narrow adapter repair now passes the local-build two-turn coding
and Guardian allow/deny sample. This changes product bytes: rc16 remains failed,
and a new shared candidate needs Mac and Windows qualification. See the
[follow-up evidence](#retained-login-follow-up-and-local-fix) below.

The following sections retain the earlier diagnostic history and its original
authorization limits. The maintainer subsequently authorized continued work,
removed the usage cap, and instructed us to retain and reuse the Windows login.

The authorized one-request diagnostic **reproduced an oversized initial event**
declared as `response.created`. Its data line crossed the observer's 256 KiB
event bound before JSON parsing. CR-only framing did not occur in this attempt.
The contents and final size of that event remain unknown; request metadata being
echoed is a hypothesis, not a measured fact. One upstream inference request ran
in this diagnosis, without retry, and its isolated login was removed.
[#110](https://github.com/kreuzhofer/tofa-launcher/issues/110) and Windows
qualification #105 remain open; the original failed evidence is unchanged.

## Evidence and offline reproduction

The [original attempt](../releases/v0.1.0-rc.16-windows.md) received HTTP 200,
then failed before observing a text/tool delta or completed response. The
retained report has no event size/type or delimiter counts. It cannot identify
the original payload or framing retrospectively.

The [offline probe](evidence/issue110-stream-probe.py) sends synthetic HTTP/SSE
responses through the real `EvaluationProxy`; it uses neither credentials nor
paid inference. Run from the repository root:

```powershell
python docs/testing/evidence/issue110-stream-probe.py
```

At revision `9538008`, this is a deliberately red diagnostic probe, not a passing regression test.
It exits 1 because two separately bounded CR-only events are rejected. Repeated
runs produced the same result in under four seconds. The
[recorded matrix](evidence/issue110-framing-2026-10-09.json) shows:

| Input | Largest event | Result |
| --- | ---: | --- |
| Two events, LF separators | 150,073 bytes | Completed |
| Two events, CRLF separators, fragmented writes | 150,075 bytes | Completed |
| Same two events, CR-only separators | 150,073 bytes | `event_body_limit`, no parsed text/tool deltas |
| One oversized event, LF separators | 263,073 bytes | `event_body_limit`, no parsed text/tool deltas |

The [SSE standard](https://html.spec.whatwg.org/multipage/server-sent-events.html#parsing-an-event-stream)
allows CR, LF and CRLF line endings. The observer splits only at LF. CR-only
events therefore accumulate into one pending line and cross its 256 KiB bound.
This is a demonstrated observer defect, **not proof of the live failure's cause**.
The framing parser has intentionally not been changed during this diagnostic
step, preserving the original failure path for measurement.

## Bounded observability

The observer now records a fixed-size set of numeric/categorical diagnostics:
forwarded request bytes, received response bytes, CR/LF counts, processed and
blank line counts, parsed JSON-line count, event/pending-line bytes at stop,
categorized content type/encoding, last parsed event type, and an initial event
type hint. Unknown header/type values become fixed categories. A maximum
1,024-byte in-memory prefix can supply the hint; the prefix is never exported,
and a hint does not assert valid framing or a fully parsed event.

No payload, prompt, credential, raw unknown event/header string, or exception
text is added to reports. The existing request, response, event, output, deadline
and request-count limits are unchanged. Oversized JSON is still rejected before
parsing. No launcher/product bytes changed.

The checks distinguish these hypotheses without asserting one is established:

1. One oversized initial event: bytes accumulate within one event, with a type
   hint where available.
2. Missing separators: complete lines accumulate without blank event boundaries.
3. CR-only framing: CR counts grow while LF/processed-line counts remain zero.
4. An unexpected response format: header categories and framing counters differ
   from SSE expectations.

## Validation before the live diagnostic

The two existing oversized-event HTTP tests were first extended to require
diagnostics and failed with `KeyError: stream_diagnostics`. After implementation,
all **17 observer tests passed**, including fixed-label redaction, privacy,
limits, deadlines and cancellation. The explicitly selected native Codex 0.160.1
loopback coding/Guardian [fixture](evidence/issue110-native-loopback-2026-10-09.json)
passed in 27.7 seconds, with native config/auth
preserved and its three owned sessions removed. Full `go test ./...`, `go vet
./...` and Python syntax checks also passed. These are offline/synthetic checks.

A separate interactive diagnostic used the unchanged
published rc16 executable, explicit Codex 0.160.1, and this instrumented observer.
It permitted **one** upstream inference request, 4096 output tokens, a 180-second
coding deadline, the unchanged 1 MiB request/256 KiB event/8 MiB response bounds,
and no Guardian campaign or automatic paid retry. It used a new isolated local
login and purged only that login afterward. Its report records the observer's
SHA-256, so it cannot be mistaken for the original pinned qualification runner.

## Authorized live diagnostic result

The maintainer authorized the diagnostic and entered credentials locally.
The [unaltered sanitized report](evidence/issue110-diagnostic-01-2026-10-09.json)
records one upstream inference request and the same `event_body_limit` failure.
The coding turn ended after 4.72 seconds without executing a tool or producing
the expected output file. No Guardian check, continuation campaign, retry or
model substitution ran.

| Measurement | Result |
| --- | ---: |
| Forwarded request bytes | 390,852 |
| Received response bytes before stopping | 265,679 |
| Content type | `text/event-stream` |
| Content encoding header | Empty |
| CR bytes | 0 |
| LF bytes / processed lines | 1 / 1 |
| Blank lines / parsed JSON lines | 0 / 0 |
| Initial event type hint | `response.created` |
| Processed event bytes | 24 |
| Pending data-line bytes at stop | 265,655 |
| Event limit | 262,144 |

These counters locate the reproduced failure: the initial event declaration
was read, but its following data line exceeded the bound before completing.
They rule out CR-only framing and accumulation of multiple completed JSON lines
for this attempt. The declared type is a bounded hint from the stream prefix,
not a parsed oversized JSON object. The complete event size and contents were
not captured, so neither echoed request fields nor any particular provider
payload field is established as the source of the size. The original rc16
report remains unchanged and lacks these counters; the diagnostic reproduces
its symptom but cannot retroactively prove identical contents.

The observer SHA-256 was
`9d963a03963388458e601c0245fe0370ddca1b4891b66556a8b938dcab219c6e`,
matching the reviewed source at `a0c6857`. Limits and product bytes were unchanged.
The report's `passed: false` is the failed coding result, not a cleanup failure.
All five cleanup checks passed: isolated config/file credentials/vault credential
removed, ordinary user and machine PATH preserved. Native config/auth preservation,
removal of the one owned native session, and scratch removal also passed.
Usage and cost are unknown because no completed usage was returned. Across the
original qualification and this diagnostic, two upstream requests have run.

## Next step

The new HTTP-seam test
`ProxyTests.test_large_created_event_reproduces_the_diagnostic_pending_line_failure`
reproduces the measured signature offline in about one second: a 24-byte
`event: response.created` header followed by one large data line, LF framing,
no parsed JSON or blank line, and rejection at the unchanged event limit. It
uses synthetic contents and does not assert those contents match the live event.
After adding this reproduction, the full observer suite passed: **18 tests in
69.7 seconds**. No production code or resource limit changed in this follow-up.

Next, decide how the observer should handle such an
event while retaining explicit finite resource bounds and privacy; do not change
the limit merely to produce a passing qualification. The separate CR-only parser
defect remains real but is not the cause demonstrated by this diagnostic.

No fix or release acceptance is claimed. Any resulting change needs tests and
renewed affected qualification before #105 can pass. Another paid attempt is a
separate step; this diagnostic's one-request authorization has been consumed.

## Review

The pre-diagnostic independent reviews compared `e368efa` with diagnostic commit
`a990819`; they did not review or execute the later live attempt.

### Standards

No blocking findings, ADR conflicts or actionable code-smell concerns. The
diagnostic additions preserve limits and export only fixed categories/counters;
HTTP tests cover size enforcement and redaction. The ignored one-request
controller was also inspected for isolated login and owned cleanup boundaries.

### Spec

No blocking implementation mismatch. #110 remains partial: the original live
cause is unconfirmed, and no fix or renewed actual-candidate lifecycle is claimed.
The prepared diagnostic caps the budget at one, uses the actual rc16 artifact,
and includes scoped credential purge and preservation checks. Reviewers did not
execute inference or repeat the tests.

Review findings: Standards 0; Spec 0. Issue-level diagnosis and acceptance remain incomplete.

## Retained-login follow-up and local fix

The maintainer entered a login once into the normal Windows profile and requested
reuse without purging it. Each follow-up verified that the saved vault credential,
ordinary tofa files and native Codex config/auth remained unchanged. No credential
values, project identifiers, conversation text or tool arguments are in the reports.
The sample explicitly uses `--no-request-limit`; the default remains 12 for callers
that do not opt in. Request counts are still recorded. The 4096-token output bound,
1 MiB request bound, 8 MiB response bound and finite deadlines remain operational
limits, not a user usage budget.

The observer now distinguishes ordinary events (256 KiB) from the fixed set of
response-envelope events (at most 1 MiB + 256 KiB). Oversized envelopes must parse
as the hinted event type, preserve the selected model, and contain at most 256 KiB
of serialized output. The ordinary delta/tool-event bound and total response bound
still apply. This follows the distinction between an event delta and an envelope
carrying a response object in the [Responses streaming contract](https://developers.openai.com/api/reference/resources/responses/streaming-events).
No claim is made about the unknown original payload's exact contents. The unrelated
CR-only parser limitation is unchanged.

Four attempts used the unchanged published rc16 ARM64 executable and Codex 0.160.1,
with the modified observer. Their reports record runner hashes and baseline
`9538008`; they are not runs of the original pinned qualifier.

| Retained report | Upstream requests | Measured result |
| --- | ---: | --- |
| [01](evidence/issue110-retained-01-2026-10-09.json) | 2 | Initial response completed with three large envelopes; continuation HTTP 422 initially mislabeled by the observer's event bound |
| [02](evidence/issue110-retained-02-2026-10-09.json) | 2 | Same failure; bounded JSON-error diagnostics correctly report HTTP 422 |
| [03](evidence/issue110-retained-03-2026-10-09.json) | 2 | Input-shape metadata identifies a reasoning item without an ID |
| [04](evidence/issue110-retained-04-2026-10-09.json) | 3 | Continuation without reasoning accepted; next continuation rejected at `ResponseReasoningItem.id` for input item 6 |

All four install/repeat-install/fresh-terminal checks passed. All failed live samples
stopped before Guardian and reinstall acceptance; failure cleanup removed only the
owned test installation and PATH entry, preserving the login. All recorded cleanup
and native-state preservation checks passed. No failed report was overwritten.

The provider's [public OpenAPI schema](https://api.tokenfactory.nebius.com/openapi.json)
requires `id`, `summary` and `type` on `ResponseReasoningItem`. Attempt 04 records
`summary` as an array, `type` as reasoning, and the provider's exact fixed-category
missing-ID error. These observations distinguish the defect from assistant-message
normalization and tool-call formatting. The regression
`TestAdaptedLaunchRepairsMissingReasoningID` reproduced HTTP 422 through the real
adapter before the fix. The adapter now supplies a deterministic ID only when a
reasoning item has an array summary and no supplied ID. Retries retain the same ID;
repeated items have distinct IDs. Supplied IDs (including null), reasoning content,
encrypted fields and unrelated history stay intact.

The [local diagnostic build](evidence/issue110-local-fix-01-2026-10-09.json), SHA-256
`1d323d7c0bfb01741e66a8e2731bb94e730c2d172830d88ffffd22715f3beb1b`,
passed both coding turns in one native session (four and two successful tools),
then Guardian allow executed the marker and Guardian deny prevented execution.
All 12 upstream responses completed. Native config/auth were preserved, all three
owned sessions were removed, and the saved Windows login remained intact. This is
live local-fix evidence, **not published-candidate or installation acceptance**.

Validation: the new missing-ID test failed before repair and passed afterward;
`go test ./...` and `go vet ./...` passed. The full affected Python suite passed
**70 tests in 86.7 seconds, with three optional tests skipped**. The selected native
loopback fixture had also passed after the envelope repair, before the later
diagnostic metadata additions. Actual native live checks above cover the final
adapter repair. Source hashes in each report identify exactly what it measured.

The Mac coordinator can take the reviewed commit, publish a new immutable shared
candidate, and collect renewed affected Mac and Windows evidence. #105/#106/#110
remain open until the required candidate acceptance is complete. Stable release,
model promotion (#75), Windows desktop ownership, and the separate managed-daemon
sandbox recurrence (#108) are not established by these results.

## Follow-up review

Independent reviews covered the final uncommitted task diff against `9538008`
and all five follow-up evidence files. They did not rerun tests or paid inference.

### Standards

Zero hard violations and zero actionable code-smell findings. The reasoning-ID
repair preserves supplied IDs and unrelated fields; diagnostics remain bounded
and redact values. No ADR conflict was found. Credential reuse follows the
maintainer's explicit instruction.

### Spec

Zero implementation or evidence-identity findings. The remaining acceptance gate
is explicit: publish a new shared candidate and qualify the exact artifacts on
both platforms. The successful local diagnostic cannot close #105/#106/#110.

Review findings: Standards 0; Spec 0 implementation findings, with candidate
acceptance still incomplete.
