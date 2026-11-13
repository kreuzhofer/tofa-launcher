import importlib.util
import os
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

    def test_skill_drift_reports_retained_files_without_attributing_cause(self):
        before = {'identity':{'hashes':{'skills':'before','agent_skills':'agent-before'}},
                  'protected':{'skills':'before'},
                  'skill_files':{'skills':{'edit/SKILL.md':'old','remove/SKILL.md':'gone'},
                                 'agent_skills':{'link':'link:old'}}}
        after = {'identity':{'hashes':{'skills':'after','agent_skills':'agent-after'}},
                 'protected':{'skills':'after'},
                 'skill_files':{'skills':{'edit/SKILL.md':'new','add/SKILL.md':'added'},
                                'agent_skills':{'link':'link:new'}}}
        self.write('before.json', before)
        self.write('after.json', after)
        original = {p.name:p.read_bytes() for p in self.run.iterdir()}
        report = guide.summary(self.run)
        self.assertEqual(report['skill_file_changes']['skills'], {
            'status':'recorded', 'added':['add/SKILL.md'],
            'removed':['remove/SKILL.md'], 'modified':['edit/SKILL.md']})
        self.assertEqual(report['skill_file_changes']['agent_skills'], {
            'status':'recorded', 'added':[], 'removed':[], 'modified':['link']})
        self.assertEqual(report['protected_drift'], ['skills'])
        self.assertFalse(report['qualified'])
        self.assertEqual(original, {p.name:p.read_bytes() for p in self.run.iterdir()})
        # Historical aggregate-only receipts stay unknown, never reconstructed
        # from the current installation or presented as an empty difference.
        del before['skill_files']
        self.write('before.json', before)
        report = guide.summary(self.run)
        self.assertEqual(report['skill_file_changes']['skills'], {'status':'not_recorded'})
        self.assertEqual(report['protected_drift'], ['skills'])
        self.assertFalse(report['qualified'])

    def test_plugin_delta_preserves_gate_and_unknown_history(self):
        before = {'identity':{'hashes':{'plugins':'before'}}, 'protected':{'plugins':'before'},
                  'plugin_files':{'edit':'old','remove':'gone','link':'link:old'}}
        after = {'identity':{'hashes':{'plugins':'after'}}, 'protected':{'plugins':'after'},
                 'plugin_files':{'edit':'new','add':'added','link':'link:new'}}
        self.write('before.json', before)
        self.write('after.json', after)
        original = {p.name:p.read_bytes() for p in self.run.iterdir()}
        report = guide.summary(self.run)
        self.assertEqual(report['plugin_file_changes'], {'status':'recorded', 'added':['add'],
                         'removed':['remove'], 'modified':['edit','link']})
        self.assertEqual(report['protected_drift'], ['plugins'])
        self.assertTrue(report['integration_identity_equal'])
        self.assertTrue(report['integration_protected_equal'])
        self.assertFalse(report['qualified'])
        self.assertEqual(original, {p.name:p.read_bytes() for p in self.run.iterdir()})
        del before['plugin_files']
        self.write('before.json', before)
        report = guide.summary(self.run)
        self.assertEqual(report['plugin_file_changes'], {'status':'not_recorded'})
        self.assertEqual(report['protected_drift'], ['plugins'])
        self.assertFalse(report['qualified'])

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

    def test_refused_launch_cli_reports_profile_ownership_without_echoing_logs(self):
        import subprocess
        import sys
        root = Path('/tmp/tofa-presentation-validation')
        root.mkdir(exist_ok=True, mode=0o700)
        with tempfile.TemporaryDirectory(dir=root) as temporary:
            run = Path(temporary)
            (run/'launcher.log').write_text('private unrelated diagnostic\n'
                'tofa: ordinary desktop profile is already owned or has an unresolved native lock. '
                'Quit Codex desktop before launching through tofa; resolve unrecognized profile ownership '
                'in the ordinary client first. No existing process was changed\n')
            dead = subprocess.Popen([sys.executable, '-c', 'pass'])
            dead.wait(timeout=3)
            result = subprocess.run([sys.executable, str(Path(__file__).with_name('desktop_qualification_guide.py')),
                                     str(run/'kit'),'ready',str(run),str(dead.pid)],capture_output=True,text=True,timeout=3)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Desktop profile is in use or has an unresolved native lock', result.stderr)
            self.assertNotIn('private unrelated diagnostic', result.stderr)
            report = guide.summary(run)
            self.assertEqual(report['launcher_refusal'], 'ordinary_profile_owned_or_unresolved_lock')
            self.assertFalse(report['qualified'])
            self.assertEqual(report['status'], 'incomplete_collection')
            self.assertIsNone(report['exit_code'])

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

    def test_retained_incomplete_run_reports_only_observed_launch_facts(self):
        # The retained 1c913081dad1d33a run had these records, but no finish or
        # after snapshot. An exit code cannot be recovered from a PID receipt.
        (self.run/'stop-reason.txt').write_text('launch_failed')
        self.write('requests.json', [])
        self.write('launcher-process.json', {'launcher_pid':123})
        report = guide.summary(self.run)
        self.assertEqual(report['stop'], 'launch_failed')
        self.assertEqual(report['failure_phase'], 'prelaunch')
        self.assertEqual(report['observer_requests'], 0)
        self.assertEqual(report['launcher_pid'], 123)
        self.assertIsNone(report['exit_code'])
        self.assertIsNone(report['protected_equal'])
        self.assertEqual(report['status'], 'incomplete_collection')
        self.assertFalse(report['qualified'])
        (self.run/'stop-reason.txt').write_text('private-untrusted-diagnostic')
        report = guide.summary(self.run)
        self.assertIsNone(report['stop'])
        self.assertNotIn('private-untrusted-diagnostic', json.dumps(report))

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

    def test_handoff_announces_declared_roles_and_keeps_invocations_durable(self):
        import subprocess
        script = Path(__file__).with_name('desktop_qualification_operator.sh').read_text()
        start = script.index('  stage "Prepare host Desktop"')
        end = script.index('  say "Allocating one fresh workspace', start)
        durable = self.run/'durable'
        durable.mkdir()
        fixture = ('set -euo pipefail\n'
                   'KIT="$1/temporary"; DURABLE="$1/durable"; REVISION=reviewed-revision; MODEL=another/main; GUARDIAN=another/reviewer\n'
                   'stage() { echo "$*"; }; say() { echo "$*"; }; step() { :; }; note() { :; }; confirm() { return 0; }\n'
                   'guide() { if [[ "$1" == field ]]; then echo 8; else echo "$INVOCATION"; fi; }\n'
                   'cleanup() { :; }\nrun() {\n' + script[start:end] + '\n}\nrun\n')
        result = subprocess.run(['bash','-c',fixture,'fixture',str(self.run)],capture_output=True,text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('reviewed-revision', result.stdout)
        self.assertIn('another/main', result.stdout)
        self.assertIn('another/reviewer', result.stdout)
        self.assertNotIn('372255f', result.stdout)
        self.assertEqual(len(list((durable/'invocations').glob('guide.*'))), 1)
        self.assertFalse((self.run/'temporary/invocations').exists())

    def test_failed_prepare_reports_a_visible_error(self):
        import subprocess
        script = Path(__file__).with_name('desktop_qualification_operator.sh').read_text()
        # Execute the real guide's prepare boundary with a failing fixture.
        start = script.rfind('\n', 0, script.index('if guide prepare')) + 1
        end = script.index('\n  RUN=$(', start)
        fixture = ('set -euo pipefail\n'
                   'INVOCATION="$1"; KIT=unused; CANDIDATE=unused; runtime=unused\n'
                   'guide() { false; }; warn() { echo "$*" >&2; }\n'
                   'cleanup() { echo cleanup; }; trap cleanup EXIT\nrun() {\n' + script[start:end] + '\n}\nrun\n')
        result = subprocess.run(['bash','-c',fixture,'fixture',str(self.run)],capture_output=True,text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.run/'prepare.json').read_text(), '')
        self.assertIn('cleanup',result.stdout)
        self.assertIn('Preparation failed before launch', result.stderr)


    def test_workspace_setup_confirmation_precedes_freeze_and_launch(self):
        import subprocess
        script=Path(__file__).with_name('desktop_qualification_operator.sh').read_text()
        start=script.index('  RUN=$(')
        end=script.index('  say "Recording hashes',start)
        fragment=script[start:end]
        self.write('prepare.json',{'run':str(self.run/'attempt')})
        fixture=('set -euo pipefail\n'
            'INVOCATION="$1"; PYTHON=/usr/bin/python3; EVENTS="$1/events"\n'
            'say() { :; }; step() { :; }; stage() { :; }; warn() { :; }\n'
            'confirm() { echo confirm >> "$EVENTS"; return "$CONFIRM_RC"; }\n'
            'collect() { echo "$*" >> "$EVENTS"; return "$FREEZE_RC"; }\n'
            'run() {\n'+fragment+'\n}\nrun\n')
        # The actual guidance boundary must require a positive setup response;
        # EOF/cancellation and failed snapshots must never start collection.
        for confirmed,freeze_rc in ((0,0),(1,0),(0,1)):
            with self.subTest(confirmed=confirmed,freeze_rc=freeze_rc):
                (self.run/'events').write_text('')
                result=subprocess.run(['bash','-c',fixture,'fixture',str(self.run)],
                    env={**os.environ,'CONFIRM_RC':str(confirmed),'FREEZE_RC':str(freeze_rc)},
                    capture_output=True,text=True)
                events=(self.run/'events').read_text().splitlines()
                self.assertTrue(events and events[0]=='confirm', 'workspace setup must be confirmed before snapshot')
                if confirmed: self.assertEqual(events,['confirm'])
                else: self.assertEqual(events,['confirm','freeze '+str(self.run/'attempt')])
                if confirmed or freeze_rc: self.assertNotEqual(result.returncode,0)
                else: self.assertEqual(result.returncode,0,result.stderr)

    def test_summary_reports_drift_keys_without_claiming_qualification(self):
        self.write('before.json', {'identity':{'hashes':{'runtime':'old'}}, 'protected':{'config.toml':'old'}})
        self.write('after.json', {'identity':{'hashes':{'runtime':'new'}}, 'protected':{'config.toml':'new'}})
        self.write('finish.json', {'stop':'operator_finished','exit_code':0})
        result = guide.summary(self.run)
        self.assertEqual(result['identity_drift'], ['runtime'])
        self.assertEqual(result['protected_drift'], ['config.toml'])
        self.assertFalse(result['qualified'])

    def test_summary_names_all_identity_differences_without_private_values_or_keys(self):
        before = {'source_revision':'old', 'home':'/private/home-before',
                  'hashes':{'engine':'old', 'harness/private-script.py':'old', 'private-key':'old'}}
        after = {'source_revision':'new', 'home':'/private/home-after',
                 'hashes':{'engine':'new', 'harness/private-script.py':'new', 'private-key':'new'}}
        self.write('before.json', {'identity':before, 'protected':{}})
        self.write('prelaunch.json', {'identity':after, 'protected':{}})
        report = guide.summary(self.run)
        self.assertFalse(report['identity_equal'])
        self.assertEqual(report['identity_drift'], ['engine','harness','home','identity metadata','source'])
        self.assertNotIn('private-', json.dumps(report))
        for field, label in [('profile','profile'), ('runtime_root','runtime root'), ('harness_root','harness root'),
                             ('private-unknown','identity metadata')]:
            with self.subTest(field=field):
                self.write('before.json', {'identity':{field:'private-old'}, 'protected':{}})
                self.write('prelaunch.json', {'identity':{field:'private-new'}, 'protected':{}})
                report = guide.summary(self.run)
                self.assertEqual(report['identity_drift'], [label])
                self.assertNotIn('private-', json.dumps(report))

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
