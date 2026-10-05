# tofa-template-stage -- only unique runner-owned staging and tasks are changed.
$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
$root='__ROOT__'
$request=Get-Content -Raw -LiteralPath ($root+'\request.json')|ConvertFrom-Json
$run=$request.run
$result=@{run=$run;phase='completion';ok=$false;completed=$false;unregistered=$false;reason='guest_staging_failed'}
try {
  # The root and files were created protected before any upload. Add read-only
  # access for this user; same-volume moves from Public must never be used here.
  & icacls.exe $root /grant:r ('*'+$request.sid+':(OI)(CI)RX')|Out-Null
  if($LASTEXITCODE -ne 0){throw 'staging ACL failed'}
  # User output lives in a separate directory; never grant write to the harness.
  New-Item -ItemType Directory -Path ($root+'\output')|Out-Null
  & icacls.exe ($root+'\output') /grant:r ('*'+$request.sid+':(OI)(CI)M')|Out-Null
  if($LASTEXITCODE -ne 0){throw 'output ACL failed'}
  if($request.workspace_fixture -eq 'acl-unmanageable') {
    $fixture=$root+'\acl-fixture'
    New-Item -ItemType Directory -Path $fixture|Out-Null
    & icacls.exe $fixture /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' ('*'+$request.sid+':(OI)(CI)M')|Out-Null
    if($LASTEXITCODE -ne 0){throw 'fixture ACL failed'}
  }
  if(Get-ScheduledTask -TaskName $run -ErrorAction SilentlyContinue){throw 'existing task'}
  $action=New-ScheduledTaskAction -Execute 'powershell.exe' -Argument '-NoProfile -NonInteractive -WindowStyle Hidden -EncodedCommand __USER_COMMAND__'
  $principal=New-ScheduledTaskPrincipal -UserId $request.sid -LogonType Interactive -RunLevel Limited
  $settings=New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Seconds 120)
  Register-ScheduledTask -TaskName $run -Action $action -Principal $principal -Settings $settings|Out-Null
  Start-ScheduledTask -TaskName $run
  $deadline=[DateTime]::UtcNow.AddSeconds(125)
  do {
    Start-Sleep -Milliseconds 500
    $task=Get-ScheduledTask -TaskName $run
  } while(([DateTime]::UtcNow -lt $deadline) -and (($task.State -eq 'Running') -or !(Test-Path ($root+'\output\result.json'))))
  $result.state=[string]$task.State
  $result.last_result=(Get-ScheduledTaskInfo -TaskName $run).LastTaskResult
  $result.completed=(Test-Path ($root+'\output\result.json')) -and ($task.State -ne 'Running')
  if($task.State -ne 'Running') {
    Unregister-ScheduledTask -TaskName $run -Confirm:$false
    $result.unregistered=$true
  }
  $result.ok=$result.completed -and $result.unregistered -and ($result.last_result -eq 0)
  $result.reason=if($result.ok){'completed'}else{'native_task_failed'}
} catch {}
if(Test-Path ($root+'\output\result.json')) {Copy-Item -LiteralPath ($root+'\output\result.json') -Destination ($root+'\result.json')}
$result|ConvertTo-Json -Compress|Set-Content -Encoding UTF8 ($root+'\task.json')
