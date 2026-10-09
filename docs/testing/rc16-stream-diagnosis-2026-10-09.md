# rc16 stream failure diagnosis (#110)

The cause of the original rc16 Windows live failure remains **unconfirmed**.
An offline probe demonstrates a separate observer framing defect that produces
the same `event_body_limit` category, and bounded diagnostics are now tested
for distinguishing the causes. No new paid inference has run in this diagnosis.
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

## Validation and next step

The two existing oversized-event HTTP tests were first extended to require
diagnostics and failed with `KeyError: stream_diagnostics`. After implementation,
all **17 observer tests passed**, including fixed-label redaction, privacy,
limits, deadlines and cancellation. The explicitly selected native Codex 0.160.1
loopback coding/Guardian fixture passed in 27.7 seconds, with native config/auth
preserved and its three owned sessions removed. Full `go test ./...`, `go vet
./...` and Python syntax checks also passed. These are offline/synthetic checks.

A separate interactive diagnostic is prepared locally with the unchanged
published rc16 executable, explicit Codex 0.160.1, and this instrumented observer.
It permits **one** upstream inference request, 4096 output tokens, a 180-second
coding deadline, the unchanged 1 MiB request/256 KiB event/8 MiB response bounds,
and no Guardian campaign or automatic paid retry. It uses a new isolated local
login and purges only that login afterward. Its report records the observer's
SHA-256, so it cannot be mistaken for the original pinned qualification runner.

The maintainer has been asked to enter credentials locally again for that
one-request diagnostic. The previous test login was correctly purged. No new
login or live request has started at the time of this report. A diagnostic
result will not qualify the release; any resulting fix needs regression tests
and renewed affected qualification before #105 can pass.
