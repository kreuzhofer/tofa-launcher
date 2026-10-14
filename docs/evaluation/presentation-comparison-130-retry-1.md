# Desktop comparison retry amendment (#130)

The maintainer explicitly requested a retry after original attempt 1 stopped.
This amendment retains that result and declares one retry of case 03 Kimi,
followed by the three original pending attempts: case 03 GLM, case 04 Kimi,
case 04 GLM. The recorded order is unchanged. No live retry has started.

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
Evidence stays under the fixed root, in `runs/comparison-130-retry-1`; the original
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
