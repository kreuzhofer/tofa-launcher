# Presentation runtime qualification for the Mac pilot

Issue [#122](https://github.com/kreuzhofer/tofa-launcher/issues/122) implements its
explicit-block outcome. Cases 03/04 now report
`infra_blocked / presentation_runtime_unqualified` before client launch on both
CLI and Desktop. No qualified client path supplies the installed presentation
skill's required runtime, so these cases cannot spend inference tokens or search
for substitute installations. The original campaign attempts remain unchanged.

## Observed contract

Installed presentations 26.1011.11113 requires calling
`load_workspace_dependencies` and using the returned Node executable, packages,
override binaries and Python executable. It prohibits substitute installation or
modification of bundled dependencies. Its implementation SHA-256 remains
`45a8c01663a4b1dad6e80e1112223b8a19529b32be5f46a47a2dbc058806f55d`,
matching the retained #119 source. Exact skill, implementation, resource and
location hashes are in the [assessment](evidence/capability-runtime-122/assessment.json).

The installed package's helper requires `RUNTIME_NODE_MODULES` or
`CODEX_PRIMARY_RUNTIME_NODE_MODULES`; it does not supply the required loader.
Current CLI 0.162.1 does not advertise the exact callable loader in its observed
request inventory. This establishes a missing instructed client path, not the
physical absence of every possible presentation runtime. No loader result exists
in this evidence, so supplied executable/package versions remain unobserved.
Ordinary Python and Node versions are inventoried separately and do not qualify
the supplied runtime.

## Enforced boundary

Preflight inventories the installed skill and its implementation requirement,
records `presentation-runtime-v1` provenance and blocks before starting the
client. Missing or changed guidance cannot silently establish a qualified path.
`--live`, instruction variants, inventory roots, available models and Node on PATH
cannot bypass this qualification block. Comparison includes runtime provenance
and retains environment drift explicitly.

The authenticated request observer also rejects any deck inference request.
For a valid main request, it records whether the exact callable loader occurs in
top-level or embedded tool inventories, including namespaces. A namespace name
alone is not a callable loader. Absence yields
`presentation_runtime_tool_missing`; advertised presence remains
`presentation_runtime_unqualified`. Advertising a tool does not demonstrate its
returned runtime, rendering, export or preservation contract. Auxiliary naming
also remains blocked before runtime qualification; its inventory does not stand
in for the main's inventory.

Rejected requests retain private raw bytes with existing authentication and
capture bounds. Exports retain the classified role, ordered instruction and tool
hashes, bounded shape and categorical runtime assessment. Runtime blocks are
infrastructure outcomes, not model task failures. No new bypass option, provider
route, approval policy or substitute library is introduced.

## Retained current-client calibration

After 45 passing synthetic command/request-boundary checks, a separate
[installed-CLI diagnostic](evidence/capability-runtime-122/cli-runtime-calibration.json)
used the unchanged v3 case-03 prompt, persistent installed skills/settings and a
synthetic loopback provider with synthetic launcher credentials. It is excluded
from the original matrix and fresh campaign attempts.

The command blocked without client launch. A separately bounded native request
diagnostic then inspected the actual CLI's initial request: the loader was absent,
one main request was rejected, zero inference requests reached the provider, no
workspace artifact or installation proposal was produced, protected settings
were preserved and no environment drift occurred. The diagnostic used the
existing 180-second launcher observer contract, one request and 8192 output
tokens, with a 35-second native-process supervisor. Raw requests and client logs
remain private. It does not test the named model's presentation quality.

An earlier [setup attempt](evidence/capability-runtime-122/cli-runtime-setup-block.json)
used an unsupported 30-second observer contract and stopped before any client
request. That evidence remains intact; the correction reused the launcher's
existing contract. A missing scripts import path in the initial test invocation
also failed before an attempt was allocated. Neither is relabelled as model
behavior or replaced by the completed diagnostic.

Task content, model-driven skill discovery/use, language, artifact validity and
visible previews remain unrun. Installed skill discovery is not a skill-use pass.
No Desktop UI or Windows session was operated, and a CLI request does not establish
the Desktop renderer's tool inventory. Desktop deck attempts remain blocked by
unqualified runtime provenance, with UI observations pending independently.

## Remaining prerequisite

Before enabling fresh 03/04 deck inference, qualify a client/host integration that
exposes the instructed loader and records exact returned executable/package
provenance. Demonstrate the installed presentation workflow through its real
client, no substitute installation, preserved settings and independent task,
skill, artifact and UI judgments. A changed runtime environment requires a named
new attempt rather than rewriting an old infrastructure block.

The [validation record](evidence/capability-runtime-122/validation.json) and
[independent reviews](evidence/capability-runtime-122/review.md) record checks and
limits. #119 remains incomplete. Native Guardian approval/resume, repeated
delivery comparisons, held-out model execution and guidance adoption remain
separate gates. No Supported-model or release promotion follows from this block.
