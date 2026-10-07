# Human review of the owned synthetic desktop. No UI clicks or credentials collected.
$ErrorActionPreference='Stop'
$request=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('__REQUEST__'))|ConvertFrom-Json
$result=@{ok=$false;stage='identity';choices=@();mode='guided'}
try {
  $Host.UI.RawUI.WindowTitle='TOFA: guided Windows catalog review'
  $process=Get-Process -Id $request.pid
  if($process.StartTime.ToUniversalTime().Ticks -ne $request.started_ticks -or $process.Path -ne $request.executable){throw 'identity changed'}
  Clear-Host
  Write-Host 'Stage 1/3: finish native Windows setup' -ForegroundColor Cyan
  Write-Host 'Use the ChatGPT/Codex window opened by this test in this disposable VM.'
  Write-Host 'If it says Finish Windows setup to continue, click Continue and complete native setup.'
  Write-Host 'Review any Windows consent prompt yourself. Do not select Full access.'
  Write-Host 'This review uses synthetic models and a local provider; no API key or sign-in is needed.'
  if((Read-Host 'Type ready when setup is complete, or stop to cancel') -ne 'ready'){throw 'cancelled'}

  Clear-Host
  $result.stage='model_choice'
  Write-Host 'Stage 2/3: select the synthetic model and reasoning' -ForegroundColor Cyan
  Write-Host 'In the owned workspace chat, open the model picker, then Select model.'
  Write-Host 'Verify that BOTH tofa-catalog-a and tofa-catalog-b are visible.'
  Write-Host 'Select tofa-catalog-b, then set Power/reasoning to High.'
  Write-Host 'Use Change permissions to select Approve for me, with workspace access.'
  Write-Host 'If setup returned you home, create a new chat in the workspace shown in the sidebar.'
  if((Read-Host 'Type both when both models were visible and B/High is selected, or stop') -ne 'both'){throw 'cancelled'}
  $result.choices=@('tofa-catalog-a','tofa-catalog-b')

  Clear-Host
  $result.stage='reasoning_choice'
  Write-Host 'Stage 3/3: send the bounded test prompt' -ForegroundColor Cyan
  Write-Host 'Send the prefilled prompt below once. If the composer is empty, paste it exactly:'
  Write-Host ''
  Write-Host 'Reply with the exact text TOFA CATALOG OK. This is a synthetic test. Do not call tools.' -ForegroundColor Yellow
  Write-Host ''
  Write-Host 'The local test provider returns an empty completion; visible answer text is not required.'
  Write-Host 'Leave the app open. The script checks the actual request, native policy and CLI defaults.'
  if((Read-Host 'Type sent after pressing Send once, or stop to cancel') -ne 'sent'){throw 'cancelled'}
  $result.ok=$true
  $result.stage='complete'
} catch {
  $result.ok=$false
}
$temporary=$request.output+'.tmp'
$result|ConvertTo-Json -Depth 4 -Compress|Set-Content -Encoding UTF8 -LiteralPath $temporary
Move-Item -Force -LiteralPath $temporary -Destination $request.output
if(!$result.ok){exit 1}
