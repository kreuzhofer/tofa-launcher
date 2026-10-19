# Declared multi-turn Observer scope

The optional `tofa-observer-scope-v1` declaration supports bounded qualification
of routed service switching and resumed histories. It does not change ordinary
launch behavior or the existing single-prompt Observer contract. This is a
prerequisite for #142 collection, not actual Desktop qualification evidence.

The collector creates private `scope.json` inside the attempt root before launch,
then supplies its exact raw-byte SHA-256 and the same attempt identifier to
`Observer(..., scope_declaration=path, scope_sha256=digest, scope_attempt=attempt)`.
The native-account admission declaration binds this digest separately. The
Observer consumes the declaration once by exclusively creating
`scope-consumed.json`, before it listens. Registration must use the existing v2
split control/inference authorization. Credentials, strict role contracts,
request/byte/deadline limits, native usage validation and approval enforcement
remain in effect.

Example private declaration (paths and identifiers are illustrative):

```json
{
  "schema": "tofa-observer-scope-v1",
  "attempt": "declared-attempt",
  "root": "/private/tmp/tofa-presentation-validation/runs/declared-attempt",
  "threads": [{
    "label": "switch",
    "thread_id": null,
    "workspace": "/private/tmp/tofa-presentation-validation/runs/declared-attempt/workspace",
    "initial_user_messages_sha256": null,
    "turns": [
      {"model": "moonshotai/Kimi-K3", "service": "token_factory", "prompt": "Remember the declared synthetic value."},
      {"model": "gpt-6-astra", "service": "native", "prompt": "Recall the declared synthetic value."}
    ]
  }],
  "titles": []
}
```

Declarations reject unknown/duplicate fields, mismatched root/attempt/digest,
non-private or symlink files, unknown services/models, duplicate prompts and
unbounded sequences. Limits are eight threads, sixteen total declared Main
turns, eight title-only contexts and 16 KiB per prompt. A declaration is at most
1 MiB. Every admitted request rechecks file privacy and exact bytes.

A new thread uses an owned workspace and binds its actual request thread ID only
on the first exact declared prompt. Workspace matching resolves an exact whole-path user context or the
engine’s explicit `<cwd>` field, including macOS `/tmp` aliases; path substrings
do not match. Each subsequent task requires the next
prompt, selected model, a new turn ID and exactly the prior accepted user-message
list. Tool continuations and engine-originated retries remain within the same
thread/turn/model and accepted user-message list; all consume the normal request
budget. A Guardian review requires its immutable admitted originating turn and
does not advance the sequence. No wildcard thread admission or latest-selection
review routing is introduced.

A resumed thread instead declares its known thread ID, original existing
workspace and `initial_user_messages_sha256`. This digest uses the existing
Observer `hashed(user_messages)['sha256']` encoding, preserving message order,
roles and content representation. The first new task must carry precisely that
user-message prefix. The Observer does not move, rewrite or create files in the
old workspace. Its action watcher still covers only the owned `run/workspace`;
this scope check does not prove filesystem preservation in another workspace.
The user-message digest likewise does not prove complete assistant/tool history
continuity. Qualification must separately inspect the native history evidence.

Private `scope-state.json` records bound thread IDs, progress and the latest
user-message digest to prepare a later explicit resume declaration. Request
records contain hashes and declared labels, not raw prompts or thread IDs.
These private files must not be published without review.

## Direct-native histories and naming

Preserved direct-native Main requests intentionally bypass the Observer. They
are not counted or qualified by its routed Main observations. For launch-wide
Token Factory naming of such a history, an optional `titles` entry can declare
`{"thread_id":"intended-ui-case-thread", "prompt":"Exact unique synthetic task."}`.
A titles-only declaration has an empty `threads` list. It authorizes no Main or
Guardian traffic. Only the existing strict recognized native title contract
containing the exact declared prompt is admitted.

The title request does not provide verified parent identity. Its record says
`parent_unverified: true`, `main_observed: false` and records the hash as
`intended_ui_thread_sha256`, never as a verified request parent. Actual UI/native
trace association is separate required qualification evidence. Titles for
routed threads require a previously admitted Main prompt, and also retain
`parent_unverified: true`. Timing or prompt matching does not establish parentage.

## Owned shutdown

Observer exit stops accepting connections, closes all owned accepted sockets
(including incomplete unauthenticated headers), and joins its request handlers
before final persistence returns. A regression holds a usage-failure handler in
its owned stop request after the client has disconnected. Exit must wait for
that handler's final diagnostic write, rather than race temporary-root cleanup.
No cleanup errors are ignored and no arbitrary delay is used to hide writes.

The scope and shutdown tests use owned loopback HTTP upstreams and synthetic
credentials. They do not launch Desktop, contact a provider, or prove account,
plugin, preview or real-history preservation. Those remain the actual Desktop
qualification gates in #141–#143.

A public-launch test also drives the real bundled engine through the actual
Python Observer and owned local upstreams: Token Factory → native GPT (one tool
continuation) → Token Factory. It checks exact scope indices, separated
credentials, retained thread identity and assistant/tool context. This protocol
fixture uses synthetic credentials and disables plugins only in its owned
profile; it is not an actual signed-in Desktop or plugin-preservation pass.
