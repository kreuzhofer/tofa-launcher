"""Run only the no-turn probe on the named existing Windows ARM64 guest."""
import argparse
import base64
import datetime
import json
from pathlib import Path
import subprocess
import time

p=argparse.ArgumentParser();p.add_argument('--vm',required=True);p.add_argument('--bridge',type=Path,required=True);a=p.parse_args()
u='/Applications/UTM.app/Contents/MacOS/utmctl'
here=Path(__file__).resolve().parent
run='tofa77-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
root='C:\\Users\\Public\\'+run
output=here/'evidence'/run;output.mkdir(parents=True,exist_ok=False)
def utm(*args,**kwargs):
    r=subprocess.run([u,*args],capture_output=True,timeout=30,**kwargs)
    if r.returncode or r.stderr or b'Error from event:' in r.stdout: raise RuntimeError('UTM command failed: '+r.stderr.decode(errors='replace')+r.stdout.decode(errors='replace'))
    return r.stdout
def ps(source):
    utm('exec',a.vm,'--cmd','powershell.exe','-NoProfile','-NonInteractive','-EncodedCommand',base64.b64encode(source.encode('utf-16-le')).decode())
def pull(name):
    return json.loads(utm('file','pull',a.vm,root+'\\'+name).decode('utf-8-sig'))
ps("$ErrorActionPreference='Stop';if(Test-Path '"+root+"'){throw 'scratch exists'};New-Item -ItemType Directory -Path '"+root+"'|Out-Null;'{\"ready\":true}'|Set-Content -Encoding UTF8 '"+root+"\\ready.json'")
for attempt in range(20):
    try:
        if pull('ready.json').get('ready'): break
    except (RuntimeError,ValueError): time.sleep(.5)
else: raise RuntimeError('guest scratch readiness timed out')
for name,path in [('bridge.exe',a.bridge),('guest-probe.py',here/'guest-probe.py'),('preflight.ps1',here/'preflight.ps1'),('test_bridge.py',here/'test_bridge.py')]:
    utm('file','push',a.vm,root+'\\'+name,input=path.read_bytes())
source=r"""$ErrorActionPreference='Stop'
$name='RUN';$root='ROOT'
if(Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue){throw 'task already exists'}
$user=(Get-CimInstance Win32_ComputerSystem).UserName
if(!$user){throw 'no interactive user'}
$action=New-ScheduledTaskAction -Execute 'C:\Python313ARM\python.exe' -Argument ('"'+$root+'\guest-probe.py"')
$principal=New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
$settings=New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 2)
Register-ScheduledTask -TaskName $name -Action $action -Principal $principal -Settings $settings|Out-Null
Start-ScheduledTask -TaskName $name
""".replace('RUN',run).replace('ROOT',root)
ps(source)
report=None
for attempt in range(45):
    try: report=pull('result.json');break
    except (RuntimeError,ValueError): time.sleep(1)
if report is not None:
    (output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
# Record last-run result, and unregister only our own completed task.
ps(r"""$ErrorActionPreference='Stop'
$name='RUN';$root='ROOT'
$t=Get-ScheduledTask -TaskName $name;$i=Get-ScheduledTaskInfo -TaskName $name
$r=[ordered]@{state=[string]$t.State;last_result=$i.LastTaskResult;last_run_utc=$i.LastRunTime.ToUniversalTime().ToString('o');unregistered=$false}
if($t.State -ne 'Running') {Unregister-ScheduledTask -TaskName $name -Confirm:$false;$r.unregistered=$true}
$r|ConvertTo-Json|Set-Content -Encoding UTF8 ($root+'\task.json')
""".replace('RUN',run).replace('ROOT',root))
for attempt in range(20):
    try: task=pull('task.json');break
    except (RuntimeError,ValueError): time.sleep(.5)
else: raise RuntimeError('guest task completion timed out')
(output/'task.json').write_text(json.dumps(task,indent=2)+'\n')
print(json.dumps({'evidence':str(output),'report':report,'task':task},indent=2))
if report is None or report.get('exit_code')!=0 or task['last_result']!=0 or not task['unregistered']: raise SystemExit(1)
