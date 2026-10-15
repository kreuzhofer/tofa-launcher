# Allow explicit model selection to switch inference services

For new conversations under the proposed native-account Desktop route, explicit
model selection may switch between Token Factory and native inference while
retaining conversation identity and history. The selected service receives the
context needed for subsequent requests. Provider-bound conversations should not
be imposed as a product restriction merely because the present implementation
uses them; routing feasibility, credential separation and review/title behavior
must instead be verified before adoption.

The model choice must clearly identify the destination service. Explicit model
selection is sufficient to request a switch; a separate confirmation dialog for
each switch is not required. The supported way to communicate that destination
through Desktop's existing interface still needs verification.

Review and title requests follow the service of the work that triggered them:
Token Factory work uses the configured TOFA Guardian and naming model, while
native work retains native handling. A subsequent model selection must not
reroute already-running requests. This requires reliable request provenance;
the most recently selected model or request timing alone is not sufficient.

This deliberately revises ADR 0003's restriction on cross-service selection for
that future route. Its history-preservation, session-scoped settings and
no-automatic-migration requirements remain. Errors must never silently switch
services. Compatibility for existing conversations and behavior outside a TOFA
launch remain design prerequisites; this decision does not authorize rewriting
stored provider identities or enabling an unqualified route.
