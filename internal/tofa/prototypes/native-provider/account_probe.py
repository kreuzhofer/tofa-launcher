"""THROWAWAY #133: actual bundled-engine account/config reads; no inference."""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import select
import signal
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / 'scripts'))
from capability_runtime import protected, desktop_identity


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def snapshot(home, runtime):
    manifest = json.loads((runtime / 'runtime.json').read_text())
    skill = home / 'plugins/cache/openai-primary-runtime/presentations' / manifest['bundleVersion'] / 'skills/presentations'
    launcher = home.parent / '.config/tofa'
    leaves = [launcher / 'config.yml', launcher / 'credentials.yml',
              *launcher.glob('desktop-bridge-v2/*/tofa-desktop-engine'),
              *launcher.glob('desktop-bridge-v2/*/owner.json')]
    return {'protected': protected(home, skill, runtime),
            'launcher': {str(p): digest(p) if p.is_file() else None for p in leaves}}


def read_case(engine, home, out, extra, policy):
    env = {k: v for k, v in os.environ.items()
           if not k.upper().startswith(('CODEX_', 'OPENAI_', 'TOFA_', 'ELECTRON_', 'DYLD_'))
           and k.upper() not in ('NODE_OPTIONS', 'ZDOTDIR')}
    env.update(CODEX_HOME=str(home), TMPDIR=str(out), TMP=str(out), TEMP=str(out))
    command = ['/usr/bin/sandbox-exec', '-p', policy, str(engine), 'app-server',
               '-c', 'log_dir=' + json.dumps(str(out / 'logs')),
               '-c', 'sqlite_home=' + json.dumps(str(out / 'state')), *extra]
    log = (out / 'engine.stderr').open('xb')
    os.chmod(out / 'engine.stderr', 0o600)
    p = subprocess.Popen(command, env=env, cwd=out, stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=log,
                         start_new_session=True)
    buf = b''

    def rpc(number, method, params):
        nonlocal buf
        p.stdin.write((json.dumps({'id': number, 'method': method, 'params': params}) + '\n').encode())
        p.stdin.flush()
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            while b'\n' in buf:
                line, buf = buf.split(b'\n', 1)
                message = json.loads(line)
                if message.get('id') == number:
                    if 'error' in message:
                        detail = str(message['error'].get('message', '')).lower()
                        categories = [word for word in ('auth', 'keychain', 'permission', 'permitted', 'network', 'socket', 'file', 'cache', 'config', 'refresh', 'client', 'experimental', 'method', 'unsupported') if word in detail]
                        code = message['error'].get('code')
                        diagnostic = str(message['error'].get('message', ''))
                        diagnostic = re.sub(r'\S*@\S*|https?://\S+|/[^\s]+|[A-Za-z0-9_+=.-]{24,}', '<REDACTED>', diagnostic)
                        raise RuntimeError('engine rejected ' + method + '; code=' + str(code if isinstance(code, int) else None) + '; categories=' + ','.join(categories) + '; diagnostic=' + diagnostic[:220])
                    return message['result']
            if not select.select([p.stdout], [], [], max(0, deadline - time.monotonic()))[0]:
                break
            chunk = os.read(p.stdout.fileno(), 65536)
            if not chunk:
                break
            buf += chunk
            if len(buf) > 4 * 1024 * 1024:
                raise RuntimeError('bounded RPC response exceeded')
        raise RuntimeError('engine closed or timed out before: ' + method)

    try:
        rpc(1, 'initialize', {'clientInfo': {'name': 'tofa-prototype-133', 'version': '1'}})
        p.stdin.write(b'{"method":"initialized"}\n')
        p.stdin.flush()
        result = rpc(2, 'account/read', {'refreshToken': False})
        account_type = (result.get('account') or {}).get('type')
        requires_auth = result.get('requiresOpenaiAuth')
        del result  # Never serialize account identity, subscription details or credentials.
        config = rpc(3, 'config/read', {'includeLayers': False, 'cwd': str(out)})['config']
        return {'account_type': account_type, 'requires_openai_auth': requires_auth,
                'effective_provider': config.get('model_provider'),
                'loopback_override_observed': config.get('openai_base_url') == 'http://127.0.0.1:1/v1',
                'alternate_model_observed': config.get('model') == 'moonshotai/Kimi-K3',
                'code_review_configured': 'code-review@openai-bundled' in (config.get('plugins') or {})}
    finally:
        p.stdin.close()
        try:
            p.wait(timeout=2)
        except subprocess.TimeoutExpired:
            os.killpg(p.pid, signal.SIGTERM)
            try:
                p.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid, signal.SIGKILL)
                p.wait()
        log.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--engine', type=Path, required=True)
    parser.add_argument('--home', type=Path, required=True)
    parser.add_argument('--runtime', type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    fixed_root = Path('/tmp/tofa-presentation-validation').resolve()
    if fixed_root not in out.parents:
        raise ValueError('output must be below fixed validation root')
    out.mkdir(mode=0o700, parents=True, exist_ok=False)
    # Protect shared state while allowing the engine's own ephemeral startup IO.
    # A blanket write denial prevents this engine from initializing (retained runs 1–3).
    folders = [args.home / 'plugins', args.home / 'skills', args.home.parent / '.agents',
               args.runtime, args.home.parent / '.config/tofa',
               args.home.parent / 'Library/Application Support/Codex', Path('/Applications/ChatGPT.app')]
    leaves = [args.home / name for name in ('config.toml', 'auth.json', 'managed_config.toml', 'AGENTS.md', 'AGENTS.override.md')]
    policy = '(version 1)(allow default)(deny file-write* ' + ' '.join(
        '(subpath ' + json.dumps(str(p.resolve())) + ')' for p in folders) + ' ' + ' '.join(
        '(literal ' + json.dumps(str(p.resolve())) + ')' for p in leaves) + ')'
    before = snapshot(args.home, args.runtime)
    result = {'schema': 'tofa-native-provider-account-prototype-v1', 'cases': {},
              'method': ['initialize', 'account/read', 'config/read'], 'refresh_token': False,
              'network_policy': 'normal native account lookup connectivity; no model/inference RPC submitted',
              'network_limit': 'account/config RPCs only; native HTTPS account discovery not captured; no inference RPC or user prompt submitted',
              'write_policy': 'deny protected settings, auth, plugins, skills, supplied runtime, launcher state and native app/profile writes; engine ephemeral startup IO allowed',
              'desktop_started': False, 'inference_rpc_count': 0,
              'source_sha256': digest(Path(__file__)), 'status': 'failed'}
    native = ['-c', 'model_provider="openai"', '-c', 'openai_base_url="http://127.0.0.1:1/v1"']
    custom = ['-c', 'model_provider="tofa-auth-prototype"', '-c', 'model_providers.tofa-auth-prototype.name="Owned offline prototype"',
              '-c', 'model_providers.tofa-auth-prototype.base_url="http://127.0.0.1:1/v1"',
              '-c', 'model_providers.tofa-auth-prototype.wire_api="responses"',
              '-c', 'model_providers.tofa-auth-prototype.requires_openai_auth=false']
    try:
        result['client'] = {'sha256': digest(args.engine),
                            'version': subprocess.check_output([str(args.engine), '--version'], text=True, timeout=10).strip()}
        result['desktop_identity'] = desktop_identity(Path('/Applications/ChatGPT.app'), args.engine)
        for name, extra in [('ordinary', []), ('custom_provider_control', custom),
                            ('native_provider_router', native),
                            ('native_provider_alternate_model', native + ['-c', 'model="moonshotai/Kimi-K3"']),
                            ('ordinary_after', [])]:
            folder = out / name
            folder.mkdir(mode=0o700)
            result['cases'][name] = read_case(args.engine, args.home, folder, extra, policy)
            if snapshot(args.home, args.runtime) != before:
                raise RuntimeError('protected state changed; experiment stopped')
        cases = result['cases']
        baseline = cases['ordinary']
        checks = {
            'ordinary_signed_in': baseline['account_type'] in ('chatgpt', 'chatgptAuthTokens'),
            'custom_control_loses_account': cases['custom_provider_control']['account_type'] is None and cases['custom_provider_control']['requires_openai_auth'] is False,
            'native_route_retains_account': all(cases[n]['account_type'] == baseline['account_type'] and cases[n]['requires_openai_auth'] is True and cases[n]['effective_provider'] == 'openai' and cases[n]['loopback_override_observed'] for n in ('native_provider_router', 'native_provider_alternate_model')),
            'alternate_model_selected': cases['native_provider_alternate_model']['alternate_model_observed'],
            'ordinary_after_identical': cases['ordinary_after'] == baseline,
        }
        result['checks'] = checks
        result['status'] = 'passed' if all(checks.values()) else 'failed'
    except Exception as error:
        # No raw engine/account/config data or exception values are exported.
        result['error_type'] = type(error).__name__
        result['failed_case'] = name if 'name' in locals() else 'preflight'
        if isinstance(error, RuntimeError):
            # Engine error text is bounded and redacted above; no account result is exported.
            result['probe_failure'] = str(error)
    finally:
        result['protected_state_preserved'] = snapshot(args.home, args.runtime) == before
        if not result['protected_state_preserved']:
            result['status'] = 'failed'
        (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result, indent=2))
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    sys.exit(main())
