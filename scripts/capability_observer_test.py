"""Synthetic actual-client HTTP boundary tests; never contact a provider."""
import http.client
import http.server
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from capability_observer import LoopbackServer, Observer

SCRIPT_ROOT = Path(__file__).resolve().parent.parent


class BoundaryTests(unittest.TestCase):
    def test_provider_terminal_errors_are_private_and_distinct_from_truncation(self):
        for kind in ('response.failed', 'response.incomplete', 'error'):
            event = {'type': kind, 'response': {'error': {'message': 'private-provider-error'}}}
            raw = ('data: ' + json.dumps(event) + '\n\n').encode()
            def failed(handler, body):
                handler.send_response(200); handler.end_headers(); handler.wfile.write(raw)
            with self.subTest(kind=kind), self.boundary(response=failed) as (observer, _):
                self.assertEqual(self.post(observer, '/responses', self.body(), 'client-token', 200), raw)
                record = observer.records[0]
                self.assertEqual(record.get('provider_failure'), {'event_type': kind})
                self.assertEqual(record['transport_failure']['category'], 'provider_error')
                self.assertFalse(record['completed'])
                self.assertNotIn('private-provider-error', json.dumps(observer.records))
                private = observer.run / 'provider-error-1.json'
                self.assertEqual(private.stat().st_mode & 0o777, 0o600)
                self.assertIn('private-provider-error', private.read_text())

    def test_http_rejection_and_incomplete_stream_have_distinct_diagnostics(self):
        for status, category in ((400, 'http_status'), (200, 'incomplete_response')):
            def rejected(handler, body):
                handler.send_response(status); handler.end_headers()
                handler.wfile.write(b'private-provider-detail' if status == 400 else b'data: [DONE]\n\n')
            with self.subTest(status=status), self.boundary(response=rejected) as (observer, _):
                self.post(observer, '/responses', self.body(), 'client-token', status)
                self.assertEqual(observer.records[0].get('transport_failure'), {
                    'stage': 'upstream_read', 'category': category, 'exception_type': None})
                self.assertNotIn('private-provider-detail', json.dumps(observer.records))

    def test_private_upstream_status_text_never_enters_exported_records(self):
        def malformed(handler, body):
            handler.wfile.write(b'private-prompt-token\r\n\r\n')
        with self.boundary(response=malformed) as (observer, _):
            with self.assertRaises(http.client.RemoteDisconnected):
                self.post(observer, '/responses', self.body(), 'client-token', 200)
            record = observer.records[0]
            self.assertEqual(record['transport_failure'], {
                'stage': 'upstream_headers', 'category': 'invalid_headers',
                'exception_type': 'BadStatusLine'})
            self.assertNotIn('private-prompt-token', json.dumps(observer.records))
            self.assertIn('private-prompt-token', (observer.run / 'transport-error-1.json').read_text())

    def test_naming_disconnect_before_headers_retains_private_exception(self):
        def disconnected(handler, body):
            handler.close_connection = True
        title = json.loads((SCRIPT_ROOT / 'internal/tofa/testdata/desktop-luna6-title-request.json').read_text())
        with self.boundary(response=disconnected) as (observer, seen):
            with self.assertRaises(http.client.RemoteDisconnected):
                self.post(observer, '/responses', title, 'client-token', 200)
            record = observer.records[0]
            self.assertEqual(record['failure'], 'stream_failure')
            self.assertEqual(record.get('transport_failure'), {
                'stage': 'upstream_headers', 'category': 'peer_closed',
                'exception_type': 'RemoteDisconnected'})
            private = observer.run / 'transport-error-1.json'
            self.assertEqual(private.stat().st_mode & 0o777, 0o600)
            self.assertIn('RemoteDisconnected', json.loads(private.read_text())['traceback'])
            self.assertIsNone(observer.reason)

    def test_deck_naming_cannot_infer_before_runtime_qualification(self):
        title = json.loads((SCRIPT_ROOT / 'internal/tofa/testdata/desktop-luna6-title-request.json').read_text())
        with self.boundary(case='03') as (observer, seen):
            self.post(observer, '/responses', title, 'client-token', 400)
            self.assertEqual(seen, [])
            self.assertEqual(observer.reason, 'presentation_runtime_unqualified')
            self.assertEqual(observer.records[0]['role'], 'auxiliary_title')
            self.assertEqual(observer.records[0]['presentation_runtime']['advertised'], 'not_observed')

    def test_advertised_loader_does_not_qualify_a_deck_runtime(self):
        body = self.body()
        body['input'] = [{'type': 'additional_tools', 'tools': [
            {'type': 'namespace', 'name': 'mcp__tofa_presentation_runtime', 'tools': [
                {'type': 'function', 'name': 'load_workspace_dependencies',
                 'parameters': {'type': 'object'}}]}]}]
        with self.boundary(case='04') as (observer, seen):
            self.post(observer, '/responses', body, 'client-token', 400)
            self.assertEqual(seen, [])
            self.assertEqual(observer.reason, 'presentation_runtime_unqualified')
            self.assertEqual(observer.records[0]['presentation_runtime'], {
                'required_tool': 'load_workspace_dependencies',
                'advertised': 'present', 'qualified': False})

    def test_unrelated_mcp_provider_with_the_same_loader_name_is_not_admitted(self):
        body = self.body()
        body['tools'] = [{'type': 'namespace', 'name': 'mcp__unrelated', 'tools': [
            {'type': 'function', 'name': 'load_workspace_dependencies', 'parameters': {
                'type': 'object', 'properties': {}, 'additionalProperties': False}}]}]
        with self.boundary(case='03') as (observer, seen):
            self.post(observer, '/responses', body, 'client-token', 400)
            self.assertEqual(observer.reason, 'presentation_runtime_tool_missing')
            self.assertEqual(seen, [])

    def test_deck_missing_required_runtime_tool_stops_before_inference(self):
        body = self.body()
        body['tools'] = [{'type': 'namespace', 'name': 'functions', 'tools': [
            {'type': 'function', 'name': 'exec_command', 'parameters': {'type': 'object'}}]}]
        with self.boundary(case='03') as (observer, seen):
            self.post(observer, '/responses', body, 'client-token', 400)
            self.assertEqual(seen, [])
            self.assertEqual(observer.reason, 'presentation_runtime_tool_missing')
            record = observer.records[0]
            self.assertEqual(record['role'], 'main')
            self.assertFalse(record['forwarded'])
            self.assertEqual(record['presentation_runtime'], {
                'required_tool': 'load_workspace_dependencies',
                'advertised': 'absent', 'qualified': False})
            self.assertEqual(record['audit']['tools'][0]['source'], 'tools')
            self.assertNotIn('exec_command', json.dumps(record))
            self.assertTrue(record['raw_body_retained'])

    def test_listener_registration_does_not_require_reverse_dns(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory); (run / 'workspace').mkdir()
            with patch('socket.getfqdn', side_effect=AssertionError('unexpected reverse DNS')):
                with Observer(run, model='moonshotai/Kimi-K3', guardian='zai-org/GLM-5.3-Flash',
                              limits={'seconds': 180, 'requests': 12, 'output_tokens': 4096}) as observer:
                    self.post(observer, '/register', {'endpoint': 'http://127.0.0.1:1',
                              'token': 'client-token'}, observer.secret, 200)

    @contextmanager
    def boundary(self, limits=None, response=None, case='05', prompt=None, guardian='zai-org/GLM-5.3-Flash', qualification=None):
        seen = []
        class Upstream(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_POST(self):
                if self.path == '/evaluation-stop':
                    self.send_response(204); self.end_headers(); return
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                seen.append(body)
                if response:
                    response(self, body); return
                self.send_response(200); self.send_header('Content-Type', 'text/event-stream'); self.end_headers()
                model = 'nvidia/Nemotron-3_5-Lightning' if body['model'].startswith('gpt-') else body['model']
                event = {'type': 'response.completed', 'response': {'model': model, 'output': [],
                         'usage': {'input_tokens': 3, 'output_tokens': 2}}}
                self.wfile.write(('data: ' + json.dumps(event) + '\n\n').encode())
        server = LoopbackServer(('127.0.0.1', 0), Upstream)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                run = Path(directory); (run / 'workspace').mkdir()
                if prompt: (run / 'prompt.txt').write_text(prompt)
                with Observer(run, model='moonshotai/Kimi-K3', guardian=guardian,
                        limits=limits or {'seconds': 180, 'requests': 12, 'output_tokens': 4096}, case=case,
                        runtime_qualification=qualification) as observer:
                    self.post(observer, '/register', {'endpoint': 'http://127.0.0.1:' + str(server.server_port),
                              'token': 'client-token'}, observer.secret, 200)
                    yield observer, seen
        finally:
            server.shutdown(); server.server_close()

    def body(self):
        return {'model': 'moonshotai/Kimi-K3', 'stream': True, 'input': [], 'tools': []}

    def test_image_guardian_and_independent_title_share_the_bound(self):
        guardian = self.body()
        guardian.update(model='zai-org/GLM-5.3-Flash', instructions='Native policy', tool_choice='auto',
            tools=[{'type': 'function', 'name': name, 'parameters': {'type': 'object'}}
                   for name in ('exec_command', 'write_stdin', 'view_image')],
            text={'format': {'type': 'json_schema', 'strict': False, 'schema': {
                'type': 'object', 'additionalProperties': False, 'required': ['outcome'],
                'properties': {'outcome': {'type': 'string', 'enum': ['allow', 'deny']},
                    'risk_level': {'type': 'string', 'enum': ['low', 'medium', 'high', 'critical']},
                    'user_authorization': {'type': 'string', 'enum': ['unknown', 'low', 'medium', 'high']},
                    'rationale': {'type': 'string'}}}}})
        image = self.body()
        image['input'] = [{'role': 'user', 'content': [{'type': 'input_image', 'image_url': 'data:image/png;base64,eA=='}]}]
        title = json.loads((SCRIPT_ROOT / 'internal/tofa/testdata/desktop-luna6-title-request.json').read_text())
        with self.boundary(limits={'seconds': 180, 'requests': 3, 'output_tokens': 4096}) as (observer, seen):
            for body in (image, guardian, title):
                self.post(observer, '/responses', body, 'client-token', 200)
            self.post(observer, '/responses', self.body(), 'client-token', 429)
            self.assertEqual([r['role'] for r in observer.records[:3]], ['main', 'guardian', 'auxiliary_title'])
            self.assertTrue(all(r['completed'] for r in observer.records[:3]))
            self.assertEqual([body['model'] for body in seen], ['moonshotai/Kimi-K3', 'zai-org/GLM-5.3-Flash', 'gpt-6-luna'])
            self.assertEqual(seen[0]['input'], image['input'])
            self.assertEqual(seen[1]['text'], guardian['text'])
            self.assertEqual(observer.records[2]['routed_model'], 'nvidia/Nemotron-3_5-Lightning')

    def test_unknown_contract_never_reaches_upstream(self):
        for change in ({'tools': [{'type': 'remote_inference'}]}, {'previous_response_id': 'private-id'},
                       {'model': 'unselected/model'}, {'input': [{'type': 'future_item'}]}):
            with self.subTest(change=change), self.boundary() as (observer, seen):
                body = self.body(); body.update(change)
                self.post(observer, '/responses', body, 'client-token', 400)
                self.assertEqual(seen, [])
                self.assertEqual(observer.reason, 'unsupported_request_contract')

    def test_rejected_contract_retains_private_body_and_exports_only_shape(self):
        body = self.body()
        body.update(previous_response_id='private-native-id',
                    client_metadata={'private-key': 'private-token'},
                    tools=[{'type': 'function', 'name': 'private-tool',
                            'description': 'private-prompt'}])
        body['input'] = [{'role': 'user', 'content': 'private-prompt'}]
        with self.boundary() as (observer, seen):
            self.post(observer, '/responses', body, 'client-token', 400)
            record = observer.records[0]
            self.assertEqual(record['rejection_category'], 'prior_context')
            self.assertEqual(record['shape']['fields']['previous_response_id'], 'string')
            self.assertEqual(record['shape']['input'][0],
                             {'type': 'message', 'role': 'user', 'content': 'string'})
            self.assertEqual(record['shape']['tools'], [{'type': 'function'}])
            raw = observer.run / 'rejected-request-1.json'
            self.assertEqual(json.loads(raw.read_text()), body)
            self.assertEqual(raw.stat().st_mode & 0o777, 0o600)
            self.assertEqual(seen, [])
            self.assertNotIn('private-', json.dumps(observer.records))

    def test_unknown_shape_names_are_redacted_and_diagnostics_are_bounded(self):
        body = self.body()
        body['private-key'] = 'private-token'
        body['input'] = [{'type': 'private-future-item', 'role': 'private-role'}] * 100
        with self.boundary() as (observer, seen):
            self.post(observer, '/responses', body, 'client-token', 400)
            record = observer.records[0]
            self.assertEqual(record['rejection_category'], 'input_item')
            self.assertEqual(record['shape']['unknown_fields'], 1)
            self.assertEqual(record['shape']['input_count'], 100)
            self.assertLessEqual(len(record['shape']['input']), 64)
            self.assertEqual(record['shape']['input'][0]['type'], 'unknown')
            self.assertNotIn('private-', json.dumps(observer.records))
            self.assertEqual(seen, [])

    def test_rejected_null_and_malformed_json_retain_only_private_raw_bytes(self):
        for raw, shape in ((b'null', {'body': 'null'}),
                           (b'{"private-value":', {'body': 'unavailable'})):
            with self.subTest(raw=raw), self.boundary() as (observer, seen):
                connection = http.client.HTTPConnection('127.0.0.1', observer.port, timeout=2)
                connection.request('POST', '/responses', raw, {'Authorization': 'Bearer client-token'})
                response = connection.getresponse(); response.read(); connection.close()
                self.assertEqual(response.status, 400)
                self.assertEqual(observer.records[0]['shape'], shape)
                self.assertEqual((observer.run / 'rejected-request-1.json').read_bytes(), raw)
                self.assertNotIn('private-', json.dumps(observer.records))
                self.assertEqual(seen, [])

    def test_current_desktop_developer_role_review_is_an_observer_block(self):
        # Structural replay of engine 0.162.0-alpha.17.2, with policy text and
        # native IDs removed. This is a contract limit, not a Guardian decision.
        body = json.loads((SCRIPT_ROOT / 'scripts/fixtures/current-desktop-review-shape.json').read_text())
        with self.boundary(guardian='moonshotai/Kimi-K3') as (observer, seen):
            self.post(observer, '/responses', body, 'client-token', 400)
            record = observer.records[0]
            self.assertEqual(record['rejection_category'], 'guardian')
            self.assertEqual(record['shape']['fields']['instructions'], 'null')
            self.assertEqual(record['shape']['input'][0]['role'], 'developer')
            self.assertEqual(record['shape']['model_matches'], ['main', 'guardian'])
            self.assertTrue(record['shape']['format']['guardian_schema_matches'])
            self.assertTrue(record['raw_body_retained'])
            self.assertEqual(observer.reason, 'unsupported_request_contract')
            self.assertEqual(seen, [])

    def test_unauthenticated_body_is_never_captured(self):
        with self.boundary() as (observer, seen):
            self.post(observer, '/responses', {'private-key': 'private-token'}, 'wrong-token', 401)
            self.assertEqual(observer.records, [])
            self.assertFalse(list(observer.run.glob('rejected-request-*')))
            self.assertEqual(seen, [])

    def test_private_capture_failure_stops_without_overwriting_evidence(self):
        with self.boundary() as (observer, seen):
            existing = observer.run / 'rejected-request-1.json'
            existing.write_text('retained earlier evidence')
            body = self.body(); body['previous_response_id'] = 'private-native-id'
            self.post(observer, '/responses', body, 'client-token', 500)
            self.assertEqual(observer.reason, 'diagnostic_capture_failure')
            self.assertEqual(observer.records[0]['failure'], 'diagnostic_capture_failure')
            self.assertFalse(observer.records[0]['raw_body_retained'])
            self.assertEqual(existing.read_text(), 'retained earlier evidence')
            self.assertEqual(seen, [])

    def test_absolute_deadline_bounds_stalled_and_trickling_streams(self):
        for trickle in (False, True):
            def slow(handler, body):
                handler.send_response(200); handler.end_headers()
                try:
                    for _ in range(100):
                        if trickle:
                            handler.wfile.write(b': keepalive\n\n'); handler.wfile.flush()
                        time.sleep(.02)
                except OSError:
                    pass
            start = time.monotonic()
            with self.subTest(trickle=trickle), self.boundary(
                    limits={'seconds': .25, 'requests': 12, 'output_tokens': 4096}, response=slow) as (observer, seen):
                self.post(observer, '/responses', self.body(), 'client-token', 200)
                self.assertLess(time.monotonic() - start, 1)
                self.assertEqual(observer.reason, 'deadline')
                self.assertEqual(len(seen), 1)

    def test_crlf_multiline_events_and_compact_data_fields_are_observed(self):
        def framed(handler, body):
            handler.send_response(200); handler.end_headers()
            handler.wfile.write(b'data:{"type":"response.completed",\r\ndata: "response":{"model":"moonshotai/Kimi-K3","output":[],"usage":{"output_tokens":2}}}\r\n\r\n')
        with self.boundary(response=framed) as (observer, _):
            self.post(observer, '/responses', self.body(), 'client-token', 200)
            self.assertTrue(observer.records[0]['completed'])
            self.assertEqual(observer.records[0]['usage']['output_tokens'], 2)

    def test_title_disconnect_does_not_stop_main(self):
        for send_headers in (False, True):
            title_started = threading.Event()
            title_closed = threading.Event()
            release_main = threading.Event()
            def upstream(handler, body):
                if body['model'].startswith('gpt-'):
                    if send_headers:
                        handler.send_response(200); handler.end_headers(); handler.wfile.flush()
                    title_started.set()
                    handler.connection.settimeout(3)
                    try:
                        if not handler.connection.recv(1): title_closed.set()
                    except OSError: pass
                else:
                    handler.send_response(200); handler.end_headers(); handler.wfile.flush()
                    release_main.wait(3)
                    event = {'type': 'response.completed', 'response': {'model': body['model'], 'output': []}}
                    try: handler.wfile.write(('data: ' + json.dumps(event) + '\n\n').encode())
                    except OSError: pass
            with self.subTest(send_headers=send_headers), self.boundary(response=upstream) as (observer, seen):
                title = json.loads((SCRIPT_ROOT / 'internal/tofa/testdata/desktop-luna6-title-request.json').read_text())
                clients, responses = [], []
                try:
                    for body in (title, self.body()):
                        client = http.client.HTTPConnection('127.0.0.1', observer.port, timeout=3)
                        clients.append(client)
                        client.request('POST', '/responses', json.dumps(body), {'Authorization': 'Bearer client-token'})
                        if body is title:
                            self.assertTrue(title_started.wait(1))
                            responses.append(client.getresponse() if send_headers else None)
                        else: responses.append(client.getresponse())
                    if responses[0] is not None: responses[0].close()
                    clients[0].close()
                    self.assertTrue(title_closed.wait(1), 'cancelled title left its upstream request alive')
                    self.assertIsNone(observer.reason, 'title cancellation stopped the entire run')
                    release_main.set(); responses[1].read()
                    self.assertTrue(observer.records[1]['completed'])
                    self.assertEqual(observer.records[0]['failure'], 'client_disconnected')
                    self.assertEqual(observer.records[0]['client_disconnect']['source'], 'socket_eof')
                    self.assertEqual(len(seen), 2, 'cancellation must not retry either request')
                    self.assertEqual(observer.used, 2, 'cancelled naming still consumes its request budget')
                finally:
                    release_main.set()
                    for response in responses:
                        if response is not None: response.close()
                    for client in clients: client.close()

    def test_native_client_disconnect_cancels_a_stalled_upstream(self):
        closed = threading.Event()
        def stalled(handler, body):
            handler.send_response(200); handler.end_headers(); handler.wfile.flush()
            handler.connection.settimeout(3)
            try:
                if not handler.connection.recv(1): closed.set()
            except OSError: pass
        with self.boundary(response=stalled) as (observer, seen):
            connection = http.client.HTTPConnection('127.0.0.1', observer.port, timeout=2)
            connection.request('POST', '/responses', json.dumps(self.body()), {'Authorization': 'Bearer client-token'})
            response = connection.getresponse()
            response.close(); connection.close()
            self.assertTrue(closed.wait(.75), 'cancelled client left its upstream inference alive')
            self.assertEqual(observer.reason, 'client_disconnected')

    def test_instruction_audit_preserves_roles_order_and_embedded_tools(self):
        body = self.body()
        body['instructions'] = ''
        body['input'] = [{'role': 'developer', 'content': 'private-first'},
            {'role': 'system', 'content': 'private-second'},
            {'role': 'user', 'content': 'private-workspace-AGENTS-instructions'},
            {'type': 'additional_tools', 'role': 'developer', 'id': 'private-id',
             'tools': [{'name': 'functions', 'type': 'namespace', 'tools': [
                 {'type': 'custom', 'name': 'exec', 'format': {'type': 'grammar', 'definition': 'private grammar'}}]}]}]
        with self.boundary() as (observer, seen):
            self.post(observer, '/responses', body, 'client-token', 200)
            audit = observer.records[0]['audit']
            self.assertEqual([i['role'] for i in audit['instructions']], ['instructions', 'developer', 'system', 'user', 'developer'])
            self.assertEqual(audit['instructions'][3]['index'], 2)
            self.assertEqual(len(audit['instructions'][3]['sha256']), 64)
            self.assertEqual(audit['tools'][0]['source'], 'input')
            self.assertEqual(seen[0]['input'], body['input'])
            self.assertNotIn('private-', json.dumps(observer.records))

    def history(self, number, command='cat missing.txt', output='unchanged', tool='exec_command', args=None):
        return [{'type': 'function_call', 'name': tool, 'call_id': 'call-' + str(number),
                 'arguments': json.dumps(args or {'cmd': command})},
                {'type': 'function_call_output', 'call_id': 'call-' + str(number),
                 'output': 'Chunk ID: ' + str(number) + '\nWall time: 0.' + str(number) +
                           ' seconds\nProcess exited with code 0\nOutput:\n' + output}]

    def test_five_equivalent_completed_actions_stop_before_more_inference(self):
        with self.boundary() as (observer, seen):
            body = self.body()
            for number in range(1, 6):
                body['input'] += self.history(number, command='cat  missing.txt' if number % 2 else 'cat missing.txt')
                self.post(observer, '/responses', body, 'client-token', 429 if number == 5 else 200)
            self.assertEqual(len(seen), 4)
            self.assertEqual(observer.reason, 'repeated_action_without_progress')

    def test_polling_and_real_workspace_progress_do_not_form_a_loop(self):
        for progress in (False, True):
            with self.subTest(progress=progress), self.boundary() as (observer, seen):
                body = self.body()
                for number in range(1, 7):
                    if progress:
                        (observer.run / 'workspace/progress.txt').write_text(str(number))
                        body['input'] += self.history(number)
                    else:
                        body['input'] += self.history(number, tool='write_stdin', args={'session_id': 12, 'chars': ''})
                    self.post(observer, '/responses', body, 'client-token', 200)
                self.assertIsNone(observer.reason)
                self.assertEqual(len(seen), 6)

    def test_timing_shaped_content_inside_tool_output_is_real_progress(self):
        with self.boundary() as (observer, seen):
            body = self.body()
            for number in range(1, 7):
                body['input'] += self.history(number, output='Measured job result\nWall time: 0.' + str(number) + ' seconds\n')
                self.post(observer, '/responses', body, 'client-token', 200)
            self.assertIsNone(observer.reason)

    def test_quote_semantics_are_not_collapsed_into_action_equivalence(self):
        with self.boundary() as (observer, _):
            body = self.body()
            for number in range(1, 7):
                command = 'printf "$VALUE"' if number % 2 else "printf '$VALUE'"
                body['input'] += self.history(number, command=command)
                self.post(observer, '/responses', body, 'client-token', 200)
            self.assertIsNone(observer.reason)

    def test_probe_failure_is_recorded_even_when_the_shell_exits_zero(self):
        with self.boundary() as (observer, seen):
            body = self.body()
            body['input'] = self.history(1, command='python3 probe.py; printf done',
                output='TOFA_RECOVERY_FAILURE_V3: required synthetic dependency unavailable; exit=2\ndone')
            self.post(observer, '/responses', body, 'client-token', 200)
            self.assertTrue(observer.actions['probe_failure_observed'])
            self.assertEqual(observer.actions['diagnostic_calls'], 1)

    def test_fourth_recovery_tool_proposal_is_not_delivered(self):
        def proposals(handler, body):
            handler.send_response(200); handler.end_headers()
            items = [{'type': 'function_call', 'name': 'exec_command', 'call_id': 'call-' + str(i),
                      'arguments': '{"cmd":"true"}'} for i in range(4)]
            event = {'type': 'response.completed', 'response': {'model': body['model'], 'output': items}}
            handler.wfile.write(('data: ' + json.dumps(event) + '\n\n').encode())
        with self.boundary(case='07', response=proposals) as (observer, seen):
            output = self.post(observer, '/responses', self.body(), 'client-token', 200)
            self.assertNotIn(b'call-3', output)
            self.assertEqual(observer.reason, 'diagnostic_call_limit')
            self.assertEqual(seen[0]['parallel_tool_calls'], False)

    def test_run_scope_rejects_an_existing_or_unrelated_conversation(self):
        for existing in (False, True):
            with self.subTest(existing=existing), self.boundary(prompt='exact synthetic prompt') as (observer, seen):
                body = self.body()
                body['input'] = [{'role': 'user', 'content': 'exact synthetic prompt\n<cwd>' +
                    str(observer.run / 'workspace') + '</cwd>' if existing else 'another private conversation'}]
                if existing: body['input'].insert(0, {'role': 'assistant', 'content': 'older answer'})
                self.post(observer, '/responses', body, 'client-token', 403)
                self.assertEqual(seen, [])

    def test_new_user_task_cannot_reuse_the_original_prompt_in_history(self):
        with self.boundary(prompt='exact synthetic prompt') as (observer, seen):
            body = self.body()
            body['input'] = [{'role': 'user', 'content': 'exact synthetic prompt\n<cwd>' +
                str(observer.run / 'workspace') + '</cwd>'}]
            self.post(observer, '/responses', body, 'client-token', 200)
            body['input'].append({'role': 'user', 'content': 'Now work on something unrelated.'})
            self.post(observer, '/responses', body, 'client-token', 403)
            self.assertEqual(len(seen), 1)
            self.assertEqual(observer.reason, 'scope_mismatch')

    def test_budget_is_shared_and_exhaustion_precedes_upstream(self):
        seen = []
        class Upstream(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_POST(self):
                if self.path == '/evaluation-stop':
                    self.send_response(204); self.end_headers(); return
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                seen.append(body)
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.end_headers()
                self.wfile.write(b'data: {"type":"response.completed","response":{"model":"moonshotai/Kimi-K3","output":[],"usage":{"input_tokens":3,"output_tokens":2}}}\n\n')
        server = LoopbackServer(('127.0.0.1', 0), Upstream)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                run = Path(directory)
                (run / 'workspace').mkdir()
                with Observer(run, model='moonshotai/Kimi-K3', guardian='zai-org/GLM-5.3-Flash',
                              limits={'seconds': 180, 'requests': 1, 'output_tokens': 4096}) as observer:
                    self.post(observer, '/register', {'endpoint': 'http://127.0.0.1:' + str(server.server_port),
                        'token': 'client-token'}, observer.secret, 200)
                    body = {'model': 'moonshotai/Kimi-K3', 'stream': True,
                        'instructions': 'Private instruction never exported.',
                        'input': [{'role': 'user', 'content': 'synthetic fixture'}], 'tools': []}
                    self.post(observer, '/responses', body, 'client-token', 200)
                    self.post(observer, '/responses', body, 'client-token', 429)
                    self.assertEqual(len(seen), 1)
                    self.assertEqual(seen[0]['max_output_tokens'], 4096)
                    records = observer.records
                    self.assertEqual(records[0]['role'], 'main')
                    self.assertEqual(records[0]['usage']['output_tokens'], 2)
                    self.assertEqual(records[-1]['failure'], 'request_budget_limit')
                    self.assertNotIn('Private instruction', json.dumps(records))
        finally:
            server.shutdown(); server.server_close()

    def post(self, observer, path, body, token, status):
        connection = http.client.HTTPConnection('127.0.0.1', observer.port, timeout=3)
        try:
            connection.request('POST', path, json.dumps(body),
                               {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
            response = connection.getresponse()
            payload = response.read()
            self.assertEqual(response.status, status, payload)
            return payload
        finally:
            connection.close()


class SplitAuthorizationTests(unittest.TestCase):
    control = 'c' * 64
    inference = 'a' * 64
    native = 'synthetic-native-credential'

    @contextmanager
    def boundary(self, observer_type=Observer, response=None, **options):
        seen = []
        class Adapter(http.server.BaseHTTPRequestHandler):
            def log_message(self, *unused): pass
            def do_GET(self): self.respond()
            def do_POST(self): self.respond()
            def respond(self):
                raw = self.rfile.read(int(self.headers.get('Content-Length', 0)))
                seen.append((self.path, dict(self.headers), json.loads(raw) if raw else None))
                self.raw_body = raw
                if response and self.path == '/responses':
                    response(self); return
                self.send_response(200); self.end_headers()
                if self.path == '/responses':
                    event = {'type': 'response.completed', 'response': {'model': 'moonshotai/Kimi-K3', 'output': []}}
                    self.wfile.write(('data: ' + json.dumps(event) + '\n\n').encode())
                else: self.wfile.write(b'{}')
        adapter = LoopbackServer(('127.0.0.1', 0), Adapter)
        threading.Thread(target=adapter.serve_forever, daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                run = Path(directory); (run / 'workspace').mkdir()
                with observer_type(run, model='moonshotai/Kimi-K3', guardian='zai-org/GLM-5.3-Flash',
                        limits={'seconds': 180, 'requests': 12, 'output_tokens': 4096}, **options) as observer:
                    registration = {'version': 2, 'endpoint': 'http://127.0.0.1:' + str(adapter.server_port),
                                    'control_token': self.control, 'inference_token': self.inference}
                    yield observer, seen, registration
        finally:
            adapter.shutdown(); adapter.server_close()

    def request(self, observer, path, headers, body=None, method='POST', raw=None):
        connection = http.client.HTTPConnection('127.0.0.1', observer.port, timeout=3)
        try:
            payload = raw if raw is not None else json.dumps(body) if body is not None else b''
            connection.putrequest(method, path)
            for key, value in headers: connection.putheader(key, value)
            connection.putheader('Content-Length', str(len(payload.encode() if isinstance(payload, str) else payload)))
            connection.endheaders(payload.encode() if isinstance(payload, str) else payload)
            response = connection.getresponse()
            return response.status, response.read()
        finally: connection.close()

    def register(self, observer, registration):
        status, data = self.request(observer, '/register', [('Authorization', 'Bearer ' + observer.secret)], registration)
        self.assertEqual(status, 200, data)

    def test_native_and_legacy_inference_preserve_separate_control_authority(self):
        with self.boundary() as (observer, seen, registration):
            self.register(observer, registration)
            body = {'model': 'moonshotai/Kimi-K3', 'stream': True, 'input': [], 'tools': []}
            status, data = self.request(observer, '/responses', [
                ('Authorization', 'Bearer ' + self.native), ('X-TOFA-Launch', self.inference),
                ('ChatGPT-Account-Id', 'synthetic-account')], body)
            self.assertEqual(status, 200, data)
            self.assertEqual(seen[0][1]['Authorization'], 'Bearer ' + self.native)
            self.assertEqual(seen[0][1]['X-TOFA-Launch'], self.inference)
            self.assertEqual(seen[0][1]['ChatGPT-Account-Id'], 'synthetic-account')
            status, data = self.request(observer, '/responses', [('Authorization', 'Bearer ' + self.inference)], body)
            self.assertEqual(status, 200, data)
            self.assertEqual(seen[1][1]['Authorization'], 'Bearer ' + self.inference)
            self.assertNotIn('X-TOFA-Launch', seen[1][1])
            status, data = self.request(observer, '/desktop-launch', [('Authorization', 'Bearer ' + self.control),
                ('X-Tofa-Parent-Pid', '123')], method='GET')
            self.assertEqual(status, 200, data)
            self.assertEqual(seen[2][1]['Authorization'], 'Bearer ' + self.control)
            self.assertEqual(seen[2][1]['X-Tofa-Parent-Pid'], '123')
            observer.stop('operator_finished')
            self.assertEqual(seen[3][0], '/evaluation-stop')
            self.assertEqual(seen[3][1]['Authorization'], 'Bearer ' + self.control)
            retained = ''.join(p.read_text() for p in observer.run.iterdir() if p.is_file())
            for secret in (self.control, self.inference, self.native, 'synthetic-account'):
                self.assertNotIn(secret, retained)

    def test_launch_capabilities_cannot_cross_scopes_or_use_ambiguous_headers(self):
        with self.boundary() as (observer, seen, registration):
            self.register(observer, registration)
            bearer = lambda token: ('Authorization', 'Bearer ' + token)
            launch = ('X-TOFA-Launch', self.inference)
            attempts = [
                ('POST', '/responses', [bearer(self.native)]),
                ('POST', '/responses', [bearer(self.control)]),
                ('POST', '/responses', [bearer(observer.secret)]),
                ('POST', '/responses', [('Authorization', 'Bearer '), launch]),
                ('POST', '/responses', [bearer(self.native), ('X-TOFA-Launch', 'wrong')]),
                ('POST', '/responses', [bearer(self.control), launch]),
                ('POST', '/responses', [bearer(self.native), launch, launch]),
                ('POST', '/responses', [bearer(self.native), bearer('other'), launch]),
                ('POST', '/responses', [bearer('x' * 8193), launch]),
                ('POST', '/responses', [bearer(self.native), launch,
                                       ('ChatGPT-Account-Id', 'one'), ('ChatGPT-Account-Id', 'two')]),
                ('GET', '/responses', [bearer(self.native), launch]),
                ('POST', '/responses?control=1', [bearer(self.native), launch]),
                ('POST', '/desktop-launch', [bearer(self.control)]),
                ('GET', '/desktop-launch', [bearer(self.native), launch]),
                ('GET', '/desktop-launch', [bearer(self.inference)]),
                ('GET', '/desktop-launch', [bearer(self.control), launch]),
                ('POST', '/evaluation-stop', [bearer(self.inference)]),
                ('POST', '/evaluation-stop', [bearer(self.control)]),
                ('GET', '/register', [bearer(observer.secret)]),
            ]
            for method, path, headers in attempts:
                with self.subTest(method=method, path=path, header_names=[name for name, _ in headers]):
                    status, data = self.request(observer, path, headers, {'model': 'moonshotai/Kimi-K3', 'input': []}, method)
                    self.assertEqual(status, 401, data)
            self.assertEqual(seen, [])
            self.assertEqual(observer.records, [])

    def test_registration_is_bounded_exact_and_cannot_be_replaced(self):
        changes = [
            {'version': True}, {'version': 3}, {'version': 1},
            {'control_token': 'short'}, {'inference_token': 'g' * 64},
            {'inference_token': self.control}, {'token': 'legacy-extra'},
            {'endpoint': 'http://127.0.0.1:80/'}, {'endpoint': 'http://localhost:80'},
            {'endpoint': 'http://127.0.0.1:70000'}, {'endpoint': 'http://user@127.0.0.1:80'},
        ]
        for change in changes:
            with self.subTest(fields=list(change)), self.boundary() as (observer, seen, registration):
                registration.update(change)
                status, data = self.request(observer, '/register', [('Authorization', 'Bearer ' + observer.secret)], registration)
                self.assertEqual(status, 400, data)
                self.assertEqual(seen, [])
        for shape in ('duplicate', 'oversized'):
            with self.subTest(shape=shape), self.boundary() as (observer, seen, registration):
                raw = json.dumps(registration)
                raw = raw[:-1] + ', "version": 2}' if shape == 'duplicate' else raw + ' ' * 4096
                status, data = self.request(observer, '/register', [('Authorization', 'Bearer ' + observer.secret)], raw=raw)
                self.assertEqual(status, 400, data)
                self.assertEqual(seen, [])
        with self.boundary() as (observer, seen, registration):
            self.register(observer, registration)
            registration['endpoint'] = 'http://127.0.0.1:1'
            status, data = self.request(observer, '/register', [('Authorization', 'Bearer ' + observer.secret)], registration)
            self.assertEqual(status, 409, data)
            status, data = self.request(observer, '/desktop-launch', [('Authorization', 'Bearer ' + self.control)], method='GET')
            self.assertEqual(status, 200, data)
            self.assertEqual(len(seen), 1)

    def test_inference_capability_is_independent_of_native_authentication(self):
        with self.boundary() as (observer, seen, registration):
            self.register(observer, registration)
            status, data = self.request(observer, '/responses', [('X-TOFA-Launch', self.inference)],
                {'model': 'moonshotai/Kimi-K3', 'stream': True, 'input': [], 'tools': []})
            self.assertEqual(status, 200, data)
            self.assertNotIn('Authorization', seen[0][1])
            self.assertEqual(seen[0][1]['X-TOFA-Launch'], self.inference)

    def test_reflected_native_credentials_never_enter_retained_diagnostics(self):
        def broken(handler):
            handler.wfile.write(('reflected ' + self.native + ' ' + self.control + ' ' + self.inference + '\r\n\r\n').encode())
        with self.boundary(response=broken) as (observer, _, registration):
            self.register(observer, registration)
            with self.assertRaises(http.client.RemoteDisconnected):
                self.request(observer, '/responses', [('Authorization', 'Bearer ' + self.native),
                    ('X-TOFA-Launch', self.inference)], {'model': 'moonshotai/Kimi-K3', 'stream': True, 'input': [], 'tools': []})
            retained = ''.join(p.read_text() for p in observer.run.iterdir() if p.is_file())
            self.assertIn('BadStatusLine', retained)
            for secret in (self.native, self.control, self.inference):
                self.assertNotIn(secret, retained)


class ServiceDeclarationTests(unittest.TestCase):
    services = {'moonshotai/Kimi-K3': 'token_factory', 'gpt-6-astra': 'native'}

    def test_declared_switching_preserves_native_wire_body_and_reports_enforced_limits(self):
        helper = SplitAuthorizationTests()
        raw_requests = []
        def upstream(handler):
            raw_requests.append(handler.raw_body)
            body = json.loads(handler.raw_body)
            event = {'type': 'response.completed', 'response': {'model': body['model'], 'output': [],
                     'usage': {'input_tokens': 3, 'output_tokens': 2}}}
            handler.send_response(200); handler.end_headers()
            handler.wfile.write(('data: ' + json.dumps(event) + '\n\n').encode())
        with helper.boundary(response=upstream, model_services=self.services) as (observer, seen, registration):
            helper.register(observer, registration)
            headers = [('Authorization', 'Bearer ' + helper.native), ('X-TOFA-Launch', helper.inference)]
            factory = {'model': 'moonshotai/Kimi-K3', 'stream': True, 'input': [], 'tools': [],
                       'max_output_tokens': 5000, 'parallel_tool_calls': True}
            native = {'model': 'gpt-6-astra', 'stream': True, 'input': [], 'tools': [],
                      'parallel_tool_calls': True, 'client_metadata': {'x-codex-turn-metadata': '{"request_kind":"turn"}'}}
            raw = json.dumps(native, indent=3).encode()
            for body, payload in ((factory, None), (None, raw), (factory, None)):
                status, data = helper.request(observer, '/responses', headers, body, raw=payload)
                self.assertEqual(status, 200, data)
            self.assertEqual([body['model'] for _, _, body in seen], list(self.services) + ['moonshotai/Kimi-K3'])
            self.assertEqual(raw_requests[1], raw)
            self.assertNotIn('max_output_tokens', seen[1][2])
            self.assertTrue(seen[1][2]['parallel_tool_calls'])
            self.assertEqual(seen[0][2]['max_output_tokens'], 4096)
            self.assertFalse(seen[0][2]['parallel_tool_calls'])
            native_record = observer.records[1]
            self.assertEqual(native_record['service'], 'native')
            self.assertEqual(native_record['limit_enforcement'], {
                'wall_clock': 'enforced', 'requests': 'enforced', 'bytes': 'enforced',
                'output_tokens': 'observed_usage', 'upstream_output_cap': None})
            self.assertTrue(native_record['completed'])

    def test_service_declarations_are_bounded_and_native_contracts_fail_before_forwarding(self):
        helper = SplitAuthorizationTests()
        for declaration in ({}, {'gpt-6-astra': 'native'}, {'moonshotai/Kimi-K3': 'https://arbitrary.invalid'},
                            {'moonshotai/Kimi-K3': None}, [('moonshotai/Kimi-K3', 'token_factory')],
                            dict(self.services, **{'x' * 513: 'native'}),
                            dict(self.services, **{str(i): 'native' for i in range(128)})):
            with self.subTest(declaration_type=type(declaration).__name__), self.assertRaisesRegex(ValueError, 'model_services'):
                with helper.boundary(model_services=declaration): pass
        native = {'model': 'gpt-6-astra', 'stream': True, 'input': [], 'tools': []}
        changes = [
            {'max_output_tokens': 4097}, {'max_output_tokens': True},
            {'parallel_tool_calls': 'true'}, {'previous_response_id': 'previous'},
            {'client_metadata': {'x-codex-turn-metadata': '{"request_kind":"unknown"}'}},
            {'client_metadata': {'x-codex-turn-metadata': '{"thread_source":"future_helper"}'}},
            {'client_metadata': {'x-codex-turn-metadata': '{"turn_trigger":"guardian"}'}},
            {'client_metadata': {'x-openai-subagent': 'guardian'}},
            *[{'client_metadata': {'x-codex-turn-metadata': json.dumps({'thread_source': source})}}
              for source in ('cli', 'vscode', 'appServer')],
            {'client_metadata': {'x-codex-turn-metadata': '{"turn_trigger":"user"}'}},
            {'model': 'undeclared/model'},
        ]
        for change in changes:
            with self.subTest(fields=list(change)), helper.boundary(model_services=self.services) as (observer, seen, registration):
                helper.register(observer, registration)
                body = dict(native, **change)
                status, data = helper.request(observer, '/responses', [('Authorization', 'Bearer ' + helper.native),
                    ('X-TOFA-Launch', helper.inference)], body)
                self.assertEqual(status, 400, data)
                self.assertFalse(any(path == '/responses' for path, _, _ in seen))
        with helper.boundary() as (observer, seen, registration):
            helper.register(observer, registration)
            status, data = helper.request(observer, '/responses', [('X-TOFA-Launch', helper.inference)], native)
            self.assertEqual(status, 400, data)
            self.assertFalse(any(path == '/responses' for path, _, _ in seen))

    def test_native_usage_must_be_observed_and_over_budget_stops_subsequent_requests(self):
        helper = SplitAuthorizationTests()
        for usage, cap, reason in ((None, None, 'native_output_usage_unobserved'),
                                  ({'input_tokens': 3}, None, 'native_output_usage_unobserved'),
                                  ({'output_tokens': -1}, None, 'native_output_usage_unobserved'),
                                  ({'output_tokens': True}, None, 'native_output_usage_unobserved'),
                                  ({'output_tokens': 4097}, None, 'provider_output_limit_violation'),
                                  ({'output_tokens': 129}, 128, 'provider_output_limit_violation')):
            def upstream(handler):
                response = {'model': 'gpt-6-astra', 'output': []}
                if usage is not None: response['usage'] = usage
                handler.send_response(200); handler.end_headers()
                handler.wfile.write(('data: ' + json.dumps({'type': 'response.completed', 'response': response}) + '\n\n').encode())
            with self.subTest(usage=usage, cap=cap), helper.boundary(response=upstream, model_services=self.services) as (observer, seen, registration):
                helper.register(observer, registration)
                body = {'model': 'gpt-6-astra', 'stream': True, 'input': [], 'tools': []}
                if cap is not None: body['max_output_tokens'] = cap
                headers = [('Authorization', 'Bearer ' + helper.native), ('X-TOFA-Launch', helper.inference)]
                helper.request(observer, '/responses', headers, body)
                self.assertEqual(observer.reason, reason)
                self.assertFalse(observer.records[0]['completed'])
                status, _ = helper.request(observer, '/responses', headers, body)
                self.assertEqual(status, 401)
                self.assertEqual(len([path for path, _, _ in seen if path == '/responses']), 1)

    def test_native_protocol_headers_reach_only_registered_adapter_without_arbitrary_headers(self):
        helper = SplitAuthorizationTests()
        forwarded = {'OpenAI-Beta': 'responses=fixture', 'Originator': 'codex_fixture',
                     'Session-Id': 'fixture-session', 'X-Client-Request-Id': 'fixture-request',
                     'X-Codex-Turn-State': 'fixture-turn-state', 'X-Codex-Turn-Metadata': '{"request_kind":"turn"}',
                     'Thread-Id': 'fixture-thread', 'User-Agent': 'fixture-engine',
                     'X-Codex-Beta-Features': 'fixture-feature', 'X-Codex-Window-Id': 'fixture-window',
                     'X-Openai-Internal-Codex-Responses-Lite': 'true'}
        def upstream(handler):
            event = {'type': 'response.completed', 'response': {'model': 'gpt-6-astra', 'output': [], 'usage': {'output_tokens': 2}}}
            handler.send_response(200); handler.end_headers()
            handler.wfile.write(('data: ' + json.dumps(event) + '\n\n').encode())
        with helper.boundary(response=upstream, model_services=self.services) as (observer, seen, registration):
            helper.register(observer, registration)
            headers = [('Authorization', 'Bearer ' + helper.native), ('X-TOFA-Launch', helper.inference),
                       ('Cookie', 'private-cookie'), ('X-Arbitrary-Upstream', 'https://arbitrary.invalid'), *forwarded.items()]
            status, data = helper.request(observer, '/responses', headers,
                {'model': 'gpt-6-astra', 'stream': True, 'input': [], 'tools': []})
            self.assertEqual(status, 200, data)
            for name, value in forwarded.items(): self.assertEqual(seen[0][1].get(name), value)
            self.assertNotIn('Cookie', seen[0][1])
            self.assertNotIn('X-Arbitrary-Upstream', seen[0][1])
            retained = ''.join(p.read_text() for p in observer.run.iterdir() if p.is_file())
            for value in ('private-cookie', 'fixture-turn-state', 'fixture-session', 'fixture-request'):
                self.assertNotIn(value, retained)

    def test_native_turn_state_response_is_preserved_without_retaining_or_forwarding_other_headers(self):
        helper = SplitAuthorizationTests()
        for model in self.services:
            def upstream(handler):
                event = {'type': 'response.completed', 'response': {'model': model, 'output': [], 'usage': {'output_tokens': 2}}}
                handler.send_response(200)
                handler.send_header('X-Codex-Turn-State', 'private-next-turn-state')
                handler.send_header('Set-Cookie', 'private-cookie')
                handler.send_header('X-Arbitrary-Response', 'private-extra')
                handler.end_headers()
                handler.wfile.write(('data: ' + json.dumps(event) + '\n\n').encode())
            with self.subTest(model=model), helper.boundary(response=upstream, model_services=self.services) as (observer, seen, registration):
                helper.register(observer, registration)
                connection = http.client.HTTPConnection('127.0.0.1', observer.port, timeout=3)
                try:
                    connection.request('POST', '/responses', json.dumps({'model': model, 'stream': True, 'input': [], 'tools': []}),
                        {'X-TOFA-Launch': helper.inference})
                    response = connection.getresponse()
                    self.assertEqual(response.getheader('X-Codex-Turn-State'),
                        'private-next-turn-state' if self.services[model] == 'native' else None)
                    self.assertIsNone(response.getheader('Set-Cookie'))
                    self.assertIsNone(response.getheader('X-Arbitrary-Response'))
                    response.read()
                finally: connection.close()
                retained = ''.join(p.read_text() for p in observer.run.iterdir() if p.is_file())
                for value in ('private-next-turn-state', 'private-cookie', 'private-extra'):
                    self.assertNotIn(value, retained)

    def test_native_declared_main_accepts_known_client_origins_and_triggers(self):
        helper = SplitAuthorizationTests()
        def upstream(handler):
            event = {'type': 'response.completed', 'response': {'model': 'gpt-6-astra', 'output': [], 'usage': {'output_tokens': 2}}}
            handler.send_response(200); handler.end_headers()
            handler.wfile.write(('data: ' + json.dumps(event) + '\n\n').encode())
        with helper.boundary(response=upstream, model_services=self.services) as (observer, seen, registration):
            helper.register(observer, registration)
            for source in (None, 'user'):
                for trigger in (None, 'composer'):
                    body = {'model': 'gpt-6-astra', 'stream': True, 'input': [], 'tools': [],
                        'client_metadata': {'x-codex-turn-metadata': json.dumps({
                            'request_kind': 'turn', 'thread_source': source, 'turn_trigger': trigger})}}
                    status, data = helper.request(observer, '/responses', [('X-TOFA-Launch', helper.inference)], body)
                    self.assertEqual(status, 200, data)
                    self.assertEqual(seen[-1][2], body)

    def test_native_response_turn_state_is_bounded_and_unambiguous(self):
        helper = SplitAuthorizationTests()
        for values in (['one', 'two'], ['x' * 8193], ['state\twith-control']):
            def upstream(handler):
                handler.send_response(200)
                for value in values: handler.send_header('X-Codex-Turn-State', value)
                handler.end_headers()
            with self.subTest(lengths=[len(value) for value in values]), helper.boundary(response=upstream, model_services=self.services) as (observer, seen, registration):
                helper.register(observer, registration)
                with self.assertRaises(http.client.RemoteDisconnected):
                    helper.request(observer, '/responses', [('X-TOFA-Launch', helper.inference)],
                        {'model': 'gpt-6-astra', 'stream': True, 'input': [], 'tools': []})
                self.assertFalse(observer.records[0]['completed'])
                self.assertEqual(observer.records[0]['transport_failure']['stage'], 'upstream_headers')

    def test_declared_native_lane_requires_v2_and_unambiguous_wire_model(self):
        helper = SplitAuthorizationTests()
        with helper.boundary(model_services=self.services) as (observer, seen, registration):
            helper.register(observer, {'endpoint': registration['endpoint'], 'token': 'legacy-client'})
            status, data = helper.request(observer, '/responses', [('Authorization', 'Bearer legacy-client')],
                {'model': 'gpt-6-astra', 'stream': True, 'input': [], 'tools': []})
            self.assertEqual(status, 400, data)
            self.assertFalse(any(path == '/responses' for path, _, _ in seen))
        with helper.boundary(model_services=self.services) as (observer, seen, registration):
            helper.register(observer, registration)
            status, data = helper.request(observer, '/responses', [('X-TOFA-Launch', helper.inference)],
                raw=b'{"model":"moonshotai/Kimi-K3","model":"gpt-6-astra","stream":true,"input":[],"tools":[]}')
            self.assertEqual(status, 400, data)
            self.assertFalse(any(path == '/responses' for path, _, _ in seen))


if __name__ == '__main__':
    unittest.main()
