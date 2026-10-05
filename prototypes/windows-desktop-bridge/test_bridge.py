"""Public executable boundary tests for the throwaway bridge."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent

class BridgeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = tempfile.TemporaryDirectory(prefix='tofa77-test-')
        if os.environ.get('TOFA_TEST_BRIDGE'):
            cls.binary = Path(os.environ['TOFA_TEST_BRIDGE'])
            return
        cls.binary = Path(cls.scratch.name) / ('bridge.exe' if os.name == 'nt' else 'bridge')
        subprocess.run(['go', 'build', '-o', str(cls.binary), '.'], cwd=HERE, check=True)

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def test_stdio_arguments_environment_exit_and_private_evidence(self):
        with tempfile.TemporaryDirectory(prefix='tofa77-case-') as tmp:
            root = Path(tmp)
            engine = Path(sys.executable).resolve()
            fixture = root / 'engine fixture.py'
            fixture.write_text('''import os, sys
assert sys.argv[1:] == ['argument with spaces', 'quote"literal', 'back\\\\slash']
assert os.environ['TOFA_TEST_VALUE'] == 'keep this value'
assert 'CODEX_WINDOWS_REGISTERED_CORE' not in os.environ
assert 'CODEX_WINDOWS_SANDBOX_PACKAGE_FAMILY' not in os.environ
sys.stdout.buffer.write(sys.stdin.buffer.read())
sys.stderr.write('PRIVATE-STDERR')
sys.exit(7)
''')
            config = root / 'bridge.json'
            config.write_text(json.dumps({'engine': str(engine), 'sha256': hashlib.sha256(engine.read_bytes()).hexdigest(), 'evidence_dir': str(root)}))
            env = dict(os.environ, TOFA_PROTOTYPE_CONFIG=str(config), TOFA_TEST_VALUE='keep this value')
            for key in ('CODEX_WINDOWS_REGISTERED_CORE', 'CODEX_WINDOWS_SANDBOX_PACKAGE_FAMILY'):
                env.pop(key, None)
            payload = b'{"id":1,"method":"initialize","params":{"private":"SECRET-PAYLOAD"}}\n\x00opaque\xff\n'
            run = subprocess.run([str(self.binary), str(fixture), 'argument with spaces', 'quote"literal', 'back\\slash'], input=payload, capture_output=True, env=env, timeout=15)
            self.assertEqual(run.returncode, 7, run.stderr)
            self.assertEqual(run.stdout, payload)
            self.assertEqual(run.stderr, b'PRIVATE-STDERR')
            logs = list(root.glob('bridge-*.jsonl'))
            self.assertEqual(len(logs), 1)
            evidence = logs[0].read_text()
            self.assertNotIn('SECRET-PAYLOAD', evidence)
            self.assertNotIn('PRIVATE-STDERR', evidence)
            self.assertNotIn('keep this value', evidence)
            events = [json.loads(line) for line in evidence.splitlines()]
            self.assertTrue(any(e['event'] == 'exit' and e['exit_code'] == 7 for e in events))

    def test_initialization_metadata_without_payload(self):
        with tempfile.TemporaryDirectory(prefix='tofa77-init-') as tmp:
            root=Path(tmp)
            engine=Path(sys.executable).resolve()
            fixture=root/'engine.py'
            fixture.write_text('import sys,json\nrequest=json.loads(sys.stdin.readline())\nprint(json.dumps({"id":request["id"],"result":{"userAgent":"PRIVATE-RESPONSE"}}),flush=True)\n')
            config=root/'bridge.json'
            config.write_text(json.dumps({'engine':str(engine),'sha256':hashlib.sha256(engine.read_bytes()).hexdigest(),'evidence_dir':str(root)}))
            result=subprocess.run([str(self.binary),str(fixture)],input=b'{"id":"private-id","method":"initialize","params":{"private":"PRIVATE-REQUEST"}}\n',capture_output=True,env=dict(os.environ,TOFA_PROTOTYPE_CONFIG=str(config)),timeout=15)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads(result.stdout)['result']['userAgent'],'PRIVATE-RESPONSE')
            evidence=next(root.glob('bridge-*.jsonl')).read_text()
            self.assertNotIn('PRIVATE-',evidence)
            self.assertNotIn('private-id',evidence)
            events=[json.loads(line) for line in evidence.splitlines()]
            self.assertTrue(any(e['event']=='initialize_response' and e['success'] for e in events))

    def test_unset_policy_is_not_reported_as_an_effective_policy(self):
        with tempfile.TemporaryDirectory(prefix='tofa77-null-') as tmp:
            root=Path(tmp);engine=Path(sys.executable).resolve()
            fixture=root/'engine.py'
            fixture.write_text('import sys,json\nr=json.loads(sys.stdin.readline())\nprint(json.dumps({"id":r["id"],"result":{"config":{"approval_policy":None,"features":{"windows_sandbox_service":True}}}}),flush=True)\n')
            config=root/'bridge.json'
            config.write_text(json.dumps({'engine':str(engine),'sha256':hashlib.sha256(engine.read_bytes()).hexdigest(),'evidence_dir':str(root)}))
            result=subprocess.run([str(self.binary),str(fixture)],input=b'{"id":1,"method":"config/read","params":{}}\n',capture_output=True,env=dict(os.environ,TOFA_PROTOTYPE_CONFIG=str(config)),timeout=15)
            self.assertEqual(result.returncode,0,result.stderr)
            events=[json.loads(line) for line in next(root.glob('bridge-*.jsonl')).read_text().splitlines()]
            event=next(e for e in events if e['event']=='config/read_response')
            self.assertEqual(event['approval_policy'],'unset')
            self.assertEqual(event['approvals_reviewer'],'absent')
            self.assertTrue(event['windows_sandbox_service'])

    def test_native_review_notification_is_recorded_without_action_content(self):
        with tempfile.TemporaryDirectory(prefix='tofa77-review-') as tmp:
            root=Path(tmp);engine=Path(sys.executable).resolve()
            fixture=root/'engine.py'
            fixture.write_text('import json\nprint(json.dumps({"method":"item/autoApprovalReview/completed","params":{"review":{"status":"denied"},"action":"PRIVATE-ACTION","threadId":"PRIVATE-ID"}}),flush=True)\n')
            config=root/'bridge.json'
            config.write_text(json.dumps({'engine':str(engine),'sha256':hashlib.sha256(engine.read_bytes()).hexdigest(),'evidence_dir':str(root)}))
            result=subprocess.run([str(self.binary),str(fixture)],input=b'',capture_output=True,env=dict(os.environ,TOFA_PROTOTYPE_CONFIG=str(config)),timeout=15)
            self.assertEqual(result.returncode,0,result.stderr)
            evidence=next(root.glob('bridge-*.jsonl')).read_text()
            self.assertNotIn('PRIVATE-',evidence)
            events=[json.loads(line) for line in evidence.splitlines()]
            event=next(e for e in events if e['event']=='native_review')
            self.assertEqual(event['status'],'denied')

if __name__ == '__main__':
    unittest.main(verbosity=2)
