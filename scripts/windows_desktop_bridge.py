"""Disposable desktop bridge: native transport plus bounded, correlated evidence."""
import datetime
import hashlib
import json
import ntpath
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import threading
from windows_template_probe import workspace_owner
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
    items: dict[tuple[str, str, str], int] = {}
    reviews: dict[str, dict[str, Any]] = {}
    catalog_models: set[str] = set()
    admitted: set[str] = set()
    restricted = {'tool_registration_refused': 0, 'unrelated_turn_refused': 0}
    lock, stdout_lock = threading.Lock(), threading.Lock()
    workspace = ntpath.normcase(ntpath.normpath(config['workspace']))
    with output.open('x', encoding='utf-8') as evidence:
        def record(event, **fields):
            if event in restricted:
                restricted[event] += 1
                if restricted[event] > 128: raise ValueError('restriction_limit')
            evidence.write(json.dumps(dict(event=event, bridge_pid=os.getpid(), **fields)) + '\n')
            evidence.flush()

        def write(raw):
            with stdout_lock:
                sys.stdout.buffer.write(raw)
                sys.stdout.buffer.flush()

        def roots_safe(paths):
            return isinstance(paths, list) and all(isinstance(path, str)
                and ntpath.normcase(ntpath.normpath(path)) == workspace for path in paths)

        def environments_safe(value):
            if value in (None, []): return True
            return (isinstance(value, list) and len(value) == 1 and isinstance(value[0], dict)
                    and set(value[0]) <= {'environmentId', 'cwd', 'runtimeWorkspaceRoots'}
                    and value[0].get('environmentId') == 'local'
                    and isinstance(value[0].get('cwd'), str)
                    and ntpath.normcase(ntpath.normpath(value[0]['cwd'])) == workspace
                    and (value[0].get('runtimeWorkspaceRoots') is None or roots_safe(value[0]['runtimeWorkspaceRoots'])))

        def sandbox_roots_safe(paths, thread_id):
            if roots_safe(paths): return True
            if (not isinstance(paths, list) or not 1 <= len(paths) <= 2 or not all(isinstance(path, str) for path in paths)
                    or not threads.get(thread_id, {}).get('fresh')
                    or not isinstance(thread_id, str) or not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', thread_id)):
                return False
            extra = [path for path in paths if ntpath.normcase(ntpath.normpath(path)) != workspace]
            if len(extra) != 1 or any(part in ('.', '..') for part in extra[0].replace('\\', '/').split('/')): return False
            relative = ntpath.relpath(extra[0], config['visualization_root']).split('\\')
            if len(relative) != 4 or relative[-1] != thread_id: return False
            try: datetime.date.fromisoformat('-'.join(relative[:3]))
            except ValueError: return False
            existing = None
            for path in (Path(extra[0]), *Path(extra[0]).parents):
                try: metadata = path.lstat()
                except FileNotFoundError: continue
                if path.is_symlink() or getattr(metadata, 'st_file_attributes', 0) & 0x400 or not path.is_dir(): return False
                if existing is None: existing = path
            return existing is not None and workspace_owner(existing) == config['sid']

        def sandbox_safe(value, thread_id=None):
            return (isinstance(value, dict) and value.get('type') == 'workspaceWrite'
                    and value.get('networkAccess', False) is False
                    and sandbox_roots_safe(value.get('writableRoots', []), thread_id))

        def overrides_safe(params, model, thread_id=None):
            collaboration = params.get('collaborationMode') or {}
            selected_model = (collaboration.get('settings') or {}).get('model')
            effective_model = selected_model or params.get('model') or model
            return (effective_model in catalog_models or effective_model == model) and (params.get('model') in (None, effective_model) and selected_model in (None, effective_model)
                    and params.get('modelProvider') in (None, 'openai')
                    and environments_safe(params.get('environments'))
                    and (params.get('runtimeWorkspaceRoots') is None or roots_safe(params['runtimeWorkspaceRoots']))
                    and params.get('approvalPolicy') in (None, 'on-request')
                    and params.get('approvalsReviewer') in (None, 'auto_review', 'guardian_subagent')
                    and (params.get('sandboxPolicy') is None or sandbox_safe(params['sandboxPolicy'], thread_id))
                    and all(params.get(key) is None for key in ('permissions', 'permissionProfile', 'permissionsProfile'))
                    and (params.get('cwd') is None or ntpath.normcase(ntpath.normpath(params['cwd'])) == workspace))

        def bind_turn(thread_id, turn_id):
            if thread_id not in admitted or not isinstance(turn_id, str) or not turn_id:
                raise ValueError('unadmitted_turn')
            key = (thread_id, turn_id)
            if key not in turns:
                if len(turns) >= 16: raise ValueError('turn_limit')
                turns[key] = len(turns) + 1
                record('turn_admitted', thread=threads[thread_id]['ordinal'], turn=turns[key], model=threads[thread_id]['selected_model'])
            return {'thread': threads[thread_id]['ordinal'], 'turn': turns[key]}

        def bind_item(thread_id, turn_id, item_id):
            if not isinstance(item_id, str) or not item_id: raise ValueError('missing_review_target')
            key = (thread_id, turn_id, item_id)
            if key not in items:
                if len(items) >= 16: raise ValueError('item_limit')
                items[key] = len(items) + 1
            return items[key]

        def synthetic_command(command):
            if config.get('expected_command') is not None:
                if command == config['expected_command']: return True
                # Native command/review events use shlex_join(argv), including on Windows.
                try: arguments = shlex.split(command)
                except ValueError: return False
                return (len(arguments) >= 3 and isinstance(config.get('shell_path'), str)
                        and ntpath.normcase(arguments[0]) == ntpath.normcase(config['shell_path'])
                        and [value.lower() for value in arguments[1:-2]] in ([], ['-noprofile'], ['-noprofile', '-noninteractive'])
                        and arguments[-2].lower() in ('-command', '-c') and arguments[-1] == config['expected_command'])
            return config.get('marker_name', 'tofa-desktop-smoke.txt') in command

        def observe(raw, request):
            try:
                message = json.loads(raw)
                if not isinstance(message, dict): raise ValueError('invalid_message')
                method, params = message.get('method'), message.get('params', {})
                if request:
                    if method in ('config/value/write', 'config/batchWrite'):
                        edits = params.get('edits', [params])
                        tool_keys = {'mcp_servers.node_repl', 'mcp_servers.cua_repl'}
                        environment_keys = {'shell_environment_policy.set.BROWSER_USE_AVAILABLE_BACKENDS',
                                            'shell_environment_policy.set.NODE_REPL_TRUSTED_CODE_PATHS'}
                        registration = (params.get('filePath') is None and bool(edits)
                            and all(item.get('mergeStrategy') == 'replace' and (
                                item.get('keyPath') in tool_keys and (item.get('value') is None or isinstance(item.get('value'), dict))
                                or item.get('keyPath') in environment_keys and item.get('value') is None) for item in edits))
                        if registration:
                            record('tool_registration_refused')
                            write((json.dumps({'id': message.get('id'), 'error': {'code': -32600,
                                'message': 'Desktop tool registration is unavailable in this bounded test; shared CLI settings were not changed'}}) + '\n').encode())
                            return False
                        record('policy_refused', reason='shared_write_unsupported')
                        write((json.dumps({'id': message.get('id'), 'error': {'code': -32600,
                            'message': 'Shared configuration writes are not supported by this bounded desktop test'}}) + '\n').encode())
                        return False
                    # Refuse unsafe or unrelated turns before they reach the native
                    # engine. Approval requests/responses themselves stay native.
                    if method in ('turn/start', 'turn/settings/update', 'turn/steer'):
                        thread_id = params.get('threadId')
                        thread = threads.get(thread_id, {})
                        inputs = params.get('input', [])
                        synthetic = (len(inputs) == 1 and inputs[0].get('type') == 'text'
                                     and isinstance(inputs[0].get('text'), str)
                                     and inputs[0]['text'].strip() == config['prompt'])
                        allowed = (method == 'turn/start' and thread.get('safe') is True
                                   and synthetic and not admitted and overrides_safe(params, thread['model'], thread_id))
                        if not allowed:
                            if synthetic: record('synthetic_guard', thread_verified=thread.get('safe') is True, sandbox_verified=params.get('sandboxPolicy') is None or sandbox_safe(params['sandboxPolicy'], thread_id), model_verified=overrides_safe({key: value for key, value in params.items() if key in ('model', 'collaborationMode')}, thread.get('model'), thread_id))
                            record('unrelated_turn_refused' if method == 'turn/start' and not synthetic else 'policy_refused',
                                   reason='synthetic_policy' if synthetic else 'unrelated_turn')
                            write((json.dumps({'id': message.get('id'), 'error': {
                                'code': -32001, 'message': 'Desktop qualification refused unsafe or unrelated turn'}}) + '\n').encode())
                            return False
                        if not roots_safe((params.get('sandboxPolicy') or {}).get('writableRoots', [])):
                            record('native_visualization_scope')
                        thread['selected_model'] = ((params.get('collaborationMode') or {}).get('settings') or {}).get('model') or params.get('model') or thread['model']
                        admitted.add(thread_id)
                    if method in ('initialize', 'config/read', 'model/list', 'thread/start', 'thread/resume', 'turn/start'):
                        if len(pending) >= 128: raise ValueError('pending_request_limit')
                        pending[str(message['id'])] = (method, params)
                    return True
                # Server requests (including approvals) have a separate ID namespace.
                prior = pending.pop(str(message.get('id')), None) if not method else None
                result = message.get('result', {})
                if prior is not None and isinstance(result, dict):
                    operation, arguments = prior
                    if operation == 'model/list':
                        for item in result.get('data', []):
                            model = item.get('model')
                            if isinstance(model, str) and re.fullmatch(r'(?:gpt-[a-z0-9.-]+|o[0-9][a-z0-9.-]*|codex-[a-z0-9.-]+)', model): catalog_models.add(model)
                        if len(catalog_models) > 256: raise ValueError('model_catalog_limit')
                    if operation == 'initialize':
                        record('initialized', ok='error' not in message, main_connection=message.get('id') == '__codex_initialize__')
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
                                and environments_safe(arguments.get('environments'))
                                and result.get('approvalsReviewer') == 'auto_review'
                                and result.get('approvalPolicy') == 'on-request' and sandbox_safe(result.get('sandbox')))
                        if config.get('record_ownership') and owned and operation == 'thread/start':
                            history = result.get('thread', {}).get('path')
                            if isinstance(history, str) and ntpath.commonpath([ntpath.normcase(history), ntpath.normcase(str(Path.home() / '.codex/sessions'))]) == ntpath.normcase(str(Path.home() / '.codex/sessions')):
                                record('synthetic_history', path=history)
                        ordinal = threads.get(thread_id, {}).get('ordinal', len(threads) + 1)
                        threads[thread_id] = {'ordinal': ordinal, 'safe': safe, 'model': result['model'],
                                              'environment_verified': environments_safe(arguments.get('environments')) and roots_safe(result.get('runtimeWorkspaceRoots', [])),
                                              'fresh': operation == 'thread/start' or threads.get(thread_id, {}).get('fresh') is True}
                        record('thread_ready', thread=ordinal, policy_verified=safe, owned_workspace=owned,
                               requested_model=arguments.get('model') if arguments.get('model') is None or isinstance(arguments.get('model'), str) and re.fullmatch(r'(?:gpt-[a-z0-9.-]+|o[0-9][a-z0-9.-]*|codex-[a-z0-9.-]+)', arguments['model']) else 'unknown',
                               native_reviewer=result.get('approvalsReviewer') if result.get('approvalsReviewer') in ('user', 'auto_review', 'guardian_subagent') else 'unknown',
                               requested_reviewer=arguments.get('approvalsReviewer') if arguments.get('approvalsReviewer') in (None, 'user', 'auto_review', 'guardian_subagent') else 'unknown',
                               reviewer_verified=result.get('approvalsReviewer') == 'auto_review',
                               approval_verified=result.get('approvalPolicy') == 'on-request',
                               sandbox_verified=sandbox_safe(result.get('sandbox')),
                               roots_verified=roots_safe(result.get('runtimeWorkspaceRoots', [])),
                               environment_verified=environments_safe(arguments.get('environments')),
                               model=result['model'], provider='openai', reviewer='auto_review' if safe else 'unexpected')
                    if operation == 'turn/start' and 'error' not in message:
                        bind_turn(arguments.get('threadId'), result.get('turn', {}).get('id'))
                if method == 'thread/settings/updated' and params.get('threadId') in threads:
                    thread_id, updated = params['threadId'], params.get('threadSettings', {})
                    thread = threads[thread_id]
                    model = updated.get('model')
                    if (not isinstance(model, str) or not re.fullmatch(r'(?:gpt-[a-z0-9.-]+|o[0-9][a-z0-9.-]*|codex-[a-z0-9.-]+)', model)
                            or updated.get('modelProvider') != 'openai'):
                        record('invalid_identity')
                        return True
                    owned = ntpath.normcase(ntpath.normpath(updated.get('cwd') or '')) == workspace
                    if thread_id in admitted:
                        policy = updated.get('sandboxPolicy') or {}
                        record('updated_policy_details', environment_verified=thread.get('environment_verified') is True,
                               reviewer=updated.get('approvalsReviewer') if updated.get('approvalsReviewer') in ('auto_review', 'guardian_subagent', 'user') else 'unknown',
                               approval=updated.get('approvalPolicy') if updated.get('approvalPolicy') in ('never', 'on-request', 'untrusted') else 'other',
                               sandbox_present='sandboxPolicy' in updated, sandbox_type=policy.get('type') if policy.get('type') in ('workspaceWrite', 'dangerFullAccess', 'readOnly', 'externalSandbox') else 'other',
                               network_disabled=policy.get('networkAccess', False) is False,
                               root_count=len(policy.get('writableRoots', [])),
                               workspace_roots=sum(isinstance(path, str) and ntpath.normcase(ntpath.normpath(path)) == workspace for path in policy.get('writableRoots', [])))
                    safe = (owned and thread.get('environment_verified') is True
                            and updated.get('approvalsReviewer') == 'auto_review' and updated.get('approvalPolicy') == 'on-request'
                            and sandbox_safe(updated.get('sandboxPolicy'), thread_id))
                    if thread_id in admitted and (not safe or model != thread['selected_model']):
                        record('policy_refused', reason='native_settings_changed')
                    thread.update(safe=safe, model=model)
                    record('thread_settings_updated', thread=thread['ordinal'], policy_verified=safe, owned_workspace=owned,
                           model=model, provider='openai', reviewer='auto_review' if safe else 'unexpected')
                if method == 'model/rerouted' and params.get('threadId') in admitted:
                    record('invalid_identity')
                if method == 'turn/started':
                    bind_turn(params.get('threadId'), params.get('turn', {}).get('id'))
                if method in ('item/autoApprovalReview/started', 'item/autoApprovalReview/completed'):
                    key = (params.get('threadId'), params.get('turnId'))
                    if key not in turns: return True
                    correlation = {'thread': threads[key[0]]['ordinal'], 'turn': turns[key],
                                   'item': bind_item(*key, params.get('targetItemId'))}
                    action = params.get('action', {})
                    if (action.get('type') != 'command' or not isinstance(action.get('command'), str)
                            or not isinstance(action.get('cwd'), str)
                            or ntpath.normcase(ntpath.normpath(action['cwd'])) != workspace):
                        raise ValueError('unsupported_review_action')
                    review_id = params.get('reviewId')
                    if not isinstance(review_id, str) or not review_id: raise ValueError('missing_review_identity')
                    signature = hashlib.sha256(action['command'].encode()).hexdigest()
                    synthetic = synthetic_command(action['command'])
                    if method.endswith('/started'):
                        if review_id in reviews or len(reviews) >= 16: raise ValueError('review_limit')
                        reviews[review_id] = dict(correlation, signature=signature, ordinal=len(reviews) + 1, completed=False)
                        record('review_started', **correlation, review=reviews[review_id]['ordinal'], synthetic_command=synthetic)
                    else:
                        review = reviews.get(review_id, {})
                        if (review.get('completed') is not False or review.get('signature') != signature
                                or any(review.get(name) != value for name, value in correlation.items())):
                            raise ValueError('review_identity_changed')
                        decision = params.get('review', {}).get('status')
                        if decision not in ('approved', 'denied', 'timedOut', 'aborted') or params.get('decisionSource') != 'agent':
                            raise ValueError('unsupported_review_decision')
                        review['completed'] = True
                        record('review_completed', **correlation, review=review['ordinal'],
                               decision=decision, source='agent', synthetic_command=synthetic)
                if method in ('item/completed', 'turn/completed'):
                    turn_id = params.get('turnId') if method == 'item/completed' else params.get('turn', {}).get('id')
                    key = (params.get('threadId'), turn_id)
                    if key not in turns: return True
                    correlation = {'thread': threads[key[0]]['ordinal'], 'turn': turns[key]}
                    if method == 'item/completed' and params.get('item', {}).get('type') == 'commandExecution':
                        item = params['item']
                        item_ordinal = bind_item(*key, item.get('id'))
                        signature = hashlib.sha256(item.get('command', '').encode()).hexdigest()
                        if any(review['item'] == item_ordinal and review['signature'] != signature for review in reviews.values()):
                            raise ValueError('review_command_changed')
                        record('command_completed', success=item.get('exitCode') == 0,
                               synthetic_command=synthetic_command(item.get('command', '')), exit_code_present=item.get('exitCode') is not None,
                               item=item_ordinal, status=item.get('status') if item.get('status') in ('completed', 'failed', 'declined') else 'unknown', **correlation)
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
                          'projects={' + json.dumps(config['workspace']) + '={trust_level="trusted"}}'):
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
