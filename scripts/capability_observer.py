"""Per-run, authenticated loopback boundary for actual Codex requests.

Only the launcher registers the upstream adapter. No provider credentials, endpoint
override, retries, model substitutions or approval answers live in this observer.
"""
import hashlib
import hmac
import http.client
import http.server
import json
import os
import re
from pathlib import Path
import secrets
import select
import socket
import socketserver
import threading
import time
from urllib.parse import urlsplit

from capability_actions import Actions, polling
from capability_runtime import loader_tools, loader_call, qualify, catalog_tools
from presentation_runtime import from_loader_output

BODY_LIMIT = 16 * 1024 * 1024
EVENT_LIMIT = 32 * 1024 * 1024
RESPONSE_LIMIT = 64 * 1024 * 1024
UNAVAILABLE = object()
NAMING_MODEL = 'nvidia/Nemotron-3_5-Lightning'
GUARDIAN_SCHEMA = {'type': 'object', 'additionalProperties': False,
    'properties': {'risk_level': {'type': 'string', 'enum': ['low', 'medium', 'high', 'critical']},
        'user_authorization': {'type': 'string', 'enum': ['unknown', 'low', 'medium', 'high']},
        'outcome': {'type': 'string', 'enum': ['allow', 'deny']}, 'rationale': {'type': 'string'}},
    'required': ['outcome']}


class ContractError(ValueError):
    def __init__(self, category):
        super().__init__('unsupported_request_contract')
        self.category = category


def request_shape(body, main, guardian):
    """Bounded, value-free diagnostics; unknown names can contain private data."""
    def value_type(value):
        if value is None: return 'null'
        if isinstance(value, bool): return 'boolean'
        if isinstance(value, str): return 'string'
        if isinstance(value, list): return 'array'
        if isinstance(value, dict): return 'object'
        return 'number'

    def known(value, choices):
        return value if isinstance(value, str) and value in choices else 'unknown'

    if not isinstance(body, dict): return {'body': value_type(body)}
    fields = {'model', 'stream', 'input', 'tools', 'instructions', 'reasoning', 'text',
              'tool_choice', 'max_output_tokens', 'parallel_tool_calls', 'client_metadata',
              'previous_response_id', 'conversation', 'prompt', 'store', 'include'}
    shape = {'fields': {key: value_type(value) for key, value in body.items() if key in fields},
             'unknown_fields': len(body.keys() - fields),
             'model_matches': [name for name, matched in (
                 ('main', body.get('model') == main), ('guardian', body.get('model') == guardian),
                 ('title', body.get('model') in ('gpt-5.6-luna', 'gpt-6-luna'))) if matched]}
    text = body.get('text')
    format_spec = text.get('format') if isinstance(text, dict) else None
    if isinstance(format_spec, dict):
        shape['format'] = dict(type=known(format_spec.get('type'), ('json_schema', 'text')),
                              strict_is_false=format_spec.get('strict') is False,
                              guardian_schema_matches=format_spec.get('schema') == GUARDIAN_SCHEMA)
    items = body.get('input')
    if isinstance(items, list):
        shape['input_count'] = len(items)
        shape['input'] = []
        for item in items[:64]:
            if not isinstance(item, dict):
                shape['input'].append({'type': value_type(item)}); continue
            entry = {'type': known(item.get('type', 'message'), ('message', 'function_call',
                'function_call_output', 'custom_tool_call', 'custom_tool_call_output',
                'reasoning', 'additional_tools')),
                'role': known(item.get('role'), ('user', 'assistant', 'system', 'developer'))}
            if 'content' in item: entry['content'] = value_type(item['content'])
            shape['input'].append(entry)
    tools = body.get('tools')
    if isinstance(tools, list):
        shape['tool_count'] = len(tools)
        shape['tools'] = [{'type': known(tool.get('type'), ('function', 'custom', 'namespace'))}
                          if isinstance(tool, dict) else {'type': value_type(tool)} for tool in tools[:64]]
    return shape


class LoopbackServer(http.server.ThreadingHTTPServer):
    def server_bind(self):
        # Numeric loopback listeners need no reverse DNS. HTTPServer's lookup
        # can stall startup before the watchdog or owned client starts.
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address


