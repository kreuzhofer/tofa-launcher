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

from windows_template_transport import Failure, Transport
from windows_candidate import verify_candidate
from windows_test_runner import sanitized_native, validate_native

UUID = r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}'
RUN = r'tofa-run-[0-9a-f]{32}'


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
    temporary = path.with_suffix('.tmp')
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


def owned_vm(transport, owner):
    clone = owner['clone']
    if (not re.fullmatch(UUID, clone['uuid'].lower()) or clone['uuid'].lower() == owner['template']['uuid'].lower()
            or clone['name'] != owner['run'] or not re.fullmatch(r'tofa-run-[0-9a-f]{32}', owner['run'])):
        raise Failure('unsafe_cleanup_target')
    vm = inventory(transport).get(clone['uuid'].lower())
    if vm is None or vm['name'] != clone['name']:
        raise Failure('clone_identity_mismatch')
    return vm


def stop_clone(transport, owner):
    vm = owned_vm(transport, owner)
    if vm['state'] != 'stopped':
        transport.call('stop', vm['uuid'], '--request')
    while owned_vm(transport, owner)['state'] != 'stopped':
        time.sleep(.5)


def dispose_clone(transport, owner):
    stop_clone(transport, owner)
    owned_vm(transport, owner)
    transport.call('delete', owner['clone']['uuid'])
    remaining = inventory(transport)
    if owner['template']['uuid'].lower() not in remaining:
        raise Failure('incomplete_vm_inventory')
    if owner['clone']['uuid'].lower() in remaining:
        raise Failure('clone_delete_incomplete')


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
        report = read_record(directory / 'report.json')
        retained = report.get('retained') is True
        cleanup = report.get('cleanup', {}).get('outcome', 'unknown')
        if (directory / 'lifecycle.json').exists():
            lifecycle = read_record(directory / 'lifecycle.json')
            retained, cleanup = lifecycle['retained'], lifecycle['cleanup']
        runs.append({'run': path.name, 'outcome': report['outcome'], 'retained': retained,
                     'clone': report.get('clone'), 'cleanup': cleanup})
    return runs


def cleanup_run(options):
    directory = run_directory(options.state_dir, options.run)
    owner = read_record(directory / 'ownership.json')
    if owner.get('run') != options.run: raise Failure('unsafe_cleanup_target')
    transport = Transport(options.utmctl, owner['clone']['uuid'], options.timeout)
    result = {'run': options.run, 'outcome': 'failed'}
    try:
        dispose_clone(transport, owner)
        result['outcome'] = 'deleted'
        save(directory / 'lifecycle.json', {'retained': False, 'cleanup': 'deleted'})
    except Failure as error:
        result['reason'] = str(error)
    finally:
        save(directory / ('cleanup-' + uuid.uuid4().hex + '.json'), result)
    print(json.dumps(result))
    return 0 if result['outcome'] == 'deleted' else 1


def validate_preflight(preflight):
    if not preflight['ok']: raise Failure('guest_prerequisites_failed')
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
    transport = Transport(options.utmctl, (options.template or '').lower(), options.timeout)
    def passed():
        report['stages'].append({'stage': stage, 'outcome': 'passed'})
        save(directory / 'report.json', report)
    owner = None
    try:
        retained = [run for run in owned_runs(options.state_dir) if run['retained']]
        if len(retained) >= 2:
            report['cleanup_action'] = shlex.join([sys.executable, str(Path(__file__).with_name('windows_test_runner.py')),
                'cleanup', '--state-dir', str(options.state_dir), '--run', retained[0]['run'], '--utmctl', options.utmctl])
            print('Retained clone limit reached. Run: ' + report['cleanup_action'], flush=True)
            raise Failure('retained_clone_limit')
        if not options.dedicated_template: raise Failure('dedicated_template_designation_required')
        if not re.fullmatch(UUID, transport.template): raise Failure('template_uuid_required')
        if not re.fullmatch(r'(?:[A-Za-z0-9_.-]+\\)?[A-Za-z0-9_.-]+', options.test_user or ''):
            raise Failure('explicit_local_test_user_required')
        before = inventory(transport)
        source = before.get(transport.template)
        if source is None: raise Failure('template_not_found')
        report['template'] = {'uuid': source['uuid'], 'state': source['state']}
        if source['state'] != 'stopped': raise Failure('template_must_be_stopped')
        passed()
        stage = 'candidate_validation'
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
        stage = 'clone_creation'
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
        stage = 'boot'
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
        stage = 'guest_session'
        report['diagnostics'] = {'guest_staging': 'C:\\Users\\Public\\' + report['run'],
                                 'guest_workspace': '%USERPROFILE%\\' + report['run']}
        print('Waiting for the intended Windows user session...', flush=True)
        while True:
            preflight = transport.preflight({'run': report['run'], 'user': options.test_user, 'operation': 'status'})
            if preflight['ok'] or preflight.get('reason') != 'test_user_sign_in_required': break
            time.sleep(.5)
        report['os'] = validate_preflight(preflight)
        passed()
        stage = 'native_smoke'
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
        stage = 'cleanup'
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
        report['stages'].append({'stage': stage, 'outcome': 'failed', 'reason': reason})
        if owner:
            report['cleanup'] = {'outcome': 'retained'}
            save(directory / 'report.json', report)
            recovery = Transport(options.utmctl, owner['clone']['uuid'], min(options.timeout, 60))
            try:
                stop_clone(recovery, owner)
                report['cleanup']['shutdown'] = 'stopped'
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
        save(directory / 'report.json', report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('run', 'status', 'cleanup'))
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
    parser.add_argument('--suite', choices=('native-smoke',), default='native-smoke')
    parser.add_argument('--run', help='Exact owned run ID for explicit cleanup')
    options = parser.parse_args()
    if not 1 <= options.timeout <= 1800: parser.error('timeout must be 1–1800 seconds')
    def interrupt(*unused): raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupt)
    locked = False
    preserve_lock = False
    try:
        if options.state_dir.is_symlink(): raise Failure('unsafe_state_directory')
        options.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        options.state_dir = options.state_dir.resolve()
        if options.state_dir.stat().st_uid != os.getuid() or options.state_dir.stat().st_mode & 0o077:
            raise Failure('unsafe_state_directory')
        if options.command == 'status':
            print(json.dumps({'locked': (options.state_dir / 'active.json').exists(), 'runs': owned_runs(options.state_dir)}, indent=2))
            return 0
        try:
            descriptor = os.open(options.state_dir / 'active.json', os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            raise Failure('active_or_abandoned_invocation: inspect status; resolve active.json before further mutations') from None
        locked = True
        with os.fdopen(descriptor, 'w') as stream:
            json.dump({'pid': os.getpid(), 'operation': options.command}, stream)
            stream.flush()
            os.fsync(stream.fileno())
        if options.command == 'cleanup': return cleanup_run(options)
        run = 'tofa-run-' + uuid.uuid4().hex
        directory = options.state_dir / run
        directory.mkdir(mode=0o700)
        report = {'schema': 1, 'run': run, 'outcome': 'running', 'stages': [], 'suite': options.suite,
                  'retained': False, 'cleanup': {'outcome': 'not_needed'},
                  'capabilities': {'native_sandbox': 'unverified', 'desktop_guardian': 'unverified'}}
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
