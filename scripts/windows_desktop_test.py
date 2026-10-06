"""Desktop qualification through the operator CLI and external VM boundary."""
import os
import json
import unittest

import windows_run_test as fixture


@unittest.skipIf(os.name == 'nt', 'Mac operator CLI requires Unix executable fixtures')
class DesktopTests(fixture.WindowsRunFixture):
    def test_control_failure_retains_only_bounded_diagnostic_fields(self):
        self.change(mode='desktop_control_details')
        result, report, _ = self.invoke('--suite', 'desktop-smoke', '--test-auth', 'native-session')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report['reason'], 'desktop_control_unsupported')
        self.assertEqual(report['desktop'].get('control_failure'),
                         {'action': 'configure', 'stage': 'search', 'error': 'stale_element'})
        self.assertNotIn('PRIVATE_KEY', json.dumps(report))
        self.assertTrue(report['retained'])

    def test_invalid_control_diagnostics_fail_without_exposing_external_content(self):
        self.change(mode='desktop_control_invalid')
        result, report, _ = self.invoke('--suite', 'desktop-smoke', '--test-auth', 'native-session')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report['reason'], 'malformed_desktop_result')
        self.assertNotIn('PRIVATE_KEY', json.dumps(report))

    def test_desktop_tool_environment_batch_preserves_shared_cli_settings(self):
        self.change(mode='desktop_bridge_environment_settings')
        result, report, state = self.invoke('--suite', 'desktop-smoke', '--test-auth', 'native-session')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(state['bridge_trial']['settings_unchanged'])
        self.assertTrue(state['bridge_trial']['settings_rejected'])
        self.assertEqual(report['desktop'].get('restrictions', {}).get('tool_registration_writes_refused'), 1)

    def test_desktop_composer_trailing_newline_preserves_the_exact_synthetic_task(self):
        self.change(mode='desktop_bridge_whitespace')
        result, report, state = self.invoke('--suite', 'desktop-smoke', '--test-auth', 'native-session')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(state['bridge_trial'], {'refused': False, 'executed': True, 'exit_code': 0})

    def test_unrelated_background_turn_is_blocked_without_invalidating_the_authorized_task(self):
        self.change(mode='desktop_bridge_background')
        result, report, state = self.invoke('--suite', 'desktop-smoke', '--test-auth', 'native-session')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(state['bridge_trial'], {'refused': False, 'executed': True, 'exit_code': 0, 'background_blocked': True})

    def test_unknown_write_after_successful_command_cannot_pass_final_policy_audit(self):
        self.change(mode='desktop_bridge_late_write')
        result, report, state = self.invoke('--suite', 'desktop-smoke', '--test-auth', 'native-session')
        self.assertTrue(state['bridge_trial']['executed'])
        self.assertTrue(state['bridge_trial']['late_write_refused'])
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(report['retained'])

    def test_builtin_local_environment_is_limited_to_the_owned_workspace(self):
        self.change(mode='desktop_bridge_local_environment')
        result, report, state = self.invoke('--suite', 'desktop-smoke', '--test-auth', 'native-session')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(state['bridge_trial'], {'refused': False, 'executed': True, 'exit_code': 0})

    def test_native_thread_visualization_root_stays_scoped_to_the_verified_thread(self):
        self.change(mode='desktop_bridge_visualization')
        result, report, state = self.invoke('--suite', 'desktop-smoke', '--test-auth', 'native-session')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(state['bridge_trial'], {'refused': False, 'executed': True, 'exit_code': 0, 'visualization_roots': 1})
        self.assertEqual(report['desktop']['restrictions']['native_visualization_roots'], 1)

    def test_visualization_scope_rejects_unrelated_shared_redirected_and_wrong_owner_directories(self):
        for suffix in ('other_thread', 'shared', 'reparse', 'owner_wrong'):
            with self.subTest(suffix=suffix):
                self.change(mode='desktop_bridge_visualization_' + suffix)
                result, report, state = self.invoke('--suite', 'desktop-smoke', '--test-auth', 'native-session')
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(state['bridge_trial']['executed'])
                self.assertTrue(state['bridge_trial']['refused'])
                self.assertEqual(self.invoke('--run', report['run'], command='cleanup')[0].returncode, 0)

    def test_desktop_selected_catalog_model_requires_native_effective_identity(self):
        self.change(mode='desktop_bridge_catalog_model')
        result, report, state = self.invoke('--suite', 'desktop-smoke', '--test-auth', 'native-session')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(state['bridge_trial']['executed'])
        self.assertEqual(state['bridge_trial']['model_observed'], 'gpt-5.5')
        self.assertEqual(report['desktop']['identity']['model'], 'gpt-5.5')

    def test_native_model_reroute_cannot_qualify_the_original_model_identity(self):
        self.change(mode='desktop_bridge_rerouted')
        result, report, state = self.invoke('--suite', 'desktop-smoke', '--test-auth', 'native-session')
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(report['retained'])
        self.assertFalse(state['bridge_trial']['policy_preserved'])

    def test_native_canonical_sandbox_keeps_the_cwd_implicit(self):
        self.change(mode='desktop_bridge_visualization_canonical')
        result, report, state = self.invoke('--suite', 'desktop-smoke', '--test-auth', 'native-session')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(state['bridge_trial']['policy_preserved'])
        self.assertEqual(report['desktop']['restrictions']['native_visualization_roots'], 1)

    def test_native_guardian_reviewer_alias_preserves_verified_automatic_review(self):
        self.change(mode='desktop_bridge_reviewer_alias')
        result, report, state = self.invoke('--suite', 'desktop-smoke', '--test-auth', 'native-session')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(state['bridge_trial'], {'refused': False, 'executed': True, 'exit_code': 0})
        self.assertEqual(report['desktop']['identity']['reviewer'], 'auto_review')

    def test_desktop_pass_requires_automated_permission_control_confirmation(self):
        self.change(mode='desktop_permissions_unverified')
        result, report, _ = self.invoke('--suite', 'desktop-smoke', '--test-auth', 'native-session')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report['reason'], 'desktop_assertion_failed')

    def test_desktop_tool_registration_does_not_write_shared_cli_settings(self):
        self.change(mode='desktop_bridge_settings')
        result, report, state = self.invoke('--suite', 'desktop-smoke', '--test-auth', 'native-session')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(state['bridge_trial']['settings_unchanged'])
        self.assertTrue(state['bridge_trial']['settings_rejected'])
        self.assertEqual(report['desktop'].get('restrictions', {}).get('tool_registration_writes_refused'), 1)
        self.assertTrue(report['desktop']['checks']['cli_defaults_unchanged'])

    def test_unsupported_permission_write_is_refused_before_shared_settings_change(self):
        self.change(mode='desktop_bridge_permission_write')
        result, report, state = self.invoke('--suite', 'desktop-smoke', '--test-auth', 'native-session')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report['reason'], 'desktop_policy_mismatch')
        self.assertEqual(state['bridge_trial'], {'refused': True, 'executed': False, 'exit_code': 0,
                                                'settings_unchanged': True})

    def test_failed_native_readiness_prevents_desktop_trials(self):
        self.change(mode='task_failed')
        result, report, state = self.invoke('--suite', 'desktop-smoke', '--test-auth', 'native-session')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report.get('reason'), 'contradictory_guest_completion')
        self.assertFalse(any(effect['effect'] == 'desktop_started' for effect in state['effects']))
        self.assertTrue(report['retained'])

    def test_missing_desktop_authentication_is_a_setup_failure_before_trials(self):
        self.change(mode='desktop_auth_missing')
        result, report, state = self.invoke('--suite', 'desktop-smoke', '--test-auth', 'native-session')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report.get('reason'), 'desktop_authentication_required')
        self.assertEqual(report['stages'][-1]['stage'], 'desktop_smoke')
        self.assertTrue(report['native']['checks']['workspace_write_read'])
        self.assertFalse(any(effect['effect'] == 'desktop_started' for effect in state['effects']))

    def test_desktop_pass_requires_real_bridge_command_and_clean_shutdown(self):
        result, report, state = self.invoke('--suite', 'desktop-smoke', '--test-auth', 'native-session')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(report['desktop']['route'], 'native-desktop-bridge')
        self.assertTrue(report['desktop']['checks']['command_effect'])
        self.assertTrue(report['desktop']['checks']['normal_quit'])
        self.assertTrue(report['desktop']['checks']['owned_children_exited'])
        for field in ('app_pid', 'bridge_pid', 'engine_pid'):
            self.assertGreater(report['desktop']['identity'][field], 0)
        self.assertEqual(len(report['desktop']['identity']['bridge_sha256']), 64)
        self.assertEqual(report['capabilities']['desktop_smoke'], 'verified')
        self.assertEqual(report['capabilities']['desktop_guardian'], 'unverified')
        self.assertEqual(len(state['vms']), 2)

    def test_desktop_requires_explicit_test_authentication_choice(self):
        result, report, state = self.invoke('--suite', 'desktop-smoke')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report.get('reason'), 'explicit_test_authentication_required')
        self.assertEqual(state['effects'], [])

    def test_unrelated_desktop_instance_is_refused_without_adoption_or_termination(self):
        self.change(mode='desktop_busy')
        result, report, state = self.invoke('--suite', 'desktop-smoke', '--test-auth', 'native-session')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report.get('reason'), 'native_client_busy')
        self.assertFalse(any(effect['effect'] == 'desktop_started' for effect in state['effects']))
        self.assertTrue(report['retained'])

    def test_desktop_policy_identity_effect_and_cleanup_failures_cannot_pass(self):
        for mode in ('desktop_untrusted', 'desktop_wrong_policy', 'desktop_wrong_identity',
                     'desktop_no_effect', 'desktop_cleanup_failed', 'desktop_secret'):
            with self.subTest(mode=mode):
                self.change(mode=mode)
                result, report, _ = self.invoke('--suite', 'desktop-smoke', '--test-auth', 'native-session')
                self.assertNotEqual(result.returncode, 0)
                self.assertTrue(report['retained'])
                self.assertEqual(report['capabilities']['desktop_guardian'], 'unverified')
                self.assertNotEqual(report['capabilities'].get('desktop_smoke'), 'verified')
                cleaned, _, _ = self.invoke('--run', report['run'], command='cleanup')
                self.assertEqual(cleaned.returncode, 0)

    def test_completion_from_another_turn_cannot_qualify_the_desktop_command(self):
        self.change(mode='desktop_mixed_completion')
        result, report, _ = self.invoke('--suite', 'desktop-smoke', '--test-auth', 'native-session')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report['reason'], 'desktop_execution_mismatch')
        self.assertTrue(report['retained'])

    def test_failed_desktop_diagnostics_cannot_pass_even_after_clean_quit(self):
        self.change(mode='desktop_diagnostics_failed')
        result, report, state = self.invoke('--suite', 'desktop-smoke', '--test-auth', 'native-session')
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(report['desktop']['checks']['normal_quit'])
        self.assertTrue(report['desktop']['checks']['owned_children_exited'])
        self.assertTrue(report['retained'])
        self.assertEqual(state['vms'][-1]['status'], 'stopped')

    def test_actual_bridge_refuses_full_access_before_native_execution(self):
        self.change(mode='desktop_bridge_unsafe')
        result, report, state = self.invoke('--suite', 'desktop-smoke', '--test-auth', 'native-session')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report['reason'], 'desktop_policy_mismatch')
        self.assertEqual(state['bridge_trial'], {'refused': True, 'executed': False, 'exit_code': 0})

    def test_actual_bridge_forwards_the_authorized_workspace_turn(self):
        self.change(mode='desktop_bridge_safe')
        result, report, state = self.invoke('--suite', 'desktop-smoke', '--test-auth', 'native-session')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(state['bridge_trial'], {'refused': False, 'executed': True, 'exit_code': 0})

    def test_bridge_refuses_policy_and_identity_overrides_before_execution(self):
        for mode in ('desktop_bridge_network', 'desktop_bridge_model', 'desktop_bridge_roots', 'desktop_bridge_environment'):
            with self.subTest(mode=mode):
                self.change(mode=mode)
                result, report, state = self.invoke('--suite', 'desktop-smoke', '--test-auth', 'native-session')
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(report['reason'], 'desktop_policy_mismatch')
                self.assertEqual(state['bridge_trial'], {'refused': True, 'executed': False, 'exit_code': 0})
                self.assertEqual(self.invoke('--run', report['run'], command='cleanup')[0].returncode, 0)

    def test_interrupted_desktop_collects_its_own_run_diagnostics_before_shutdown(self):
        self.change(mode='crash_during_desktop')
        result, report, _ = self.invoke('--suite', 'desktop-smoke', '--test-auth', 'native-session')
        self.assertNotEqual(result.returncode, 0)
        recovered, report, state = self.invoke(command='recover')
        self.assertEqual(recovered.returncode, 0, recovered.stderr)
        self.assertEqual(report['reason'], 'runner_abandoned')
        self.assertEqual(json.loads(recovered.stdout)['diagnostics']['files']['desktop_progress']['outcome'], 'collected')
        self.assertEqual(state['vms'][-1]['status'], 'stopped')


if __name__ == '__main__':
    unittest.main()
