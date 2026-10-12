# Capability method requalification (#123)

This work follows [#118](https://github.com/kreuzhofer/tofa-launcher/issues/118)
and repairs method gaps found in [#119](https://github.com/kreuzhofer/tofa-launcher/issues/119).
Method `capability-evaluation-v2` retains the report schema, fresh-task scope,
request limits, native execution policy, model identity and independent naming.
The launcher and production guidance are unchanged. The v3 corpus and historical
scores remain immutable; new results have new harness hashes and method identity.

## Scoring and diagnostics

The old scorer rejected a completed GLM Desktop handoff whose absolute Markdown
destinations encoded the space in `Application Support` as `%20`. Both intended
fixture previews opened, as recorded in
[#123's evidence comment](https://github.com/kreuzhofer/tofa-launcher/issues/123#issuecomment-6125817787).
The command regression reproduces that false negative. The new scorer compares
literal or once-decoded UTF-8 destinations with the exact expected paths. Other
workspaces and malformed encodings receive no credit. The scorer does not infer
preview success or change artifact integrity scores.

Authenticated rejected requests now record a categorical rejection cause and
bounded shapes: known field types, model-role matches, input types/roles, tool
types and review-format checks. Unknown names and all text/metadata values stay
out of exports. Up to 64 input/tool entries are summarized. The bounded received
body is saved privately as `rejected-request-N.json`, mode 0600, before the error
response; malformed JSON is retained as bytes with an unavailable parsed shape.
Unread bodies and unsupported encodings report unavailable capture. Headers,
registration credentials and unauthenticated bodies are never captured this way.
Unknown contracts still stop without forwarding inference.

Protected-settings preservation remains a strict gate. New results identify
changed file categories and before/after configuration hashes. Credential-file
fingerprints are comparison-only and never exported. The evaluator never restores
a snapshot over a concurrent edit. The original two zero-request launches lost
their private configuration evidence after reboot, so their precise edits and
origin remain unknown. Their old blocks cannot be retrospectively waived.
The older Kimi deck rejection also lacks its original raw request; the native
review diagnosis below does not establish that earlier rejection's cause.

## Installed-client regression classification

The checks use isolated temporary homes, fake Desktop bundles and synthetic
loopback responses. No real Desktop UI or paid inference is used.

| Check | Finding | Disposition |
| --- | --- | --- |
| CLI tool execution and continuation, 0.162.1 | Coding instructions arrive in developer input messages. | Fixture accepts the trusted developer location as well as legacy top-level instructions; tool execution and continuation pass. |
| Bridge partial-copy cleanup | The child-only file-size limit interfered with the Python/Xcode fixture's version-probe startup before copying. | A shell-only version fixture reaches the intended real filesystem copy failure and verifies cleanup. Production version checking is retained. |
| Bundled-engine automatic approval, 0.162.0-alpha.17.2 | Native review has the expected assessment schema and three inspection tools, but `instructions: null` and policy in developer messages. | Current adapter requires top-level instructions, rejects before upstream, and native execution fails closed. This remains an infrastructure/contract block. |
| Bundled-engine resume regression, same engine | Its initial Kimi Guardian turn has the same instruction-location mismatch. | Initial execution is not approved; the test stops before its second launch/resume. No Guardian inference is forwarded, and resume approval remains unqualified. |

The [sanitized structural replay](../../scripts/fixtures/current-desktop-review-shape.json)
retains roles, schema and tool identities with synthetic text and no native IDs.
An actual HTTP-boundary test classifies it as `unsupported_request_contract /
guardian`. It does not make the installed approval/resume tests pass, substitute
a reviewer, or certify allow/deny behavior. Those opt-in checks remain red for
this engine. Resolving the production review contract requires separate runtime
work; it cannot be hidden by relaxing these fixtures.

The held-out incident workflow is separately versioned and bounded. Its exact
prompt, CSV checksum, output paths and independent rubric are documented in
[the evaluator guide](capabilities.md). It does not reuse case 05's identity.

## Qualification boundary

The [verification record](evidence/capability-method-123/validation.json),
[retained calibrations](evidence/capability-method-123/calibrations.json) and
[independent reviews](evidence/capability-method-123/review.md) describe the checks
and their limits. Passing
synthetic checks qualifies observation and supervision only. A retained installed
CLI calibration uses synthetic credentials and provider responses with the
ordinary persistent skills/settings preserved. Desktop preview calibration is
an asynchronous operator step: the human starts the bounded launch when ready,
selects its freshly printed workspace, submits the exact prompt, waits for naming,
and opens both references. A completed backend naming request does not establish
visible title success. No production guidance adoption, campaign completion,
release or Supported-model promotion follows from these method checks.
