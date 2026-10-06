"""External VM fixture; forbidden lifecycle operations fail visibly."""
import json
import gzip
import hashlib
import base64
import os
import re
from pathlib import Path
import sys

path = Path(os.environ['TEMPLATE_FIXTURE_STATE'])
state = json.loads(path.read_text())
args = sys.argv[1:]
request = state.get('request')
guest_uuid = state.get('guest_uuid', state['vms'][0]['uuid']).lower()
if args == ['list']:
    print('UUID                                 Status   Name')
    for vm in state['vms']:
        print(vm['uuid'], 'PRIVATE_KEY' if state['mode'] == 'inventory_secret' else vm['status'], vm['name'])
elif args[:1] == ['exec'] and args[1].lower() == guest_uuid:
    script = base64.b64decode(args[-1]).decode('utf-16-le')
    if '# tofa-template-protected-root' in script:
        state['protected_root'] = script.split("$root='C:\\Users\\Public\\", 1)[1].split("'", 1)[0]
        path.write_text(json.dumps(state))
    elif '# tofa-template-preflight' in script:
        request = json.loads(base64.b64decode(script.split("$requestJson='", 1)[1].split("'", 1)[0]))
        report = {'run': request['run'], 'phase': 'preflight', 'ok': True,
                  'os': {'name': 'Windows 11', 'version': '10.0.26200', 'build': '26200', 'architecture': 'ARM64'},
                  'user': {'sid': 'S-1-5-21-123-456-789-1001', 'session': 2},
                  'python': r'C:\Python313ARM\python.exe'}
        if state['mode'] == 'no_session':
            report.update(ok=False, reason='test_user_sign_in_required', outcome='bootstrap_required')
        if state['mode'] == 'boot_session_delay' and not state.get('session_waited'):
            state['session_waited'] = True
            report.update(ok=False, reason='test_user_sign_in_required', outcome='bootstrap_required')
        if state['mode'] == 'register_client':
            if request.get('operation') == 'prepare':
                report['register_package'] = r'C:\Program Files\WindowsApps\OpenAI.Codex_26.928.21956.0_arm64__2p2nqsd0c76g0'
            else:
                report.update(ok=False, reason='native_client_missing_or_ambiguous')
        if state['mode'] == 'unsupported_guest': report['os']['architecture'] = 'AMD64'
        if state['mode'] == 'bad_sid': report['user']['sid'] = 42
        if state['mode'] == 'missing_python': report.pop('python')
        if state['mode'] == 'unsafe_python': report['python'] = r'\\server\share\payload.exe'
        if state['mode'] == 'bad_reason': report.update(ok=False, reason=[])
        if state['mode'] == 'transport_secret': sys.exit('PRIVATE_KEY UNRELATED_CONTENT')
        if state['mode'] == 'progress':
            sys.stderr.write('#< CLIXML\n<Objs><Obj S="progress"/></Objs>')
        if state['mode'] == 'error_clixml':
            sys.stderr.write('#< CLIXML\n<Objs><S S="Error">PRIVATE_KEY</S></Objs>')
        state['preflight'] = report
        path.write_text(json.dumps(state))
    elif '# tofa-template-stage' in script:
        state['probe_window_style'] = re.search(r'-WindowStyle (\w+)', script).group(1)
        state['task_prepared'] = True
        path.write_text(json.dumps(state))
    elif '# tofa-template-wait' in script:
        if not state.get('task_prepared'): sys.exit('task must be staged before execution')
        if state['mode'] == 'native_transport_failure': sys.exit('PRIVATE_KEY UNRELATED_CONTENT')
        state['effects'].append({'vm': args[1], 'effect': 'limited_user_probe'})
        if request.get('register_package'):
            state['effects'].append({'vm': args[1], 'effect': 'registered_test_user_client'})
        if request.get('initialize_sandbox'):
            state['effects'].append({'vm': args[1], 'effect': 'native_sandbox_setup_requested'})
        path.write_text(json.dumps(state))
    else:
        sys.exit('unexpected guest mutation')
elif args[:2] == ['file', 'push'] and args[2].lower() == guest_uuid:
    if state['mode'] == 'protected_staging' and not state.get('protected_root'):
        sys.exit('cannot stage executable harness in an unprotected location')
    content = sys.stdin.buffer.read()
    if args[3].endswith('\\request.json'):
        state['request'] = json.loads(content)
    if args[3].endswith('\\candidate.exe.gz'):
        state['candidate_transfer_sha256'] = hashlib.sha256(gzip.decompress(content)).hexdigest()
        state['candidate_transfer_size'] = len(content)
    state['effects'].append({'vm': args[2], 'effect': 'staged_owned_file'})
    path.write_text(json.dumps(state))
