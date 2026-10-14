# Throwaway native-provider routing experiment (#133)

Question: can the installed engine retain its real account context with a
process-only built-in-provider/base-URL override, and can model routing separate
native credentials from alternate-provider credentials?

This directory belongs only on `prototype/133-native-provider-routing`. It is
not imported by the launcher. The existing launch guard is unchanged. Related:
[#133](https://github.com/kreuzhofer/tofa-launcher/issues/133), #130 and #119.
See the [pinned Ollama research](../../../../docs/research/ollama-desktop-provider-routing-2026-10-14.md).

## Open the walkthrough

Double-click `walkthrough.html`. It is a single self-contained HTML file with
free-play actions and guided scenarios. All controls simulate state in memory;
the observed experiment results appear separately. No browser network request,
native app launch, settings write, or model inference is triggered by its controls.

## Reproduce the bounded probes

From the repository root, use Python 3.12+ and choose new output paths for each
attempt. These probes refuse to overwrite existing evidence. macOS permission
to run the installed engine and bind owned loopback fixtures is required.

```sh
python3 -B internal/tofa/prototypes/native-provider/account_probe.py \
  --out /tmp/tofa-presentation-validation/checks/prototype-133/account-new \
  --engine /Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex \
  --home "$HOME/.codex" \
  --runtime "$HOME/.cache/codex-runtimes/codex-primary-runtime"

python3 -B internal/tofa/prototypes/native-provider/router_probe.py \
  --unsafe-header-copy \
  --out /tmp/tofa-presentation-validation/checks/prototype-133/router-negative-new.json

python3 -B internal/tofa/prototypes/native-provider/router_probe.py \
  --out /tmp/tofa-presentation-validation/checks/prototype-133/router-positive-new.json
```

The negative router control must exit 1 because it deliberately forwards fake
native credentials to the fake alternate service. The safe variant must exit 0.
Four actual loopback upstream requests exercise alternate routing, native ChatGPT
routing, native API routing and a sanitized upstream error. Unknown-model and
unavailable-service cases must never reach another service. These are experiment
controls, not a production adapter test suite or real model calls.

The account probe submits only initialization, `account/read` with token refresh
disabled, and `config/read`. Native account contents are filtered immediately;
only account type, authentication requirement and selected configuration facts
are exported. Stderr stays in the private temporary run directory. It does not
copy credentials, request a model turn or start the Desktop app. Protected files
are checked between cases. It refuses to change the shared routing configuration.

## Interpretation limits

- Account metadata alone does not establish native plugin eligibility or prove
  that Desktop preserves a plugin across launch, crash, ordinary restart and
  uninstall.
- The synthetic router is throwaway Python. It demonstrates the boundary with
  fake credentials; it does not qualify the production Go adapter, streaming,
  Guardian, naming, compaction, loopback access control, or native transport.
- Existing `nebius-tofa` conversation provider identities must not be silently
  rewritten. This experiment does not decide the compatibility mechanism.
- Ollama's persistent root-config/restore lifecycle is not adopted. Process-only
  overrides must preserve concurrent CLI behavior under ADR 0003.
- No release, supported-model promotion, guard removal or paid comparison is
  implied by a passing probe.
