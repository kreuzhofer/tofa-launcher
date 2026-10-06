"""External desktop/native-engine dialogue for the operator CLI fixture."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def engine():
    for line in sys.stdin:
        message = json.loads(line)
        method = message.get('method')
        if method == 'thread/start':
            result = {'thread': {'id': 'private-thread', 'cwd': os.environ['DESKTOP_WORKSPACE']},
                      'model': 'gpt-5.4', 'modelProvider': 'openai', 'approvalsReviewer': 'auto_review',
                      'approvalPolicy': 'on-request', 'sandbox': {'type': 'workspaceWrite', 'writableRoots': []}}
        elif method == 'turn/start':
            Path(os.environ['DESKTOP_EFFECT']).write_text('executed')
            result = {'turn': {'id': 'private-turn'}}
        else:
            result = {}
        print(json.dumps({'id': message['id'], 'result': result}), flush=True)


def trial(override):
    with tempfile.TemporaryDirectory(prefix='desktop-engine-') as temporary:
        root = Path(temporary)
        native = root / 'native'
        native.write_text('#!' + sys.executable + '\nimport runpy\nrunpy.run_path(' + repr(__file__) + ',run_name="__main__")\n')
        native.chmod(0o700)
        configuration = root / 'configuration.json'
        configuration.write_text(json.dumps({'engine': str(native), 'sha256': hashlib.sha256(native.read_bytes()).hexdigest(),
                                             'evidence_dir': str(root), 'workspace': str(root), 'prompt': 'synthetic'}))
        bridge = Path(__file__).resolve().parents[1] / 'windows_desktop_bridge.py'
        env = dict(os.environ, TOFA_DESKTOP_PROBE_CONFIG=str(configuration), DESKTOP_WORKSPACE=str(root),
                   DESKTOP_EFFECT=str(root / 'effect'))
        child = subprocess.Popen([sys.executable, str(bridge), '--observe', 'app-server'], env=env,
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            child.stdin.write(json.dumps({'id': 1, 'method': 'thread/start', 'params': {'cwd': str(root)}}) + '\n')
            child.stdin.flush()
            first = json.loads(child.stdout.readline())
            params = {'threadId': first['result']['thread']['id'], 'input': [{'type': 'text', 'text': 'synthetic'}]}
            if override == 'unsafe': params['sandboxPolicy'] = {'type': 'dangerFullAccess'}
            if override == 'network': params['sandboxPolicy'] = {'type': 'workspaceWrite', 'networkAccess': True}
            if override == 'model': params['model'] = 'gpt-unexpected'
            if override == 'roots': params['runtimeWorkspaceRoots'] = [str(root.parent)]
            if override == 'environment': params['environments'] = [{'id': 'unrelated-environment'}]
            child.stdin.write(json.dumps({'id': 2, 'method': 'turn/start', 'params': params}) + '\n')
            child.stdin.flush()
            second = json.loads(child.stdout.readline())
            child.stdin.close()
            child.wait(timeout=5)
            return {'refused': 'error' in second, 'executed': (root / 'effect').exists(), 'exit_code': child.returncode}
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)
            child.stdout.close()
            child.stderr.close()


if __name__ == '__main__':
    engine()
