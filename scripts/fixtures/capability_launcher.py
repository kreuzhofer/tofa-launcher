"""Synthetic executable boundary for capability command tests. Loopback only."""
import http.client
import http.server
import json
import os
from pathlib import Path
import sys
import threading
import time
from urllib.parse import urlsplit


def post(endpoint, path, token, body):
    target = urlsplit(endpoint)
    assert target.hostname == '127.0.0.1'
    connection = http.client.HTTPConnection(target.hostname, target.port, timeout=5)
    connection.request('POST', path, json.dumps(body), {'Authorization': 'Bearer ' + token})
    response = connection.getresponse()
    data = response.read()
    connection.close()
    assert response.status == 200, (response.status, data)


if sys.argv[1] == '--version':
    print('codex-cli 0.162.0')
elif sys.argv[1] == 'evaluation-protocol':
    print('{"version":1}')
elif sys.argv[1] == 'models':
    print('moonshotai/Kimi-K3\nzai-org/GLM-5.3-Flash\nnvidia/Nemotron-3_5-Lightning')
elif sys.argv[1] == 'launch':
    config = json.loads(Path(sys.argv[sys.argv.index('--evaluation-observer') + 1]).read_text())
    class Upstream(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_POST(self):
            self.rfile.read(int(self.headers.get('Content-Length', 0)))
            self.send_response(200); self.send_header('Content-Type', 'text/event-stream'); self.end_headers()
            text = '[Deck](' + str(Path.cwd() / 'fixtures/sample-deck.pptx') + ') and [PDF](' + str(Path.cwd() / 'fixtures/sample-deck.pdf') + ')'
            event = {'type': 'response.completed', 'response': {'model': 'moonshotai/Kimi-K3',
                'output': [{'type': 'message', 'role': 'assistant', 'content': [{'type': 'output_text', 'text': text}]}],
                'usage': {'input_tokens': 10, 'output_tokens': 20}}}
            if os.environ.get('CAPABILITY_FIXTURE_USAGE') == 'missing': del event['response']['usage']
            elif os.environ.get('CAPABILITY_FIXTURE_USAGE') == 'partial': del event['response']['usage']['output_tokens']
            self.wfile.write(('data: ' + json.dumps(event) + '\n\n').encode())
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Upstream)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        post(config['endpoint'], '/register', config['secret'],
             {'endpoint': 'http://127.0.0.1:' + str(server.server_port), 'token': 'synthetic-token'})
        prompt = sys.stdin.read()
        post(config['endpoint'], '/responses', 'synthetic-token', {'model': 'moonshotai/Kimi-K3', 'stream': True,
             'input': [{'role': 'user', 'content': '<cwd>' + str(Path.cwd()) + '</cwd>\n' + prompt}], 'tools': []})
        if os.environ.get('CAPABILITY_FIXTURE_SLOW'):
            Path('started').write_text('synthetic owned process')
            time.sleep(30)
    finally:
        server.shutdown(); server.server_close()
else:
    raise SystemExit(2)
