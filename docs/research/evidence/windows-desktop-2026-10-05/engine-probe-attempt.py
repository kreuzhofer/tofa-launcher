"""Bounded read/config-only installed-engine probe; no inference or real account."""
import json, os, pathlib, queue, subprocess, tempfile, threading, time
report = {'started_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'status': 'running', 'inference_requests': 0}
engine = r'C:\Users\SabreTest\AppData\Local\OpenAI\Codex\bin\5c1982dfef3b03a5\codex.exe'
proc = None
try:
    report['version'] = subprocess.run([engine, '--version'], capture_output=True, text=True, timeout=15).__dict__
    report['version'] = {k: report['version'][k] for k in ('returncode', 'stdout', 'stderr')}
    with tempfile.TemporaryDirectory(prefix='tofa76-engine-') as home:
        env = {k:v for k,v in os.environ.items() if not k.upper().startswith(('CODEX_', 'OPENAI_', 'TOFA_'))}
        env['CODEX_HOME'] = home
        args = [engine, 'app-server', '-c', 'model="probe-main"', '-c', 'model_provider="tofa76"', '-c', 'model_providers.tofa76.name="Synthetic investigation"', '-c', 'model_providers.tofa76.base_url="http://127.0.0.1:9/v1"', '-c', 'model_providers.tofa76.wire_api="responses"', '-c', 'model_providers.tofa76.requires_openai_auth=false', '-c', 'cli_auth_credentials_store="ephemeral"']
        with open(pathlib.Path(home)/'stderr.txt', 'w') as err:
            proc = subprocess.Popen(args, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=err, text=True)
            messages = queue.Queue()
            def read():
                for line in proc.stdout:
                    try: messages.put(json.loads(line))
                    except ValueError: messages.put({'invalid_json': True})
            threading.Thread(target=read, daemon=True).start()
            def rpc(id, method, params):
                proc.stdin.write(json.dumps({'id':id,'method':method,'params':params})+'\n'); proc.stdin.flush()
                deadline=time.monotonic()+15
                while True:
                    obj=messages.get(timeout=max(0,deadline-time.monotonic()))
                    if obj.get('id')==id:
                        if 'error' in obj: raise RuntimeError({'method':method,'error':obj['error']})
                        return obj['result']
            init=rpc(1,'initialize',{'clientInfo':{'name':'tofa76-probe','version':'1'},'capabilities':{'experimentalApi':True}})
            report['initialize']={k:v for k,v in init.items() if k in ('userAgent','platformFamily','platformOs')}
            proc.stdin.write(json.dumps({'method':'initialized','params':{}})+'\n');proc.stdin.flush()
            config=rpc(2,'config/read',{'includeLayers':False})['config']
            report['runtime_configuration']={k:config.get(k) for k in ('model','model_provider','approvals_reviewer','windows','model_reasoning_effort')}
            report['synthetic_provider']=config.get('model_providers',{}).get('tofa76')
            req=rpc(3,'configRequirements/read',{})
            report['requirements_present']=req.get('requirements') is not None
            account=rpc(4,'account/read',{'refreshToken':False})
            report['account_present']=account.get('account') is not None
            report['requires_openai_auth']=account.get('requiresOpenaiAuth')
            proc.stdin.close()
            try: proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.terminate();proc.wait(timeout=5);report['forced_probe_exit']=True
            report['engine_exit_code']=proc.returncode
    report['status']='completed'; report['exit_code']=0
except Exception as exc:
    report['status']='failed';report['exit_code']=1;report['error']=str(exc)
finally:
    if proc is not None and proc.poll() is None: proc.kill();proc.wait(timeout=5)
    report['finished_utc']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
    pathlib.Path(r'C:\Windows\Temp\tofa76-engine-probe.json').write_text(json.dumps(report,indent=2))
raise SystemExit(report['exit_code'])
