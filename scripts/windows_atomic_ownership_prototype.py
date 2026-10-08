"""THROWAWAY #102 native ownership experiment; never production admission.

Run through windows_test_runner.py run --suite desktop-atomic-ownership.
The standalone --inspect-asar command fingerprints source without exporting it.
"""
import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import threading
import time


def fingerprint(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def inspect_asar(path):
    """Read the bounded ASAR header and relevant JS; never extract vendor files."""
    sources = []
    with path.open('rb') as stream:
        first = stream.read(16)
        if len(first) != 16: raise ValueError('invalid_archive')
        size, header_size, payload_size, json_size = struct.unpack('<IIII', first)
        if size != 4 or not 4 <= json_size <= payload_size <= header_size <= 16 * 1024 * 1024:
            raise ValueError('invalid_archive')
        header = json.loads(stream.read(json_size))
        def visit(entries, prefix=''):
            for name, entry in entries.items():
                relative = prefix + name
                if 'files' in entry:
                    yield from visit(entry['files'], relative + '/')
                elif relative.endswith('.js') and 'offset' in entry and not entry.get('unpacked'):
                    yield relative, entry
        for name, entry in visit(header['files']):
            length, offset = entry['size'], int(entry['offset'])
            if not 0 <= length <= 20 * 1024 * 1024 or offset < 0: raise ValueError('invalid_archive')
            stream.seek(8 + header_size + offset)
            data = stream.read(length)
            if len(data) != length: raise ValueError('invalid_archive')
            signals = {key: data.count(token) for key, token in (
                ('singleton_calls', b'requestSingleInstanceLock'), ('fixed_pipe_names', b'codex-ipc'),
                ('collision_handlers', b'EADDRINUSE'), ('reconnect_handlers', b'scheduleReconnect'))}
            if signals['singleton_calls'] or signals['fixed_pipe_names']:
                sources.append(dict(name=name, sha256=hashlib.sha256(data).hexdigest(), **signals))
                if len(sources) > 32: raise ValueError('invalid_archive')
    return {'asar_sha256': fingerprint(path), 'sources': sources}


class SyntheticPipe:
    """An owned first-instance pipe. No impersonation, ACL edits, or message reads."""
    def __init__(self):
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.kernel = kernel
        kernel.CreateNamedPipeW.argtypes = [wintypes.LPCWSTR, *([wintypes.DWORD] * 6), wintypes.LPVOID]
        kernel.CreateNamedPipeW.restype = wintypes.HANDLE
        kernel.ConnectNamedPipe.argtypes = [wintypes.HANDLE, wintypes.LPVOID]
        kernel.ConnectNamedPipe.restype = wintypes.BOOL
        kernel.GetNamedPipeClientProcessId.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.ULONG)]
        kernel.GetNamedPipeClientProcessId.restype = wintypes.BOOL
        kernel.PeekNamedPipe.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD)]
        kernel.PeekNamedPipe.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        self.client = None
        # DUPLEX | FIRST_PIPE_INSTANCE; byte mode | NOWAIT | REJECT_REMOTE_CLIENTS.
        self.handle = kernel.CreateNamedPipeW(r'\\.\pipe\codex-ipc', 3 | 0x80000,
                                              1 | 8, 1, 65536, 65536, 0, None)
        if self.handle == ctypes.c_void_p(-1).value:
            self.handle = None
            raise ValueError('pipe_unavailable')

    def observe(self, timeout=12):
        result = {'connected': False, 'client_pid': 0, 'bytes_available': 0, 'admitted': False}
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            connected = self.kernel.ConnectNamedPipe(self.handle, None)
            error = 0 if connected else ctypes.get_last_error()
            if connected or error == 535:  # ERROR_PIPE_CONNECTED
                result['connected'] = True
                pid, available = wintypes.ULONG(), wintypes.DWORD()
                if not self.kernel.GetNamedPipeClientProcessId(self.handle, ctypes.byref(pid)):
                    result['failure'] = 'client_identity_unavailable'
                    break
                result['client_pid'] = pid.value
                # Retain the process object while caller attributes the connection.
                if self.client is None:
                    self.client = self.kernel.OpenProcess(0x101000, False, pid.value)
                    if not self.client:
                        result['failure'] = 'client_identity_unavailable'
                        break
                if self.kernel.PeekNamedPipe(self.handle, None, 0, None, ctypes.byref(available), None):
                    result['bytes_available'] = available.value
                    if available.value: break
            elif error not in (536, 232):  # LISTENING / NO_DATA
                result['pipe_error'] = error
                break
            # Polling observes completion only; the pipe is already bound before
            # the explicitly ordered native start. No sleep specifies a race.
            time.sleep(.05)
        return result

    def close(self):
        for handle in (self.handle, self.client):
            if handle: self.kernel.CloseHandle(handle)
        self.handle = self.client = None


