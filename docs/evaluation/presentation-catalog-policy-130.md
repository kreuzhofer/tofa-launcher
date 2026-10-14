# Selected-model catalog policy for #130

Status: evaluator correction reviewed; fresh native qualification and all four
selected-model preflights passed. The amended handoff is predeclared; live model
outcomes remain pending.

## Reproduced failure

Two preparations stopped before native launch or inference, with zero requests:
`57a57646fd1a41059d0f8261743310ae` and
`aa3542fc2efc43efaa12d568601aa896`. Their only provenance difference from their
respective preflights was `catalog_sha256`. The catalog changed from
`09bd7a5557b9a09bcf7aa7f5185605d17f73eff1d1f95015e610919d836a66ad`
to `807ac0c4ae71a6187832423bc2ca4b975a40b8f4b5ec661da6a3bee728bbfc4f`
and back. Adding only `Qwen/Qwen3.5-397B-A17B` to the smaller captured ID list
reproduces the larger fingerprint exactly. No selected model ID changed.
Refreshing the full-catalog anchor therefore did not provide a durable handoff.

## Explicit correction

The evaluator now accepts `--catalog-policy selected-models` on both `preflight`
and `run`. The default remains `exact`, including for old anchors that have no
policy field. A comparison rejects different policies between its anchor and run.

Under the selected-model policy, every preflight still requires the chosen main,
Guardian and, on Desktop, Lightning naming model to be available. Missing roles
block launch. Full catalog fingerprints remain recorded; changes are retained as
`catalog_change` with before/after hashes and the explicit policy, rather than
blocking solely because an unrelated ID changed. Runtime, skill, settings,
executable, harness and other provenance comparisons remain strict. The launcher,
provider routing, approval enforcement, model choices and request budgets are
unchanged. No fallback, automatic retry or model substitution is introduced.

#130 will use this explicit policy for its two main models with the already
declared Guardian and naming model. The prior strict-policy declarations and all
failed runs remain historical, without rewriting their outcomes. New anchors and
private control hashes will be published before execution. The original four
model cells and their order remain unchanged; zero-request preparations do not
count as new model outcomes.

## Verification and remaining gate

Tests exercise the accepted evaluator command and executable boundary. The new
behavior first failed because the policy was unavailable, then passed for an
unrelated catalog addition through both preflight and a synthetic live handoff.
Coverage also verifies each missing Desktop role blocks before launch, local
settings drift still blocks, policy changes block, and default/legacy anchors
retain exact-catalog rejection. Malformed comparison controls are rejected
explicitly. All 25 evaluator tests pass. The 86 related observer, runtime, preview,
synthetic transport, operator, preservation and adapter tests also pass, with two
installed-runtime tests skipped because their explicit opt-in variables were unset.
Standards and Spec reviews of `4e406b3...32b31e8` each reported zero findings.
The final evaluator rerun also passed all 25 tests. Current native assets pass
read-only validation; the old comparison command now stops with concise
qualification instructions, and its previous bytes remain archived privately.

Changing the evaluator changes its recorded harness hash. Existing runtime proofs
are preserved as historical and must not be rewritten or silently rebound. The
next native synthetic qualification must use the corrected harness, record human
PPTX/PDF previews and demonstrate protected-state preservation. Only then can the
selected-model preflights and comparison handoff be published. No release or
model-support promotion follows from the correction.

## Fresh qualification and amended handoff

Native synthetic run `23f05e423df947979218d92a49d96352` passed independent
qualification against the corrected harness. The actual loader call/result,
executable identities, generated artifacts and maintainer-observed PPTX/PDF native
previews validated; protected settings were preserved. No paid inference was used.
The proof and original operator record remain at their original private location.

The [amended declaration](evidence/presentation-runtime-126-127/comparison-130-selected-models.json)
binds this fresh proof and four ready preflights to `selected-models` on both
preflight and live commands. It retains the original order: implicit Kimi,
implicit GLM, explicit Kimi, explicit GLM; original prompts, baseline instructions,
Guardian, naming model and 900-second/80-request/8192-token ceilings are unchanged.
This is the already authorized retry of original attempt 1 plus the three pending
cells. The two zero-request catalog stops remain retained.

The stable operator command remains
`bash /tmp/tofa-presentation-validation/run-comparison-130-retry-1.sh`.
Its new private run directory stays below the agreed temporary root. Declaration
and anchor verification, four unchanged campaign gate tests, bash syntax and a
byte-identical wizard library check pass. Shellcheck is unavailable. The wizard
has not been run end-to-end because its native UI steps require the maintainer.
No live model outcome or release qualification is claimed.

Standards and Spec reviews of `8dfb45e...491a643` and the bound private controls
each report zero findings. The reviewed handoff is ready for human execution.
