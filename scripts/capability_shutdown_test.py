"""Owned HTTP handlers must finish diagnostic writes before Observer exit returns."""
import http.server
import json
from pathlib import Path
import tempfile
import threading
import unittest

from capability_observer import LoopbackServer, Observer
import capability_observer_test as boundary_tests


class ShutdownTests(unittest.TestCase):
    def test_exit_waits_for_usage_failure_handler_and_its_final_diagnostics(self):
        stop_entered, release_stop, exited = threading.Event(), threading.Event(), threading.Event()
        class Adapter(http.server.BaseHTTPRequestHandler):
            def log_message(self, *unused): pass
            def do_POST(self):
                self.rfile.read(int(self.headers.get('Content-Length', 0)))
                if self.path == '/evaluation-stop':
                    stop_entered.set(); release_stop.wait(3)
                    self.send_response(200); self.end_headers(); return
                event = {'type': 'response.completed', 'response': {'model': 'gpt-6-astra',
                    'output': [], 'usage': {'output_tokens': 4097}}}
                self.send_response(200); self.end_headers()
                self.wfile.write(('data: ' + json.dumps(event) + '\n\n').encode())
        adapter = LoopbackServer(('127.0.0.1', 0), Adapter)
        serving = threading.Thread(target=adapter.serve_forever); serving.start()
        helper = boundary_tests.SplitAuthorizationTests()
        closing = None
        try:
            with tempfile.TemporaryDirectory() as directory:
                run = Path(directory); (run / 'workspace').mkdir()
                observer = Observer(run, model='gpt-6-astra', guardian='zai-org/GLM-5.3-Flash',
                    model_services={'gpt-6-astra': 'native'}, limits={'seconds': 30, 'requests': 2, 'output_tokens': 4096})
                observer.__enter__()
                helper.register(observer, {'version': 2, 'endpoint': 'http://127.0.0.1:' + str(adapter.server_port),
                    'control_token': helper.control, 'inference_token': helper.inference})
                helper.request(observer, '/responses', [('X-TOFA-Launch', helper.inference)],
                    {'model': 'gpt-6-astra', 'stream': True, 'input': [], 'tools': []})
                self.assertTrue(stop_entered.wait(1))
                def close():
                    observer.__exit__(); exited.set()
                closing = threading.Thread(target=close); closing.start()
                try:
                    self.assertFalse(exited.wait(.65), 'Observer exit returned while its usage-failure handler still owns diagnostic writes')
                finally:
                    release_stop.set(); closing.join(3)
                self.assertTrue(exited.is_set(), 'owned handler shutdown did not finish')
                records = json.loads((run / 'requests.json').read_text())
                self.assertIn('ended_ms', records[0])
                self.assertEqual(records[0]['failure'], 'provider_output_limit_violation')
        finally:
            release_stop.set()
            if closing: closing.join(3)
            adapter.shutdown(); adapter.server_close(); serving.join()

    def test_exit_closes_owned_connections_that_have_not_finished_headers(self):
        import socket
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory); (run / 'workspace').mkdir()
            observer = Observer(run, model='moonshotai/Kimi-K3', guardian='zai-org/GLM-5.3-Flash',
                limits={'seconds': 30, 'requests': 2, 'output_tokens': 4096})
            observer.__enter__()
            client = socket.create_connection(('127.0.0.1', observer.port), timeout=2)
            exited = threading.Event()
            closing = None
            try:
                client.sendall(b'POST /responses HTTP/1.1\r\n')
                closing = threading.Thread(target=lambda: (observer.__exit__(), exited.set()))
                closing.start()
                self.assertTrue(exited.wait(3), 'partial unauthenticated headers prevented owned shutdown')
            finally:
                client.close()
                if closing: closing.join(3)


    def test_stop_during_connect_never_forwards_late_inference(self):
        import http.client
        from unittest.mock import patch
        helper = boundary_tests.SplitAuthorizationTests()
        connected, release = threading.Event(), threading.Event()
        original_connect = http.client.HTTPConnection.connect
        with helper.boundary() as (observer, seen, registration):
            helper.register(observer, registration)
            upstream_port = int(registration['endpoint'].rsplit(':', 1)[1])
            def held_connect(connection):
                original_connect(connection)
                if connection.port == upstream_port and not connected.is_set():
                    connected.set()
                    self.assertTrue(release.wait(3), 'test did not release owned connect')
            def request():
                try:
                    helper.request(observer, '/responses', [('Authorization', 'Bearer ' + helper.inference)],
                        {'model': 'moonshotai/Kimi-K3', 'stream': True, 'input': [], 'tools': []})
                except (OSError, http.client.HTTPException): pass
            with patch.object(http.client.HTTPConnection, 'connect', held_connect):
                client = threading.Thread(target=request); client.start()
                try:
                    self.assertTrue(connected.wait(2))
                    observer.stop('operator_cancelled')
                finally:
                    release.set(); client.join(3)
                self.assertFalse(client.is_alive())
        self.assertFalse(any(entry[0] == '/responses' for entry in seen), 'inference forwarded after attempt cancellation')


    def test_stop_does_not_wait_for_stalled_request_send(self):
        import http.client
        from unittest.mock import patch
        helper = boundary_tests.SplitAuthorizationTests()
        sending, release, stopped = threading.Event(), threading.Event(), threading.Event()
        original_send = http.client.HTTPConnection.send
        with helper.boundary() as (observer, seen, registration):
            helper.register(observer, registration)
            upstream_port = int(registration['endpoint'].rsplit(':', 1)[1])
            def held_send(connection, data):
                if connection.port == upstream_port and not sending.is_set():
                    sending.set()
                    if not release.wait(5): raise TimeoutError('owned send barrier was not released')
                return original_send(connection, data)
            def request():
                try:
                    helper.request(observer, '/responses', [('Authorization', 'Bearer ' + helper.inference)],
                        {'model': 'moonshotai/Kimi-K3', 'stream': True,
                         'input': [{'role': 'user', 'content': 'Synthetic large upload. ' * 65536}], 'tools': []})
                except (OSError, http.client.HTTPException): pass
            def stop():
                observer.stop('operator_cancelled'); stopped.set()
            with patch.object(http.client.HTTPConnection, 'send', held_send):
                client = threading.Thread(target=request); client.start()
                cancelling = None
                try:
                    self.assertTrue(sending.wait(2), 'owned request never reached send barrier')
                    cancelling = threading.Thread(target=stop); cancelling.start()
                    self.assertTrue(stopped.wait(2), 'cancellation waited for stalled request send')
                finally:
                    release.set(); client.join(3)
                    if cancelling: cancelling.join(3)
                self.assertFalse(client.is_alive())
                self.assertFalse(cancelling.is_alive())
        self.assertFalse(any(entry[0] == '/responses' for entry in seen), 'released send forwarded after cancellation acknowledgement')


if __name__ == '__main__':
    unittest.main()
