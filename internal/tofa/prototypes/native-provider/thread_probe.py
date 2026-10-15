"""THROWAWAY #133: bundled-engine routing with fake auth and loopback fixtures.

No Desktop, real account, external inference, or production adapter is used.
Each invocation requires a new output directory. All attempts are retained.
"""
import argparse
import copy
import hashlib
import http.client
import json
import os
from pathlib import Path
import queue
import secrets
import signal
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

KIMI = 'moonshotai/Kimi-K3'
GPT = 'gpt-6-astra'
GUARDIAN = 'zai-org/GLM-5.3-Flash'
NATIVE_REVIEW = 'codex-auto-review'
LUNA = 'gpt-6-luna'


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def message(text):
    return dict(id='msg_fixture', type='message', role='assistant', status='completed',
                content=[dict(type='output_text', text=text, annotations=[])])


def is_review(body):
    return body.get('client_metadata', {}).get('x-openai-subagent') == 'guardian'


def sse(item, model):
    response = dict(id='resp_fixture', object='response', status='completed',
                    model=model, output=[item], usage=dict(input_tokens=10, output_tokens=2, total_tokens=12))
    events = [('response.created', dict(response=dict(id='resp_fixture', status='in_progress', output=[]))),
              ('response.output_item.added', dict(output_index=0, item=item)),
              ('response.output_item.done', dict(output_index=0, item=item)),
              ('response.completed', dict(response=response))]
    return ''.join('event: ' + name + '\ndata: ' + json.dumps(dict(type=name, **body)) + '\n\n'
                   for name, body in events).encode()


