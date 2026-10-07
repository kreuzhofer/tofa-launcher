"""Catalog experiment at the public runner and executable bridge boundaries."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import select
import sys
import tempfile
import unittest

import windows_run_test as fixture


class CatalogProviderTests(unittest.TestCase):
    def test_final_native_evidence_replaces_early_completion_snapshot(self):
        from windows_catalog_result import finalize_completion
        evidence = {'checks': {'selected_request': False, 'native_turn_completed': False},
                    'requests': [{'model': 'tofa-catalog-b', 'effort': 'high', 'path': '/responses'}],
                    'events': [{'event': 'turn_completed', 'success': True}]}
        finalize_completion(evidence)
        self.assertEqual(evidence['checks'], {'selected_request': True, 'native_turn_completed': True})
        evidence['requests'].append({'model': 'tofa-catalog-a', 'effort': 'low', 'path': '/responses'})
        evidence['events'] = []
        finalize_completion(evidence)
        self.assertEqual(evidence['checks'], {'selected_request': False, 'native_turn_completed': False})

    def test_malformed_http_bodies_are_counted_and_refused(self):
        from http.client import HTTPConnection
        from http.server import ThreadingHTTPServer
        import threading
        from windows_catalog_experiment import provider_handler
        evidence = {'requests': [], 'provider_refusals': 0, 'authorization_absent': True}
        server = ThreadingHTTPServer(('127.0.0.1', 0), provider_handler(evidence))
        worker = threading.Thread(target=server.serve_forever)
        worker.start()
        try:
            for body in ([], None, {'model': 'tofa-catalog-b', 'reasoning': None}):
                connection = HTTPConnection('127.0.0.1', server.server_port, timeout=5)
                try:
                    connection.request('POST', '/responses', json.dumps(body))
                    response = connection.getresponse()
                    self.assertEqual(response.status, 400)
                    response.read()
                finally:
                    connection.close()
            self.assertEqual(evidence['provider_refusals'], 3)
            self.assertEqual(evidence['requests'], [])
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=5)


class CatalogRunnerTests(fixture.WindowsRunFixture):
    def test_guided_review_has_a_visible_bounded_task_and_keeps_native_gates(self):
        self.change(mode='catalog_complete')
        result, report, state = self.invoke('--suite', 'desktop-catalog', '--guided-catalog',
                                            '--test-auth', 'native-session', '--timeout', '1800')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(state['probe_window_style'], 'Normal')
        self.assertEqual(state['task_execution_seconds'], 1200)
        self.assertEqual(report['desktop']['catalog']['picker']['mode'], 'guided')
        self.assertEqual(report['desktop']['catalog']['production_gate'], 'blocked')

    def test_guided_confirmation_cannot_replace_request_or_protocol_evidence(self):
        for mode in ('wrong_request', 'no_protocol'):
            with self.subTest(mode=mode):
                self.change(mode='catalog_' + mode)
                result, report, _ = self.invoke('--suite', 'desktop-catalog', '--guided-catalog',
                                                '--test-auth', 'native-session', '--timeout', '1800')
                self.assertNotEqual(result.returncode, 0)
                self.assertTrue(report['retained'])
                self.assertEqual(self.invoke('--run', report['run'], command='cleanup')[0].returncode, 0)

    def test_guided_mode_rejects_other_suites_before_creating_a_clone(self):
        result, _, state = self.invoke('--guided-catalog')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(state['effects'], [])

    def test_completed_synthetic_experiment_keeps_production_blocked(self):
        self.change(mode='catalog_complete')
        result, report, _ = self.invoke('--suite', 'desktop-catalog', '--test-auth', 'native-session')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(report['capabilities']['desktop_catalog'], 'experiment-complete')
        self.assertEqual(report['desktop']['catalog']['production_gate'], 'blocked')
        self.assertFalse(report['retained'])

    def test_incomplete_or_mismatched_native_evidence_retains_the_clone(self):
        for mode in ('headless', 'changed_cli', 'wrong_request', 'wrong_engine', 'private', 'no_protocol'):
            with self.subTest(mode=mode):
                self.change(mode='catalog_' + mode)
                result, report, _ = self.invoke('--suite', 'desktop-catalog', '--test-auth', 'native-session')
                self.assertNotEqual(result.returncode, 0)
                self.assertTrue(report['retained'])
                self.assertNotIn('PRIVATE_KEY', json.dumps(report))
                self.assertEqual(self.invoke('--run', report['run'], command='cleanup')[0].returncode, 0)

    def test_headless_or_missing_catalog_evidence_cannot_qualify_desktop(self):
        result, report, _ = self.invoke('--suite', 'desktop-catalog', '--test-auth', 'native-session')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report.get('reason'), 'catalog_evidence_missing')
        self.assertTrue(report['retained'])
        self.assertNotEqual(report['capabilities'].get('desktop_catalog'), 'verified')


@unittest.skipIf(os.name == 'nt', 'External executable fixture uses a Unix shebang')
class CatalogBridgeTests(unittest.TestCase):
    def test_native_title_metadata_is_classified_but_remains_refused(self):
        responses, _ = self.exchange([{'id': 1, 'method': 'turn/start', 'params': {
            'threadId': 'background', 'turnTrigger': 'thread_title',
            'input': [{'type': 'text', 'text': 'Unrelated title request'}]}}])
        self.assertIn('error', responses[0])
        self.assertTrue(any(event.get('event') == 'catalog_background_turn_refused'
                            and event.get('category') == 'title' for event in self.events))

    def exchange(self, messages, native_mode='valid'):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            native = root / 'native'
            native.write_text('#!' + sys.executable + '\nimport runpy\nrunpy.run_path(' +
                repr(str(fixture.SCRIPTS / 'fixtures/windows_catalog_native.py')) + ',run_name="__main__")\n')
            native.chmod(0o700)
            settings = root / 'config.toml'
            original = {'model': 'synthetic-cli', 'model_reasoning_effort': 'low'}
            settings.write_text(json.dumps(original))
            config = root / 'bridge.json'
            config.write_text(json.dumps({'engine': str(native), 'sha256': hashlib.sha256(native.read_bytes()).hexdigest(),
                'workspace': str(root), 'prompt': 'synthetic', 'evidence_dir': str(root), 'catalog': {'config_file': str(settings)}}))
            messages = json.loads(json.dumps(messages).replace('WORKSPACE', str(root)))
            child = subprocess.Popen([sys.executable, str(fixture.SCRIPTS / 'windows_desktop_bridge.py'), '--observe', 'app-server'],
                env=dict(os.environ, TOFA_DESKTOP_PROBE_CONFIG=str(config), CATALOG_TEST_SETTINGS=str(settings), CATALOG_TEST_WORKSPACE=str(root), CATALOG_TEST_MODE=native_mode),
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            assert child.stdin and child.stdout and child.stderr
            responses = []
            try:
                for message in messages:
                    child.stdin.write(json.dumps(message) + '\n')
                    child.stdin.flush()
                    self.assertTrue(select.select([child.stdout], [], [], 5)[0], 'bridge response timed out')
                    responses.append(json.loads(child.stdout.readline()))
                child.stdin.close()
                self.assertEqual(child.wait(timeout=5), 0, child.stderr.read())
            finally:
                if child.poll() is None: child.kill()
                child.wait(timeout=5)
                child.stdin.close()
                child.stdout.close()
                child.stderr.close()
            self.events = [json.loads(line) for path in root.glob('bridge-*.jsonl') for line in path.read_text().splitlines()]
            return responses, json.loads(settings.read_text())

    def write(self, edits, **params):
        return {'id': 1, 'method': 'config/batchWrite', 'params': dict(filePath=None, edits=[
            {'keyPath': key, 'value': value, 'mergeStrategy': 'replace'} for key, value in edits], **params)}

    def test_explicit_synthetic_selection_reaches_engine_and_outside_catalog_fails(self):
        for model in ('tofa-catalog-b', 'outside-catalog'):
            with self.subTest(model=model):
                responses, _ = self.exchange([
                    {'id': 1, 'method': 'model/list', 'params': {}},
                    {'id': 2, 'method': 'thread/start', 'params': {'cwd': 'WORKSPACE'}},
                    {'id': 3, 'method': 'turn/start', 'params': {'threadId': 'synthetic-thread', 'model': model,
                        'effort': 'high', 'input': [{'type': 'text', 'text': 'synthetic'}]}}])
                selected = next(response for response in responses if response['id'] == 3)
                if model == 'tofa-catalog-b':
                    self.assertEqual(selected.get('result', {}).get('receivedModel'), model)
                    self.assertEqual(selected['result']['receivedEffort'], 'high')
                else:
                    self.assertIn('error', selected)

    def test_model_default_write_is_session_only_and_cli_defaults_survive(self):
        responses, settings = self.exchange([self.write([('model', 'tofa-catalog-b'), ('model_reasoning_effort', 'high')])])
        self.assertEqual(responses[0].get('result', {}).get('status'), 'okOverridden')
        self.assertEqual(settings, {'model': 'synthetic-cli', 'model_reasoning_effort': 'low'})

    def test_mixed_default_write_is_refused_atomically(self):
        responses, settings = self.exchange([self.write([('model', 'tofa-catalog-b'), ('tui.animations', False)])])
        self.assertIn('error', responses[0])
        self.assertEqual(settings, {'model': 'synthetic-cli', 'model_reasoning_effort': 'low'})

    def test_malformed_write_parameters_receive_explicit_refusal(self):
        for params in (None, {'edits': [{'keyPath': [], 'value': 'x', 'mergeStrategy': 'replace'}]}):
            with self.subTest(params=params):
                responses, settings = self.exchange([{'id': 1, 'method': 'config/batchWrite', 'params': params}])
                self.assertIn('error', responses[0])
                self.assertEqual(settings['model'], 'synthetic-cli')

    def test_native_layer_matches_file_identity_and_rejects_a_different_file(self):
        for mode in ('same_file', 'different_file'):
            with self.subTest(mode=mode):
                responses, settings = self.exchange([self.write([('model', 'tofa-catalog-b')])], native_mode=mode)
                if mode == 'same_file': self.assertEqual(responses[0]['result']['status'], 'okOverridden')
                else: self.assertIn('error', responses[0])
                self.assertEqual(settings['model'], 'synthetic-cli')

    def test_native_errors_and_missing_layers_cannot_qualify_an_override(self):
        for mode in ('native_error', 'missing_layer'):
            with self.subTest(mode=mode):
                responses, settings = self.exchange([self.write([('model', 'tofa-catalog-b')])], native_mode=mode)
                self.assertIn('error', responses[0])
                self.assertEqual(settings['model'], 'synthetic-cli')
                self.assertFalse(any(event.get('disposition') == 'session_override' for event in self.events))

    def test_stale_version_has_no_successful_override_evidence(self):
        self.exchange([self.write([('model', 'tofa-catalog-b')], expectedVersion='stale')])
        self.assertFalse(any(event.get('disposition') == 'session_override' for event in self.events))

    def test_stale_version_and_profile_writes_fail_without_changing_cli_defaults(self):
        for request in (self.write([('model', 'tofa-catalog-b')], expectedVersion='stale'),
                        self.write([('profiles.synthetic.model', 'tofa-catalog-b')])):
            responses, settings = self.exchange([request])
            self.assertIn('error', responses[0])
            self.assertEqual(settings, {'model': 'synthetic-cli', 'model_reasoning_effort': 'low'})

    def test_unrelated_write_remains_native(self):
        responses, settings = self.exchange([self.write([('tui.animations', False)])])
        self.assertEqual(responses[0].get('result', {}).get('status'), 'ok')
        self.assertEqual(settings, {'model': 'synthetic-cli', 'model_reasoning_effort': 'low', 'tui.animations': False})


if __name__ == '__main__':
    unittest.main()
