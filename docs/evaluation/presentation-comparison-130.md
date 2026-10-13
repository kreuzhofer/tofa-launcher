# Post-diagnosis Desktop comparison (#130)

Status: all prerequisites and four preflights pass; four live attempts are
predeclared and have not started. #126/#127 merged in #131; #128/#129 merged in
#132 as `2fd66e4`. Keep naming independent: its original intermittent cause remains
unknown, with diagnostic instrumentation and a bounded successful native check.

## Frozen comparison

The tested implementation is `2fd66e4`, whose tree matches reviewed `8ff0cd3`.
The retained namespace launcher is unchanged (`deb5ac9` Go source), SHA-256
`11d28bf933f5230bc9c06744d98726b51d096504e9e683471f21b9c369fbea1e`.
Desktop is 26.1007.30912 build 20156; bundled engine 0.162.0-alpha.17.2.
Supplied runtime, installed skill and harness hashes are frozen in the
[predeclaration](evidence/presentation-runtime-126-127/comparison-130-predeclaration.json).
No guidance treatment or alternative model is introduced.

| Order | Case | Main model |
| --- | --- | --- |
| 1 | 03: implicit presentation skill discovery | moonshotai/Kimi-K3 |
| 2 | 03: implicit presentation skill discovery | zai-org/GLM-5.3 |
| 3 | 04: explicit installed presentation skill | moonshotai/Kimi-K3 |
| 4 | 04: explicit installed presentation skill | zai-org/GLM-5.3 |

Order was drawn once with SystemRandom separately for each case, before outcomes.
Both draws produced Kimi then GLM; retain that order without redrawing. Each attempt
uses a fresh conversation/workspace, accepted v3 prompt bytes, baseline instructions,
GLM-5.3-Flash Guardian, independent Lightning naming, and the original ceilings:
900 seconds including setup, 80 requests, 8192 output tokens per request. This
comparison budget is distinct from the ten-minute synthetic qualification.

Four network-enabled preflights verified the declared models, Guardian/naming
availability and exact runtime proof; no model inference or Desktop launch occurred.
The operator uses the same declared process environment; each live launch repeats
preflight and compares it with its retained preflight record. Drift fails explicitly.

## Current runtime proof

Fresh native run `manual.cMfarK/runs/b73cce4e34cb46e9b37eab82a127a913` qualified
against the current harness. Independent validation confirmed the actual loader
call/result, executable identities, finalized PPTX/PDF/image, maintainer-observed
native previews and protected-state preservation. The proof hash is
`d44a21842f8cf5d8c7aad31e3d43f578c27bb54622be02b64c048f11c0316b60`.
No paid inference was used. The fresh bundled-CLI synthetic proof passed separately;
it does not establish a native Desktop preview or qualify another CLI executable.
All old proofs, failures and model outcomes remain intact.

## Operator handoff and scoring

Run `bash /tmp/tofa-presentation-validation/run-comparison-130.sh` in an interactive
Terminal. For each attempt, the wizard names the model, starts Desktop, supplies the
fresh workspace and exact prompt, then batches the PPTX/PDF preview checks. Record
the visible title separately without renaming it. Finish after main work and the
observations; do not wait for failed naming. Pending naming can finish only within
the existing attempt deadline. Ctrl-C requests cancellation of the owned attempt.

The wizard retains observations even if the run has already ended. Timestamps and
whether title observation happened after termination remain explicit. A failed,
cancelled or blocked attempt, unfinished response, state drift or unexpected
stopping condition halts the batch for agent inspection. No automatic retry occurs;
remaining scheduled attempts stay pending. Re-running the wizard refuses an
already-started campaign. All private evidence remains beneath
`/tmp/tofa-presentation-validation/runs/comparison-130`.

Content, language, skill discovery/use, native loader execution, artifact integrity
and finalization, reference syntax, human previews, repetition, provider naming and
visible title are scored independently. A transport-completed run or completed
wizard is not a task pass. Preserve aggregate infrastructure failures and incomplete
usage; identify delivered files and hashes during assessment. Original #119 matrix
cells are not replaced by these fresh attempts.

## Verification and next decision

The merged source passed Standards/Spec review (zero findings each) and artifact,
macOS, Linux and Windows CI. The private batch gate was tested red first, then all
four tests passed, covering declared identity/limits, drift, early stops, missing
results and naming failure. Bash syntax passes and the wizard library matches its
skill template byte-for-byte. Shellcheck is unavailable; control/data flow was
inspected statically. The human wizard was not run end-to-end by the agent. Separate prelaunch
Standards and Spec reviews against `2fd66e4` found zero issues in the declaration
and private operator controls, including the public-path sanitization.

After all retained attempts are independently assessed, run the required outcome
review and update #119 with a resume, revise or remain-blocked decision. #130 stays
open until that assessment. Guidance adoption (#120), the wider campaign (#119),
and combined release readiness (#106) remain separate gates.
