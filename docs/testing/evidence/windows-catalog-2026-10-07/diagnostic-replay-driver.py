import json,sys,time,uuid
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'scripts'))
from windows_template_transport import Transport,Failure
from windows_clone_runner import owned_vm,stop_clone,validate_preflight
from windows_run_lock import InvocationLease
state=Path('.qualification/windows-clone-runs')
owner=json.loads((state/'tofa-run-d906f287fa754b7a993772ab44901baf/ownership.json').read_text())
label=sys.argv[1]
probe='''import json,shutil
from pathlib import Path
from windows_catalog_experiment import experiment
from windows_template_probe import safe_directory
root=Path(__file__).parent
request=json.loads((root/'request.json').read_text(encoding='utf-8-sig'))
identity=json.loads((root/'output/identity.json').read_text(encoding='utf-8-sig'))
workspace=Path.home()/request['run']/'workspace'
safe_directory(workspace)
smoke=workspace.parent/'desktop'
safe_directory(smoke)
original=Path.home()/'tofa-run-d906f287fa754b7a993772ab44901baf'/'desktop'
for name in ('tofa-supervisor.exe','codex.exe'):
    shutil.copyfile(original/name,smoke/name)
config=json.loads((original/'bridge.json').read_text())
config['workspace']=str(workspace)
(smoke/'bridge.json').write_text(json.dumps(config),encoding='utf-8')
report={'run':request['run'],'phase':'desktop','ok':False,'reason':'catalog_observation_failed','checks':{}}
try:
    experiment(root,request,identity,workspace,report)
    report.update(ok=True,reason='catalog_complete')
except Exception as error:
    report['error_type']=type(error).__name__
    if str(error) in ('catalog_picker_failed','catalog_protocol_failed','catalog_observation_failed','catalog_discovery_failed'):
        report['reason']=str(error)
finally:
    (root/'output/result.json').write_text(json.dumps(report),encoding='utf-8')
'''
class Replay(Transport):
 def call(self,*args,data=None):
  if args[:2]==('file','push') and args[-1].endswith('\\probe.py'): data=probe.encode()
  return super().call(*args,data=data)
lease=InvocationLease(state)
assert lease.held
transport=Replay('/Applications/UTM.app/Contents/MacOS/utmctl',owner['clone']['uuid'],650,lease.descriptor)
try:
 assert owned_vm(transport,owner)['state']=='stopped'
 transport.call('start',owner['clone']['uuid'])
 for _ in range(60):
  try:
   transport.call('ip-address',owner['clone']['uuid']);break
  except Failure: time.sleep(1)
 run='tofa-run-'+uuid.uuid4().hex
 request={'run':run,'user':'tofa-test','operation':'status'}
 for _ in range(20):
  preflight=transport.preflight(request)
  if preflight.get('ok'):break
  time.sleep(1)
 validate_preflight(preflight)
 request.update(sid=preflight['user']['sid'],session=preflight['user']['session'],python=preflight['python'],initialize_sandbox=False,
                workspace_fixture='user-owned',test_auth='native-session')
 task,result=transport.measure(request,desktop=True)
 evidence={'owner_run':owner['run'],'replay_run':run,'task':task,'result':result,'progress':transport.last_progress}
 Path('docs/testing/evidence/windows-catalog-2026-10-07/'+label+'.json').write_text(json.dumps(evidence,indent=2)+'\n')
 c=result.get('catalog',{})
 print(json.dumps({k:c.get(k) for k in ('stage','picker','requests','checks')},indent=2))
 print(json.dumps([e for e in c.get('events',[]) if e['event'].startswith('catalog_')],indent=2))
finally:
 transport.deadline=time.monotonic()+60
 cleanup=stop_clone(transport,owner)
 Path('docs/testing/evidence/windows-catalog-2026-10-07/'+label+'-cleanup.json').write_text(json.dumps({'shutdown':cleanup})+'\n')
 print(cleanup)
 lease.close()
