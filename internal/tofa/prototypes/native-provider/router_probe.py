"""THROWAWAY #133. Owned loopback services and fake credentials only.

This demonstrates routing boundaries, not the production adapter or native UI.
--unsafe-header-copy is a deliberate negative control using only fake tokens.
"""
import argparse
from contextlib import contextmanager
import hashlib
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading

NATIVE_TOKEN = 'fake-native-token-prototype-133'
FACTORY_TOKEN = 'fake-factory-token-prototype-133'


def route(model, headers):
    if model == 'fixture-factory':
        return 'factory'
    if model == 'fixture-native':
        return 'chatgpt' if headers.get('ChatGPT-Account-ID') else 'openai'
    return None


@contextmanager
def serve(handler):
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def send(address, body, headers):
    connection = HTTPConnection(*address, timeout=2)
    try:
        connection.request('POST', '/v1/responses', json.dumps(body), headers)
        response = connection.getresponse()
        return response.status, response.read(65536)
    finally:
        connection.close()


def experiment(unsafe):
    seen = []
    mode = {'upstream_error': False, 'unavailable': False}

    def upstream(name):
        class Upstream(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                seen.append({'route': name, 'headers': dict(self.headers)})
                self.send_response(503 if mode['upstream_error'] else 200)
                self.end_headers()
                self.wfile.write((NATIVE_TOKEN + FACTORY_TOKEN).encode() if mode['upstream_error'] else b'{"fixture":"ok"}')
        return Upstream

    with serve(upstream('factory')) as factory, serve(upstream('chatgpt')) as chatgpt, serve(upstream('openai')) as openai:
        targets = {'factory': factory, 'chatgpt': chatgpt, 'openai': openai}

        class Router(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                target = route(body.get('model'), self.headers)
                if target is None:
                    status, reply = 400, b'Unknown model; request refused'
                else:
                    headers = {'Content-Type': 'application/json'}
                    if target == 'factory':
                        headers['Authorization'] = 'Bearer ' + FACTORY_TOKEN
                        if unsafe:
                            # Deliberately wrong, only for the synthetic negative control.
                            headers.update(dict(self.headers))
                    else:
                        for name in ('Authorization', 'ChatGPT-Account-ID'):
                            if self.headers.get(name):
                                headers[name] = self.headers[name]
                    try:
                        address = ('127.0.0.1', 1) if mode['unavailable'] else targets[target]
                        status, reply = send(address, body, headers)
                        if status != 200:
                            status, reply = 502, b'Upstream failed; no fallback'
                    except OSError:
                        status, reply = 502, b'Upstream unavailable; no fallback'
                self.send_response(status)
                self.end_headers()
                self.wfile.write(reply)

        checks = {}
        with serve(Router) as router:
            headers = {'Authorization': 'Bearer ' + NATIVE_TOKEN, 'ChatGPT-Account-ID': 'fake-account',
                       'Content-Type': 'application/json', 'Cookie': 'fake-cookie', 'X-Private': 'fake-private'}
            status, _ = send(router, {'model': 'fixture-factory'}, headers)
            event = seen[-1]
            checks['alternate_route_selected'] = status == 200 and event['route'] == 'factory'
            checks['independent_factory_credential'] = event['headers'].get('Authorization') == 'Bearer ' + FACTORY_TOKEN
            checks['native_credentials_stripped'] = all(name not in event['headers'] for name in ('ChatGPT-Account-ID', 'Cookie', 'X-Private')) and NATIVE_TOKEN not in json.dumps(event)

            status, _ = send(router, {'model': 'fixture-native'}, headers)
            event = seen[-1]
            checks['signed_in_native_route'] = status == 200 and event['route'] == 'chatgpt' and event['headers'].get('Authorization') == 'Bearer ' + NATIVE_TOKEN and event['headers'].get('ChatGPT-Account-ID') == 'fake-account'

            api_headers = {name: value for name, value in headers.items() if name != 'ChatGPT-Account-ID'}
            status, _ = send(router, {'model': 'fixture-native'}, api_headers)
            checks['native_api_route'] = status == 200 and seen[-1]['route'] == 'openai'

            count = len(seen)
            status, _ = send(router, {'model': 'unknown'}, headers)
            checks['unknown_model_no_upstream'] = status == 400 and len(seen) == count

            mode['upstream_error'] = True
            status, reply = send(router, {'model': 'fixture-factory'}, headers)
            checks['error_body_redacted_no_fallback'] = status == 502 and NATIVE_TOKEN.encode() not in reply and FACTORY_TOKEN.encode() not in reply and len(seen) == count + 1 and seen[-1]['route'] == 'factory'

            count = len(seen)
            mode['unavailable'] = True
            status, reply = send(router, {'model': 'fixture-factory'}, headers)
            checks['unavailable_no_fallback'] = status == 502 and len(seen) == count and reply == b'Upstream unavailable; no fallback'
    return {'schema': 'tofa-native-provider-router-prototype-v1',
            'status': 'passed' if all(checks.values()) else 'failed',
            'deliberate_negative_control': unsafe, 'checks': checks,
            'upstream_requests': len(seen), 'real_credentials_used': False,
            'external_network_requests': 0, 'production_adapter_tested': False,
            'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--unsafe-header-copy', action='store_true')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if Path('/tmp/tofa-presentation-validation').resolve() not in args.out.resolve().parents:
        raise ValueError('output must be below fixed validation root')
    result = experiment(args.unsafe_header_copy)
    with args.out.open('x') as file:
        file.write(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['status'] == 'passed' else 1)
