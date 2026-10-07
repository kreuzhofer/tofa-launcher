"""Owned, synthetic Windows desktop catalog/settings experiment for #86."""
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import threading
import time
from urllib.parse import urlencode

from windows_catalog_protocol import MODELS, PROVIDER
from windows_desktop_runtime import observations, powershell, ui
from windows_ownership_experiment import inspect, wait_app
from windows_ownership_contract import refusal
from windows_process import stop, supervised
from windows_template_probe import NativeEngine, safe_directory


def descriptor(model, priority):
    return {'slug': model, 'display_name': model, 'description': 'Synthetic catalog experiment',
        'default_reasoning_level': 'low', 'supported_reasoning_levels': [
            {'effort': value, 'description': 'Synthetic ' + value} for value in ('low', 'high')],
        'shell_type': 'unified_exec', 'visibility': 'list', 'supported_in_api': True, 'priority': priority,
        'include_apps_usage_instructions': False, 'supports_reasoning_summary_parameter': True,
        'support_verbosity': False, 'truncation_policy': {'mode': 'bytes', 'limit': 10000},
        'context_window': 32000, 'max_context_window': 32000, 'effective_context_window_percent': 95,
        'experimental_supported_tools': [], 'input_modalities': ['text'],
        'model_messages': {'instructions_template': 'Respond to the synthetic test. Do not use tools.'}}


def connect(executable, workspace, home, settings=(), environment=None):
    engine = NativeEngine(executable, workspace, settings, home=home, environment=environment)
    try:
        response = engine.call('initialize', {'clientInfo': {'name': 'tofa_catalog_probe', 'version': '1'},
            'capabilities': {'experimentalApi': True}})
        if 'result' not in response: raise ValueError('catalog_protocol_failed')
        engine.send({'method': 'initialized'})
        return engine
    except Exception:
        engine.close()
        raise


def provider_handler(evidence):
    class Provider(BaseHTTPRequestHandler):
        def log_message(self, format, *args): pass
        def do_GET(self):
            self.send_error(426)
        def do_POST(self):
            try:
                self.connection.settimeout(5)
                evidence['authorization_absent'] = evidence['authorization_absent'] and self.headers.get('Authorization') is None
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length < 1024 * 1024 or self.path != '/responses': raise ValueError()
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict) or not isinstance(body.get('reasoning'), dict): raise ValueError()
                model = body.get('model')
                effort = body.get('reasoning', {}).get('effort')
                if model not in MODELS or effort not in ('low', 'high') or len(evidence['requests']) >= 16: raise ValueError()
                evidence['requests'].append({'model': model, 'effort': effort, 'path': '/responses'})
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.end_headers()
                response = {'id': 'resp_synthetic', 'status': 'completed', 'output': [],
                    'usage': {'input_tokens': 1, 'output_tokens': 0, 'total_tokens': 1}}
                for kind in ('response.created', 'response.completed'):
                    self.wfile.write(('event: ' + kind + '\ndata: ' + json.dumps({'type': kind, 'response': response}) + '\n\n').encode())
                self.wfile.flush()
            except (ValueError, KeyError, TypeError):
                evidence['provider_refusals'] += 1
                self.send_error(400)
    return Provider