def tool_contract(tools):
    if not isinstance(tools, list): return False
    for tool in tools:
        if not isinstance(tool, dict): return False
        if tool.get('type') == 'namespace':
            if not tool_contract(tool.get('tools')): return False
        elif tool.get('type') not in ('function', 'custom'):
            return False
        if not isinstance(tool.get('name'), str): return False
    return True


def role(body, main, guardian):
    """Classify the client's captured contracts; the launcher still validates them."""
    if body.get('stream') is not True or not isinstance(body.get('input'), list):
        raise ContractError('stream_or_input')
    if any(body.get(key) is not None for key in ('previous_response_id', 'conversation', 'prompt')):
        raise ContractError('prior_context')
    if not tool_contract(body.get('tools', [])): raise ContractError('tools')
    for item in body['input']:
        if not isinstance(item, dict) or item.get('type', 'message') not in (
                'message', 'function_call', 'function_call_output', 'custom_tool_call',
                'custom_tool_call_output', 'reasoning', 'additional_tools'):
            raise ContractError('input_item')
        if item.get('role') not in (None, 'user', 'assistant', 'system', 'developer'):
            raise ContractError('input_role')
        if 'tools' in item and not tool_contract(item['tools']): raise ContractError('embedded_tools')
        if item.get('type', 'message') == 'message':
            content = item.get('content', [])
            if not isinstance(content, (str, list)): raise ContractError('message_content')
            if isinstance(content, list):
                for part in content:
                    if not isinstance(part, dict) or part.get('type') not in ('input_text', 'output_text', 'input_image'):
                        raise ContractError('message_part')
    metadata = json.loads(body.get('client_metadata', {}).get('x-codex-turn-metadata', '{}'))
    if metadata.get('request_kind') == 'compaction': raise ContractError('compaction')
    title = metadata.get('thread_source') == metadata.get('turn_trigger') == 'thread_title'
    schema = body.get('text', {}).get('format', {})
    if title:
        if body.get('model') not in ('gpt-5.6-luna', 'gpt-6-luna') or schema.get('type') != 'json_schema':
            raise ContractError('title')
        return 'auxiliary_title'
    if metadata.get('thread_source') in ('thread_summary', 'thread_title'):
        raise ContractError('auxiliary')
    review = schema.get('schema') == GUARDIAN_SCHEMA
    if review:
        names = {tool.get('name') for tool in body.get('tools', [])}
        if (body.get('model') != guardian or schema.get('strict') is not False or
                schema.get('type') != 'json_schema' or body.get('tool_choice') != 'auto' or
                not isinstance(body.get('instructions'), str) or
                names != {'exec_command', 'write_stdin', 'view_image'}):
            raise ContractError('guardian')
        return 'guardian'
    if ('outcome' in schema.get('schema', {}).get('properties', {}) or body.get('model') != main):
        raise ContractError('model_or_schema')
    return 'main'


