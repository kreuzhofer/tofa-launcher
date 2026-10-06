"""Disposable desktop bridge: native transport plus bounded, correlated evidence."""
import hashlib
import json
import ntpath
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
from typing import Any


def main():
    config = json.loads(Path(os.environ['TOFA_DESKTOP_PROBE_CONFIG']).read_text(encoding='utf-8-sig'))
    engine = Path(config['engine'])
    if not engine.is_absolute() or hashlib.sha256(engine.read_bytes()).hexdigest() != config['sha256']:
        return 125
    output = Path(config['evidence_dir']) / ('bridge-' + str(os.getpid()) + '.jsonl')
    pending: dict[str, tuple[str, dict[str, Any]]] = {}
    threads: dict[str, dict[str, Any]] = {}
    turns: dict[tuple[str, str], int] = {}
    admitted: set[str] = set()
    lock, stdout_lock = threading.Lock(), threading.Lock()
    workspace = ntpath.normcase(ntpath.normpath(config['workspace']))
    with output.open('x', encoding='utf-8') as evidence:
        def record(event, **fields):
            evidence.write(json.dumps(dict(event=event, bridge_pid=os.getpid(), **fields)) + '\n')
            evidence.flush()

        def write(raw):
            with stdout_lock:
                sys.stdout.buffer.write(raw)
                sys.stdout.buffer.flush()

        def roots_safe(paths):
            return isinstance(paths, list) and all(isinstance(path, str)
                and ntpath.normcase(ntpath.normpath(path)) == workspace for path in paths)

        def sandbox_safe(value):
            return (isinstance(value, dict) and value.get('type') == 'workspaceWrite'
                    and value.get('networkAccess', False) is False
                    and roots_safe(value.get('writableRoots', [])))

        def overrides_safe(params, model):
            collaboration = params.get('collaborationMode') or {}
            selected_model = (collaboration.get('settings') or {}).get('model')
            return (params.get('model') in (None, model) and selected_model in (None, model)
                    and params.get('modelProvider') in (None, 'openai')
                    and params.get('environments') in (None, [])
                    and (params.get('runtimeWorkspaceRoots') is None or roots_safe(params['runtimeWorkspaceRoots']))
                    and params.get('approvalPolicy') in (None, 'on-request')
                    and params.get('approvalsReviewer') in (None, 'auto_review')
                    and (params.get('sandboxPolicy') is None or sandbox_safe(params['sandboxPolicy']))
                    and all(params.get(key) is None for key in ('permissions', 'permissionProfile', 'permissionsProfile'))
                    and (params.get('cwd') is None or ntpath.normcase(ntpath.normpath(params['cwd'])) == workspace))

        def bind_turn(thread_id, turn_id):
            if thread_id not in admitted or not isinstance(turn_id, str) or not turn_id:
                raise ValueError('unadmitted_turn')
            key = (thread_id, turn_id)
            if key not in turns:
                if len(turns) >= 16: raise ValueError('turn_limit')
                turns[key] = len(turns) + 1
                record('turn_admitted', thread=threads[thread_id]['ordinal'], turn=turns[key])
            return {'thread': threads[thread_id]['ordinal'], 'turn': turns[key]}

        def observe(raw, request):
            try:
                message = json.loads(raw)
                if not isinstance(message, dict): raise ValueError('invalid_message')
                method, params = message.get('method'), message.get('params', {})
                if request:
                    # Refuse unsafe or unrelated turns before they reach the native
                    # engine. Approval requests/responses themselves stay native.
                    if method in ('turn/start', 'turn/settings/update', 'turn/steer'):
                        thread_id = params.get('threadId')
                        thread = threads.get(thread_id, {})
                        inputs = params.get('input', [])
                        synthetic = (len(inputs) == 1 and inputs[0].get('type') == 'text'
                                     and inputs[0].get('text') == config['prompt'])
                        allowed = (method == 'turn/start' and thread.get('safe') is True
                                   and synthetic and not admitted and overrides_safe(params, thread['model']))
                        if not allowed:
                            record('policy_refused')
                            write((json.dumps({'id': message.get('id'), 'error': {
                                'code': -32001, 'message': 'Desktop qualification refused unsafe or unrelated turn'}}) + '\n').encode())
                            return False
                        admitted.add(thread_id)
                    if method in ('initialize', 'config/read', 'thread/start', 'thread/resume', 'turn/start'):
                        if len(pending) >= 128: raise ValueError('pending_request_limit')
                        pending[str(message['id'])] = (method, params)
                    return True
                prior = pending.pop(str(message.get('id')), None)
                result = message.get('result', {})
                if prior is not None and isinstance(result, dict):
                    operation, arguments = prior
                    if operation == 'initialize': record('initialized', ok='error' not in message)
                    if operation == 'config/read':
                        settings = result.get('config', {})
                        projects = settings.get('projects', {})
                        trusted = any(ntpath.normcase(ntpath.normpath(key)) == workspace and item.get('trust_level') == 'trusted'
                                      for key, item in projects.items() if isinstance(item, dict))
                        record('settings', workspace_trusted=trusted,
                               automatic_review=settings.get('approvals_reviewer') == 'auto_review',
                               full_access_disabled=settings.get('sandbox_mode') == 'workspace-write')
                    if operation in ('thread/start', 'thread/resume'):
                        thread_id = result.get('thread', {}).get('id')
                        owned = ntpath.normcase(ntpath.normpath(arguments.get('cwd') or result.get('thread', {}).get('cwd') or '')) == workspace
                        if (not isinstance(thread_id, str) or not thread_id or len(threads) >= 128
                                or not isinstance(result.get('model'), str)
                                or not re.fullmatch(r'(?:gpt-[a-z0-9.-]+|o[0-9][a-z0-9.-]*|codex-[a-z0-9.-]+)', result['model'])
                                or result.get('modelProvider') != 'openai'):
                            record('invalid_identity')
                            return True
                        safe = (owned and roots_safe(result.get('runtimeWorkspaceRoots', []))
                                and arguments.get('environments') in (None, [])
                                and result.get('approvalsReviewer') == 'auto_review'
                                and result.get('approvalPolicy') == 'on-request' and sandbox_safe(result.get('sandbox')))
                        ordinal = threads.get(thread_id, {}).get('ordinal', len(threads) + 1)
                        threads[thread_id] = {'ordinal': ordinal, 'safe': safe, 'model': result['model']}
                        record('thread_ready', thread=ordinal, policy_verified=safe, owned_workspace=owned,
                               model=result['model'], provider='openai', reviewer='auto_review' if safe else 'unexpected')
                    if operation == 'turn/start' and 'error' not in message:
                        bind_turn(arguments.get('threadId'), result.get('turn', {}).get('id'))
                if method == 'turn/started':
                    bind_turn(params.get('threadId'), params.get('turn', {}).get('id'))
                if method in ('item/completed', 'turn/completed'):
                    turn_id = params.get('turnId') if method == 'item/completed' else params.get('turn', {}).get('id')
                    key = (params.get('threadId'), turn_id)
                    if key not in turns: return True
                    correlation = {'thread': threads[key[0]]['ordinal'], 'turn': turns[key]}
                    if method == 'item/completed' and params.get('item', {}).get('type') == 'commandExecution':
                        item = params['item']
                        record('command_completed', success=item.get('exitCode') == 0,
                               synthetic_command='tofa-desktop-smoke.txt' in item.get('command', ''), **correlation)
                    if method == 'turn/completed':
                        record('turn_completed', success=params.get('turn', {}).get('status') == 'completed', **correlation)
                return True
            except (ValueError, TypeError, KeyError, AttributeError):
                record('invalid_observation')
                if request:
                    # Fail closed when a request cannot be observed safely.
                    raise ValueError('invalid_desktop_request')
                return True

        arguments = sys.argv[2:]
        if 'app-server' in arguments:
            for value in ('windows.sandbox="elevated"', 'sandbox_mode="workspace-write"',
                          'approval_policy="on-request"', 'approvals_reviewer="auto_review"',
                          'projects.' + json.dumps(config['workspace']) + '.trust_level="trusted"'):
                arguments.extend(['-c', value])
        record('start', pid=os.getpid(), parent_pid=os.getppid(), engine_sha256=config['sha256'],
               app_server='app-server' in arguments)
        child = subprocess.Popen([str(engine), *arguments], stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, stderr=sys.stderr.buffer)
        input_pipe, output_pipe = child.stdin, child.stdout
        assert input_pipe is not None and output_pipe is not None
        record('child', pid=child.pid)
        def forward():
            try:
                while True:
                    line = sys.stdin.buffer.readline(1024 * 1024)
                    if not line: break
                    with lock: allowed = observe(line, True)
                    if allowed:
                        input_pipe.write(line)
                        input_pipe.flush()
            except (OSError, ValueError):
                child.kill()
            finally:
                input_pipe.close()
        threading.Thread(target=forward, daemon=True).start()
        try:
            while True:
                line = output_pipe.readline(1024 * 1024)
                if not line: break
                with lock: observe(line, False)
                write(line)
            code = child.wait(timeout=5)
            with lock: record('exit', exit_code=code)
            return code
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:
        sys.exit(125)
