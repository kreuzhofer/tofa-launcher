# Native account qualification (#134)

The ordinary signed-in profile is part of the product contract. Tests with an
owned fake application or a real engine in an isolated HOME do not establish
account visibility, plugin eligibility, ordinary Desktop recovery or previews.
Keep #141–#143 and the integration branch pending until those observations exist.
The known direct-engine recovery-guidance gap from #137 is not a passing result.

## Admission boundaries

`--native-account-candidate --evaluation-observer PATH` retains the old plugin
protection unless the private version-2 observer configuration names a matching
`qualification_declaration`. A declaration permits one bounded attempt, not a
qualified installation. The public launcher still checks sign-in, policy,
ordinary profile ownership, bridge ownership, routing conflicts and the unsafe
legacy route. It consumes `start.json` exclusively before admitting the candidate.
The declaration lasts 600 or 900 seconds including setup, limits adapter-visible
requests to 1–80, and cannot be retried. Observer independently checks its limits.

Normal use requires `--native-account-proof PATH`. That explicit private path is
not installed in shared settings. The same executable validates all required
case records and required checks/reviews; a status boolean is insufficient.
There is no periodic expiry for an unchanged qualified installation. Changed
source/binary, Desktop, engine, catalog, harness, plugins, skills or runtime bytes,
missing evidence, or a `revoked.json` sibling fail admission. A declaration
expires; historical evidence of a completed matching case does not.

All evidence lives beneath `/tmp/tofa-presentation-validation`. macOS may display
its canonical `/private/tmp` alias. Evidence descendants must be private owned
directories, with private regular files and no symlink traversal. Preserve failed
attempts. Do not rewrite them to make a later attempt appear successful.

## Freeze and prepare

Run the required Go race suite, vet, offline scripts and platform CI. Complete
independent Standards and Spec reviews against
`a91477481ff5fe4f0823731e35302d3794806660`. Freeze the candidate executable and these
collector scripts before actual Desktop work. Do not rebuild after gathering
qualification evidence and then reuse that evidence for different bytes.

The read-only public collector command is:

```sh
/path/to/frozen/tofa desktop-qualification snapshot \
  --app-bundle /Applications/ChatGPT.app \
  --runtime-root /path/discovered/from/runtime/loader \
  --harness-root /path/to/frozen/scripts \
  --source-revision COMMIT
```

Save stdout as a private `snapshot.json`; it contains paths and hashes, not
credential values. Snapshot reads the configured catalog and files. It does not
launch Desktop or perform model inference. Native catalog descriptors retain
routing/display semantics while cache timestamps are excluded. Full TOML
comparison retains unused profiles, unknown keys, primitive types and disabled
tables. Only exact owned inactive provider tables and the two exact owned MCP
executable references normalize. User extras in an owned table fail ownership.
Broken supplier metadata symlinks are inventoried by target text and missing
state; required runtime executables and package paths must resolve within the
runtime. The collector never repairs the installed runtime.

`desktop_qualification.py prepare` takes the frozen launcher, app, runtime,
source, case, model, a private model-to-service map, and either an exact `--prompt`
or private `--scope` declaration. It produces an immutable plan and before
snapshot. It does not launch Desktop. Then `run RUN` performs the one explicitly
prepared launch. The operator must save/quit unrelated Desktop work beforehand.
There are no retries, model substitutions, profile replacements or credential
writes in this harness.

For scoped #142 runs use `tofa-observer-scope-v1`: exact attempt/root, at most
8 threads/16 turns, each turn with model, service and exact prompt. New threads
are beneath RUN/workspace. Existing threads require their exact thread ID,
workspace and preceding-user-message hash. `$WORKSPACE` in a prepared scope is
replaced with this attempt's workspace before hashing. Observer retains private
scope state for a later independently declared resume. Direct-native title-only
entries admit only the strict automatic-title role; their Main is unobserved.
They do not establish parent-thread provenance.

## Record each outcome

Required cases: clean-exit, repeat-launch, launcher-crash, native-crash,
ordinary-launch, bridge-update, uninstall-reinstall, service-switching,
history-resume, review-routing, launch-naming and runtime-preview.

Use `observe RUN --criterion NAME --operator NAME --method human|computer_use
--outcome passed|failed|not_observed` while the attempt is active. Native preview
observations hash both exact RUN/workspace/output artifacts. Account/plugin/UI
claims must come from the actual UI. Fixtures do not qualify installed plugins.

