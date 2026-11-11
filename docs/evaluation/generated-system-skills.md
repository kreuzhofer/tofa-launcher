# Verified native-generated system-skill refreshes

ADR 0007 allows identified, contract-checked native refreshes without treating
all generated paths as unprotected. The #142 attempt stopped before registration
when the shared system skills changed between snapshot and launch. The complete
after inventory matched isolated initialization of another installed Codex daemon;
the Desktop engine generated the before version. This identifies the generated
content, not the historical writer. The original refusal and receipts stay intact.

Qualification can opt into a private `tofa-generated-system-skills-v1` contract.
`scripts/system_skills_contract.py --engine ABSOLUTE_PATH [--engine ABSOLUTE_PATH]
--output NEW_FILE` captures one to four explicitly selected installed engines.
Each receives an isolated temporary HOME/CODEX_HOME under the established `/tmp`
root, file-only absent credentials, and only `--version` and app-server
initialization. It runs no turn and does not launch Desktop or edit shared state.
It records canonical executable paths, executable digests, reported versions and
all regular-file digests under the generated `.system` tree. Engine mutation,
symlinks, missing markers and failed initialization are refused. No versions are
hard-coded or silently substituted.

The collector's optional `prepare --system-skills-contract FILE` copies the
private contract into the new attempt, then passes it to the public snapshot
entry point. The declaration binds its raw-byte digest. Snapshot and live
admission validate the source executable hashes and require the entire observed
`.system` inventory to equal one captured version. Marker-only matching, extra
files, edited instructions and symlinks cannot authorize a refresh.

For comparison only, the launcher computes allowed full-skill hashes by combining
each generated version with the **current unchanged user-file inventory**.
Changing any user file therefore changes the allowed set and fails declaration
comparison. Raw hashes and per-file maps remain in snapshots. Contract paths may
differ between owned attempts; content bindings and allowed sets must agree.
Protected-state comparison uses the same bounded set. Receipt validation checks
file-map linkage and recomputes the case-relative, digest-bound contract binding
without consulting today's executable bytes. Updating or removing a source engine
cannot invalidate intact historical evidence before reuse assessment; live
admission still checks the selected source executables. Old evidence without the
optional field keeps its original strict semantics. Nothing retroactively turns
a failed attempt into a pass.

This contract is same-user maintainer qualification evidence, not a new security
credential or a cryptographic attestation of an engine. Its generator and private
receipt bindings support review; arbitrary hand-authored claims are not trusted
release evidence. Unknown refreshes require a new offline capture and review,
not a blanket exclusion. Ordinary launch, account, credential, routing, history,
approval and lifecycle contracts and the production guard are unchanged.

Tests exercise public snapshot/launch admission across a generated refresh,
including actual inventories from distinct installed engines. Negative controls
retain rejection of unknown/changed system files, symlinks, changed user skills,
contract/engine drift and forged allowed sets. Collector tests retain differing
raw receipts while comparing only the verified generated change. These are
protocol and preservation checks; signed-in UI switching remains a manual gate.
