"""Bounded actual-client runtime calibration with synthetic loopback inference only."""
import argparse
import http.server
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import threading
import time
import uuid
import sqlite3
import platform
from urllib.parse import quote

from capability_evaluation import digest, save, version, launcher_seconds
from capability_observer import LoopbackServer, Observer
from capability_runtime import protected, executable_versions, PROVIDERS, loader_tools, desktop_identity, harness_identity, catalog_tools, smoke_execution, read_object
from evaluation_proxy import fixture_response, message
from presentation_runtime import from_loader_output, inventory
from retained_mcp import retained_policy, LIFECYCLE
from presentation_synthetic import SyntheticObserver


def tools(body):
    return [(namespace, tool.get('name')) for namespace, tool in catalog_tools(body)]


def thread_identity(client, log, home, workspace, started):
    if client == 'cli':
        for line in log.read_text(errors='replace').splitlines():
            try: event = json.loads(line)
            except ValueError: continue
            if event.get('type') == 'thread.started': return {'id': event['thread_id'], 'source': 'actual_client_event'}
    else:
        threads = []
        for database in home.glob('state_*.sqlite'):
            with sqlite3.connect('file:' + quote(str(database)) + '?mode=ro', uri=True) as connection:
                columns = {row[1] for row in connection.execute('PRAGMA table_info(threads)')}
                if not {'id', 'cwd', 'created_at'} <= columns: continue
                threads += connection.execute('SELECT id FROM threads WHERE cwd=? AND created_at>=?',
                    (str(workspace), int(started))).fetchall()
        if len(set(threads)) == 1: return {'id': threads[0][0], 'source': 'native_thread_store_read_only'}
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--client', choices=('cli', 'desktop'), required=True)
    parser.add_argument('--codex', required=True, type=Path)
    parser.add_argument('--launcher', required=True, type=Path)
    parser.add_argument('--runtime-root', required=True, type=Path)
    parser.add_argument('--skill', required=True, type=Path)
    parser.add_argument('--private-root', required=True, type=Path)
    parser.add_argument('--codex-home', type=Path, default=Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))))
    parser.add_argument('--app-bundle', type=Path)
    parser.add_argument('--check', action='store_true', help='validate local assets without launch or inference')
    parser.add_argument('--retained-mcp-bridge', type=Path,
        help='allow only the two verified retained Desktop MCP executable references')
    parser.add_argument('--retained-mcp-evidence', type=Path, default=LIFECYCLE)
    parser.add_argument('--production-launcher', action='store_true',
        help='serve synthetic Responses at the observer; use normal launcher/catalog credentials read-only')
    parser.add_argument('--native-account-snapshot', type=Path,
        help='frozen private snapshot for a bounded runtime-preview native-account candidate')
    options = parser.parse_args()
    if options.native_account_snapshot and (options.client != 'desktop' or not options.production_launcher):
        raise ValueError('native_account_calibration_requires_desktop_production_launcher')
    if options.retained_mcp_bridge and options.client != 'desktop':
        raise ValueError('retained_mcp_desktop_only')
    native = desktop_identity(options.app_bundle, options.codex) if options.client == 'desktop' else None
    client_path = options.codex.resolve()
    policy = retained_policy(options.codex_home.resolve(), client_path,
        options.retained_mcp_bridge.absolute(), native, options.retained_mcp_evidence.absolute()) if options.retained_mcp_bridge else None
    client_identity = version(client_path)
    launcher_identity = version(options.launcher)
    expected = inventory(options.runtime_root)
    provider_name = PROVIDERS[options.client]
    expected['provider'] = provider_name
    if options.check:
        print(json.dumps({'status': 'assets_ready', 'client': options.client, 'client_identity': version(options.codex),
            'launcher_identity': version(options.launcher), 'native': native, 'runtime': expected, 'retained_mcp': policy, 'paid_inference': False}))
        return 0
    root = options.private_root.resolve()
    if any((parent / '.git').exists() for parent in (root, *root.parents)):
        raise ValueError('private_root_must_be_outside_git')
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if root.stat().st_mode & 0o077: raise ValueError('private_root_requires_mode_0700')
    run = root / uuid.uuid4().hex; run.mkdir(mode=0o700)
    workspace = run / 'workspace'; workspace.mkdir(mode=0o700)
    prompt = 'Use the provided runtime loader and create the synthetic smoke deck.'
    (run / 'prompt.txt').write_text(prompt + '\n')
    raw_before = protected(options.codex_home, options.skill, options.runtime_root)
    before = protected(options.codex_home, options.skill, options.runtime_root, retained_mcp=policy) if policy else raw_before
    state = {'loader_name': None, 'runtime': None, 'calls': 0, 'failure': None}
    started = time.time()
    observed_versions = {}
    def synthetic_response(body):
        state['calls'] += 1
        save(run / ('model-request-' + str(state['calls']) + '.json'), body)
        outputs = {item.get('call_id'): item.get('output') for item in body.get('input', []) if item.get('type') == 'function_call_output'}
        names = tools(body)
        if body['model'] == 'nvidia/Nemotron-3_5-Lightning':
            item = message(json.dumps({'title': 'Supplied runtime smoke', 'description': 'Synthetic native runtime check'}))
        elif 'runtime-loader' not in outputs:
            name = 'mcp__' + provider_name + '__load_workspace_dependencies'
            if not loader_tools(body, provider_name):
                state['failure'] = 'required_actual_client_loader_missing'
                item = message('Runtime loader unavailable. No artifact was created.')
            else:
                state['loader_name'] = name
                item = {'id': 'fc_runtime', 'type': 'function_call', 'name': 'load_workspace_dependencies',
                        'namespace': 'mcp__' + provider_name,
                        'call_id': 'runtime-loader', 'status': 'completed', 'arguments': '{}'}
        elif 'runtime-smoke' not in outputs:
            output = outputs['runtime-loader']; save(run / 'loader-result.json', output)
            try:
                state['runtime'] = from_loader_output(output, provider_name)
                if state['runtime'] != expected: raise ValueError('returned_runtime_drift')
                command = shlex.join([sys.executable, str(Path(__file__).with_name('presentation_smoke.py')),
                    '--workspace', str(workspace), '--skill', str(options.skill.resolve()),
                    '--provider', provider_name, '--loader-result', str(run / 'loader-result.json')])
                executors = [(namespace, name) for namespace, name in names if name == 'exec_command']
                if len(executors) != 1: raise ValueError('actual_client_exec_tool_missing')
                item = {'id': 'fc_smoke', 'type': 'function_call', 'name': executors[0][1],
                    'call_id': 'runtime-smoke', 'status': 'completed',
                    'arguments': json.dumps({'cmd': command, 'login': False, 'yield_time_ms': 30000, 'max_output_tokens': 2000})}
                if executors[0][0]: item['namespace'] = executors[0][0]
            except (OSError, ValueError):
                state['failure'] = 'loader_result_unqualified'; item = message('Runtime qualification stopped.')
        else:
            save(run / 'smoke-result.json', outputs['runtime-smoke'])
            try:
                smoke_execution(outputs['runtime-smoke'], workspace)
                item = message('[Deck](' + str(workspace / 'output/deck.pptx') + ') [PDF](' + str(workspace / 'output/deck.pdf') + ')')
            except (OSError, ValueError):
                state['failure'] = 'presentation_smoke_failed'
                item = message('The supplied-runtime smoke failed. No delivery was qualified.')
        return fixture_response(item, body['model'])

    class Provider(http.server.BaseHTTPRequestHandler):
        def log_message(self, *unused): pass
        def do_GET(self):
            self.send_response(200); self.end_headers()
            self.wfile.write(json.dumps({'data': [{'id': name} for name in
                ('moonshotai/Kimi-K3', 'zai-org/GLM-5.3', 'zai-org/GLM-5.3-Flash', 'nvidia/Nemotron-3_5-Lightning')]}).encode())
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            if self.path == '/evaluation-stop': self.send_response(204); self.end_headers(); return
            response = synthetic_response(body)
            self.send_response(200); self.send_header('Content-Type', 'text/event-stream'); self.end_headers()
            self.wfile.write(response)
    provider = LoopbackServer(('127.0.0.1', 0), Provider)
    threading.Thread(target=provider.serve_forever, daemon=True).start()
    limits = {'seconds': 600, 'requests': 8, 'output_tokens': 4096}
    process = None
    termination = None
    records = []
    qualification_plan = None
    try:
        observer_type = SyntheticObserver if options.production_launcher else Observer
        observer_options = {'respond': synthetic_response} if options.production_launcher else {}
        with observer_type(run, model='moonshotai/Kimi-K3', guardian='zai-org/GLM-5.3-Flash', limits=limits, **observer_options) as observer:
            records = observer.records
            control = dict(version=1, endpoint=observer.url, secret=observer.secret, seconds=launcher_seconds(limits['seconds']))
            if options.native_account_snapshot:
                import desktop_qualification as qualification
                qualification_plan = qualification.prepare_calibration(run, options, limits)
                control.update(version=2, seconds=limits['seconds'], qualification_declaration=str(run/'declaration.json'))
            if options.client == 'cli':
                control['presentation_runtime'] = {'root': str(options.runtime_root.resolve()),
                    'script': str(Path(__file__).with_name('presentation_runtime.py').resolve())}
            save(run / 'observer.json', control)
            shim = run / 'bin'; shim.mkdir()
            (shim / 'codex').write_text('#!/bin/sh\nexec ' + shlex.quote(str(client_path)) + ' "$@"\n')
            (shim / 'codex').chmod(0o700)
            temporary = run / 'tmp'; temporary.mkdir(mode=0o700)
            env = dict(os.environ, CODEX_HOME=str(options.codex_home.resolve()), FIXTURE_ENDPOINT='http://127.0.0.1:' + str(provider.server_port),
                       PATH=str(shim) + os.pathsep + os.environ.get('PATH', ''), OTEL_SDK_DISABLED='true',
                       TMPDIR=str(temporary), TMP=str(temporary), TEMP=str(temporary))
            if options.production_launcher:
                env.pop('FIXTURE_ENDPOINT', None)
                env.pop('FIXTURE_RETAINED_DIR', None)
            command = [str(options.launcher.resolve()), 'launch', 'codex' if options.client == 'cli' else 'codex-desktop',
                '--model', 'moonshotai/Kimi-K3', '--guardian-model', 'zai-org/GLM-5.3-Flash',
                '--allow-unverified', '--evaluation-observer', str(run / 'observer.json')]
            if options.native_account_snapshot: command += ['--native-account-candidate']
            if options.client == 'cli':
                command += ['--', '--sandbox', 'workspace-write', 'exec', '--ephemeral', '--skip-git-repo-check', '--json', '-']
            else:
                command += ['--app-bundle', str(options.app_bundle.resolve())]
                print('Create a NEW Codex conversation in workspace: ' + str(workspace) +
                    '\nSubmit exactly: ' + prompt + '\nOpen BOTH delivered PPTX/PDF native previews, then record observations for: ' + str(run),
                    file=sys.stderr, flush=True)
            with (run / 'client.log').open('wb') as log:
                process = subprocess.Popen(command, cwd=workspace, env=env, start_new_session=True,
                    stdin=subprocess.PIPE if options.client == 'cli' else subprocess.DEVNULL, stdout=log, stderr=log)
                try:
                    if options.client == 'cli': process.communicate((prompt + '\n').encode(), timeout=limits['seconds'] - 10)
                    else:
                        while process.poll() is None and not observer.reason:
                            if qualification_plan:
                                qualification.calibration_process(run, options.launcher, process, qualification.read(run/'before.json')['identity']['profile'])
                            if (run / 'finish.request').exists(): observer.stop('operator_finished')
                            elif (run / 'cancel.request').exists(): observer.stop('operator_cancelled')
                            time.sleep(.1)
                except subprocess.TimeoutExpired:
                    state['failure'] = 'client_timeout'
                finally:
                    if process.poll() is None:
                        if options.client == 'cli': os.killpg(process.pid, signal.SIGTERM)
                        else: process.terminate()  # Launcher stops only its owned native application.
                        try: process.wait(timeout=5)
                        except subprocess.TimeoutExpired: os.killpg(process.pid, signal.SIGKILL); process.wait(timeout=5)
            records = observer.records
            termination = observer.reason
            if qualification_plan: qualification.finish_calibration(run, qualification_plan, process, observer)
    except KeyboardInterrupt:
        state['failure'] = 'operator_cancelled'
        termination = 'operator_cancelled'
    except (OSError, ValueError, subprocess.SubprocessError):
        state['failure'] = 'actual_client_launch_failed'
    finally:
        provider.shutdown(); provider.server_close()
    if state['runtime']:
        try: observed_versions = executable_versions(state['runtime'], workspace)
        except (OSError, ValueError, subprocess.SubprocessError): state['failure'] = 'supplied_executable_versions_unqualified'
    raw_after = protected(options.codex_home, options.skill, options.runtime_root)
    try:
        after = protected(options.codex_home, options.skill, options.runtime_root, retained_mcp=policy) if policy else raw_after
    except (OSError, ValueError):
        after = None
        state['failure'] = 'retained_mcp_preservation_failed'
    artifacts = {name: digest(workspace / 'output' / name) for name in ('deck.pptx', 'deck.pdf', 'slide.png') if (workspace / 'output' / name).is_file()}
    try: thread = thread_identity(options.client, run / 'client.log', options.codex_home, workspace, started)
    except (OSError, ValueError, sqlite3.DatabaseError): thread = None
    native_preview = 'not_observed'
    if native and (run / 'operator.json').is_file():
        try:
            observation = read_object(run / 'operator.json')
            if observation.get('status') == 'passed' and observation.get('artifacts') == {key: artifacts.get(key) for key in ('deck.pptx', 'deck.pdf')}:
                native_preview = 'passed'
        except (OSError, ValueError): state['failure'] = 'native_preview_evidence_invalid'
    code = process.returncode if process else None
    ended = code == 0 if options.client == 'cli' else termination == 'operator_finished' and native_preview == 'passed'
    if state['failure'] is None:
        try:
            if options.codex.resolve() != client_path or version(client_path) != client_identity:
                state['failure'] = 'client_executable_drift'
            elif native and desktop_identity(options.app_bundle, options.codex) != native:
                state['failure'] = 'native_application_drift'
        except (OSError, ValueError, subprocess.SubprocessError): state['failure'] = 'client_or_application_drift'
    if state['failure'] is None:
        if state['runtime'] is None: state['failure'] = 'actual_client_loader_unobserved'
        elif len(artifacts) != 3: state['failure'] = 'runtime_artifacts_incomplete'
        elif before != after: state['failure'] = 'protected_files_drift'
        elif thread is None: state['failure'] = 'fresh_actual_thread_unobserved'
        elif native and native_preview != 'passed': state['failure'] = 'native_preview_unobserved'
        elif not ended: state['failure'] = termination or 'actual_client_exit_failed'
        elif any(record.get('failure') for record in records) or not any(record.get('role') == 'main' and
                record.get('completed') is True and record.get('final_answer') is True for record in records):
            state['failure'] = 'qualification_delivery_unobserved'
    qualified = state['failure'] is None and state['runtime'] is not None and len(artifacts) == 3 and before == after and ended and thread is not None
    proof = {'schema': 'tofa-presentation-qualification-v1', 'status': 'qualified' if qualified else 'infra_blocked',
        'client': options.client, 'client_identity': client_identity, 'launcher_identity': launcher_identity,
        'client_executable': str(client_path), 'app_bundle': str(options.app_bundle.resolve()) if native else None,
        'host': {'system': platform.system(), 'arch': platform.machine(), 'platform': platform.platform()},
        'paid_inference': False, 'synthetic_transport': 'observer' if options.production_launcher else 'provider_fixture', 'run': str(run), 'limits': limits, 'exit_code': code,
        'termination': termination, 'thread_identity': thread, 'observed_versions': observed_versions,
        'launcher_seconds': launcher_seconds(limits['seconds']),
        'failure': state['failure'], 'loader_name': state['loader_name'], 'runtime': state['runtime'],
        'loader_result_sha256': digest(run / 'loader-result.json') if (run / 'loader-result.json').exists() else None,
        'preservation': {'before': before, 'after': after, 'raw_before': raw_before, 'raw_after': raw_after},
        'retained_mcp': policy, 'settings_preserved': before == after,
        'artifacts': artifacts, 'requests': records, 'model_capability': 'not_measured',
        'pdf_route': 'supplied_libreoffice',
        'native_preview': native_preview, 'native': native,
        'application_sha256': native['application_sha256'] if native else None,
        'operator_sha256': digest(run / 'operator.json') if (run / 'operator.json').is_file() and not (run / 'operator.json').is_symlink() else None,
        'harness': harness_identity()}
    save(run / 'qualification.json', proof)
    print(json.dumps({key: proof[key] for key in ('status', 'run', 'failure', 'loader_name',
        'paid_inference', 'settings_preserved', 'artifacts', 'exit_code')}))
    return 0 if qualified else 1


if __name__ == '__main__': sys.exit(main())
