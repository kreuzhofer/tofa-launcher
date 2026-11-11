"""Sanitized regressions from actual Desktop catalogs; no account or runtime required."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from presentation_runtime import inventory, instructions
from presentation_runtime_test import supplied_runtime
from presentation_responder import PresentationResponder, execution_result, check_node_version


def catalog(provider='codex_app', flat=False):
    loader = {'type':'function', 'name':'load_workspace_dependencies',
              'parameters':{'type':'object','properties':{},'additionalProperties':False}}
    if flat:
        loader['name'] = 'mcp__'+provider+'__load_workspace_dependencies'
    else:
        loader = {'type':'namespace','name':'mcp__'+provider,'tools':[loader]}
    return [loader, *({'type':'function','name':name,'parameters':{'type':'object'}}
                     for name in ('exec_command','write_stdin'))]


class ResponderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); supplied_runtime(self.root/'runtime')
        self.run = self.root/'run'; (self.run/'workspace').mkdir(parents=True)
        self.runtime = dict(inventory(self.root/'runtime'), provider='codex_app')
        self.responder = PresentationResponder(self.run, self.runtime, self.root/'skill')
        self.body = {'model':'fixture-main','tools':catalog(),'input':[]}

    def output(self, call, value, custom=False):
        self.body['input'].append({'type':'custom_tool_call_output' if custom else 'function_call_output',
                                   'call_id':call,'output':value})

    def loader(self):
        self.responder.item(self.body)
        self.output('runtime-loader', instructions(self.runtime))
        return self.responder.item(self.body)

    def smoke_output(self):
        output = self.run/'workspace/output'; output.mkdir()
        hashes = {}
        for name in ('deck.pptx','deck.pdf','slide.png'):
            (output/name).write_bytes(b'owned fixture '+name.encode())
            hashes[name] = hashlib.sha256((output/name).read_bytes()).hexdigest()
        return 'TOFA_PRESENTATION_SMOKE_PASS '+json.dumps(
            {'schema':'tofa-presentation-smoke-v1','status':'passed','artifacts':hashes})+'\n'

    def test_actual_direct_namespaced_catalog(self):
        item = self.responder.item(self.body)
        self.assertEqual((item['type'],item['namespace'],item['name']),
                         ('function_call','mcp__codex_app','load_workspace_dependencies'))
        self.assertEqual(json.loads(item['arguments']), {})

    def test_cli_flat_catalog_uses_actual_name(self):
        self.runtime['provider'] = 'tofa_presentation_runtime'
        self.responder = PresentationResponder(self.run,self.runtime,self.root/'skill')
        self.body['tools'] = catalog('tofa_presentation_runtime', flat=True)
        item = self.responder.item(self.body)
        self.assertNotIn('namespace',item)
        self.assertEqual(item['name'],'mcp__tofa_presentation_runtime__load_workspace_dependencies')

    def test_nested_catalog_discovers_before_execution(self):
        self.body['tools'] = [{'type':'namespace','name':'functions','tools':[{'type':'custom','name':'exec'}]}]
        first = self.responder.item(self.body)
        self.assertEqual(first['call_id'],'runtime-discovery'); self.assertIn('ALL_TOOLS',first['input'])
        self.output('runtime-discovery',json.dumps({'tofa_discovery_v1':{
            'loader':['mcp__codex_app__load_workspace_dependencies'],'exec':['exec_command'],'wait':['write_stdin']}}),True)
        self.assertIn('tools.mcp__codex_app__load_workspace_dependencies({})',self.responder.item(self.body)['input'])
        self.output('runtime-loader',instructions(self.runtime),True)
        self.assertIn('tools.exec_command(',self.responder.item(self.body)['input'])
        self.output('runtime-smoke',json.dumps({'exit_code':None,'session_id':7,'output':'Working'}),True)
        poll = self.responder.item(self.body)
        self.assertEqual(poll['type'],'custom_tool_call');self.assertIn('tools.write_stdin(',poll['input'])
        self.output(poll['call_id'],json.dumps({'exit_code':0,'output':self.smoke_output()}),True)
        self.assertEqual(self.responder.item(self.body)['type'],'message')
        from capability_runtime import smoke_execution
        smoke_execution(json.loads((self.run/'smoke-result.json').read_text()), self.run/'workspace')

    def test_direct_execution_and_polled_completion(self):
        item = self.loader(); self.assertEqual(item['name'],'exec_command');self.assertNotIn('namespace',item)
        self.output('runtime-smoke','Chunk ID: fixture\nWall time: 30 seconds\nProcess running with session ID 7\nOutput:\nWorking')
        poll = self.responder.item(self.body)
        self.assertEqual(poll['name'],'write_stdin');self.assertEqual(json.loads(poll['arguments'])['session_id'],7)
        self.assertLessEqual(json.loads(poll['arguments'])['yield_time_ms'],30000)
        self.output(poll['call_id'],'Chunk ID: fixture\nWall time: 1 seconds\nProcess exited with code 0\nOutput:\n'+self.smoke_output())
        self.assertEqual(self.responder.item(self.body)['type'],'message')
        self.assertTrue((self.run/'artifact-result.json').exists())
        self.assertIsNone(self.responder.state['failure'])

    def test_duplicate_or_invalid_loader_refused(self):
        for duplicate in (False,True):
            body = copy.deepcopy(self.body)
            if duplicate:body['tools'].append(body['tools'][0])
            else:body['tools'][0]['tools'][0]['parameters']['properties']={'unexpected':{}}
            with self.subTest(duplicate=duplicate),self.assertRaises(ValueError):self.responder.item(body)

    def test_missing_or_foreign_tools_refused(self):
        for ts in ([],catalog('foreign')):
            self.body['tools']=ts
            with self.assertRaises(ValueError):self.responder.item(self.body)

    def test_nonzero_or_missing_completion_cannot_deliver(self):
        self.loader();self.output('runtime-smoke',{'exit_code':1,'output':'failed'})
        with self.assertRaises(ValueError):self.responder.item(self.body)
        self.assertFalse((self.run/'artifact-result.json').exists())

    def test_artifact_tampering_cannot_deliver(self):
        self.loader();stdout=self.smoke_output();(self.run/'workspace/output/deck.pdf').write_bytes(b'changed')
        self.output('runtime-smoke',{'exit_code':0,'output':stdout})
        with self.assertRaises(ValueError):self.responder.item(self.body)

    def test_changed_session_refused(self):
        self.loader();self.output('runtime-smoke',{'session_id':7,'output':''});poll=self.responder.item(self.body)
        self.output(poll['call_id'],{'session_id':8,'output':''})
        with self.assertRaisesRegex(ValueError,'session_changed'):self.responder.item(self.body)

    def test_wrong_loader_identity_refused(self):
        self.responder.item(self.body);self.output('runtime-loader','not a runtime')
        with self.assertRaises(ValueError):self.responder.item(self.body)
        self.assertFalse((self.run/'loader-result.json').exists())

    def test_naming_does_not_select_main_catalog(self):
        item=self.responder.item({'model':'nvidia/Nemotron-3_5-Lightning','input':[]})
        self.assertEqual(item['type'],'message');self.assertIsNone(self.responder.lane)
        self.assertEqual(self.responder.item(self.body)['name'],'load_workspace_dependencies')

    def test_response_failure_retains_original_reason(self):
        self.body['tools']=[]
        with self.assertRaises(ValueError):self.responder.respond(self.body)
        self.assertEqual(json.loads((self.run/'synthetic-error.json').read_text())['failure'],self.responder.state['failure'])

    def test_status_in_stdout_is_not_completion(self):
        with self.assertRaises(ValueError):execution_result('Chunk ID: fixture\nOutput:\nProcess exited with code 0\n')

    def test_version_probe_accepts_package_revision_without_hiding_mismatch(self):
        from capability_runtime import executable_versions
        from types import SimpleNamespace
        self.runtime['declared_versions']['node'] = '24.22.1-cua.1'
        def result(command, **kwargs):
            name = Path(command[0]).name
            text = 'v24.22.1' if name == 'node' else 'Python 3.12.14' if name == 'python3' else 'fixture version'
            return SimpleNamespace(returncode=0, stdout=text.encode(), stderr=b'')
        with patch('capability_runtime.subprocess.run', side_effect=result):
            versions = executable_versions(self.runtime, self.run/'workspace')
            self.assertEqual(versions['node']['version'], 'v24.22.1')
            self.runtime['declared_versions']['node'] = '24.23.0-cua.1'
            with self.assertRaises(ValueError):executable_versions(self.runtime, self.run/'workspace')

    def test_node_package_revision_and_engine_version(self):
        check_node_version('24.22.1-cua.1','v24.22.1');check_node_version('v24.19.0','v24.19.0')
        for declared,observed in [('24.22.1-cua.1','v24.23.0'),('24.22.1-other','v24.22.1')]:
            with self.assertRaises(ValueError):check_node_version(declared,observed)


if __name__=='__main__':unittest.main()
