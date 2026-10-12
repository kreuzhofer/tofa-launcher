"""Behavioral tests of the explicitly invoked capability evaluator command."""
import json
import hashlib
import os
import platform
import plistlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import shlex
import time

SCRIPT = Path(__file__).with_name('capability_evaluation.py')


def desktop_handoff(root, encoding, *, command='run', case='05', artifacts='present', settings_drift=False, client='desktop'):
    bundle = root / 'FixtureDesktop.app'
    contents = bundle / 'Contents'
    (contents / 'Resources').mkdir(parents=True)
    (contents / 'MacOS').mkdir()
    (contents / 'Info.plist').write_bytes(plistlib.dumps({
        'CFBundleShortVersionString': '0.0.0', 'CFBundleVersion': 'synthetic'}))
    (contents / 'MacOS/ChatGPT').write_text('synthetic app; never executed')
    (contents / 'Resources/app.asar').write_text('synthetic resources')
    executable = contents / 'Resources/codex'
    executable.write_text('#!/bin/sh\nexec ' + shlex.quote(sys.executable) + ' ' +
        shlex.quote(str(SCRIPT.parent / 'fixtures/capability_launcher.py')) + ' "$@"\n')
    executable.chmod(0o700)
    (root / 'home').mkdir()
    if settings_drift: (root / 'home/config.toml').write_text('# synthetic original settings\n')
    (root / 'skills').mkdir()
    if case == '18':
        (root / 'skills/documents').mkdir()
        (root / 'skills/documents/SKILL.md').write_text('---\nname: documents\n---\nSynthetic inventory only.\n')
    if case in ('03', '04'):
        skill = root / 'skills/presentations'
        (skill / 'references').mkdir(parents=True)
        (skill / 'SKILL.md').write_text('---\nname: presentations\n---\nSynthetic inventory only.\n')
        (skill / 'references/implementation.md').write_text(
            'Call `load_workspace_dependencies`. Do not install substitutes.\n')
    return subprocess.run([sys.executable, str(SCRIPT), command] + (['--live'] if command == 'run' else []) + [
        '--private-root', str(root / 'runs'), '--case', case, '--client', client,
        '--model', 'moonshotai/Kimi-K3', '--launcher', str(executable),
        '--codex', str(executable), '--app-bundle', str(bundle),
        '--codex-home', str(root / 'home'), '--skill-root', str(root / 'skills')],
        env=dict(os.environ, CAPABILITY_FIXTURE_REFERENCE_ENCODING=encoding,
                 CAPABILITY_FIXTURE_ARTIFACTS=artifacts,
                 CAPABILITY_FIXTURE_SETTING_DRIFT='1' if settings_drift else ''),
        capture_output=True, text=True, timeout=15)


