"""Offline qualification collector contracts; never launches native Desktop."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
import contextlib
import io
import sys
from unittest.mock import patch
from types import SimpleNamespace

import desktop_qualification as q


class QualificationTests(unittest.TestCase):
    def deferred_attempt(self, root):
        (root/'runs').mkdir(mode=0o700)
        services=root/'services.json'
        q.save(services, {'zai-org/GLM-5.3':'token_factory'})
        options=SimpleNamespace(launcher=root/'launcher',app_bundle=root/'unused',
            runtime_root=root/'unused',source_revision='a'*40,case='clean-exit',
            model='zai-org/GLM-5.3',guardian='zai-org/GLM-5.3-Flash',seconds=600,
            requests=2,output_tokens=100,model_services=services,scope=None,
            prompt='Reply exactly: fixture-ok.',defer_snapshot=True)
        output=io.StringIO()
        with contextlib.redirect_stdout(output): q.prepare(options)
        return Path(json.loads(output.getvalue())['run'])

    def test_workspace_setup_precedes_immutable_baseline(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, unused, initial=self.refused_attempt(temporary)
            with patch.object(q,'ROOT',root):
                run=self.deferred_attempt(root)
                self.assertTrue((run/'workspace').is_dir())
                self.assertFalse((run/'before.json').exists(), 'baseline captured before workspace trust setup')
                self.assertFalse((run/'launcher-process.json').exists())
                ready={**initial,'protected':{'fixture':'trusted workspace'}}
                (root/'snapshot.json').write_text(json.dumps(ready))
                with contextlib.redirect_stdout(io.StringIO()): q.freeze(run)
                self.assertEqual(q.read(run/'before.json'),ready)
                with self.assertRaisesRegex(ValueError,'baseline_already_frozen'): q.freeze(run)
                with contextlib.redirect_stdout(io.StringIO()): q.launch(run)
                self.assertEqual(q.read(run/'finish.json')['stop'],'launch_failed')
                self.assertEqual(q.read(run/'before.json'),q.read(run/'after.json'))

    def test_deferred_setup_still_rejects_post_baseline_drift(self):
        with tempfile.TemporaryDirectory() as temporary:
            root,unused,initial=self.refused_attempt(temporary)
            with patch.object(q,'ROOT',root):
                run=self.deferred_attempt(root)
                with contextlib.redirect_stdout(io.StringIO()): q.freeze(run)
                (root/'snapshot.json').write_text(json.dumps({**initial,'protected':{'fixture':'changed'}}))
                with contextlib.redirect_stdout(io.StringIO()):
                    with self.assertRaisesRegex(ValueError,'environment_drift'): q.launch(run)
                self.assertFalse((run/'launcher-process.json').exists())
                with self.assertRaisesRegex(ValueError,'attempt_consumed'): q.freeze(run)
                self.assertEqual(q.read(run/'before.json'),initial)

    def test_deferred_setup_cannot_launch_without_baseline(self):
        with tempfile.TemporaryDirectory() as temporary:
            root,unused,initial=self.refused_attempt(temporary)
            with patch.object(q,'ROOT',root):
                run=self.deferred_attempt(root)
                with contextlib.redirect_stdout(io.StringIO()):
                    with self.assertRaises(ValueError): q.launch(run)
                self.assertFalse((run/'launcher-process.json').exists())
                with self.assertRaisesRegex(ValueError,'attempt_consumed'): q.freeze(run)

    def refused_attempt(self, temporary):
        root = Path(temporary).resolve()
        launcher = root/'launcher'
        launcher.write_text('#!'+sys.executable+'\n'+
            (Path(__file__).parent/'fixtures/qualification-launcher.py').read_text())
        launcher.chmod(0o700)
        (root/'refuse-launch').touch()
        frozen = {'identity':{'profile':str(root/'profile')}, 'protected':{'fixture':'unchanged'}}
        q.save(root/'snapshot.json', frozen)
        run = root/'refused'; run.mkdir(mode=0o700); (run/'workspace').mkdir(mode=0o700)
        q.save(run/'before.json', frozen)
        q.save(run/'plan.json', {'launcher':str(launcher), 'app_bundle':str(root/'unused'),
            'runtime_root':str(root/'unused'), 'source_revision':'a'*40, 'case':'clean-exit',
            'model':'moonshotai/Kimi-K3', 'guardian':'zai-org/GLM-5.3-Flash',
            'seconds':600, 'requests':2, 'output_tokens':100,
            'model_services':{'moonshotai/Kimi-K3':'token_factory'}, 'scope':None})
        return root, run, frozen

    def test_snapshot_failure_retains_original_launch_outcome(self):
        import desktop_qualification_guide as guide
        with tempfile.TemporaryDirectory() as temporary:
            root, run, frozen = self.refused_attempt(temporary)
            (root/'fail-after-snapshot').touch()
            with patch.object(q, 'ROOT', root), contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(ValueError): q.launch(run)
            report = guide.summary(run)
            self.assertEqual(report['stop'], 'launch_failed')
            self.assertEqual(report['exit_code'], 7)
            self.assertEqual(report['observer_requests'], 0)
            self.assertEqual(report['launcher_refusal'], 'ordinary_profile_owned_or_unresolved_lock')
            self.assertEqual(report['status'], 'incomplete_collection')
            self.assertEqual(report['collection_errors'], [{'phase':'after_snapshot', 'reason':'snapshot_failed'}])
            self.assertIsNone(report['protected_equal'])
            self.assertFalse(report['qualified'])
            self.assertNotIn('private-fixture-diagnostic', json.dumps(report))
            self.assertFalse((run/'finish.json').exists())
            self.assertTrue((run/'collection-error.log').is_file())

    def test_drain_failure_retains_launch_failure_and_unknown_request_count(self):
        import desktop_qualification_guide as guide
        with tempfile.TemporaryDirectory() as temporary:
            root, run, frozen = self.refused_attempt(temporary)
            (root/'break-observer-drain').touch()
            with patch.object(q, 'ROOT', root), contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(ValueError): q.launch(run)
            report = guide.summary(run)
            self.assertEqual(report['stop'], 'launch_failed')
            self.assertEqual(report['exit_code'], 7)
            self.assertIsNone(report['observer_requests'])
            self.assertEqual(report['collection_errors'], [{'phase':'observer_drain', 'reason':'observer_drain_failed'}])
            self.assertTrue(report['protected_equal'])
            self.assertFalse(report['qualified'])
            self.assertFalse((run/'finish.json').exists())

    def test_missing_route_after_handoff_is_still_a_collection_failure(self):
        import desktop_qualification_guide as guide
        with tempfile.TemporaryDirectory() as temporary:
            root, run, frozen = self.refused_attempt(temporary)
            (root/'missing-route-after-handoff').touch()
            with patch.object(q, 'ROOT', root), contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(ValueError): q.launch(run)
            report = guide.summary(run)
            self.assertEqual(report['collection_errors'], [{'phase':'route_stop', 'reason':'route_stop_probe_failed'}])
            self.assertFalse(report['qualified'])
            self.assertFalse((run/'finish.json').exists())
            self.assertFalse((run/'route-stop.json').exists())

    def test_launch_refusal_is_collected_before_route_registration(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, run, frozen = self.refused_attempt(temporary)
            with patch.object(q, 'ROOT', root), contextlib.redirect_stdout(io.StringIO()):
                q.launch(run)
            finish = q.read(run/'finish.json')
            self.assertEqual(finish['stop'], 'launch_failed')
            self.assertEqual(finish['exit_code'], 7)
            self.assertTrue(finish['process_exited_before_stop'])
            self.assertEqual(finish['observer_requests'], 0)
            self.assertFalse(finish['qualified'])
            self.assertEqual(q.read(run/'after.json'), frozen)
            self.assertFalse((run/'route-stop.json').exists())
            self.assertFalse((run/'start.json').exists())
            for name in ('collection.json','launch-outcome.json','finish.json'):
                self.assertEqual((run/name).stat().st_mode & 0o777, 0o600)

    def test_refusal_guide_cli_keeps_safe_reason_and_durable_evidence(self):
        import subprocess
        root = q.ROOT; root.mkdir(mode=0o700, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as temporary:
            fixture_root, run, frozen = self.refused_attempt(temporary)
            with contextlib.redirect_stdout(io.StringIO()): q.launch(run)
            script = str(Path(__file__).with_name('desktop_qualification_guide.py'))
            kit = fixture_root/'kit'; kit.mkdir(mode=0o700)
            command = [sys.executable, script, str(kit)]
            ready = subprocess.run(command+['ready',str(run),'99999999'], capture_output=True, text=True, timeout=3)
            self.assertNotEqual(ready.returncode, 0)
            self.assertIn('Desktop profile is in use', ready.stderr)
            result = subprocess.run(command+['summarize',str(run)], capture_output=True, text=True, timeout=3)
            self.assertEqual(result.returncode, 0, result.stderr)
            archive = kit/'evidence'/run.name
            summary = json.loads((archive/'guide-summary.json').read_text())
            self.assertEqual(summary['durable_evidence'], str(archive))
            self.assertEqual(summary['failure_phase'], 'prelaunch')
            self.assertEqual(summary['stop'], 'launch_failed')
            self.assertEqual(summary['exit_code'], 7)
            self.assertTrue(summary['protected_equal'])
            self.assertFalse(summary['qualified'])
            self.assertNotIn('private-fixture-diagnostic', result.stdout+ready.stderr)
            for name in ('launcher.log','before.json','after.json','launch-outcome.json','collection.json'):
                self.assertEqual((archive/name).read_bytes(), (run/name).read_bytes())

    def test_drift_before_observer_retains_comparison_and_consumes_attempt(self):
        import desktop_qualification_guide as guide
        with tempfile.TemporaryDirectory() as temporary:
            root, run, frozen = self.refused_attempt(temporary)
            (root/'snapshot.json').write_text(json.dumps({**frozen, 'protected':{'fixture':'changed'}}))
            with patch.object(q, 'ROOT', root):
                with self.assertRaisesRegex(ValueError, 'environment_drift'): q.launch(run)
                report = guide.summary(run)
                self.assertEqual(report['failure_phase'], 'prelaunch_snapshot')
                self.assertEqual(report['collection_errors'],
                    [{'phase':'prelaunch_snapshot', 'reason':'environment_drift_before_launch'}])
                self.assertEqual(report['protected_drift'], ['fixture'])
                self.assertFalse(report['protected_equal'])
                self.assertIsNone(report['exit_code'])
                self.assertIsNone(report['observer_requests'])
                self.assertFalse(report['qualified'])
                self.assertFalse((run/'launcher-process.json').exists())
                with self.assertRaisesRegex(ValueError, 'attempt_consumed'): q.launch(run)

    def test_cancel_before_route_retains_stop_without_claiming_route_proof(self):
        import desktop_qualification_guide as guide
        with tempfile.TemporaryDirectory() as temporary:
            root, run, frozen = self.refused_attempt(temporary)
            (root/'refuse-launch').unlink()
            (root/'cancel-before-route').touch()
            with patch.object(q, 'ROOT', root), contextlib.redirect_stdout(io.StringIO()):
                q.launch(run)
            report = guide.summary(run)
            self.assertEqual(report['stop'], 'operator_cancelled')
            self.assertFalse(report['qualified'])
            self.assertEqual(report['observer_requests'], 0)
            self.assertFalse((run/'route-stop.json').exists())
            self.assertFalse(q.read(run/'collection.json')['route_registered'])

    def test_launch_creates_private_exclusive_log_and_stops_owned_process(self):
        # Actual launch orchestration, Observer and subprocesses. Only the
        # launcher/native application are task-owned fixtures; Path.open and
        # Popen are not replaced.
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve()
            launcher=root/'launcher'
            fixture=(Path(__file__).parent/'fixtures/qualification-launcher.py').read_text()
            launcher.write_text('#!'+sys.executable+'\n'+fixture)
            launcher.chmod(0o700)
            profile=root/'profile';profile.mkdir(mode=0o700)
            frozen={'identity':{'profile':str(profile)},'protected':{'fixture':'unchanged'}}
            q.save(root/'snapshot.json',frozen)
            def attempt(name):
                run=root/name;run.mkdir(mode=0o700);(run/'workspace').mkdir(mode=0o700)
                q.save(run/'before.json',frozen)
                q.save(run/'plan.json',{'launcher':str(launcher),'app_bundle':str(root/'unused'),
                    'runtime_root':str(root/'unused'),'source_revision':'a'*40,'case':'clean-exit',
                    'model':'moonshotai/Kimi-K3','guardian':'zai-org/GLM-5.3-Flash',
                    'seconds':600,'requests':2,'output_tokens':100,
                    'model_services':{'moonshotai/Kimi-K3':'token_factory'},'scope':None})
                return run
            run=attempt('successful')
            old_umask=os.umask(0o022)
            try:
                with patch.object(q,'ROOT',root),contextlib.redirect_stdout(io.StringIO()):
                    q.launch(run)
            finally:
                os.umask(old_umask)
            log=run/'launcher.log'
            self.assertEqual(log.stat().st_mode & 0o777,0o600)
            self.assertIn('owned launcher stdout',log.read_text())
            self.assertIn('owned launcher stderr',log.read_text())
            process=q.read(run/'process.json');stop=q.read(run/'fixture-stop.json')
            self.assertEqual(process['launcher_pid'],stop['launcher_pid'])
            self.assertEqual(process['native_pid'],stop['child_pid'])
            for pid in (process['launcher_pid'],process['native_pid']):
                with self.assertRaises(ProcessLookupError):os.kill(pid,0)
            finish=q.read(run/'finish.json')
            self.assertEqual((finish['stop'],finish['exit_code']),('operator_finished',0))
            self.assertTrue(finish['stop_acknowledged'])
            self.assertFalse(finish['process_exited_before_stop'])
            self.assertFalse(finish['qualified'])
            self.assertEqual(q.read(run/'requests.json'),[])
            self.assertEqual(q.read(run/'after.json'),frozen)
            blocked=attempt('existing-log')
            (blocked/'launcher.log').write_text('retain existing log')
            with patch.object(q,'ROOT',root),self.assertRaises(FileExistsError):
                q.launch(blocked)
            self.assertEqual((blocked/'launcher.log').read_text(),'retain existing log')
            self.assertFalse((blocked/'launcher-process.json').exists())
            import desktop_qualification_guide as guide
            report = guide.summary(blocked)
            self.assertEqual(report['status'], 'incomplete_collection')
            self.assertEqual(report['failure_phase'], 'launcher_start')
            self.assertIsNone(report['exit_code'])
            self.assertFalse(report['qualified'])

    def test_records_are_private_exclusive_and_ambiguous_json_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'record.json'
            q.save(path, {'one': 1})
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError): q.save(path, {'one': 2})
            path.write_text('{"one":1,"one":2}')
            with self.assertRaisesRegex(ValueError, 'duplicate'): q.read(path)

    def test_finish_does_not_grant_pass_or_retry(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); run = root / 'attempt'; run.mkdir(mode=0o700)
            with patch.object(q, 'ROOT', root):
                q.control(SimpleNamespace(run=run, action='finish'))
                self.assertEqual(set(q.read(run / 'finish.request')), {'requested_utc'})
                with self.assertRaises(FileExistsError): q.control(SimpleNamespace(run=run, action='finish'))

    def test_crash_requires_declared_case(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); run=root/'attempt';run.mkdir(mode=0o700)
            q.save(run/'plan.json', {'case':'clean-exit'})
            with patch.object(q,'ROOT',root), self.assertRaisesRegex(ValueError,'crash_not_declared'):
                q.control(SimpleNamespace(run=run,action='launcher-crash'))

    def test_symlink_parent_cannot_redirect_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); target=root/'target';target.mkdir(mode=0o700)
            link=root/'link';link.symlink_to(target,target_is_directory=True)
            child=target/'child';child.mkdir(mode=0o700)
            with patch.object(q,'ROOT',root), self.assertRaisesRegex(ValueError,'symlink'):
                q.private_run(link/'child')

    def test_stopped_route_receipt_is_from_both_owned_capability_probes(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as temporary:
            run=Path(temporary)
            observer=SimpleNamespace(endpoint='http://127.0.0.1:4321',inference_token='private-inference',token='private-control')
            class Closed:
                def __init__(self,*args,**kwargs):pass
                def request(self,*args,**kwargs):raise ConnectionRefusedError()
                def close(self):pass
            with patch.object(q.http.client,'HTTPConnection',Closed):q.probe_stopped_route(run,observer,123)
            receipt=q.read(run/'route-stop.json')
            self.assertEqual(receipt['inference'],{'http_status':0,'socket_closed':True})
            self.assertEqual(receipt['control'],receipt['inference'])
            self.assertNotIn('private-',(run/'route-stop.json').read_text())

    def test_calibration_declaration_binds_current_snapshot_and_has_ten_minutes(self):
        from types import SimpleNamespace
        from datetime import datetime
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);run=root/'attempt';run.mkdir(mode=0o700)
            frozen={'schema':'tofa-native-account-snapshot-v1','identity':{'source_revision':'a'*40},'protected':{'auth':'before'}}
            q.save(root/'snapshot.json',frozen)
            options=SimpleNamespace(native_account_snapshot=root/'snapshot.json',launcher=root/'tofa',app_bundle=root/'App',runtime_root=root/'runtime')
            with patch.object(q,'ROOT',root), patch.object(q,'snapshot',return_value=frozen):
                plan=q.prepare_calibration(run,options,{'seconds':600,'requests':8})
            declaration=q.read(run/'declaration.json')
            self.assertEqual(declaration['identity'],frozen['identity'])
            self.assertEqual(declaration['case'],'runtime-preview')
            self.assertEqual(declaration['attempt'],run.name)
            self.assertEqual((datetime.fromisoformat(declaration['expires_utc'].replace('Z','+00:00'))-datetime.fromisoformat(declaration['issued_utc'].replace('Z','+00:00'))).total_seconds(),600)
            self.assertEqual(plan['source_revision'],'a'*40)
            with patch.object(q,'ROOT',root), patch.object(q,'snapshot',return_value={**frozen,'identity':{'source_revision':'b'*40}}), self.assertRaisesRegex(ValueError,'identity_drift'):
                q.prepare_calibration(run,options,{'seconds':600,'requests':8})

    def test_finish_preserves_prior_failure_and_drains_before_receipts(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as temporary:
            run=Path(temporary)
            class Observer:
                reason='scope_mismatch';records=[];stop_acknowledged=True;endpoint='http://127.0.0.1:4321'
                def __exit__(self,*unused):
                    self.records.append({'failure':'scope_mismatch'})
                    q.save(run/'requests.json',self.records)
            observer=Observer();process=SimpleNamespace(returncode=1,pid=123)
            with patch.object(q,'snapshot',return_value={'identity':{},'protected':{}}),patch.object(q,'probe_stopped_route'):
                q.finish_collection(run,{},process,observer,'operator_finished',False)
            finish=q.read(run/'finish.json')
            self.assertEqual(finish['stop'],'scope_mismatch')
            self.assertEqual(finish['observer_stop'],'scope_mismatch')
            self.assertEqual(finish['observer_requests'],1)
            self.assertEqual(len(q.read(run/'requests.json')),1)
            self.assertFalse(finish['qualified'])

    def test_record_uses_immutable_receipts_and_never_grants_pass(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);run=root/'attempt';run.mkdir(mode=0o700)
            records={'before.json':{'identity':{'binary':'a'},'protected':{'auth':'x'}},'after.json':{'identity':{'binary':'a'},'protected':{'auth':'x'}},
                     'declaration.json':{'case':'clean-exit','attempt':'attempt'},'start.json':{'started_utc':'start'},
                     'finish.json':{'finished_utc':'finish','stop':'operator_finished'},'process.json':{'launcher_pid':123},'requests.json':[],
                     'facts.json':{'raw':[],'history_before':{},'history_after':{}}}
            for name,value in records.items():q.save(run/name,value)
            with patch.object(q,'ROOT',root):q.record(SimpleNamespace(run=run,facts=run/'facts.json'))
            case=q.read(run/'case.json')
            self.assertEqual(case['process_receipt']['sha256'],q.digest(run/'process.json'))
            self.assertEqual(case['protected_before'],{'auth':'x'})
            self.assertFalse(q.read(run/'export.json')['qualified'])

if __name__ == '__main__': unittest.main()