class Engine:
    def __init__(self, executable, out, env, policy, config, tag):
        self.number = 0
        self.messages = queue.Queue()
        self.stderr = (out / (tag + '.stderr')).open('xb')
        self.transcript = (out / (tag + '.jsonl')).open('x')
        command = ['/usr/bin/sandbox-exec', '-p', policy, str(executable), 'app-server']
        for setting in config:
            command += ['-c', setting]
        self.process = subprocess.Popen(command, cwd=out, env=env, stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=self.stderr,
                                        text=True, start_new_session=True)
        def reader():
            for line in self.process.stdout:
                self.messages.put(json.loads(line))
            self.messages.put({'probe_eof': True})
        threading.Thread(target=reader, daemon=True).start()

    def read(self):
        data = self.messages.get(timeout=30)
        self.transcript.write(json.dumps(data) + '\n')
        self.transcript.flush()
        if data.get('probe_eof'):
            raise RuntimeError('engine closed before response')
        if 'id' in data and 'method' in data:
            # Do not approve any unexpected command/permission request.
            raise RuntimeError('unexpected server request: ' + data['method'])
        return data

    def call(self, method, params):
        self.number += 1
        self.process.stdin.write(json.dumps(dict(id=self.number, method=method, params=params)) + '\n')
        self.process.stdin.flush()
        while True:
            data = self.read()
            if data.get('id') == self.number:
                if 'error' in data:
                    raise RuntimeError(method + ': ' + json.dumps(data['error']))
                return data['result']

    def initialize(self):
        self.call('initialize', dict(clientInfo=dict(name='tofa-local-thread-prototype', version='1'),
                                     capabilities=dict(experimentalApi=True)))
        self.process.stdin.write('{"method":"initialized"}\n')
        self.process.stdin.flush()

    def turn(self, thread, text='Synthetic local routing fixture.', **extra):
        result = self.call('turn/start', dict(threadId=thread, input=[dict(type='text', text=text)], **extra))
        return result, self.finish_turn(thread)

    def finish_turn(self, thread):
        observed = []
        deadline = time.monotonic() + 60
        while True:
            if time.monotonic() > deadline:
                raise RuntimeError('prototype turn deadline reached')
            data = self.read()
            observed.append(data)
            if data.get('method') == 'turn/completed' and data['params']['threadId'] == thread:
                turn = data['params']['turn']
                if turn['status'] != 'completed':
                    raise RuntimeError('turn failed: ' + json.dumps(turn.get('error')))
                return observed

    def close(self):
        self.process.stdin.close()
        try:
            self.process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            os.killpg(self.process.pid, signal.SIGTERM)
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait()
        self.stderr.close()
        self.transcript.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--engine', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--auth-mode', choices=('path', 'header'), default='path')
    args = parser.parse_args()
    out = args.out.resolve()
    if Path('/tmp/tofa-presentation-validation').resolve() not in out.parents:
        raise ValueError('output must stay below the fixed validation root')
    out.mkdir(mode=0o700, parents=True, exist_ok=False)
    home = out / 'home'
    home.mkdir(mode=0o700)
    workspace = out / 'workspace'
    workspace.mkdir()
    (home / 'auth.json').write_text('{"OPENAI_API_KEY":"synthetic-native"}\n')
    os.chmod(home / 'auth.json', 0o600)
    original_home = Path.home()
    protected = [original_home / '.codex', original_home / '.agents', original_home / '.config/tofa',
                 original_home / '.cache/codex-runtimes',
                 original_home / 'Library/Application Support/Codex', Path('/Applications/ChatGPT.app')]
    # Engine reads its own binary, but cannot write the app or read the real auth/config.
    policy = '(version 1)(allow default)(deny network*)' + \
        '(allow network-outbound (remote ip "localhost:*"))' + \
        '(allow network-inbound (local ip "localhost:*"))' + \
        '(deny file-write* ' + ' '.join('(subpath ' + json.dumps(str(p)) + ')' for p in protected) + ')' + \
        '(deny file-read* ' + ' '.join('(subpath ' + json.dumps(str(p)) + ')' for p in protected[:3]) + ')'
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(
        ('CODEX_', 'OPENAI_', 'TOFA_', 'ELECTRON_', 'DYLD_')) and k not in ('NODE_OPTIONS', 'ZDOTDIR')}
    env.update(HOME=str(home), CODEX_HOME=str(home), TMPDIR=str(out), TMP=str(out), TEMP=str(out),
               XDG_CONFIG_HOME=str(home / '.config'), XDG_CACHE_HOME=str(home / '.cache'),
               TOFA_FIXTURE_KEY='synthetic-factory')
    secret = secrets.token_urlsafe(24)
    prefix = '/' + secret + '/v1' if args.auth_mode == 'path' else '/v1'
    requests, upstreams, auth_rejections = [], [], []
    phase = {'name': 'switch', 'review_calls': 0}
    servers = []
    engines = []
    result = dict(schema='tofa-engine-thread-prototype-v1', status='failed', checks={},
                  authorization_mode=args.auth_mode,
                  real_credentials_used=False, desktop_started=False,
                  external_network='denied in engine sandbox; fixture upstreams are loopback only',
                  source_sha256=digest(__file__), phases=[], limits=dict(requests=30, rpc_seconds=30))

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def log_message(self, *unused):
            pass

        def send(self, status, body=b'', content='application/json'):
            self.send_response(status)
            self.send_header('Content-Type', content)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            # Native WebSocket capability probe must fall back to HTTP explicitly.
            self.send(426)

        def do_POST(self):
            raw = self.rfile.read(int(self.headers.get('Content-Length', 0)))
            if self.server.role == 'router':
                if (self.path != prefix + '/responses' or
                        (args.auth_mode == 'header' and self.headers.get('X-TOFA-Launch') != secret)):
                    auth_rejections.append(True)
                    self.send(401, b'{"error":"launch authorization required"}')
                    return
                body = json.loads(raw)
                if len(requests) >= 30:
                    self.send(429, b'{"error":"prototype budget exhausted"}')
                    return
                model = body.get('model')
                requests.append(dict(phase=phase['name'], body=body, headers=dict(self.headers),
                                     path_suffix='/v1/responses', launch_secret_observed=True))
                if model in (KIMI, GUARDIAN):
                    destination = factory
                    headers = {'Content-Type': 'application/json', 'Authorization': 'Bearer synthetic-factory'}
                elif model in (GPT, NATIVE_REVIEW, LUNA):
                    destination = native
                    headers = {'Content-Type': 'application/json', 'Authorization': self.headers.get('Authorization', '')}
                else:
                    self.send(400, b'{"error":"unknown fixture model"}')
                    return
                connection = http.client.HTTPConnection('127.0.0.1', destination.server_port, timeout=5)
                try:
                    connection.request('POST', '/responses', raw, headers)
                    response = connection.getresponse()
                    self.send(response.status, response.read(), response.getheader('Content-Type'))
                finally:
                    connection.close()
                return
            body = json.loads(raw)
            model = body.get('model')
            upstreams.append(dict(phase=phase['name'], destination=self.server.role, model=model,
                                  authorization=self.headers.get('Authorization'), header_names=list(self.headers),
                                  role='review' if is_review(body) else 'main_or_title'))
            if is_review(body):
                item = message('{"outcome":"deny"}')
            elif phase['name'].startswith('review') and phase['review_calls'] == 0:
                phase['review_calls'] += 1
                item = dict(id='fc_fixture', type='function_call', call_id='call_fixture', name='exec_command',
                            status='completed', arguments=json.dumps(dict(cmd='printf prototype-review-denied',
                            sandbox_permissions='require_escalated', justification='Synthetic denied action.', max_output_tokens=100)))
            elif model == LUNA:
                item = message('{"title":"Synthetic routing","description":"Local fixture"}')
            else:
                item = message('Synthetic local response from ' + self.server.role + '.')
            self.send(200, sse(item, model), 'text/event-stream')

    def serve(role):
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        server.role = role
        servers.append(server)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return server

    def start(config, tag):
        e = Engine(args.engine, out, env, policy, config, tag)
        engines.append(e)
        e.initialize()
        return e

    def note(name, **values):
        result['phases'].append(dict(name=name, **values))

    try:
        result['client'] = dict(sha256=digest(args.engine), version=subprocess.check_output(
            [str(args.engine), '--version'], env=env, text=True, timeout=10).strip())
        bundled = json.loads(subprocess.check_output(['/usr/bin/sandbox-exec', '-p', policy,
            str(args.engine), 'debug', 'models', '--bundled'], env=env, cwd=out, timeout=15))
        native_entries = {m['slug']: m for m in bundled['models']}
        if not all(model in native_entries for model in (GPT, NATIVE_REVIEW, LUNA)):
            raise RuntimeError('required native fixture models missing')
        entries = [native_entries[m] for m in (GPT, NATIVE_REVIEW, LUNA)]
        for model, label in ((KIMI, 'Kimi (Token Factory)'), (GUARDIAN, 'Guardian (Token Factory)')):
            entry = copy.deepcopy(native_entries[GPT])
            entry.update(slug=model, display_name=label, supported_in_api=True,
                         auto_review_model_override=GUARDIAN, visibility='list')
            entries.append(entry)
        catalog = out / 'catalog.json'
        catalog.write_text(json.dumps(dict(models=entries)))
        native, factory, router = serve('native'), serve('factory'), serve('router')
        base = 'http://127.0.0.1:' + str(router.server_port) + prefix
        config = ['model_provider="openai"', 'model=' + json.dumps(KIMI),
                  'openai_base_url=' + json.dumps(base), 'model_catalog_json=' + json.dumps(str(catalog)),
                  'features.plugins=false', 'features.apps=false', 'features.shell_snapshot=false',
                  'features.enable_fanout=false', 'features.hooks=false', 'web_search="disabled"',
                  'model_providers.nebius-tofa.name="Legacy fixture"',
                  'model_providers.nebius-tofa.base_url=' + json.dumps(base),
                  'model_providers.nebius-tofa.env_key="TOFA_FIXTURE_KEY"',
                  'model_providers.nebius-tofa.wire_api="responses"',
                  'model_providers.nebius-tofa.requires_openai_auth=false',
                  'log_dir=' + json.dumps(str(out / 'logs')), 'sqlite_home=' + json.dumps(str(out / 'state'))]
        if args.auth_mode == 'header':
            config += ['model_providers.openai.http_headers={ "X-TOFA-Launch" = ' + json.dumps(secret) + ' }',
                       'model_providers.nebius-tofa.http_headers={ "X-TOFA-Launch" = ' + json.dumps(secret) + ' }']
        for invalid in ('/v1/responses', '/wrong/v1/responses', prefix + '/evaluation-stop'):
            connection = http.client.HTTPConnection('127.0.0.1', router.server_port, timeout=5)
            connection.request('POST', invalid, json.dumps(dict(model=KIMI)), {'Authorization': 'Bearer synthetic-native'})
            response = connection.getresponse()
            if response.status != 401:
                raise RuntimeError('negative launch-authorization control failed')
            response.read()
            connection.close()
        result['checks']['missing_wrong_secret_and_control_path_denied'] = len(auth_rejections) == 3 and not upstreams
        e = start(config, 'engine-1')
        account = e.call('account/read', dict(refreshToken=False))
        result['account_fixture'] = dict(type=(account.get('account') or {}).get('type'),
                                        requires_openai_auth=account.get('requiresOpenaiAuth'))
        result['checks']['native_auth_still_required'] = account.get('requiresOpenaiAuth') is True
        models = e.call('model/list', dict(includeHidden=True))
        (out / 'model-list.json').write_text(json.dumps(models, indent=2))
        thread = e.call('thread/start', dict(cwd=str(workspace), model=KIMI,
                        approvalPolicy='never', sandbox='read-only'))
        thread_id = thread['thread']['id']
        result['checks']['new_thread_native_provider'] = thread['modelProvider'] == 'openai'
        for model in (KIMI, GPT, KIMI):
            e.call('thread/settings/update', dict(threadId=thread_id, model=model))
            e.turn(thread_id, text='Synthetic local switching fixture ' + model)
        observed = e.call('thread/read', dict(threadId=thread_id, includeTurns=True))['thread']
        result['checks']['same_thread_three_completed_turns'] = observed['id'] == thread_id and len(observed['turns']) == 3
        result['checks']['switch_sequence'] = [(r['model'], r['destination']) for r in upstreams] == [(KIMI, 'factory'), (GPT, 'native'), (KIMI, 'factory')]
        result['checks']['context_reaches_next_selected_service'] = (
            'Synthetic local response from factory.' in json.dumps(requests[1]['body'].get('input')) and
            'Synthetic local response from native.' in json.dumps(requests[2]['body'].get('input')))
        note('switch', provider=thread['modelProvider'], turns=len(observed['turns']))
        legacy = e.call('thread/start', dict(cwd=str(workspace), model=KIMI, modelProvider='nebius-tofa',
                                           approvalPolicy='never', sandbox='read-only'))
        legacy_id = legacy['thread']['id']
        phase['name'] = 'legacy'
        e.turn(legacy_id)
        e.close()
        engines.remove(e)
        e = start(config, 'engine-2')
        for identifier, provider in ((thread_id, 'openai'), (legacy_id, 'nebius-tofa')):
            resumed = e.call('thread/resume', dict(threadId=identifier, model=None, modelProvider=None))
            if resumed['modelProvider'] != provider or resumed['thread']['id'] != identifier:
                raise RuntimeError('resume changed identity/provider')
            e.turn(identifier)
        result['checks']['new_and_legacy_resume_preserve_provider'] = True
        note('resume', new_provider='openai', legacy_provider='nebius-tofa')
        review = e.call('thread/start', dict(cwd=str(workspace), model=KIMI,
                       approvalPolicy='on-request', approvalsReviewer='auto_review', sandbox='read-only'))
        review_id = review['thread']['id']
        for model in (KIMI, GPT, KIMI):
            phase.update(name='review-' + model, review_calls=0)
            e.call('thread/settings/update', dict(threadId=review_id, model=model))
            before = len(upstreams)
            _, events = e.turn(review_id, text='Propose the synthetic command once; stop if denied.')
            review_models = [r['model'] for r in upstreams[before:] if r['role'] == 'review']
            executed = any(x.get('method') == 'item/completed' and
                           x['params']['item'].get('type') == 'commandExecution' and
                           x['params']['item'].get('exitCode') == 0 for x in events)
            note('review', main=model, reviewers=review_models, command_executed=executed)
        phase['name'] = 'title'
        title = e.call('thread/start', dict(model=LUNA, modelProvider=None, cwd=str(workspace),
                approvalPolicy='never', permissions=':read-only', runtimeWorkspaceRoots=[],
                ephemeral=True, threadSource='thread_title', allowProviderModelFallback=True))
        e.turn(title['thread']['id'], text='Generate a title for the synthetic local routing fixture.',
               turnTrigger='thread_title', outputSchema=dict(type='object', properties=dict(
               title=dict(type='string'), description=dict(type='string')), required=['title', 'description'], additionalProperties=False))
        note('title', provider=title['modelProvider'], request_count=sum(r['phase'] == 'title' for r in requests))
        result['checks']['launch_secret_delivered_by_engine'] = bool(requests) and all(r['launch_secret_observed'] for r in requests)
        result['checks']['upstream_credentials_separated'] = all(r['authorization'] == 'Bearer synthetic-' + ('factory' if r['destination'] == 'factory' else 'native') for r in upstreams)
        reviews = [p for p in result['phases'] if p['name'] == 'review']
        expected_native_reviewer = native_entries[GPT].get('auto_review_model_override') or GPT
        result['checks']['review_follows_model'] = [p['reviewers'] for p in reviews] == [[GUARDIAN], [expected_native_reviewer], [GUARDIAN]]
        result['checks']['review_parent_link_observed'] = all(
            r['body']['client_metadata'].get('x-codex-parent-thread-id') == review_id and
            bool(r['body']['client_metadata'].get('parent_turn_id'))
            for r in requests if is_review(r['body']))
        result['checks']['denied_commands_not_executed'] = not any(p['command_executed'] for p in reviews)
        result['status'] = 'passed' if all(result['checks'].values()) else 'failed'
    except Exception as error:
        result['failure'] = str(error).replace(secret, '<launch-secret>')[:1000]
    finally:
        for e in engines:
            e.close()
        for server in servers:
            server.shutdown()
            server.server_close()
        # Private fixture trace has synthetic content only; never publish path secrets.
        serialized = json.dumps(requests, indent=2).replace(secret, '<launch-secret>')
        (out / 'requests.json').write_text(serialized)
        (out / 'upstreams.json').write_text(json.dumps(upstreams, indent=2))
        result['request_count'] = len(requests)
        result['upstream_count'] = len(upstreams)
        result['title_provenance'] = 'not established; helper fixture contains no parent identity'
        result['qualification_limits'] = [
            'Synthetic API-key transport fixture, not a real ChatGPT account or Desktop lifecycle test.',
            'Secret URL path delivery is proven only for path mode; engine diagnostics can contain URLs.',
            'Launch secret redaction and production inbound authorization remain unqualified.',
            'Review switches were between completed turns, not while a review was pending.',
            'The simulated router is not the production Go adapter.']
        (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result, indent=2))
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
