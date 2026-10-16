"""DEBUG #133: minimal actual-engine launch-secret disclosure regression.

Fake credentials, disposable HOME, localhost-only network, no Desktop or tools.
Exit 1 if a request actually occurs and its launch secret appears in diagnostics.
Exit 2 if the trigger never runs. Never print the generated secret.
"""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from thread_probe import Engine, digest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--engine', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--secret-location', choices=('path','absent','header'), default='path')
    parser.add_argument('--failure', choices=('handshake','disconnect'), default='handshake')
    args = parser.parse_args()
    out = args.out.resolve()
    if Path('/tmp/tofa-presentation-validation').resolve() not in out.parents:
        raise ValueError('use fixed validation root')
    out.mkdir(mode=0o700, parents=True, exist_ok=False)
    home = out / 'home'
    home.mkdir(mode=0o700)
    (home / 'auth.json').write_text('{"OPENAI_API_KEY":"synthetic-native"}\n')
    secret = secrets.token_urlsafe(24)
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(
        ('CODEX_', 'OPENAI_', 'TOFA_', 'ELECTRON_', 'DYLD_')) and k not in ('NODE_OPTIONS', 'ZDOTDIR')}
    env.update(HOME=str(home), CODEX_HOME=str(home), TMPDIR=str(out), TMP=str(out), TEMP=str(out))
    # A deliberately broken HTTP/1.0 WebSocket handshake reaches the observed
    # native error formatter. No response content or real model is involved.
    seen = threading.Event()
    observed = {}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *unused):
            pass
        def do_GET(self):
            seen.set()
            observed.update(header_secret_received=self.headers.get('X-TOFA-Launch')==secret,
                            native_auth_received=self.headers.get('Authorization')=='Bearer synthetic-native')
            if args.failure == 'disconnect':
                self.close_connection = True
                return
            self.send_response(426)
            self.send_header('Content-Length', '0')
            self.end_headers()
        def do_POST(self):
            seen.set()
            self.send_response(503)
            self.send_header('Content-Length', '0')
            self.end_headers()
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    original = Path.home()
    protected = [original / '.codex', original / '.agents', original / '.config/tofa',
                 original / '.cache/codex-runtimes', original / 'Library/Application Support/Codex',
                 Path('/Applications/ChatGPT.app')]
    policy = '(version 1)(allow default)(deny network*)' + \
        '(allow network-outbound (remote ip "localhost:*"))' + \
        '(deny file-write* ' + ' '.join('(subpath '+json.dumps(str(p))+')' for p in protected) + ')' + \
        '(deny file-read* ' + ' '.join('(subpath '+json.dumps(str(p))+')' for p in protected[:3]) + ')'
    config = ['model_provider="openai"', 'model="gpt-6-astra"',
              'openai_base_url='+json.dumps('http://127.0.0.1:'+str(server.server_port)+('/'+secret if args.secret_location=='path' else '')+'/v1'),
              'features.plugins=false', 'features.apps=false', 'features.shell_snapshot=false',
              'features.hooks=false', 'web_search="disabled"',
              'log_dir='+json.dumps(str(out/'logs')), 'sqlite_home='+json.dumps(str(out/'state'))]
    if args.secret_location == 'header':
        env['TOFA_DIAGNOSTIC_LAUNCH_SECRET']=secret
        config[0]='model_provider="tofa-authenticated-router"'
        config += ['model_providers.tofa-authenticated-router.name="Authenticated loopback fixture"',
                   'model_providers.tofa-authenticated-router.base_url='+json.dumps('http://127.0.0.1:'+str(server.server_port)+'/v1'),
                   'model_providers.tofa-authenticated-router.wire_api="responses"',
                   'model_providers.tofa-authenticated-router.requires_openai_auth=true',
                   'model_providers.tofa-authenticated-router.supports_websockets=true',
                   'model_providers.tofa-authenticated-router.env_http_headers={ "X-TOFA-Launch" = "TOFA_DIAGNOSTIC_LAUNCH_SECRET" }']
    started = time.monotonic()
    engine = None
    report = {'schema':'tofa-launch-secret-regression-v1', 'status':'infra_blocked',
              'engine_sha256':digest(args.engine), 'source_sha256':digest(__file__),
              'external_network':'denied', 'real_credentials_used':False}
    report.update(secret_location=args.secret_location, failure_mode=args.failure)
    try:
        engine = Engine(args.engine, out, env, policy, config, 'engine')
        engine.initialize()
        account=engine.call('account/read',dict(refreshToken=False))
        report['requires_openai_auth']=account.get('requiresOpenaiAuth')
        report['account_type']=(account.get('account') or {}).get('type')
        thread = engine.call('thread/start', dict(cwd=str(out), approvalPolicy='never', sandbox='read-only'))
        engine.call('turn/start', dict(threadId=thread['thread']['id'], input=[dict(type='text', text='Synthetic local error fixture. No tools.')]))
        deadline = time.monotonic()+8
        while time.monotonic()<deadline:
            raw = (out/'engine.stderr').read_text()
            if seen.is_set() and ('responses_websocket' in raw or secret in raw):
                break
            time.sleep(.05)
        report['request_observed'] = seen.is_set()
        report.update(observed)
    except Exception as error:
        report['error'] = str(error).replace(secret, '<REDACTED>')[:500]
    finally:
        if engine:
            engine.close()
        server.shutdown()
        server.server_close()
        raw = (out/'engine.stderr').read_text() if (out/'engine.stderr').exists() else ''
        report['secret_in_stderr'] = secret in raw
        report['signal'] = next((line.replace(secret,'<REDACTED>') for line in raw.splitlines() if 'responses_websocket' in line), None)
        leaks=[]
        for path in out.rglob('*'):
            if path.is_file() and path.name != 'engine.stderr':
                data=path.read_bytes()
                if secret.encode() in data:
                    leaks.append(str(path.relative_to(out)))
                    path.write_bytes(data.replace(secret.encode(),b'<REDACTED>'))
        report['other_artifacts_containing_secret']=leaks
        # Retain only redacted stderr. The transient launch capability is dead.
        (out/'engine.stderr').write_text(raw.replace(secret,'<REDACTED>'))
        if report.get('request_observed') and report['signal']:
            report['status'] = 'failed' if report['secret_in_stderr'] or leaks else 'passed'
            if args.secret_location=='header' and not all(report.get(k) is True for k in
                    ('header_secret_received','native_auth_received','requires_openai_auth')):
                report['status']='failed'
        report['seconds'] = round(time.monotonic()-started,2)
        (out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report,indent=2))
    return {'failed':1,'passed':0,'infra_blocked':2}[report['status']]


if __name__ == '__main__':
    raise SystemExit(main())
