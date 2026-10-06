"""External UTM lifecycle fixture; guest protocol uses the template fixture."""
import json
import os
from pathlib import Path
import runpy
import signal
import sys
import uuid

path = Path(os.environ['TEMPLATE_FIXTURE_STATE'])
state = json.loads(path.read_text())
args = sys.argv[1:]
if args == ['list']:
    if state['mode'] == 'diagnostic_inventory_failure':
        state['recovery_lists'] = state.get('recovery_lists', 0) + 1
        path.write_text(json.dumps(state))
        if state['recovery_lists'] == 2: sys.exit('PRIVATE_KEY inventory failed')
    if state.get('delete_attempted') and state['mode'] == 'empty_inventory_after_delete': sys.exit(0)
    print('UUID                                 Status   Name')
    if state.get('delete_attempted') and state['mode'] == 'header_only_after_delete': sys.exit(0)
    for vm in state['vms']:
        print(vm['uuid'], vm['status'], vm['name'])
elif args[0] == 'ip-address':
    if state['mode'] == 'boot_hang': sys.exit(0)
    if state['mode'] == 'boot_session_delay' and not state.get('boot_waited'):
        state['boot_waited'] = True
        path.write_text(json.dumps(state))
    else:
        print('192.0.2.10')
elif args[0] == 'clone':
    if args[1] != state['vms'][0]['uuid'] or state['vms'][0]['status'] != 'stopped':
        sys.exit('unsafe clone source')
    identity = str(uuid.uuid4())
    if state['mode'] == 'uppercase_uuid': identity = identity.upper()
    state['vms'].append({'uuid': identity, 'status': 'stopped', 'name': args[3]})
    state['guest_uuid'] = identity
    state['effects'].append({'vm': identity, 'effect': 'cloned'})
    path.write_text(json.dumps(state))
    if state['mode'] != 'empty_clone_stdout':
        print(state['vms'][1]['uuid'] if state['mode'] == 'wrong_clone_uuid' else identity)
elif args[0] in ('start', 'stop', 'delete'):
    if args[1] in [vm['uuid'] for vm in state['vms'][:2]]:
        sys.exit('unsafe lifecycle target')
    vm = next(vm for vm in state['vms'] if vm['uuid'] == args[1])
    directory = Path(state['runs']) / vm['name']
    owner = json.loads((directory / 'ownership.json').read_text())
    if owner['clone']['uuid'] != args[1] or owner['template']['uuid'] != state['vms'][0]['uuid']:
        sys.exit('missing ownership')
    if args[0] == 'start':
        state['ownership_before_boot'] = True
        vm['status'] = 'started'
    elif args[0] == 'stop':
        if args[2:] not in (['--request'], ['--force']): sys.exit('unexpected shutdown mode')
        if args[2:] == ['--request'] and state['mode'] in ('shutdown_refused', 'shutdown_hang', 'force_refused'):
            state['effects'].append({'vm': args[1], 'effect': 'request_refused'})
            path.write_text(json.dumps(state))
            if state['mode'] == 'shutdown_hang':
                import time
                time.sleep(30)
            sys.exit('PRIVATE_KEY shutdown refused')
        if args[2:] == ['--force']:
            if state['mode'] == 'force_refused': sys.exit('PRIVATE_KEY force refused')
            state['effects'].append({'vm': args[1], 'effect': 'forced'})
        vm['status'] = 'stopped'
    else:
        if state['mode'] == 'delete_failure': sys.exit('PRIVATE_KEY deletion failed')
        state['report_before_delete'] = (directory / 'report.json').is_file()
        if vm['status'] != 'stopped' or not state['report_before_delete']: sys.exit('unsafe deletion')
        state['delete_attempted'] = True
        if state['mode'] not in ('empty_inventory_after_delete', 'header_only_after_delete'):
            state['vms'].remove(vm)
    state['effects'].append({'vm': args[1], 'effect': args[0]})
    path.write_text(json.dumps(state))
    if (args[0] == 'start' and state['mode'] in ('crash_after_boot', 'crash_with_inflight_transport')
            or args[0] == 'delete' and state['mode'] == 'crash_after_delete'):
        os.kill(os.getppid(), signal.SIGKILL)
        if state['mode'] == 'crash_with_inflight_transport':
            import time
            time.sleep(2)
else:
    if state['mode'] == 'crash_during_trial' and args[:2] == ['file', 'pull'] and args[-1].endswith('task.json'):
        os.kill(os.getppid(), signal.SIGKILL)
    runpy.run_path(str(Path(__file__).with_name('windows_template_utm.py')), run_name='__main__')
