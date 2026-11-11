# Qualify Desktop behaviour across compatible updates

For the experimental macOS Desktop route, maintainer qualification establishes
release readiness; ordinary-user launch uses local compatibility, sign-in,
ownership and routing checks rather than a private qualification campaign bound
to one installation. Reuse unaffected behavioural evidence across compatible
updates with a recorded reason, retain original identities and integrity bindings,
and require targeted actual-Desktop checks only for affected or unproven
behaviour that automated real-path tests cannot establish.

This trades a single exact-installation proof for explicit compatibility and
evidence-reuse decisions, so routine native updates do not restart the entire
campaign. Preserve user-managed state and capabilities while allowing identified,
contract-checked native-generated refreshes; this does not excuse credential,
permission or routing changes, or permit blanket generated-file exclusions.
The maintainer accepted this boundary on 2026-11-10; the
[acceptance matrix](../evaluation/desktop-release-readiness.md) specifies the
requirements. Existing production protection remains until its replacement is
implemented and validated; ADRs 0005 and 0006 remain in force.
