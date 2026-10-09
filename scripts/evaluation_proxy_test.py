"""Local HTTP seam tests; synthetic credentials and model output only."""
import http.server
import json
import os
import subprocess
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request

from evaluation_proxy import EvaluationProxy, BODY_LIMIT, initial_event_hint
import evaluation_proxy


ASSESSMENT = {'required': ['outcome'], 'properties': {'outcome': {'type': 'string', 'enum': ['allow', 'deny']}}}


class ProxyTests(unittest.TestCase):
    def test_reasoning_validation_is_visible_after_union_branch_noise(self):
        details = [{'type': 'literal_error', 'loc': ['PRIVATE_CONTENT']}] * 20
        details += [{'type': 'missing', 'loc': ['body', 'input', 'PRIVATE_CONTENT',
                     3, 'ResponseReasoningItem', 'id'], 'input': 'PRIVATE_CONTENT'}]
        result = evaluation_proxy.validation_summary(json.dumps({'detail': details}))
        self.assertEqual(result['reasoning_errors'], [{'type': 'missing',
            'loc': ['body', 'input', 'other', 3, 'ResponseReasoningItem', 'id']}])
        self.assertNotIn('PRIVATE_CONTENT', json.dumps(result))

    def test_history_shape_is_bounded_and_never_exports_values(self):
        items = [{'role': 'assistant', 'content': [{'type': 'output_text',
                  'text': 'PRIVATE_CONTENT'}]},
                 {'type': 'function_call', 'name': 'PRIVATE_CONTENT',
                  'arguments': 'PRIVATE_CONTENT', 'id': None},
                 {'type': ['PRIVATE_CONTENT'], 'content': 'PRIVATE_CONTENT'}]
        result = evaluation_proxy.history_shape(items * 20)
        self.assertEqual(result['count'], 60)
        self.assertEqual(len(result['items']), 32)
        self.assertEqual(result['items'][0]['type'], 'missing')
        self.assertEqual(result['items'][0]['role'], 'assistant')
        self.assertEqual(result['items'][0]['content'][0],
                         {'type': 'output_text', 'annotations': 'missing'})
        self.assertEqual(result['items'][1]['id'], 'null')
        self.assertEqual(result['items'][1]['name'], 'other')
        self.assertNotIn('PRIVATE_CONTENT', json.dumps(result))

    def test_event_type_hints_are_fixed_labels_not_captured_payloads(self):
        for prefix, expected in (
            (b'event: response.created\r\ndata: {"private":"SECRET"}', 'response.created'),
            (b'data: {"type":"response.created","private":"SECRET"', 'response.created'),
            (b'data: {"type":"PRIVATE_SECRET"}', 'unrecognized'),
            (b'event: PRIVATE_SECRET\n', 'unrecognized'),
            (b'data: {"response":{"type":"response.created"}}', None),
            (b'data: {"type":"response.cre', None),
        ):
            with self.subTest(expected=expected):
                self.assertEqual(initial_event_hint(prefix), expected)

    def test_stream_diagnostics_do_not_export_unknown_headers_or_events(self):
        class Upstream(http.server.BaseHTTPRequestHandler):
            def log_message(self, *unused): pass
            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                self.send_response(200)
                self.send_header('Content-Type', 'PRIVATE_HEADER')
                self.send_header('Content-Encoding', 'PRIVATE_ENCODING')
                self.end_headers()
                self.wfile.write(b'data: {"type":"PRIVATE_EVENT","delta":"PRIVATE_CONTENT"}\r\n\r\n')
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Upstream)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                report = Path(directory) / 'report.json'
                with EvaluationProxy('http://127.0.0.1:' + str(server.server_port), 'fixture-token',
                                     report, None, 'coding', 5) as proxy:
                    request = urllib.request.Request(proxy.url + '/responses',
                        data=b'{"model":"moonshotai/Kimi-K3","stream":true,"input":[]}',
                        headers={'Authorization': 'Bearer fixture-token'})
                    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request) as response:
                        response.read()
                observed = json.loads(report.read_text())[0]
                diagnostics = observed['stream_diagnostics']
                self.assertEqual(diagnostics['content_type'], 'other')
                self.assertEqual(diagnostics['content_encoding'], 'other')
                self.assertEqual(diagnostics['first_event_type_hint'], 'unrecognized')
                self.assertEqual(diagnostics['last_event_type'], 'unrecognized')
                self.assertEqual(diagnostics['cr_bytes'], 2)
                self.assertEqual(diagnostics['lf_bytes'], 2)
                self.assertEqual(diagnostics['lines'], 2)
                self.assertEqual(diagnostics['blank_lines'], 1)
                self.assertEqual(diagnostics['parsed_json_lines'], 1)
                self.assertEqual(observed['failure'], 'response_incomplete')
                self.assertNotIn('PRIVATE_', report.read_text())
                self.assertNotIn('fixture-token', report.read_text())
                self.assertLess(len(report.read_bytes()), 4000)
        finally:
            server.shutdown(); server.server_close()

    def test_approval_proposal_executes_a_benign_marker_in_the_native_shell(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / 'observations.json'
            with EvaluationProxy('http://127.0.0.1:1', 'fixture-token', report,
                                 None, 'allow', 1) as proxy:
                request = urllib.request.Request(proxy.url + '/responses',
                    data=b'{"model":"moonshotai/Kimi-K3","stream":true,"input":[]}',
                    headers={'Authorization': 'Bearer fixture-token'})
                with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request) as response:
                    events = [json.loads(line[6:]) for line in response.read().decode().splitlines() if line.startswith('data: ')]
            completed = next(event for event in events if event['type'] == 'response.completed')
            arguments = json.loads(completed['response']['output'][0]['arguments'])
            self.assertEqual(arguments['sandbox_permissions'], 'require_escalated')
            shell = ['powershell.exe', '-NoProfile', '-NonInteractive', '-Command'] if os.name == 'nt' else ['/bin/sh', '-c']
            result = subprocess.run(shell + [arguments['cmd']], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), 'tofa-evaluation-benign-marker')
            self.assertTrue(all(not record['paid_inference'] for record in json.loads(report.read_text())))

    def test_unlimited_observations_survive_restart_without_replacing_attempts(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / 'observations.json'
            # Failed native attempts are retained too; there is no total quota.
            for _ in range(2):
                with EvaluationProxy('http://127.0.0.1:1', 'fixture-token', report,
                                     None, 'coding', 1) as proxy:
                    for _ in range(26):
                        request = urllib.request.Request(proxy.url + '/responses',
                            data=b'{"model":"moonshotai/Kimi-K3","stream":true,"input":[]}',
                            headers={'Authorization': 'Bearer fixture-token'})
                        try:
                            urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request).read()
                        except (urllib.error.URLError, OSError):
                            pass
            records = json.loads(report.read_text())
            self.assertEqual(len(records), 52)
            self.assertEqual(len({r['request_id'] for r in records}), 52)
            # A refused loopback connection can exceed this one-second budget on Windows.
            self.assertTrue(all(r['failure'] in ('transport_failure', 'deadline_incomplete') for r in records))

    def test_unrecognized_auxiliary_traffic_is_counted_and_sanitized(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'requests.json'
            with EvaluationProxy('http://127.0.0.1:1', 'fixture-token', output, None, 'coding', 1) as proxy:
                request = urllib.request.Request(proxy.url + '/responses',
                    data=json.dumps({'model': 'private-title-model', 'stream': True, 'input': [],
                        'text': {'format': {'type': 'json_schema', 'schema': {'title': 'PRIVATE'}}}}).encode(),
                    headers={'Authorization': 'Bearer fixture-token'})
                with self.assertRaises(urllib.error.HTTPError):
                    urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request)
            records = json.loads(output.read_text())
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]['role'], 'auxiliary')
            self.assertFalse(records[0]['paid_inference'])
            self.assertNotIn('private-title-model', output.read_text())
            self.assertNotIn('PRIVATE', output.read_text())

    def test_selected_pair_rejects_swapped_and_unexpected_roles_before_inference(self):
        main, guardian = 'moonshotai/Kimi-K3', 'zai-org/GLM-5.3-Flash'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            budget = root / 'budget.json'; budget.write_text('{"used":0,"maximum":48}')
            report = root / 'observations.json'
            with EvaluationProxy('http://127.0.0.1:1', 'fixture-token', report, budget,
                                 'allow', 1, model=main, guardian_model=guardian) as proxy:
                for model, review in ((guardian, False), (main, True), ('private/unexpected', True)):
                    body = {'model': model, 'stream': True, 'input': []}
                    if review:
                        body['text'] = {'format': {'name': 'guardian_assessment', 'type': 'json_schema', 'schema': ASSESSMENT}}
                    request = urllib.request.Request(proxy.url + '/responses', data=json.dumps(body).encode(),
                        headers={'Authorization': 'Bearer fixture-token'})
                    with self.assertRaises(urllib.error.HTTPError) as error:
                        urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request)
                    self.assertEqual(error.exception.code, 400)
            self.assertEqual(json.loads(budget.read_text())['used'], 0)
            self.assertEqual(len(json.loads(report.read_text())), 3)
            self.assertNotIn('private/unexpected', report.read_text())

    def test_guardian_only_routes_in_approval_cases_with_the_guardian_schema(self):
        for case, schema in (('coding', 'guardian_assessment'), ('allow', 'other_schema')):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                budget = root / 'budget.json'; budget.write_text('{"used":0,"maximum":48}')
                report = root / 'observations.json'
                with EvaluationProxy('http://127.0.0.1:1', 'fixture-token', report, budget,
                                     case, 1, model='moonshotai/Kimi-K3', guardian_model='zai-org/GLM-5.3') as proxy:
                    body = {'model': 'zai-org/GLM-5.3', 'stream': True, 'input': [],
                            'text': {'format': {'type': 'json_schema', 'name': schema, 'schema': ASSESSMENT if schema == 'guardian_assessment' else {}}}}
                    request = urllib.request.Request(proxy.url + '/responses', data=json.dumps(body).encode(),
                        headers={'Authorization': 'Bearer fixture-token'})
                    with self.assertRaises(urllib.error.HTTPError) as error:
                        urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request)
                    self.assertEqual(error.exception.code, 400)
                self.assertEqual(json.loads(budget.read_text())['used'], 0)

    def test_guardian_decision_is_measured_separately_from_synthetic_task(self, model="moonshotai/Kimi-K3", effort=None):
        seen = []
        class Upstream(http.server.BaseHTTPRequestHandler):
            def log_message(self, *unused): pass
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                seen.append(body)
                self.send_response(200)
                self.end_headers()
                for event in [
                    {'type': 'response.output_text.delta', 'delta': '{"out'},
                    {'type': 'response.output_text.delta', 'delta': 'come":"deny","rationale":"PRIVATE"}'},
                    {'type': 'response.completed', 'response': {'model': model, 'usage': {'input_tokens': 100, 'output_tokens': 20}}}]:
                    self.wfile.write(('data: ' + json.dumps(event) + '\n\n').encode())
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Upstream)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                budget = root / 'budget.json'
                budget.write_text('{"used":0,"maximum":8}')
                report = root / 'observations.json'
                with EvaluationProxy('http://127.0.0.1:' + str(server.server_port), 'fixture-token',
                                     report, budget, 'deny', 10, model=model) as proxy:
                    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                    def post(body):
                        request = urllib.request.Request(proxy.url + '/responses', data=json.dumps({'model': model, 'stream': True, 'input': [], **body}).encode(),
                            headers={'Authorization': 'Bearer fixture-token'})
                        return opener.open(request).read()
                    ordinary = post({'input': []})
                    self.assertIn(b'function_call', ordinary)
                    self.assertIn(model.encode(), ordinary)
                    post({'text': {'format': {'name': 'guardian_assessment', 'type': 'json_schema', 'schema': ASSESSMENT}},
                          'instructions': 'Preserve this policy', 'tools': [{'name': 'exec_command'}],
                          **({'reasoning': {'effort': effort}} if effort is not None else {})})
                self.assertEqual(len(seen), 1)
                self.assertEqual(seen[0]['max_output_tokens'], 4096)
                self.assertEqual(seen[0]['instructions'], 'Preserve this policy')
                self.assertEqual(json.loads(budget.read_text())['used'], 1)
                data = json.loads(report.read_text())
                self.assertEqual(data[-1]['kind'], 'automatic_review')
                self.assertEqual(data[-1]['decision'], 'deny')
                self.assertEqual(data[-1]['model'], model)
                self.assertEqual(data[-1]['role'], 'guardian')
                self.assertEqual(data[-1]['reasoning_effort'], effort)
                self.assertEqual(seen[0].get('reasoning', {}).get('effort'), effort)
                self.assertEqual(seen[0]['model'], model)
                self.assertEqual(data[0]['model'], model)
                self.assertFalse(data[0]['paid_inference'])
                self.assertTrue(data[-1]['paid_inference'])
                self.assertNotIn('PRIVATE', report.read_text())
        finally:
            server.shutdown()
            server.server_close()

    def test_selected_candidate_routes_guardian_and_synthetic_proposal(self):
        self.test_guardian_decision_is_measured_separately_from_synthetic_task("zai-org/GLM-5.3-Flash")

    def test_explicit_native_reasoning_effort_is_recorded_without_substitution(self):
        self.test_guardian_decision_is_measured_separately_from_synthetic_task(effort='none')

    def test_provider_cannot_complete_with_a_different_model_identity(self):
        class Upstream(http.server.BaseHTTPRequestHandler):
            def log_message(self, *unused): pass
            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                self.send_response(200); self.end_headers()
                self.wfile.write(b'data: {"type":"response.completed","response":{"model":"PRIVATE_UNEXPECTED_MODEL"}}\n\n')
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Upstream)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                budget = root / 'budget.json'; budget.write_text('{"used":0,"maximum":8}')
                report = root / 'observations.json'
                with EvaluationProxy('http://127.0.0.1:' + str(server.server_port), 'fixture-token',
                                     report, budget, 'coding', 5) as proxy:
                    request = urllib.request.Request(proxy.url + '/responses',
                        data=b'{"model":"moonshotai/Kimi-K3","stream":true,"input":[]}',
                        headers={'Authorization': 'Bearer fixture-token'})
                    urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request).read()
                observed = json.loads(report.read_text())[0]
                self.assertEqual(observed['failure'], 'response_model_mismatch')
                self.assertFalse(observed['completed'])
                self.assertNotIn('PRIVATE_UNEXPECTED_MODEL', report.read_text())
        finally:
            server.shutdown(); server.server_close()

    def test_budget_and_body_limits_stop_before_upstream(self):
        for body, used, expected_status, failure in [
                ({'input': []}, 0, 413, 'request_body_limit'),
                ({'input': []}, 8, 429, 'request_budget_limit')]:
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                budget = root / 'budget.json'
                budget.write_text(json.dumps({'used': used, 'maximum': 8}))
                output = root / 'observations.json'
                with EvaluationProxy('http://127.0.0.1:1', 'fixture-token', output,
                                     budget, 'coding', 1) as proxy:
                    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                    request = urllib.request.Request(proxy.url + '/responses', data=json.dumps({'model': 'moonshotai/Kimi-K3', 'stream': True, 'input': [], **body}).encode(),
                        headers={'Authorization': 'Bearer fixture-token'})
                    if failure == 'request_body_limit':
                        request.add_header('Content-Length', str(BODY_LIMIT + 1))
                    with self.assertRaises(urllib.error.HTTPError) as error:
                        opener.open(request)
                    self.assertEqual(error.exception.code, expected_status)
                records = json.loads(output.read_text())
                self.assertEqual(records[0]['failure'], failure)
                self.assertFalse(records[0]['completed'])
                self.assertEqual(records[0]['status'], expected_status)
                self.assertEqual(json.loads(budget.read_text())['used'], used)

    def test_output_cap_cannot_make_upstream_input_exceed_body_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            budget = root / 'budget.json'; budget.write_text('{"used":0,"maximum":8}')
            report = root / 'observations.json'
            with EvaluationProxy('http://127.0.0.1:1', 'fixture-token', report, budget, 'coding', 1) as proxy:
                body = {'model': 'moonshotai/Kimi-K3', 'stream': True, 'input': [], 'instructions': ''}
                encoded = json.dumps(body, separators=(',', ':')).encode()
                body['instructions'] = 'a' * (BODY_LIMIT - len(encoded))
                request = urllib.request.Request(proxy.url + '/responses',
                    data=json.dumps(body, separators=(',', ':')).encode(), headers={'Authorization': 'Bearer fixture-token'})
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request)
                self.assertEqual(error.exception.code, 413)
            self.assertEqual(json.loads(budget.read_text())['used'], 0)
            self.assertEqual(json.loads(report.read_text())[0]['failure'], 'request_body_limit')

    def test_unknown_models_server_context_and_nontext_inputs_are_refused(self):
        for change in ({'model': 'other/model'}, {'stream': False},
                       {'previous_response_id': 'synthetic-server-history'},
                       {'input': [{'type': 'input_image', 'image_url': 'http://example.invalid'}]},
                       {'tools': [{'type': 'web_search'}]}):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                budget = root / 'budget.json'
                budget.write_text('{"used":0,"maximum":8}')
                report = root / 'observations.json'
                with EvaluationProxy('http://127.0.0.1:1', 'fixture-token', report, budget, 'coding', 1) as proxy:
                    body = {'model': 'moonshotai/Kimi-K3', 'stream': True, 'input': [], **change}
                    request = urllib.request.Request(proxy.url + '/responses', data=json.dumps(body).encode(),
                        headers={'Authorization': 'Bearer fixture-token'})
                    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                    with self.assertRaises(urllib.error.HTTPError) as error:
                        opener.open(request)
                    self.assertEqual(error.exception.code, 400)
                self.assertEqual(json.loads(budget.read_text())['used'], 0)
                self.assertEqual(json.loads(report.read_text())[0]['failure'], 'unsupported_request_contract')
                self.assertNotIn('example.invalid', report.read_text())

    def test_trickling_stream_cannot_extend_the_total_request_deadline(self):
        class Upstream(http.server.BaseHTTPRequestHandler):
            def log_message(self, *unused): pass
            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                self.send_response(200); self.end_headers()
                try:
                    for _ in range(30):
                        self.wfile.write(b':'); self.wfile.flush(); time.sleep(0.1)
                except OSError: pass
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Upstream)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                budget = root / 'budget.json'; budget.write_text('{"used":0,"maximum":8}')
                report = root / 'observations.json'
                with EvaluationProxy('http://127.0.0.1:' + str(server.server_port), 'fixture-token',
                                     report, budget, 'coding', 1) as proxy:
                    request = urllib.request.Request(proxy.url + '/responses',
                        data=b'{"model":"moonshotai/Kimi-K3","stream":true,"input":[]}',
                        headers={'Authorization': 'Bearer fixture-token'})
                    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                    start = time.monotonic()
                    opener.open(request, timeout=5).read()
                    elapsed = time.monotonic() - start
                self.assertLess(elapsed, 2)
                self.assertEqual(json.loads(report.read_text())[0]['failure'], 'deadline_incomplete')
        finally:
            server.shutdown(); server.server_close()

    def test_complete_oversized_event_is_rejected_before_json_parsing(self, multiline=False):
        class Upstream(http.server.BaseHTTPRequestHandler):
            def log_message(self, *unused): pass
            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
                self.end_headers()
                line = ('data: ' + json.dumps({'type': 'response.output_text.delta',
                                              'delta': 'PRIVATE_PAYLOAD' + 'x' * 263000}) + '\n\n').encode()
                if multiline: line = (b':' + b'x' * 150000 + b'\n') * 2 + b'\n'
                self.wfile.write(line)
                self.wfile.write(b'data: {"type":"response.completed"}\n\n')
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Upstream)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                budget = root / 'budget.json'; budget.write_text('{"used":0,"maximum":8}')
                report = root / 'observations.json'
                with EvaluationProxy('http://127.0.0.1:' + str(server.server_port), 'fixture-token',
                                     report, budget, 'coding', 5) as proxy:
                    request = urllib.request.Request(proxy.url + '/responses',
                        data=b'{"model":"moonshotai/Kimi-K3","stream":true,"input":[]}',
                        headers={'Authorization': 'Bearer fixture-token'})
                    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                    opener.open(request).read()
                observed = json.loads(report.read_text())[0]
                self.assertEqual(observed['failure'], 'event_body_limit')
                self.assertFalse(observed['completed'])
                self.assertEqual(observed['text_deltas'], 0)
                diagnostics = observed['stream_diagnostics']
                self.assertEqual(diagnostics['content_type'], 'text/event-stream')
                self.assertGreater(diagnostics['response_bytes'], 256 * 1024)
                self.assertGreater(diagnostics['event_bytes_at_stop'] + diagnostics['pending_line_bytes_at_stop'], 256 * 1024)
                self.assertEqual(diagnostics['cr_bytes'], 0)
                self.assertEqual(diagnostics['parsed_json_lines'], 0)
                self.assertEqual(diagnostics['first_event_type_hint'], None if multiline else 'response.output_text.delta')
                self.assertNotIn('PRIVATE_PAYLOAD', report.read_text())
                self.assertNotIn('fixture-token', report.read_text())
        finally:
            server.shutdown(); server.server_close()

    def test_multiline_sse_event_has_one_shared_size_limit(self):
        self.test_complete_oversized_event_is_rejected_before_json_parsing(multiline=True)

    def test_large_created_event_preserves_the_stream_and_reaches_completion(self):
        # Reproduce the measured framing/category, without claiming the unknown
        # live event contained this synthetic field or had this complete size.
        header = b'event: response.created\n'
        payload = b'data: ' + json.dumps({'type': 'response.created',
            'response': {'fixture': 'PRIVATE_CONTENT' + 'x' * 390000}}).encode() + b'\n\n'
        stream = header + payload + b'data: {"type":"response.completed","response":{}}\n\n'
        class Upstream(http.server.BaseHTTPRequestHandler):
            def log_message(self, *unused): pass
            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.end_headers()
                try:
                    self.wfile.write(stream)
                except (BrokenPipeError, ConnectionResetError): pass
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Upstream)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                report = Path(directory) / 'report.json'
                with EvaluationProxy('http://127.0.0.1:' + str(server.server_port), 'fixture-token',
                                     report, None, 'coding', 5) as proxy:
                    request = urllib.request.Request(proxy.url + '/responses',
                        data=b'{"model":"moonshotai/Kimi-K3","stream":true,"input":[]}',
                        headers={'Authorization': 'Bearer fixture-token'})
                    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request) as response:
                        received = response.read()
                observed = json.loads(report.read_text())[0]
                self.assertNotIn('failure', observed)
                self.assertTrue(observed['completed'])
                self.assertEqual(received, stream)
                diagnostics = observed['stream_diagnostics']
                self.assertEqual(diagnostics['first_event_type_hint'], 'response.created')
                self.assertEqual(diagnostics['large_response_envelopes'], 1)
                self.assertEqual(diagnostics['cr_bytes'], 0)
                self.assertEqual(diagnostics['parsed_json_lines'], 2)
                self.assertNotIn('PRIVATE_CONTENT', report.read_text())
                self.assertNotIn('fixture-token', report.read_text())
        finally:
            server.shutdown(); server.server_close()


