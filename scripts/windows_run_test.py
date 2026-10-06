"""Public clone-to-result CLI exercised against external VM/guest resources."""
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import time
import unittest

SCRIPTS = Path(__file__).resolve().parent
TEMPLATE = 'aaaaaaaa-1111-4111-8111-111111111111'
EVERYDAY = 'bbbbbbbb-2222-4222-8222-222222222222'


@unittest.skipIf(os.name == 'nt', 'Mac operator CLI requires Unix executable fixtures')
class RunTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='tofa run ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.runs = self.root / 'runs'
        self.state = self.root / 'vms.json'
        self.state.write_text(json.dumps({'vms': [
            {'uuid': TEMPLATE, 'status': 'stopped', 'name': 'Dedicated template'},
            {'uuid': EVERYDAY, 'status': 'started', 'name': 'Everyday Windows'},
        ], 'effects': [], 'mode': 'success', 'runs': str(self.runs)}))
        self.utm = self.root / 'utmctl'
        self.utm.write_text('#!' + sys.executable + '\nimport runpy\nrunpy.run_path(' +
                            repr(str(SCRIPTS / 'fixtures/windows_run_utm.py')) + ', run_name="__main__")\n')
        self.utm.chmod(0o700)
        self.env = {**os.environ, 'TEMPLATE_FIXTURE_STATE': str(self.state)}
        self.candidate = self.root / 'candidate.exe'
        data = bytearray(256)
        data[:2] = b'MZ'
        struct.pack_into('<I', data, 60, 128)
        data[128:132] = b'PE\0\0'
        struct.pack_into('<H', data, 132, 0xAA64)
        self.candidate.write_bytes(data)

    def change(self, **values):
        state = json.loads(self.state.read_text())
        state.update(values)
        self.state.write_text(json.dumps(state))

    def invoke(self, *extra, command='run'):
        args = [sys.executable, str(SCRIPTS / 'windows_test_runner.py'), command,
                '--state-dir', str(self.runs), '--utmctl', str(self.utm), '--timeout', '240']
        if command == 'run':
            args += ['--template', TEMPLATE, '--dedicated-template', '--test-user', 'tofa-test',
                     '--candidate', str(self.candidate), '--version', 'v0.0.1-rc.14',
                     '--sha256', hashlib.sha256(self.candidate.read_bytes()).hexdigest(),
                     '--candidate-commit', 'c' * 40, '--suite', 'native-smoke']
        result = subprocess.run(args + list(extra), env=self.env, capture_output=True, text=True, timeout=20)
        reports = list(self.runs.glob('tofa-run-*/report.json'))
        report = json.loads(max(reports, key=lambda p: p.stat().st_mtime_ns).read_text()) if reports else {}
        for secret in ('PRIVATE_KEY', 'UNRELATED_CONTENT'):
            self.assertNotIn(secret, result.stdout + result.stderr + json.dumps(report))
        return result, report, json.loads(self.state.read_text())

    def test_running_source_is_rejected_without_mutation(self):
        state = json.loads(self.state.read_text())
        state['vms'][0]['status'] = 'started'
        self.change(vms=state['vms'])
        result, report, state = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report['reason'], 'template_must_be_stopped')
        self.assertEqual(state['effects'], [])

    def test_fresh_clone_collects_native_results_then_deletes_only_owned_clone(self):
        result, report, state = self.invoke()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(report['outcome'], 'passed')
        self.assertEqual(report['suite'], 'native-smoke')
        self.assertEqual(report['candidate']['sha256'], hashlib.sha256(self.candidate.read_bytes()).hexdigest())
        self.assertEqual(report['candidate']['architecture'], 'ARM64')
        self.assertEqual(report['native']['identity']['engine_version'], '0.159.2')
        self.assertTrue(report['native']['checks']['workspace_write_read'])
        self.assertTrue(report['native']['checks']['outside_permission_denied'])
        self.assertEqual(report['cleanup']['outcome'], 'deleted')
        self.assertFalse(report['retained'])
        self.assertEqual(report['capabilities']['desktop_guardian'], 'unverified')
        self.assertEqual([vm['uuid'] for vm in state['vms']], [TEMPLATE, EVERYDAY])
        self.assertEqual([vm['status'] for vm in state['vms']], ['stopped', 'started'])
        self.assertTrue(state['ownership_before_boot'])
        self.assertTrue(state['report_before_delete'])
        self.assertNotIn(report['clone']['uuid'], (TEMPLATE, EVERYDAY))

    def test_failed_clone_is_stopped_retained_and_listed_until_explicit_cleanup(self):
        self.change(mode='task_failed')
        result, report, state = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report['reason'], 'contradictory_guest_completion')
        self.assertTrue(report['retained'])
        self.assertEqual(state['vms'][-1]['status'], 'stopped')
        history = (self.runs / report['run'] / 'report.json').read_bytes()
        status, _, _ = self.invoke(command='status')
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertIn(report['run'], status.stdout)
        self.assertIn('failed', status.stdout)
        cleaned, _, state = self.invoke('--run', report['run'], command='cleanup')
        self.assertEqual(cleaned.returncode, 0, cleaned.stdout + cleaned.stderr)
        self.assertEqual(len(state['vms']), 2)
        self.assertEqual((self.runs / report['run'] / 'report.json').read_bytes(), history)
        status, _, _ = self.invoke(command='status')
        self.assertIn('deleted', status.stdout)

    def test_two_retained_failures_refuse_another_clone_with_concrete_cleanup(self):
        self.change(mode='task_failed')
        _, first, _ = self.invoke()
        _, second, _ = self.invoke()
        result, report, state = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report['reason'], 'retained_clone_limit')
        self.assertEqual(len(state['vms']), 4)
        self.assertIn('cleanup', result.stdout)
        self.assertIn('--run', result.stdout)
        self.assertTrue(any(run['run'] in result.stdout for run in (first, second)))
        cleaned, _, _ = self.invoke('--run', first['run'], command='cleanup')
        self.assertEqual(cleaned.returncode, 0, cleaned.stdout + cleaned.stderr)
        self.change(mode='success')
        result, report, state = self.invoke()
        self.assertEqual(result.returncode, 0, report)
        self.assertEqual(len(state['vms']), 3)
        self.assertNotEqual(first['clone']['uuid'], second['clone']['uuid'])

    def test_boot_and_session_readiness_are_awaited(self):
        self.change(mode='boot_session_delay')
        result, report, state = self.invoke()
        self.assertEqual(result.returncode, 0, report)
        self.assertTrue(state['boot_waited'])
        self.assertTrue(state['session_waited'])

    def test_misleading_completion_never_passes_and_retains_evidence(self):
        for mode in ('stale', 'missing', 'malformed', 'task_failed', 'running_task', 'wrong_engine',
                     'wrong_user', 'no_denial', 'outside_written', 'full_access', 'not_manageable',
                     'transport_secret', 'error_clixml', 'secrets', 'bad_native_reason',
                     'task_secret', 'candidate_mismatch', 'host_zero_no_result'):
            with self.subTest(mode=mode):
                self.change(mode=mode)
                result, report, state = self.invoke()
                self.assertNotEqual(result.returncode, 0, report)
                self.assertTrue(report['retained'])
                self.assertEqual(state['vms'][-1]['uuid'], report['clone']['uuid'])
                cleaned, _, _ = self.invoke('--run', report['run'], command='cleanup')
                self.assertEqual(cleaned.returncode, 0, cleaned.stdout + cleaned.stderr)

    def test_cleanup_failure_is_nonpassing_and_keeps_the_smoke_evidence(self):
        self.change(mode='delete_failure')
        result, report, state = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(report['retained'])
        self.assertTrue(report['native']['checks']['workspace_write_read'])
        self.assertEqual(report['stages'][-1]['stage'], 'cleanup')
        self.assertEqual(len(state['vms']), 3)

    def test_cleanup_refuses_wrong_targets_and_symlinked_ownership(self):
        self.change(mode='task_failed')
        _, report, _ = self.invoke()
        for target in (TEMPLATE, EVERYDAY, '../outside'):
            result, _, state = self.invoke('--run', target, command='cleanup')
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(len(state['vms']), 3)
        owner_path = self.runs / report['run'] / 'ownership.json'
        owner = json.loads(owner_path.read_text())
        original = owner_path.read_bytes()
        owner['clone']['uuid'] = EVERYDAY
        owner_path.write_text(json.dumps(owner))
        result, _, state = self.invoke('--run', report['run'], command='cleanup')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(state['vms']), 3)
        owner_path.unlink()
        outside = self.root / 'owner.json'
        outside.write_bytes(original)
        owner_path.symlink_to(outside)
        result, _, _ = self.invoke('--run', report['run'], command='cleanup')
        self.assertNotEqual(result.returncode, 0)

    def test_existing_lock_refuses_mutations_but_status_explains_it(self):
        self.runs.mkdir(mode=0o700)
        lock = self.runs / 'active.json'
        lock.write_text('{"pid": 999999, "operation": "run"}')
        result, _, state = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('active_or_abandoned_invocation', result.stderr)
        self.assertEqual(state['effects'], [])
        self.assertTrue(lock.exists())
        status, _, _ = self.invoke(command='status')
        self.assertTrue(json.loads(status.stdout)['locked'])

    def test_known_progress_is_recorded_and_newer_compatible_client_is_accepted(self):
        self.change(mode='progress', identity={'engine_version': '1.0.0', 'client_version': '27.1000.12345.0'})
        result, report, _ = self.invoke()
        self.assertEqual(result.returncode, 0, report)
        self.assertTrue(report['transport_progress_observed'])

    def test_guest_session_wait_has_a_deadline_and_retains_clone(self):
        self.change(mode='no_session')
        result, report, state = self.invoke('--timeout', '2')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report['stages'][-1]['stage'], 'guest_session')
        self.assertTrue(report['retained'])
        self.assertEqual(state['vms'][-1]['status'], 'stopped')

    def test_vm_commands_preserve_utms_case_sensitive_uuid_identity(self):
        state = json.loads(self.state.read_text())
        state['vms'][0]['uuid'] = TEMPLATE.upper()
        self.change(vms=state['vms'], mode='uppercase_uuid')
        result, report, _ = self.invoke()
        self.assertEqual(result.returncode, 0, report)
        self.assertEqual(report['template']['uuid'], TEMPLATE.upper())

    def test_unverified_clone_return_cannot_boot_or_delete_an_unrelated_vm(self):
        self.change(mode='wrong_clone_uuid')
        result, report, state = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report['reason'], 'unverified_clone_identity')
        self.assertFalse(any(effect['effect'] in ('start', 'stop', 'delete') for effect in state['effects']))
        self.assertTrue((self.runs / 'active.json').exists())
        self.assertTrue(report['ownership_unresolved'])
        again, _, state = self.invoke()
        self.assertNotEqual(again.returncode, 0)
        self.assertEqual(len(state['vms']), 3)

    def test_candidate_integrity_is_checked_before_creating_a_clone(self):
        result, report, state = self.invoke('--sha256', '0' * 64)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report['reason'], 'candidate_checksum_mismatch')
        self.assertEqual(state['effects'], [])
        self.candidate.write_bytes(b'not an ARM64 executable')
        result, report, state = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report['reason'], 'candidate_not_arm64')
        self.assertEqual(state['effects'], [])

    def test_utm_without_clone_stdout_requires_a_unique_new_inventory_identity(self):
        self.change(mode='empty_clone_stdout')
        result, report, _ = self.invoke()
        self.assertEqual(result.returncode, 0, report)
        self.assertEqual(report['clone_identity_source'], 'unique_inventory_delta')

    def test_failed_completion_report_includes_sanitized_task_diagnostics(self):
        self.change(mode='task_failed')
        result, report, _ = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report['completion']['last_result'], 1)
        self.assertEqual(report['completion']['state'], 'Ready')
        self.assertTrue(report['diagnostics']['guest_staging'].endswith(report['run']))

    def test_incomplete_task_records_guest_checkpoints_and_host_timings(self):
        self.change(mode='task_incomplete')
        result, report, state = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report['reason'], 'guest_task_incomplete')
        self.assertEqual(report['guest_progress']['checkpoints'][-1],
                         {'stage': 'package_discovered', 'elapsed_ms': 400})
        for stage in report['stages']:
            self.assertGreaterEqual(stage['elapsed_seconds'], 0)
        self.assertEqual(report['stages'][-1]['outcome'], 'failed')
        self.assertIn('stage_candidate', [step['step'] for step in report['transport_steps']])
        self.assertTrue(report['retained'])
        self.assertEqual(state['vms'][-1]['status'], 'stopped')

    def test_native_task_is_not_started_without_its_full_completion_budget(self):
        result, report, state = self.invoke('--timeout', '10')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report['reason'], 'insufficient_native_task_budget')
        self.assertFalse(any(effect['effect'] == 'limited_user_probe' for effect in state['effects']))
        self.assertTrue(report['retained'])
        self.assertEqual(state['vms'][-1]['status'], 'stopped')

    def test_transport_failure_collects_checkpoints_before_retaining_clone(self):
        self.change(mode='native_transport_failure')
        result, report, state = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report['reason'], 'vm_transport_failed')
        self.assertEqual(report['guest_progress']['outcome'], 'collected')
        self.assertEqual(report['transport_steps'][-1]['step'], 'native_task')
        self.assertEqual(report['transport_steps'][-1]['outcome'], 'failed')
        self.assertEqual(state['vms'][-1]['status'], 'stopped')

    def test_invalid_guest_checkpoints_fail_without_leaking_content(self):
        for mode in ('progress_secret', 'progress_stale', 'progress_negative'):
            with self.subTest(mode=mode):
                self.change(mode=mode)
                result, report, _ = self.invoke()
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(report['reason'], 'guest_progress_invalid')
                self.assertNotIn('checkpoints', report['guest_progress'])
                cleaned, _, _ = self.invoke('--run', report['run'], command='cleanup')
                self.assertEqual(cleaned.returncode, 0)

    def test_concurrent_run_is_refused_and_interruption_retains_the_owned_clone(self):
        self.change(mode='boot_hang')
        args = [sys.executable, str(SCRIPTS / 'windows_test_runner.py'), 'run',
                '--state-dir', str(self.runs), '--utmctl', str(self.utm), '--timeout', '10',
                '--template', TEMPLATE, '--dedicated-template', '--test-user', 'tofa-test',
                '--candidate', str(self.candidate), '--version', 'v0.0.1-rc.14',
                '--sha256', hashlib.sha256(self.candidate.read_bytes()).hexdigest(),
                '--candidate-commit', 'c' * 40]
        process = subprocess.Popen(args, env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        def finish():
            if process.poll() is None: process.kill()
            process.communicate(timeout=5)
        self.addCleanup(finish)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            reports = list(self.runs.glob('tofa-run-*/report.json'))
            if reports and json.loads(reports[0].read_text()).get('clone'): break
            time.sleep(.05)
        status, _, _ = self.invoke(command='status')
        self.assertEqual(json.loads(status.stdout)['runs'][0]['outcome'], 'running')
        result, _, state = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(state['vms']), 3)
        process.terminate()
        output, errors = process.communicate(timeout=15)
        self.assertNotEqual(process.returncode, 0, output + errors)
        report = json.loads(reports[0].read_text())
        self.assertEqual(report['reason'], 'interrupted')
        self.assertTrue(report['retained'])
        self.assertFalse((self.runs / 'active.json').exists())

    def test_missing_inventory_cannot_prove_successful_deletion(self):
        for mode in ('empty_inventory_after_delete', 'header_only_after_delete'):
            with self.subTest(mode=mode):
                self.change(mode=mode, delete_attempted=False)
                result, report, state = self.invoke()
                self.assertNotEqual(result.returncode, 0, report)
                self.assertTrue(report['retained'])
                self.assertEqual(report['stages'][-1]['stage'], 'cleanup')
                self.change(mode='success')
                cleaned, _, _ = self.invoke('--run', report['run'], command='cleanup')
                self.assertEqual(cleaned.returncode, 0)

    def test_candidate_transfer_preserves_integrity_with_compressed_staging(self):
        result, report, state = self.invoke()
        self.assertEqual(result.returncode, 0, report)
        self.assertEqual(state['candidate_transfer_sha256'], report['candidate']['sha256'])
        self.assertLess(state['candidate_transfer_size'], self.candidate.stat().st_size)


if __name__ == '__main__':
    unittest.main()
