"""Mac-side Windows test infrastructure. Template preparation is the first slice."""
import argparse
import json
import os
from pathlib import Path, PureWindowsPath
import re
import subprocess
import sys
import uuid
from typing import Any
from windows_template_transport import Failure, Transport


BOOTSTRAP = {
    'test_user_missing': 'Create and enable the designated local test account in Windows Settings, then sign in to it. Rerun template prepare to verify its SID and session.',
    'test_user_sign_in_required': 'Sign in to the designated test user and wait for its desktop. Rerun template prepare; exactly one interactive session must be discovered.',
    'native_client_missing_or_ambiguous': 'Install the native ARM64 Codex desktop for the designated test user. Rerun template prepare to verify its package and bundled engine.',
    'python_runtime_missing_or_ambiguous': 'Install one native ARM64 Python 3.11+ runtime with its machine PythonCore registration. Rerun template prepare to verify execution.',
    'native_sandbox_consent_required': 'Rerun template prepare with --initialize-sandbox and approve Windows consent in the designated test account. Setup completion, workspace write/read, and outside-write denial must all pass.',
    'native_setup_incomplete': 'The native setup API did not complete. Complete the installed app\'s native sandbox bootstrap in the designated test account, then quit the app and rerun template status. A timeout alone does not prove that a consent prompt appeared.',
    'native_client_first_launch_required': 'Open Codex once as the designated test user to initialize its native engine and sandbox. Complete required OS/native consent, then fully quit Codex and rerun template prepare. No login or model credentials are required by this probe.',
}


