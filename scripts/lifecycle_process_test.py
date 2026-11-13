"""Owned child processes test failure receipts, cleanup and secret exclusion."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).with_name('lifecycle_process.py')

class ProcessTests(unittest.TestCase):
    def test_hung_child_is_stopped_and_sanitized_receipt_survives_scratch_cleanup(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            scratch = root/'scratch'
            scratch.mkdir()
            child = scratch/'child.py'
            child.write_text('import os,time\nprint("PRIVATE_KEY", flush=True)\n'
                             'print("Checksum mismatch", flush=True)\ntime.sleep(30)\n')
            job = {'executable':sys.executable,'arguments':[str(child)],
                   'stdout':str(scratch/'out'),'stderr':str(scratch/'err'),'timeout_ms':1500}
            (scratch/'job.json').write_text(json.dumps(job))
            result = subprocess.run([sys.executable,str(SCRIPT),'--job',str(scratch/'job.json'),
                '--phase','fresh_probe_removed','--diagnostics',str(root/'diagnostics')],
                capture_output=True,text=True,timeout=10)
            self.assertNotEqual(result.returncode, 0)
            receipts = list((root/'diagnostics').glob('*.json'))
            self.assertEqual(len(receipts), 1, result.stdout + result.stderr)
            raw = receipts[0].read_text()
            report = json.loads(raw)
            self.assertEqual(report['phase'], 'fresh_probe_removed')
            self.assertEqual(report['outcome'], 'timeout')
            self.assertTrue(report['direct_process_exited'])
            self.assertEqual(report['deadline_ms'], 1500)
            self.assertGreaterEqual(report['elapsed_ms'], 1500)
            self.assertIn('checksum_mismatch', report['stdout']['markers'])
            self.assertNotIn('PRIVATE_KEY', raw + result.stdout + result.stderr)
            self.assertNotIn(str(root), raw)
            if os.name != 'nt':
                with self.assertRaises(ProcessLookupError): os.kill(report['pid'], 0)
            shutil.rmtree(scratch)
            self.assertEqual(receipts[0].read_text(), raw)

    def test_success_preserves_exact_arguments_and_emits_no_failure_receipt(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            child = root/'argument fixture.py'
            child.write_text('import json,sys\nprint(json.dumps(sys.argv[1:]))\n')
            arguments = ['path with spaces', 'quote"literal', 'ampersand&literal']
            job = {'executable':sys.executable,'arguments':[str(child),*arguments],
                   'stdout':str(root/'out'),'stderr':str(root/'err'),'timeout_ms':10000}
            (root/'job.json').write_text(json.dumps(job))
            result = subprocess.run([sys.executable,str(SCRIPT),'--job',str(root/'job.json'),
                '--phase','fresh_probe_installed','--diagnostics',str(root/'diagnostics')],
                capture_output=True,text=True,timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads((root/'out').read_text()), arguments)
            self.assertFalse((root/'diagnostics').exists())

    def test_failed_child_keeps_exit_code_but_excludes_arbitrary_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            job = {'executable':sys.executable,'arguments':['-c',
                'import sys; print("PRIVATE_VALUE",file=sys.stderr); sys.exit(7)'],
                'stdout':str(root/'out'),'stderr':str(root/'err'),'timeout_ms':10000}
            (root/'job.json').write_text(json.dumps(job))
            result = subprocess.run([sys.executable,str(SCRIPT),'--job',str(root/'job.json'),
                '--phase','uninstall_preserve','--diagnostics',str(root/'diagnostics')],
                capture_output=True,text=True,timeout=15)
            self.assertNotEqual(result.returncode, 0)
            raw = next((root/'diagnostics').glob('*.json')).read_text()
            report = json.loads(raw)
            self.assertEqual(report['outcome'], 'nonzero_exit')
            self.assertEqual(report['exit_code'], 7)
            self.assertGreater(report['stderr']['bytes'], 0)
            self.assertNotIn('PRIVATE_VALUE', raw)

    @unittest.skipIf(os.name == 'nt', 'owned executable script fixture uses POSIX shebang')
    def test_uninstaller_removing_itself_still_retains_original_executable_identity(self):
        import hashlib
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            executable = root/'owned-uninstaller'
            executable.write_text('#!'+sys.executable+'\nimport pathlib,sys\npathlib.Path(__file__).unlink()\nsys.exit(7)\n')
            executable.chmod(0o700)
            expected = hashlib.sha256(executable.read_bytes()).hexdigest()
            job = {'executable':str(executable),'arguments':[], 'stdout':str(root/'out'),
                   'stderr':str(root/'err'),'timeout_ms':10000}
            (root/'job.json').write_text(json.dumps(job))
            result = subprocess.run([sys.executable,str(SCRIPT),'--job',str(root/'job.json'),
                '--phase','uninstall_purge','--diagnostics',str(root/'diagnostics')],
                capture_output=True,text=True,timeout=15)
            self.assertNotEqual(result.returncode, 0)
            receipts = list((root/'diagnostics').glob('*.json'))
            self.assertEqual(len(receipts), 1, result.stderr)
            self.assertEqual(json.loads(receipts[0].read_text())['executable_sha256'], expected)

if __name__ == '__main__': unittest.main()
