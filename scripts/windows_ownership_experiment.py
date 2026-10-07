"""Bounded #85 measurements in an owned runner clone, never production admission."""
import json
import os
from pathlib import Path
import subprocess
import time

from windows_desktop_runtime import observations, powershell, ui
from windows_process import stop, supervised


def inspect(root, probe=''):
    source = (root / 'windows_ownership_inspect.ps1').read_text().replace('__PROBE_PATH__', str(probe).replace("'", "''"))
    return powershell(source, timeout=25)


def wait_app(process, executable):
    deadline = time.monotonic() + 20
    escaped = executable.replace("'", "''")
    while time.monotonic() < deadline:
        if process.poll() is not None: raise ValueError('ownership_startup_failed')
        result = powershell("$all=@(Get-CimInstance Win32_Process);$ids=@(" + str(process.pid) + ");"
            "do{$new=@($all|Where-Object {$_.ParentProcessId -in $ids -and $_.ProcessId -notin $ids}|ForEach-Object {$_.ProcessId});$ids+=$new}while($new.Count -gt 0);"
            "$p=@(Get-Process|Where-Object {$_.Id -in $ids -and $_.Path -eq '" + escaped + "' -and $_.MainWindowHandle -ne 0});"
            "if($p.Count -eq 1){@{pid=$p[0].Id;started_ticks=$p[0].StartTime.ToUniversalTime().Ticks;executable=$p[0].Path}|ConvertTo-Json}else{'null'}")
        if result: return result
        time.sleep(.3)
    raise ValueError('ownership_startup_failed')


