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
        if method == 'model/list':
            result = {'data': [{'id': 'gpt-5.5', 'model': 'gpt-5.5'}], 'nextCursor': None}
        elif method in ('config/batchWrite', 'config/value/write'):
            Path(os.environ['DESKTOP_CONFIG']).write_text('desktop tools leaked into CLI settings')
            result = {'status': 'ok', 'version': 'fixture-version', 'filePath': os.environ['DESKTOP_CONFIG']}
        elif method == 'thread/start':
            result = {'thread': {'id': '00000000-0000-4000-8000-000000000082', 'cwd': os.environ['DESKTOP_WORKSPACE']},
                      'model': 'gpt-5.4', 'modelProvider': 'openai', 'approvalsReviewer': 'auto_review',
                      'approvalPolicy': 'on-request', 'sandbox': {'type': 'workspaceWrite', 'writableRoots': []}}
        elif method == 'turn/start':
            if os.environ['DESKTOP_TRIAL'] == 'catalog_model':
                print(json.dumps({'method': 'thread/settings/updated', 'params': {'threadId': message['params']['threadId'], 'threadSettings': {'cwd': os.environ['DESKTOP_WORKSPACE'], 'model': 'gpt-5.5', 'modelProvider': 'openai', 'approvalPolicy': 'on-request', 'approvalsReviewer': 'auto_review', 'sandboxPolicy': {'type': 'workspaceWrite', 'networkAccess': False, 'writableRoots': []}}}}), flush=True)
            if os.environ['DESKTOP_TRIAL'] == 'visualization_canonical':
                print(json.dumps({'method': 'thread/settings/updated', 'params': {'threadId': message['params']['threadId'], 'threadSettings': {'cwd': os.environ['DESKTOP_WORKSPACE'], 'model': 'gpt-5.4', 'modelProvider': 'openai', 'approvalPolicy': 'on-request', 'approvalsReviewer': 'auto_review', 'sandboxPolicy': dict(message['params']['sandboxPolicy'], writableRoots=message['params']['sandboxPolicy']['writableRoots'][1:])}}}), flush=True)
            if os.environ['DESKTOP_TRIAL'] == 'rerouted':
                print(json.dumps({'method': 'model/rerouted', 'params': {'threadId': message['params']['threadId'], 'turnId': 'private-turn', 'fromModel': 'gpt-5.4', 'toModel': 'gpt-5.5', 'reason': 'highRiskCyber'}}), flush=True)
            Path(os.environ['DESKTOP_EFFECT']).write_text('executed')
            result = {'turn': {'id': 'private-turn'}}
        else:
            result = {}
        print(json.dumps({'id': message['id'], 'result': result}), flush=True)


