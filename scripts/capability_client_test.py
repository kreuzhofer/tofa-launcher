"""Opt-in installed CLI calibration, synthetic provider and credentials only."""
import http.server
import json
import os
import shlex
import signal
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
import uuid
from types import SimpleNamespace

from evaluation_proxy import fixture_response, message
from capability_observer import LoopbackServer, Observer
from capability_evaluation import digest, environment, protected_settings, save, version


@unittest.skipUnless(sys.platform == 'darwin' and os.environ.get('TOFA_TEST_CODEX'), 'set TOFA_TEST_CODEX on macOS for real-client calibration')
class InstalledCapabilityTests(unittest.TestCase):
    def test_installed_cli_deck_runtime_stops_before_provider_inference(self):
        self.calibrate('03')

    def test_installed_cli_with_persistent_skills_delivers_unchanged_fixtures(self):
        self.calibrate('05')

    def test_installed_cli_reports_the_probe_failure_despite_zero_shell_exit(self):
        self.calibrate('07')

    def calibrate(self, case):
        seen = []
        class Provider(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                self.send_response(200); self.end_headers()
                self.wfile.write(json.dumps({'data': [{'id': name} for name in
                    ('moonshotai/Kimi-K3', 'zai-org/GLM-5.3-Flash')]}).encode())
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                seen.append({'model': body['model'], 'cap': body.get('max_output_tokens')})
                self.send_response(200); self.send_header('Content-Type', 'text/event-stream'); self.end_headers()
                item = message('Open fixtures/sample-deck.pptx and fixtures/sample-deck.pdf.')
                if case == '07':
                    if not any(row.get('type') == 'function_call_output' for row in body['input']):
                        # Keep the declared runtime PATH instead of replacing it
                        # through a user's login-shell startup configuration.
                        item = {'id': 'fc_probe', 'type': 'function_call', 'name': 'exec_command',
                                'call_id': 'probe', 'status': 'completed',
                                'arguments': json.dumps({'cmd': 'python3 probe.py; printf "wrapper done\\n"',
                                                         'login': False, 'max_output_tokens': 500})}
                    else:
                        item = message('The probe failed because its synthetic dependency is unavailable. Next step: supply the fixture dependency; nothing was installed.')
                self.wfile.write(fixture_response(item, body['model']))
        server = LoopbackServer(('127.0.0.1', 0), Provider)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            # Keep native configuration and installed skills; only the launcher
            # credential store is synthetic, as in the existing evaluation fixture.
            root = Path(os.environ.get('TOFA_CAPABILITY_CALIBRATION_ROOT', tempfile.gettempdir())) / ('tofa-capability-' + uuid.uuid4().hex)
            root.mkdir(mode=0o700)
            launcher = root / 'launcher'
            subprocess.run(['go', 'build', '-o', str(launcher), './scripts/fixtures/evaluation_launcher'], check=True)
            env = dict(os.environ, FIXTURE_ENDPOINT='http://127.0.0.1:' + str(server.server_port))
            result = subprocess.run([sys.executable, str(Path(__file__).with_name('capability_evaluation.py')),
                'run', '--live', '--case', case, '--client', 'cli', '--model', 'moonshotai/Kimi-K3',
                '--launcher', str(launcher), '--codex', os.environ['TOFA_TEST_CODEX'], '--private-root', str(root / 'runs')],
                env=env, capture_output=True, text=True, timeout=210)
            report = json.loads(result.stdout)
            evidence = {'calibration': 'installed CLI, loopback synthetic provider', 'paid_inference': False,
                        'upstream': seen, 'report': report}
            (root / 'calibration.json').write_text(json.dumps(evidence, indent=2))
            print('Retained calibration: ' + str(root / 'calibration.json'), file=sys.stderr)
            if case == '03':
                self.assertEqual(result.returncode, 1, json.dumps(report))
                self.assertEqual(report['status'], 'infra_blocked')
                self.assertIn('presentation_runtime_unqualified', report['blockers'])
                self.assertEqual(seen, [])
                self.assertEqual(report['requests'], [])
                self.observe_runtime_boundary(root, launcher, env, report, seen)
                return
            self.assertEqual(result.returncode, 0, json.dumps(report))
            self.assertEqual(seen, [{'model': 'moonshotai/Kimi-K3', 'cap': 4096}] * (2 if case == '07' else 1))
            self.assertEqual(report['criteria']['file_integrity']['status'], 'passed')
            self.assertEqual(report['criteria']['visible_preview']['reason'], 'ui_check_pending')
            self.assertTrue(report['settings_preserved'])
            self.assertGreater(len(report['requests'][0]['audit']['instructions']), 0)
            self.assertGreater(len(report['requests'][0]['audit']['tools']), 0)
            if case == '07':
                self.assertEqual(report['criteria']['recovery']['status'], 'passed')
                self.assertEqual(report['actions']['diagnostic_calls'], 1)
        finally:
            server.shutdown(); server.server_close()


    def observe_runtime_boundary(self, root, launcher, env, preflight, seen):
        # This is a separate zero-inference request diagnostic. It does not
        # resume the blocked command or count as a fresh campaign deck cell.
        run = root / 'runtime-boundary'; run.mkdir(mode=0o700)
        workspace = run / 'workspace'; workspace.mkdir(mode=0o700)
        prompt = (root / 'runs' / preflight['run_id'] / 'prompt.txt').read_bytes()
        (run / 'prompt.txt').write_bytes(prompt)
        home = os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))
        options = SimpleNamespace(codex_home=home, launcher=launcher,
                                  codex=os.environ['TOFA_TEST_CODEX'], case='03', skill_root=None)
        before = protected_settings(options)
        inventory_before = environment(options)
        shim = run / 'bin'; shim.mkdir(mode=0o700)
        executable = shim / 'codex'
        executable.write_text('#!/bin/sh\nexec ' + shlex.quote(str(Path(options.codex).resolve())) + ' "$@"\n')
        executable.chmod(0o700)
        env = dict(env, CODEX_HOME=str(Path(home).expanduser().resolve()),
                   PATH=str(shim) + os.pathsep + env.get('PATH', ''), OTEL_SDK_DISABLED='true')
        # The launcher accepts its qualified 180/900-second observer contracts.
        # This diagnostic additionally supervises the native process at 35 seconds.
        limits = {'seconds': 180, 'requests': 1, 'output_tokens': 8192}
        with Observer(run, model='moonshotai/Kimi-K3', guardian='zai-org/GLM-5.3-Flash',
                      limits=limits, case='03') as observer:
            config = run / 'observer.json'
            save(config, dict(version=1, endpoint=observer.url, secret=observer.secret, seconds=limits['seconds']))
            command = [str(launcher), 'launch', 'codex', '--model', 'moonshotai/Kimi-K3',
                       '--guardian-model', 'zai-org/GLM-5.3-Flash', '--allow-unverified',
                       '--evaluation-observer', str(config), '--', '--sandbox', 'workspace-write',
                       'exec', '--ephemeral', '--skip-git-repo-check', '--json', '-']
            process = subprocess.Popen(command, cwd=workspace, env=env, start_new_session=True,
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            try:
                output, _ = process.communicate(prompt, timeout=35)
            finally:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGTERM)
                    try: process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL); process.wait(timeout=5)
            (run / 'client.log').write_bytes(output); (run / 'client.log').chmod(0o600)
        inventory_after = environment(options)
        evidence = {
            'schema': 'tofa-presentation-runtime-calibration-v1',
            'scope': 'installed CLI request diagnostic; blocked command retained separately; not a campaign cell',
            'paid_inference': False, 'client': version(options.codex), 'launcher': version(launcher),
            'limits': limits, 'elapsed_ms': observer.elapsed(), 'exit_code': process.returncode,
            'native_process_timeout_seconds': 35,
            'runtime_contract': preflight['provenance']['presentation_runtime'],
            'settings_preserved': before == protected_settings(options),
            'environment_drift': [key for key in inventory_before if inventory_before[key] != inventory_after.get(key)],
            'requests': observer.records, 'stop_reason': observer.reason, 'upstream': seen,
            'harness_sha256': preflight['provenance']['harness_sha256'],
            'rejected_body_sha256': digest(run / 'rejected-request-1.json') if (run / 'rejected-request-1.json').exists() else None,
            'workspace_artifacts': sorted(path.name for path in workspace.iterdir()),
            'criteria': preflight['criteria'], 'preflight': preflight,
        }
        save(root / 'runtime-calibration.json', evidence)
        print('Retained runtime calibration: ' + str(root / 'runtime-calibration.json'), file=sys.stderr)
        self.assertEqual(observer.reason, 'presentation_runtime_tool_missing')
        self.assertEqual(seen, [])
        self.assertEqual(len(observer.records), 1)
        self.assertFalse(observer.records[0]['forwarded'])
        self.assertEqual(observer.records[0]['presentation_runtime']['advertised'], 'absent')
        self.assertTrue(evidence['settings_preserved'])
        self.assertEqual(evidence['environment_drift'], [])
        self.assertEqual(evidence['workspace_artifacts'], [])
        self.assertTrue(evidence['rejected_body_sha256'])


if __name__ == '__main__':
    unittest.main()
