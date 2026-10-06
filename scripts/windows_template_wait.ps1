# tofa-template-wait -- starts only the uniquely staged Limited task.
$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
$root='__ROOT__'
$request=Get-Content -Raw -LiteralPath ($root+'\request.json')|ConvertFrom-Json
$run=$request.run
$result=@{run=$run;phase='completion';ok=$false;completed=$false;unregistered=$false;reason='native_task_failed'}
try {
  Start-ScheduledTask -TaskName $run
  $deadline=[DateTime]::UtcNow.AddSeconds([int]'__WAIT_SECONDS__')
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
