"""Offline public-runner tests: isolated homes, release downloads, client and vault.

No real credentials, native vault, GitHub network, or inference service are used.
"""
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import signal
import time
import unittest

SCRIPTS = Path(__file__).resolve().parent
VERSION = "v0.1.0-rc.1"
COMMIT = "1234567890abcdef1234567890abcdef12345678"


class QualificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tofa synthetic qualification ")
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.bin = self.home / "fixtures"
        self.bin.mkdir()
        self.assets = self.home / "assets"
        self.assets.mkdir()
        self.report = self.home / "report.json"
        self.install = self.home / ".local/share/tofa"
        self.config = self.home / ".config/tofa"
        self.config.mkdir(parents=True)
        self.unrelated = self.config / "unrelated.txt"
        self.unrelated.write_text("private-unrelated-value")
        self.codex_home = self.home / ".codex"
        self.codex_home.mkdir()
        (self.codex_home / "auth.json").write_text("private-codex-auth")
        (self.home / ".zshrc").write_text("# unrelated shell settings\n")
        (self.home / ".bashrc").write_text("# unrelated shell settings\n")
        self.env = {"HOME": str(self.home), "XDG_CONFIG_HOME": str(self.home / ".config"),
                    "CODEX_HOME": str(self.codex_home), "ZDOTDIR": str(self.home),
                    "PATH": str(self.bin) + os.pathsep + os.defpath,
                    "SHELL": "/bin/zsh" if platform.system() == "Darwin" else "/bin/bash",
                    "TMPDIR": str(self.home), "LC_ALL": "C", "TERM": "dumb",
                    "FIXTURE_ASSETS": str(self.assets), "FIXTURE_MODE": "success"}
        self.asset = f"tofa_{VERSION}_{platform.system().lower()}_" + {"arm64": "arm64", "aarch64": "arm64", "x86_64": "amd64"}[platform.machine()]
        for name in ("install.sh", "uninstall.sh"):
            shutil.copyfile(SCRIPTS / name, self.assets / name)
        self.executable(self.bin / "gh", '''
import json, os, pathlib, shutil, sys
if os.environ["FIXTURE_MODE"] == "download_failure": sys.exit(1)
args = sys.argv[1:]
if args[0] == 'api':
    assert args[1].startswith('repos/kreuzhofer/tofa-launcher/'), args
    if '/commits/' in args[1]: print(json.dumps({'sha': '1234567890abcdef1234567890abcdef12345678'}))
    else: print(json.dumps({'tag_name':'v0.1.0-rc.1','draft':False,'prerelease':True}))
else:
    assert args[args.index('--repo')+1] == 'kreuzhofer/tofa-launcher', args
    target = pathlib.Path(args[args.index('--dir')+1])
    for name in ('install.sh','uninstall.sh','SHA256SUMS'):
        shutil.copyfile(pathlib.Path(os.environ['FIXTURE_ASSETS'])/name, target/name)
    for p in pathlib.Path(os.environ['FIXTURE_ASSETS']).glob('tofa_*'):
        shutil.copyfile(p, target/p.name)
''')
        self.executable(self.assets / self.asset, '''
import http.server, json, os, pathlib, socketserver, subprocess, sys, threading
home = pathlib.Path(os.environ['HOME'])
config = home/'.config/tofa'
mode = os.environ['FIXTURE_MODE']
backend = os.environ.get('FIXTURE_BACKEND','file')
vault = home/'synthetic-vault'
reference = '0123456789abcdef0123456789abcdef'
if sys.argv[1:] == ['--version']:
    print('tofa v0.1.0-rc.1'); sys.exit()
if sys.argv[1:3] == ['auth','login']:
    config.mkdir(parents=True,exist_ok=True)
    (config/'config.yml').write_text('credential_backend: '+backend+'\\n')
    if backend == 'keyring':
        (config/'keyring-refs').mkdir(exist_ok=True)
        (config/'keyring-refs'/reference).write_text('reference')
        vault.write_text('PRIVATE_KEY')
    else: (config/'credentials.yml').write_text('PRIVATE_KEY')
    with (home/'login-count').open('a') as out: out.write('login\\n')
    sys.exit()
if sys.argv[1] == 'doctor':
    print('Credential backend: '+backend+' (access not tested; no keychain prompt)'); sys.exit()
if sys.argv[1] == 'uninstall':
    if '--purge' in sys.argv and backend == 'keyring':
        if mode == 'purge_failure': sys.exit(1)
        vault.unlink()
        (config/'keyring-refs'/reference).unlink()
        (config/'keyring-refs').rmdir()
    if mode == 'lost_login': (config/'credentials.yml').unlink()
    sys.exit(subprocess.call(['sh',str(pathlib.Path(os.environ['FIXTURE_ASSETS'])/'uninstall.sh')]+sys.argv[2:]))
if not (vault if backend == 'keyring' else config/'credentials.yml').exists(): sys.exit(1)
if mode == 'timeout':
    (home/'child.pid').write_text(str(os.getpid()))
    import time
    time.sleep(60)
if mode == 'preservation_failure': (home/'.codex/auth.json').write_text('changed')
if mode == 'no_dns':
    import socket
    def unavailable(*args): raise RuntimeError('numeric loopback fixture must not need DNS')
    socket.getfqdn = unavailable
class Adapter(http.server.BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def do_POST(self):
        self.rfile.read(int(self.headers['Content-Length']))
        self.send_response(200); self.end_headers()
        for kind in ['response.output_text.delta','response.output_text.delta','response.completed']:
            self.wfile.write(('data: '+json.dumps({'type':kind,'delta':'PRIVATE_CONVERSATION'})+'\\n\\n').encode())
            self.wfile.flush()
class Loopback(http.server.ThreadingHTTPServer):
    def server_bind(self):
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address
server = Loopback(('127.0.0.1',0),Adapter)
threading.Thread(target=server.serve_forever,daemon=True).start()
os.environ['TOFA_API_KEY']='PRIVATE_LOCAL_TOKEN'
provider='model_providers.nebius-tofa={base_url='+json.dumps('http://127.0.0.1:'+str(server.server_port))+'}'
code=subprocess.call(['codex','-c',provider]+sys.argv[sys.argv.index('--')+1:])
server.shutdown(); server.server_close(); sys.exit(code)
''')
        self.executable(self.bin / "codex", '''
import json, os, pathlib, re, sys, urllib.request
if sys.argv[1:] == ['--version']: print('codex-cli 0.100.0'); sys.exit()
provider=next(a for a in sys.argv if a.startswith('model_providers.'))
endpoint=json.loads(re.search(r'base_url\\s*=\\s*("[^"]+")',provider).group(1))
request=urllib.request.Request(endpoint+'/responses', data=b'{}',headers={'Authorization':'Bearer '+os.environ['TOFA_API_KEY']})
with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request,timeout=5) as response: response.read()
values={'count':4,'total':18,'max':9}
if 'resume' in sys.argv: values.update(min=-2,average=4.5)
pathlib.Path('summary.json').write_text(json.dumps(values))
print(json.dumps({'type':'thread.started','thread_id':'11111111-1111-4111-8111-111111111111'}))
print(json.dumps({'type':'item.completed','item':{'type':'command_execution','status':'completed','exit_code':0}}))
print(json.dumps({'type':'turn.completed'}))
''')
        self.executable(self.bin / "security", """
import os, pathlib, sys
assert sys.argv[1] == 'find-generic-password' and '-w' not in sys.argv and '-g' not in sys.argv
sys.exit(0 if (pathlib.Path(os.environ['HOME'])/'synthetic-vault').exists() else 44)
""")
        self.checksums()

    def executable(self, path, source):
        path.write_text("#!" + sys.executable + "\n" + source)
        path.chmod(0o700)

    def checksums(self):
        (self.assets / "SHA256SUMS").write_text("".join(
            hashlib.sha256(path.read_bytes()).hexdigest() + "  " + path.name + "\n"
            for path in self.assets.iterdir() if path.name != "SHA256SUMS"))

    def run_runner(self, answers="READY\nFOUND\nPURGE\n", timeout=10, extra=()):
        result = subprocess.run([sys.executable, str(SCRIPTS / "qualify_macos.py"),
                                 "--version", VERSION, "--output", str(self.report),
                                 "--timeout", str(timeout), *extra], input=answers, text=True, capture_output=True,
                                env=self.env, timeout=50)
        self.assertTrue(self.report.is_file(), result.stdout + result.stderr)
        evidence = json.loads(self.report.read_text())
        for secret in ("PRIVATE_KEY", "PRIVATE_CONVERSATION", "PRIVATE_LOCAL_TOKEN",
                       "private-codex-auth", "private-unrelated-value", str(self.home),
                       "11111111-1111-4111-8111-111111111111",
                       hashlib.sha256(b"PRIVATE_KEY").hexdigest()):
            self.assertNotIn(secret, self.report.read_text())
            self.assertNotIn(secret, self.report.with_suffix(".md").read_text())
        return result, evidence

    def test_existing_login_is_reused_without_reauthentication(self):
        (self.config / "config.yml").write_text("credential_backend: file\n")
        (self.config / "credentials.yml").write_text("PRIVATE_KEY")
        result, report = self.run_runner(answers="READY\nFOUND\n")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((self.home / "login-count").exists())
        self.assertEqual(report["login_action"], "reused")
        self.assertTrue(all(report["retained_state"].values()))

    def test_live_failure_retains_login_without_purge(self):
        self.env["FIXTURE_MODE"] = "preservation_failure"
        result, report = self.run_runner(answers="READY\nFOUND\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report["reason"], "preservation_failed")
        self.assertEqual((self.config / "credentials.yml").read_text(), "PRIVATE_KEY")
        self.assertTrue((self.install / "bin/tofa").is_file())

    def test_default_retains_working_login_and_reports_purge_unrun(self):
        result, report = self.run_runner(answers="READY\nFOUND\n")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(report["qualification_scope"], "preserve_lifecycle")
        self.assertTrue(all(report["retained_state"].values()))
        self.assertEqual((self.config / "credentials.yml").read_text(), "PRIVATE_KEY")
        self.assertTrue((self.install / "bin/tofa").is_file())
        self.assertEqual(next(s for s in report["stages"] if s["name"] == "purge"),
                         {"name": "purge", "status": "not_run", "reason": "retained_by_policy"})

    def test_complete_lifecycle_uses_pinned_download_and_saved_login(self):
        result, report = self.run_runner(extra=('--purge',))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr + json.dumps(report))
        self.assertEqual(report["outcome"], "passed")
        self.assertEqual(report["candidate"]["tag"], VERSION)
        self.assertEqual(report["candidate"]["commit"], COMMIT)
        self.assertEqual(report["backend"], "file")
        self.assertEqual(report["client"]["version"], "codex-cli 0.100.0")
        self.assertEqual((self.home / "login-count").read_text(), "login\n")
        self.assertTrue(all(report["preservation"].values()))
        self.assertTrue(all(report["cleanup"].values()))
        self.assertFalse((self.install / "bin/tofa").exists())
        self.assertFalse((self.config / "credentials.yml").exists())
        self.assertEqual(self.unrelated.read_text(), "private-unrelated-value")
        self.assertEqual((self.codex_home / "auth.json").read_text(), "private-codex-auth")
        stages = {stage["name"]: stage["status"] for stage in report["stages"]}
        for stage in ("preflight", "recovery", "download", "install", "login", "fresh_terminal", "live", "uninstall", "reinstall", "saved_login_reuse", "purge"):
            self.assertEqual(stages[stage], "passed")

    def test_host_downloaded_assets_are_checked_before_login(self):
        (self.assets/'release.json').write_text(json.dumps({'tag_name': VERSION, 'draft': False, 'prerelease': True}))
        (self.assets/'commit.json').write_text(json.dumps({'sha': COMMIT}))
        (self.assets/self.asset).write_text('corrupt candidate')
        result, report = self.run_runner(extra=('--downloaded-assets', str(self.assets)))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report['reason'], 'checksum_mismatch')
        self.assertFalse((self.home/'login-count').exists())

    def test_agent_runs_disposable_lifecycle_without_fabricated_confirmations(self):
        ordinary_shell = '# ordinary settings\n# >>> tofa >>>\nexport PATH=ordinary-install:$PATH\n# <<< tofa <<<\n'
        (self.home/'.zshrc').write_text(ordinary_shell)
        candidate = self.assets / self.asset
        candidate.write_text(candidate.read_text().replace(
            "config = home/'.config/tofa'", "config = pathlib.Path(os.environ['XDG_CONFIG_HOME'])/'tofa'").replace(
            "sys.argv[1:3] == ['auth','login']", "sys.argv[1:2] == ['--model']"))
        self.checksums()
        result, report = self.run_runner(answers='', extra=('--agent-state-root', str(self.home/'agent-state'), '--purge'))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr + json.dumps(report))
        self.assertTrue(all(report['cleanup'].values()))
        self.assertEqual(report['operator'], 'agent')
        self.assertEqual((self.home/'.zshrc').read_text(), ordinary_shell)
        self.assertNotIn('Type READY', result.stdout)
        self.assertNotIn('Type FOUND', result.stdout)
        self.assertNotIn('Type PURGE', result.stdout)
        self.assertEqual(self.unrelated.read_text(), 'private-unrelated-value')

    def test_agent_rejects_existing_state_root_before_mutation(self):
        result = subprocess.run([sys.executable, str(SCRIPTS/'qualify_macos.py'), '--version', VERSION,
            '--output', str(self.report), '--agent-state-root', str(self.home)], env=self.env,
            input='', text=True, capture_output=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('state root must be new', result.stderr)
        self.assertFalse(self.install.exists())

    def test_selected_pair_is_recorded_and_used_for_both_live_stages(self):
        candidate = self.assets / self.asset
        candidate.write_text(candidate.read_text().replace(
            "provider='model_providers.nebius-tofa=",
            "assert sys.argv[sys.argv.index('--model')+1] == 'deepseek-ai/DeepSeek-V4.1-Flash'\n"
            "assert sys.argv[sys.argv.index('--evaluation-guardian-model')+1] == 'zai-org/GLM-5.3-Flash'\n"
            "provider='model_providers.nebius-tofa="))
        self.checksums()
        result, report = self.run_runner(extra=('--model', 'deepseek-ai/DeepSeek-V4.1-Flash',
                                                '--guardian-model', 'zai-org/GLM-5.3-Flash'))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(report['model'], 'deepseek-ai/DeepSeek-V4.1-Flash')
        self.assertEqual(report['guardian_model'], 'zai-org/GLM-5.3-Flash')
        self.assertTrue(report['live']['passed'])
        self.assertTrue(report['saved_login_reuse']['passed'])

    def test_invalid_startup_file_reports_preflight_failure_without_mutation(self):
        (self.home / ".zshrc").unlink()
        (self.home / ".zshrc").mkdir()
        result, report = self.run_runner()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report["outcome"], "failed")
        self.assertFalse(self.install.exists())

    def test_symlinked_codex_auth_target_changes_fail_preservation(self):
        auth = self.codex_home / "auth.json"
        target = self.home / "ordinary-auth.json"
        auth.rename(target)
        auth.symlink_to(target)
        self.env["FIXTURE_MODE"] = "preservation_failure"
        result, report = self.run_runner()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(report["preservation"]["codex_auth"])

    @unittest.skipIf(os.geteuid() == 0, "root bypasses directory write permission")
    def test_unwritable_report_directory_rejected_before_install(self):
        folder = self.home / "readonly"
        folder.mkdir()
        self.report = folder / "report.json"
        folder.chmod(0o500)
        self.addCleanup(folder.chmod, 0o700)
        result = subprocess.run([sys.executable, str(SCRIPTS / "qualify_macos.py"),
                                 "--version", VERSION, "--output", str(self.report)],
                                env=self.env, text=True, input="READY\nFOUND\nPURGE\n",
                                capture_output=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.home / "login-count").exists())
        self.assertNotIn("Traceback", result.stderr)

    def test_missing_report_parent_is_rejected_without_account_changes(self):
        self.report = self.home / "missing/report.json"
        result = subprocess.run([sys.executable, str(SCRIPTS / "qualify_macos.py"),
                                 "--version", VERSION, "--output", str(self.report)],
                                env=self.env, text=True, capture_output=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.install.exists())

    def test_wrong_installed_version_fails_before_login(self):
        candidate = self.assets / self.asset
        candidate.write_text(candidate.read_text().replace("print('tofa v0.1.0-rc.1')", "print('tofa v0.1.0-rc.2')"))
        self.checksums()
        result, report = self.run_runner()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report["reason"], "installed_version_mismatch")
        self.assertFalse((self.home / "login-count").exists())

    def test_synthetic_loopback_qualification_does_not_depend_on_dns(self):
        self.env["FIXTURE_MODE"] = "no_dns"
        result, report = self.run_runner()
        self.assertEqual(result.returncode, 0, json.dumps(report))
        self.assertEqual(report["outcome"], "passed")

    def test_corrupt_script_is_rejected_before_install_or_login(self):
        with (self.assets / "install.sh").open("a") as out:
            out.write("\n# unexpected bytes\n")
        result, report = self.run_runner()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report["reason"], "checksum_mismatch")
        self.assertFalse(self.install.exists())
        self.assertFalse((self.home / "login-count").exists())

    def test_declined_recovery_keeps_existing_state_and_records_incomplete(self):
        (self.config / "credentials.yml").write_text("PRIVATE_KEY")
        result, report = self.run_runner("NO\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report["outcome"], "incomplete")
        self.assertTrue(report["existing_state"]["file_credentials"])
        self.assertFalse(report["cleanup"]["file_credentials_removed"])
        self.assertEqual((self.config / "credentials.yml").read_text(), "PRIVATE_KEY")
        self.assertFalse((self.home / "login-count").exists())

    def test_declined_fresh_terminal_never_claims_live_success(self):
        result, report = self.run_runner("READY\nNO\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report["outcome"], "incomplete")
        self.assertNotIn("live", report)
        self.assertFalse(report["cleanup"]["binary_removed"])

    def test_declined_purge_retains_saved_credentials(self):
        result, report = self.run_runner("READY\nFOUND\nNO\n", extra=("--purge",))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report["outcome"], "incomplete")
        self.assertTrue(report["saved_login_reuse"]["passed"])
        self.assertFalse(report["cleanup"]["file_credentials_removed"])

    def test_download_failure_still_saves_sanitized_reports(self):
        self.env["FIXTURE_MODE"] = "download_failure"
        result, report = self.run_runner()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report["outcome"], "failed")
        self.assertTrue(report["cleanup"]["scratch_removed"])
        self.assertFalse((self.home / "login-count").exists())

    def test_changed_normal_codex_auth_fails_preservation(self):
        self.env["FIXTURE_MODE"] = "preservation_failure"
        result, report = self.run_runner()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(report["preservation"]["codex_auth"])
        self.assertEqual(report["reason"], "preservation_failed")

    def test_uninstall_losing_login_stops_before_reinstall(self):
        self.env["FIXTURE_MODE"] = "lost_login"
        result, report = self.run_runner()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report["reason"], "saved_state_changed")
        self.assertEqual((self.home / "login-count").read_text(), "login\n")

    @unittest.skipUnless(platform.system() == "Darwin", "macOS vault boundary")
    def test_synthetic_vault_lifecycle_checks_presence_without_reading_secret(self):
        self.env["FIXTURE_BACKEND"] = "keyring"
        result, report = self.run_runner(extra=('--purge',))
        self.assertEqual(result.returncode, 0, json.dumps(report))
        self.assertEqual(report["backend"], "keyring")
        self.assertTrue(report["cleanup"]["vault_credentials_removed"])
        self.assertFalse((self.home / "synthetic-vault").exists())

    @unittest.skipUnless(platform.system() == "Darwin", "macOS vault boundary")
    def test_failed_synthetic_vault_purge_keeps_recovery_and_fails(self):
        self.env.update(FIXTURE_BACKEND="keyring", FIXTURE_MODE="purge_failure")
        result, report = self.run_runner(extra=('--purge',))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report["outcome"], "failed")
        self.assertFalse(report["cleanup"]["vault_credentials_removed"])
        self.assertTrue(report["saved_login_reuse"]["passed"])
        self.assertEqual(next(stage["status"] for stage in report["stages"] if stage["name"] == "purge"), "failed")
        self.assertTrue((self.config / "keyring-refs").is_dir())

    def test_live_timeout_stops_child_and_reports_failure(self):
        self.env["FIXTURE_MODE"] = "timeout"
        result, report = self.run_runner(timeout=1)
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(report["live"]["turns"][0]["timed_out"])
        self.assertTrue(report["cleanup"]["scratch_removed"])
        with self.assertRaises(ProcessLookupError):
            os.kill(int((self.home / "child.pid").read_text()), 0)

    def test_interrupted_live_run_stops_child_and_saves_incomplete_report(self):
        self.env["FIXTURE_MODE"] = "timeout"
        with subprocess.Popen([sys.executable, str(SCRIPTS / "qualify_macos.py"),
                               "--version", VERSION, "--output", str(self.report)],
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              env=self.env, text=True) as process:
            process.stdin.write("READY\nFOUND\n")
            process.stdin.flush()
            deadline = time.monotonic() + 15
            while not (self.home / "child.pid").exists() and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertTrue((self.home / "child.pid").exists())
            process.send_signal(signal.SIGTERM)
            process.communicate(timeout=10)
            self.assertNotEqual(process.returncode, 0)
        report = json.loads(self.report.read_text())
        self.assertEqual(report["outcome"], "incomplete")
        self.assertEqual(report["reason"], "interrupted")
        self.assertTrue(report["cleanup"]["scratch_removed"])
        self.assertFalse(report["cleanup"]["binary_removed"])
        with self.assertRaises(ProcessLookupError):
            os.kill(int((self.home / "child.pid").read_text()), 0)


if __name__ == "__main__":
    unittest.main()
