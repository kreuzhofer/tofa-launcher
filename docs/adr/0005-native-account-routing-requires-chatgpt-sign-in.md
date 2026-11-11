# Require ChatGPT sign-in for the first native-account routing version

The first Desktop native-account routing version requires an existing, verifiable
ChatGPT sign-in. The #133 prototype established account preservation only in that
state; signed-out and API-key-only operation remain outside this version's scope.
If the prerequisite is absent or cannot be verified, TOFA stops before launching
Desktop with an actionable explanation, without creating credentials or switching
authentication modes. This scopes the proposed route; it does not qualify Desktop
plugin preservation or authorize removal of the existing launch guard.
