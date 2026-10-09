# Windows desktop retains the ordinary-profile contract

For [#102](https://github.com/kreuzhofer/tofa-launcher/issues/102), the maintainer
confirmed on 2026-10-09 that the Windows desktop target must retain the ordinary
account, profile and conversation experience required by
[#77](https://github.com/kreuzhofer/tofa-launcher/issues/77). We will pursue a
supported native ownership contract rather than change that product scope.

The [retained experiment](https://github.com/kreuzhofer/tofa-launcher/blob/e1cd869cf750042990666268caef6bdd350e74d1/docs/testing/windows-atomic-ownership-evidence-2026-10-08.md)
observed native IPC traffic before launcher admission and reconnection after
endpoint replacement. Ownership of the stdio main-engine bridge does not
establish ownership of that separate desktop IPC route. Windows desktop
availability stays disabled and [#87](https://github.com/kreuzhofer/tofa-launcher/issues/87)
stays blocked until the native boundary is supported and demonstrated against
the existing acceptance criteria. Local development recovery in #103/#108 does
not change this product gate.

The [upstream inquiry and continuation criteria](../research/windows-desktop-atomic-ownership-2026-10-08.md#maintainer-decision-and-upstream-inquiry---2026-10-09)
preserve authenticated or isolated IPC and a supported IPC-disable route as
questions for upstream, not established capabilities. A different profile,
weaker ownership checks, or history migration is not an accepted substitute.