def trial(override):
    with tempfile.TemporaryDirectory(prefix='desktop-engine-') as temporary:
        root = Path(temporary).resolve()
        native = root / 'native'
        native.write_text('#!' + sys.executable + '\nimport runpy\nrunpy.run_path(' + repr(__file__) + ',run_name="__main__")\n')
        native.chmod(0o700)
        owner = root / 'powershell.exe'
        owner.write_text('#!' + sys.executable + '\nprint(' + repr('S-1-5-21-999' if override == 'visualization_owner_wrong' else 'S-1-5-21-82') + ')\n')
        owner.chmod(0o700)
        configuration = root / 'configuration.json'
        shared = root / 'config.toml'
        shared.write_text('unchanged CLI settings')
        configuration.write_text(json.dumps({'engine': str(native), 'sha256': hashlib.sha256(native.read_bytes()).hexdigest(),
                                             'evidence_dir': str(root), 'visualization_root': str(root / 'visualizations'), 'sid': 'S-1-5-21-82', 'workspace': str(root), 'prompt': 'synthetic'}))
        bridge = Path(__file__).resolve().parents[1] / 'windows_desktop_bridge.py'
        env = dict(os.environ, PATH=str(root) + os.pathsep + os.environ['PATH'], TOFA_DESKTOP_PROBE_CONFIG=str(configuration), DESKTOP_WORKSPACE=str(root),
                   DESKTOP_EFFECT=str(root / 'effect'), DESKTOP_CONFIG=str(shared), DESKTOP_TRIAL=override)
        child = subprocess.Popen([sys.executable, str(bridge), '--observe', 'app-server'], env=env,
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            settings = None
            if override in ('settings', 'environment_settings', 'permission_write'):
                edits = [{'keyPath': 'mcp_servers.node_repl', 'value': {'command': 'synthetic-server'}, 'mergeStrategy': 'replace'}]
                if override == 'permission_write': edits = [{'keyPath': 'approvals_reviewer', 'value': 'user', 'mergeStrategy': 'replace'}]
                if override == 'environment_settings':
                    edits.extend({'keyPath': 'shell_environment_policy.set.' + name, 'value': None, 'mergeStrategy': 'replace'} for name in ('BROWSER_USE_AVAILABLE_BACKENDS', 'NODE_REPL_TRUSTED_CODE_PATHS'))
                child.stdin.write(json.dumps({'id': 3, 'method': 'config/batchWrite', 'params': {
                    'filePath': None, 'reloadUserConfig': True, 'edits': edits}}) + '\n')
                child.stdin.flush()
                settings = json.loads(child.stdout.readline())
                if 'error' in settings and override == 'permission_write':
                    child.stdin.close()
                    child.wait(timeout=5)
                    return {'refused': True, 'executed': False, 'exit_code': child.returncode,
                            'settings_unchanged': shared.read_text() == 'unchanged CLI settings'}
            child.stdin.write(json.dumps({'id': 1, 'method': 'thread/start', 'params': {'cwd': str(root)}}) + '\n')
            child.stdin.flush()
            first = json.loads(child.stdout.readline())
            if override == 'catalog_model':
                child.stdin.write(json.dumps({'id': 6, 'method': 'model/list', 'params': {}}) + '\n')
                child.stdin.flush()
                json.loads(child.stdout.readline())
            params = {'threadId': first['result']['thread']['id'], 'input': [{'type': 'text', 'text': 'synthetic'}]}
            if override == 'background':
                child.stdin.write(json.dumps({'id': 4, 'method': 'turn/start', 'params': {'threadId': first['result']['thread']['id'], 'input': [{'type': 'text', 'text': 'Generate a title for this synthetic conversation'}]}}) + '\n')
                child.stdin.flush()
                background = json.loads(child.stdout.readline())
                background_blocked = 'error' in background and not (root / 'effect').exists()
            if override == 'catalog_model': params['collaborationMode'] = {'mode': 'default', 'settings': {'model': 'gpt-5.5'}}
            if override == 'whitespace': params['input'][0]['text'] = 'synthetic\n'
            if override.startswith('visualization'):
                params['sandboxPolicy'] = {'type': 'workspaceWrite', 'networkAccess': False, 'writableRoots': [str(root), str(root / 'visualizations' / '2026' / '10' / '06' / first['result']['thread']['id'])]}
            if override == 'visualization_other_thread': params['sandboxPolicy']['writableRoots'][1] = str(root / 'visualizations' / '2026' / '10' / '06' / '00000000-0000-4000-8000-000000000099')
            if override == 'visualization_shared': params['sandboxPolicy']['writableRoots'][1] = str(root / 'visualizations')
            if override == 'visualization_reparse':
                (root / 'elsewhere').mkdir()
                (root / 'visualizations').symlink_to(root / 'elsewhere', target_is_directory=True)
            if override == 'unsafe': params['sandboxPolicy'] = {'type': 'dangerFullAccess'}
            if override == 'network': params['sandboxPolicy'] = {'type': 'workspaceWrite', 'networkAccess': True}
            if override == 'model': params['model'] = 'gpt-unexpected'
            if override == 'reviewer_alias': params['approvalsReviewer'] = 'guardian_subagent'
            if override == 'roots': params['runtimeWorkspaceRoots'] = [str(root.parent)]
            if override == 'local_environment': params['environments'] = [{'environmentId': 'local', 'cwd': str(root), 'runtimeWorkspaceRoots': [str(root)]}]
            if override == 'environment': params['environments'] = [{'id': 'unrelated-environment'}]
            child.stdin.write(json.dumps({'id': 2, 'method': 'turn/start', 'params': params}) + '\n')
            child.stdin.flush()
            second = json.loads(child.stdout.readline())
            while 'method' in second: second = json.loads(child.stdout.readline())
            if override == 'late_write':
                child.stdin.write(json.dumps({'id': 5, 'method': 'config/value/write', 'params': {'keyPath': 'approvals_reviewer', 'value': 'user', 'mergeStrategy': 'replace'}}) + '\n')
                child.stdin.flush()
                late = json.loads(child.stdout.readline())
            child.stdin.close()
            child.wait(timeout=5)
            result = {'refused': 'error' in second, 'executed': (root / 'effect').exists(), 'exit_code': child.returncode}
            if override == 'catalog_model':
                events = [json.loads(line) for path in root.glob('bridge-*.jsonl') for line in path.read_text().splitlines()]
                result['model_observed'] = next((item['model'] for item in events if item['event'] == 'thread_settings_updated'), None)
            if override.startswith('visualization'):
                events = [json.loads(line) for path in root.glob('bridge-*.jsonl') for line in path.read_text().splitlines()]
                result['visualization_roots'] = sum(item['event'] == 'native_visualization_scope' for item in events)
                if override == 'visualization_canonical': result['policy_preserved'] = not any(item['event'] == 'policy_refused' for item in events)
            if override == 'rerouted':
                events = [json.loads(line) for path in root.glob('bridge-*.jsonl') for line in path.read_text().splitlines()]
                result['policy_preserved'] = not any(item['event'] in ('invalid_identity', 'policy_refused') for item in events)
            if override == 'late_write':
                events = [json.loads(line) for path in root.glob('bridge-*.jsonl') for line in path.read_text().splitlines()]
                result.update(late_write_refused='error' in late, policy_preserved=not any(item['event'] == 'policy_refused' for item in events))
            if override == 'background':
                events = [json.loads(line) for path in root.glob('bridge-*.jsonl') for line in path.read_text().splitlines()]
                result.update(background_blocked=background_blocked)
                result['refused'] = result['refused'] or any(item['event'] == 'policy_refused' for item in events)
            if settings is not None:
                result.update(settings_unchanged=shared.read_text() == 'unchanged CLI settings',
                              settings_rejected='error' in settings)
            return result
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)
            child.stdout.close()
            child.stderr.close()


if __name__ == '__main__':
    engine()
