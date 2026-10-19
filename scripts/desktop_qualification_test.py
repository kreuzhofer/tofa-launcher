"""Offline qualification collector contracts; never launches native Desktop."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import desktop_qualification as q


class QualificationTests(unittest.TestCase):
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
                reason='scope_mismatch';records=[];stop_acknowledged=True
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
