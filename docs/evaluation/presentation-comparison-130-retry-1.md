# Desktop comparison retry amendment (#130)

Current status: a second catalog-only preparation stopped before launch. The
[selected-model policy correction](presentation-catalog-policy-130.md) supersedes
the handoff below and awaits fresh native qualification. Do not rerun these
historical strict-catalog anchors.

The maintainer explicitly requested a retry after original attempt 1 stopped.
This amendment retains that result and declares one retry of case 03 Kimi,
followed by the three original pending attempts: case 03 GLM, case 04 Kimi,
case 04 GLM. The recorded order is unchanged. No live retry has started.

## Catalog-only prelaunch stop and refresh

Launch preparation `57a57646fd1a41059d0f8261743310ae` stopped before Desktop
launch or inference: zero requests, `environment_drift`, with only
`catalog_sha256` different. The provider catalog removed
`Qwen/Qwen3.5-397B-A17B`. Adding that single ID to the current sorted catalog
reproduces the old fingerprint exactly. Both main models, Guardian and naming
remain available; all other recorded provenance fields are identical.

Four refreshed preflights pass. The existing native qualification remains valid;
no new manual runtime check is required. The
[catalog refresh evidence](evidence/presentation-runtime-126-127/comparison-130-catalog-refresh-1.json)
is now authoritative for preflight and control hashes. Prior declaration evidence
is historical and unchanged. Whole-catalog drift checks remain enabled, with no
allowlist, substitution, automatic refresh or automatic retry at launch.

The operator command below is unchanged. Its new evidence subdirectory is
`runs/comparison-130-retry-1/catalog-refresh-1`, beneath the same fixed root.
The stopped preparation and former script bytes are retained. The four declared
model attempts are still pending; this refresh does not add a paid model attempt.

## Why the declaration changed

Original run `64e1f32f1e1245e0857a755f93fca9b5` stopped after 107.7 seconds with
`presentation_runtime_environment_drift`, aggregate status `infra_blocked`.
Its qualified runtime was 26.1011.11113 / artifact-tool 2.8.93; the installed
runtime changed to 26.1013.11914 / 2.8.94. Revalidation failed with
`loader_bundle_version_mismatch`. The updater's identity is not established.
Protected settings were preserved. Kimi read the presentation skill and called
the loader successfully before the stop. Seven main responses and one naming
response completed; no main final answer or artifacts were delivered. Naming
returned HTTP 200, but no human title or preview observation was saved.
This is an infrastructure stop, not a model-quality verdict.

The next synthetic qualification (`8895c20489214774ae5d43897a7ab3b1`) failed
because its old versioned skill directory disappeared before the smoke subprocess.
That run also had differing protected inventory hashes; it does not establish
preservation. The private manual wrapper now selects the skill matching the
installed runtime manifest and fails explicitly if absent. Launcher source,
installed skills and settings were not edited. Three selection tests passed after
the red phase, and the local artifact smoke created PPTX, PDF and PNG successfully.

Fresh native run `9be2064b304c472cb2f5f7882753c105` then qualified on
26.1013.11914 / 2.8.94. Independent proof validation passed, with actual loader
execution, finalized artifacts, human native previews and protected state preserved.
Four refreshed preflights are ready; no inference occurred in those preflights.
Exact hashes and controls are in the
[amended evidence](evidence/presentation-runtime-126-127/comparison-130-retry-1.json).
All previous proofs and failures remain unchanged.

## Controls and handoff

Implementation remains `2fd66e4`, launcher SHA-256
`11d28bf933f5230bc9c06744d98726b51d096504e9e683471f21b9c369fbea1e`.
Desktop/engine and harness are unchanged. Only the supplied runtime, installed
skill inventory, qualification and preflight anchors are refreshed. Prompts remain
accepted v3 cases 03/04, baseline instructions, fixed GLM-5.3-Flash Guardian and
independent Lightning naming. Each attempt uses a fresh workspace/conversation and
900 seconds including setup, 80 requests, 8192 output tokens per request.

Run `bash /tmp/tofa-presentation-validation/run-comparison-130-retry-1.sh`.
Evidence stays under the fixed root, within `runs/comparison-130-retry-1`; the original
`runs/comparison-130` is retained. Preview/title observations remain separate.
The existing gate stops on infrastructure or state drift, incomplete requests,
failed naming or unexpected termination. No automatic retries or substitutions.
A second invocation refuses an already-started retry campaign.

The gate logic is unchanged and its four tests pass; Bash syntax and declaration
hash checks pass. The wizard library is unchanged. No human workflow was run
end-to-end by the agent. Prelaunch Standards and Spec reviews against `25aa775` each found zero issues;
results are recorded in the evidence.
After the live attempts, independent scoring and outcome review remain required.
#130/#119 remain open; no model-support or release promotion follows from this check.
