"""Opt-in installed CLI calibration, synthetic provider and credentials only."""
import http.server
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
import uuid

from evaluation_proxy import fixture_response, message


@unittest.skipUnless(sys.platform == 'darwin' and os.environ.get('TOFA_TEST_CODEX'), 'set TOFA_TEST_CODEX on macOS for real-client calibration')
class InstalledCapabilityTests(unittest.TestCase):
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
                        item = {'id': 'fc_probe', 'type': 'function_call', 'name': 'exec_command',
                                'call_id': 'probe', 'status': 'completed',
                                'arguments': json.dumps({'cmd': 'python3 probe.py; printf "wrapper done\\n"', 'max_output_tokens': 500})}
                    else:
                        item = message('The probe failed because its synthetic dependency is unavailable. Next step: supply the fixture dependency; nothing was installed.')
                self.wfile.write(fixture_response(item, body['model']))
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Provider)
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


if __name__ == '__main__':
    unittest.main()
