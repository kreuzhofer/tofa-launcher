"""Compiled launcher PTY checks; only synthetic credentials and loopback inference."""
import http.server
import fcntl
import json
import os
import pathlib
import platform
import pty
import select
import re
import struct
import signal
import subprocess
import sys
import tempfile
import termios
import threading
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
KIMI = 'moonshotai/Kimi-K3'
GLM = 'zai-org/GLM-5.3-Flash'
DEEPSEEK = 'deepseek-ai/DeepSeek-V4.1-Flash'


class PickerFixture(unittest.TestCase):
    support_records = [
        dict(target='codex', route='adapted', main=KIMI, guardian=GLM),
        dict(target='codex', route='adapted', main=DEEPSEEK, guardian=KIMI),
        dict(target='codex', route='direct', main=DEEPSEEK, guardian=''),
        dict(target='codex', route='adapted', main=GLM, guardian=GLM,
             platforms=['unverified/architecture']),
    ]

    @classmethod
    def setUpClass(cls):
        cls.build = tempfile.TemporaryDirectory()
        cls.experimental = pathlib.Path(cls.build.name) / 'experimental-launcher'
        cls.production = pathlib.Path(cls.build.name) / 'production-launcher'
        subprocess.run(['go', 'build', '-o', str(cls.production), './scripts/fixtures/picker_launcher'], cwd=ROOT, check=True)
        cls.binary = cls.production
        # Synthetic support records are compiled only into this test executable.
        # Production assets remain untouched. A separate empty snapshot keeps
        # generic experimental-consent tests independent of current promotions.
        records = [dict(record) for record in cls.support_records]
        for record in records:
            record.update(status='supported', evidence='test-only synthetic verification')
        snapshot = pathlib.Path(cls.build.name) / 'verification.json'
        snapshot.write_text(json.dumps({'records': records}))
        overlay = pathlib.Path(cls.build.name) / 'overlay.json'
        overlay.write_text(json.dumps({'Replace': {str(ROOT / 'internal/tofa/assets/model-verification.json'): str(snapshot)}}))
        snapshot.write_text(json.dumps({'records': []}))
        subprocess.run(['go', 'build', '-overlay', str(overlay), '-o', str(cls.experimental), './scripts/fixtures/picker_launcher'], cwd=ROOT, check=True)
        snapshot.write_text(json.dumps({'records': records}))
        cls.supported = pathlib.Path(cls.build.name) / 'supported-launcher'
        subprocess.run(['go', 'build', '-overlay', str(overlay), '-o', str(cls.supported), './scripts/fixtures/picker_launcher'], cwd=ROOT, check=True)

    @classmethod
    def tearDownClass(cls):
        cls.build.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = pathlib.Path(self.temp.name)
        self.store = self.home / 'store'
        self.store.mkdir(mode=0o700)
        ref = 'a' * 32
        (self.store / 'config.yml').write_text(f'version: 1\nproject_id: synthetic-project\nmodel: {GLM}\ncredential_backend: file\ncredential_ref: {ref}\n')
        (self.store / 'credentials.yml').write_text(f'{ref}: synthetic-key\n')
        for path in self.store.iterdir():
            path.chmod(0o600)
        self.saved = {p.name: p.read_bytes() for p in self.store.iterdir()}
        self.models = [DEEPSEEK, 'mid/unknown-model', KIMI, GLM]
        self.requests = []
        self.catalog_status = 200
        owner = self

        class Provider(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                owner.requests.append((self.path, self.headers.get('Authorization'), None))
                self.send_response(owner.catalog_status)
                self.end_headers()
                self.wfile.write(json.dumps({'data': [{'id': m} for m in owner.models]}).encode())

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                owner.requests.append((self.path, self.headers.get('Authorization'), body))
                owner.respond(self, body)

            def log_message(self, *_):
                pass

        self.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Provider)
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.marker = self.home / 'launched.json'
        client = self.home / 'codex'
        client.write_text('#!' + sys.executable + '\n' + '''import json,os,re,sys,urllib.request
args=sys.argv[1:]
model=json.loads(next(a[6:] for a in args if a.startswith('model=')))
provider=next(a for a in args if a.startswith('model_providers.nebius-tofa='))
endpoint=json.loads(re.search(r'base_url = ("[^"]+")',provider).group(1))
if endpoint.startswith('http://127.0.0.1:'):
 request=urllib.request.Request(endpoint+'/responses',json.dumps({'model':model,'input':[]}).encode(),{'Authorization':'Bearer '+os.environ['TOFA_API_KEY'],'Content-Type':'application/json'})
 with urllib.request.urlopen(request) as response: assert response.status==200
open(os.environ['FIXTURE_MARKER'],'w').write(json.dumps({'model':model,'args':args}))
''')
        client.chmod(0o700)
        self.env = dict(os.environ, HOME=str(self.home), XDG_CONFIG_HOME=str(self.home / '.config'),
                        PATH=str(self.home) + os.pathsep + os.environ['PATH'],
                        FIXTURE_ENDPOINT=f'http://127.0.0.1:{self.server.server_port}',
                        FIXTURE_DIR=str(self.store), FIXTURE_MARKER=str(self.marker))

    def respond(self, handler, body):
        handler.send_response(200)
        handler.end_headers()
        handler.wfile.write(b'{"output":[]}')

    def start(self, args, binary=None, width=120, height=24, prelude=b''):
        self.master, self.slave = pty.openpty()
        fcntl.ioctl(self.slave, termios.TIOCSWINSZ, struct.pack('HHHH', height, width, 0, 0))
        self.before = termios.tcgetattr(self.slave)
        if prelude:
            os.write(self.slave, prelude)
        self.process = subprocess.Popen([str(binary or self.binary), *args], stdin=self.slave, stdout=self.slave, stderr=self.slave, env=self.env)
        self.output = b''
        process, master, slave = self.process, self.master, self.slave
        def stop():
            if process.poll() is None:
                process.kill()
                process.wait()
            os.close(master)
            os.close(slave)
        self.addCleanup(stop)

    def read_until(self, text):
        target = text.encode()
        end = time.monotonic() + 5
        while target not in self.output and time.monotonic() < end:
            if select.select([self.master], [], [], .05)[0]:
                self.output += os.read(self.master, 65536)
        self.assertIn(target, self.output)
        return self.output.decode(errors='replace')

    def wait_for_screen(self, predicate):
        end = time.monotonic() + 5
        while time.monotonic() < end:
            lines = self.screen_lines()
            if predicate(lines):
                return lines
            if select.select([self.master], [], [], .05)[0]:
                self.output += os.read(self.master, 65536)
        self.fail('Expected terminal view was not rendered:\n' + '\n'.join(self.screen_lines()))

    def finish(self, code=0):
        # Drain terminal output while waiting: a full catalog can fill the PTY
        # buffer and otherwise block the process before it reads cancellation.
        end = time.monotonic() + 5
        while self.process.poll() is None and time.monotonic() < end:
            if select.select([self.master], [], [], .05)[0]:
                self.output += os.read(self.master, 65536)
        self.assertEqual(self.process.wait(timeout=1), code)
        while select.select([self.master], [], [], 0)[0]:
            self.output += os.read(self.master, 65536)
        if b'\x1b[?25l' in self.output:
            self.assertGreater(self.output.rfind(b'\x1b[?25h'), self.output.rfind(b'\x1b[?25l'))
        restored = termios.tcgetattr(self.slave)
        # macOS sets this transient kernel flag when tcsetattr re-enables ICANON.
        # It is not a changed terminal setting; compare every other flag and cc.
        restored[3] &= ~getattr(termios, 'PENDIN', 0)
        before = list(self.before)
        before[3] &= ~getattr(termios, 'PENDIN', 0)
        self.assertEqual(restored, before)
        self.assertEqual({name: (self.store / name).read_bytes() for name in self.saved}, self.saved)

    def screen_lines(self):
        # Interpret the terminal's cursor/erase operations to assert the visible
        # list, rather than binding the test to a particular redraw sequence.
        lines = [[]]
        row = col = 0
        saved = None
        for token in re.findall(r'\x1b\[[0-9;?]*[A-Za-z]|[^\x1b]', self.output.decode(errors='replace')):
            if token.startswith('\x1b['):
                args, command = token[2:-1], token[-1]
                count = int(args or '1') if command in ('A', 'K', 'J') else 0
                if args == '?1049' and command == 'h':
                    saved = (lines, row, col)
                    lines, row, col = [[]], 0, 0
                elif args == '?1049' and command == 'l':
                    if saved is not None:
                        lines, row, col = saved
                        saved = None
                elif command == 'H':
                    row = col = 0
                elif command == 'A':
                    row = max(0, row - count)
                elif command == 'K':
                    if count == 2:
                        lines[row] = []
                    else:
                        lines[row] = lines[row][:col]
                elif command == 'J':
                    lines[row] = lines[row][:col]
                    lines = lines[:row + 1]
                continue
            if token == '\r':
                col = 0
            elif token == '\n':
                row += 1
                while len(lines) <= row:
                    lines.append([])
            else:
                while len(lines[row]) <= col:
                    lines[row].append(' ')
                lines[row][col] = token
                col += 1
        return [''.join(line).rstrip() for line in lines]


