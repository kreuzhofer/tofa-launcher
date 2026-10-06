# Windows interrupted-run recovery — 2026-10-06

Issue #81's controlled native acceptance passed through the public
`scripts/windows_test_runner.py` CLI. This measures lifecycle recovery, not
real desktop or live Guardian behavior (#82–84).

A fresh clone `tofa-run-c92a3cb57004462fb3782f4ea4956560` booted from the stopped
dedicated ARM64 template. A simultaneous invocation refused and identified the
active run. The acceptance driver sent SIGKILL only to its own runner subprocess
after boot completed. Status subsequently reported the invocation abandoned.

`recover` recorded `runner_abandoned`, attempted bounded diagnostic collection,
and requested normal shutdown. Normal shutdown did not complete within its
reserved budget; recovery force-stopped only the verified owned clone and
retained its disk. Neither native trial results nor guest checkpoints were
available at this early interruption; both are explicitly unavailable in the
recovery report. This is a successful recovery of an intentionally failed run,
not a passing smoke result.

The earlier failed clone remained retained. A third invocation therefore refused
with `retained_clone_limit` and a concrete cleanup command. Explicit cleanup
removed only the new interrupted clone. Repeated cleanup returned
`already_absent`; repeated recovery returned `no_recovery_needed`. Final UTM
inventory exactly matched the initial inventory: the dedicated template stayed
stopped, the everyday VM stayed running, and the prior retained clone and Ubuntu
VM stayed stopped. No account or credential operation was used.

[Evidence directory](evidence/windows-recovery-2026-10-06/) retains the original
interruption, concurrency refusal, abandoned status, recovery attempt, failed
report, retention refusal, cleanup and repeated-operation results. The standalone
acceptance driver used no recovery internals: it invoked the public CLI, observed
its durable reports, and killed the `Popen` process handle it had created.

The fixture suite additionally covers shutdown refusal/hang, failed forced
shutdown and retry, stale/reused PID, replaced lock identity, in-flight transport
lease ownership, diagnostic failure, ambiguous clone identity, crash before the
initial report, crash between ownership/report saves, trial interruption, and
crash after deletion. Full validation and independent review results are recorded
in `validation.json` after completion.