def hashed(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    return {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}


def presentation_tool_advertised(body):
    for namespace, tool in catalog_tools(body):
        if ((namespace in ('mcp__codex_app', 'mcp__tofa_presentation_runtime') and
               tool.get('name') == 'load_workspace_dependencies') or
              (namespace is None and tool.get('name') in ('mcp__codex_app__load_workspace_dependencies',
               'mcp__tofa_presentation_runtime__load_workspace_dependencies'))):
            return True
    return False


def audit(body):
    """Preserve ordering and omission, without exporting instruction/tool text."""
    instructions = []
    tools = []
    if 'instructions' in body:
        instructions.append(dict(source='instructions', role='instructions', **hashed(body['instructions'])))
    for index, item in enumerate(body.get('input', [])):
        # Native clients may deliver workspace/skill instructions in user roles.
        # Hash every such message without guessing which text is instructional.
        if item.get('role') in ('system', 'developer', 'user'):
            instructions.append(dict(source='input', index=index, role=item['role'], **hashed(item.get('content'))))
        if 'tools' in item:
            tools.append(dict(source='input', index=index, **hashed(item['tools'])))
    if 'tools' in body:
        tools.append(dict(source='tools', **hashed(body['tools'])))
    return dict(instructions=instructions, tools=tools, reasoning=hashed(body.get('reasoning')),
                input_types=[item.get('type', 'message') for item in body.get('input', [])],
                input_roles=[item.get('role') for item in body.get('input', [])])


class Observer:
    def __init__(self, run, *, model, guardian, limits, case='05', runtime_qualification=None):
        self.runtime_qualification = None
        if runtime_qualification is not None:
            evidence = runtime_qualification
            verified = qualify(evidence['proof_path'], client=evidence['client'],
                client_identity=evidence['client_identity'], home=Path(evidence['home']),
                skill=Path(evidence['skill']), application_identity=evidence['application_identity'])
            if verified != evidence: raise ValueError('presentation_qualification_drift')
            self.runtime_qualification = verified
        self.run = Path(run)
        self.model, self.guardian, self.limits = model, guardian, limits
        self.secret = secrets.token_hex(32)
        self.endpoint = self.token = None
        self.records = []
        self.used = 0
        self.lock = threading.RLock()
        self.active = set()
        self.done = threading.Event()
        self.reason = None
        self.started = time.monotonic()
        self.deadline = self.started + limits['seconds']
        self.action_watch = Actions(self.run / 'workspace')
        self.actions = self.action_watch.summary
        self.case = case
        self.proposals = set()
        self.main_started = False
        self.initial_user_messages = None
        self.expected_prompt = (self.run / 'prompt.txt').read_text().strip() if (self.run / 'prompt.txt').exists() else None
        variant = self.run / 'workspace/AGENTS.md'
        self.expected_instructions = variant.read_text().strip() if variant.exists() else None
        owner = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *unused): pass

            def reply(self, status, value):
                data = json.dumps(value).encode()
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                self.wfile.flush()

            def do_GET(self):
                self.handle_request()

            def do_POST(self):
                self.handle_request()

            def handle_request(self):
                control = self.path == '/register'
                body = UNAVAILABLE
                self.raw_request = None
                expected = owner.secret if control else owner.token
                if not expected or not hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + expected):
                    self.reply(401, {'error': 'unauthorized'}); return
                with owner.lock:
                    owner.active.add(self.connection)
                try:
                    if control:
                        self.register(); return
                    if self.command == 'GET' and self.path == '/desktop-launch':
                        owner.forward(self, None, None); return
                    if self.command != 'POST' or self.path != '/responses':
                        owner.reject(self, 'unsupported_request_contract', 400); return
                    if self.headers.get('Content-Encoding', 'identity') != 'identity':
                        owner.reject(self, 'unsupported_encoding', 400); return
                    body = self.read_json()
                    if not isinstance(body, dict):
                        owner.reject(self, 'unsupported_request_contract', 400, body,
                                     category='body_type'); return
                    owner.request(self, body)
                except (ValueError, TypeError, KeyError, UnicodeError) as error:
                    owner.reject(self, 'unsupported_request_contract', 400,
                                 UNAVAILABLE if control else body,
                                 category=getattr(error, 'category', 'malformed_contract'))
                except (OSError, http.client.HTTPException):
                    # A disconnected client does not authorize another inference.
                    owner.stop('client_disconnected')
                finally:
                    with owner.lock:
                        owner.active.discard(self.connection)

            def read_json(self):
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= BODY_LIMIT:
                    raise ContractError('body_limit')
                self.connection.settimeout(max(.01, owner.deadline - time.monotonic()))
                raw = self.rfile.read(length)
                if self.path == '/responses': self.raw_request = raw
                return json.loads(raw)

            def register(self):
                body = self.read_json()
                target = urlsplit(body['endpoint'])
                if (target.scheme != 'http' or target.hostname != '127.0.0.1' or not target.port or
                        target.path or target.query or target.fragment or target.username or not body['token']):
                    self.reply(400, {'error': 'loopback_adapter_required'}); return
                with owner.lock:
                    if owner.endpoint is not None:
                        self.reply(409, {'error': 'already_registered'}); return
                    owner.endpoint, owner.token = body['endpoint'], body['token']
                self.reply(200, {'ready': True})

        self.server = LoopbackServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        self.port = self.server.server_port
        self.url = 'http://127.0.0.1:' + str(self.port)

    def persist(self):
        temporary = self.run / 'requests.tmp'
        temporary.write_text(json.dumps(self.records, indent=2) + '\n')
        temporary.chmod(0o600)
        temporary.replace(self.run / 'requests.json')

    def reject(self, handler, reason, status, body=UNAVAILABLE, *, category=None,
               known_role=None, presentation_runtime=None):
        with self.lock:
            record = {'role': 'unknown', 'forwarded': False, 'failure': reason,
                      'rejection_category': category or reason}
            if body is not UNAVAILABLE:
                record['shape'] = request_shape(body, self.model, self.guardian)
            else:
                record['shape'] = {'body': 'unavailable'}
            if known_role:
                record.update(role=known_role, audit=audit(body))
            if presentation_runtime is not None:
                record['presentation_runtime'] = presentation_runtime
            raw_bytes = getattr(handler, 'raw_request', None)
            record['raw_body_retained'] = False
            if raw_bytes is not None:
                raw = self.run / ('rejected-request-' + str(len(self.records) + 1) + '.json')
                try:
                    with open(raw, 'xb', opener=lambda path, flags: os.open(path, flags, 0o600)) as output:
                        output.write(raw_bytes)
                    record['raw_body_retained'] = True
                except OSError:
                    record.update(failure='diagnostic_capture_failure', original_rejection=reason)
                    status = 500
            self.records.append(record)
            try:
                self.persist()
            except OSError:
                record['failure'] = 'diagnostic_capture_failure'
                self.stop('diagnostic_capture_failure')
                raise
        handler.reply(status, {'error': record['failure']})
        self.stop(record['failure'])

    def request(self, handler, body):
        try:
            kind = role(body, self.model, self.guardian)
            cap = body.get('max_output_tokens', self.limits['output_tokens'])
            if type(cap) is not int or cap <= 0: raise ContractError('output_token_cap')
        except (ValueError, TypeError, AttributeError) as error:
            self.reject(handler, 'unsupported_request_contract', 400, body,
                        category=getattr(error, 'category', 'malformed_contract')); return
        with self.lock:
            if self.expected_prompt:
                encoded_input = json.dumps(body['input'], ensure_ascii=False)
                # Each run is a fresh workspace and conversation. The observer
                # never admits an existing conversation merely because it uses
                # this launch's main model. Title calls must name this same task.
                if kind == 'main':
                    user_messages = hashed([item for item in body['input'] if item.get('role') == 'user'])
                    text = '\n'.join(item.get('content', '') if isinstance(item.get('content'), str)
                        else '\n'.join(part.get('text', '') for part in item.get('content', []) if isinstance(part, dict))
                        for item in body['input'] if item.get('role') == 'user')
                    old_history = any(item.get('role') == 'assistant' or item.get('type') in
                        ('function_call', 'function_call_output', 'custom_tool_call', 'custom_tool_call_output') for item in body['input'])
                    if (self.expected_prompt not in text or str(self.run / 'workspace') not in text or
                            not self.main_started and old_history or
                            self.main_started and user_messages != self.initial_user_messages):
                        self.reject(handler, 'scope_mismatch', 403, body); return
                    self.initial_user_messages = user_messages
                    self.main_started = True
                elif kind == 'guardian' and not self.main_started:
                    self.reject(handler, 'scope_mismatch', 403, body); return
                elif kind == 'auxiliary_title' and self.expected_prompt not in encoded_input:
                    self.reject(handler, 'scope_mismatch', 403, body); return
            if kind == 'main' and self.expected_instructions:
                # The client chooses the instruction role; verify delivery at
                # this boundary instead of assuming the file was discovered.
                if json.dumps(self.expected_instructions, ensure_ascii=False)[1:-1] not in json.dumps(body, ensure_ascii=False):
                    self.reject(handler, 'instruction_variant_missing', 400, body); return
            if self.case in ('03', '04'):
                try: advertised = ('present' if presentation_tool_advertised(body) else 'absent') if kind == 'main' else 'not_observed'
                except ValueError:
                    self.reject(handler, 'presentation_runtime_tool_invalid', 400, body, known_role=kind); return
                evidence = self.runtime_qualification
                try:
                    current = qualify(evidence['proof_path'], client=evidence['client'],
                        client_identity=evidence['client_identity'], home=Path(evidence['home']),
                        skill=Path(evidence['skill']), application_identity=evidence['application_identity']) if evidence else None
                    qualified = evidence is not None and current == evidence
                except (OSError, ValueError, TypeError):
                    self.reject(handler, 'presentation_runtime_environment_drift', 400, body, known_role=kind,
                        presentation_runtime={'advertised': advertised, 'qualified': False}); return
                try: callable_loader = bool(loader_tools(body, evidence['provider'])) if qualified and kind == 'main' else True
                except ValueError: callable_loader = False
                if not qualified or not callable_loader:
                    reason = 'presentation_runtime_tool_missing' if advertised == 'absent' else 'presentation_runtime_unqualified'
                    self.reject(handler, reason, 400, body, known_role=kind,
                        presentation_runtime={'required_tool': 'load_workspace_dependencies',
                                              'advertised': advertised, 'qualified': False}); return
                if kind == 'main':
                    try:
                        for call in body['input']:
                            if not loader_call(call, evidence['provider']): continue
                            outputs = [item.get('output') for item in body['input'] if
                                item.get('type') == 'function_call_output' and item.get('call_id') == call.get('call_id')]
                            if json.loads(call.get('arguments', 'null')) != {} or len(outputs) != 1 or (
                                    from_loader_output(outputs[0], evidence['provider']) != evidence['runtime']):
                                raise ValueError('live_loader_result_invalid')
                    except (OSError, ValueError, TypeError):
                        self.reject(handler, 'presentation_runtime_result_invalid', 400, body, known_role=kind,
                            presentation_runtime={'advertised': advertised, 'qualified': False}); return
            if kind == 'main':
                failure = self.action_watch.observe(body)
                if failure:
                    self.reject(handler, failure, 429, body); return
            if self.reason or self.used >= self.limits['requests']:
                self.reject(handler, self.reason or 'request_budget_limit', 429, body); return
            if time.monotonic() >= self.deadline:
                self.reject(handler, 'deadline', 429, body); return
            self.used += 1
            record = dict(number=self.used, role=kind, model=body['model'], forwarded=True,
                          routed_model=NAMING_MODEL if kind == 'auxiliary_title' else body['model'],
                          audit=audit(body), completed=False, started_ms=self.elapsed())
            if kind == 'main': record['instruction_variant_observed'] = self.expected_instructions is not None
            self.records.append(record)
            self.persist()
        raw = self.run / ('request-' + str(record['number']) + '.json')
        raw.write_text(json.dumps(body)); raw.chmod(0o600)
        body['max_output_tokens'] = min(cap, self.limits['output_tokens'])
        body['parallel_tool_calls'] = False
        record['output_token_cap'] = body['max_output_tokens']
        record['parallel_tool_calls'] = False
        self.forward(handler, body, record)

    def elapsed(self):
        return round((time.monotonic() - self.started) * 1000, 3)

    def forward(self, handler, body, record):
        target = urlsplit(self.endpoint)
        connection = http.client.HTTPConnection(target.hostname, target.port,
            timeout=max(.01, self.deadline - time.monotonic()))
        finished = threading.Event()
        def disconnect():
            while not finished.wait(.02):
                try:
                    ready, _, _ = select.select([handler.connection], [], [], 0)
                    if ready and not handler.connection.recv(1, socket.MSG_PEEK):
                        if record is not None and not record.get('completed'):
                            self.stop('client_disconnected')
                        return
                except OSError:
                    return
        watcher = threading.Thread(target=disconnect, daemon=True)
        watcher.start()
        try:
            connection.connect()
            with self.lock: self.active.add(connection.sock)
            upstream_socket = connection.sock
            headers = {'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/json'}
            if record is None:
                for key in ('X-Tofa-Parent-Pid', 'X-Tofa-Main-Engine-Pid'):
                    if handler.headers.get(key): headers[key] = handler.headers[key]
            connection.request(handler.command, handler.path, None if body is None else json.dumps(body), headers)
            response = connection.getresponse()
            if record is not None:
                record.update(status=response.status, headers_ms=self.elapsed())
            handler.send_response(response.status)
            handler.send_header('Content-Type', response.getheader('Content-Type', 'application/json'))
            handler.end_headers()
            total, pending = 0, b''
            while True:
                if time.monotonic() >= self.deadline: raise TimeoutError()
                chunk = response.read1(65536)
                if not chunk: break
                total += len(chunk)
                if total > RESPONSE_LIMIT: raise ValueError('response_body_limit')
                if record is None or response.status != 200:
                    handler.wfile.write(chunk); handler.wfile.flush(); continue
                pending += chunk
                if len(pending) > EVENT_LIMIT: raise ValueError('event_body_limit')
                while True:
                    boundary = re.search(rb'\r?\n\r?\n', pending)
                    if not boundary: break
                    framed, pending = pending[:boundary.end()], pending[boundary.end():]
                    data = b'\n'.join(line[5:].lstrip(b' ') for line in framed.splitlines() if line.startswith(b'data:'))
                    if data and data != b'[DONE]': self.event(record, json.loads(data))
                    handler.wfile.write(framed); handler.wfile.flush()
                if record['completed']: break
            if record is not None and not record['completed']:
                record['failure'] = 'upstream_http_error' if response.status != 200 else 'response_incomplete'
        except (OSError, http.client.HTTPException, ValueError, TypeError, AttributeError, KeyError) as error:
            if isinstance(error, TimeoutError) or time.monotonic() >= self.deadline:
                self.stop('deadline')
            elif str(error) == 'diagnostic_call_limit':
                self.stop('diagnostic_call_limit')
            if record is not None:
                record['failure'] = self.reason or ('deadline' if isinstance(error, TimeoutError) else 'stream_failure')
        finally:
            finished.set()
            watcher.join(timeout=2)
            with self.lock:
                if 'upstream_socket' in locals(): self.active.discard(upstream_socket)
                if record is not None:
                    record['ended_ms'] = self.elapsed()
                    self.persist()
            connection.close()

    def event(self, record, event):
        if not isinstance(event, dict): raise ValueError('unsupported_response_contract')
        if event.get('type') in ('response.output_text.delta', 'response.function_call_arguments.delta'):
            record.setdefault('first_delta_ms', self.elapsed())
        items = ([event.get('item', {})] if event.get('type') == 'response.output_item.done' else
                 event.get('response', {}).get('output', []) if event.get('type') == 'response.completed' else [])
        if record['role'] == 'main' and self.case == '07':
            for item in items:
                if item.get('type') not in ('function_call', 'custom_tool_call'): continue
                identity = item.get('call_id')
                if not identity: raise ValueError('unsupported_tool_contract')
                arguments = json.loads(item.get('arguments', '{}')) if item['type'] == 'function_call' else {}
                if identity in self.proposals or polling(item.get('name'), arguments): continue
                if len(self.proposals) >= 3: raise ValueError('diagnostic_call_limit')
                self.proposals.add(identity)
        if event.get('type') == 'response.completed':
            response = event['response']
            if response.get('model', record['routed_model']) != record['routed_model']:
                raise ValueError('response_model_mismatch')
            record['completed'] = True
            record['usage'] = {key: value for key, value in response.get('usage', {}).items()
                               if key in ('input_tokens', 'output_tokens', 'total_tokens') and type(value) is int and value >= 0}
            if record['usage'].get('output_tokens', 0) > record['output_token_cap']:
                record['completed'] = False
                self.stop('provider_output_limit_violation')
                raise ValueError('provider_output_limit_violation')
            record['output_sha256'] = hashed(response.get('output', []))['sha256']
            if record['role'] == 'main':
                text = ''.join(part.get('text', '') for item in response.get('output', [])
                    if item.get('type') == 'message' for part in item.get('content', [])
                    if part.get('type') == 'output_text')
                record['final_answer'] = bool(text) and not any(item.get('type') in ('function_call', 'custom_tool_call')
                    for item in response.get('output', []))
                if text:
                    path = self.run / 'final.txt'
                    path.write_text(text); path.chmod(0o600)

    def stop(self, reason):
        with self.lock:
            if self.reason: return
            self.reason = reason
            (self.run / 'stop-reason.txt').write_text(reason)
            for stream in list(self.active):
                try: stream.shutdown(socket.SHUT_RDWR)
                except OSError: pass
        if self.endpoint:
            target = urlsplit(self.endpoint)
            connection = http.client.HTTPConnection(target.hostname, target.port, timeout=1)
            try:
                connection.request('POST', '/evaluation-stop', b'', {'Authorization': 'Bearer ' + self.token})
                connection.getresponse().read()
            except (OSError, http.client.HTTPException): pass
            finally: connection.close()

    def __enter__(self):
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        def deadline():
            if not self.done.wait(max(0, self.deadline - time.monotonic())):
                self.stop('deadline')
        self.watchdog = threading.Thread(target=deadline, daemon=True)
        self.watchdog.start()
        return self

    def __exit__(self, *unused):
        with self.lock:
            active = bool(self.active)
        if active: self.stop(self.reason or 'observer_closed')
        self.done.set()
        self.server.shutdown(); self.server.server_close()
        self.thread.join(); self.watchdog.join(timeout=2)
        with self.lock: self.persist()
