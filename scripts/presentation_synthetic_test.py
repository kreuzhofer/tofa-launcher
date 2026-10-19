"""No-inference production-launcher calibration at its authenticated HTTP boundary."""
import json
from pathlib import Path
import tempfile
import threading
import time
import http.server
import http.client
import unittest

from capability_observer import LoopbackServer
import capability_observer_test
from evaluation_proxy import fixture_response, message


class SyntheticObserverTests(unittest.TestCase):
    def test_only_native_launch_control_reaches_registered_adapter(self):
        from presentation_synthetic import SyntheticObserver
        seen, synthetic = [], []
        class Adapter(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                seen.append(self.path)
                self.send_response(200); self.end_headers(); self.wfile.write(b'{}')
            def do_POST(self):
                if self.path != '/evaluation-stop': seen.append(self.path)
                self.send_response(204); self.end_headers()
        adapter = LoopbackServer(('127.0.0.1', 0), Adapter)
        threading.Thread(target=adapter.serve_forever, daemon=True).start()
        self.addCleanup(adapter.server_close); self.addCleanup(adapter.shutdown)
        def respond(body):
            synthetic.append(body)
            return fixture_response(message('Synthetic runtime check'), body['model'])
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory); (run / 'workspace').mkdir()
            with SyntheticObserver(run, respond=respond, model='moonshotai/Kimi-K3',
                    guardian='zai-org/GLM-5.3-Flash', limits={'seconds':180,'requests':8,'output_tokens':4096}) as observer:
                helper = capability_observer_test.BoundaryTests()
                helper.post(observer, '/register', {'endpoint':'http://127.0.0.1:'+str(adapter.server_port),
                    'token':'owned-client-token'}, observer.secret, 200)
                helper.post(observer, '/responses', helper.body(), 'wrong-token', 401)
                self.assertEqual(synthetic, [])
                helper.post(observer, '/responses', helper.body(), 'owned-client-token', 200)
                connection = http.client.HTTPConnection('127.0.0.1', observer.port)
                connection.request('GET','/desktop-launch',headers={'Authorization':'Bearer owned-client-token'})
                response=connection.getresponse(); self.assertEqual(response.status,200);response.read();connection.close()
                self.assertEqual(seen,['/desktop-launch'])
                self.assertEqual(len(synthetic),1)
                self.assertTrue(observer.records[0]['completed'])
                self.assertFalse(observer.records[0]['forwarded'])
                self.assertEqual(observer.records[0]['transport'],'synthetic_observer')

    def test_split_authorization_keeps_synthetic_responses_out_of_control_lane(self):
        from presentation_synthetic import SyntheticObserver
        helper = capability_observer_test.SplitAuthorizationTests()
        synthetic = []
        def respond(body):
            synthetic.append(body)
            return fixture_response(message('Synthetic runtime check'), body['model'])
        with helper.boundary(observer_type=SyntheticObserver, respond=respond) as (observer, seen, registration):
            helper.register(observer, registration)
            body = {'model': 'moonshotai/Kimi-K3', 'stream': True, 'input': [], 'tools': []}
            headers = [('Authorization', 'Bearer ' + helper.native), ('X-TOFA-Launch', helper.inference)]
            status, _ = helper.request(observer, '/desktop-launch', headers, method='GET')
            self.assertEqual(status, 401)
            status, _ = helper.request(observer, '/responses', [('Authorization', 'Bearer ' + helper.control)], body)
            self.assertEqual(status, 401)
            status, data = helper.request(observer, '/responses', headers, body)
            self.assertEqual(status, 200, data)
            self.assertEqual(len(synthetic), 1)
            self.assertEqual(seen, [])
            self.assertFalse(observer.records[0]['forwarded'])
            status, data = helper.request(observer, '/desktop-launch', [('Authorization', 'Bearer ' + helper.control)], method='GET')
            self.assertEqual(status, 200, data)
            self.assertEqual([item[0] for item in seen], ['/desktop-launch'])
            observer.stop('operator_finished')
            status, _ = helper.request(observer, '/responses', headers, body)
            self.assertEqual(status, 401)
            self.assertEqual(len(synthetic), 1)
            self.assertEqual([item[0] for item in seen], ['/desktop-launch', '/evaluation-stop'])
            retained = ''.join(p.read_text() for p in observer.run.iterdir() if p.is_file())
            for secret in (helper.native, helper.control, helper.inference):
                self.assertNotIn(secret, retained)

    def test_guardian_cannot_receive_a_synthetic_approval_or_forwarded_inference(self):
        from presentation_synthetic import SyntheticObserver
        from capability_observer import GUARDIAN_SCHEMA
        seen = []
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory); (run / 'workspace').mkdir()
            with SyntheticObserver(run, respond=lambda body: seen.append(body), model='moonshotai/Kimi-K3',
                    guardian='zai-org/GLM-5.3-Flash', limits={'seconds':180,'requests':8,'output_tokens':4096}) as observer:
                helper = capability_observer_test.BoundaryTests()
                helper.post(observer, '/register', {'endpoint':'http://127.0.0.1:1',
                    'token':'owned-client-token'}, observer.secret, 200)
                body=helper.body()
                body.update(model='zai-org/GLM-5.3-Flash', instructions='Native policy', tool_choice='auto',
                    tools=[{'type':'function','name':name,'parameters':{'type':'object'}}
                        for name in ('exec_command','write_stdin','view_image')],
                    text={'format':{'type':'json_schema','strict':False,'schema':GUARDIAN_SCHEMA}})
                helper.post(observer, '/responses', body, 'owned-client-token', 400)
                self.assertEqual(seen, [])
                self.assertEqual(observer.reason, 'synthetic_guardian_unsupported')
                self.assertFalse(any(record['forwarded'] for record in observer.records))

    def test_concurrent_responses_retain_every_audit_record(self):
        from presentation_synthetic import SyntheticObserver
        from concurrent.futures import ThreadPoolExecutor
        barrier = threading.Barrier(8)
        def respond(body):
            barrier.wait(timeout=5)
            return fixture_response(message('Synthetic concurrent response'), body['model'])
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory); (run / 'workspace').mkdir()
            with SyntheticObserver(run, respond=respond, model='moonshotai/Kimi-K3',
                    guardian='zai-org/GLM-5.3-Flash', limits={'seconds':180,'requests':32,'output_tokens':4096}) as observer:
                helper = capability_observer_test.BoundaryTests()
                helper.post(observer, '/register', {'endpoint':'http://127.0.0.1:1',
                    'token':'owned-client-token'}, observer.secret, 200)
                for unused in range(4):
                    with ThreadPoolExecutor(max_workers=8) as pool:
                        list(pool.map(lambda unused: helper.post(observer, '/responses', helper.body(),
                            'owned-client-token', 200), range(8)))
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline:
                    records=json.loads((run/'requests.json').read_text())
                    if len(records)==32 and all('ended_ms' in record for record in records): break
                    time.sleep(.01)
                self.assertEqual(len(records),32)
                self.assertTrue(all(record.get('completed') and not record.get('failure') and
                    'ended_ms' in record for record in records))
                self.assertIsNone(observer.reason)


if __name__ == '__main__': unittest.main()