elif args[:2] == ['file', 'pull'] and args[2].lower() == guest_uuid:
    if args[3].endswith('\\staging.json'):
        print(json.dumps({'run':state['protected_root'], 'phase':'staging', 'ok':True}))
    elif args[3].endswith('\\preflight.json'):
        if state['mode'] == 'delayed' and not state.get('polled'):
            state['polled'] = True
            path.write_text(json.dumps(state))
            sys.stderr.write("Error from event: OSStatus error -2700.\nfailed to open file 'owned-report': The system cannot find the file specified.\n")
            sys.exit(0)
        print(json.dumps(state['preflight']))
    elif args[3].endswith('task-staging.json'):
        print(json.dumps({'run': request['run'], 'phase': 'task_staging', 'ok': True}))
    elif args[3].endswith('task.json'):
        if state['mode'] == 'delayed_task' and not state.get('polled'):
            state['polled'] = True
            path.write_text(json.dumps(state))
            sys.stderr.write("Error from event: OSStatus error -2700.\nfailed to open file 'owned-report': The system cannot find the path specified.\n")
            sys.exit(0)
        task = {'run': request['run'], 'phase': 'completion', 'ok': True,
                'completed': True, 'unregistered': True, 'last_result': 0, 'state': 'Ready'}
        if state['mode'] == 'task_failed': task.update(ok=False, last_result=1)
        if state['mode'] == 'task_incomplete': task.update(ok=False, completed=False, unregistered=False, last_result=267014, state='Running')
        if state['mode'] == 'running_task': task.update(state='Running')
        if state['mode'] == 'host_zero_no_result': sys.exit(0)
        if state['mode'] == 'task_secret': task.update(state='PRIVATE_KEY', last_result='UNRELATED_CONTENT')
        if state['mode'] == 'stale': task['run'] = 'old-run'
        if state['mode'] == 'missing': sys.exit('PRIVATE_KEY missing completion')
        if state['mode'] == 'malformed': print('not json'); sys.exit(0)
        print(json.dumps(task))
    elif args[3].endswith('progress.json'):
        progress = {'run': request['run'], 'phase': 'progress', 'ok': True,
                    'checkpoints': [{'stage': 'user_started', 'elapsed_ms': 0},
                                    {'stage': 'package_discovered', 'elapsed_ms': 400}]}
        if state['mode'] == 'progress_secret': progress['checkpoints'][1]['stage'] = 'PRIVATE_KEY'
        if state['mode'] == 'progress_stale': progress['run'] = 'old-run'
        if state['mode'] == 'progress_negative': progress['checkpoints'][0]['elapsed_ms'] = -1
        print(json.dumps(progress))
    elif args[3].endswith('result.json'):
        if request.get('test_auth'):
            if state['mode'] in ('desktop_bridge_unsafe', 'desktop_bridge_safe', 'desktop_bridge_network', 'desktop_bridge_model', 'desktop_bridge_roots', 'desktop_bridge_environment'):
                import runpy
                bridge_trial = runpy.run_path(str(Path(__file__).with_name('windows_desktop_native.py')))['trial']
                observation = bridge_trial(state['mode'].removeprefix('desktop_bridge_'))
                state['bridge_trial'] = observation
                path.write_text(json.dumps(state))
                if observation['refused']:
                    print(json.dumps({'run': request['run'], 'phase': 'desktop', 'ok': False,
                                      'reason': 'desktop_policy_mismatch', 'checks': {}}))
                    sys.exit(0)
            if state['mode'] == 'desktop_auth_missing':
                print(json.dumps({'run': request['run'], 'phase': 'desktop', 'ok': False,
                                  'reason': 'desktop_authentication_required', 'checks': {'authenticated': False}}))
                sys.exit(0)
            if not request.get('desktop_readiness_only'):
                state['effects'].append({'vm': args[2], 'effect': 'desktop_started'})
            path.write_text(json.dumps(state))
            desktop = {'run': request['run'], 'phase': 'desktop', 'ok': True,
                'reason': 'desktop_smoke_passed', 'route': 'native-desktop-bridge',
                'identity': {'model': 'gpt-5.4', 'provider': 'openai', 'reviewer': 'auto_review',
                             'app_pid': 101, 'bridge_pid': 102, 'engine_pid': 103,
                             'app_sha256': 'c'*64, 'bridge_sha256': 'd'*64,
                             'engine_sha256': 'a'*64, 'package': 'OpenAI.Codex_26.928.21956.0_arm64__2p2nqsd0c76g0'},
                'checks': {key: True for key in ('authenticated', 'workspace_trusted', 'automatic_review', 'readiness_engine_exited',
                    'full_access_disabled', 'bridge_initialized', 'desktop_started', 'command_effect', 'normal_quit',
                    'owned_children_exited', 'cli_defaults_unchanged', 'vendor_service_preserved', 'diagnostics_written')}}
            desktop['execution'] = {name: {'bridge_pid': 102, 'thread': 1, 'turn': 1}
                                    for name in ('admitted', 'command', 'completed')}
            if state['mode'] == 'desktop_mixed_completion': desktop['execution']['completed']['turn'] = 2
            if state['mode'] == 'desktop_diagnostics_failed': desktop['checks']['diagnostics_written'] = False
            if state['mode'] == 'desktop_untrusted': desktop['checks']['workspace_trusted'] = False
            if state['mode'] == 'desktop_wrong_policy': desktop['checks']['automatic_review'] = False
            if state['mode'] == 'desktop_wrong_identity': desktop['identity']['engine_sha256'] = 'b'*64
            if state['mode'] == 'desktop_no_effect': desktop['checks']['command_effect'] = False
            if state['mode'] == 'desktop_cleanup_failed': desktop['checks']['normal_quit'] = False
            if state['mode'] == 'desktop_secret': desktop['identity']['model'] = 'PRIVATE_KEY'
            print(json.dumps(desktop))
            sys.exit(0)
        report = {'run': request['run'], 'phase': 'native', 'ok': True,
            'setup_status': 'completed' if request.get('initialize_sandbox') else 'not_requested',
            'identity': {'client_version': '26.928.21956.0', 'engine_version': '0.159.2',
                         'engine_sha256': 'a'*64, 'package_engine_sha256': 'a'*64,
                         'package': 'OpenAI.Codex_26.928.21956.0_arm64__2p2nqsd0c76g0',
                         'architecture': 'ARM64', 'python_version': '3.13.7',
                         'sid': request['sid'], 'session': request['session']},
            'checks': {'limited_user': True, 'workspace_owned_by_user': True,
                       'harness_read_only': True,
                       'workspace_acl_manageable': True, 'ordinary_write': True,
                       'workspace_write_read': True, 'outside_permission_denied': True,
                       'outside_marker_exists': False, 'full_access_disabled': True,
                       'engine_exited': True, 'markers_removed': True},
            'execution': {'workspace_exit_code': 0, 'outside_exit_code': 1,
                          'outside_denial_signal': 'GetContentWriterUnauthorizedAccessError'}}
        if state['mode'] == 'wrong_engine': report['identity']['engine_sha256'] = 'b'*64
        if state['mode'] == 'desktop_busy': report.update(ok=False, reason='native_client_busy')
        if state['mode'] == 'wrong_user': report['identity']['sid'] = 'S-1-5-18'
        if state['mode'] == 'no_denial': report['execution']['outside_denial_signal'] = 'command not found'
        if state['mode'] == 'outside_written': report['checks']['outside_marker_exists'] = True
        if state['mode'] == 'full_access': report['checks']['full_access_disabled'] = False
        if state['mode'] == 'not_manageable': report['checks']['workspace_acl_manageable'] = False
        if state['mode'] == 'consent': report.update(ok=False, reason='native_sandbox_consent_required')
        if state['mode'] == 'bad_native_reason': report.update(ok=False, reason=[])
        if state['mode'] == 'missing_setup_completion': report['setup_status'] = 'awaiting_completion'
        if state['mode'] == 'needs_setup' and not request.get('initialize_sandbox'):
            report.update(ok=False, reason='native_sandbox_consent_required')
        if state['mode'] == 'secrets':
            report.update(raw_logs='PRIVATE_KEY', unrelated='UNRELATED_CONTENT')
            report['identity']['package'] = 'PRIVATE_KEY'
        if request['workspace_fixture'] == 'acl-unmanageable':
            report.update(ok=False, reason='native_workspace_acl_failed')
            report['checks'].update(workspace_owned_by_user=False, workspace_acl_manageable=False, workspace_write_read=False)
        report['identity'].update(state.get('identity', {}))
        if request.get('candidate'):
            report['candidate'] = dict(request['candidate'], architecture='ARM64', version_verified=True)
            if state['mode'] == 'candidate_mismatch': report['candidate']['sha256'] = 'd' * 64
        print(json.dumps(report))
    else:
        sys.exit('unknown guest report')
else:
    state['effects'].append(args)
    path.write_text(json.dumps(state))
    sys.exit('unexpected operation')