`finish RUN` and `cancel RUN` are exclusive explicit controls. `launcher-crash RUN`
is accepted only for the declared crash case and only after the collector has
observed the native PID as the launcher's direct child. It kills only that owned
launcher. Native crash, bridge interruption and uninstall/reinstall have an
explicit `external-action` receipt interface: record the already-observed
case-specific action, operator, method and private source files. The command
does not kill native apps or invoke an installer. The source must identify the
owned process/action; do not act on unrelated running work. Finish records do not
claim success. The first Observer stop cause remains authoritative. Final receipts
are written only after owned request handlers drain; every retained request must
be reconciled, including failed naming requests. A normal launcher exit1 qualifies
only for an acknowledged owned evaluation stop while that launcher was still live;
an earlier exit/failure cannot be relabeled by pressing Finish. Declared crashes
have separate exit semantics and retain their action receipts. Expiry/cancellation
stays unqualified. Cancellation or a crash during active inference retains an
incomplete attempt; interrupted Main/review work never becomes successful
transport evidence. An idle lifecycle fault can qualify only with its declared
case-specific action and terminal receipts. The pending-review, cancellation and
late-allow boundaries are tested through the actual bundled engine and Observer;
those fixture checks do not turn an incomplete native attempt into a pass.

The collector captures the registered route's post-stop HTTP rejection or
connection-refused outcomes using its old capabilities, without saving token
values. It retains the owned PID receipt, before/after protected snapshots,
Observer requests and stop receipt. A lifecycle case must link these concrete
receipts. `record RUN --facts PRIVATE_JSON` adds reviewed history, lifecycle,
transport and runtime evidence plus source references; it cannot overwrite
receipts or grant admission. The launcher cross-checks references, request
numbers, role/service/model, raw request thread/turn IDs, review parents,
process identities, stop outcome, timestamps and protected snapshots.

Transport entries preserve `original_model` separately from routed `model`.
In particular, a native Luna title request may route to configured Lightning.
Each required naming success has a distinct context (`routed-native`,
`routed-token-factory`, `existing-native`) and attributed UI source association;
the title protocol does not reliably expose parent IDs. A source-linked naming
failure remains an independent failure entry, never a successful title or a
fallback. Main tool continuations are grouped by thread and turn before checking
Token Factory → native → Token Factory switching.

Existing direct-native histories intentionally bypass the adapter/Observer.
Their requests/tokens and credentials are not covered by Observer counters.
Use attributed native/relay inspection with exact attempt, model, thread/turn,
operator and source references, and the owned launch deadline. Routed native
requests are observed, but native requests lacking `max_output_tokens` have
usage-observed accounting, not a claimed hard upstream token cap. Credential
separation for observed routes is the reviewed adapter contract plus linked
request/service evidence; no collector reads or publishes provider secrets.

## Runtime preview case and final admission

Use the existing `presentation_calibration.py` with `--client desktop
--production-launcher --native-account-snapshot PRIVATE_SNAPSHOT` and its normal
runtime/skill/launcher arguments. This creates a runtime-preview declaration,
uses version-2 launch authorization and the production launcher, and retains the
same actual loader-call, supplied-version, first-party smoke, finalization,
artifact and native-preview checks. The smoke creates only its own new build/output directories with private permissions,
inherits a restrictive umask into supplied tools, and privatizes generated files
before artifact observation/hashing; installed dependencies are never chmodded.
The transport is synthetic and makes no paid
model requests. Its result cannot prove model quality or live service routing.
The normal qualification collector can assemble its before/after/process/finish
receipts and retained runtime evidence into that case record.

The final `tofa-native-account-proof-v1` index contains the exact identity,
relative hashed references to all twelve `tofa-native-account-case-v1` records,
and one `tofa-native-account-checks-v1` record. Checks require `go-race`, `go-vet`,
`script-regressions`, `platform-ci` and the two independent review reports with
zero unresolved findings. Runtime evidence independently links actual advertised
loader call/result, supplied executable versions/hashes, first-party finalization,
smoke marker, exact owned PPTX/PDF/PNG hashes and UI preview observations.

Verify with the same frozen executable using `desktop-qualification verify`
(the snapshot identity arguments plus `--proof PATH`). A passing offline verifier
means the submitted linked evidence satisfies this contract; it is not a new UI
observation. Owner-local attribution prevents accidental source/attempt reuse,
not a malicious author forging their own machine. Publish only the sanitized
per-case exports and reviewed evidence summaries; raw traces stay private.
