"""Contract generation through owned executable fixtures; no account or Desktop."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import system_skills_contract as contract


class ContractTests(unittest.TestCase):
    def test_generator_isolates_home_and_retains_exact_output_without_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); engine=root/'engine'
            engine.write_text('#!'+sys.executable+'\n'+'''
import os,sys,json
from pathlib import Path
if sys.argv[1:]==['--version']:print('fixture 1');sys.exit()
home=Path(os.environ['CODEX_HOME']);assert str(home.parent)==os.environ['HOME']
assert 'TOKEN_FACTORY_API_KEY' not in os.environ
assert (home/'config.toml').read_text()=='cli_auth_credentials_store="file"\\n'
r=json.loads(sys.stdin.readline());assert r['method']=='initialize'
s=home/'skills/.system';s.mkdir(parents=True)
(s/'.codex-system-skills.marker').write_text('owned marker')
(s/'SKILL.md').write_text('owned instructions')
print(json.dumps({'id':1,'result':{}}),flush=True)
sys.stdin.read()
''');engine.chmod(0o700)
            output=root/'contract.json'
            command=[sys.executable,str(Path(contract.__file__)), '--engine',str(engine),'--output',str(output)]
            env=dict(os.environ,TOKEN_FACTORY_API_KEY='synthetic-must-not-reach-child')
            result=subprocess.run(command,env=env,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)
            raw=output.read_bytes();value=json.loads(raw)
            self.assertEqual(value['sources'][0]['engine_sha256'],contract.digest(engine))
            self.assertEqual(set(value['sources'][0]['files']),{'.system/.codex-system-skills.marker','.system/SKILL.md'})
            self.assertEqual(output.stat().st_mode&0o777,0o600)
            self.assertFalse((root/'skills').exists())
            self.assertNotEqual(subprocess.run(command,capture_output=True).returncode,0)
            self.assertEqual(output.read_bytes(),raw)

    def test_closed_input_still_reaps_owned_engine(self):
        import time
        import signal
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);engine=root/'engine'
            engine.write_text('#!'+sys.executable+'\n'+'''
import os,sys,time
from pathlib import Path
if sys.argv[1:]==['--version']:print('fixture 1');sys.exit()
os.close(0)
(Path(os.environ['HOME'])/'stdin-closed').touch()
time.sleep(60)
''');engine.chmod(0o700)
            original=subprocess.Popen;children=[]
            def start(*args,**kwargs):
                child=original(*args,**kwargs)
                if 'app-server' in args[0]:
                    children.append(child);deadline=time.monotonic()+5
                    while not (Path(kwargs['cwd'])/'stdin-closed').exists():
                        if time.monotonic()>=deadline:raise AssertionError('fixture did not close input')
                        time.sleep(.01)
                return child
            try:
                with patch.object(contract.subprocess,'Popen',start):
                    with self.assertRaises(BrokenPipeError):contract.capture(engine)
                self.assertTrue(children)
                self.assertIsNotNone(children[0].poll(),'owned engine remained alive after broken pipe')
            finally:
                for child in children:
                    if child.poll() is None:os.killpg(child.pid,signal.SIGKILL);child.wait()
