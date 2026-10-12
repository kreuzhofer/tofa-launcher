"""Behavioral tests of the explicitly invoked capability evaluator command."""
import json
import os
import platform
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import shlex
import time

SCRIPT = Path(__file__).with_name('capability_evaluation.py')


class CommandTests(unittest.TestCase):
    def test_unavailable_comparison_retains_a_blocked_attempt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for content in (None, '{', '{"provenance": []}'):
                comparison = root / 'comparison'; comparison.mkdir(exist_ok=True)
                if content is not None: (comparison / 'result.json').write_text(content)
                result = subprocess.run([sys.executable, str(SCRIPT), 'preflight',
                    '--private-root', str(root / 'runs'), '--case', '05', '--client', 'cli',
                    '--model', 'moonshotai/Kimi-K3', '--launcher', '/missing', '--codex', '/missing',
                    '--compare-with', str(comparison)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 1)
                report = json.loads(result.stdout)
                self.assertEqual(report['status'], 'infra_blocked')
                self.assertIn('comparison_unavailable', report['blockers'])
                self.assertEqual(report, json.loads((root / 'runs' / report['run_id'] / 'result.json').read_text()))

    @unittest.skipUnless((sys.platform, platform.machine()) == ('darwin', 'arm64'), 'macOS pilot')
    def test_missing_usage_and_instruction_delivery_remain_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / 'client'
            executable.write_text('#!/bin/sh\nexec ' + shlex.quote(sys.executable) + ' ' +
                shlex.quote(str(SCRIPT.parent / 'fixtures/capability_launcher.py')) + ' "$@"\n')
            executable.chmod(0o700)
            (root / 'home').mkdir(); (root / 'skills').mkdir()
            command = [sys.executable, str(SCRIPT), 'run', '--live', '--private-root', str(root / 'runs'),
                '--case', '05', '--client', 'cli', '--model', 'moonshotai/Kimi-K3',
                '--launcher', str(executable), '--codex', str(executable),
                '--skill-root', str(root / 'skills'), '--codex-home', str(root / 'home')]
            for usage in ('missing', 'partial'):
                result = subprocess.run(command, env=dict(os.environ, CAPABILITY_FIXTURE_USAGE=usage),
                                        capture_output=True, text=True)
                report = json.loads(result.stdout)
                self.assertEqual(report['status'], 'completed', result.stderr)
                self.assertFalse(report['usage']['complete'])
                self.assertIsNone(report['usage']['output_tokens'])
                self.assertEqual(report['usage']['input_tokens'], 10 if usage == 'partial' else None)
            instructions = root / 'instructions'; instructions.write_text('Required variant instructions.')
            result = subprocess.run(command + ['--variant', 'required', '--instructions', str(instructions)],
                                    capture_output=True, text=True)
            report = json.loads(result.stdout)
            self.assertEqual(report['status'], 'infra_blocked')
            self.assertEqual(report['stop_reason'], 'instruction_variant_missing')
            self.assertEqual(sum(report['request_counts'].values()), 0)

    def test_deck_preflight_declares_larger_limits_without_handoff_fixtures(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = subprocess.run([sys.executable, str(SCRIPT), 'preflight', '--private-root', str(root / 'runs'),
                '--case', '03', '--client', 'desktop', '--model', 'moonshotai/Kimi-K3',
                '--launcher', '/missing', '--codex', '/missing'], capture_output=True, text=True)
            report = json.loads(result.stdout)
            self.assertEqual(report['limits'], {'seconds': 900, 'requests': 80, 'output_tokens': 8192})
            workspace = root / 'runs' / report['run_id'] / 'workspace'
            self.assertEqual(list(workspace.iterdir()), [])
            self.assertEqual(report['provenance']['fixture_hashes'], {})

    def test_instruction_variant_is_scoped_to_its_new_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            instructions = root / 'variant.txt'
            instructions.write_text('Use absolute Markdown links for artifact handoff.\n')
            result = subprocess.run([sys.executable, str(SCRIPT), 'preflight', '--private-root', str(root / 'runs'),
                '--case', '05', '--client', 'cli', '--model', 'moonshotai/Kimi-K3',
                '--launcher', '/missing', '--codex', '/missing', '--variant', 'markdown-v1',
                '--instructions', str(instructions)], capture_output=True, text=True)
            report = json.loads(result.stdout)
            scoped = root / 'runs' / report['run_id'] / 'workspace/AGENTS.md'
            self.assertEqual(scoped.read_bytes(), instructions.read_bytes())
            self.assertIn('instruction_file_sha256', report['provenance'])

    @unittest.skipUnless((sys.platform, platform.machine()) == ('darwin', 'arm64'), 'macOS pilot')
    def test_live_gate_and_completed_run_keep_integrity_and_ui_independent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / 'client'
            fixture = SCRIPT.parent / 'fixtures/capability_launcher.py'
            executable.write_text('#!/bin/sh\nexec ' + shlex.quote(sys.executable) + ' ' + shlex.quote(str(fixture)) + ' "$@"\n')
            executable.chmod(0o700)
            home = root / 'codex'; home.mkdir()
            (home / 'config.toml').write_text('approval_policy = "on-request"\n')
            (root / 'skills').mkdir()
            command = [sys.executable, str(SCRIPT), 'run', '--private-root', str(root / 'runs'),
                '--case', '05', '--client', 'cli', '--model', 'moonshotai/Kimi-K3',
                '--launcher', str(executable), '--codex', str(executable),
                '--skill-root', str(root / 'skills'), '--codex-home', str(home)]
            blocked = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(blocked.returncode, 1, blocked.stderr)
            self.assertIn('explicit_live_mode_required', json.loads(blocked.stdout)['blockers'])
            success = subprocess.run(command + ['--live'], capture_output=True, text=True)
            self.assertEqual(success.returncode, 0, success.stderr)
            report = json.loads(success.stdout)
            self.assertEqual(report['status'], 'completed')
            self.assertEqual(report['criteria']['file_integrity']['status'], 'passed')
            self.assertEqual(report['criteria']['reference_syntax']['status'], 'passed')
            self.assertEqual(report['criteria']['visible_preview']['status'], 'not_run')
            self.assertEqual(report['criteria']['task_content']['status'], 'not_run')
            self.assertTrue(report['settings_preserved'])
            self.assertEqual(report['requests'][0]['usage']['output_tokens'], 20)
            self.assertEqual((home / 'config.toml').read_text(), 'approval_policy = "on-request"\n')
            self.assertEqual(len(list((root / 'runs').glob('*/result.json'))), 2)

    @unittest.skipUnless((sys.platform, platform.machine()) == ('darwin', 'arm64'), 'macOS pilot')
    def test_cancellation_only_stops_the_owned_attempt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'sitecustomize.py').write_text('import socket\n'
                'def unavailable(*args):\n'
                '    raise RuntimeError("loopback startup must not require reverse DNS")\n'
                'socket.getfqdn = unavailable\n')
            executable = root / 'client'
            fixture = SCRIPT.parent / 'fixtures/capability_launcher.py'
            executable.write_text('#!/bin/sh\nexec ' + shlex.quote(sys.executable) + ' ' + shlex.quote(str(fixture)) + ' "$@"\n')
            executable.chmod(0o700)
            (root / 'home').mkdir(); (root / 'skills').mkdir()
            unrelated = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
            command = [sys.executable, str(SCRIPT), 'run', '--live', '--private-root', str(root / 'runs'),
                '--case', '05', '--client', 'cli', '--model', 'moonshotai/Kimi-K3',
                '--launcher', str(executable), '--codex', str(executable),
                '--skill-root', str(root / 'skills'), '--codex-home', str(root / 'home')]
            process = subprocess.Popen(command, env=dict(os.environ, CAPABILITY_FIXTURE_SLOW='1', PYTHONPATH=str(root)),
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    markers = list((root / 'runs').glob('*/workspace/started'))
                    if markers: break
                    if process.poll() is not None:
                        _, stderr = process.communicate()
                        self.fail('owned client exited before readiness: ' + stderr)
                    time.sleep(.05)
                self.assertTrue(markers, 'owned client did not start')
                run = markers[0].parent.parent
                cancelled = subprocess.run([sys.executable, str(SCRIPT), 'cancel', str(run)], capture_output=True)
                self.assertEqual(cancelled.returncode, 0)
                stdout, stderr = process.communicate(timeout=10)
                self.assertEqual(json.loads(stdout)['status'], 'cancelled', stderr)
                self.assertIsNone(unrelated.poll())
            finally:
                if process.poll() is None: process.terminate(); process.communicate(timeout=5)
                unrelated.terminate(); unrelated.wait(timeout=5)

    @unittest.skipUnless((sys.platform, platform.machine()) == ('darwin', 'arm64'), 'macOS pilot')
    def test_preflight_detects_changed_client_before_a_comparison(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            launcher = root / 'launcher'
            launcher.write_text('#!/bin/sh\ncase "$1" in\n--version) echo tofa-test;;\n'
                'evaluation-protocol) echo \'{"version":1}\';;\n'
                'models) printf "moonshotai/Kimi-K3\\nzai-org/GLM-5.3-Flash\\n";;\n*) exit 99;;\nesac\n')
            launcher.chmod(0o700)
            codex = root / 'codex'
            codex.write_text('#!/bin/sh\necho codex-cli 0.162.0\n'); codex.chmod(0o700)
            (root / 'skills').mkdir(); (root / 'home').mkdir()
            command = [sys.executable, str(SCRIPT), 'preflight', '--private-root', str(root / 'runs'),
                '--case', '05', '--client', 'cli', '--model', 'moonshotai/Kimi-K3',
                '--launcher', str(launcher), '--codex', str(codex), '--skill-root', str(root / 'skills'),
                '--codex-home', str(root / 'home')]
            first = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            report = json.loads(first.stdout)
            codex.write_text(codex.read_text() + '# changed artifact\n')
            second = subprocess.run(command + ['--compare-with', str(root / 'runs' / report['run_id'])],
                                    capture_output=True, text=True)
            self.assertEqual(second.returncode, 1, second.stderr)
            changed = json.loads(second.stdout)
            self.assertIn('environment_drift', changed['blockers'])
            self.assertIn('codex', changed['drift'])
            self.assertEqual(changed['requests'], [])

    def test_operator_preview_observation_is_attributed_without_changing_other_scores(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = root / 'attempt'; run.mkdir()
            original = {'schema': 'tofa-capability-v1', 'run_id': 'synthetic', 'status': 'failed',
                        'criteria': {'visible_preview': {'status': 'not_run', 'reason': 'ui_check_pending'},
                                     'file_integrity': {'status': 'failed', 'reason': 'fixture_changed'}},
                        'observations': []}
            (run / 'result.json').write_text(json.dumps(original))
            result = subprocess.run([sys.executable, str(SCRIPT), 'observe', str(run),
                '--operator', 'maintainer', '--criterion', 'visible_preview', '--status', 'passed',
                '--reason', 'both_previews_opened'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            output = root / 'export.json'
            exported = subprocess.run([sys.executable, str(SCRIPT), 'export', str(run), '--output', str(output)],
                                      capture_output=True, text=True)
            self.assertEqual(exported.returncode, 0, exported.stderr)
            report = json.loads(output.read_text())
            self.assertEqual(report['criteria']['file_integrity'], original['criteria']['file_integrity'])
            self.assertEqual(report['criteria']['visible_preview']['status'], 'passed')
            self.assertEqual(report['observations'][0]['operator'], 'maintainer')
            self.assertEqual(json.loads((run / 'result.json').read_text()), original)
            self.assertEqual(len(list(run.glob('observation-*.json'))), 1)

    def test_preflight_retains_unique_attempts_without_inference(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            launcher = root / 'launcher'
            launcher.write_text('#!/bin/sh\nexit 99\n')
            launcher.chmod(0o700)
            runs = []
            for _ in range(2):
                result = subprocess.run([sys.executable, str(SCRIPT), 'preflight',
                    '--private-root', str(root / 'runs'), '--case', '05', '--client', 'cli',
                    '--model', 'moonshotai/Kimi-K3', '--launcher', str(launcher),
                    '--codex', str(launcher)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 1, result.stderr)
                run = json.loads(result.stdout)
                runs.append(run)
                self.assertEqual(run['status'], 'infra_blocked')
                self.assertEqual(run['limits'], {'seconds': 180, 'requests': 12, 'output_tokens': 4096})
                self.assertEqual(run['requests'], [])
                self.assertEqual(run['criteria']['visible_preview'],
                                 {'status': 'not_run', 'reason': 'ui_check_pending'})
                self.assertNotIn(str(Path.home()), result.stdout)
            self.assertNotEqual(runs[0]['run_id'], runs[1]['run_id'])
            self.assertEqual(runs[0]['cell_id'], runs[1]['cell_id'])
            self.assertEqual(len(list((root / 'runs').glob('*/result.json'))), 2)


if __name__ == '__main__':
    unittest.main()