class PickerTests(PickerFixture):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.binary = cls.experimental

    def test_qualified_production_pairs_follow_native_unix_scope(self):
        self.models.append('zai-org/GLM-5.3')
        for model in (DEEPSEEK, 'zai-org/GLM-5.3', KIMI):
            with self.subTest(model=model):
                self.start(['launch', 'codex'], self.production)
                self.read_until('Enter confirms')
                os.write(self.master, model.encode() + b'\r')
                if sys.platform == 'darwin' and platform.machine() == 'arm64':
                    self.finish()
                    self.read_until('Status: supported')
                    self.assertNotIn(b'Launch experimental selection?', self.output)
                    self.assertEqual(json.loads(self.marker.read_text())['model'], model)
                    self.marker.unlink()
                else:
                    self.read_until('Launch experimental selection?')
                    self.assertFalse(self.marker.exists())
                    os.write(self.master, b'\x03')
                    self.finish(1)

    def test_first_launch_authenticates_before_app_and_continues(self):
        for path in self.store.iterdir():
            path.unlink()
        self.saved = {}
        self.start(['--allow-unverified'])
        self.read_until('API key:')
        self.assertNotIn(b'Choose an app', self.output)
        time.sleep(.05)
        os.write(self.master, b'synthetic-key\r')
        self.read_until('Project ID:')
        os.write(self.master, b'synthetic-project\n')
        self.read_until('Choose an app')
        self.assertIn(b'First-use setup', self.output)
        self.assertIn(b'Catalog authentication succeeded', self.output)
        self.assertEqual(self.requests[0][1], 'Bearer synthetic-key')
        os.write(self.master, b'\r')
        self.read_until('Choose a main model')
        os.write(self.master, b'\r')
        self.finish()
        self.assertEqual(json.loads(self.marker.read_text())['model'], DEEPSEEK)
        self.assertNotIn(b'synthetic-key', self.output)

    def fresh_store(self):
        for path in self.store.iterdir():
            path.unlink()
        self.saved = {}

    def enter_login(self):
        self.read_until('API key:')
        time.sleep(.05)
        os.write(self.master, b'synthetic-key\r')
        self.read_until('Project ID:')
        os.write(self.master, b'synthetic-project\n')

    def test_first_explicit_launch_preserves_selections_and_client_args(self):
        self.fresh_store()
        self.start(['launch', 'codex', '--model', KIMI, '--guardian-model', DEEPSEEK,
                    '--project-id', 'override-project', '--allow-unverified', '--', 'exec', 'hello'])
        self.enter_login()
        self.finish()
        launch = json.loads(self.marker.read_text())
        self.assertEqual(launch['model'], KIMI)
        self.assertEqual(launch['args'][-2:], ['exec', 'hello'])
        self.assertIn(('Guardian: ' + DEEPSEEK).encode(), self.output)
        self.assertTrue(all('ai_project_id=override-project' in r[0] for r in self.requests))
        self.assertNotIn(b'Choose an app', self.output)
        self.assertNotIn(b'Choose a main model', self.output)

    def test_invalid_launch_arguments_never_collect_credentials(self):
        self.fresh_store()
        for args in (['--bogus'], ['--model='], ['--project-id=bad project'],
                     ['--direct', '--guardian-model', KIMI], ['--', '--config=x'],
                     ['launch', 'unknown'], ['launch', 'codex', '--model='],
                     ['launch', 'codex-desktop', '--model=']):
            with self.subTest(args=args):
                self.start(args)
                self.finish(1)
                self.assertNotIn(b'API key:', self.output)
                self.assertNotIn(b'Choose an app', self.output)
                self.assertFalse((self.store / 'config.yml').exists())

    def test_onboarding_cancel_and_eof_do_not_write_or_launch(self):
        self.fresh_store()
        for label, key in [('API key:', b'\x03'), ('API key:', b'\x04'), ('Project ID:', b'\x04')]:
            with self.subTest(label=label, key=key):
                self.start([])
                self.read_until('API key:')
                time.sleep(.05)
                if label == 'Project ID:':
                    os.write(self.master, b'synthetic-key\r')
                    self.read_until(label)
                os.write(self.master, key)
                self.finish(1)
                self.assertFalse((self.store / 'config.yml').exists())
                self.assertFalse((self.store / 'credentials.yml').exists())
                self.assertFalse(self.marker.exists())
                self.assertEqual(self.requests, [])

    def test_remote_rejection_keeps_saved_login_but_stops_setup(self):
        self.fresh_store()
        self.catalog_status = 401
        self.start([])
        self.enter_login()
        self.finish(1)
        self.assertIn(b'Remote authentication has not been tested', self.output)
        self.assertNotIn(b'Catalog authentication succeeded', self.output)
        self.assertNotIn(b'Choose an app', self.output)
        self.assertFalse(self.marker.exists())
        self.assertTrue((self.store / 'credentials.yml').exists())

    def test_logout_then_launch_onboards(self):
        result = subprocess.run([str(self.binary), 'auth', 'logout'], env=self.env, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.saved = {}
        self.start(['launch', 'codex', '--model', KIMI, '--allow-unverified'])
        self.enter_login()
        self.finish()
        self.assertTrue(self.marker.exists())

    def test_unreadable_or_missing_saved_credentials_never_onboard(self):
        for broken in ('missing file', 'malformed config', 'missing vault entry'):
            with self.subTest(broken=broken):
                for name, data in self.saved.items():
                    (self.store / name).write_bytes(data)
                if broken == 'missing file':
                    (self.store / 'credentials.yml').unlink()
                elif broken == 'malformed config':
                    (self.store / 'config.yml').write_text('not: [valid')
                else:
                    config = self.store / 'config.yml'
                    config.write_text(config.read_text().replace('backend: file', 'backend: keyring'))
                snapshot = {p.name: p.read_bytes() for p in self.store.iterdir()}
                self.start(['launch', 'codex', '--model', KIMI, '--allow-unverified'])
                original, self.saved = self.saved, snapshot
                self.finish(1)
                self.saved = original
                self.assertNotIn(b'API key:', self.output)
                self.assertFalse(self.marker.exists())

    def test_vault_failures_never_fall_back_or_claim_success(self):
        self.fresh_store()
        for mode in ('locked', 'denied', 'failed', 'write-failed'):
            with self.subTest(mode=mode):
                self.env['FIXTURE_VAULT'] = mode
                self.start([])
                if mode == 'write-failed':
                    self.enter_login()
                self.finish(1)
                self.assertFalse((self.store / 'credentials.yml').exists())
                self.assertFalse((self.store / 'config.yml').exists())
                self.assertNotIn(b'Catalog authentication succeeded', self.output)
                self.assertNotIn(b'Choose an app', self.output)
                self.assertFalse(self.marker.exists())
                self.assertEqual(self.requests, [])

    def test_orphaned_credentials_require_recovery_before_input(self):
        (self.store / 'config.yml').unlink()
        self.saved.pop('config.yml')
        self.start([])
        self.finish(1)
        self.assertNotIn(b'API key:', self.output)
        self.assertNotIn(b'Choose an app', self.output)
        self.assertIn(b'recovery', self.output)

    def test_fresh_nonterminal_without_model_has_login_guidance(self):
        self.fresh_store()
        result = subprocess.run([str(self.binary)], env=self.env, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 1)
        self.assertIn(b'tofa auth login', result.stderr)
        self.assertIn(b'--model ID', result.stderr)
        self.assertFalse((self.store / 'config.yml').exists())

    def test_fresh_nonterminal_has_actionable_login_error(self):
        self.fresh_store()
        result = subprocess.run([str(self.binary), 'launch', 'codex', '--model', KIMI,
                                 '--allow-unverified'], env=self.env, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 1)
        self.assertIn(b'tofa auth login', result.stderr)
        self.assertNotIn(b'API key:', result.stdout)
        self.assertFalse((self.store / 'config.yml').exists())

    def test_app_picker_cancel_restores_terminal_before_catalog_discovery(self):
        for key in (b'\x1b', b'\x03'):
            with self.subTest(key=key):
                self.start([])
                self.read_until('Choose an app')
                os.write(self.master, key)
                self.finish(1)
                self.assertEqual(self.requests, [])
                self.assertFalse(self.marker.exists())

    def test_bare_experimental_launch_selects_app_then_model(self):
        self.start(['--allow-unverified'])
        self.read_until('Choose an app')
        self.assertEqual(self.requests, [])
        os.write(self.master, b'\r')
        self.read_until('Choose a main model')
        os.write(self.master, b'\r')
        self.finish()
        self.assertEqual(json.loads(self.marker.read_text())['model'], DEEPSEEK)

    def test_arrows_skip_blocked_rows_and_launch_selected_upstream(self):
        self.start(['launch', 'codex', '--allow-unverified'])
        output = self.read_until('Enter confirms')
        self.assertIn('Unavailable 1', output)
        self.assertIn('Codex CLI', output)
        os.write(self.master, b'\x1b[B\r')
        self.finish()
        self.assertEqual(json.loads(self.marker.read_text())['model'], KIMI)
        self.assertEqual(self.requests[-1][2]['model'], KIMI)
        self.assertEqual(self.requests[-1][1], 'Bearer synthetic-key')
        self.assertIn('ai_project_id=synthetic-project', self.requests[-1][0])

    def test_indicator_moves_in_presented_list(self):
        self.start(['launch', 'codex', '--allow-unverified'])
        self.read_until('Type to filter')
        rows = [line.strip() for line in self.screen_lines() if line.strip().startswith('> ')]
        self.assertEqual(len(rows), 1)
        self.assertIn('DeepSeek', rows[0])
        os.write(self.master, b'\x1b[B')
        self.read_until(KIMI)
        rows = [line.strip() for line in self.screen_lines() if line.strip().startswith('> ')]
        self.assertEqual(len(rows), 1)
        self.assertIn('Kimi', rows[0])
        os.write(self.master, b'\r')
        self.finish()
        self.assertEqual(json.loads(self.marker.read_text())['model'], KIMI)

    def test_unavailable_view_explains_offscreen_models_without_launch(self):
        long_id = 'unknown/' + 'x' * 180
        self.models = [DEEPSEEK] + [f'unknown/model-{i:02}' for i in range(30)] + [long_id]
        self.start(['launch', 'codex', '--direct', '--allow-unverified'])
        self.read_until('Type to filter')
        os.write(self.master, b'\txxxx?')
        lines = self.wait_for_screen(lambda lines: long_id in ''.join(line.strip() for line in lines) and any('Up/Down scroll' in line for line in lines))
        visible = ''.join(line.strip() for line in lines)
        self.assertIn(long_id, visible)
        os.write(self.master, b'\r')
        time.sleep(.05)
        self.assertIsNone(self.process.poll())
        self.assertFalse(self.marker.exists())
        os.write(self.master, b'\x03')
        self.finish(1)

    def test_filter_finds_model_and_launches_without_catalog_noise(self):
        self.start(['launch', 'codex', '--allow-unverified'])
        self.read_until('Type to filter')
        self.assertIn('Choose a main model', self.output.decode(errors='replace'))
        os.write(self.master, b'kimi')
        # PTY reads can split a redraw after its filter heading. Wait for the
        # matching result footer before asserting the complete visible list.
        lines = self.wait_for_screen(lambda lines: 'Filter: kimi' in '\n'.join(lines)
                                     and '1 match' in '\n'.join(lines))
        self.assertTrue(any('Kimi' in line and line.lstrip().startswith('>') for line in lines), lines)
        self.assertFalse(any('DeepSeek' in line for line in lines), lines)
        self.assertIn('1 match', '\n'.join(lines))
        os.write(self.master, b'\r')
        self.finish()
        self.assertEqual(json.loads(self.marker.read_text())['model'], KIMI)

    def test_cancel_returns_to_original_shell_screen(self):
        self.start(['launch', 'codex', '--allow-unverified'], prelude=b'Previous shell output\r\n')
        self.read_until('Type to filter')
        self.assertNotIn('Previous shell output', '\n'.join(self.screen_lines()))
        os.write(self.master, b'\x03')
        self.finish(1)
        screen = '\n'.join(self.screen_lines())
        self.assertIn('Previous shell output', screen)
        self.assertNotIn('Choose a main model', screen)
        self.assertFalse(self.marker.exists())

    def test_resize_reflows_without_key_input_or_selection_loss(self):
        self.start(['launch', 'codex', '--allow-unverified'])
        self.read_until('Type to filter')
        os.write(self.master, b'\x1b[B')
        self.wait_for_screen(lambda lines: any(KIMI in line for line in lines))
        fcntl.ioctl(self.slave, termios.TIOCSWINSZ, struct.pack('HHHH', 18, 40, 0, 0))
        lines = self.wait_for_screen(lambda lines: any('Tab views' in line for line in lines))
        self.assertLessEqual(len(lines), 18)
        self.assertTrue(all(len(line) < 40 for line in lines), lines)
        self.assertTrue(any('Kimi' in line and line.strip().startswith('>') for line in lines))
        os.write(self.master, b'\r')
        self.finish()
        self.assertEqual(json.loads(self.marker.read_text())['model'], KIMI)

    def test_page_navigation_and_empty_search_are_recoverable(self):
        self.models += [f'unknown/model-{i:02}' for i in range(20)]
        self.start(['launch', 'codex', '--allow-unverified'])
        self.read_until('Type to filter')
        os.write(self.master, b'\t\x1b[6~')
        lines = self.wait_for_screen(lambda lines: any('unknown/model-07' in line for line in lines))
        self.assertTrue(any('Unavailable:' in line for line in lines))
        os.write(self.master, b'\tno-such-model\r')
        self.wait_for_screen(lambda lines: any('Choose a matching model' in line for line in lines))
        self.assertFalse(self.marker.exists())
        os.write(self.master, b'\x15kimiX\x7f')
        self.wait_for_screen(lambda lines: any('Filter: kimi' in line for line in lines) and any(KIMI in line for line in lines))
        os.write(self.master, b'\r')
        self.finish()
        self.assertEqual(json.loads(self.marker.read_text())['model'], KIMI)

    def test_detail_navigation_never_changes_selected_model(self):
        self.start(['launch', 'codex', '--allow-unverified'])
        self.read_until('Type to filter')
        os.write(self.master, b'\x1b[B?')
        self.read_until('Up/Down scroll')
        os.write(self.master, b'\x1b[F\x1b[H\x15\x7f?\r')
        self.finish()
        self.assertEqual(json.loads(self.marker.read_text())['model'], KIMI)

    def test_empty_catalog_does_not_open_picker(self):
        self.models = []
        self.start(['launch', 'codex', '--allow-unverified'])
        self.read_until('no models available')
        self.finish(1)
        self.assertFalse(self.marker.exists())
        self.assertNotIn(b'Enter confirms', self.output)

    def test_launch_command_and_up_arrow(self):
        self.start(['launch', 'codex', '--allow-unverified', '--project-id', 'other-project'])
        self.read_until('Enter confirms')
        # Up wraps to the last eligible row; Down wraps back, skipping no choice.
        os.write(self.master, b'\x1bOA\x1bOB\r')
        self.finish()
        self.assertEqual(json.loads(self.marker.read_text())['model'], DEEPSEEK)
        self.assertTrue(all('ai_project_id=other-project' in r[0] for r in self.requests))

    def test_supported_bare_picker_ignores_saved_model(self):
        self.start([], self.supported)
        self.read_until('Choose an app')
        self.assertEqual(self.requests, [])
        self.assertFalse(self.marker.exists())
        self.assertIn('Codex CLI', '\n'.join(self.screen_lines()))
        os.write(self.master, b'\r')
        self.read_until('Choose a main model')
        output = self.read_until('Enter confirms')
        self.assertIn('Kimi-K3', output)
        self.assertIn('Supported', output)
        self.assertIn(DEEPSEEK.encode(), self.output)
        os.write(self.master, b'kimi\r')
        self.finish()
        self.read_until('Guardian: ' + GLM)
        self.assertEqual(json.loads(self.marker.read_text())['model'], KIMI)

    def test_supported_choices_follow_guardian_override(self):
        self.start(['launch', 'codex', '--guardian-model', KIMI], self.supported)
        output = self.read_until('Enter confirms')
        self.assertIn(DEEPSEEK, output)
        self.assertIn('Supported', output)
        os.write(self.master, b'\r')
        self.finish()
        self.read_until('Guardian: ' + KIMI)
        self.assertEqual(json.loads(self.marker.read_text())['model'], DEEPSEEK)

    def test_support_from_another_platform_requires_experimental_consent(self):
        self.start(['launch', 'codex'], self.supported)
        self.read_until('Enter confirms')
        os.write(self.master, b'glm\r')
        self.read_until('Launch experimental selection?')
        self.assertFalse(self.marker.exists())
        os.write(self.master, b'y')
        self.finish()
        self.assertEqual(json.loads(self.marker.read_text())['model'], GLM)
        self.read_until('Status: experimental')

    def test_direct_picker_uses_route_support_and_native_reviewer(self):
        self.start(['launch', 'codex', '--direct'], self.supported)
        output = self.read_until('Enter confirms')
        self.assertIn(DEEPSEEK, output)
        self.assertIn('Supported', output)
        self.assertIn(b'Kimi-K3', self.output)
        os.write(self.master, b'\r')
        self.finish()
        self.read_until('Guardian: native reviewer selection')
        self.assertEqual(json.loads(self.marker.read_text())['model'], DEEPSEEK)
        self.assertTrue(all(r[2] is None for r in self.requests))

    def test_cancel_restores_terminal_and_never_launches(self):
        # Each process owns its PTY; a cancellation must not start a client.
        for key in (b'\x1b', b'\x03', b'\x1b['):
            with self.subTest(key=key):
                self.start(['launch', 'codex', '--allow-unverified'])
                self.read_until('Enter confirms')
                os.write(self.master, key)
                self.finish(1)
                self.assertFalse(self.marker.exists())

    def test_signal_restores_terminal(self):
        self.start(['launch', 'codex', '--allow-unverified'])
        self.read_until('Enter confirms')
        self.process.send_signal(signal.SIGTERM)
        self.finish(1)
        self.assertFalse(self.marker.exists())

    def test_experimental_models_visible_and_require_explicit_confirmation(self):
        self.start(['launch', 'codex'])
        output = self.read_until('Enter confirms')
        self.assertIn('Kimi-K3', output)
        self.assertIn('GLM-5.3-Flash', output)
        self.assertIn('Experimental', output)
        os.write(self.master, b'kimi\r')
        self.read_until('Launch experimental selection?')
        self.assertFalse(self.marker.exists())
        os.write(self.master, b'y')
        self.finish()
        self.assertEqual(json.loads(self.marker.read_text())['model'], KIMI)
        self.read_until('Status: experimental')

    def test_experimental_confirmation_decline_and_cancel_never_launch(self):
        for key in (b'\r', b'n', b'\x1b', b'\x03'):
            with self.subTest(key=key):
                self.start(['launch', 'codex'])
                self.read_until('Enter confirms')
                os.write(self.master, b'\r')
                self.read_until('Launch experimental selection?')
                os.write(self.master, key)
                if key in (b'\r', b'n'):
                    self.wait_for_screen(lambda lines: any('Choose a main model' in line for line in lines))
                    self.assertFalse(self.marker.exists())
                    os.write(self.master, b'\x03')
                self.finish(1)
                self.assertFalse(self.marker.exists())

    def test_explicit_experimental_main_still_requires_flag(self):
        self.start(['launch', 'codex', '--model', KIMI])
        self.read_until('--allow-unverified')
        self.finish(1)
        self.assertFalse(self.marker.exists())
        self.assertNotIn(b'Launch experimental selection?', self.output)

    def test_catalog_failure_never_launches(self):
        self.catalog_status = 503
        self.start(['launch', 'codex', '--allow-unverified'])
        self.read_until('model catalog returned HTTP 503')
        self.finish(1)
        self.assertFalse(self.marker.exists())

    def test_all_blocked_rows_explain_reasons_without_prompt(self):
        self.models = ['outside/shortlist']
        self.start(['launch', 'codex', '--direct', '--allow-unverified'])
        self.read_until('outside/shortlist [disabled: missing bundled model metadata]')
        self.read_until('no eligible main models')
        self.finish(1)
        self.assertFalse(self.marker.exists())
        self.assertNotIn(b'Enter confirms', self.output)

    def test_explicit_main_bypasses_picker_and_saved_preference(self):
        self.start(['launch', 'codex', '--model', KIMI, '--allow-unverified'])
        self.finish()
        self.read_until('Main: ' + KIMI)
        self.assertNotIn(b'Enter confirms', self.output)
        self.assertEqual(json.loads(self.marker.read_text())['model'], KIMI)

    def test_invalid_explicit_id_never_prompts_or_launches(self):
        self.start(['launch', 'codex', '--model', 'absent/model', '--allow-unverified'])
        self.read_until('main model absent/model: not available')
        self.finish(1)
        self.assertFalse(self.marker.exists())
        self.assertNotIn(b'Enter confirms', self.output)

    def test_noninteractive_omitted_main_ignores_saved_preference(self):
        for args in ([], ['--allow-unverified'], ['launch', 'codex', '--allow-unverified']):
            with self.subTest(args=args):
                result = subprocess.run([str(self.binary), *args], input='', capture_output=True, text=True, env=self.env, timeout=5)
                self.assertEqual(result.returncode, 1)
                self.assertIn('--model ID', result.stderr)
                self.assertFalse(self.marker.exists())
        self.assertEqual(self.requests, [])

    def test_output_error_restores_terminal_without_launch(self):
        self.env['FIXTURE_OUTPUT_FAILURE'] = '1'
        self.start(['launch', 'codex', '--allow-unverified'])
        self.read_until('synthetic terminal output failure')
        self.finish(1)
        self.assertFalse(self.marker.exists())

    def test_missing_guardian_does_not_prompt_or_substitute(self):
        self.models = [KIMI]
        self.start(['launch', 'codex', '--allow-unverified'])
        self.read_until('Guardian model ' + GLM + ': not available')
        self.finish(1)
        self.assertFalse(self.marker.exists())
        self.assertNotIn(b'Enter confirms', self.output)


if __name__ == '__main__':
    unittest.main()
