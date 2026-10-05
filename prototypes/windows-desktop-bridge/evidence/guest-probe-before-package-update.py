"""PROTOTYPE: limited-user, no-turn transport and incumbent refusal checks."""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time

root = Path(__file__).resolve().parent
report_path = root / 'result.json'
report = {'started_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'status':'running', 'inference_requests':0}
proc = None
home = None
try:
    report['elevated'] = bool(ctypes.windll.shell32.IsUserAnAdmin())
    assert not report['elevated'], 'limited user required'
    refusal = subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-File',str(root/'preflight.ps1')],capture_output=True,text=True,timeout=15)
    assert refusal.returncode == 41, 'expected refusal of ordinary running app'
    preflight = json.loads((root/'preflight.json').read_text(encoding='utf-8-sig'))
    assert preflight['reason'] == 'ordinary_app_running' and preflight['launched'] is False
    report['incumbent_refusal'] = preflight
    engine = Path(os.environ['LOCALAPPDATA'])/'OpenAI/Codex/bin/5c1982dfef3b03a5/codex.exe'
    engine_hash = hashlib.sha256(engine.read_bytes()).hexdigest()
    assert engine_hash == 'fcdd6134ddd030fa4ec05779513a94290c7317796f0641add72c5e8ad978f8b4', 'engine changed'
    bridge = root/'bridge.exe'
    report['engine_sha256'] = engine_hash
    report['bridge_sha256'] = hashlib.sha256(bridge.read_bytes()).hexdigest()
    transport = subprocess.run([sys.executable,str(root/'test_bridge.py')],env=dict(os.environ,TOFA_TEST_BRIDGE=str(bridge)),capture_output=True,timeout=30)
    report['transport_contract_test_exit_code'] = transport.returncode
    assert transport.returncode == 0, 'native executable transport contract test failed'
    home = Path(tempfile.mkdtemp(prefix='tofa77-home-'))
    config = home/'bridge.json'
    config.write_text(json.dumps({'engine':str(engine),'sha256':engine_hash,'evidence_dir':str(home)}))
    env = {k:v for k,v in os.environ.items() if not k.upper().startswith(('CODEX_','OPENAI_','TOFA_'))}
    env.update(CODEX_HOME=str(home),TOFA_PROTOTYPE_CONFIG=str(config))
    args = [str(bridge),'app-server','-c','cli_auth_credentials_store="ephemeral"','-c','model_provider="tofa77"','-c','model_providers.tofa77.name="No inference prototype"','-c','model_providers.tofa77.base_url="http://127.0.0.1:9/v1"','-c','model_providers.tofa77.wire_api="responses"','-c','model_providers.tofa77.requires_openai_auth=false']
    proc = subprocess.Popen(args,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,env=env,text=True,encoding='utf-8')
    messages = queue.Queue()
    def read():
        for line in proc.stdout:
            try: messages.put(json.loads(line))
            except ValueError: messages.put({'invalid_json':True})
    reader=threading.Thread(target=read,daemon=True);reader.start()
    def rpc(id,method,params):
        proc.stdin.write(json.dumps({'id':id,'method':method,'params':params})+'\n');proc.stdin.flush()
        deadline=time.monotonic()+15
        while True:
            obj=messages.get(timeout=max(0,deadline-time.monotonic()))
            if obj.get('id')==id:
                assert 'error' not in obj, method+' failed'
                return obj['result']
    initialized=rpc(1,'initialize',{'clientInfo':{'name':'tofa77-prototype','version':'1'},'capabilities':{'experimentalApi':True}})
    report['initialize']={k:initialized.get(k) for k in ('userAgent','platformFamily','platformOs')}
    proc.stdin.write('{"method":"initialized","params":{}}\n');proc.stdin.flush()
    config=rpc(2,'config/read',{'includeLayers':False})['config']
    report['config']={k:config.get(k) for k in ('approval_policy','approvals_reviewer','sandbox_mode','windows')}
    report['sandbox_service_feature']=(config.get('features') or {}).get('windows_sandbox_service')
    proc.stdin.close();proc.wait(timeout=15);reader.join(timeout=2);proc.stdout.close()
    report['bridge_exit_code']=proc.returncode
    assert proc.returncode == 0, 'bridge EOF failed'
    report['bridge_events']=[json.loads(line) for p in home.glob('bridge-*.jsonl') for line in p.read_text().splitlines()]
    assert any(e['event']=='exit' and e['exit_code']==0 for e in report['bridge_events'])
    # Changed binary identities must be rejected before execution.
    (home/'bridge.json').write_text(json.dumps({'engine':str(engine),'sha256':'0'*64,'evidence_dir':str(home)}))
    bad=subprocess.run([str(bridge),'--version'],env=env,capture_output=True,timeout=10)
    assert bad.returncode==125 and not bad.stdout
    report['hash_mismatch_refused']=True
    report['status']='completed';report['exit_code']=0
except Exception as exc:
    report.update(status='failed',exit_code=1,error_type=type(exc).__name__,error=str(exc))
finally:
    if proc and proc.poll() is None:
        # Kill only this owned probe; no ordinary desktop/service process is selected.
        proc.kill();proc.wait(timeout=5);report['forced_bridge_exit']=True
    if proc:
        for stream in (proc.stdin,proc.stdout):
            if stream and not stream.closed: stream.close()
    if home:
        for attempt in range(10):
            try: shutil.rmtree(home);report['temporary_home_removed']=True;break
            except OSError:
                if attempt==9: report.update(status='failed',exit_code=1,temporary_home_removed=False)
                else: time.sleep(.3)
    report['finished_utc']=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    report_path.write_text(json.dumps(report,indent=2))
sys.exit(report['exit_code'])
