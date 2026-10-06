"""Limited-user native readiness probe; no model turns or credential access."""
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import platform
import queue
import re
import subprocess
import sys
import threading
import time
from typing import Any


def safe_directory(path):
    for parent in (path, *path.parents):
        if parent.exists() and (parent.is_symlink() or getattr(parent.stat(), 'st_file_attributes', 0) & 0x400):
            raise ValueError('unsafe_workspace_path')
    path.mkdir(parents=True, exist_ok=False)


def can_access(path, access):
    api = ctypes.WinDLL('kernel32', use_last_error=True)
    api.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                               ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    api.CreateFileW.restype = wintypes.HANDLE
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = api.CreateFileW(str(path), access, 7, None, 3, 0x02000000, None)
    if handle == wintypes.HANDLE(-1).value:
        if ctypes.get_last_error() != 5:
            raise ValueError('acl_check_failed')
        return False
    api.CloseHandle(handle)
    return True


def workspace_owner(path):
    script = "(Get-Acl -LiteralPath '" + str(path).replace("'", "''") + "').GetOwner([Security.Principal.SecurityIdentifier]).Value"
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
                            capture_output=True, text=True, timeout=10)
    if result.returncode or not re.fullmatch(r'S-1-\d+(?:-\d+)+', result.stdout.strip()):
        raise ValueError('owner_discovery_failed')
    return result.stdout.strip()


class NativeEngine:
    def __init__(self, executable, workspace):
        env = {key: value for key, value in os.environ.items()
               if not key.upper().startswith(('CODEX_', 'OPENAI_', 'TOFA_')) and key.upper() != 'PSMODULEPATH'}
        env['CODEX_HOME'] = str(Path.home() / '.codex')
        args = [str(executable), 'app-server']
        # Settings apply only to this owned process; the native home stays intact.
        for setting in ('windows.sandbox="elevated"', 'sandbox_mode="workspace-write"',
                        'approval_policy="never"', 'mcp_servers={}', 'plugins={}', 'hooks={}',
                        'features.plugins=false', 'features.hooks=false', 'features.memories=false',
                        'history.persistence="none"', 'project_doc_max_bytes=0'):
            args.extend(['-c', setting])
        self.process = subprocess.Popen(args, cwd=workspace, env=env, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding='utf-8',
            creationflags=subprocess.CREATE_NO_WINDOW)
        self.messages: queue.Queue[Any] = queue.Queue(maxsize=128)
        self.sequence = 0
        self.notifications = []
        self.setup_status = 'not_requested'
        threading.Thread(target=self.read, daemon=True).start()

    def read(self):
        assert self.process.stdout is not None
        try:
            while True:
                line = self.process.stdout.readline(1024 * 1024)
                if not line or len(line) >= 1024 * 1024:
                    break
                self.messages.put(json.loads(line), timeout=1)
        except (ValueError, queue.Full):
            pass
        finally:
            try: self.messages.put(None, timeout=1)
            except queue.Full: pass

    def send(self, message):
        assert self.process.stdin is not None
        self.process.stdin.write(json.dumps(message) + '\n')
        self.process.stdin.flush()

    def call(self, method, params):
        self.sequence += 1
        self.send({'id': self.sequence, 'method': method, 'params': params})
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            try:
                message = self.messages.get(timeout=max(.01, deadline - time.monotonic()))
            except queue.Empty as error:
                raise ValueError('engine_timeout') from error
            if not isinstance(message, dict):
                raise ValueError('engine_contract_failed')
            if 'method' in message and 'id' in message:
                raise ValueError('unexpected_approval_callback')
            if message.get('id') == self.sequence:
                return message
            if len(self.notifications) >= 128: raise ValueError('engine_contract_failed')
            self.notifications.append(message)
        raise ValueError('engine_timeout')

    def setup(self):
        self.setup_status = 'requesting'
        response = self.call('windowsSandbox/setupStart', {'mode': 'elevated'})
        if response.get('result', {}).get('started') is not True:
            self.setup_status = 'rejected'
            return False
        self.setup_status = 'awaiting_completion'
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            message = self.notifications.pop(0) if self.notifications else self.messages.get(timeout=max(.01, deadline - time.monotonic()))
            if not isinstance(message, dict): return False
            if message.get('method') == 'windowsSandbox/setupCompleted':
                params = message.get('params', {})
                success = params.get('mode') == 'elevated' and params.get('success') is True and params.get('error') is None
                self.setup_status = 'completed' if success else 'failed'
                return success
            if 'method' in message and 'id' in message: return False
        return False

    def execute(self, workspace, command):
        return self.call('command/exec', {
            'command': [r'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe',
                        '-NoProfile', '-NonInteractive', '-Command', "$ErrorActionPreference='Stop';" + command],
            'cwd': str(workspace), 'timeoutMs': 10000,
            'sandboxPolicy': {'type': 'workspaceWrite', 'writableRoots': [str(workspace)],
                              'networkAccess': False, 'excludeTmpdirEnvVar': True, 'excludeSlashTmp': True}})

    def close(self):
        assert self.process.stdin is not None and self.process.stdout is not None
        self.process.stdin.close()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)
            return False
        finally:
            self.process.stdout.close()
        return self.process.returncode == 0


