"""Guardian qualification through the public operator CLI and external guest."""
import unittest

import windows_run_test as fixture


class GuardianTests(fixture.WindowsRunFixture):
    def test_bridge_observes_native_review_lifecycle_without_answering_it(self):
        self.change(mode='guardian_bridge')
        result, report, state = self.invoke('--suite', 'desktop-guardian', '--test-auth', 'native-session')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(report['guardian']['deny']['guardian']['decision'], 'denied')
        self.assertFalse(state['bridge_trial']['executed'])
        self.assertEqual(state['bridge_trial']['approval_responses'], 0)

    def test_live_review_suite_requires_both_decisions_and_clean_clone_deletion(self):
        result, report, state = self.invoke('--suite', 'desktop-guardian', '--test-auth', 'native-session')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(report['capabilities']['desktop_smoke'], 'verified')
        self.assertEqual(report['capabilities']['desktop_guardian'], 'verified')
        self.assertEqual(report['guardian']['allow']['guardian']['decision'], 'approved')
        self.assertEqual(report['guardian']['deny']['guardian']['decision'], 'denied')
        self.assertEqual(report['cleanup']['outcome'], 'deleted')
        self.assertEqual(len(state['vms']), 2)

    def test_missing_review_cannot_turn_a_marker_effect_into_guardian_approval(self):
        self.change(mode='guardian_missing_review')
        result, report, _ = self.invoke('--suite', 'desktop-guardian', '--test-auth', 'native-session')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report['reason'], 'guardian_review_missing')
        self.assertTrue(report['retained'])
        self.assertEqual(report['capabilities']['desktop_guardian'], 'unverified')

    def test_marker_mention_does_not_authorize_an_additional_command(self):
        self.change(mode='guardian_bridge_extra')
        result, report, _ = self.invoke('--suite', 'desktop-guardian', '--test-auth', 'native-session')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report['reason'], 'guardian_enforcement_failed')

    def test_native_shell_wrapper_preserves_the_exact_synthetic_script(self):
        self.change(mode='guardian_bridge_wrapped')
        result, report, _ = self.invoke('--suite', 'desktop-guardian', '--test-auth', 'native-session')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(report['guardian']['allow']['guardian']['synthetic_command'])

    def test_native_declined_item_with_successful_exit_cannot_prove_denial(self):
        self.change(mode='guardian_bridge_declined_success')
        result, report, _ = self.invoke('--suite', 'desktop-guardian', '--test-auth', 'native-session')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report['reason'], 'guardian_enforcement_failed')

    def test_guardian_requires_the_verified_native_shell_identity(self):
        self.change(mode='guardian_shell_missing')
        result, report, _ = self.invoke('--suite', 'desktop-guardian', '--test-auth', 'native-session')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report['reason'], 'desktop_identity_mismatch')

    def test_destructive_denial_candidate_requires_verified_absent_target_drive(self):
        self.change(mode='guardian_target_present')
        result, report, _ = self.invoke('--suite', 'desktop-guardian', '--test-auth', 'native-session')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report['reason'], 'guardian_target_unavailable')

    def test_denial_requires_native_decision_and_declined_execution_of_the_same_item(self):
        cases = {'acl_error': 'guardian_review_missing', 'review_timeout': 'guardian_decision_mismatch',
                 'unexpected_allow': 'guardian_decision_mismatch', 'wrong_item': 'guardian_review_mismatch',
                 'deny_effect': 'guardian_enforcement_failed', 'failed_command': 'guardian_enforcement_failed'}
        for mode, reason in cases.items():
            with self.subTest(mode=mode):
                self.change(mode='guardian_' + mode)
                result, report, _ = self.invoke('--suite', 'desktop-guardian', '--test-auth', 'native-session')
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(report['reason'], reason)
                self.assertEqual(report['stages'][-1]['stage'], 'guardian_deny')
                self.assertTrue(report['retained'])
                self.assertEqual(self.invoke('--run', report['run'], command='cleanup')[0].returncode, 0)


if __name__ == '__main__':
    unittest.main()
