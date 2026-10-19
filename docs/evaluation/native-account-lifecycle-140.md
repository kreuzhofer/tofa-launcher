# Native-account route lifecycle regression evidence

Part of #134/#140. These tests extend the existing ownership and lifecycle
boundaries to `tofa-native-router`. They use disposable homes, a test-owned
Desktop shell, synthetic credentials and owned local upstreams. The history
matrix drives the installed bundled engine. No installed Desktop application,
real sign-in inference or user configuration is changed by these tests.

The existing lifecycle implementation handles the candidate route without a new
manager or restore-on-exit mechanism. This slice adds regression coverage and
fixture adaptations; it makes no production lifecycle change. The native CI job
budget increases from 20 to 30 minutes after run `39293124397` completed all
macOS test steps but exceeded the aggregate job limit (1205 seconds). Every
client, ownership, review and observer deadline remains unchanged.

The same public-launch tests now cover both legacy and candidate routes:

- A killed launcher loses its route and both capabilities. A surviving fixture
  client blocks replacement until the test explicitly quits its own process
  group. Subsequent launches reject old inference and control capabilities,
  remove only owned abandoned resources and leave an unrelated process and an
  outside symlink target untouched.
- Native ownership acquisition serializes competing launchers. Concurrent
  configuration edits and incompatible ownership records remain intact. A
  control capability cannot submit inference before readiness.
- Engine exit, graceful client shutdown, cancellation and adapter failure stop
  owned work. Active owners block installation and uninstallation.
- Interrupted executable replacement retains a callable saved reference, fails
  visibly on an actual file-size-limited write and permits a later explicit
  replacement. Modified, partial, future-version and symlinked ownership
  artifacts are refused.
- The actual installer/uninstaller scripts update a fixture installation, follow
  an engine layout move, refuse an incompatible client, detach and reattach saved
  references and preserve fixture account, settings and workspace bytes. An
  ordinary native lock blocks uninstall/purge independently of the launcher lease.

The real-engine history matrix creates native `openai`, legacy `nebius-tofa` and
mixed `tofa-native-router` conversations, then exercises launcher crash, client
crash, clean exit, interrupted bridge replacement and uninstall/reattach. Every
case checks preserved account/configuration bytes, history identity, title,
prior service context and tool result. It exercises ordinary saved-bridge
readability/refusal and two new TOFA launches with a different default while
retaining each conversation's recorded model/provider. The launcher-crash case
creates its cross-service history using owned transports, then kills a separate
public-launch process attached to that profile; it performs no inference through
the subprocess's default HTTP transport.

The observer belongs to the test process. Its socket can remain open after a
launcher crash, so the assertion is that both expired capabilities fail through
that observer and that a later launch rejects them with HTTP 401. Observer socket
liveness does not imply that the launcher-hosted adapter survived.

See [sanitized results](evidence/native-account-routing-134/lifecycle-140.json).
The combined race run passed 46 test/subtest events but retained four test
failures (six events): two engine-exit deadlines, one cancellation startup
deadline and one fixture engine-version preflight. An exclusive scoped rerun of
those cases, their legacy/candidate controls and the stricter fresh-route
HTTP 401 assertion passed in 59.551 seconds. No client or test deadline changed;
the initial failures remain evidence rather than being erased. `go vet` and
`git diff --check` passed. This is affected regression coverage, not the final
full-repository validation gate.

Raw failed attempts and command logs stay in the agreed private validation root.
Initial extensions exposed legacy fixture assumptions (401 versus 503, observer
socket lifetime, and the explicit `uninstalled` error); those were corrected in
the tests. They were not production defects and are not described as production
red-to-green fixes.

## Remaining qualification

The [#137 ordinary-client gap](native-account-history-137.md) remains open. The
saved bridge can provide relaunch guidance; direct bundled-engine access instead
reports a reconnect error. These lifecycle tests neither repair nor qualify the
actual ordinary Desktop behavior. Actual Desktop account/plugin preservation,
process selection, native crash/restart behavior and visible recovery still need
#141/#142 qualification. No model capability, presentation preview or release
pass follows from this fixture matrix. Windows ownership remains a separate gate.