def main():
    root = Path(__file__).resolve().parent
    request = json.loads((root / 'request.json').read_text(encoding='utf-8-sig'))
    report = {'run': request['run'], 'phase': 'native', 'ok': False,
              'reason': 'native_probe_failed', 'checks': {}, 'execution': {}}
    engine = None
    markers = []
    started = time.monotonic()
    progress = json.loads((root / 'output/progress.json').read_text(encoding='utf-8-sig'))
    offset = progress['checkpoints'][-1]['elapsed_ms']
    def checkpoint(stage):
        progress['checkpoints'].append({'stage': stage, 'elapsed_ms': offset + int((time.monotonic() - started) * 1000)})
        temporary = root / 'output/progress.tmp'
        temporary.write_text(json.dumps(progress), encoding='utf-8')
        os.replace(temporary, root / 'output/progress.json')
    try:
        identity = json.loads((root / 'output/identity.json').read_text(encoding='utf-8-sig'))
        executable = Path(identity.pop('engine'))
        identity['engine_sha256'] = hashlib.sha256(executable.read_bytes()).hexdigest()
        identity['python_version'] = platform.python_version()
        version = subprocess.run([str(executable), '--version'], capture_output=True, text=True, timeout=10)
        if version.returncode or not version.stdout.startswith('codex-cli '):
            raise ValueError('engine_version_invalid')
        identity['engine_version'] = version.stdout.strip().removeprefix('codex-cli ')
        report['identity'] = identity
        if identity['engine_sha256'] != identity['package_engine_sha256']:
            raise ValueError('engine_identity_mismatch')
        if platform.machine().upper() != 'ARM64' or sys.version_info < (3, 11):
            raise ValueError('unsupported_python_runtime')
        report['checks']['limited_user'] = not bool(ctypes.windll.shell32.IsUserAnAdmin())
        if not report['checks']['limited_user']:
            raise ValueError('limited_user_required')
        report['checks']['harness_read_only'] = not any(can_access(path, access)
            for path in (root / 'request.json', root / 'probe.py', root / 'user.ps1') for access in (0x2, 0x40000))
        if not report['checks']['harness_read_only']: raise ValueError('unsafe_staging_permissions')
        if request.get('candidate'):
            checkpoint('candidate_verification')
            from windows_candidate import verify_candidate
            candidate = root / 'candidate.exe'
            if any(can_access(path, access) for path in (candidate, root / 'windows_candidate.py')
                   for access in (0x2, 0x40000)):
                raise ValueError('unsafe_staging_permissions')
            verify_candidate(candidate, request['candidate'])
            measured = subprocess.run([str(candidate), '--version'], capture_output=True, text=True, timeout=10)
            if measured.returncode or measured.stderr or measured.stdout.strip() != 'tofa ' + request['candidate']['version']:
                raise ValueError('candidate_version_mismatch')
            report['candidate'] = dict(request['candidate'], architecture='ARM64', version_verified=True)
        checkpoint('workspace_preparation')
        fixture = request['workspace_fixture'] == 'acl-unmanageable'
        base = Path.home() / request['run']
        safe_directory(base)
        workspace = root / 'acl-fixture' if fixture else base / 'workspace'
        if not fixture: safe_directory(workspace)
        outside = base / 'outside'
        safe_directory(outside)
        report['checks']['workspace_owned_by_user'] = workspace_owner(workspace) == identity['sid']
        report['checks']['workspace_acl_manageable'] = can_access(workspace, 0x40000)  # WRITE_DAC
        ordinary = workspace / 'ordinary.txt'
        markers.append(ordinary)
        ordinary.write_text('ordinary-write-ok')
        report['checks']['ordinary_write'] = ordinary.read_text() == 'ordinary-write-ok'
        ordinary.unlink()
        marker = workspace / 'sandbox.txt'
        outside_marker = outside / 'must-not-exist.txt'
        markers.extend([marker, outside_marker])
        checkpoint('engine_initialization')
        engine = NativeEngine(executable, workspace)
        initialized = engine.call('initialize', {'clientInfo': {'name': 'tofa_template_readiness', 'version': '1'},
                                                  'capabilities': {'experimentalApi': True}})
        if 'result' not in initialized: raise ValueError('engine_contract_failed')
        engine.send({'method': 'initialized'})
        if request['initialize_sandbox']:
            try:
                ready = engine.setup()
            except (queue.Empty, ValueError):
                ready = False
            if not ready: raise ValueError('native_setup_incomplete')
        checkpoint('sandbox_configuration')
        config = engine.call('config/read', {'includeLayers': False}).get('result', {}).get('config', {})
        report['checks']['full_access_disabled'] = (config.get('sandbox_mode') == 'workspace-write'
                                                    and (config.get('windows') or {}).get('sandbox') == 'elevated')
        if not report['checks']['full_access_disabled']: raise ValueError('sandbox_configuration_failed')
        quoted = str(marker).replace("'", "''")
        checkpoint('workspace_execution')
        executed = engine.execute(workspace, "Set-Content -LiteralPath '" + quoted
                                  + "' -Value 'tofa-sandbox-ok' -NoNewline;Get-Content -Raw -LiteralPath '" + quoted + "'")
        result = executed.get('result', {})
        report['execution']['workspace_exit_code'] = result.get('exitCode')
        report['checks']['workspace_write_read'] = (result.get('exitCode') == 0
            and result.get('stdout', '').strip() == 'tofa-sandbox-ok'
            and marker.is_file() and marker.read_text() == 'tofa-sandbox-ok')
        if not report['checks']['workspace_write_read']:
            # Only classify known setup text. No raw engine output enters reports.
            error = json.dumps(executed)
            if 'refresh' in error.lower() and 'acl' in error.lower():
                raise ValueError('native_workspace_acl_failed')
            if re.search(r'sandbox.*(not initialized|setup required|not set up)', error, re.I):
                raise ValueError('native_sandbox_consent_required')
            raise ValueError('native_workspace_execution_failed')
        checkpoint('outside_execution')
        denied = engine.execute(workspace, "Set-Content -LiteralPath '" + str(outside_marker).replace("'", "''")
                                + "' -Value 'unexpected-write' -NoNewline").get('result', {})
        report['execution']['outside_exit_code'] = denied.get('exitCode')
        signal = 'GetContentWriterUnauthorizedAccessError'
        report['execution']['outside_denial_signal'] = signal if signal in denied.get('stderr', '') else None
        report['checks']['outside_marker_exists'] = outside_marker.exists()
        report['checks']['outside_permission_denied'] = (type(denied.get('exitCode')) is int
            and denied['exitCode'] != 0 and signal in denied.get('stderr', '') and not outside_marker.exists())
        report['ok'] = all(value is True for key, value in report['checks'].items() if key != 'outside_marker_exists')
        report['reason'] = 'native_ready' if report['ok'] else 'native_assertion_failed'
    except ValueError as error:
        allowed = {'unsafe_workspace_path', 'acl_check_failed', 'owner_discovery_failed', 'engine_contract_failed',
                   'unexpected_approval_callback', 'engine_timeout', 'engine_version_invalid', 'engine_identity_mismatch',
                   'unsupported_python_runtime', 'limited_user_required', 'sandbox_configuration_failed',
                   'native_workspace_acl_failed', 'native_sandbox_consent_required', 'native_workspace_execution_failed',
                   'unsafe_staging_permissions', 'native_setup_incomplete', 'invalid_candidate',
                   'candidate_checksum_mismatch', 'candidate_not_arm64', 'candidate_version_mismatch'}
        report['reason'] = str(error) if str(error) in allowed else 'native_probe_failed'
    except Exception:
        report['reason'] = 'native_probe_failed'
    finally:
        report['setup_status'] = engine.setup_status if engine else 'not_requested'
        report['checks']['engine_exited'] = engine.close() if engine else True
        removed = True
        for marker in markers:
            try:
                if marker.exists(): marker.unlink()
            except OSError: removed = False
        report['checks']['markers_removed'] = removed
        report['ok'] = report['ok'] and removed and report['checks']['engine_exited']
        if not report['ok'] and report['reason'] == 'native_ready': report['reason'] = 'native_cleanup_failed'
        (root / 'output/result.json').write_text(json.dumps(report), encoding='utf-8')
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
