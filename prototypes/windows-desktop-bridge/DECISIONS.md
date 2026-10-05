# Maintainer decisions

2026-10-05: The maintainer approved normally shutting down “Sabre Windows 11
ARM64”, creating an owned disposable clone for the Windows desktop bridge
experiment, then restarting the original. They accepted interruption of its open
apps and asked that this decision be remembered. Do not request the same approval
again during this experiment. Force stop, reset and snapshot overwrite are not
included in this approval.

The approved shutdown → clone → original restart sequence completed. The original
and the uniquely named disposable clone were both running afterward.

The maintainer manually trusted the clone-only scratch workspace
`C:\Users\Public\tofa77-approval-workspace`. They also explicitly approved selecting
“Approve for me” in the disposable clone for the bounded Guardian experiment,
knowing that it permits the native reviewer to approve actions it considers safe.
This does not authorize Full access or changes to the ordinary VM's permissions.

The maintainer selected “Approve for me” manually after automation could not
reliably activate the guest permission control. The resulting setting was
visibly verified before the first bounded native shell trial.
