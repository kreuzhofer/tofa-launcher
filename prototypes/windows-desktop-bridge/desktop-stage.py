"""PROTOTYPE: stage a native app observation only in the explicitly owned clone."""
import argparse
import base64
import datetime
import json
from pathlib import Path
import subprocess
import time

CLONE='EF96CF12-D901-455F-81FF-4C5001E15F80'
p=argparse.ArgumentParser();p.add_argument('mode',choices=['baseline','registered','bridge','close','observe']);p.add_argument('--bridge',type=Path,default=Path('/private/tmp/tofa77-observed-bridge.exe'));a=p.parse_args()
u='/Applications/UTM.app/Contents/MacOS/utmctl';here=Path(__file__).resolve().parent
run='tofa77-desktop-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
root='C:\\Users\\Public\\'+run
out=here/'evidence'/run;out.mkdir(parents=True,exist_ok=False)
def utm(*args,**kwargs):
 r=subprocess.run([u,*args],capture_output=True,timeout=30,**kwargs)
 if r.returncode or r.stderr or b'Error from event:' in r.stdout: raise RuntimeError('UTM transport failed: '+r.stdout.decode(errors='replace')+r.stderr.decode(errors='replace'))
 return r.stdout
def ps(s):utm('exec',CLONE,'--cmd','powershell.exe','-NoProfile','-NonInteractive','-EncodedCommand',base64.b64encode(s.encode('utf-16-le')).decode())
def pull(name):return json.loads(utm('file','pull',CLONE,root+'\\'+name).decode('utf-8-sig'))
def wait(name,seconds=45):
 for _ in range(seconds*2):
  try:return pull(name)
  except (ValueError,RuntimeError):time.sleep(.5)
 raise RuntimeError(name+' did not arrive')
ps("$ErrorActionPreference='Stop';if(Test-Path '"+root+"'){throw 'exists'};New-Item -ItemType Directory -Path '"+root+"'|Out-Null;'{\"ready\":true}'|Set-Content -Encoding UTF8 '"+root+"\\ready.json'")
assert wait('ready.json')['ready']
if a.mode=='bridge':utm('file','push',CLONE,root+'\\bridge.exe',input=a.bridge.read_bytes())
source="$Mode='"+a.mode+"';$Run='"+run+"';$Root='"+root+"'\n"+(here/'desktop-stage.ps1').read_text()
utm('file','push',CLONE,root+'\\stage.ps1',input=source.encode('utf-8'))
ps(r"""$ErrorActionPreference='Stop'
$name='RUN';if(Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue){throw 'task exists'}
$user=(Get-CimInstance Win32_ComputerSystem).UserName;if(!$user){throw 'no user'}
$a=New-ScheduledTaskAction -Execute 'powershell.exe' -Argument '-NoProfile -NonInteractive -File "ROOT\stage.ps1"'
$p=New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
$s=New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 2)
Register-ScheduledTask -TaskName $name -Action $a -Principal $p -Settings $s|Out-Null
Start-ScheduledTask -TaskName $name
""".replace('RUN',run).replace('ROOT',root))
report=wait('result.json');(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
ps(r"""$ErrorActionPreference='Stop'
$name='RUN';$root='ROOT';$t=Get-ScheduledTask -TaskName $name
for($n=0;$n -lt 10 -and $t.State -eq 'Running';$n++){Start-Sleep -Milliseconds 500;$t=Get-ScheduledTask -TaskName $name}
$i=Get-ScheduledTaskInfo -TaskName $name
$r=[ordered]@{state=[string]$t.State;last_result=$i.LastTaskResult;unregistered=$false}
if($t.State -ne 'Running'){Unregister-ScheduledTask -TaskName $name -Confirm:$false;$r.unregistered=$true}
$r|ConvertTo-Json|Set-Content -Encoding UTF8 ($root+'\task.json')
""".replace('RUN',run).replace('ROOT',root))
task=wait('task.json');(out/'task.json').write_text(json.dumps(task,indent=2)+'\n')
print(json.dumps({'evidence':str(out),'report':report,'task':task},indent=2))
if report['exit_code'] or task['last_result'] or not task['unregistered']:raise SystemExit(1)