def experiment(root, request, identity, workspace, report):
    owned = workspace.parent / 'catalog'
    safe_directory(owned)
    home, profile = owned / 'home', owned / 'electron'
    safe_directory(home)
    safe_directory(profile)
    evidence = {'production_gate': 'blocked', 'stage': 'preparation', 'checks': {}, 'requests': [], 'provider_refusals': 0, 'authorization_absent': True}
    report['catalog'] = evidence
    output = root / 'output/catalog.json'
    def save(): output.write_text(json.dumps(evidence, indent=2), encoding='utf-8')
    save()
    checks = evidence['checks']
    original_path = Path.home() / '.codex/config.toml'
    original = original_path.read_bytes() if original_path.exists() else None
    before = inspect(root)
    # Reuse discovery only; #85 explicitly does not grant production ownership.
    if refusal(before) != (42, 'ownership_unproven'):
        raise ValueError('catalog_discovery_failed')
    executable = before['packages'][0]['app']
    config_path = home / 'config.toml'
    config_path.write_text('model="synthetic-cli"\nmodel_reasoning_effort="low"\n', encoding='utf-8')
    catalog_path = owned / 'models.json'
    catalog_path.write_text(json.dumps({'models': [descriptor(model, i) for i, model in enumerate(MODELS)]}), encoding='utf-8')
    prompt = 'Reply with the exact text TOFA CATALOG OK. This is a synthetic test. Do not call tools.'
    cli = None
    process = None
    app = None
    cli_model = 'synthetic-cli'
    def cli_defaults():
        if cli is None: return False
        value = cli.call('config/read', {'includeLayers': False})['result']['config']
        return value.get('model') == cli_model and value.get('model_reasoning_effort') == 'low'
    server = ThreadingHTTPServer(('127.0.0.1', 0), provider_handler(evidence))
    serving = False
    try:
        settings = ['model=' + json.dumps(MODELS[0]), 'model_provider=' + json.dumps(PROVIDER),
            'model_catalog_json=' + json.dumps(str(catalog_path)), 'model_reasoning_effort="low"',
            'model_providers.' + PROVIDER + '={name="Synthetic catalog",base_url="http://127.0.0.1:' + str(server.server_port) + '",wire_api="responses",requires_openai_auth=false}',
            'mcp_servers={}', 'plugins={}', 'hooks={}', 'features.plugins=false', 'features.hooks=false',
            'features.memories=false', 'project_doc_max_bytes=0']
        smoke = workspace.parent / 'desktop'
        supervisor = smoke / 'tofa-supervisor.exe'
        config = json.loads((smoke / 'bridge.json').read_text())
        config.update(evidence_dir=str(owned), prompt=prompt, visualization_root=str(home / 'visualizations'),
            catalog={'config_file': str(config_path), 'settings': settings})
        bridge_config = owned / 'bridge.json'
        bridge_config.write_text(json.dumps(config), encoding='utf-8')
        threading.Thread(target=server.serve_forever, daemon=True).start()
        serving = True
        cli = connect(identity['engine'], workspace, home)
        checks['cli_before'] = cli_defaults()
        evidence['stage'] = 'desktop'
        save()
        env = {key: value for key, value in os.environ.items() if not key.upper().startswith(('CODEX_', 'OPENAI_', 'TOFA_'))}
        env.update(CODEX_HOME=str(home), CODEX_ELECTRON_USER_DATA_PATH=str(profile),
            CODEX_CLI_PATH=str(smoke / 'codex.exe'), TOFA_LIVE_PYTHON=request['python'],
            TOFA_LIVE_HARNESS=str(root / 'windows_desktop_bridge.py'), TOFA_DESKTOP_PROBE_CONFIG=str(bridge_config))
        link = 'codex://threads/new?' + urlencode({'path': str(workspace), 'prompt': prompt})
        process = subprocess.Popen(supervised([executable, '--force-renderer-accessibility', link], supervisor),
            env=env, cwd=workspace, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        app = wait_app(process, executable)
        evidence['identity'] = {'app_sha256': hashlib.sha256(Path(executable).read_bytes()).hexdigest(),
            'engine_sha256': identity['package_engine_sha256']}
        ready_deadline = time.monotonic() + 30
        while time.monotonic() < ready_deadline:
            startup_events = observations(owned)
            main_bridges = {item['bridge_pid'] for item in startup_events if item.get('event') == 'initialized'
                            and item.get('main_connection') is True and item.get('ok') is True}
            if len(main_bridges) == 1 and any(item.get('event') == 'catalog_advertised'
                    and item.get('bridge_pid') in main_bridges for item in startup_events): break
            time.sleep(.25)
        else: raise ValueError('catalog_protocol_failed')
        evidence['stage'] = 'picker'
        save()
        control = (root / 'windows_catalog_ui.ps1').read_text().replace('__REQUEST__', base64.b64encode(json.dumps(app).encode()).decode())
        selection = powershell(control, timeout=45)
        evidence['picker'] = selection
        save()
        if not selection.get('ok'): raise ValueError('catalog_picker_failed')
        cli_model = 'synthetic-cli-concurrent'
        changed = cli.call('config/value/write', {'keyPath': 'model', 'value': cli_model, 'mergeStrategy': 'replace'})
        checks['cli_during'] = 'result' in changed and cli_defaults()
        if not ui(root, app, 'configure', report): raise ValueError('catalog_picker_failed')
        if not ui(root, app, 'submit', report): raise ValueError('catalog_picker_failed')
        evidence['stage'] = 'request'
        save()
        events = []
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            events = observations(owned)
            if any(item.get('event') == 'turn_completed' for item in events): break
            time.sleep(.25)
        checks['provider_scope_preserved'] = evidence['provider_refusals'] == 0 and evidence['authorization_absent']
        checks['selected_request'] = evidence['requests'] == [{'model': MODELS[1], 'effort': 'high', 'path': '/responses'}]
        checks['native_turn_completed'] = any(item.get('event') == 'turn_completed' and item.get('success') for item in events)
        checks['cli_after_selection'] = cli_defaults()
        evidence['stage'] = 'settings'
        save()
        # Replay mixed/unrelated writes through the same executable and native engine.
        replay = connect(str(smoke / 'codex.exe'), workspace, home, environment={key: env[key] for key in ('TOFA_LIVE_PYTHON', 'TOFA_LIVE_HARNESS', 'TOFA_DESKTOP_PROBE_CONFIG')})
        try:
            def write(edits):
                return replay.call('config/batchWrite', {'filePath': None, 'reloadUserConfig': True, 'edits': [
                    {'keyPath': key, 'value': value, 'mergeStrategy': 'replace'} for key, value in edits]})
            prior_tui = cli.call('config/read', {})['result']['config'].get('tui')
            mixed = write([('model', MODELS[1]), ('tui.animations', False)])
            checks['mixed_refused'] = 'error' in mixed
            checks['mixed_atomic'] = cli.call('config/read', {})['result']['config'].get('tui') == prior_tui
            unrelated = write([('tui.animations', False)])
            checks['unrelated_native'] = 'result' in unrelated and cli.call('config/read', {})['result']['config'].get('tui', {}).get('animations') is False
            checks['cli_after_writes'] = cli_defaults()
        finally:
            checks['replay_exited'] = replay.close()
    finally:
        evidence['last_work_stage'] = evidence['stage']
        evidence['stage'] = 'cleanup'
        checks['normal_quit'] = False
        try:
            if process is not None and app and process.poll() is None and ui(root, app, 'quit', report):
                checks['normal_quit'] = process.wait(timeout=10) == 0
        except (ValueError, OSError, subprocess.SubprocessError):
            checks['normal_quit'] = False
        finally:
            # Each cleanup is independent: failed engine/VM IO must not strand
            # the provider or suppress the remaining preservation evidence.
            try:
                if process is not None and process.poll() is None: stop(process)
            except Exception:
                checks['normal_quit'] = False
            if cli is not None:
                try: checks['cli_after_shutdown'] = cli_defaults()
                except Exception: checks['cli_after_shutdown'] = False
                try: checks['cli_exited'] = cli.close()
                except Exception: checks['cli_exited'] = False
            checks['provider_closed'] = True
            try:
                if serving: server.shutdown()
            except Exception: checks['provider_closed'] = False
            try: server.server_close()
            except Exception: checks['provider_closed'] = False
            checks['provider_scope_preserved'] = evidence['provider_refusals'] == 0 and evidence['authorization_absent']
            try: checks['ordinary_config_preserved'] = original == (original_path.read_bytes() if original_path.exists() else None)
            except OSError: checks['ordinary_config_preserved'] = False
            try:
                after = inspect(root)
                checks['vendor_service_preserved'] = before['service'] == after['service']
                checks['owned_apps_exited'] = not after['incumbents']
            except Exception:
                checks['vendor_service_preserved'] = checks['owned_apps_exited'] = False
            try:
                evidence['events'] = observations(owned, final=True)
                checks['diagnostics_written'] = True
            except Exception: checks['diagnostics_written'] = False
            save()
    evidence['stage'] = 'complete'
    save()
    if not all(checks.values()): raise ValueError('catalog_observation_failed')