class CommandTests(unittest.TestCase):
    @unittest.skipUnless((sys.platform, platform.machine()) == ('darwin', 'arm64'), 'macOS pilot')
    def test_decks_block_before_launch_with_installed_runtime_contract_provenance(self):
        for case, client in (('03', 'desktop'), ('04', 'cli')):
            with self.subTest(case=case, client=client), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                result = desktop_handoff(root, 'raw', case=case, client=client, settings_drift=True)
                self.assertEqual(result.returncode, 1, result.stderr)
                report = json.loads(result.stdout)
                self.assertEqual(report['status'], 'infra_blocked')
                self.assertEqual(report['blockers'], ['presentation_runtime_unqualified'])
                self.assertEqual(report['requests'], [])
                run = root / 'runs' / report['run_id']
                self.assertFalse((run / 'client.log').exists())
                self.assertEqual((root / 'home/config.toml').read_text(), '# synthetic original settings\n')
                self.assertEqual(list((run / 'workspace').iterdir()), [])
                runtime = report['provenance']['presentation_runtime']
                self.assertEqual(runtime['status'], 'unqualified')
                self.assertEqual(runtime['required_tool'], 'load_workspace_dependencies')
                self.assertEqual(runtime['loader_result'], 'not_observed')
                implementation = 'Call `load_workspace_dependencies`. Do not install substitutes.\n'
                self.assertEqual(runtime['skill_implementations'][0]['implementation_sha256'],
                                 hashlib.sha256(implementation.encode()).hexdigest())
                self.assertTrue(runtime['skill_implementations'][0]['requirement_observed'])
                self.assertEqual(report['limits'], {'seconds': 900, 'requests': 80, 'output_tokens': 8192})
                for criterion in ('task_content', 'skill_use', 'visible_preview'):
                    self.assertEqual(report['criteria'][criterion]['status'], 'not_run')

    @unittest.skipUnless((sys.platform, platform.machine()) == ('darwin', 'arm64'), 'macOS pilot')
    def test_protected_settings_drift_is_hash_audited_and_never_restored(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = desktop_handoff(root, 'uri', settings_drift=True)
            self.assertEqual(result.returncode, 1, result.stderr)
            report = json.loads(result.stdout)
            self.assertFalse(report['settings_preserved'])
            self.assertIn('protected_settings_changed', report['blockers'])
            audit = report['protected_settings_hashes']
            self.assertEqual(audit['changed'], ['codex_config'])
            self.assertEqual(set(audit['before']), {'codex_config', 'launcher_config'})
            self.assertEqual(set(audit['after']), {'codex_config', 'launcher_config'})
            self.assertNotEqual(audit['before']['codex_config'], audit['after']['codex_config'])
            self.assertEqual((root / 'home/config.toml').read_text(), '# synthetic concurrent edit\n')
            self.assertNotIn('synthetic concurrent edit', json.dumps(report))

    @unittest.skipUnless((sys.platform, platform.machine()) == ('darwin', 'arm64'), 'macOS pilot')
    def test_heldout_preflight_has_its_own_contract_and_frozen_incident_input(self):
        with tempfile.TemporaryDirectory(prefix='capability heldout ') as directory:
            root = Path(directory)
            result = desktop_handoff(root, 'angle', command='preflight', case='18')
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report['cell']['corpus'], 'incident-handover-v1')
            self.assertEqual(report['limits'], {'seconds': 900, 'requests': 80, 'output_tokens': 8192})
            self.assertEqual(report['provenance']['fixture_hashes'], {
                'fixtures/incident.csv': '7455fdd0980e532817241cfe455da739729647edb8d16f52b405c3be40ad35d6'})
            run = root / 'runs' / report['run_id']
            self.assertIn('12 synthetic users affected', (run / 'workspace/fixtures/incident.csv').read_text())
            self.assertIn('handover outputs/incident brief.docx', (run / 'prompt.txt').read_text())
            self.assertFalse((run / 'workspace/fixtures/sample-deck.pptx').exists())
            self.assertFalse((run / 'workspace/handover outputs').exists())
            self.assertEqual(report['criteria']['visible_preview']['status'], 'not_run')

    @unittest.skipUnless((sys.platform, platform.machine()) == ('darwin', 'arm64'), 'macOS pilot')
    def test_heldout_requires_desktop_and_an_installed_document_skill(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ready = desktop_handoff(root, 'angle', command='preflight', case='18')
            self.assertEqual(ready.returncode, 0, ready.stderr)
            executable = root / 'FixtureDesktop.app/Contents/Resources/codex'
            (root / 'skills/documents/SKILL.md').unlink()
            result = subprocess.run([sys.executable, str(SCRIPT), 'run', '--live',
                '--private-root', str(root / 'runs'), '--case', '18', '--client', 'cli',
                '--model', 'moonshotai/Kimi-K3', '--launcher', str(executable), '--codex', str(executable),
                '--codex-home', str(root / 'home'), '--skill-root', str(root / 'skills')],
                capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 1, result.stderr)
            report = json.loads(result.stdout)
            self.assertIn('workflow_client_mismatch', report['blockers'])
            self.assertIn('document_skill_missing', report['blockers'])
            self.assertEqual(report['requests'], [])

    @unittest.skipUnless((sys.platform, platform.machine()) == ('darwin', 'arm64'), 'macOS pilot')
    def test_heldout_space_paths_require_valid_markdown_destinations(self):
        for encoding, status in (('raw', 'failed'), ('uri', 'passed'), ('uri-other-workspace', 'failed')):
            with self.subTest(encoding=encoding), tempfile.TemporaryDirectory(prefix='capability heldout ') as directory:
                result = desktop_handoff(Path(directory), encoding, case='18')
                self.assertEqual(result.returncode, 0, result.stderr)
                report = json.loads(result.stdout)
                self.assertEqual(report['criteria']['reference_syntax']['status'], status)
                self.assertEqual(report['criteria']['file_integrity']['status'], 'inconclusive')
                self.assertEqual(report['criteria']['visible_preview']['status'], 'not_run')

    @unittest.skipUnless((sys.platform, platform.machine()) == ('darwin', 'arm64'), 'macOS pilot')
    def test_heldout_records_generated_hashes_and_leaves_document_checks_pending(self):
        with tempfile.TemporaryDirectory(prefix='capability heldout ') as directory:
            root = Path(directory)
            result = desktop_handoff(root, 'angle', case='18')
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report['status'], 'completed')
            self.assertEqual(report['criteria']['reference_syntax']['status'], 'passed')
            self.assertEqual(report['input_integrity']['status'], 'passed')
            self.assertEqual(set(report['artifacts']), {
                'handover outputs/incident brief.docx', 'handover outputs/incident brief.pdf'})
            for artifact in report['artifacts'].values():
                self.assertEqual(artifact['status'], 'present')
                self.assertEqual(len(artifact['sha256']), 64)
                self.assertEqual(artifact['validation'], 'operator_check_pending')
            self.assertEqual(report['criteria']['file_integrity'], {
                'status': 'inconclusive', 'reason': 'document_validation_pending'})
            for criterion in ('task_content', 'language', 'skill_use', 'visible_preview'):
                self.assertEqual(report['criteria'][criterion]['status'], 'not_run')

    @unittest.skipUnless((sys.platform, platform.machine()) == ('darwin', 'arm64'), 'macOS pilot')
    def test_heldout_does_not_credit_missing_or_symlinked_generated_outputs(self):
        for mode, status in (('missing', 'missing'), ('symlink', 'unsafe_path')):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory(prefix='capability heldout ') as directory:
                result = desktop_handoff(Path(directory), 'angle', case='18', artifacts=mode)
                self.assertEqual(result.returncode, 0, result.stderr)
                report = json.loads(result.stdout)
                self.assertEqual(report['criteria']['reference_syntax']['status'], 'passed')
                self.assertEqual(report['criteria']['file_integrity']['status'], 'failed')
                self.assertEqual(report['artifacts']['handover outputs/incident brief.pdf']['status'], status)
                self.assertNotIn('sha256', report['artifacts']['handover outputs/incident brief.pdf'])
                self.assertEqual(report['criteria']['visible_preview']['status'], 'not_run')

    @unittest.skipUnless((sys.platform, platform.machine()) == ('darwin', 'arm64'), 'macOS pilot')
    def test_symlinked_workspace_cannot_supply_input_or_generated_artifact_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            result = desktop_handoff(Path(directory), 'angle', case='18', artifacts='workspace-symlink')
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report['input_integrity']['status'], 'failed')
            for artifact in report['artifacts'].values():
                self.assertEqual(artifact, {'status': 'unsafe_path'})


    @unittest.skipUnless((sys.platform, platform.machine()) == ('darwin', 'arm64'), 'macOS pilot')
    def test_desktop_handoff_scores_percent_encoded_absolute_fixture_links(self):
        with tempfile.TemporaryDirectory(prefix='capability handoff ') as directory:
            root = Path(directory)
            result = desktop_handoff(root, 'uri')
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report['criteria']['reference_syntax'], {
                'status': 'passed', 'reason': 'absolute_markdown_links'})
            self.assertEqual(report['criteria']['file_integrity']['status'], 'passed')
            self.assertEqual(report['criteria']['visible_preview']['status'], 'not_run')

    @unittest.skipUnless((sys.platform, platform.machine()) == ('darwin', 'arm64'), 'macOS pilot')
    def test_desktop_handoff_does_not_credit_links_to_another_workspace(self):
        with tempfile.TemporaryDirectory(prefix='capability handoff ') as directory:
            result = desktop_handoff(Path(directory), 'uri-other-workspace')
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report['criteria']['reference_syntax']['status'], 'failed')
            self.assertEqual(report['criteria']['file_integrity']['status'], 'passed')
            self.assertEqual(report['criteria']['visible_preview']['status'], 'not_run')

    @unittest.skipUnless((sys.platform, platform.machine()) == ('darwin', 'arm64'), 'macOS pilot')
    def test_desktop_reference_forms_keep_pending_ui_independent(self):
        for encoding, status in (('raw', 'passed'), ('angle', 'passed'), ('uri-malformed', 'failed')):
            with self.subTest(encoding=encoding), tempfile.TemporaryDirectory(prefix='capability handoff ') as directory:
                result = desktop_handoff(Path(directory), encoding)
                self.assertEqual(result.returncode, 0, result.stderr)
                report = json.loads(result.stdout)
                self.assertEqual(report['criteria']['reference_syntax']['status'], status)
                self.assertEqual(report['criteria']['file_integrity']['status'], 'passed')
                self.assertEqual(report['criteria']['visible_preview']['status'], 'not_run')

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
