"""Disposable Windows runs; exposed through windows_test_runner.py."""
import argparse
import ipaddress
import json
import os
from pathlib import Path, PureWindowsPath
import re
import signal
import shlex
import sys
import time
import uuid
from typing import Any

from windows_template_transport import Failure, Transport, envelope, progress_envelope
from windows_candidate import verify_candidate
from windows_desktop_result import sanitized_desktop, validate_desktop
from windows_run_lock import InvocationLease
from windows_test_runner import sanitized_native, validate_native

UUID = r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}'
RUN = r'tofa-run-[0-9a-f]{32}'
STAGE_SECONDS = {'template_validation': 30, 'candidate_validation': 30, 'clone_creation': 150,
                 'boot': 120, 'guest_session': 120, 'native_smoke': 360, 'desktop_smoke': 240, 'cleanup': 60}


def initial_report(run, suite='native-smoke'):
    return {'schema': 1, 'run': run, 'outcome': 'running', 'stages': [], 'suite': suite,
            'retained': False, 'cleanup': {'outcome': 'not_needed'},
            'capabilities': {'native_sandbox': 'unverified', 'desktop_guardian': 'unverified'}}


def inventory(transport):
    result = {}
    lines = transport.call('list').decode().splitlines()
    if not lines or lines[0].split() != ['UUID', 'Status', 'Name']:
        raise Failure('malformed_vm_inventory')
    for line in lines[1:]:
        fields = line.split(None, 2)
        if (len(fields) != 3 or not re.fullmatch(UUID, fields[0].lower())
                or fields[1] not in ('started', 'stopped', 'paused', 'suspended', 'starting', 'stopping')
                or fields[0].lower() in result):
            raise Failure('malformed_vm_inventory')
        result[fields[0].lower()] = {'uuid': fields[0], 'state': fields[1], 'name': fields[2]}
    return result


