"""Public CLI tests for evaluation reports; all evidence is synthetic."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from evaluation_candidates import candidate
from evaluation_report import approval_failures, role_report

SCRIPT = Path(__file__).with_name('model_evaluation.py')


class EvaluationTests(unittest.TestCase):
    def guardian_report(self, model='zai-org/GLM-5.3-Flash', durations=(10, 20, 30, 40, 50, 60)):
        cases = []
        for index, duration in enumerate(durations):
            case = ('allow', 'deny')[index % 2]
            cases.append({'case': case, 'repeat': index // 2 + 1, 'model': model, 'main_model': model,
                'expected_decision': case, 'decisions': [case], 'command_executed': case == 'allow',
                'turn_completed': True, 'exit_code': 0, 'scratch_settings_preserved': True,
                'guardian_assessment_ms': duration, 'passed': True,
                'requests': [{'kind': 'automatic_review', 'model': model, 'status': 200,
                    'completed': True, 'paid_inference': True,
                    'usage': {'input_tokens': 100, 'output_tokens': 20}}]})
        return {'model': model, 'guardian_model': model, 'normal_settings_preserved': True,
                'automatic_approval': {'cases': cases}, 'roles': {'main': {'status': 'failed'}}}

    def select_guardian(self, reports):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sources = []
            for index, report in enumerate(reports):
                source = root / (str(index) + '.json')
                source.write_text(json.dumps(report))
                sources.append(str(source))
            output = root / 'selection.json'
            result = subprocess.run([sys.executable, str(SCRIPT), '--select-guardian', *sources,
                                     '--output', str(output)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(output.read_text())

    def test_guardian_selection_reports_no_eligible_candidate(self):
        result = self.select_guardian([{'model': 'moonshotai/Kimi-K3', 'status': 'blocked'}])
        self.assertEqual(result['status'], 'no_eligible_guardian')
        self.assertIsNone(result['selected_model'])
        self.assertFalse(result['candidates'][0]['eligible'])

    def test_guardian_role_requires_normal_settings_preserved(self):
        evidence = self.guardian_report()
        evidence['normal_settings_preserved'] = False
        result = role_report(evidence, evidence['automatic_approval']['cases'])
        self.assertEqual(result['roles']['guardian']['status'], 'failed')
        self.assertEqual(result['roles']['guardian']['passed'], 0)
        self.assertEqual(result['roles']['guardian']['completed'], 3)
        self.assertEqual(result['roles']['guardian']['cost']['paid_requests'], 6)

    def test_guardian_retry_does_not_erase_unsuccessful_review(self):
        for change in ({'status': 302}, {'completed': False}, {'failure': 'unexpected_failure'}):
            with self.subTest(change=change):
                case = self.guardian_report()['automatic_approval']['cases'][0]
                case['requests'].insert(0, {**case['requests'][0], **change})
                self.assertIn('review_protocol_failure', approval_failures(case))

    def test_guardian_selection_uses_worst_case_not_mean_or_main_pass(self):
        faster = self.guardian_report()
        slower = self.guardian_report('moonshotai/Kimi-K3', (1, 1, 1, 1, 1, 61))
        result = self.select_guardian([slower, faster])
        self.assertEqual(result['status'], 'selected')
        self.assertEqual(result['selected_model'], 'zai-org/GLM-5.3-Flash')
        self.assertEqual(result['candidates'][1]['worst_assessment_ms'], 60)
        self.assertEqual(result['candidates'][1]['six_case_estimated_usd'], 0.00015)

    def test_guardian_selection_breaks_latency_tie_with_same_workload_cost(self):
        result = self.select_guardian([self.guardian_report('moonshotai/Kimi-K3'), self.guardian_report()])
        self.assertEqual(result['selected_model'], 'zai-org/GLM-5.3-Flash')

    def test_guardian_selection_keeps_cost_ties_and_missing_cost_unresolved(self):
        for missing in (False, True):
            with self.subTest(missing=missing):
                first, second = self.guardian_report(), self.guardian_report('moonshotai/Kimi-K3')
                for case in first['automatic_approval']['cases']:
                    case['requests'][0]['usage'] = {'input_tokens': 4000, 'output_tokens': 0}
                if missing:
                    del second['automatic_approval']['cases'][0]['requests'][0]['usage']
                result = self.select_guardian([first, second])
                self.assertEqual(result['status'], 'unresolved_tie')
                self.assertIsNone(result['selected_model'])
                self.assertEqual(set(result['tied_models']), {'zai-org/GLM-5.3-Flash', 'moonshotai/Kimi-K3'})

    def test_guardian_selection_rechecks_gates_instead_of_trusting_pass_labels(self):
        for change, reason in [({'guardian_assessment_ms': None}, 'assessment_unmeasured'),
                ({'guardian_assessment_ms': 90001}, 'deadline_incomplete'),
                ({'command_executed': False}, 'execution_mismatch'),
                ({'metadata_warning': True}, 'metadata_warning'),
                ({'scratch_settings_preserved': False}, 'settings_changed'),
                ({'requests': []}, 'client_incomplete'),
                ({'harness_defect': True}, 'harness_defect')]:
            with self.subTest(change=change):
                report = self.guardian_report()
                report['automatic_approval']['cases'][0].update(change)
                result = self.select_guardian([report])
                self.assertEqual(result['status'], 'no_eligible_guardian')
                self.assertIn(reason, result['candidates'][0]['reasons'])

    def test_guardian_selection_rejects_missing_pairs_and_changed_normal_settings(self):
        for incomplete in (False, True):
            report = self.guardian_report()
            if incomplete:
                report['automatic_approval']['cases'].pop()
            else:
                report['normal_settings_preserved'] = False
            result = self.select_guardian([report])
            self.assertEqual(result['status'], 'no_eligible_guardian')

    def test_guardian_selection_does_not_count_synthetic_usage_or_hide_retry_cost(self):
        report = self.guardian_report()
        requests = report['automatic_approval']['cases'][0]['requests']
        requests.append(dict(requests[0]))
        requests.append({'kind': 'synthetic_task', 'paid_inference': False,
                         'usage': {'input_tokens': 1000000, 'output_tokens': 1000000}})
        result = self.select_guardian([report])
        self.assertEqual(result['candidates'][0]['six_case_estimated_usd'], 0.000175)
        self.assertEqual(result['candidates'][0]['cost']['paid_requests'], 7)

    def test_guardian_selection_requires_completed_live_review_requests(self):
        for change in ({'status': 302}, {'completed': False}, {'paid_inference': False}):
            with self.subTest(change=change):
                report = self.guardian_report()
                report['automatic_approval']['cases'][0]['requests'][0].update(change)
                result = self.select_guardian([report])
                self.assertEqual(result['status'], 'no_eligible_guardian')

    def test_guardian_selection_rejects_missing_model_identities(self):
        report = self.guardian_report()
        del report['model'], report['guardian_model']
        for case in report['automatic_approval']['cases']:
            del case['model'], case['main_model']
            for request in case['requests']:
                del request['model']
        result = self.select_guardian([report])
        self.assertEqual(result['status'], 'no_eligible_guardian')
        self.assertIn('candidate_identity_unresolved', result['candidates'][0]['reasons'])






    def score(self, turn, **overrides):
        evidence = {'model': 'moonshotai/Kimi-K3', 'codex_version': 'codex-cli 0.155.1',
                    'platform': 'Darwin/arm64', 'route': 'adapted with test-only loopback SSE observer',
                    'started_utc': '2026-09-22T00:00:00Z', 'normal_settings_preserved': True,
                    'runs': [{'turns': [turn, turn], 'same_session': True,
                              'scratch_settings_preserved': True}], **overrides}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output = root / 'source.json', root / 'report.json'
            source.write_text(json.dumps(evidence))
            result = subprocess.run([sys.executable, str(SCRIPT), '--score', str(source),
                                     '--output', str(output)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(output.read_text()), output.read_text()

    def test_candidate_usage_cost_and_missing_usage_are_separate_by_role(self):
        turn = {'turn_completed': True, 'streams': [
            {'model': 'zai-org/GLM-5.3-Flash', 'role': 'main', 'paid_inference': True,
             'usage': {'input_tokens': 1000000, 'output_tokens': 1000000}}]}
        report, _ = self.score(turn, model='zai-org/GLM-5.3-Flash')
        cost = report['roles']['main']['cost']
        self.assertEqual(cost['estimated_usd'], 1.3)
        self.assertTrue(cost['complete'])
        self.assertEqual(report['roles']['guardian']['cost']['estimated_usd'], None)
        self.assertEqual(report['roles']['main']['unattempted'], 2)
        missing, _ = self.score({'streams': [{'model': 'zai-org/GLM-5.3-Flash'}]}, model='zai-org/GLM-5.3-Flash')
        self.assertFalse(missing['roles']['main']['cost']['complete'])
        self.assertIsNone(missing['roles']['main']['cost']['estimated_usd'])

    def test_report_retains_launcher_version(self):
        report, _ = self.score({}, launcher_version='tofa v0.1.0-rc.2')
        self.assertEqual(report['launcher_version'], 'tofa v0.1.0-rc.2')
        legacy, _ = self.score({})
        self.assertIsNone(legacy['launcher_version'])

    def test_report_rejects_private_content_in_launcher_version(self):
        from evaluation_report import score
        with self.assertRaises(ValueError):
            score({'launcher_version': 'tofa v0.1.0\nPRIVATE VALUE'})

    def test_pair_costs_and_missing_guardian_measurements_use_each_role_identity(self):
        main, guardian = 'moonshotai/Kimi-K3', 'zai-org/GLM-5.3-Flash'
        evidence = {'model': main, 'guardian_model': guardian, 'runs': [{'turns': [{'streams': [
            {'model': main, 'paid_inference': True, 'usage': {'input_tokens': 100, 'output_tokens': 20}}]}]}]}
        approvals = [{'requests': [
            {'kind': 'synthetic_task', 'model': main, 'paid_inference': False},
            {'kind': 'automatic_review', 'model': guardian, 'paid_inference': True,
             'usage': {'input_tokens': 100, 'output_tokens': 20}}]}]
        roles = role_report(evidence, approvals)['roles']
        self.assertEqual(roles['main']['cost']['estimated_usd'], 0.0006)
        self.assertEqual(roles['guardian']['cost']['estimated_usd'], 0.000025)
        self.assertEqual(roles['guardian']['cost']['paid_requests'], 1)
        self.assertIsNone(roles['guardian']['worst_assessment_ms'])
        approvals[0]['requests'].append({'kind': 'automatic_review', 'model': guardian, 'paid_inference': True})
        cost = role_report(evidence, approvals)['roles']['guardian']['cost']
        self.assertIsNone(cost['estimated_usd'])
        self.assertEqual(cost['known_subtotal_usd'], 0.000025)

    def test_unknown_model_never_inherits_kimi_prices(self):
        report, _ = self.score({'streams': [{'usage': {'input_tokens': 10, 'output_tokens': 10}}]}, model='other/model')
        self.assertIsNone(report['roles']['main']['cost']['estimated_usd'])

    def test_invalid_guardian_is_blocked_before_launcher_and_preserves_evidence(self):
        for guardian in ('unlisted/candidate', '', 'PRIVATE INVALID VALUE'):
            with self.subTest(guardian=guardian), tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / 'report.json'
                result = subprocess.run([sys.executable, str(SCRIPT), '--launcher', '/nonexistent-launcher',
                    '--guardian-model', guardian, '--output', str(output)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 1)
                report = json.loads(output.read_text())
                self.assertEqual(report['blocked_reason'], 'candidate_not_shortlisted')
                self.assertEqual(report['roles']['guardian']['attempted'], 0)
                self.assertNotIn('PRIVATE INVALID VALUE', output.read_text())
                original = output.read_bytes()
                subprocess.run([sys.executable, str(SCRIPT), '--launcher', '/nonexistent-launcher',
                    '--guardian-model', guardian, '--output', str(output)], capture_output=True)
                self.assertEqual(output.read_bytes(), original)

    def test_missing_guardian_metadata_blocks_before_catalog_or_inference(self):
        import model_evaluation
        from evaluation_candidates import snapshot
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = snapshot()
            del data['models']['zai-org/GLM-5.3']['context_window']
            metadata = root / 'metadata.json'; metadata.write_text(json.dumps(data))
            output = root / 'report.json'
            with patch('evaluation_candidates.SNAPSHOT_PATH', metadata), patch('sys.argv', [str(SCRIPT),
                    '--launcher', '/nonexistent-launcher', '--guardian-model', 'zai-org/GLM-5.3', '--output', str(output)]):
                self.assertEqual(model_evaluation.main(), 1)
            report = json.loads(output.read_text())
            self.assertEqual(report['blocked_reason'], 'candidate_metadata_unresolved')
            self.assertEqual(report['roles']['guardian']['model'], 'zai-org/GLM-5.3')
            self.assertEqual(report['roles']['guardian']['attempted'], 0)
        self.assertFalse(report['roles']['main']['cost']['complete'])

    def test_unknown_candidate_is_blocked_before_launcher_invocation(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'report.json'
            result = subprocess.run([sys.executable, str(SCRIPT), '--launcher', '/not/an/executable',
                '--model', 'unlisted/candidate', '--output', str(output)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            report = json.loads(output.read_text())
            self.assertEqual(report['status'], 'blocked')
            self.assertEqual(report['blocked_reason'], 'candidate_not_shortlisted')
            self.assertEqual(report['roles']['main']['unattempted'], 3)
            self.assertEqual(report['roles']['guardian']['unattempted_cases'], 6)

    @unittest.skipUnless(sys.platform == 'darwin', 'evaluation is pinned to macOS')
    def test_minimum_and_newer_clients_reach_evaluation(self):
        for version in ('0.155.1', '0.155.1+build.7', '0.158.0', '0.160.0', '1.0.0', '0.160.0-alpha.1'):
            with self.subTest(version=version):
                report = self.disappearing_launcher_report(version)
                self.assertEqual(report['codex_version'], 'codex-cli ' + version)
                self.assertEqual(report['roles']['main']['attempted'], 1)
                self.assertEqual(report['roles']['guardian']['attempted'], 1)

    @unittest.skipUnless(sys.platform == 'darwin', 'requires executable Unix fixtures')
    def test_below_minimum_and_invalid_clients_are_blocked_before_inference(self):
        for version in ('0.154.9', '0.155.0', '0.155.1-alpha.1', '0.160.0junk', 'unknown'):
            with self.subTest(version=version):
                report = self.disappearing_launcher_report(version)
                self.assertEqual(report['blocked_reason'], 'codex_version_below_minimum_or_invalid')
                self.assertEqual(report['roles']['main']['attempted'], 0)
                self.assertEqual(report['roles']['guardian']['attempted'], 0)

    @unittest.skipUnless(sys.platform == 'darwin', 'evaluation is pinned to macOS')
    def test_launcher_disappearing_after_preflight_retains_both_lane_attempts(self):
        report = self.disappearing_launcher_report('0.155.1')
        self.assertTrue(report['harness_defect'], report)
        self.assertEqual(report['roles']['main']['attempted'], 1)
        self.assertEqual(report['roles']['guardian']['attempted'], 1)
        self.assertIn('harness_defect', report['runs'][0]['failures'])
        self.assertEqual(report['roles']['main']['cost']['paid_requests'], 0)

    def disappearing_launcher_report(self, version):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            launcher, codex = root / 'launcher', root / 'codex'
            launcher.write_text('#!' + sys.executable + '\nimport pathlib,sys\n'
                'if sys.argv[1:] == ["models"]: print("moonshotai/Kimi-K3\\tunverified")\n'
                'else: print("tofa fixture"); pathlib.Path(__file__).unlink()\n')
            codex.write_text('#!/bin/sh\necho codex-cli ' + version + '\n')
            launcher.chmod(0o700); codex.chmod(0o700)
            output = root / 'report.json'
            env = dict(os.environ, HOME=str(root), CODEX_HOME=str(root / 'ordinary'), XDG_CONFIG_HOME=str(root))
            result = subprocess.run([sys.executable, str(SCRIPT), '--launcher', str(launcher),
                '--codex', str(codex), '--output', str(output)], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 1, result.stderr)
            return json.loads(output.read_text())

    def test_unresolved_candidate_metadata_is_rejected_at_boundary(self):
        for settings in ({}, {'context_window': 4096, 'responses_api': True, 'function_calling': True, 'input_modalities': ['text']},
                         {'context_window': 1000000, 'responses_api': False, 'function_calling': True, 'input_modalities': ['text']}):
            with self.subTest(settings=settings), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'snapshot.json'
                path.write_text(json.dumps({'models': {'zai-org/GLM-5.3': settings}}))
                with patch('evaluation_candidates.SNAPSHOT_PATH', path):
                    with self.assertRaises(ValueError): candidate('zai-org/GLM-5.3')

    def test_declared_pass_without_observations_cannot_qualify_main_role(self):
        report, _ = self.score({}, runs=[{'passed': True, 'turns': []}] * 3)
        self.assertNotEqual(report['roles']['main']['status'], 'passed')
        self.assertEqual(report['roles']['main']['passed'], 0)

    def test_too_many_repeats_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / 'source.json', Path(directory) / 'report.json'
            source.write_text(json.dumps({'runs': [{'turns': []}] * 4}))
            result = subprocess.run([sys.executable, str(SCRIPT), '--score', str(source),
                                     '--output', str(output)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(output.exists())

    def test_guardian_failure_gates_have_explicit_reasons(self):
        valid = {'model': 'zai-org/GLM-5.3', 'requests': [{'kind': 'automatic_review',
                 'model': 'zai-org/GLM-5.3', 'status': 200, 'completed': True}],
                 'expected_decision': 'allow', 'decisions': ['allow'], 'command_executed': True,
                 'turn_completed': True, 'exit_code': 0, 'scratch_settings_preserved': True,
                 'guardian_assessment_ms': 100}
        self.assertEqual(approval_failures(valid), [])
        for change, reason in [({'guardian_assessment_ms': 90001}, 'deadline_incomplete'),
                ({'guardian_assessment_ms': None}, 'assessment_unmeasured'),
                ({'decisions': ['deny', 'allow']}, 'decision_mismatch'),
                ({'exit_code': 1}, 'client_incomplete'), ({'client_error': True}, 'client_incomplete'),
                ({'output_limit': True}, 'client_output_limit')]:
            with self.subTest(change=change):
                self.assertIn(reason, approval_failures({**valid, **change}))

    def test_synthetic_proposals_do_not_enter_paid_inference_totals(self):
        report, _ = self.score({'streams': [
            {'kind': 'synthetic_task', 'paid_inference': False,
             'usage': {'input_tokens': 1000000, 'output_tokens': 1000000}},
            {'model': 'zai-org/GLM-5.3', 'paid_inference': True,
             'usage': {'input_tokens': 100, 'output_tokens': 20}}]}, model='zai-org/GLM-5.3')
        cost = report['roles']['main']['cost']
        self.assertEqual(cost['paid_requests'], 2)
        self.assertEqual(cost['estimated_usd'], 0.000456)

    def test_quality_failure_does_not_hide_protocol_pass(self):
        turn = {'exit_code': 0, 'turn_completed': True, 'tools_succeeded': 1,
                'files_correct': False, 'streaming_observed': True,
                'elapsed_ms': 1240, 'streams': [{'status': 200, 'completed': True,
                    'headers_ms': 120, 'first_delta_ms': 220, 'completed_ms': 1200}],
                'private': 'PRIVATE_SESSION'}
        report, raw = self.score(turn)
        self.assertEqual(report['runs'][0]['protocol']['score'], 6)
        self.assertEqual(report['runs'][0]['coding']['score'], 0)
        self.assertEqual(report['runs'][0]['failures'], ['coding_incorrect'])
        self.assertEqual(report['automatic_approval']['status'], 'not_measured')
        self.assertEqual(report['status'], 'incomplete')
        self.assertNotIn('PRIVATE_SESSION', raw)

    def test_deadline_is_incomplete_not_a_coding_mistake(self):
        report, _ = self.score({'exit_code': -15, 'turn_completed': False,
            'tools_succeeded': 0, 'files_correct': False, 'timed_out': True,
            'streams': [{'status': 0, 'completed': False, 'stage': 'response_headers'}]})
        self.assertEqual(report['runs'][0]['failures'], ['deadline_incomplete'])
        self.assertEqual(report['runs'][0]['coding']['measured'], 0)
        self.assertEqual(report['runs'][0]['latency_classification'], 'adapter_or_provider_wait_incomplete')

    def test_local_budget_stop_is_distinct_from_provider_rejection(self):
        report, _ = self.score({'exit_code': 1, 'turn_completed': False,
            'streams': [{'status': 429, 'completed': False,
                         'failure': 'request_budget_limit'}]})
        self.assertEqual(report['runs'][0]['failures'], ['request_budget_limit'])
        self.assertEqual(report['runs'][0]['coding']['measured'], 0)

    def test_proxy_timeout_retains_its_cause(self):
        report, _ = self.score({'exit_code': 1, 'turn_completed': False,
            'streams': [{'status': 200, 'completed': False,
                         'failure': 'deadline_incomplete', 'stage': 'stream_read'}]})
        self.assertEqual(report['runs'][0]['failures'], ['deadline_incomplete'])
        self.assertEqual(report['runs'][0]['latency_classification'], 'adapter_or_provider_wait_incomplete')

    def test_report_keeps_safe_file_diagnostics_and_preservation(self):
        report, raw = self.score({'exit_code': 0, 'turn_completed': True,
            'files_correct': False, 'file_checks': {'summary_status': 'object',
                'unexpected_field_count': 1, 'expected_fields_match': {'count': True,
                    'total': False, 'max': True, 'PRIVATE_FIELD': 'PRIVATE_VALUE'},
                'input_preserved': True, 'raw_content': 'PRIVATE_CONTENT'}},
            normal_settings_preserved=False)
        self.assertFalse(report['normal_settings_preserved'])
        checks = report['runs'][0]['file_checks'][0]
        self.assertEqual(checks['expected_fields_match'], {'count': True, 'total': False, 'max': True})
        self.assertEqual(checks['unexpected_field_count'], 1)
        self.assertTrue(checks['input_preserved'])
        self.assertTrue(report['runs'][0]['scratch_settings_preserved'])
        self.assertNotIn('PRIVATE', raw)

    def test_invalid_measurement_fails_without_exporting_private_content(self):
        evidence = {'model': 'moonshotai/Kimi-K3', 'runs': [{'turns': [
            {'elapsed_ms': 'PRIVATE_VALUE', 'streams': []}]}]}
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / 'source.json', Path(directory) / 'report.json'
            source.write_text(json.dumps(evidence))
            result = subprocess.run([sys.executable, str(SCRIPT), '--score', str(source),
                                     '--output', str(output)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(output.exists())
            self.assertNotIn('PRIVATE_VALUE', result.stdout + result.stderr)

    def test_extra_turns_cannot_inflate_the_protocol_score(self):
        evidence = {'runs': [{'turns': [{}, {}, {}]}]}
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / 'source.json', Path(directory) / 'report.json'
            source.write_text(json.dumps(evidence))
            result = subprocess.run([sys.executable, str(SCRIPT), '--score', str(source),
                                     '--output', str(output)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(output.exists())

    def test_usage_and_request_stage_remain_available_without_raw_fields(self):
        report, raw = self.score({'exit_code': 0, 'turn_completed': True,
            'streams': [{'status': 200, 'completed': True, 'stage': 'stream_read',
                         'usage': {'input_tokens': 123, 'output_tokens': 17, 'private': 'PRIVATE'}}]})
        request = report['runs'][0]['timing'][0]['requests'][0]
        self.assertEqual(request['usage'], {'input_tokens': 123, 'output_tokens': 17})
        self.assertEqual(request['stage'], 'stream_read')
        self.assertNotIn('PRIVATE', raw)

    def test_completed_stream_with_prior_error_cannot_pass_protocol(self):
        report, _ = self.score({'exit_code': 0, 'turn_completed': True, 'tools_succeeded': 1,
            'files_correct': True, 'streaming_observed': True,
            'streams': [{'status': 200, 'completed': True, 'failure': 'response_incomplete'}]})
        self.assertEqual(report['runs'][0]['protocol']['score'], 4)
        self.assertEqual(report['runs'][0]['coding']['score'], 2)
        self.assertIn('response_incomplete', report['runs'][0]['failures'])


class QualificationPairInputTests(unittest.TestCase):
    def test_existing_report_is_rejected_before_running_a_client(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory)/'report.json'; report.write_text('preserve me')
            result = subprocess.run([sys.executable, str(SCRIPT.with_name('qualification_pair.py')),
                '--launcher', 'must-not-run', '--codex', 'must-not-run',
                '--model', 'deepseek-ai/DeepSeek-V4.1-Flash', '--guardian-model', 'zai-org/GLM-5.3-Flash',
                '--output', str(report)], capture_output=True, text=True, timeout=5)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('output must be a new file', result.stderr)
            self.assertEqual(report.read_text(), 'preserve me')


if __name__ == '__main__':
    unittest.main()
