"""No-inference admission for a saved Windows CLI login; never changes its state."""
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import uuid

from windows_template_probe import NativeEngine


@contextmanager
def execution_workspace(parent):
    """Normal inherited ACLs, unlike Python's private Windows temporary trees."""
    parent = Path(parent).resolve()
    if not parent.is_dir():
        raise ValueError('workspace_parent_missing')
    root = parent / ('tofa-cli-' + uuid.uuid4().hex)
    root.mkdir()
    try:
        yield root
    finally:
        shutil.rmtree(root)


def verify_installation(launcher, root):
    root = Path(root)
    paths = [root, root / 'bin', Path(launcher), root / '.tofa-install', root / '.path-owned']
    if any(p.is_symlink() or getattr(p, 'is_junction', lambda: False)() for p in paths):
        raise ValueError('unsafe_installation')
    if Path(launcher).resolve() != (root / 'bin/tofa.exe').resolve():
        raise ValueError('installation_mismatch')
    if (root / '.tofa-install').read_text(encoding='utf-8-sig').strip() != 'tofa-install-v1':
        raise ValueError('installation_mismatch')
    marker = root / '.path-owned'
    if marker.exists() and Path(marker.read_text(encoding='utf-8-sig').strip()).resolve() != (root / 'bin').resolve():
        raise ValueError('path_ownership_mismatch')


def measure(options, root):
    report = {'passed': False, 'paid_inference': False, 'checks': {}}
    checks = report['checks']; engine = None
    try:
        if getattr(options, 'owned_installation', None):
            verify_installation(options.launcher, options.owned_installation)
            checks['installation_ownership'] = True
        codex = options.codex if isinstance(options.codex, list) else [options.codex]
        if len(codex) != 1:
            raise ValueError('native_executable_required')
        env = dict(os.environ, PATH=str(Path(codex[0]).parent) + os.pathsep + str(Path(sys.executable).parent)
                   + os.pathsep + os.environ.get('PATH', ''))
        command = [str(options.launcher), 'launch', 'codex', '--model', options.model, '--allow-unverified']
        if options.guardian_model:
            command += ['--evaluation-guardian-model', options.guardian_model]
        if os.name == 'nt':
            # Own the launcher and every child even if admission times out.
            from qualify_windows import command as supervised_command, Failure
            from windows_process import build_supervisor
            try:
                output, _ = supervised_command(command + ['--', '--version'], build_supervisor(root / 'supervisor'), 45, env=env)
                checks['model_admission'] = re.search(r'codex-cli [0-9]+\.[0-9]+', output) is not None
            except Failure:
                checks['model_admission'] = False
        else:
            # Controlled executable fixtures exercise this same protocol off Windows.
            result = subprocess.run(command + ['--', '--version'], env=env, capture_output=True, timeout=45)
            checks['model_admission'] = (result.returncode == 0 and re.search(rb'codex-cli [0-9]+\.[0-9]+', result.stdout) is not None)
        if not checks['model_admission']:
            raise ValueError('model_admission_failed')
        workspace = root / 'workspace'; workspace.mkdir()
        (workspace / 'input.json').write_text('{"qualification":true}\n')
        outside = root / 'outside.txt'
        engine = NativeEngine(codex[0], workspace, additional_settings=('allow_login_shell=false',),
                              home=getattr(options, 'native_home', None), environment={'PATH': env['PATH']})
        initialized = engine.call('initialize', {'clientInfo': {'name': 'tofa_cli_qualification', 'version': '1'}})
        if not isinstance(initialized.get('result'), dict):
            raise ValueError('native_initialize_failed')
        engine.send({'method': 'initialized'})
        def run(command):
            value = engine.execute(workspace, command)
            if 'error' in value or not isinstance(value.get('result'), dict):
                raise ValueError('native_command_failed')
            result = value['result']
            if (type(result.get('exitCode')) is not int or not isinstance(result.get('stdout'), str)
                    or not isinstance(result.get('stderr'), str)):
                raise ValueError('native_command_failed')
            return result
        value = run('Get-Location | Select-Object -ExpandProperty Path')
        checks['cwd'] = value.get('exitCode') == 0 and os.path.normcase(value.get('stdout', '').strip()) == os.path.normcase(str(workspace))
        if not checks['cwd']:
            raise ValueError('sandbox_cwd_mismatch')
        value = run("Get-Content -Raw -LiteralPath 'input.json'")
        checks['relative_read'] = value.get('exitCode') == 0 and value.get('stdout', '').strip() == '{"qualification":true}'
        value = run("Set-Content -LiteralPath 'write.txt' -Value 'qualification-ok' -NoNewline;Get-Content -Raw -LiteralPath 'write.txt'")
        checks['relative_write'] = (value.get('exitCode') == 0 and value.get('stdout', '').strip() == 'qualification-ok'
                                    and (workspace / 'write.txt').read_text() == 'qualification-ok')
        value = run('python --version')
        checks['python'] = value.get('exitCode') == 0 and value.get('stdout', '').strip() == 'Python ' + platform.python_version()
        value = run("Set-Content -LiteralPath '" + str(outside).replace("'", "''") + "' -Value 'must-not-write'")
        error = re.sub(r'\s+', '', value.get('stderr', ''))
        checks['outside_write_denied'] = (type(value.get('exitCode')) is int and value['exitCode'] != 0
            and 'UnauthorizedAccessException' in error and 'GetContentWriterUnauthorizedAccessError' in error and not outside.exists())
        report['passed'] = all(checks.values())
        if not report['passed']:
            report['failure'] = 'native_prerequisite_failed'
    except ValueError as error:
        # Only our fixed classifications leave the process; external payloads do not.
        known = {'unsafe_installation', 'installation_mismatch', 'path_ownership_mismatch',
                 'native_executable_required', 'model_admission_failed', 'native_initialize_failed',
                 'native_command_failed', 'sandbox_cwd_mismatch'}
        report['failure'] = str(error) if str(error) in known else 'native_prerequisite_failed'
    except (OSError, KeyError, TypeError, subprocess.SubprocessError):
        report['failure'] = 'preflight_operation_failed'
    finally:
        if engine is not None:
            try:
                checks['engine_closed'] = engine.close()
            except (OSError, ValueError, subprocess.SubprocessError):
                checks['engine_closed'] = False
            report['passed'] = report['passed'] and checks['engine_closed']
            if not checks['engine_closed']:
                report['failure'] = 'native_close_failed'
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('launcher', 'codex', 'model'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--guardian-model')
    parser.add_argument('--owned-installation', type=Path)
    parser.add_argument('--native-home', type=Path, help='existing initialized sandbox home; never initializes or edits credentials')
    parser.add_argument('--workspace-parent', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    options = parser.parse_args()
    if not options.workspace_parent.is_dir():
        parser.error('workspace parent must exist')
    # Reserve evidence before any launch; never overwrite an earlier attempt.
    with os.fdopen(os.open(options.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w', encoding='utf-8') as stream:
        report = {'passed': False, 'paid_inference': False, 'checks': {}}
        try:
            with execution_workspace(options.workspace_parent) as root:
                report = measure(options, root)
        except (OSError, ValueError):
            report.update(passed=False, failure='workspace_lifecycle_failed')
        json.dump(report, stream, indent=2); stream.write('\n')
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
