"""Driven by TestDesktopPicker using the shared executable desktop fixture."""
import os
import json
import pathlib
import queue
import signal
import subprocess
import threading
import time
import urllib.request
import unittest

from picker_test import PickerFixture, KIMI, GLM, DEEPSEEK

GLM_MAIN = 'zai-org/GLM-5.3'


@unittest.skipUnless(os.environ.get('FIXTURE_DESKTOP_BUNDLE'),
                     'run through go test -run ^TestDesktopPicker$')
class DesktopPickerTests(PickerFixture):
    support_records = [
        dict(target='codex', route='adapted', main=KIMI, guardian=GLM),
        dict(target='codex-desktop', route='adapted', main=DEEPSEEK, guardian=GLM),
        dict(target='codex-desktop', route='adapted', main=KIMI, guardian=KIMI),
        dict(target='codex-desktop', route='direct', main=GLM, guardian=GLM),
    ]

    def setUp(self):
        super().setUp()
        self.capture = pathlib.Path(os.environ['FIXTURE_DESKTOP_CAPTURE'])
        for path in self.capture.parent.glob(self.capture.name + '*'):
            path.unlink()
        # Isolate native settings and credentials as well as launcher storage.
        self.env['CODEX_HOME'] = ''
        self.env['ZDOTDIR'] = str(self.home)
        self.native = self.home / '.codex'
        self.native.mkdir()
        (self.native / 'auth.json').write_text('{"OPENAI_API_KEY":"synthetic-native"}')
        (self.native / 'config.toml').write_text('cli_auth_credentials_store="file"\n')
        self.auth = (self.native / 'auth.json').read_bytes()
        history = self.native / 'sessions' / 'native-history.jsonl'
        history.parent.mkdir()
        history.write_text('preserve ordinary conversation\n')
        settings = self.home / 'Library' / 'Application Support' / 'Codex' / 'native-settings.json'
        settings.parent.mkdir(parents=True)
        settings.write_text('{"theme":"dark"}')
        self.preserved = {path: path.read_bytes() for path in [history, settings]}

    def start(self, args, bare=False, **kwargs):
        prefix = [] if bare else ['launch', 'codex-desktop']
        super().start([*prefix, '--app-bundle',
                       os.environ['FIXTURE_DESKTOP_BUNDLE'], *args], **kwargs)
        process = self.process
        def stop():
            if process.poll() is None:
                process.send_signal(signal.SIGTERM)
                process.wait(timeout=10)
        self.addCleanup(stop)

    def test_first_explicit_desktop_launch_retains_roles_and_project(self):
        for path in self.store.iterdir():
            path.unlink()
        self.saved = {}
        self.start(['--model', KIMI, '--guardian-model', KIMI,
                    '--project-id', 'desktop-override'])
        self.read_until('API key:')
        time.sleep(.05)
        os.write(self.master, b'synthetic-key\r')
        self.read_until('Project ID:')
        os.write(self.master, b'synthetic-project\n')
        child = self.launched()
        self.read_until('Main: ' + KIMI)
        self.read_until('Guardian: ' + KIMI)
        self.assertIn(b'Catalog authentication succeeded', self.output)
        self.assertNotIn(b'Choose a main model', self.output)
        self.assertTrue(all('ai_project_id=desktop-override' in r[0] for r in self.requests))
        self.stop_desktop(child)

    def test_bare_launch_selects_desktop_before_supported_model(self):
        self.start([], bare=True)
        self.read_until('Choose an app')
        self.assertEqual(self.requests, [])
        self.assert_no_start()
        self.assertIn('Codex desktop', '\n'.join(self.screen_lines()))
        os.write(self.master, b'\x1b[B\r')
        self.read_until('Choose a main model')
        self.assertFalse(self.capture.exists())
        os.write(self.master, b'\r')
        child = self.launched()
        self.read_until('Main: ' + DEEPSEEK)
        self.read_until('Status: supported')
        self.stop_desktop(child)

    def test_cancel_restores_terminal_without_desktop_startup(self):
        self.start(['--allow-unverified'])
        self.read_until('Enter confirms')
        os.write(self.master, b'\x03')
        self.finish(1)
        self.assertFalse(pathlib.Path(os.environ['FIXTURE_DESKTOP_CAPTURE']).exists())
        self.assertFalse((self.store / 'desktop-launches').exists())

    def assert_no_start(self):
        self.assertFalse(self.capture.exists())
        self.assertFalse((self.store / 'desktop-launches').exists())
        self.assertFalse((self.store / 'desktop-bridge-v2').exists())
        self.assertEqual((self.native / 'auth.json').read_bytes(), self.auth)
        self.assertEqual((self.native / 'config.toml').read_text(), 'cli_auth_credentials_store="file"\n')

    def test_supported_choices_require_desktop_route_and_pair_evidence(self):
        for guardian, main in [(GLM, DEEPSEEK), (KIMI, KIMI)]:
            with self.subTest(guardian=guardian):
                self.start(['--guardian-model', guardian], binary=self.supported)
                self.read_until('Enter confirms')
                lines = '\n'.join(self.screen_lines())
                self.assertIn('[ Ready 3 ]', lines)
                self.assertIn('DeepSeek' if main == DEEPSEEK else 'Kimi-K3', lines)
                self.assertIn('Supported', lines)
                os.write(self.master, b'\x1b')
                self.finish(1)
                self.assert_no_start()

    def test_catalog_availability_cannot_inherit_cli_support(self):
        self.models = [KIMI, GLM]
        self.start([], binary=self.supported)
        self.read_until('Enter confirms')
        os.write(self.master, b'\r')
        child = self.launched()
        self.read_until('Status: experimental')
        self.assertNotIn(b'Launch experimental selection?', self.output)
        self.stop_desktop(child)

    def test_disabled_metadata_cannot_be_confirmed(self):
        self.start(['--allow-unverified'])
        self.read_until('Enter confirms')
        os.write(self.master, b'\t\r')
        self.read_until('missing bundled model metadata')
        self.read_until('cannot be launched')
        self.assert_no_start()
        os.write(self.master, b'\x03')
        self.finish(1)

    def test_catalog_and_guardian_failures_do_not_prompt(self):
        for models, status, flags, want in [
            ([], 200, [], 'no models available'),
            ([KIMI, GLM], 503, [], 'model catalog returned HTTP 503'),
            ([KIMI], 200, [], 'Guardian model ' + GLM + ': not available'),
            ([KIMI, GLM], 200, ['--guardian-model', 'absent/model'], 'not available'),
            ([KIMI, 'mid/unknown-model'], 200, ['--guardian-model', 'mid/unknown-model'], 'missing bundled model metadata'),
            ([KIMI, GLM], 200, ['--model', ''], 'valid explicit --model ID'),
            ([KIMI, GLM], 200, ['--model', 'absent/model'], 'not available'),
        ]:
            with self.subTest(want=want, flags=flags):
                self.models, self.catalog_status = models, status
                self.start(['--allow-unverified', *flags])
                self.read_until(want)
                self.finish(1)
                self.assertNotIn(b'Enter confirms', self.output)
                self.assert_no_start()

    def test_experimental_choice_launches_without_additional_confirmation(self):
        self.models = [KIMI, GLM]
        self.start([])
        self.read_until('Enter confirms')
        os.write(self.master, b'\r')
        child = self.launched()
        self.read_until('Main: ' + KIMI)
        self.read_until('Status: experimental')
        self.stop_desktop(child)

    def test_production_support_labels_catalog_and_launches_supported_choices(self):
        for main, keys in [(DEEPSEEK, b'\r'), (GLM_MAIN, b'GLM-5.3\r')]:
            with self.subTest(main=main):
                self.models = [DEEPSEEK, GLM_MAIN, KIMI, GLM,
                               'nvidia/Nemotron-3-Ultra-550b-a55b', 'mid/unknown-model']
                self.start([])
                self.read_until('Enter confirms')
                lines = '\n'.join(self.screen_lines())
                self.assertIn('[ Ready 5 ]', lines)
                self.assertIn(DEEPSEEK, lines)
                self.assertIn('GLM-5.3', lines)
                self.assertIn('Kimi-K3', lines)
                self.assertIn('Nemotron', lines)
                self.assertIn('Experimental', lines)
                os.write(self.master, keys)
                child = self.launched()
                self.read_until('Main: ' + main)
                self.read_until('Status: supported')
                self.read_until('Naming: nvidia/Nemotron-3_5-Lightning')
                self.read_until('automatic desktop titles; independent of main and Guardian; no fallback')
                selected = next(m for m in child['catalog']['models'] if m['slug'] == main)
                self.assertEqual(selected['auto_review_model_override'], GLM)
                self.stop_desktop(child)
                for path in self.capture.parent.glob(self.capture.name + '*'):
                    path.unlink()

    def test_production_support_does_not_promote_guardian_overrides(self):
        self.start(['--guardian-model', KIMI])
        self.read_until('Enter confirms')
        self.assertIn('Experimental', '\n'.join(self.screen_lines()))
        os.write(self.master, b'\r')
        child = self.launched()
        self.read_until('Status: experimental')
        self.assertNotIn(b'Launch experimental selection?', self.output)
        self.stop_desktop(child)

    def test_production_support_still_requires_current_availability(self):
        self.models = [GLM_MAIN, GLM]
        self.start([])
        self.read_until('Enter confirms')
        lines = '\n'.join(self.screen_lines())
        self.assertIn('[ Ready 2 ]', lines)
        self.assertIn('GLM-5.3', lines)
        self.assertNotIn(DEEPSEEK, lines)
        os.write(self.master, b'\x1b')
        self.finish(1)
        self.assert_no_start()

    def test_noninteractive_omission_ignores_saved_preference(self):
        result = subprocess.run([str(self.binary), 'launch', 'codex-desktop', '--allow-unverified'],
                                input='', capture_output=True, text=True, env=self.env, timeout=5)
        self.assertEqual(result.returncode, 1)
        self.assertIn('tofa launch codex-desktop --model ID', result.stderr)
        self.assertEqual(self.requests, [])
        self.assert_no_start()

    def test_cancellation_and_output_failure_restore_terminal(self):
        for key in (b'\x1b', b'\x03', b'\x04'):
            with self.subTest(key=key):
                self.start(['--allow-unverified'])
                self.read_until('Enter confirms')
                os.write(self.master, key)
                self.finish(1)
                self.assert_no_start()
        self.env['FIXTURE_OUTPUT_FAILURE'] = '1'
        self.start(['--allow-unverified'])
        self.read_until('synthetic terminal output failure')
        self.finish(1)
        self.assert_no_start()

    def test_failure_after_confirmation_restores_terminal(self):
        self.start(['--allow-unverified', '--app-bundle', str(self.home / 'missing.app')])
        self.read_until('Enter confirms')
        os.write(self.master, b'\r')
        self.read_until('incompatible desktop bundle')
        self.finish(1)
        self.assert_no_start()

    def test_explicit_main_bypasses_picker_with_guardian_override(self):
        self.start(['--model', DEEPSEEK, '--guardian-model', KIMI, '--allow-unverified'])
        child = self.launched()
        self.assertNotIn(b'Enter confirms', self.output)
        self.read_until('Main: ' + DEEPSEEK)
        self.read_until('Guardian: ' + KIMI)
        selected = next(m for m in child['catalog']['models'] if m['slug'] == DEEPSEEK)
        self.assertEqual(selected['auto_review_model_override'], KIMI)
        self.stop_desktop(child)

    def respond(self, handler, body):
        if not hasattr(self, 'assessment'):
            return super().respond(handler, body)
        text = 'Fixture complete.'
        if len(body.get('tools', [])) == 3:
            text = json.dumps({'outcome': self.assessment})
        item = dict(id='message_fixture', type='message', role='assistant', status='completed',
                    content=[dict(type='output_text', text=text, annotations=[])])
        if len([r for r in self.requests if r[2] is not None]) == 1:
            item = dict(id='fc_picker', type='function_call', call_id='call_picker',
                        name='exec_command', status='completed', arguments=json.dumps({
                            'cmd': 'printf tofa-picker-approved',
                            'sandbox_permissions': 'require_escalated',
                            'justification': 'Run the harmless picker fixture.', 'max_output_tokens': 100}))
        handler.send_response(200)
        handler.send_header('Content-Type', 'text/event-stream')
        handler.end_headers()
        for kind, value in [
            ('response.created', dict(response=dict(id='resp_picker', status='in_progress', output=[]))),
            ('response.output_item.added', dict(output_index=0, item=item)),
            ('response.output_item.done', dict(output_index=0, item=item)),
            ('response.completed', dict(response=dict(id='resp_picker', status='completed', output=[item],
                                                     usage=dict(input_tokens=10, output_tokens=5, total_tokens=15)))),
        ]:
            handler.wfile.write(('event: ' + kind + '\ndata: ' + json.dumps(dict(type=kind, **value)) + '\n\n').encode())
            handler.wfile.flush()

    @unittest.skipUnless(os.environ.get('TOFA_TEST_DESKTOP_ENGINE'), 'set TOFA_TEST_DESKTOP_ENGINE')
    def test_installed_engine_selected_main_and_default_guardian_allow(self):
        self.engine_approval(GLM, 'allow')

    @unittest.skipUnless(os.environ.get('TOFA_TEST_DESKTOP_ENGINE'), 'set TOFA_TEST_DESKTOP_ENGINE')
    def test_installed_engine_supported_deepseek_default_guardian_deny(self):
        self.engine_approval(GLM, 'deny')

    @unittest.skipUnless(os.environ.get('TOFA_TEST_DESKTOP_ENGINE'), 'set TOFA_TEST_DESKTOP_ENGINE')
    def test_installed_engine_supported_glm_default_guardian_allow(self):
        self.engine_approval(GLM, 'allow', GLM_MAIN)

    @unittest.skipUnless(os.environ.get('TOFA_TEST_DESKTOP_ENGINE'), 'set TOFA_TEST_DESKTOP_ENGINE')
    def test_installed_engine_supported_glm_default_guardian_deny(self):
        self.engine_approval(GLM, 'deny', GLM_MAIN)

    @unittest.skipUnless(os.environ.get('TOFA_TEST_DESKTOP_ENGINE'), 'set TOFA_TEST_DESKTOP_ENGINE')
    def test_installed_engine_selected_main_and_override_guardian_deny(self):
        self.engine_approval(KIMI, 'deny')

    def engine_approval(self, guardian, assessment, main=DEEPSEEK):
        self.assessment = assessment
        self.models = [main, KIMI, GLM]
        flags = []
        if guardian != GLM:
            flags += ['--guardian-model', guardian, '--allow-unverified']
        self.start(flags)
        self.read_until('Enter confirms')
        # Exercise both arrow directions, then filter the intended main.
        os.write(self.master, b'\x1b[B\x1b[A' + main.encode() + b'\r')
        child = self.launched()
        self.read_until('Status: ' + ('supported' if guardian == GLM else 'experimental'))
        engine = subprocess.Popen([child['env']['CODEX_CLI_PATH'], 'app-server',
                                   '-c', 'features.shell_snapshot=false'], env=child['env'], cwd=child['cwd'],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        messages = queue.Queue()
        def read():
            for line in engine.stdout:
                messages.put(json.loads(line))
        thread = threading.Thread(target=read, daemon=True)
        thread.start()
        def close():
            engine.stdin.close()
            if engine.poll() is None:
                engine.kill()
            engine.wait(timeout=5)
            thread.join(timeout=5)
            engine.stdout.close()
        self.addCleanup(close)
        request_id = 0
        def send(message):
            engine.stdin.write(json.dumps(message).encode() + b'\n')
            engine.stdin.flush()
        def call(method, params):
            nonlocal request_id
            request_id += 1
            send(dict(id=request_id, method=method, params=params))
            while True:
                message = messages.get(timeout=15)
                if message.get('id') == request_id:
                    self.assertNotIn('error', message)
                    return message['result']
        call('initialize', dict(clientInfo=dict(name='tofa_picker_fixture', version='1'),
                                capabilities=dict(experimentalApi=True)))
        send(dict(method='initialized'))
        result = call('thread/start', dict(cwd=child['cwd'], approvalPolicy='on-request',
                                          approvalsReviewer='auto_review', sandbox='read-only'))
        self.assertEqual(result['model'], main)
        self.assertEqual(result['modelProvider'], 'nebius-tofa')
        self.assertEqual(result['approvalPolicy'], 'on-request')
        self.assertEqual(result['approvalsReviewer'], 'auto_review')
        thread_id = result['thread']['id']
        call('turn/start', dict(threadId=thread_id, input=[dict(type='text', text='Run the harmless fixture once.')]))
        executed = False
        while True:
            message = messages.get(timeout=15)
            if message.get('method') == 'item/completed':
                item = message['params']['item']
                if item['type'] == 'commandExecution' and item.get('exitCode') == 0:
                    executed = 'tofa-picker-approved' in item.get('aggregatedOutput', '')
            if message.get('method') == 'turn/completed':
                self.assertEqual(message['params']['turn']['status'], 'completed')
                break
        self.assertEqual(executed, assessment == 'allow')
        posts = [r for r in self.requests if r[2] is not None]
        self.assertEqual([r[2]['model'] for r in posts], [main, guardian, main])
        self.assertTrue(all(r[1] == 'Bearer synthetic-key' for r in posts))
        self.assertTrue(all('ai_project_id=synthetic-project' in r[0] for r in posts))
        close()
        self.stop_desktop(child)

    def launched(self):
        self.read_until('Launching Codex desktop')
        end = time.monotonic() + 5
        while not pathlib.Path(str(self.capture) + '.pid').exists():
            self.assertLess(time.monotonic(), end, 'desktop worker never started')
            time.sleep(.02)
        return json.loads(self.capture.read_text())

    def stop_desktop(self, child):
        # As in the normal desktop fixture, allow the launcher's 100ms process
        # observer to see the spawned engine before requesting a graceful exit.
        time.sleep(.4)
        pathlib.Path(str(self.capture) + '.exit').touch()
        self.finish()
        self.assertEqual((self.native / 'auth.json').read_bytes(), self.auth)
        self.assertIn('cli_auth_credentials_store="file"', (self.native / 'config.toml').read_text())
        self.assertEqual({path: path.read_bytes() for path in self.preserved}, self.preserved)
        self.assertEqual(list((self.store / 'desktop-launches').iterdir()), [])
        with self.assertRaises(OSError):
            urllib.request.urlopen(child['env']['TOFA_DESKTOP_CONTEXT'], timeout=1)

    def test_arrows_confirm_selected_main_at_desktop_boundary(self):
        self.start(['--allow-unverified'])
        output = self.read_until('Enter confirms')
        self.assertIn('Codex desktop', output)
        self.assertIn('Unavailable 1', output)
        self.assertFalse(self.capture.exists())
        self.assertFalse((self.store / 'desktop-launches').exists())
        os.write(self.master, b'\x1b[B\r')
        child = self.launched()
        selected = next(m for m in child['catalog']['models'] if m['slug'] == KIMI)
        self.assertEqual(selected['auto_review_model_override'], GLM)
        self.read_until('Main: ' + KIMI)
        request = urllib.request.Request(child['env']['TOFA_DESKTOP_CONTEXT'] + '/responses',
                    json.dumps({'model': KIMI, 'input': []}).encode(),
                    {'Authorization': 'Bearer ' + child['key'], 'Content-Type': 'application/json'})
        with urllib.request.urlopen(request) as response:
            self.assertEqual(response.status, 200)
        self.assertEqual(self.requests[-1][2]['model'], KIMI)
        self.assertEqual(self.requests[-1][1], 'Bearer synthetic-key')
        self.stop_desktop(child)


if __name__ == '__main__':
    unittest.main()
