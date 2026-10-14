# Provider changes and bundled plugin preservation

The launcher now refuses an adapted Desktop launch when it would expose an
installed or configured `code-review@openai-bundled` plugin to the observed native
removal path. This protects ordinary state; it does not unblock #130's model
comparison or establish a new native presentation qualification.

## Observed boundary

The [build-20398 diagnosis](evidence/presentation-runtime-126-127/desktop-plugin-preservation-20398.json)
records the native app excluding code-review from its adapted-launch marketplace
and restoring it on ordinary restart. The native eligibility check depends on
ChatGPT authentication. Its reconciliation function deletes cached files before
requesting engine uninstall. Intercepting the engine request would therefore be
too late to preserve the files. No exposed per-launch preservation switch was
found in the inspected installed reconciliation implementation.

## Implemented guard

The existing public launch command checks the version-independent bundled plugin
cache in the ordinary Codex home. Native `config/read` also checks the plugin
entry, including disabled entries and configurations whose cache is absent. A
blocked launch does not install or replace the retained bridge. The integration
preflight rechecks before publishing routing to the waiting native engine.

The guard is intentionally conservative for this plugin: it does not assume a
different app version is safe, and it leaves even an empty cache directory alone.
It neither impersonates ChatGPT authentication nor forces plugin eligibility.
It does not suppress an uninstall response, restore snapshots, silently isolate
the profile, or widen the two-reference preservation exception. Other plugins
and launches without the affected state retain their existing behavior. This is
a check at startup boundaries, not a lock against arbitrary concurrent edits to
the user's plugin files.

Regression tests use the public launcher with owned executable app/engine
fixtures. Before the guard, the native-deletion fixture removed the plugin,
changed configuration and launched Desktop; the regression failed. Separate
enabled/disabled configuration-only cases also failed before their guard. The
corrected cases preserve ordinary state and refuse before native startup or bridge
installation. The installed-profile check also observes refusal, no native process,
and unchanged protected state, launcher settings, credentials and bridge bytes.
The [sanitized guard evidence](evidence/presentation-runtime-126-127/plugin-preservation-guard-130.json)
records the tested candidate, source hashes, regression outcomes and review.

## Remaining native implementation ticket

**Problem:** native bundled-plugin reconciliation interprets a provider-dependent
eligibility change as permission to uninstall a previously installed plugin from
the shared home. Switching back reinstalls it. A stable baseline cannot remove
this behavior.

**Required behavior:** preserve the installed plugin's files and saved enabled
setting across ordinary → adapted → ordinary startup. Keep the existing native
authentication and eligibility checks controlling access: an ineligible plugin's
tools must remain unavailable for that session even when its saved enabled setting
is retained. Distinguish temporary ineligibility from an explicit user uninstall
or genuine plugin retirement.

**Implementation boundary:** an editable native reconciliation implementation or
a supported native preservation control. The current engine relay is downstream
of cache deletion. Do not patch the signed app bundle or invent an authentication
override. The launcher guard stays until the exact replacement behavior is
qualified.

**Acceptance:** a regression at the reconciliation boundary reproduces the old
removal and passes the correction; auth/eligibility and explicit uninstall retain
their contracts; actual-client clean exit, forced launcher crash, repeat launch,
ordinary restart and scoped uninstall preserve protected state. Then requalify
the actual loader and human PPTX/PDF previews before a separately declared #130
comparison. Retain all earlier failed runs and proofs. No release or supported-model
promotion follows from the guard alone.
