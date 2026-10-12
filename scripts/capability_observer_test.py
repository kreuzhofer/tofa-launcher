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
            {'type': 'namespace', 'name': 'functions', 'tools': [
                {'type': 'function', 'name': 'load_workspace_dependencies',
                 'parameters': {'type': 'object'}}]}]}]
        with self.boundary(case='04') as (observer, seen):
            self.post(observer, '/responses', body, 'client-token', 400)
            self.assertEqual(seen, [])
            self.assertEqual(observer.reason, 'presentation_runtime_unqualified')
            self.assertEqual(observer.records[0]['presentation_runtime'], {
                'required_tool': 'load_workspace_dependencies',
                'advertised': 'present', 'qualified': False})

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
    def boundary(self, limits=None, response=None, case='05', prompt=None, guardian='zai-org/GLM-5.3-Flash'):
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
                        limits=limits or {'seconds': 180, 'requests': 12, 'output_tokens': 4096}, case=case) as observer:
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


if __name__ == '__main__':
    unittest.main()