def experiment(root, request, identity, workspace, report):
    from windows_desktop_runtime import observations, powershell, ui
    from windows_ownership_contract import refusal
    from windows_ownership_experiment import inspect, wait_app
    from windows_process import build_supervisor, stop, supervised
    from windows_template_probe import safe_directory

    evidence = {'production_gate': 'blocked', 'stage': 'preparation', 'identity': {},
        'sources': [], 'trials': [], 'checks': {},
        'blockers': ['atomic_acquisition_unproven', 'cross_user_session_unavailable',
                     'runtime_source_mapping_unavailable', 'native_observation_incomplete']}
    report['atomic_ownership'] = evidence
    def save():
        (root / 'output/atomic-ownership.json').write_text(json.dumps(evidence, indent=2), encoding='utf-8')
    save()
    owned = workspace.parent / 'atomic-ownership-prototype'
    safe_directory(owned)
    supervisor = build_supervisor(owned)
    bridge = owned / 'codex.exe'
    shutil.copyfile(supervisor, bridge)
    before = inspect(root)
    if refusal(before) != (42, 'ownership_unproven'): raise ValueError('ownership_discovery_failed')
    executable = before['packages'][0]['app']
    if before['packages'][0]['name'] != identity['package']: raise ValueError('engine_identity_mismatch')
    ordinary_config = Path.home() / '.codex/config.toml'
    original = fingerprint(ordinary_config) if ordinary_config.exists() else None
    evidence['stage'] = 'source'
    archive = inspect_asar(Path(executable).parent / 'resources/app.asar')
    evidence['sources'] = archive['sources']
    evidence['identity'] = {'package': identity['package'], 'app_sha256': fingerprint(Path(executable)),
        'engine_sha256': fingerprint(Path(identity['engine'])), 'asar_sha256': archive['asar_sha256'],
        'sid': request['sid'], 'session': identity['session']}
    if evidence['identity']['engine_sha256'] != identity['package_engine_sha256']:
        raise ValueError('engine_identity_mismatch')
    save()
    children = []
    windows = {}

    def start(label, launcher, barrier=None):
        directory = owned / label
        safe_directory(directory)
        home = directory / 'home'
        safe_directory(home)
        # Dedicated empty engine homes never copy or load ordinary credentials.
        (home / 'config.toml').write_text('sandbox_mode="workspace-write"\napproval_policy="on-request"\n', encoding='utf-8')
        config = directory / 'bridge.json'
        config.write_text(json.dumps({'engine': identity['engine'], 'sha256': evidence['identity']['engine_sha256'],
            'workspace': str(workspace), 'evidence_dir': str(directory), 'sid': request['sid'],
            'visualization_root': str(home / 'visualizations'),
            'prompt': 'NO TURNS AUTHORIZED: ' + label, 'record_ownership': True}), encoding='utf-8')
        env = dict(os.environ, CODEX_HOME=str(home))
        if launcher:
            env.update(CODEX_CLI_PATH=str(bridge), TOFA_LIVE_PYTHON=request['python'],
                TOFA_LIVE_HARNESS=str(root / 'windows_desktop_bridge.py'), TOFA_DESKTOP_PROBE_CONFIG=str(config))
        else:
            for key in ('CODEX_CLI_PATH', 'TOFA_LIVE_PYTHON', 'TOFA_LIVE_HARNESS', 'TOFA_DESKTOP_PROBE_CONFIG'):
                env.pop(key, None)
        if barrier is not None: barrier.wait()
        child = subprocess.Popen(supervised([executable, '--force-renderer-accessibility'], supervisor),
            cwd=workspace, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        children.append(child)
        return child, directory

    def observe_window(child):
        try:
            app = wait_app(child, executable)
            windows[child.pid] = app
            return app
        except ValueError:
            if child.poll() == 0: return None
            raise

    def cleanup(processes, trial):
        trial['normal_quit'] = True
        for child in reversed(processes):
            app = windows.get(child.pid)
            try:
                if child.poll() is None:
                    if not app or not ui(root, app, 'quit', report):
                        trial['normal_quit'] = False
                    else:
                        child.wait(timeout=10)
            except (ValueError, OSError, subprocess.SubprocessError):
                trial['normal_quit'] = False
            finally:
                stop(child)
        trial['cleanup_complete'] = all(child.poll() is not None for child in processes)
        save()

    def pipe_trial(case):
        trial = {'case': case, 'admitted': False}
        evidence['trials'].append(trial)
        helper = SyntheticPipe()  # Acquisition barrier: bind completes before native spawn.
        child = None
        try:
            child, directory = start(case, True)
            trial.update(helper.observe())
            app = observe_window(child)
            if app: trial['launcher_pid'] = app['pid']
            if trial.get('client_pid'):
                pid = trial['client_pid']
                peer = powershell("$p=Get-CimInstance Win32_Process -Filter 'ProcessId=" + str(pid) + "';"
                    "$u=Invoke-CimMethod -InputObject $p -MethodName GetOwnerSid;"
                    "@{sid=$u.Sid;session=[int]$p.SessionId;created=[long]$p.CreationDate.ToUniversalTime().Ticks;"
                    "path=$p.ExecutablePath}|ConvertTo-Json")
                trial.update(client_matches_app=bool(app) and pid == app['pid'] and peer['path'].lower() == executable.lower(),
                    client_matches_user=peer['sid'] == request['sid'], client_matches_session=peer['session'] == identity['session'],
                    client_session=peer['session'], client_created_ticks=peer['created'])
            if trial['connected'] and 'unverified_native_pipe_connection' not in evidence['blockers']:
                evidence['blockers'].insert(0, 'unverified_native_pipe_connection')
            save()
            if trial['connected']:
                # Close only this synthetic server, then establish a new first
                # instance while the same owned app remains alive.
                helper.close()
                helper = SyntheticPipe()
                replacement = {'case': 'pipe_replaced', **helper.observe()}
                replacement['launcher_pid'] = app['pid'] if app else 0
                replacement['client_matches_app'] = bool(app) and replacement['client_pid'] == app['pid']
                if replacement['client_pid']:
                    peer = powershell("$p=Get-CimInstance Win32_Process -Filter 'ProcessId=" + str(replacement['client_pid']) + "';"
                        "$u=Invoke-CimMethod -InputObject $p -MethodName GetOwnerSid;"
                        "@{sid=$u.Sid;session=[int]$p.SessionId;created=[long]$p.CreationDate.ToUniversalTime().Ticks}|ConvertTo-Json")
                    replacement.update(client_matches_user=peer['sid'] == request['sid'],
                        client_matches_session=peer['session'] == identity['session'],
                        client_session=peer['session'], client_created_ticks=peer['created'],
                        client_same_process=peer['created'] == trial.get('client_created_ticks'))
                evidence['trials'].append(replacement)
                save()
            events = observations(directory, final=False)
            trial['main_initializations'] = sum(e.get('event') == 'initialized' and e.get('main_connection') is True for e in events)
            trial['admitted_turns'] = sum(e.get('event') == 'turn_admitted' for e in events)
        finally:
            helper.close()
            if child: cleanup([child], trial)

    try:
        evidence['stage'] = 'pipe'
        save()
        pipe_trial('pipe_precreated')
        evidence['stage'] = 'races'
        save()
        for case in ('ordinary_first', 'launcher_first', 'simultaneous', 'two_launchers'):
            trial = {'case': case, 'admitted': False}
            evidence['trials'].append(trial)
            first = second = None
            try:
                # Both workers reach the same barrier after absence discovery.
                # Ordered cases instead release the second only after the first
                # has an observed native window. Neither is a production lease.
                if inspect(root)['incumbents']: raise ValueError('native_client_busy')
                if case in ('simultaneous', 'two_launchers'):
                    barrier = threading.Barrier(3, timeout=10)
                    results, failures = {}, []
                    def contender(index):
                        try:
                            results[index] = start(case + '-' + str(index), index == 1 or case == 'two_launchers', barrier)
                        except Exception as error:
                            failures.append(error)
                    workers = [threading.Thread(target=contender, args=(i,)) for i in range(2)]
                    for worker in workers: worker.start()
                    barrier.wait()
                    for worker in workers: worker.join(timeout=15)
                    if failures or len(results) != 2: raise ValueError('ownership_startup_failed')
                    first, first_dir = results[0]
                    second, second_dir = results[1]
                    first_app, second_app = observe_window(first), observe_window(second)
                else:
                    first, first_dir = start(case + '-first', case == 'launcher_first')
                    first_app = observe_window(first)
                    if not first_app: raise ValueError('ownership_startup_failed')
                    second, second_dir = start(case + '-second', case == 'ordinary_first')
                    second_app = observe_window(second)
                if case == 'two_launchers':
                    trial.update(launcher_pid=first_app['pid'] if first_app else 0,
                        competing_launcher_pid=second_app['pid'] if second_app else 0,
                        winner='both' if first_app and second_app else ('launcher' if first_app else ('competing_launcher' if second_app else 'neither')))
                else:
                    ordinary, launcher = (second_app, first_app) if case == 'launcher_first' else (first_app, second_app)
                    trial.update(ordinary_pid=ordinary['pid'] if ordinary else 0, launcher_pid=launcher['pid'] if launcher else 0,
                        winner='both' if ordinary and launcher else ('ordinary' if ordinary else ('launcher' if launcher else 'neither')))
                current = inspect(root)
                for name, process in (('first_exit', first), ('second_exit', second)):
                    if process.poll() is not None: trial[name] = process.returncode & 0xffffffff
                trial['pipe_server_pid'] = current['pipe']['server_pid']
                trial['incumbent_preserved'] = bool(first_app) and any(p['pid'] == first_app['pid'] for p in current['incumbents'])
                events = observations(first_dir) + observations(second_dir)
                trial['main_initializations'] = sum(e.get('event') == 'initialized' and e.get('main_connection') is True for e in events)
                trial['admitted_turns'] = sum(e.get('event') == 'turn_admitted' for e in events)
                save()
            finally:
                cleanup([p for p in (first, second) if p is not None], trial)
        recovery = {'case': 'ordinary_recovery', 'admitted': False}
        evidence['trials'].append(recovery)
        child, _ = start('ordinary-recovery', False)
        app = observe_window(child)
        recovery['ordinary_pid'] = app['pid'] if app else 0
        cleanup([child], recovery)
        if not app: raise ValueError('ownership_startup_failed')
        evidence['blockers'].remove('native_observation_incomplete')
    except Exception as error:
        evidence['failed_stage'] = evidence['stage']
        evidence['failure_kind'] = type(error).__name__ if type(error).__name__ in (
            'ValueError', 'TimeoutExpired', 'OSError', 'BrokenBarrierError') else 'UnexpectedError'
        if str(error) in ('ownership_startup_failed', 'native_client_busy', 'pipe_unavailable', 'desktop_readiness_failed'):
            evidence['failure_reason'] = str(error)
        save()
        raise
    finally:
        evidence['stage'] = 'cleanup'
        save()
        for child in children: stop(child)
        after = inspect(root)
        evidence['checks'].update(owned_apps_exited=not after['incumbents'],
            cli_defaults_unchanged=(fingerprint(ordinary_config) if ordinary_config.exists() else None) == original,
            vendor_service_preserved=after['service'] == before['service'])
        save()
    if not all(evidence['checks'].values()): raise ValueError('ownership_observation_failed')
    evidence['stage'] = 'complete'
    save()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inspect-asar', type=Path)
    args = parser.parse_args()
    if args.inspect_asar:
        print(json.dumps(inspect_asar(args.inspect_asar)))
        return 0
    root = Path(__file__).resolve().parent
    request = json.loads((root / 'request.json').read_text(encoding='utf-8-sig'))
    report = {'run': request['run'], 'phase': 'desktop', 'ok': False, 'reason': 'atomic_ownership_blocked'}
    try:
        identity = json.loads((root / 'output/identity.json').read_text(encoding='utf-8-sig'))
        workspace = Path.home() / request['workspace_run'] / 'workspace'
        from windows_template_probe import workspace_owner
        if workspace_owner(workspace) != request['sid']: raise ValueError('desktop_workspace_invalid')
        experiment(root, request, identity, workspace, report)
    except Exception:
        # The saved bounded stage and observations diagnose incomplete trials;
        # arbitrary Windows/vendor error strings never cross the report boundary.
        report['reason'] = 'atomic_ownership_observation_failed'
    finally:
        (root / 'output/result.json').write_text(json.dumps(report), encoding='utf-8')
    return 1  # This prototype cannot admit a production launch.


if __name__ == '__main__':
    raise SystemExit(main())
