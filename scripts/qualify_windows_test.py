"""Public Windows runner checks, on disposable native CI with synthetic account state."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import signal
import uuid
import ctypes
import unittest

SCRIPTS = Path(__file__).resolve().parent
VERSION = "v0.1.0-rc.1"


class WindowsQualificationInterfaceTests(unittest.TestCase):
    def test_purge_requires_an_explicit_command_option(self):
        result = subprocess.run([sys.executable, str(SCRIPTS / 'qualify_windows.py'), '--help'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--purge', result.stdout)
        self.assertIn('default retains', result.stdout)


@unittest.skipUnless(os.name == "nt", "native Windows required")
class WindowsQualificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get("GITHUB_ACTIONS") != "true" and os.environ.get("TOFA_TEST_DISPOSABLE_VM") != "1":
            raise unittest.SkipTest("use disposable CI or explicit TOFA_TEST_DISPOSABLE_VM=1; tests restore user PATH")
        cls.compiled = tempfile.TemporaryDirectory(prefix="tofa native fixtures ")
        root = Path(cls.compiled.name)
        # A real .exe boundary exercises Go/Python Windows executable discovery.
        source = r'''
using System;
using System.Diagnostics;
using System.IO;
using System.Text;
class Fixture {
 static string Q(string value) {
  var b = new StringBuilder("\""); int slashes = 0;
  foreach(char c in value) {
   if(c == '\\') { slashes++; continue; }
   b.Append('\\', c == '"' ? slashes * 2 + 1 : slashes); b.Append(c); slashes = 0;
  }
  b.Append('\\', slashes * 2); return b.Append('"').ToString();
 }
 static int Main(string[] args) {
  var arguments = Q(SCRIPT) + " " + Q(Path.GetFileName(Process.GetCurrentProcess().MainModule.FileName));
  foreach(var arg in args) arguments += " " + Q(arg);
  var start = new ProcessStartInfo(PYTHON, arguments); start.UseShellExecute = false;
  var child = Process.Start(start); child.WaitForExit(); return child.ExitCode;
 }
}
'''.replace("SCRIPT", '@"' + str(SCRIPTS / "fixtures/windows_qualification.py").replace('"', '""') + '"').replace("PYTHON", '@"' + sys.executable.replace('"', '""') + '"')
        (root / "fixture.cs").write_text(source)
        compiler = Path(os.environ["SystemRoot"]) / "Microsoft.NET/Framework64/v4.0.30319/csc.exe"
        cls.exe = root / "fixture.exe"
        subprocess.run([str(compiler), "/nologo", "/out:" + str(cls.exe), str(root / "fixture.cs")], check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.compiled.cleanup()

    def setUp(self):
        import winreg
        self.temp = tempfile.TemporaryDirectory(prefix="tofa synthetic Windows ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.assets = self.root / "assets"
        self.bin = self.root / "fixtures"
        self.local = self.root / "local"
        self.config = self.local / "tofa"
        self.install = self.config / "install"
        for folder in (self.assets, self.bin, self.config, self.root / ".codex", self.root / "helpers"):
            folder.mkdir(parents=True)
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_ALL_ACCESS) as key:
            try:
                self.original_path = winreg.QueryValueEx(key, "Path")
            except FileNotFoundError:
                self.original_path = None
        def restore():
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_ALL_ACCESS) as key:
                if self.original_path is None:
                    try: winreg.DeleteValue(key, "Path")
                    except FileNotFoundError: pass
                else: winreg.SetValueEx(key, "Path", 0, self.original_path[1], self.original_path[0])
        self.addCleanup(restore)
        if os.environ.get('TOFA_TEST_DISPOSABLE_VM') == '1' and self.original_path:
            # Match disposable CI discovery while preserving the normal installation.
            # Only PATH entries resolving another tofa are excluded during this test;
            # the exact original registry value/type is restored by cleanup above.
            entries = [entry for entry in self.original_path[0].split(';')
                       if not (Path(os.path.expandvars(entry)) / 'tofa.exe').is_file()]
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Environment', 0, winreg.KEY_ALL_ACCESS) as key:
                winreg.SetValueEx(key, 'Path', 0, self.original_path[1], ';'.join(entries))
        self.report = self.root / "report.json"
        # Windows launcher/installers discover state through LOCALAPPDATA, not
        # HOME. Leave HOME untouched: no uninstall or purge is run with a
        # shadowed HOME. Only the real client's non-destructive scratch sandbox
        # receives a private HOME from live_compat.client_environment.
        self.env = {**os.environ, "USERPROFILE": str(self.root),
                    "LOCALAPPDATA": str(self.local), "APPDATA": str(self.root / "roaming"),
                    "CODEX_HOME": str(self.root / ".codex"), "TEMP": str(self.root / "helpers"),
                    "TMP": str(self.root / "helpers"), "PATH": str(self.bin) + os.pathsep + os.environ["PATH"],
                    "FIXTURE_ROOT": str(self.root), "FIXTURE_MODE": "success", "TOFA_INSTALL_DIR": ""}
        self.env["FIXTURE_REFERENCE"] = uuid.uuid4().hex
        for name in ("gh.exe", "codex.exe"):
            shutil.copyfile(self.exe, self.bin / name)
        from windows_process import architecture
        self.asset = "tofa_" + VERSION + "_windows_" + architecture() + ".exe"
        shutil.copyfile(self.exe, self.assets / self.asset)
        for name in ("install.ps1", "uninstall.ps1"):
            shutil.copyfile(SCRIPTS / name, self.assets / name)
        (self.config / "unrelated.txt").write_text("PRIVATE_NEIGHBOR")
        (self.root / ".codex/auth.json").write_text("PRIVATE_AUTH")
        self.checksums()

    def checksums(self):
        (self.assets / "SHA256SUMS").write_text("".join(
            hashlib.sha256(p.read_bytes()).hexdigest() + "  " + p.name + "\n"
            for p in self.assets.iterdir() if p.name != "SHA256SUMS"))

    def run_runner(self, answers="READY\nFOUND\nPURGE\n", timeout=20, purge=True):
        result = subprocess.run([sys.executable, str(SCRIPTS / "qualify_windows.py"),
                                 "--version", VERSION, "--output", str(self.report),
                                 "--timeout", str(timeout)] + (["--purge"] if purge else []), input=answers, text=True, capture_output=True,
                                env=self.env, timeout=120)
        self.assertTrue(self.report.is_file(), result.stdout + result.stderr)
        report = json.loads(self.report.read_text())
        for value in ("PRIVATE_AUTH", "PRIVATE_KEY", "PRIVATE_NEIGHBOR", "PRIVATE_CONVERSATION",
                      str(self.root), hashlib.sha256(b"PRIVATE_KEY").hexdigest(),
                      "11111111-1111-4111-8111-111111111111"):
            self.assertNotIn(value, self.report.read_text())
            self.assertNotIn(value, self.report.with_suffix(".md").read_text())
        return result, report

    def test_download_install_live_reinstall_reuse_and_purge(self):
        result, report = self.run_runner()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr + json.dumps(report))
        self.assertEqual(report["outcome"], "passed")
        self.assertEqual(report["candidate"]["commit"], "1234567890abcdef1234567890abcdef12345678")
        self.assertEqual(report["backend"], "file")
        self.assertEqual((self.root / "logins").read_text(), "login\n")
        self.assertTrue(all(report["preservation"].values()))
        self.assertTrue(all(report["cleanup"].values()))
        self.assertTrue(report["live"]["same_session"])
        self.assertTrue(report["saved_login_reuse"]["passed"])
        self.assertTrue(all(stage["status"] == "passed" for stage in report["stages"]))

    def test_default_preserves_working_login_configuration_and_installation(self):
        result, report = self.run_runner(answers="READY\nFOUND\n", purge=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(report['qualification_scope'], 'preserve_lifecycle')
        self.assertEqual(report['outcome'], 'passed')
        summary = self.report.with_suffix('.md').read_text()
        self.assertIn('Scope: `preserve_lifecycle`', summary)
        self.assertIn('Retained state:', summary)
        self.assertIn('Destructive purge was not run', summary)
        self.assertEqual(next(s for s in report['stages'] if s['name'] == 'purge')['status'], 'not_run')
        self.assertTrue(all(report['retained_state'].values()))
        self.assertEqual((self.config / 'credentials.yml').read_text(), 'PRIVATE_KEY')
        self.assertTrue((self.config / 'config.yml').is_file())
        self.assertTrue((self.install / 'bin/tofa.exe').is_file())
        self.assertTrue(report['saved_login_reuse']['passed'])
        self.assertTrue(all(report['preservation'].values()))
        self.assertEqual((self.root / 'logins').read_text(), 'login\n')

    def test_preserved_login_mutation_cannot_pass_retained_scope(self):
        for mode in ("saved_config_changed", "saved_credential_changed"):
            with self.subTest(mode=mode):
                self.env['FIXTURE_MODE'] = mode
                self.report = self.root / (mode + '.json')
                result, report = self.run_runner(answers="READY\nFOUND\n", purge=False)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(report['reason'], 'final_state_incomplete')
                self.assertTrue(report['saved_login_reuse']['passed'])
                self.assertFalse(all(report['retained_state'].values()))
                self.assertFalse(all(report['cleanup'].values()))
                self.assertNotEqual(next(s for s in report['stages'] if s['name'] == 'purge')['status'], 'passed')

    def test_npm_cmd_is_resolved_without_shell_argument_parsing(self):
        native = self.bin / "actual-client.exe"
        (self.bin / "codex.exe").rename(native)
        wrapper = self.bin / "codex.cmd"
        wrapper.write_text("@echo This wrapper must not execute & exit /b 77\n")
        script = self.bin / "node_modules/@openai/codex/bin/codex.js"
        script.parent.mkdir(parents=True)
        script.write_text("const {spawnSync}=require('child_process'); const r=spawnSync(" + json.dumps(str(native)) + ",process.argv.slice(2),{stdio:'inherit'}); process.exit(r.status ?? 1);\n")
        result, report = self.run_runner()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr + json.dumps(report))
        self.assertTrue(report["saved_login_reuse"]["passed"])

    def test_corrupt_matching_installer_fails_before_login(self):
        with (self.assets / "install.ps1").open("a") as stream: stream.write("# changed\n")
        result, report = self.run_runner()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report["reason"], "checksum_mismatch")
        self.assertFalse((self.root / "logins").exists())

    def test_download_failure_retains_sanitized_report(self):
        self.env["FIXTURE_MODE"] = "download_failure"
        result, report = self.run_runner()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report["outcome"], "failed")
        self.assertTrue(report["cleanup"]["scratch_removed"])

    def test_declined_recovery_and_purge_are_incomplete(self):
        for answers in ("NO\n", "READY\nFOUND\nNO\n"):
            with self.subTest(answers=answers):
                if self.report.exists():
                    self.report.unlink(); self.report.with_suffix(".md").unlink()
                result, report = self.run_runner(answers)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(report["outcome"], "incomplete")
                if answers.startswith("READY"):
                    self.assertTrue(report["saved_login_reuse"]["passed"])
                    self.assertFalse(report["cleanup"]["file_credentials_removed"])

    def test_changed_ordinary_auth_fails_preservation(self):
        self.env["FIXTURE_MODE"] = "preservation_failure"
        result, report = self.run_runner()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report["reason"], "preservation_failed")
        self.assertFalse(report["preservation"]["codex_auth"])

    def test_preserve_uninstall_losing_login_cannot_reinstall(self):
        self.env["FIXTURE_MODE"] = "lost_login"
        result, report = self.run_runner()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report["reason"], "saved_state_changed")
        self.assertEqual((self.root / "logins").read_text(), "login\n")

    def test_helper_failure_or_cancel_never_reports_cleanup_success(self):
        for mode in ("helper_failure", "helper_cancel"):
            with self.subTest(mode=mode):
                if self.report.exists():
                    self.report.unlink(); self.report.with_suffix(".md").unlink()
                self.env["FIXTURE_MODE"] = mode
                result, report = self.run_runner()
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(report["reason"], "uninstall_helper_failed")
                self.assertFalse(report["cleanup"]["helpers_completed"])
                self.assertFalse(report["cleanup"]["binary_removed"])

    def test_helper_deadline_stops_descendants_and_cannot_pass(self):
        self.env["FIXTURE_MODE"] = "helper_timeout"
        result, report = self.run_runner(timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report["reason"], "process_timeout")
        self.assertFalse(report["cleanup"]["helpers_completed"])
        self.assertTrue(report["cleanup"]["scratch_removed"])
        pid = int((self.root / "helper.pid").read_text(encoding="utf-8-sig"))
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel.OpenProcess(0x100000, False, pid)
        if handle:
            try: self.assertEqual(kernel.WaitForSingleObject(handle, 1000), 0)
            finally: kernel.CloseHandle(handle)

    def test_helper_nonzero_exit_fails_even_after_all_cleanup_side_effects(self):
        self.env["FIXTURE_MODE"] = "helper_completed_failure"
        result, report = self.run_runner()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report["reason"], "uninstall_helper_failed")
        self.assertTrue(report["cleanup"]["binary_removed"])
        self.assertFalse(report["cleanup"]["helpers_completed"])

    def test_interruption_stops_live_tree_and_saves_incomplete_report(self):
        self.env["FIXTURE_MODE"] = "live_timeout"
        with subprocess.Popen([sys.executable, str(SCRIPTS / "qualify_windows.py"), "--version", VERSION,
                               "--output", str(self.report)], env=self.env, stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                              creationflags=subprocess.CREATE_NEW_PROCESS_GROUP) as process:
            process.stdin.write("READY\nFOUND\n"); process.stdin.flush()
            deadline = time.monotonic() + 40
            while not (self.root / "live-started").exists() and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertTrue((self.root / "live-started").exists())
            process.send_signal(signal.CTRL_BREAK_EVENT)
            process.communicate(timeout=15)
            self.assertNotEqual(process.returncode, 0)
        report = json.loads(self.report.read_text())
        self.assertEqual(report["outcome"], "incomplete")
        self.assertEqual(report["reason"], "interrupted")
        self.assertTrue(report["cleanup"]["scratch_removed"])

    def test_default_retains_usable_synthetic_vault_login(self):
        self.env['FIXTURE_BACKEND'] = 'keyring'
        fixture = [sys.executable, str(SCRIPTS / 'fixtures/windows_qualification.py'), 'tofa.exe']
        # Only this test's unique synthetic reference is removed by test teardown.
        self.addCleanup(subprocess.run, fixture + ['__vault_cleanup'], env=self.env, check=True)
        result, report = self.run_runner(answers="READY\nFOUND\n", purge=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(all(report['retained_state'].values()))
        self.assertFalse(report['cleanup']['vault_credentials_removed'])
        self.assertTrue(all(report['preservation'].values()))
        self.assertEqual(next(s for s in report['stages'] if s['name'] == 'purge')['status'], 'not_run')
        subprocess.run(fixture + ['__vault_check'], env=self.env, check=True)

    def test_synthetic_vault_reuse_and_purge(self):
        self.env["FIXTURE_BACKEND"] = "keyring"
        self.addCleanup(subprocess.run, [sys.executable, str(SCRIPTS / "fixtures/windows_qualification.py"), "tofa.exe", "__vault_cleanup"], env=self.env, check=True)
        result, report = self.run_runner()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr + json.dumps(report))
        self.assertEqual(report["backend"], "keyring")
        self.assertTrue(report["cleanup"]["vault_credentials_removed"])

    def test_lost_synthetic_vault_credential_cannot_pass_saved_login_reuse(self):
        self.env.update(FIXTURE_BACKEND="keyring", FIXTURE_MODE="lost_vault")
        self.addCleanup(subprocess.run, [sys.executable, str(SCRIPTS / "fixtures/windows_qualification.py"), "tofa.exe", "__vault_cleanup"], env=self.env, check=True)
        result, report = self.run_runner()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(report["saved_login_reuse"]["passed"])

    def test_custom_installation_preserves_default_install_neighbor(self):
        self.env.update(TOFA_INSTALL_DIR=str(self.root / "custom-install"), FIXTURE_MODE="default_neighbor_changed")
        self.install.mkdir()
        (self.install / "unrelated.txt").write_text("PRIVATE_NEIGHBOR")
        result, report = self.run_runner()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(report["preservation"]["unrelated_config"])

    def test_command_output_limit_stops_a_noisy_process_tree(self):
        import qualify_windows
        import windows_process
        supervisor = windows_process.build_supervisor(self.root / "supervisor")
        started = time.monotonic()
        with self.assertRaisesRegex(qualify_windows.Failure, "output_limit"):
            qualify_windows.command([sys.executable, "-c", "import sys,time; sys.stdout.buffer.write(b'x'*2000000); sys.stdout.flush(); time.sleep(60)"], supervisor, 30)
        self.assertLess(time.monotonic() - started, 10)

    def test_windows_powershell_reconstructs_its_own_module_path(self):
        import qualify_windows
        import windows_process
        supervisor = windows_process.build_supervisor(self.root / "supervisor")
        # Reproduce PowerShell7 -> Python -> Windows PowerShell inheritance.
        # A PS7-only module path makes native Get-FileHash disappear without
        # boundary normalization, before the installer can verify its bytes.
        env = {k: v for k, v in self.env.items() if k.upper() != "PSMODULEPATH"}
        env["PSModulePath"] = str(Path(shutil.which("pwsh.exe")).parent / "Modules")
        output, errors = qualify_windows.command(["powershell.exe", "-NoProfile", "-Command", "(Get-Command Get-FileHash -ErrorAction Stop).Name"], supervisor, 20, env=env)
        self.assertEqual(output, "Get-FileHash")
        self.assertFalse(errors)

    def test_actual_candidate_cli_helper_is_awaited_through_native_supervisor(self):
        import qualify_windows
        import windows_process
        candidate = SCRIPTS.parent / "dist" / ("tofa_" + os.environ["VERSION"] + "_windows_" + windows_process.architecture() + ".exe")
        self.assertTrue(candidate.is_file())
        target = self.install / "bin/tofa.exe"
        target.parent.mkdir(parents=True)
        marker = self.install / ".tofa-install"
        reference = "0123456789abcdef0123456789abcdef"
        config = self.config / "config.yml"
        credentials = self.config / "credentials.yml"
        config.write_text("version: 1\nproject_id: synthetic\ncredential_backend: file\ncredential_ref: '" + reference + "'\n")
        credentials.write_text("'" + reference + "': synthetic-key\n")
        supervisor = windows_process.build_supervisor(self.root / "supervisor")
        for purge in (False, True):
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(candidate, target)
            marker.write_text("tofa-install-v1\n")
            output, errors = qualify_windows.command([str(target), "uninstall"] + (["--purge"] if purge else []), supervisor, 30, env=self.env, require_descendant_success=True)
            self.assertFalse(errors, output)
            self.assertIn("Uninstaller started;", output)
            self.assertIn("Existing terminals may retain the old PATH entry.", output)
            self.assertFalse(target.exists())
            self.assertEqual(config.exists(), not purge)
            self.assertEqual(credentials.exists(), not purge)
            self.assertFalse(list((self.root / "helpers").glob("tofa-uninstall-*.ps1")))


if __name__ == "__main__":
    unittest.main()
