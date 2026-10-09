"""Behavioral tests for the throwaway evaluator's command boundary."""
import json
import http.server
import os
import threading
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).with_name('pilot.py')

class PilotTest(unittest.TestCase):
    def command(self, *args):
        run = subprocess.run([sys.executable, str(SCRIPT), *args], text=True, capture_output=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        return json.loads(run.stdout)

    def replay(self, events):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'trace.jsonl'
            path.write_text(''.join(json.dumps(event) + '\n' for event in events))
            return self.command('replay', str(path))

    def test_stops_at_fifth_unchanged_read_without_exposing_trace(self):
        events = [{'tool': 'exec_command', 'command': 'cat synthetic-private-file',
                   'output': 'synthetic-private-output', 'exit_code': 0} for _ in range(6)]
        result = self.replay(events)
        self.assertEqual(result['stop_after_action'], 5)
        self.assertEqual(result['reason'], 'repeated_action_without_progress')
        self.assertNotIn('synthetic-private', json.dumps(result))

    def test_native_trace_detects_expanding_xml_window_with_unchanged_output(self):
        events = []
        for index in range(6):
            cmd = ('import zipfile, re\nz = zipfile.ZipFile("probe2.pptx")\n'
                   's = z.read("ppt/slides/slide1.xml").decode()\n'
                   'i = s.index("</p:xfrm>")\n'
                   f'print(s[max(0,i-{1000 + index * 100}):i+20])')
            events.extend([
                {'type': 'response_item', 'payload': {'type': 'function_call', 'name': 'exec_command',
                    'call_id': str(index), 'arguments': json.dumps({'cmd': cmd})}},
                {'type': 'response_item', 'payload': {'type': 'function_call_output',
                    'call_id': str(index), 'output': f'Chunk ID: {index}\nProcess exited with code 0\nOutput:\n<same-xml/>'}},
            ])
        result = self.replay(events)
        self.assertEqual(result['stop_after_action'], 5)
        self.assertEqual(result['action_family'], 'expanding_xml_inspection')

    def test_polling_changed_output_and_distinct_actions_do_not_trigger(self):
        for events in (
            [{'tool': 'write_stdin', 'command': '', 'output': '', 'exit_code': 0}] * 9,
            [{'tool': 'exec_command', 'command': 'cat status', 'output': str(i), 'exit_code': 0} for i in range(9)],
            [{'tool': 'exec_command', 'command': f'cat part-{i}', 'output': 'same', 'exit_code': 0} for i in range(9)],
        ):
            self.assertEqual(self.replay(events)['reason'], 'no_loop_observed')

    def test_valid_file_missing_skill_and_pending_preview_are_independent(self):
        with tempfile.TemporaryDirectory() as directory:
            evidence = Path(directory) / 'evidence.json'
            evidence.write_text(json.dumps({'artifact_valid': True, 'skill_read': False,
                'citation_valid': True, 'ui_opened': None, 'client': 'desktop'}))
            result = self.command('score', str(evidence))
        self.assertEqual(result['task_artifact']['status'], 'passed')
        self.assertEqual(result['workflow_skill']['status'], 'failed')
        self.assertEqual(result['delivery_reference']['status'], 'passed')
        self.assertEqual(result['delivery_ui'], {'status': 'not_run', 'reason': 'ui_check_pending'})
        self.assertNotIn('supported', result)

    def test_plan_has_24_unrun_cells_with_case_specific_limits(self):
        result = self.command('plan')
        self.assertEqual(len(result['runs']), 24)
        self.assertEqual(len({r['id'] for r in result['runs']}), 24)
        for run in result['runs']:
            self.assertEqual(run['status'], 'not_run')
            self.assertEqual(run['limits']['seconds'], 900 if run['case'] in ('03', '04') else 180)
            self.assertEqual(run['limits']['repeated_actions'], 5)
        self.assertEqual(result['prompts']['04'],
            'Use the installed presentation skill; read its instructions before creating the deck. '
            + result['prompts']['03'])

    def test_supervisor_stops_a_live_child_on_fifth_repetition(self):
        with tempfile.TemporaryDirectory() as directory:
            child = Path(directory) / 'fake_client.py'
            child.write_text("import json,time\n" +
                "event={'type':'item.completed','item':{'type':'command_execution','command':'cat fixture','aggregated_output':'same','exit_code':0}}\n" +
                "for i in range(6): print(json.dumps(event),flush=True)\n" +
                "time.sleep(30)\n")
            result = self.command('supervise', '--seconds', '3', '--', sys.executable, str(child))
        self.assertEqual(result['stop_reason'], 'repeated_action_without_progress')
        self.assertEqual(result['commands_completed'], 5)
        self.assertFalse(result['turn_completed'])

    def test_recorded_progress_breaks_a_repetition_streak(self):
        events = [{'tool': 'exec_command', 'command': 'build next chunk', 'output': '',
                   'exit_code': 0, 'workspace_changed': True} for _ in range(8)]
        self.assertEqual(self.replay(events)['reason'], 'no_loop_observed')

    def test_supervisor_enforces_wall_clock_deadline(self):
        result=self.command('supervise','--seconds','1','--',sys.executable,'-c','import time; time.sleep(30)')
        self.assertEqual(result['stop_reason'],'deadline')
        self.assertFalse(result['turn_completed'])
        self.assertLess(result['elapsed_ms'],5000)

    def test_instruction_variant_changes_only_main_file_reference_section(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog=Path(directory)/'catalog.json'
            base='Preamble\n**File References**\nUse inline code.\n**Structure**\nKeep this.'
            original={'models':[{'slug':'main','model_messages':{'instructions_template':base},'other':42},
                                {'slug':'guardian','model_messages':{'instructions_template':'Guardian unchanged'}}]}
            catalog.write_text(json.dumps(original))
            result=self.command('catalog-variant',str(catalog),'--model','main')
        self.assertIn(':codex-file-citation',result['models'][0]['model_messages']['instructions_template'])
        self.assertTrue(result['models'][0]['model_messages']['instructions_template'].endswith('**Structure**\nKeep this.'))
        self.assertEqual(result['models'][1],original['models'][1])
        self.assertEqual(result['models'][0]['other'],42)

    def test_scoped_runner_forwards_variant_and_only_exports_audit_metadata(self):
        requests=[]
        class Upstream(http.server.BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_POST(self):
                payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                requests.append(payload)
                self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
                result={'type':'response.completed','response':{'id':'fixture','object':'response','status':'completed','model':'zai-org/GLM-5.3','output':[]}}
                self.wfile.write(('data: '+json.dumps(result)+'\n\n').encode())
        server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Upstream)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                root=Path(directory)
                fake=root/'fake-client'
                fake.write_text('#!'+sys.executable+'\n'+
                    'import json,sys,re,urllib.request,os\n'+
                    'provider=next(a for a in sys.argv if a.startswith("model_providers.nebius-tofa="))\n'+
                    'url=json.loads(provider.split("base_url=",1)[1].removesuffix("}"))\n'+
                    'catalog=json.load(open(json.loads(next(a for a in sys.argv if a.startswith("model_catalog_json=")).split("=",1)[1])))\n'+
                    'body={"model":"zai-org/GLM-5.3","stream":True,"input":[],"tools":[],"instructions":catalog["models"][0]["model_messages"]["instructions_template"]}\n'+
                    'req=urllib.request.Request(url+"/responses",data=json.dumps(body).encode(),headers={"Authorization":"Bearer "+os.environ["TOFA_API_KEY"],"Content-Type":"application/json"})\n'+
                    'urllib.request.urlopen(req,timeout=10).read()\n'+
                    'body["input"]=[{"type":"message","role":"developer","content":[{"type":"input_text","text":body.pop("instructions")}]}]\n'+
                    'req=urllib.request.Request(url+"/responses",data=json.dumps(body).encode(),headers={"Authorization":"Bearer "+os.environ["TOFA_API_KEY"],"Content-Type":"application/json"})\n'+
                    'urllib.request.urlopen(req,timeout=10).read()\n')
                fake.chmod(0o700)
                (root/'settings.json').write_text(json.dumps({'model':'zai-org/GLM-5.3','codex':str(fake),'variant':'file-citations-v1'}))
                (root/'budget.json').write_text('{"used":0,"maximum":2}')
                catalog=root/'catalog.json'
                catalog.write_text(json.dumps({'models':[{'slug':'zai-org/GLM-5.3','model_messages':{'instructions_template':'Original\n**File References**\nOld\n**Structure**\nKeep'}}]}))
                args=[sys.executable,str(SCRIPT.with_name('small_run.py')),'--observe',
                    'model_catalog_json='+json.dumps(str(catalog)),
                    'model_providers.nebius-tofa={base_url='+json.dumps('http://127.0.0.1:'+str(server.server_port))+'}']
                run=subprocess.run(args,env=dict(os.environ,TOFA_PILOT_RUN=str(root),TOFA_API_KEY='fixture-secret'),capture_output=True,text=True,timeout=15)
                self.assertEqual(run.returncode,0,run.stderr)
                audit=json.loads((root/'request-audit.json').read_text())
                self.assertTrue(audit[0]['file_citation_guidance_present'])
                self.assertTrue(audit[1]['file_citation_guidance_present'])
                self.assertNotIn('fixture-secret',json.dumps(audit))
                self.assertNotIn(':codex-file-citation',catalog.read_text())
            self.assertEqual(len(requests),2)
            self.assertIn(':codex-file-citation',requests[0]['instructions'])
        finally:
            server.shutdown();server.server_close();thread.join()

if __name__ == '__main__':
    unittest.main()
