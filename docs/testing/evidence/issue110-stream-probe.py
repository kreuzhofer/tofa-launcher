"""Offline diagnostic matrix; all content and credentials are synthetic."""
import http.server
import json
from pathlib import Path
import sys
import tempfile
import threading
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'scripts'))
from evaluation_proxy import EvaluationProxy


def probe(name, ending, sizes, fragment=65536):
    events = [{'type': 'response.created', 'response': {'private_fixture': 'x' * size}} for size in sizes]
    events.append({'type': 'response.completed', 'response': {'model': 'moonshotai/Kimi-K3'}})
    stream = b''.join(b'data: ' + json.dumps(event).encode() + ending * 2 for event in events)
    class Upstream(http.server.BaseHTTPRequestHandler):
        def log_message(self, *unused): pass
        def do_POST(self):
            self.rfile.read(int(self.headers['Content-Length']))
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.end_headers()
            try:
                for offset in range(0, len(stream), fragment):
                    self.wfile.write(stream[offset:offset + fragment]); self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError): pass
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Upstream)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / 'report.json'
            with EvaluationProxy('http://127.0.0.1:' + str(server.server_port), 'synthetic-token',
                                 report, None, 'coding', 5) as proxy:
                request = urllib.request.Request(proxy.url + '/responses',
                    data=b'{"model":"moonshotai/Kimi-K3","stream":true,"input":[]}',
                    headers={'Authorization': 'Bearer synthetic-token'})
                with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=6) as response:
                    response.read()
            record = json.loads(report.read_text())[0]
            return dict(case=name, total_fixture_bytes=len(stream),
                        max_fixture_event_bytes=max(len(b'data: ' + json.dumps(e).encode() + ending * 2) for e in events),
                        completed=record['completed'], failure=record.get('failure'),
                        text_deltas=record['text_deltas'], tool_deltas=record['tool_deltas'])
    finally:
        server.shutdown(); server.server_close()


results = [probe(name, ending, sizes, fragment) for name, ending, sizes, fragment in (
    ('lf_two_bounded_events', b'\n', [150000, 150000], 65536),
    ('crlf_two_bounded_events', b'\r\n', [150000, 150000], 997),
    ('cr_two_bounded_events', b'\r', [150000, 150000], 997),
    ('lf_one_oversized_event', b'\n', [263000], 997),
)]
print(json.dumps({'actual_paid_inference': False, 'results': results}, indent=2))
assert all(r['completed'] for r in results[:3]), 'A legal bounded-event framing was rejected'
assert results[3]['failure'] == 'event_body_limit'
