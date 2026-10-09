# rc16 stream failure diagnosis (#110)

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

This is a deliberately red diagnostic probe, not a passing regression test.
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