class EnvelopeLimitTests(unittest.TestCase):
    def observe(self, stream, request_count=1, maximum=8, status=200):
        class Upstream(http.server.BaseHTTPRequestHandler):
            def log_message(self, *unused): pass
            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                self.send_response(status); self.end_headers()
                try: self.wfile.write(stream)
                except (BrokenPipeError, ConnectionResetError): pass
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Upstream)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                report = Path(directory) / 'report.json'
                budget = Path(directory) / 'budget.json'
                budget.write_text(json.dumps({'used': 0, 'maximum': maximum}))
                with EvaluationProxy('http://127.0.0.1:' + str(server.server_port), 'fixture-token',
                                     report, budget, 'coding', 5) as proxy:
                    request = urllib.request.Request(proxy.url + '/responses',
                        data=b'{"model":"moonshotai/Kimi-K3","stream":true,"input":[]}',
                        headers={'Authorization': 'Bearer fixture-token'})
                    for _ in range(request_count):
                        try:
                            response = urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request)
                        except urllib.error.HTTPError as error:
                            response = error
                        with response:
                            response.read()
                self.assertNotIn('PRIVATE_CONTENT', report.read_text())
                self.assertEqual(json.loads(budget.read_text())['used'], request_count)
                return json.loads(report.read_text())[-1]
        finally:
            server.shutdown(); server.server_close()

    def event(self, kind='response.created', size=390000, header=None, **response):
        return ((('event: ' + header + '\n').encode() if header else b'') + b'data: ' +
            json.dumps({'type': kind, 'response': {'fixture': 'PRIVATE_CONTENT' + 'x' * size, **response}}).encode() + b'\n\n')

    def test_headerless_large_completion_preserves_usage(self):
        result = self.observe(self.event('response.completed', usage={'input_tokens': 10, 'output_tokens': 2}))
        self.assertTrue(result['completed'])
        self.assertEqual(result['usage'], {'input_tokens': 10, 'output_tokens': 2})

    def test_envelope_allowance_does_not_apply_to_later_text_events(self):
        result = self.observe(self.event() + self.event('response.output_text.delta'))
        self.assertEqual(result['failure'], 'event_body_limit')
        self.assertEqual(result['stream_diagnostics']['large_response_envelopes'], 1)

    def test_spoofed_envelope_header_cannot_admit_an_oversized_tool_event(self):
        result = self.observe(self.event('response.function_call_arguments.delta', header='response.created'))
        self.assertEqual(result['failure'], 'event_type_mismatch')
        self.assertFalse(result['completed'])

    def test_envelope_has_a_hard_limit_before_json_parsing(self):
        result = self.observe(self.event(size=BODY_LIMIT + 256 * 1024, header='response.created'))
        self.assertEqual(result['failure'], 'event_body_limit')
        self.assertEqual(result['stream_diagnostics']['parsed_json_lines'], 0)

    def test_large_envelope_cannot_hide_oversized_output(self):
        result = self.observe(self.event('response.completed', size=0,
            output=[{'type': 'message', 'content': 'x' * (256 * 1024)}]))
        self.assertEqual(result['failure'], 'response_output_limit')
        self.assertFalse(result['completed'])

    def test_large_envelope_rejects_model_mismatch(self):
        result = self.observe(self.event(model='PRIVATE_CONTENT'))
        self.assertEqual(result['failure'], 'response_model_mismatch')

    def test_total_stream_limit_still_applies_to_bounded_envelopes(self):
        result = self.observe(self.event(size=1100000) * 8)
        self.assertEqual(result['failure'], 'response_body_limit')

    def test_explicit_unlimited_budget_still_counts_requests(self):
        result = self.observe(self.event('response.completed', size=0), request_count=2, maximum=None)
        self.assertTrue(result['completed'])
        self.assertEqual(result['request_id'], 2)

    def test_large_http_validation_error_reports_only_allowlisted_locations(self):
        stream = json.dumps({'detail': [{'type': 'missing', 'loc': ['body', 'input', 4, 'id'],
            'msg': 'PRIVATE_CONTENT', 'input': 'PRIVATE_CONTENT' + 'x' * 390000},
            {'type': 'PRIVATE_CONTENT', 'loc': ['PRIVATE_CONTENT'], 'msg': 'PRIVATE_CONTENT'}]}).encode()
        result = self.observe(stream, status=422)
        self.assertEqual(result['failure'], 'upstream_http_error')
        self.assertEqual(result['upstream_validation'], {'count': 2, 'errors': [
            {'type': 'missing', 'loc': ['body', 'input', 4, 'id']}, {'type': 'other', 'loc': ['other']}]})
        self.assertFalse(result['completed'])

    def test_http_error_body_remains_bounded(self):
        result = self.observe(b'x' * (BODY_LIMIT + 65536), status=422)
        self.assertEqual(result['failure'], 'upstream_http_error')
        self.assertTrue(result['error_body_limit'])
        self.assertNotIn('upstream_validation', result)


if __name__ == '__main__': unittest.main()
