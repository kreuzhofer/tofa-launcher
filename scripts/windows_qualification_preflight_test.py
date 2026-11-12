"""Public no-inference qualification boundary with controlled launcher/engine processes."""
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parent

class WindowsPreflightTests(unittest.TestCase):
    def executable(self, path, role):
        script = SCRIPTS / 'fixtures/windows_qualification_preflight.py'
        if os.name != 'nt':
            path.write_text('#!/bin/sh\nexec ' + shlex.quote(sys.executable) + ' ' + shlex.quote(str(script)) + ' ' + role + ' "$@"\n')
            path.chmod(0o700)
            return
        source = path.with_suffix('.cs')
        source.write_text(r'''using System; using System.Diagnostics; using System.Text;
class Fixture {
 static string Q(string value) {
  var b = new StringBuilder("\""); int slashes = 0;
  foreach(char c in value) {
   if(c == '\\') { slashes++; continue; }
   b.Append('\\', c == '"' ? slashes * 2 + 1 : slashes); b.Append(c); slashes = 0;
  }
  b.Append('\\', slashes * 2); return b.Append("\"").ToString();
 }
 static int Main(string[] args) {
  string arguments = Q(SCRIPT) + " " + ROLE;
  foreach(var arg in args) arguments += " " + Q(arg);
  var start = new ProcessStartInfo(PYTHON, arguments); start.UseShellExecute = false;
  var child = Process.Start(start); child.WaitForExit(); return child.ExitCode;
 }
}'''.replace('SCRIPT', '@"' + str(script).replace('"', '""') + '"')
    .replace('PYTHON', '@"' + sys.executable.replace('"', '""') + '"').replace('ROLE', '"' + role + '"'))
        compiler = Path(os.environ['SystemRoot']) / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
        subprocess.run([str(compiler), '/nologo', '/out:' + str(path), str(source)], check=True, capture_output=True)

    def run_probe(self, mode='success', marker=None, pair=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); install = root / 'install'; (install / 'bin').mkdir(parents=True)
            launcher = install / 'bin/tofa.exe'; engine = root / 'codex.exe'
            for path, role in ((launcher, 'launcher'), (engine, 'engine')):
                self.executable(path, role)
            (install / '.tofa-install').write_text('tofa-install-v1\n')
            (install / '.path-owned').write_text(marker or str(launcher.parent), encoding='utf-8-sig')
            home = root / 'home'; home.mkdir()
            (home / 'config.toml').write_text('PRIVATE_CONFIG')
            (home / 'auth.json').write_text('PRIVATE_AUTH')
            report = root / 'result.json'; log = root / 'launches.jsonl'
            env = dict(os.environ, HOME=str(root), CODEX_HOME=str(home), FIXTURE_ADMISSION_MODE=mode,
                       FIXTURE_ADMISSION_LOG=str(log), PYTHONDONTWRITEBYTECODE='1')
            command = [sys.executable, str(SCRIPTS / ('qualification_pair.py' if pair else 'windows_qualification_preflight.py')),
                '--launcher', str(launcher), '--codex', str(engine), '--model', 'fixture/main',
                '--guardian-model', 'fixture/review', '--workspace-parent', str(root),
                '--owned-installation', str(install), '--output', str(report)]
            if pair:
                command[command.index('fixture/main')] = 'moonshotai/Kimi-K3'
                command[command.index('fixture/review')] = 'zai-org/GLM-5.3-Flash'
                env['TOFA_NATIVE_WINDOWS_CODEX_HOME'] = str(home)
            result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=120)
            self.assertTrue(report.is_file(), result.stderr)
            record = json.loads(report.read_text())
            self.assertEqual((home / 'config.toml').read_text(), 'PRIVATE_CONFIG')
            self.assertEqual((home / 'auth.json').read_text(), 'PRIVATE_AUTH')
            self.assertNotIn('PRIVATE_', report.read_text())
            self.assertNotIn(str(root), report.read_text())
            calls = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
            return result.returncode, record, calls

    @unittest.skipUnless(os.name == 'nt', 'Windows pair admission boundary')
    def test_saved_login_pair_stops_before_inference_when_cwd_is_wrong(self):
        code, report, calls = self.run_probe('wrong_cwd', pair=True)
        self.assertNotEqual(code, 0)
        self.assertEqual(report['failure'], 'windows_preflight_failed')
        self.assertEqual(report['used_requests'], 0)
        self.assertNotIn('coding', report)
        self.assertTrue(report['native_config_auth_preserved'])
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][-2:], ['--', '--version'])

    def test_malformed_native_result_retains_a_sanitized_failure_receipt(self):
        for mode in ('malformed_result', 'null_stdout', 'null_stderr', 'bool_exit'):
            with self.subTest(mode=mode):
                code, report, calls = self.run_probe(mode)
                self.assertNotEqual(code, 0)
                self.assertEqual(report['failure'], 'native_command_failed')
                self.assertTrue(report['checks']['engine_closed'])
                self.assertFalse(report['passed'])

    def test_wrong_sandbox_cwd_stops_before_any_live_request(self):
        code, report, calls = self.run_probe('wrong_cwd')
        self.assertNotEqual(code, 0)
        self.assertFalse(report['passed'])
        self.assertFalse(report['checks']['cwd'])
        self.assertEqual(calls, [['launch', 'codex', '--model', 'fixture/main', '--allow-unverified',
                                 '--evaluation-guardian-model', 'fixture/review', '--', '--version']])
        self.assertFalse(report['paid_inference'])

    def test_powershell_bom_marker_and_wrapped_denial_are_accepted(self):
        code, report, calls = self.run_probe()
        self.assertEqual(code, 0)
        self.assertTrue(report['passed'])
        self.assertTrue(all(report['checks'].values()))
        self.assertEqual(len(calls), 1)

    def test_other_installation_marker_stops_before_launch(self):
        code, report, calls = self.run_probe(marker='C:\\unrelated')
        self.assertNotEqual(code, 0)
        self.assertEqual(report['failure'], 'path_ownership_mismatch')
        self.assertEqual(calls, [])

    def test_unavailable_model_stops_before_native_or_paid_work(self):
        code, report, calls = self.run_probe('unavailable')
        self.assertNotEqual(code, 0)
        self.assertEqual(report['failure'], 'model_admission_failed')
        self.assertNotIn('cwd', report['checks'])
        self.assertEqual(len(calls), 1)

    def test_outside_write_and_missing_python_cannot_pass(self):
        for mode, check in [('outside_writable', 'outside_write_denied'), ('python_missing', 'python')]:
            with self.subTest(mode=mode):
                code, report, _ = self.run_probe(mode)
                self.assertNotEqual(code, 0)
                self.assertFalse(report['checks'][check])
                self.assertFalse(report['passed'])

if __name__ == '__main__':
    unittest.main()
