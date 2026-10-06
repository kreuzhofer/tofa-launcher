# tofa-template-stage -- only unique runner-owned staging and tasks are changed.
$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
$root='__ROOT__'
$request=Get-Content -Raw -LiteralPath ($root+'\request.json')|ConvertFrom-Json
$run=$request.run
$result=@{run=$run;phase='task_staging';ok=$false;completed=$false;unregistered=$false;reason='guest_staging_failed'}
try {
  if($request.candidate) {
    # Protected staging only; execution and integrity measurement remain Limited.
    $inputFile=[IO.File]::OpenRead($root+'\candidate.exe.gz')
    try {
      $gzip=New-Object IO.Compression.GZipStream($inputFile,[IO.Compression.CompressionMode]::Decompress)
      try {
        $candidateFile=[IO.File]::Open($root+'\candidate.exe',[IO.FileMode]::CreateNew)
        try {$gzip.CopyTo($candidateFile)} finally {$candidateFile.Dispose()}
      } finally {$gzip.Dispose()}
    } finally {$inputFile.Dispose()}
  }
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
  $action=New-ScheduledTaskAction -Execute 'powershell.exe' -Argument '-NoProfile -NonInteractive -WindowStyle __WINDOW_STYLE__ -EncodedCommand __USER_COMMAND__'
  $principal=New-ScheduledTaskPrincipal -UserId $request.sid -LogonType Interactive -RunLevel Limited
  $settings=New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Seconds __TASK_SECONDS__)
  Register-ScheduledTask -TaskName $run -Action $action -Principal $principal -Settings $settings|Out-Null
  $result.ok=$true
  $result.reason='staged'
} catch {}
$result|ConvertTo-Json -Compress|Set-Content -Encoding UTF8 ($root+'\task-staging.json')