def save(path, value):
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    with temporary.open('x', encoding='utf-8') as stream:
        os.chmod(temporary, 0o600)
        json.dump(value, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def owned_vm(transport, owner, allow_missing=False):
    clone = owner['clone']
    if (not re.fullmatch(UUID, clone['uuid'].lower()) or clone['uuid'].lower() == owner['template']['uuid'].lower()
            or clone['name'] != owner['run'] or not re.fullmatch(r'tofa-run-[0-9a-f]{32}', owner['run'])):
        raise Failure('unsafe_cleanup_target')
    current = inventory(transport)
    if owner['template']['uuid'].lower() not in current:
        raise Failure('incomplete_vm_inventory')
    vm = current.get(clone['uuid'].lower())
    if vm is None and allow_missing: return None
    if vm is None or vm['name'] != clone['name']:
        raise Failure('clone_identity_mismatch')
    return vm


def stop_clone(transport, owner):
    vm = owned_vm(transport, owner)
    if vm['state'] == 'stopped': return 'stopped'
    deadline = transport.deadline
    # Reserve half the remaining shutdown budget for verified forced shutdown.
    transport.deadline = time.monotonic() + max(0, deadline - time.monotonic()) / 2
    try:
        transport.call('stop', vm['uuid'], '--request')
        while owned_vm(transport, owner)['state'] != 'stopped':
            time.sleep(.5)
        return 'stopped'
    except Failure:
        pass
    finally:
        transport.deadline = deadline
    vm = owned_vm(transport, owner)
    if vm['state'] == 'stopped': return 'stopped'
    transport.call('stop', vm['uuid'], '--force')
    while owned_vm(transport, owner)['state'] != 'stopped':
        time.sleep(.5)
    return 'forced'


def dispose_clone(transport, owner, allow_missing=False):
    if owned_vm(transport, owner, allow_missing=allow_missing) is None:
        return 'already_absent'
    if stop_clone(transport, owner) == 'forced':
        raise Failure('forced_shutdown_required')
    owned_vm(transport, owner)
    transport.call('delete', owner['clone']['uuid'])
    remaining = inventory(transport)
    if owner['template']['uuid'].lower() not in remaining:
        raise Failure('incomplete_vm_inventory')
    if owner['clone']['uuid'].lower() in remaining:
        raise Failure('clone_delete_incomplete')
    return 'deleted'


def read_record(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_uid != os.getuid() or path.stat().st_mode & 0o022:
        raise Failure('unsafe_state_record')
    value = json.loads(path.read_text())
    if not isinstance(value, dict): raise Failure('invalid_state_record')
    return value


def run_directory(root, run):
    if not re.fullmatch(RUN, run or ''): raise Failure('invalid_owned_run')
    directory = root / run
    if directory.is_symlink() or not directory.is_dir() or directory.stat().st_uid != os.getuid() or directory.stat().st_mode & 0o077:
        raise Failure('unsafe_run_directory')
    return directory


def owned_runs(root):
    runs = []
    for path in sorted(root.glob('tofa-run-*')):
        directory = run_directory(root, path.name)
        if not (directory / 'report.json').exists():
            runs.append({'run': path.name, 'outcome': 'initializing',
                         'retained': (directory / 'ownership.json').exists(), 'cleanup': 'unknown', 'clone': None})
            continue
        report = read_record(directory / 'report.json')
        retained = report.get('retained') is True
        cleanup = report.get('cleanup', {}).get('outcome', 'unknown')
        if (directory / 'lifecycle.json').exists():
            lifecycle = read_record(directory / 'lifecycle.json')
            retained, cleanup = lifecycle['retained'], lifecycle['cleanup']
        runs.append({'run': path.name, 'outcome': report['outcome'], 'retained': retained,
                     'clone': report.get('clone'), 'cleanup': cleanup})
    return runs


def runner_state(root, lease):
    if not lease.held: return 'active'
    if not (root / 'active.json').exists(): return 'idle'
    active = read_record(root / 'active.json')
    if active.get('schema') != 2 or active.get('lease') != lease.identity:
        return 'ambiguous'
    return 'abandoned'


def active_identity(root):
    if not (root / 'active.json').exists(): return None
    active = read_record(root / 'active.json')
    if not re.fullmatch(RUN, active.get('run') or '') or active.get('operation') not in ('run', 'cleanup'):
        return {'operation': 'unknown', 'run': 'unknown'}
    return {key: active[key] for key in ('operation', 'run')}


def cleanup_command(options, run):
    return shlex.join([sys.executable, str(Path(__file__).with_name('windows_test_runner.py')),
                      'cleanup', '--state-dir', str(options.state_dir), '--run', run, '--utmctl', options.utmctl])


def collect_recovery_diagnostics(transport, owner, desktop_run=None):
    result: dict[str, Any] = {'outcome': 'unavailable', 'files': {}}
    deadline = transport.deadline
    transport.deadline = min(deadline, time.monotonic() + min(15, max(0, deadline - time.monotonic()) / 4))
    try:
        vm = owned_vm(transport, owner)
        if vm['state'] != 'started': return result
        files = [(owner['run'], 'output\\progress.json', 'progress', 'progress'),
                 (owner['run'], 'result.json', 'native', 'native')]
        if isinstance(desktop_run, str) and re.fullmatch(RUN, desktop_run) and desktop_run != owner['run']:
            files.extend([(desktop_run, 'output\\progress.json', 'progress', 'desktop_progress'),
                          (desktop_run, 'result.json', 'desktop', 'desktop')])
        for run, name, phase, key in files:
            root = 'C:\\Users\\Public\\' + run
            try:
                raw = transport.call('file', 'pull', vm['uuid'], root + '\\' + name)
                value = (progress_envelope(raw, run) if phase == 'progress'
                         else (sanitized_desktop if phase == 'desktop' else sanitized_native)(envelope(raw, run, phase)))
                result['files'][key] = value
                result['outcome'] = 'collected'
            except (Failure, OSError, ValueError, TypeError):
                result['files'][key] = {'outcome': 'unavailable', 'reason': 'missing_or_invalid'}
    except (Failure, OSError, ValueError, TypeError):
        result['reason'] = 'diagnostic_inventory_unavailable'
    finally:
        transport.deadline = deadline
    return result


def recover_abandoned(options, lease):
    state = runner_state(options.state_dir, lease)
    if state == 'idle': return {'outcome': 'no_recovery_needed'}
    if state != 'abandoned':
        raise Failure('active_or_abandoned_invocation: inspect status; unresolved invocation ownership')
    active = read_record(options.state_dir / 'active.json')
    if not re.fullmatch(RUN, active.get('run') or '') or active.get('operation') not in ('run', 'cleanup'):
        raise Failure('unsafe_recovery_record')
    path = options.state_dir / active['run']
    if not path.exists() and not path.is_symlink() and active['operation'] == 'run':
        path.mkdir(mode=0o700)
    directory = run_directory(options.state_dir, active.get('run'))
    if not (directory / 'report.json').exists():
        if active['operation'] != 'run' or any((directory / name).exists() for name in ('ownership.json', 'clone-intent.json')):
            raise Failure('ambiguous_clone_ownership')
        save(directory / 'report.json', initial_report(active['run']))
    report = read_record(directory / 'report.json')
    if report.get('run') != active['run']: raise Failure('unsafe_recovery_record')
    result = {'run': active['run'], 'outcome': 'recovered', 'retained': False}
    if report['outcome'] == 'running':
        save(directory / ('abandoned-report-' + uuid.uuid4().hex + '.json'), report)
        report.update(outcome='failed', reason='runner_abandoned')
        save(directory / 'report.json', report)
    if (directory / 'ownership.json').exists():
        owner = read_record(directory / 'ownership.json')
        if owner.get('run') != active['run'] or (report.get('clone') is not None and report['clone'] != owner.get('clone')):
            raise Failure('unsafe_recovery_record')
        intent = read_record(directory / 'clone-intent.json')
        if (intent.get('run') != owner['run'] or intent.get('template') != owner.get('template')
                or owner['clone']['uuid'].lower() in intent.get('existing_uuids', [])):
            raise Failure('unsafe_recovery_record')
        report.update(clone=owner['clone'], ownership_unresolved=False)
        transport = Transport(options.utmctl, owner['clone']['uuid'], min(options.timeout, 60), options.lease_descriptor)
        if owned_vm(transport, owner, allow_missing=True) is None:
            result['cleanup'] = 'already_absent'
        else:
            result.update(retained=True, cleanup='retained', shutdown='failed')
            try:
                result['diagnostics'] = collect_recovery_diagnostics(transport, owner, report.get('desktop_run'))
                result['shutdown'] = stop_clone(transport, owner)
            except (Failure, OSError, KeyboardInterrupt):
                result['outcome'] = 'failed'
    elif (directory / 'clone-intent.json').exists() or report.get('ownership_unresolved'):
        raise Failure('ambiguous_clone_ownership')
    if report.get('reason') == 'runner_abandoned':
        report['retained'] = result['retained']
        report['cleanup'] = {'outcome': result.get('cleanup', 'not_needed')}
        if result.get('shutdown'): report['cleanup']['shutdown'] = result['shutdown']
        save(directory / 'report.json', report)
    save(directory / ('recovery-' + uuid.uuid4().hex + '.json'), result)
    save(directory / 'lifecycle.json', {'retained': result['retained'],
                                      'cleanup': result.get('cleanup', 'not_needed')})
    if result['outcome'] != 'recovered': raise Failure('recovery_incomplete: owned clone retained; retry recover')
    (options.state_dir / 'active.json').unlink()
    return result


def cleanup_run(options):
    directory = run_directory(options.state_dir, options.run)
    owner = read_record(directory / 'ownership.json')
    if owner.get('run') != options.run: raise Failure('unsafe_cleanup_target')
    transport = Transport(options.utmctl, owner['clone']['uuid'], min(options.timeout, 60), options.lease_descriptor)
    result = {'run': options.run, 'outcome': 'failed'}
    try:
        disposition = dispose_clone(transport, owner, allow_missing=True)
        result['outcome'] = 'deleted'
        result['already_absent'] = disposition == 'already_absent'
        save(directory / 'lifecycle.json', {'retained': False, 'cleanup': 'deleted'})
    except Failure as error:
        result['reason'] = str(error)
    finally:
        save(directory / ('cleanup-' + uuid.uuid4().hex + '.json'), result)
    print(json.dumps(result))
    return 0 if result['outcome'] == 'deleted' else 1


def validate_preflight(preflight):
    if not preflight['ok']:
        reason = preflight.get('reason')
        allowed = {'unsupported_guest', 'test_user_missing', 'test_user_sign_in_required',
                   'native_client_missing_or_ambiguous', 'python_runtime_missing_or_ambiguous'}
        raise Failure(reason if isinstance(reason, str) and reason in allowed else 'guest_prerequisites_failed')
    os_identity, user = preflight.get('os'), preflight.get('user')
    if (not isinstance(os_identity, dict) or os_identity.get('name') != 'Windows 11'
            or os_identity.get('architecture') != 'ARM64'
            or not re.fullmatch(r'10\.0\.\d+', str(os_identity.get('version', '')))):
        raise Failure('unsupported_guest')
    if (not isinstance(user, dict) or not re.fullmatch(r'S-1-\d+(?:-\d+)+', str(user.get('sid', '')))
            or type(user.get('session')) is not int or user['session'] <= 0):
        raise Failure('wrong_user_session')
    python = preflight.get('python')
    if not isinstance(python, str) or len(python) > 260: raise Failure('malformed_guest_result')
    path = PureWindowsPath(python)
    if not re.fullmatch('[A-Za-z]:', path.drive) or not path.is_absolute() or path.name.lower() != 'python.exe' or '..' in path.parts:
        raise Failure('malformed_guest_result')
    return {key: os_identity[key] for key in ('name', 'architecture', 'version')}


def run_clone(options, directory, report):
    stage = 'template_validation'
    transport = Transport(options.utmctl, (options.template or '').lower(), options.timeout, options.lease_descriptor)
    work_deadline = transport.deadline
    transport.deadline = min(work_deadline, time.monotonic() + STAGE_SECONDS[stage])
    def begin(name):
        nonlocal stage
        stage = name
        transport.deadline = min(work_deadline, time.monotonic() + STAGE_SECONDS[name])
    stage_started = time.monotonic()
    def passed():
        nonlocal stage_started
        report['stages'].append({'stage': stage, 'outcome': 'passed',
                                 'elapsed_seconds': round(time.monotonic() - stage_started, 3)})
        stage_started = time.monotonic()
        save(directory / 'report.json', report)
    owner = None
    try:
        retained = [run for run in owned_runs(options.state_dir) if run['retained']]
        if len(retained) >= 2:
            report['cleanup_action'] = cleanup_command(options, retained[0]['run'])
            print('Retained clone limit reached. Run: ' + report['cleanup_action'], flush=True)
            raise Failure('retained_clone_limit')
        if not options.dedicated_template: raise Failure('dedicated_template_designation_required')
        if options.suite != 'native-smoke' and options.test_auth != 'native-session':
            raise Failure('explicit_test_authentication_required')
        if not re.fullmatch(UUID, transport.template): raise Failure('template_uuid_required')
        if not re.fullmatch(r'(?:[A-Za-z0-9_.-]+\\)?[A-Za-z0-9_.-]+', options.test_user or ''):
            raise Failure('explicit_local_test_user_required')
        before = inventory(transport)
        source = before.get(transport.template)
        if source is None: raise Failure('template_not_found')
        report['template'] = {'uuid': source['uuid'], 'state': source['state']}
        if source['state'] != 'stopped': raise Failure('template_must_be_stopped')
        passed()
        begin('candidate_validation')
        candidate = {'version': options.version, 'sha256': options.sha256, 'commit': options.candidate_commit}
        if (not re.fullmatch(r'v\d+\.\d+\.\d+-[A-Za-z0-9.-]+', options.version or '')
                or not re.fullmatch(r'[0-9a-f]{64}', options.sha256 or '')
                or not re.fullmatch(r'[0-9a-f]{40}', options.candidate_commit or '') or options.candidate is None):
            raise Failure('explicit_candidate_identity_required')
        try:
            payload = verify_candidate(options.candidate, candidate)
        except ValueError as error:
            raise Failure(str(error)) from error
        report['requested_candidate'] = candidate
        passed()
        begin('clone_creation')
        print('Creating a fresh clone from the stopped designated template...', flush=True)
        report['ownership_unresolved'] = True
        save(directory / 'report.json', report)
        save(directory / 'clone-intent.json', {'run': report['run'], 'template': report['template'],
                                               'existing_uuids': sorted(before)})
        identity = transport.call('clone', source['uuid'], '--name', report['run']).decode().strip()
        after = inventory(transport)
        # UTM's clone command prints no result. Its inventory must return exactly
        # one new UUID, additionally bound to our unique requested name.
        if not identity:
            created = [value for key, value in after.items() if key not in before]
            if len(created) != 1: raise Failure('unverified_clone_identity')
            identity = created[0]['uuid']
            report['clone_identity_source'] = 'unique_inventory_delta'
        else:
            report['clone_identity_source'] = 'clone_response'
        if not re.fullmatch(UUID, identity.lower()) or identity.lower() in before:
            raise Failure('unverified_clone_identity')
        cloned = after.get(identity.lower())
        if not cloned or cloned['name'] != report['run'] or cloned['state'] != 'stopped':
            raise Failure('unverified_clone_identity')
        report['clone'] = {'uuid': identity, 'name': report['run']}
        owner = {'schema': 1, 'run': report['run'], 'template': report['template'], 'clone': report['clone']}
        save(directory / 'ownership.json', owner)
        report['ownership_unresolved'] = False
        report['retained'] = True
        passed()
        begin('boot')
        print('Booting the verified clone and waiting for its guest agent...', flush=True)
        owned_vm(transport, owner)
        transport.template = identity
        transport.call('start', identity)
        while owned_vm(transport, owner)['state'] != 'started': time.sleep(.5)
        while True:
            try:
                addresses = transport.call('ip-address', identity).decode().split()
                if addresses:
                    for address in addresses: ipaddress.ip_address(address)
                    break
            except Failure as error:
                if str(error) != 'guest_agent_pending': raise
            time.sleep(.5)
        passed()
        begin('guest_session')
        report['diagnostics'] = {'guest_staging': 'C:\\Users\\Public\\' + report['run'],
                                 'guest_workspace': '%USERPROFILE%\\' + report['run']}
        print('Waiting for the intended Windows user session...', flush=True)
        pending_reason = None
        package_deadline = None
        while True:
            try:
                preflight = transport.preflight({'run': report['run'], 'user': options.test_user, 'operation': 'status'})
            except Failure as error:
                if pending_reason and str(error) in ('transport_timeout', 'guest_completion_timeout'):
                    raise Failure(pending_reason) from error
                raise
            reason = preflight.get('reason')
            if preflight['ok'] or reason not in ('test_user_sign_in_required', 'native_client_missing_or_ambiguous'): break
            pending_reason = reason
            if reason == 'native_client_missing_or_ambiguous' and package_deadline is None:
                package_deadline = min(transport.deadline, time.monotonic() + 30)
                transport.deadline = package_deadline
                print('Waiting up to 30 seconds for native package registration after boot...', flush=True)
            report.setdefault('readiness_waits', []).append({'reason': reason,
                'elapsed_seconds': round(time.monotonic() - stage_started, 3)})
            save(directory / 'report.json', report)
            if time.monotonic() >= transport.deadline: raise Failure(reason)
            time.sleep(min(.5, max(0, transport.deadline - time.monotonic())))
        report['os'] = validate_preflight(preflight)
        passed()
        begin('native_smoke')
        request = {'run': report['run'], 'sid': preflight['user']['sid'], 'session': preflight['user']['session'],
                   'python': preflight['python'], 'workspace_fixture': 'user-owned', 'initialize_sandbox': False,
                   'candidate': candidate}
        print('Staging the candidate and measuring native sandbox boundaries as the limited user...', flush=True)
        task, native = transport.measure(request, candidate=payload)
        report['native'] = sanitized_native(native)
        validate_native(task, native, request)
        expected = dict(candidate, architecture='ARM64', version_verified=True)
        if native.get('candidate') != expected: raise Failure('candidate_identity_mismatch')
        report['candidate'] = expected
        report['completion'] = {key: task[key] for key in ('completed', 'unregistered', 'last_result', 'state')}
        report['capabilities']['native_sandbox'] = 'verified'
        passed()
        if options.suite != 'native-smoke':
            begin('desktop_smoke')
            desktop_run = 'tofa-run-' + uuid.uuid4().hex
            report['desktop_run'] = desktop_run
            save(directory / 'report.json', report)
            desktop_preflight = transport.preflight({'run': desktop_run, 'user': options.test_user, 'operation': 'status'})
            validate_preflight(desktop_preflight)
            desktop_request = dict(request, run=desktop_run, workspace_run=report['run'], test_auth=options.test_auth,
                                   candidate=None)
            desktop_task, desktop = transport.measure(desktop_request, desktop=True)
            report['desktop'] = sanitized_desktop(desktop)
            validate_desktop(desktop_task, report['desktop'], report['native'])
            report['capabilities']['desktop_smoke'] = 'verified'
            passed()
        begin('cleanup')
        print('Native smoke passed; collecting evidence and disposing of the owned clone...', flush=True)
        dispose_clone(transport, owner)
        report['retained'] = False
        report['cleanup'] = {'outcome': 'deleted'}
        passed()
        report['outcome'] = 'passed'
    except (Failure, OSError, ValueError, KeyError, TypeError, KeyboardInterrupt) as error:
        report['outcome'] = 'failed'
        reason = str(error) if isinstance(error, Failure) else ('interrupted' if isinstance(error, KeyboardInterrupt) else 'host_operation_failed')
        report['reason'] = reason
        report['failed_transport_operation'] = transport.operation
        report['stages'].append({'stage': stage, 'outcome': 'failed', 'reason': reason,
                                 'elapsed_seconds': round(time.monotonic() - stage_started, 3)})
        if owner:
            report['cleanup'] = {'outcome': 'retained'}
            save(directory / 'report.json', report)
            recovery = Transport(options.utmctl, owner['clone']['uuid'], min(options.timeout, 60), options.lease_descriptor)
            try:
                report['recovery_diagnostics'] = collect_recovery_diagnostics(recovery, owner, report.get('desktop_run'))
                shutdown = stop_clone(recovery, owner)
                report['cleanup']['shutdown'] = 'forced' if reason == 'forced_shutdown_required' else shutdown
            except (Failure, OSError, KeyboardInterrupt):
                report['cleanup']['shutdown'] = 'failed'
    finally:
        task = transport.last_task
        if task is not None:
            if (all(type(task.get(key)) is bool for key in ('completed', 'unregistered'))
                    and type(task.get('last_result')) is int
                    and task.get('state') in ('Ready', 'Running', 'Disabled', 'Queued', 'Unknown')):
                report['completion'] = {key: task[key] for key in ('completed', 'unregistered', 'last_result', 'state')}
            else:
                report['diagnostics_collection'] = 'malformed_task_diagnostics'
        report['transport_progress_observed'] = transport.progress_observed
        report['transport_steps'] = transport.steps
        if transport.last_progress is not None:
            report['guest_progress'] = transport.last_progress
        save(directory / 'report.json', report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('run', 'status', 'cleanup', 'recover'))
    parser.add_argument('--state-dir', type=Path, required=True)
    parser.add_argument('--utmctl', default='/Applications/UTM.app/Contents/MacOS/utmctl')
    parser.add_argument('--timeout', type=int, default=600)
    parser.add_argument('--template')
    parser.add_argument('--dedicated-template', action='store_true')
    parser.add_argument('--test-user')
    parser.add_argument('--candidate', type=Path)
    parser.add_argument('--version')
    parser.add_argument('--sha256')
    parser.add_argument('--candidate-commit')
    parser.add_argument('--suite', choices=('native-smoke', 'desktop-smoke'), default='native-smoke')
    parser.add_argument('--test-auth', choices=('native-session',))
    parser.add_argument('--run', help='Exact owned run ID for explicit cleanup')
    options = parser.parse_args()
    if not 1 <= options.timeout <= 1800: parser.error('timeout must be 1–1800 seconds')
    def interrupt(*unused): raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupt)
    locked = False
    preserve_lock = False
    lease = None
    try:
        if options.state_dir.is_symlink(): raise Failure('unsafe_state_directory')
        options.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        options.state_dir = options.state_dir.resolve()
        if options.state_dir.stat().st_uid != os.getuid() or options.state_dir.stat().st_mode & 0o077:
            raise Failure('unsafe_state_directory')
        lease = InvocationLease(options.state_dir)
        options.lease_descriptor = lease.descriptor
        state = runner_state(options.state_dir, lease)
        if options.command == 'status':
            runs = owned_runs(options.state_dir)
            for item in runs:
                if item['retained']: item['cleanup_action'] = cleanup_command(options, item['run'])
            print(json.dumps({'locked': state != 'idle', 'runner_state': state,
                              'active': active_identity(options.state_dir),
                              'runs': runs}, indent=2))
            return 0
        if not lease.held:
            raise Failure('active_invocation: ' + json.dumps(active_identity(options.state_dir)))
        recovered = recover_abandoned(options, lease)
        if options.command == 'recover':
            print(json.dumps(recovered))
            return 0
        run = options.run if options.command == 'cleanup' else 'tofa-run-' + uuid.uuid4().hex
        save(options.state_dir / 'active.json', {'schema': 2, 'lease': lease.identity,
                                               'pid': os.getpid(), 'operation': options.command, 'run': run})
        locked = True
        if options.command == 'cleanup': return cleanup_run(options)
        directory = options.state_dir / run
        directory.mkdir(mode=0o700)
        report = initial_report(run, options.suite)
        preserve_lock = True
        save(directory / 'report.json', report)
        run_clone(options, directory, report)
        preserve_lock = report.get('ownership_unresolved') is True
        print(report['outcome'] + ': ' + report.get('reason', 'native smoke completed'))
        print('Report: ' + str(directory / 'report.json'))
        return 0 if report['outcome'] == 'passed' else 1
    except (Failure, OSError, ValueError, KeyError, TypeError, KeyboardInterrupt) as error:
        print(str(error) if isinstance(error, Failure) else 'host_state_operation_failed', file=sys.stderr)
        return 1
    finally:
        if locked and not preserve_lock: (options.state_dir / 'active.json').unlink()
        if lease is not None: lease.close()
