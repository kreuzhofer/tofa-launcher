"""Exercise the operator CLI through a controlled external UTM boundary."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parent
TEMPLATE = 'aaaaaaaa-1111-4111-8111-111111111111'
EVERYDAY = 'bbbbbbbb-2222-4222-8222-222222222222'


@unittest.skipIf(os.name == 'nt', 'UTM host fixtures require Unix executables')
class TemplateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='tofa template ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.report = self.root / 'report.json'
        self.utm = self.root / 'utmctl'
        self.utm.write_text('#!' + sys.executable + '\n' + (SCRIPTS / 'fixtures/windows_template_utm.py').read_text())
        self.utm.chmod(0o700)
        self.state = self.root / 'state.json'
        self.state.write_text(json.dumps({'vms': [
            {'uuid': TEMPLATE, 'status': 'started', 'name': 'Dedicated template'},
            {'uuid': EVERYDAY, 'status': 'started', 'name': 'Everyday Windows'},
        ], 'effects': [], 'mode': 'success'}))
        self.env = {**os.environ, 'TEMPLATE_FIXTURE_STATE': str(self.state)}

    def change(self, **values):
        state = json.loads(self.state.read_text())
        state.update(values)
        self.state.write_text(json.dumps(state))

    def invoke(self, *extra, operation='prepare', template=TEMPLATE):
        result = subprocess.run([sys.executable, str(SCRIPTS / 'windows_test_runner.py'),
            'template', operation, '--template', template, '--dedicated-template',
            '--test-user', 'test-machine\\tofa-test', '--test-auth', 'none',
            '--utmctl', str(self.utm), '--output', str(self.report), *extra],
            env=self.env, capture_output=True, text=True, timeout=15)
        self.assertTrue(self.report.exists(), result.stdout + result.stderr)
        report = json.loads(self.report.read_text())
        for secret in ('PRIVATE_KEY', 'UNRELATED_CONTENT'):
            self.assertNotIn(secret, self.report.read_text() + result.stdout + result.stderr)
        return result, report, json.loads(self.state.read_text())

    def test_ambiguous_template_fails_without_guest_changes(self):
        state = json.loads(self.state.read_text())
        self.change(vms=state['vms'] + [state['vms'][0]])
        result, report, state = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report['reason'], 'ambiguous_template')
        self.assertEqual(state['effects'], [])
        self.assertEqual(report['capabilities']['desktop_guardian'], 'unverified')

    def test_missing_session_reports_bootstrap_without_provisioning(self):
        self.change(mode='no_session')
        result, report, state = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report['outcome'], 'bootstrap_required')
        self.assertEqual(report['reason'], 'test_user_sign_in_required')
        self.assertTrue(report['bootstrap'])
        self.assertEqual(state['effects'], [])
        self.assertIn('SYSTEM-protected diagnostic staging directory and fresh prerequisite report', report['changes'])
        self.assertTrue(report['diagnostics']['guest_staging'].endswith(report['run']))

    def test_native_readiness_is_measured_without_claiming_desktop_support(self):
        result, report, state = self.invoke()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(report['outcome'], 'native_ready')
        self.assertEqual(report['capabilities']['native_sandbox'], 'verified')
        self.assertEqual(report['capabilities']['desktop_guardian'], 'unverified')
        self.assertEqual(report['capabilities']['test_authentication'], 'unverified')
        self.assertEqual(report['authentication_choice'], 'none')
        self.assertTrue(report['native']['checks']['workspace_write_read'])
        self.assertTrue(report['native']['checks']['outside_permission_denied'])
        self.assertFalse(report['native']['checks']['outside_marker_exists'])
        self.assertEqual(report['native']['identity']['engine_version'], '0.159.2')
        self.assertTrue(state['effects'])
        self.assertTrue(all(effect['vm'] == TEMPLATE for effect in state['effects']))
        self.assertEqual([vm['status'] for vm in state['vms']], ['started', 'started'])

    def test_existing_report_is_preserved_before_any_guest_changes(self):
        self.report.write_text('{"earlier_attempt": "failed"}')
        result, report, state = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report, {'earlier_attempt': 'failed'})
        self.assertEqual(state['effects'], [])

    def test_unsupported_guest_fails_before_provisioning(self):
        self.change(mode='unsupported_guest')
        result, report, state = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report['reason'], 'unsupported_guest')
        self.assertEqual(state['effects'], [])

    def test_delayed_guest_result_is_awaited(self):
        self.change(mode='delayed')
        result, report, state = self.invoke()
        self.assertEqual(result.returncode, 0, report)

    def test_delayed_task_directory_is_awaited(self):
        self.change(mode='delayed_task')
        result, report, state = self.invoke()
        self.assertEqual(result.returncode, 0, report)

    def test_guest_content_is_not_exported_as_identity(self):
        self.change(mode='secrets')
        result, report, state = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report['reason'], 'malformed_guest_result')

    def test_prepare_registers_existing_native_installation_for_test_user(self):
        self.change(mode='register_client')
        result, report, state = self.invoke()
        self.assertEqual(result.returncode, 0, report)
        self.assertIn({'vm': TEMPLATE, 'effect': 'registered_test_user_client'}, state['effects'])
        self.assertIn('Register installed Codex package for the designated test user', report['changes'])

    def test_bad_native_evidence_never_passes(self):
        for mode in ('stale', 'missing', 'malformed', 'task_failed', 'wrong_engine', 'wrong_user',
                     'no_denial', 'outside_written', 'full_access', 'not_manageable', 'transport_secret', 'error_clixml'):
            with self.subTest(mode=mode):
                self.change(mode=mode)
                result, report, state = self.invoke()
                self.assertNotEqual(result.returncode, 0)
                self.assertNotEqual(report['capabilities']['native_sandbox'], 'verified')
                self.report.unlink()

    def test_ownership_regression_remains_a_readiness_failure(self):
        result, report, state = self.invoke('--workspace-fixture', 'acl-unmanageable')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report['reason'], 'native_workspace_acl_failed')
        self.assertTrue(report['native']['checks']['ordinary_write'])
        self.assertFalse(report['native']['checks']['workspace_acl_manageable'])

    def test_status_reports_missing_registration_without_installing(self):
        self.change(mode='register_client')
        result, report, state = self.invoke(operation='status')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report['outcome'], 'missing_prerequisites')
        self.assertEqual(state['effects'], [])

    def test_native_consent_is_a_bootstrap_requirement(self):
        self.change(mode='consent')
        result, report, state = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report['outcome'], 'bootstrap_required')
        self.assertTrue(report['bootstrap'])

    def test_progress_only_clixml_still_requires_native_evidence(self):
        self.change(mode='progress')
        result, report, state = self.invoke()
        self.assertEqual(result.returncode, 0, report)
        self.assertTrue(report['transport_progress_observed'])

    def test_versions_accept_updates_and_reject_invalid_or_old_clients(self):
        for version, expected in [('0.155.0-alpha.16.4', 0), ('0.155.0-alpha.16.10', 0),
                                  ('1.0.0', 0), ('0.155.0-alpha.16.3', 1), ('0.154.0', 1),
                                  ('0.159.2junk', 1), ('1.0.0-alpha..1', 1), ('1.0.0-01', 1)]:
            with self.subTest(version=version):
                self.change(identity={'engine_version': version})
                result, report, state = self.invoke()
                self.report.unlink()
                self.assertEqual(result.returncode, expected, report)

    def test_completion_fields_cannot_leak_guest_content(self):
        self.change(mode='task_secret')
        result, report, state = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report['reason'], 'malformed_guest_result')

    def test_explicit_native_setup_prepares_sandbox_before_measuring(self):
        self.change(mode='needs_setup')
        result, report, state = self.invoke('--initialize-sandbox')
        self.assertEqual(result.returncode, 0, report)
        self.assertIn({'vm': TEMPLATE, 'effect': 'native_sandbox_setup_requested'}, state['effects'])
        self.assertEqual(state['probe_window_style'], 'Normal')
        self.assertIn('Watch the designated VM', result.stdout)
        self.assertIn('60 seconds', result.stdout)

    def test_malformed_prerequisites_produce_a_durable_failure_before_staging(self):
        for mode in ('bad_sid', 'missing_python', 'unsafe_python', 'bad_reason'):
            with self.subTest(mode=mode):
                self.change(mode=mode)
                result, report, state = self.invoke()
                self.report.unlink()
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(report['reason'], 'malformed_guest_result')
                self.assertEqual(state['effects'], [])

    def test_executable_harness_is_staged_in_a_protected_directory(self):
        self.change(mode='protected_staging')
        result, report, state = self.invoke()
        self.assertEqual(result.returncode, 0, report)
        self.assertTrue(report['native']['checks']['harness_read_only'])

    def test_malformed_native_failure_reason_is_reported(self):
        self.change(mode='bad_native_reason')
        result, report, state = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report['reason'], 'malformed_guest_result')

    def test_stopped_template_is_not_started(self):
        state = json.loads(self.state.read_text())
        state['vms'][0]['status'] = 'stopped'
        self.change(vms=state['vms'])
        result, report, state = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report['reason'], 'template_must_be_started_for_preparation')
        self.assertEqual(state['vms'][0]['status'], 'stopped')
        self.assertEqual(state['effects'], [])

    def test_unknown_uuid_and_display_names_are_rejected(self):
        for identity in ('Dedicated template', 'cccccccc-3333-4333-8333-333333333333'):
            with self.subTest(identity=identity):
                result, report, state = self.invoke(template=identity)
                self.report.unlink()
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(state['effects'], [])

    def test_status_cannot_request_sandbox_setup(self):
        result, report, state = self.invoke('--initialize-sandbox', operation='status')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report['reason'], 'sandbox_initialization_requires_prepare')
        self.assertEqual(state['effects'], [])

    def test_requested_setup_must_have_a_completion_notification(self):
        self.change(mode='missing_setup_completion')
        result, report, state = self.invoke('--initialize-sandbox')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report['reason'], 'native_setup_incomplete')

    def test_inventory_cannot_export_unrelated_content(self):
        self.change(mode='inventory_secret')
        result, report, state = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(state['effects'], [])


if __name__ == '__main__':
    unittest.main()