def validate_native(task, native, request):
    if not (task['ok'] is True and task.get('completed') is True and task.get('unregistered') is True
            and type(task.get('last_result')) is int and task['last_result'] == 0 and task.get('state') == 'Ready'):
        if native['ok']:
            raise Failure('contradictory_guest_completion')
    if not native['ok']:
        reason = native.get('reason')
        if not isinstance(reason, str): raise Failure('malformed_guest_result')
        allowed = {'native_workspace_acl_failed', 'native_workspace_execution_failed', 'native_assertion_failed',
                   'native_sandbox_consent_required', 'engine_identity_mismatch', 'native_client_busy',
                   'wrong_user_session', 'limited_user_required', 'unsupported_python_runtime',
                   'sandbox_configuration_failed', 'native_prerequisites_failed', 'native_cleanup_failed',
                   'native_client_first_launch_required', 'unsafe_staging_permissions', 'engine_timeout', 'native_setup_incomplete'}
        raise Failure(reason if reason in allowed else 'native_readiness_failed')
    if request['initialize_sandbox'] and native.get('setup_status') != 'completed':
        raise Failure('native_setup_incomplete')
    identity = native.get('identity', {})
    if identity.get('sid') != request['sid'] or identity.get('session') != request['session']:
        raise Failure('wrong_user_session')
    digest = identity.get('engine_sha256', '')
    if not re.fullmatch('[0-9a-f]{64}', digest) or digest != identity.get('package_engine_sha256'):
        raise Failure('engine_identity_mismatch')
    if str(identity.get('architecture', '')).lower() != 'arm64':
        raise Failure('unsupported_guest')
    client = identity.get('client_version', '')
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:\.\d+)?', client) or tuple(map(int, client.split('.'))) < (26, 917, 71314):
        raise Failure('unsupported_client_version')
    version = identity.get('engine_version', '')
    match = re.fullmatch(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?', version)
    if not match:
        raise Failure('unsupported_engine_version')
    core = tuple(map(int, match.group(1, 2, 3)))
    prerelease = match[4]
    if prerelease is not None and any(not part or (part.isdigit() and len(part) > 1 and part[0] == '0') for part in prerelease.split('.')):
        raise Failure('unsupported_engine_version')
    if '+' in version and any(not part for part in version.split('+', 1)[1].split('.')):
        raise Failure('unsupported_engine_version')
    if core < (0, 155, 0):
        raise Failure('unsupported_engine_version')
    if core == (0, 155, 0) and prerelease is not None:
        # Same SemVer floor as the launcher; compare numeric prerelease components numerically.
        parts = prerelease.split('.')
        key = [(0, int(part)) if part.isdigit() else (1, part) for part in parts]
        if key < [(1, 'alpha'), (0, 16), (0, 4)]:
            raise Failure('unsupported_engine_version')
    checks = native.get('checks', {})
    required = ('limited_user', 'harness_read_only', 'workspace_owned_by_user', 'workspace_acl_manageable', 'ordinary_write',
                'workspace_write_read', 'outside_permission_denied', 'full_access_disabled', 'engine_exited', 'markers_removed')
    if any(checks.get(key) is not True for key in required) or checks.get('outside_marker_exists') is not False:
        raise Failure('native_assertion_failed')
    execution = native.get('execution', {})
    if (type(execution.get('workspace_exit_code')) is not int or execution['workspace_exit_code'] != 0
            or type(execution.get('outside_exit_code')) is not int or execution['outside_exit_code'] == 0
            or execution.get('outside_denial_signal') != 'GetContentWriterUnauthorizedAccessError'):
        raise Failure('native_assertion_failed')


def sanitized_native(native):
    # Only fields generated by the readiness protocol may cross into local diagnostics.
    fields = {'identity': ('client_version', 'engine_version', 'engine_sha256', 'package_engine_sha256',
                           'package', 'architecture', 'python_version', 'sid', 'session'),
              'checks': ('limited_user', 'harness_read_only', 'workspace_owned_by_user', 'workspace_acl_manageable', 'ordinary_write',
                         'workspace_write_read', 'outside_permission_denied', 'outside_marker_exists',
                         'full_access_disabled', 'engine_exited', 'markers_removed'),
              'execution': ('workspace_exit_code', 'outside_exit_code', 'outside_denial_signal')}
    patterns = {'client_version': r'\d+\.\d+\.\d+(?:\.\d+)?',
                'engine_version': r'\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?',
                'engine_sha256': r'[0-9a-f]{64}', 'package_engine_sha256': r'[0-9a-f]{64}',
                'package': r'OpenAI\.Codex_\d+\.\d+\.\d+\.\d+_arm64__[a-z0-9]{13}',
                'architecture': r'(?:ARM64|Arm64)', 'python_version': r'\d+\.\d+\.\d+',
                'sid': r'S-1-\d+(?:-\d+)+', 'outside_denial_signal': r'GetContentWriterUnauthorizedAccessError'}
    sanitized: dict[str, dict[str, Any]] = {}
    for section, keys in fields.items():
        source = native.get(section, {})
        if not isinstance(source, dict): raise Failure('malformed_guest_result')
        sanitized[section] = {}
        for key in keys:
            if key not in source: continue
            value = source[key]
            if section == 'checks':
                valid = type(value) is bool
            elif key in ('session', 'workspace_exit_code', 'outside_exit_code'):
                valid = type(value) is int or (section == 'execution' and value is None)
            else:
                valid = (isinstance(value, str) and len(value) < 256 and re.fullmatch(patterns[key], value) is not None) or (key == 'outside_denial_signal' and value is None)
            if not valid: raise Failure('malformed_guest_result')
            sanitized[section][key] = value
    return sanitized


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    template = commands.add_parser('template').add_subparsers(dest='operation', required=True)
    for operation in ('prepare', 'status'):
        command = template.add_parser(operation)
        command.add_argument('--template', required=True, help='Exact UTM UUID; display names are not accepted')
        command.add_argument('--dedicated-template', action='store_true', help='Explicitly designate this VM for test preparation')
        command.add_argument('--test-user', required=True, help=r'Intended Windows account, e.g. MACHINE\tofa-test')
        command.add_argument('--test-auth', choices=('none',), required=True, help='Model-free native checks need no authentication')
        command.add_argument('--utmctl', default='/Applications/UTM.app/Contents/MacOS/utmctl')
        command.add_argument('--output', type=Path, required=True, help='New local JSON report; existing reports are never overwritten')
        command.add_argument('--timeout', type=int, default=180)
        command.add_argument('--initialize-sandbox', action='store_true', help='One-time prepare only: request native elevated sandbox setup; Windows consent may be required')
        command.add_argument('--workspace-fixture', choices=('user-owned', 'acl-unmanageable'), default='user-owned',
                             help='Negative native regression: a disposable workspace allowing writes but denying ACL management')
    options = parser.parse_args()
    try:
        report_stream = options.output.open('x', encoding='utf-8')
        os.chmod(options.output, 0o600)
    except OSError:
        print('Cannot create a new report; choose an unused, writable --output path.', file=sys.stderr)
        return 1
    report = {'schema': 1, 'run': 'tofa-template-' + uuid.uuid4().hex,
              'operation': options.operation, 'outcome': 'failed',
              'capabilities': {'native_sandbox': 'unverified', 'desktop_trust': 'unverified',
                               'desktop_guardian': 'unverified', 'test_authentication': 'unverified'},
              'authentication_choice': options.test_auth,
              'stages': [], 'changes': []}
    try:
        if not options.dedicated_template:
            raise Failure('dedicated_template_designation_required')
        if options.initialize_sandbox and options.operation != 'prepare':
            raise Failure('sandbox_initialization_requires_prepare')
        if not re.fullmatch(r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}', options.template):
            raise Failure('template_uuid_required')
        if not 1 <= options.timeout <= 600:
            raise Failure('invalid_timeout')
        if not re.fullmatch(r'(?:[A-Za-z0-9_.-]+\\)?[A-Za-z0-9_.-]+', options.test_user):
            raise Failure('explicit_local_test_user_required')
        transport = Transport(options.utmctl, options.template, options.timeout)
        inventory = transport.call('list')
        selected = [line.split(None, 2) for line in inventory.decode().splitlines()[1:]
                    if line.split() and line.split()[0].lower() == options.template.lower()]
        if len(selected) != 1 or len(selected[0]) != 3:
            raise Failure('ambiguous_template')
        if selected[0][1] not in ('started', 'stopped', 'paused', 'suspended', 'starting', 'stopping'):
            raise Failure('malformed_vm_inventory')
        report['template'] = {'uuid': selected[0][0], 'state': selected[0][1]}
        if selected[0][1] != 'started':
            raise Failure('template_must_be_started_for_preparation')
        report['stages'].append({'stage': 'template_identity', 'outcome': 'passed'})
        report['changes'].append('SYSTEM-protected diagnostic staging directory and fresh prerequisite report')
        report['diagnostics'] = {'guest_staging': 'C:\\Users\\Public\\' + report['run']}
        print('Checking designated template prerequisites...', flush=True)
        preflight = transport.preflight({'run': report['run'], 'user': options.test_user, 'operation': options.operation})
        if not preflight['ok']:
            reason = preflight.get('reason')
            if not isinstance(reason, str): raise Failure('malformed_guest_result')
            if reason in BOOTSTRAP:
                report['outcome'] = ('bootstrap_required' if reason == 'test_user_sign_in_required' else 'missing_prerequisites')
                report['bootstrap'] = [BOOTSTRAP[reason]]
                raise Failure(reason)
            raise Failure('guest_prerequisites_failed')
        os_identity = preflight.get('os', {})
        if (not isinstance(os_identity, dict) or os_identity.get('name') != 'Windows 11'
                or os_identity.get('architecture') != 'ARM64'
                or not re.fullmatch(r'10\.0\.\d+', str(os_identity.get('version', '')))):
            raise Failure('unsupported_guest')
        if (not isinstance(preflight.get('user'), dict) or not isinstance(preflight['user'].get('sid'), str)
                or not re.fullmatch(r'S-1-\d+(?:-\d+)+', preflight['user']['sid'])):
            raise Failure('malformed_guest_result')
        if type(preflight['user'].get('session')) is not int or preflight['user']['session'] <= 0:
            raise Failure('wrong_user_session')
        python = preflight.get('python')
        if not isinstance(python, str) or len(python) > 260:
            raise Failure('malformed_guest_result')
        python_path = PureWindowsPath(python)
        if (not re.fullmatch('[A-Za-z]:', python_path.drive) or not python_path.is_absolute()
                or python_path.name.lower() != 'python.exe' or '..' in python_path.parts):
            raise Failure('malformed_guest_result')
        report['os'] = {key: os_identity[key] for key in ('name', 'architecture', 'version')}
        report['stages'].append({'stage': 'prerequisites', 'outcome': 'passed'})
        request = {'run': report['run'], 'sid': preflight['user']['sid'], 'session': preflight['user']['session'],
                   'python': preflight['python'], 'workspace_fixture': options.workspace_fixture,
                   'initialize_sandbox': options.initialize_sandbox}
        report['workspace_fixture'] = options.workspace_fixture
        report['diagnostics']['guest_workspace'] = '%USERPROFILE%\\' + report['run']
        report['changes'].extend(['Limited interactive task',
                                 'Synthetic workspace and outside directory; test markers removed on completion'])
        if options.initialize_sandbox:
            report['changes'].append('Request elevated native sandbox setup through the installed engine; operator supplies Windows consent')
        if preflight.get('register_package'):
            package = preflight['register_package']
            if (options.operation != 'prepare' or not isinstance(package, str)
                    or not re.fullmatch(r'C:\\Program Files\\WindowsApps\\OpenAI\.Codex_\d+\.\d+\.\d+\.\d+_arm64__[a-z0-9]{13}', package)):
                raise Failure('unsafe_package_registration')
            request['register_package'] = package
            report['changes'].append('Register installed Codex package for the designated test user')
        if options.workspace_fixture == 'acl-unmanageable':
            report['changes'].append('One disposable administrator-owned directory with user Modify but no ACL-management access')
        print('Measuring native sandbox write/read and outside-workspace denial...', flush=True)
        task, native = transport.measure(request)
        report['native'] = sanitized_native(native)
        setup_status = native.get('setup_status', 'not_requested')
        if setup_status not in ('not_requested', 'requesting', 'rejected', 'awaiting_completion', 'completed', 'failed'):
            raise Failure('malformed_guest_result')
        report['native']['setup_status'] = setup_status
        if (any(type(task.get(key)) is not bool for key in ('completed', 'unregistered'))
                or type(task.get('last_result')) is not int or task.get('state') not in ('Ready', 'Running', 'Disabled', 'Queued', 'Unknown')):
            raise Failure('malformed_guest_result')
        report['completion'] = {key: task.get(key) for key in ('completed', 'unregistered', 'last_result', 'state')}
        report['transport_progress_observed'] = transport.progress_observed
        validate_native(task, native, request)
        report['stages'].append({'stage': 'native_readiness', 'outcome': 'passed'})
        report['capabilities']['native_sandbox'] = 'verified'
        report['outcome'] = 'native_ready'
    except Failure as error:
        report['reason'] = str(error)
        report['stages'].append({'stage': 'readiness', 'outcome': 'failed', 'reason': str(error)})
        if str(error) in BOOTSTRAP:
            report['bootstrap'] = [BOOTSTRAP[str(error)]]
            if str(error) in ('native_sandbox_consent_required', 'native_client_first_launch_required', 'native_setup_incomplete'): report['outcome'] = 'bootstrap_required'
    except (OSError, ValueError, subprocess.TimeoutExpired):
        report['reason'] = 'host_operation_failed'
    except KeyboardInterrupt:
        report['reason'] = 'interrupted'
    with report_stream as stream:
        json.dump(report, stream, indent=2)
        stream.write('\n')
    print(report['outcome'] + ': ' + report.get('reason', 'native readiness measured'))
    print('Report: ' + str(options.output))
    return 0 if report['outcome'] == 'native_ready' else 1


if __name__ == '__main__':
    sys.exit(main())
