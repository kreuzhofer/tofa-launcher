"""Owned subprocess fixture for collector orchestration; never starts Desktop."""
import http.server
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import time
import urllib.request


def save(path, value):
    with open(path, 'x', opener=lambda name, flags: os.open(name, flags, 0o600)) as stream:
        json.dump(value, stream)


root = Path(__file__).parent
if sys.argv[1:3] == ['desktop-qualification', 'snapshot']:
    print((root/'snapshot.json').read_text())
    raise SystemExit(0)
assert sys.argv[1:3] == ['launch', 'codex-desktop']
run = Path.cwd().parent
control = json.loads((run/'observer.json').read_text())
stopped = threading.Event()
token = secrets.token_hex(32)
child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(20)'])
profile = root/'profile'
(profile/'SingletonLock').symlink_to('fixture-'+str(child.pid))


class Control(http.server.BaseHTTPRequestHandler):
    def log_message(self, *unused):
        pass

    def do_POST(self):
        assert self.path == '/evaluation-stop'
        assert self.headers['Authorization'] == 'Bearer '+token
        save(run/'fixture-stop.json', {'launcher_pid': os.getpid(), 'child_pid': child.pid})
        self.send_response(204)
        self.end_headers()
        stopped.set()


server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Control)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
try:
    body = {'version': 2, 'endpoint': 'http://127.0.0.1:'+str(server.server_port),
            'control_token': token, 'inference_token': secrets.token_hex(32)}
    request = urllib.request.Request(control['endpoint']+'/register',
        data=json.dumps(body).encode(), headers={'Authorization': 'Bearer '+control['secret']})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=3) as response:
        assert response.status == 200
    save(run/'start.json', {'fixture_only': True})
    deadline = time.monotonic()+8
    while not (run/'process.json').exists():
        if time.monotonic() >= deadline:
            raise RuntimeError('collector did not observe its owned child')
        time.sleep(.02)
    print('owned launcher stdout', flush=True)
    print('owned launcher stderr', file=sys.stderr, flush=True)
    save(run/'finish.request', {'fixture_only': True})
    if not stopped.wait(8):
        raise RuntimeError('collector did not stop its owned route')
finally:
    child.terminate()
    child.wait(timeout=3)
    (profile/'SingletonLock').unlink()
    server.shutdown()
    server.server_close()
    thread.join(timeout=3)
