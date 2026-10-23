import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('guide', Path(__file__).with_name('desktop_qualification_guide.py'))
guide = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guide)


class GuideTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.run = Path(self.temp.name)

    def write(self, name, value):
        (self.run/name).write_text(json.dumps(value))

    def test_deadline_rejects_input(self):
        self.write('declaration.json', {'expires_utc':'2020-01-01T00:00:00Z'})
        with self.assertRaisesRegex(ValueError, 'deadline'):
            guide.ensure_active(self.run, 123)

    def test_finished_attempt_rejects_input(self):
        self.write('finish.json', {'qualified':False})
        with self.assertRaisesRegex(ValueError, 'ended'):
            guide.ensure_active(self.run, 123)

    def test_collector_failure_rejects_input(self):
        with patch.object(guide, 'alive', return_value=False):
            with self.assertRaisesRegex(ValueError, 'collector'):
                guide.ensure_active(self.run, 123)

    def test_observations_are_explicit(self):
        self.assertEqual(guide.outcome('p'), 'passed')
        self.assertEqual(guide.outcome('f'), 'failed')
        self.assertEqual(guide.outcome('u'), 'not_observed')
        for value in ('', 'yes', 'P'):
            with self.assertRaises(ValueError): guide.outcome(value)

    def test_incomplete_summary_does_not_pass(self):
        result = guide.summary(self.run)
        self.assertFalse(result['qualified'])
        self.assertIsNone(result['protected_equal'])
        self.assertEqual(result['status'], 'incomplete_collection')

    def test_normal_collection_still_needs_review(self):
        self.write('before.json', {'identity':{}, 'protected':{'a':'hash'}})
        self.write('after.json', {'identity':{}, 'protected':{'a':'hash'}})
        self.write('finish.json', {'stop':'operator_finished', 'exit_code':0,
                   'process_exited_before_stop':True, 'observer_requests':1})
        result = guide.summary(self.run)
        self.assertFalse(result['qualified'])
        self.assertTrue(result['protected_equal'])
        self.assertEqual(result['status'], 'awaiting_agent_review')

    def test_preservation_failure_is_visible(self):
        self.write('before.json', {'identity':{}, 'protected':{'a':'old'}})
        self.write('after.json', {'identity':{}, 'protected':{'a':'new'}})
        self.write('finish.json', {'stop':'operator_finished'})
        self.assertFalse(guide.summary(self.run)['protected_equal'])

    def test_failed_prepare_reports_a_visible_error(self):
        import subprocess
        script = Path(__file__).with_name('desktop_qualification_operator.sh').read_text()
        # Execute the real guide's prepare boundary with a failing fixture.
        start = script.rfind('\n', 0, script.index('collect prepare --launcher')) + 1
        end = script.index('\n  RUN=$(', start)
        fixture = ('set -euo pipefail\n'
                   'INVOCATION="$1"; KIT=unused; CANDIDATE=unused; runtime=unused\n'
                   'collect() { false; }; warn() { echo "$*" >&2; }\n'
                   'cleanup() { echo cleanup; }; trap cleanup EXIT\nrun() {\n' + script[start:end] + '\n}\nrun\n')
        result = subprocess.run(['bash','-c',fixture,'fixture',str(self.run)],capture_output=True,text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.run/'prepare.json').read_text(), '')
        self.assertIn('cleanup',result.stdout)
        self.assertIn('Preparation failed before launch', result.stderr)


    def test_preparation_declares_reviewed_candidate_and_new_budget(self):
        import subprocess
        script = Path(__file__).with_name('desktop_qualification_operator.sh').read_text()
        start = script.rfind('\n', 0, script.index('collect prepare --launcher')) + 1
        end = script.index('\n  RUN=$(', start)
        capture = ('set -euo pipefail\n'
                   'INVOCATION="$1"; KIT=kit; CANDIDATE=candidate; runtime=runtime\n'
                   'collect() { /usr/bin/python3 -c \'import json,sys; print(json.dumps(sys.argv[1:]))\' "$@"; }\n'
                   'warn() { echo "$*" >&2; }\nrun() {\n' + script[start:end] + '\n}\nrun\n')
        result = subprocess.run(['bash','-c',capture,'fixture',str(self.run)],capture_output=True,text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        args = json.loads((self.run/'prepare.json').read_text())
        for flag, expected in {'--source-revision':'372255f639db639b7ebb6f0077ca127981c1e0f1',
                              '--seconds':'600','--requests':'8','--output-tokens':'4096',
                              '--case':'clean-exit','--model':'moonshotai/Kimi-K3'}.items():
            self.assertEqual(args[args.index(flag)+1], expected)

    def test_summary_reports_drift_keys_without_claiming_qualification(self):
        self.write('before.json', {'identity':{'hashes':{'runtime':'old'}}, 'protected':{'config.toml':'old'}})
        self.write('after.json', {'identity':{'hashes':{'runtime':'new'}}, 'protected':{'config.toml':'new'}})
        self.write('finish.json', {'stop':'operator_finished','exit_code':0})
        result = guide.summary(self.run)
        self.assertEqual(result['identity_drift'], ['runtime'])
        self.assertEqual(result['protected_drift'], ['config.toml'])
        self.assertFalse(result['qualified'])

    def test_history_cli_retains_existing_bytes_and_detects_rewrites(self):
        import os
        import subprocess
        root = Path('/tmp/tofa-presentation-validation')
        root.mkdir(exist_ok=True, mode=0o700)
        with tempfile.TemporaryDirectory(dir=root) as temporary:
            run = Path(temporary)
            home = run/'home'; (home/'sessions').mkdir(parents=True, mode=0o700)
            history = home/'sessions/retained.jsonl'; history.write_bytes(b'original history\n')
            before = run/'before.json'
            before.write_text(json.dumps({'identity':{'home':str(home)}})); before.chmod(0o600)
            def invoke(action):
                return subprocess.run([__import__('sys').executable, str(Path(__file__).with_name('desktop_qualification_guide.py')),
                                       str(run/'kit'), action, str(run)], capture_output=True, text=True)
            result = invoke('history-before')
            self.assertEqual(result.returncode, 0, result.stderr)
            history.write_bytes(b'original history\nnew turn\n')
            (home/'sessions/new.jsonl').write_text('new conversation')
            result = invoke('history-after')
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads((run/'history-after.json').read_text())
            self.assertTrue(report['existing_bytes_preserved'])
            self.assertEqual(report['changed'], [])
            self.assertEqual((run/'history-before.json').stat().st_mode & 0o777, 0o600)
            self.assertNotIn('original history', (run/'history-before.json').read_text())
            # Reuse is forbidden even when the history has since changed.
            history.write_bytes(b'overwritten history\n')
            self.assertNotEqual(invoke('history-after').returncode, 0)

    def test_history_cli_detects_loss(self):
        import subprocess
        import sys
        root = Path('/tmp/tofa-presentation-validation')
        root.mkdir(exist_ok=True, mode=0o700)
        with tempfile.TemporaryDirectory(dir=root) as temporary:
            run = Path(temporary)
            home = run/'home'; (home/'sessions').mkdir(parents=True, mode=0o700)
            history = home/'sessions/retained.jsonl'; history.write_bytes(b'original history\n')
            before = run/'before.json'
            before.write_text(json.dumps({'identity':{'home':str(home)}})); before.chmod(0o600)
            command = [sys.executable, str(Path(__file__).with_name('desktop_qualification_guide.py')), str(run/'kit')]
            first = subprocess.run(command+['history-before',str(run)],capture_output=True,text=True)
            self.assertEqual(first.returncode,0,first.stderr)
            history.write_bytes(b'damaged\n')
            after = subprocess.run(command+['history-after',str(run)],capture_output=True,text=True)
            self.assertEqual(after.returncode,0,after.stderr)
            report = json.loads((run/'history-after.json').read_text())
            self.assertFalse(report['existing_bytes_preserved'])
            self.assertEqual(report['changed'], ['sessions/retained.jsonl'])

    def test_history_cli_rejects_unreadable_directories(self):
        import subprocess
        import sys
        root = Path('/tmp/tofa-presentation-validation')
        root.mkdir(exist_ok=True, mode=0o700)
        with tempfile.TemporaryDirectory(dir=root) as temporary:
            run = Path(temporary)
            home = run/'home'
            hidden = home/'sessions/inaccessible'
            hidden.mkdir(parents=True, mode=0o700)
            (hidden/'retained.jsonl').write_bytes(b'original history\n')
            before = run/'before.json'
            before.write_text(json.dumps({'identity':{'home':str(home)}})); before.chmod(0o600)
            hidden.chmod(0)
            try:
                result = subprocess.run([sys.executable, str(Path(__file__).with_name('desktop_qualification_guide.py')),
                                         str(run/'kit'),'history-before',str(run)],capture_output=True,text=True,timeout=3)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn('Permission denied', result.stderr)
                self.assertFalse((run/'history-before.json').exists())
            finally:
                hidden.chmod(0o700)

    def test_history_cli_rejects_special_files_without_hanging(self):
        import os
        import subprocess
        import sys
        root = Path('/tmp/tofa-presentation-validation')
        root.mkdir(exist_ok=True, mode=0o700)
        with tempfile.TemporaryDirectory(dir=root) as temporary:
            run = Path(temporary)
            home = run/'home'; (home/'sessions').mkdir(parents=True, mode=0o700)
            os.mkfifo(home/'sessions/not-a-history-file')
            before = run/'before.json'
            before.write_text(json.dumps({'identity':{'home':str(home)}})); before.chmod(0o600)
            result = subprocess.run([sys.executable, str(Path(__file__).with_name('desktop_qualification_guide.py')),
                                     str(run/'kit'),'history-before',str(run)],capture_output=True,text=True,timeout=3)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('history_regular_file_required',result.stderr)
            self.assertFalse((run/'history-before.json').exists())


if __name__ == '__main__': unittest.main()