def experiment(root, request, workspace, report):
    owned = workspace.parent / 'desktop'
    supervisor = owned / 'tofa-supervisor.exe'
    evidence = {'production_gate': 'blocked', 'blocker': 'atomic_profile_ipc_ownership_unproven', 'checks': {}}
    report['ownership'] = evidence
    checks = evidence['checks']
    # Retain bounded observations even when a later native step fails.
    output = root / 'output/ownership.json'
    def save(): output.write_text(json.dumps(evidence, indent=2), encoding='utf-8')
    evidence['stage'] = 'argv'
    save()
    # Exercise native argv/environment/stdio through the same executable shim.
    values = ['', 'space value', 'quote"value', 'trailing\\', '雪']
    code = "import json,os,sys; print(json.dumps([sys.argv[1:],os.environ['TOFA_OWNERSHIP_VALUE'],sys.stdin.read()])); sys.exit(17)"
    preserved = subprocess.run(supervised([request['python'], '-c', code, *values], supervisor),
        env=dict(os.environ, TOFA_OWNERSHIP_VALUE='synthetic environment'), input='synthetic stdin',
        capture_output=True, text=True, timeout=15)
    checks['argv_environment_stdio_exit'] = preserved.returncode == 17 and json.loads(preserved.stdout) == [values, 'synthetic environment', 'synthetic stdin']
    evidence['stage'] = 'paths'
    save()
    target = owned / 'path-target'
    target.mkdir()
    junction = owned / 'path-junction'
    powershell("New-Item -ItemType Junction -Path '" + str(junction).replace("'", "''") + "' -Target '" + str(target).replace("'", "''") + "'|Out-Null;'true'")
    evidence['stage'] = 'discovery'
    save()
    before = inspect(root, junction)
    checks['reparse_refused'] = before.pop('path_probe') is False
    checks['case_equivalent'] = inspect(root, str(target).upper()).pop('path_probe') is True
    evidence['synthetic_histories'] = [{'path': item['path'], 'exists': Path(item['path']).is_file()}
        for item in observations(owned, final=True) if item.get('event') == 'synthetic_history']

    evidence['before'] = before
    save()
    snapshot = owned / 'ownership-inventory.json'
    snapshot.write_text(json.dumps(before), encoding='utf-8')
    args = [request['python'], str(root / 'windows_ownership_contract.py'), '--inventory', str(snapshot)]
    discovery = subprocess.run(args, capture_output=True, timeout=5)
    if discovery.returncode == 41: raise ValueError('native_client_busy')
    # This validates discovery for the explicitly authorized synthetic trial.
    # It deliberately does not turn the snapshot into production ownership.
    if (discovery.returncode != 42 or discovery.stderr
            or json.loads(discovery.stdout) != {'may_launch': False, 'reason': 'ownership_unproven'}):
        raise ValueError('ownership_discovery_failed')
    executable = before['packages'][0]['app']
    evidence['stage'] = 'ordinary_start'
    save()
    ordinary = subprocess.Popen(supervised([executable, '--force-renderer-accessibility'], supervisor),
        cwd=workspace, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    app = None
    alternate = None
    alternate_app = None
    try:
        app = wait_app(ordinary, executable)
        time.sleep(3)
        evidence['stage'] = 'ordinary_inspect'
        save()
        current = inspect(root)
        evidence['ordinary'] = current
        snapshot.write_text(json.dumps(current), encoding='utf-8')
        contenders = [subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(2)]
        results = [child.communicate(timeout=5) for child in contenders]
        checks['competing_guards_refused'] = all(child.returncode == 41 for child in contenders)
        checks['ordinary_refused'] = all(json.loads(out) == {'may_launch': False, 'reason': 'native_client_busy'}
                                         for out, err in results if not err) and not any(err for out, err in results)
        checks['incumbent_preserved'] = ordinary.poll() is None and inspect(root)['incumbents'] == current['incumbents']
        # Observe the native singleton, under our own Job, without treating its
        # activation of our synthetic ordinary instance as launcher ownership.
        evidence['stage'] = 'singleton'
        save()
        second = subprocess.Popen(supervised([executable], supervisor), cwd=workspace,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            evidence['same_profile_exit'] = second.wait(timeout=10)
            checks['same_profile_singleton'] = evidence['same_profile_exit'] == 0 and ordinary.poll() is None
        finally:
            if second.poll() is None: stop(second)
        evidence['stage'] = 'separate_profile'
        save()
        separate = owned / 'separate-profile'
        separate.mkdir()
        # A new Electron profile has no authority over the machine-wide IPC name.
        # Its engine still uses the already-tested bounded bridge (no turns allowed).
        separate_evidence = owned / 'separate-evidence'
        separate_evidence.mkdir()
        config = json.loads((owned / 'bridge.json').read_text())
        config.update(evidence_dir=str(separate_evidence), prompt='NO AUTHORIZED TURNS IN OWNERSHIP PROBE')
        config_path = owned / 'separate-bridge.json'
        config_path.write_text(json.dumps(config), encoding='utf-8')
        environment = dict(os.environ, CODEX_ELECTRON_USER_DATA_PATH=str(separate),
            CODEX_CLI_PATH=str(owned / 'codex.exe'), TOFA_LIVE_PYTHON=request['python'],
            TOFA_LIVE_HARNESS=str(root / 'windows_desktop_bridge.py'), TOFA_DESKTOP_PROBE_CONFIG=str(config_path))
        alternate = subprocess.Popen(supervised([executable, '--force-renderer-accessibility'], supervisor),
            env=environment, cwd=workspace, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            alternate_app = wait_app(alternate, executable)
            evidence['separate_profile_result'] = 'window'
        except ValueError:
            if alternate.poll() != 0: raise
            evidence['separate_profile_result'] = 'exited_without_window'
        time.sleep(3)
        evidence['separate'] = inspect(root)
        checks['separate_profile_measured'] = (alternate_app is not None or alternate.returncode == 0)
        checks['ordinary_still_alive'] = ordinary.poll() is None and evidence['separate']['pipe']['server_pid'] == app['pid']

    finally:
        evidence['stage'] = 'cleanup'
        save()
        for process, window, name in ((alternate, alternate_app, 'separate_owned_exit'), (ordinary, app, 'ordinary_normal_quit')):
            checks[name] = process is not None and process.poll() == 0
            if process is None: continue
            try:
                if window and process.poll() is None and ui(root, window, 'quit', report):
                    checks[name] = process.wait(timeout=10) == 0
            except (ValueError, OSError, subprocess.SubprocessError):
                checks[name] = False
            finally:
                try:
                    if process.poll() is None: stop(process)
                except (OSError, subprocess.SubprocessError):
                    checks[name] = False
                save()
        after = inspect(root)
        evidence['after'] = after
        checks['vendor_service_preserved'] = before['service'] == after['service'] and after['service']['state'] == 'Running'
        checks['owned_apps_exited'] = not after['incumbents']
        events = observations(owned, final=True)
        evidence['bridge_initializations'] = [{'main': event['main_connection'], 'ok': event['ok']}
                                              for event in events if event.get('event') == 'initialized']
        save()
    evidence['stage'] = 'complete'
    save()
    if not all(checks.values()): raise ValueError('ownership_observation_failed')
