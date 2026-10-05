import json, os, pathlib, subprocess, tempfile, time, shutil
r={'started_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'status':'running'}
root=pathlib.Path(tempfile.mkdtemp(prefix='tofa76-schema-'))
try:
 env={k:v for k,v in os.environ.items() if not k.upper().startswith(('CODEX_','OPENAI_','TOFA_'))};env['CODEX_HOME']=str(root)
 exe=r'C:\Users\SabreTest\AppData\Local\OpenAI\Codex\bin\5c1982dfef3b03a5\codex.exe'
 p=subprocess.run([exe,'app-server','generate-json-schema','--experimental','--out',str(root/'schemas')],capture_output=True,text=True,env=env,timeout=30)
 r['schema_exit']=p.returncode;r['stderr']=p.stderr;r['matches']={}
 if p.returncode:raise RuntimeError('schema command failed')
 wanted={'model_catalog_json','approvals_reviewer','model_provider','model_providers','guardian_policy_config','model_reasoning_effort','approvalsReviewer','modelProvider','supportedReasoningEfforts','isDefault','hidden','reloadUserConfig'}
 def walk(obj,path):
  if isinstance(obj,dict):
   for k,v in obj.items():
    if k in wanted and path.endswith('/properties'):r['matches'][path+'/'+k]=v
    walk(v,path+'/'+k)
  elif isinstance(obj,list):
   for n,v in enumerate(obj):walk(v,path+'/'+str(n))
 for f in (root/'schemas').rglob('*.json'):
  if f.name in ('codex_app_server_protocol.schemas.json','v2.json'):continue
  walk(json.loads(f.read_text()),str(f.relative_to(root/'schemas')).replace('\\','/'))
 r['status']='completed';r['exit_code']=0
except Exception as e:r.update(status='failed',exit_code=1,error=str(e))
finally:
 try:shutil.rmtree(root);r['cleanup']='passed'
 except Exception as e:r['cleanup']='failed';r['cleanup_error']=str(e);r['exit_code']=1
 r['finished_utc']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
 pathlib.Path(r'C:\Windows\Temp\tofa76-schema-probe.json').write_text(json.dumps(r,indent=2))
