# Native Windows CI only: actual candidate, persistent user PATH, real CLI helper.
# All files/credentials are synthetic. User PATH and process environment are restored.
param(
 [Parameter(Mandatory=$true)][string]$Dist,
 [Parameter(Mandatory=$true)][string]$Version,
 [switch]$DisposableVM,
 [string]$Diagnostics=(Join-Path (Get-Location) ".ci-diagnostics/windows-lifecycle")
)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
if ([Environment]::OSVersion.Platform -ne 'Win32NT') {throw 'Native Windows is required'}
if ($env:GITHUB_ACTIONS -ne 'true' -and !$DisposableVM) {throw 'Use disposable CI or explicitly authorize -DisposableVM; this check restores user PATH and uses synthetic state'}
if ($Version -notmatch '^[A-Za-z0-9._-]+$' -or $Version -eq 'latest') {throw 'An explicit candidate version is required'}
$Dist=(Resolve-Path -LiteralPath $Dist).Path
# Independent expected artifact for the actual-host lifecycle assertion.
$HostArchitectures=@(Get-CimInstance Win32_Processor | Select-Object -ExpandProperty Architecture -Unique)
if($HostArchitectures.Count -ne 1){throw 'Expected one native processor architecture'}
$Arch=switch($HostArchitectures[0]) {9 {'amd64'} 12 {'arm64'} default {throw 'Unsupported test host architecture'}}
$Asset="tofa_${Version}_windows_${Arch}.exe"
foreach($Name in @($Asset,'SHA256SUMS','install.ps1','uninstall.ps1')) {
 if(!(Test-Path -LiteralPath (Join-Path $Dist $Name) -PathType Leaf)){throw "Missing candidate file: $Name"}
}
$Temp=Join-Path ([IO.Path]::GetTempPath()) ('tofa lifecycle '+[Guid]::NewGuid().ToString('N'))
$Config=Join-Path $Temp 'local/tofa'
$Root=Join-Path $Config 'install'
$Bin=Join-Path $Root 'bin'
$Binary=Join-Path $Bin 'tofa.exe'
$Helpers=Join-Path $Temp 'helpers'
$PowerShell=(Get-Command powershell.exe -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
$Python=(Get-Command python -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
$ProcessRunner=Join-Path $PSScriptRoot "lifecycle_process.py"
$OriginalUserPath=[Environment]::GetEnvironmentVariable('Path','User')
$OriginalEnv=@{}
foreach($Name in @('LOCALAPPDATA','TOFA_INSTALL_DIR','TOFA_RELEASE_BASE_URL','TEMP','TMP','Path')) {
 $OriginalEnv[$Name]=[Environment]::GetEnvironmentVariable($Name,'Process')
}
$UnrelatedPath=Join-Path $Temp 'other-bin'
$ExpectedUserPath=(@($OriginalUserPath -split ';' | Where-Object {$_})+$UnrelatedPath)-join ';'
$Saved=@{}
$Unrelated=@{}
$Corrupt=$false
$Sequence=0
function Assert($Condition,[string]$Message) {if(!$Condition){throw $Message}}
function Read-Log([string]$Path) {
 if(!(Test-Path -LiteralPath $Path)){return ''}
 # The asynchronous helper can still hold the redirected write handle open.
 $Reader=[IO.StreamReader]::new([IO.File]::Open($Path,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::ReadWrite))
 try{return $Reader.ReadToEnd()}finally{$Reader.Dispose()}
}
function Assert-Files($Files) {
 foreach($Path in $Files.Keys) {
  Assert (Test-Path -LiteralPath $Path) "File was removed: $Path"
  Assert ([IO.File]::ReadAllText($Path) -ceq $Files[$Path]) "File was changed: $Path"
 }
}
# Replace only the download boundary. The matching bundled installer still verifies
# its real SHA256SUMS and installs the exact versioned executable.
function Invoke-WebRequest {
 param([switch]$UseBasicParsing,[string]$Uri,[string]$OutFile)
 $Name=if($Uri -ceq "$env:TOFA_RELEASE_BASE_URL/$Asset"){$Asset}
       elseif($Uri -ceq "$env:TOFA_RELEASE_BASE_URL/SHA256SUMS"){'SHA256SUMS'}
       else {throw "Unexpected download: $Uri"}
 Copy-Item -LiteralPath (Join-Path $Dist $Name) -Destination $OutFile
 if($Corrupt -and $Name -eq $Asset){[IO.File]::AppendAllText($OutFile,'corrupt download')}
}
function Install-Candidate {
 & (Join-Path $Dist 'install.ps1') -Version $Version
}
function Helper-Processes {
 # Only helpers whose command line names this test's private temporary directory.
 @(Get-CimInstance Win32_Process -Filter "Name = 'powershell.exe'" | Where-Object {
  $_.CommandLine -and $_.CommandLine.Contains($Helpers+[IO.Path]::DirectorySeparatorChar)
 })
}
function Stop-Helpers {
 foreach($Helper in @(Helper-Processes)) {
  $Process=Get-Process -Id $Helper.ProcessId -ErrorAction SilentlyContinue
  if($Process -and !$Process.HasExited){
   $Process.Kill()
   Assert ($Process.WaitForExit(5000)) 'Could not stop test uninstall helper'
  }
 }
}
function Wait-Cleanup([string]$Out,[string]$Err,[int]$TimeoutSeconds=20) {
 $Timer=[Diagnostics.Stopwatch]::StartNew()
 while(@(Helper-Processes).Count) {
  if($Timer.Elapsed.TotalSeconds -ge $TimeoutSeconds){
   Stop-Helpers
   throw "Uninstall helper timeout after ${TimeoutSeconds}s. $(Read-Log $Err)"
  }
  Start-Sleep -Milliseconds 100
 }
 $Output=Read-Log $Out
 $ErrorOutput=Read-Log $Err
 if($ErrorOutput -or !$Output.Contains('Existing terminals may retain the old PATH entry.')) {
  throw "Uninstall helper failed or was cancelled; cleanup incomplete. $ErrorOutput $Output"
 }
 return $Output
}
function Run-Process([string]$File,[string[]]$Arguments,[string]$Phase) {
 $script:Sequence++
 $Out=Join-Path $Temp "$Sequence.out"
 $Err=Join-Path $Temp "$Sequence.err"
 $Job=Join-Path $Temp "$Sequence.job.json"
 # JSON preserves argument boundaries across PowerShell/Python/native processes.
 # Logs remain scratch-only; the runner retains allowlisted failure metadata.
 @{executable=$File;arguments=@($Arguments);stdout=$Out;stderr=$Err;timeout_ms=10000} |
  ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $Job -Encoding UTF8
 & $Python $ProcessRunner --job $Job --phase $Phase --diagnostics $Diagnostics
 Assert ($LASTEXITCODE -eq 0) "Lifecycle process failed in $Phase; inspect retained sanitized diagnostics"
 return @{Out=$Out;Err=$Err;Text=(Read-Log $Out)}
}
function Uninstall-Candidate([switch]$Purge) {
 $Arguments=@('uninstall')
 if($Purge){$Arguments+='--purge'}
 $Phase=if($Purge){'uninstall_purge'}else{'uninstall_preserve'}
 $Result=Run-Process $Binary $Arguments $Phase
 Assert ($Result.Text.Contains('Uninstaller started;')) 'CLI did not start its asynchronous helper'
 $Output=Wait-Cleanup $Result.Out $Result.Err
 Assert ($Output.Contains('Removed tofa')) 'Missing cleanup completion message'
 Assert (@(Get-ChildItem -LiteralPath $Helpers -Filter 'tofa-uninstall-*.ps1').Count -eq 0) 'Successful helper did not remove itself'
}
function Fresh-Probe([switch]$Removed) {
 # A child normally inherits stale PATH. Reconstruct it from persistent stores,
 # as a new login would, before launching a new Windows PowerShell process.
 $env:Path=[Environment]::ExpandEnvironmentVariables(
  [Environment]::GetEnvironmentVariable('Path','Machine')+';'+[Environment]::GetEnvironmentVariable('Path','User'))
 # The installer's documented session activation isolates a custom test install
 # when this non-CI account already has an ordinary tofa earlier in user PATH.
 if($DisposableVM -and !$Removed){$env:Path=$Bin+';'+(($env:Path -split ';' | Where-Object {$_ -ne $Bin}) -join ';')}
 try {
  $Arguments=@('-NoProfile','-File',(Join-Path $Temp 'probe.ps1'),'-ExpectedBinary',$Binary,'-Version',$Version)
  if($Removed){$Arguments+='-Removed'}
  $Phase=if($Removed){'fresh_probe_removed'}else{'fresh_probe_installed'}
  $null=Run-Process $PowerShell $Arguments $Phase
 } finally {$env:Path=$OriginalEnv['Path']}
}
function Assert-Installed {
 Fresh-Probe
 Assert ((Get-FileHash -LiteralPath $Binary).Hash -eq (Get-FileHash -LiteralPath (Join-Path $Dist $Asset)).Hash) 'Installed candidate bytes differ'
 $Entries=@([Environment]::GetEnvironmentVariable('Path','User') -split ';')
 Assert (@($Entries | Where-Object {$_ -eq $Bin}).Count -eq 1) 'Persistent PATH duplicates or omits installation'
 Assert (($Entries | Where-Object {$_ -ne $Bin}) -join ';' -ceq $ExpectedUserPath) 'Unrelated user PATH entries changed'
 Assert-Files $Saved
 Assert-Files $Unrelated
}
function Assert-Removed([switch]$Purge) {
 foreach($Path in @($Binary,(Join-Path $Root '.path-owned'))) {Assert (!(Test-Path -LiteralPath $Path)) "Cleanup retained $Path"}
 Assert ([Environment]::GetEnvironmentVariable('Path','User') -ceq $ExpectedUserPath) 'PATH cleanup removed unrelated entries or retained owned entry'
 Fresh-Probe -Removed
 Assert-Files $Unrelated
 if($Purge){
  foreach($Path in @($Saved.Keys)+@((Join-Path $Root '.tofa-install'),(Join-Path $Config 'keyring-refs'),(Join-Path $Config '.auth-lock'))) {
   Assert (!(Test-Path -LiteralPath $Path)) "Purge retained $Path"
  }
 }else{Assert-Files $Saved}
}
try {
 New-Item -ItemType Directory -Path $Config,$Helpers,$UnrelatedPath | Out-Null
 $env:LOCALAPPDATA=Join-Path $Temp 'local'
 $env:TOFA_INSTALL_DIR=$null
 $env:TOFA_RELEASE_BASE_URL='https://fixture.invalid/releases/download/'+$Version
 $env:TEMP=$Helpers;$env:TMP=$Helpers
 [Environment]::SetEnvironmentVariable('Path',$ExpectedUserPath,'User')
 $Reference='0123456789abcdef0123456789abcdef'
 $Saved[(Join-Path $Config 'config.yml')]="version: 1`nproject_id: synthetic-project`nmodel: synthetic-model`ncredential_backend: file`ncredential_ref: '$Reference'`n"
 $Saved[(Join-Path $Config 'credentials.yml')]="'$Reference': synthetic-key`n"
 $Other=Join-Path $Temp 'other-client'
 New-Item -ItemType Directory -Path $Other | Out-Null
 $Unrelated[(Join-Path $Other 'credentials.yml')]='unrelated synthetic credential'
 $Unrelated[(Join-Path $Config 'unrelated.txt')]='keep config neighbor'
 foreach($Files in @($Saved,$Unrelated)){foreach($Path in $Files.Keys){[IO.File]::WriteAllText($Path,$Files[$Path])}}
 @'
param([string]$ExpectedBinary,[string]$Version,[switch]$Removed)
$ErrorActionPreference='Stop'
$Bin=Split-Path -Parent $ExpectedBinary
$Count=@($env:Path -split ';' | Where-Object {$_ -eq $Bin}).Count
$Found=@(Get-Command tofa -CommandType Application -All -ErrorAction SilentlyContinue)
if($Removed){
 if($Count -ne 0 -or @($Found | Where-Object {$_.Source -eq $ExpectedBinary}).Count){throw 'Removed candidate is still discoverable'}
 exit 0
}
if($Count -ne 1 -or !$Found.Count -or $Found[0].Source -ne $ExpectedBinary){throw "Fresh environment did not resolve candidate exactly once: count=$Count; found=$($Found.Source -join '|'); expected=$ExpectedBinary"}
$Actual=& tofa --version
if($LASTEXITCODE -ne 0 -or $Actual -cne "tofa $Version"){throw "Wrong candidate version: $Actual"}
$Help=& tofa --help
if($LASTEXITCODE -ne 0 -or !($Help -match 'tofa uninstall')){throw 'Candidate invocation failed'}
'@ | Set-Content -LiteralPath (Join-Path $Temp 'probe.ps1') -Encoding UTF8

 Fresh-Probe -Removed
 Install-Candidate
 Assert-Installed
 foreach($Name in @('unrelated.txt','bin/other-tool.txt')) {
  $Path=Join-Path $Root $Name
  $Unrelated[$Path]='keep installation neighbor'
  [IO.File]::WriteAllText($Path,$Unrelated[$Path])
 }
 Install-Candidate
 Assert-Installed
 Uninstall-Candidate
 Assert-Removed
 Install-Candidate
 Assert-Installed
 Write-Host 'PASS: actual candidate, fresh PATH, repeated install, asynchronous preserve and reinstall'

 $Corrupt=$true
 $Rejected=$false
 try{Install-Candidate}catch{Assert ($_.Exception.Message -match 'Checksum mismatch') "Unexpected download failure: $_";$Rejected=$true}
 $Corrupt=$false
 Assert $Rejected 'Corrupt candidate was accepted'
 Assert-Installed
 Write-Host 'PASS: corrupt upgrade preserves working candidate and state'

 $Lock=Join-Path $Config '.auth-lock'
 New-Item -ItemType Directory -Path $Lock | Out-Null
 $Rejected=$false
 try{Uninstall-Candidate -Purge}catch{
  Assert ($_.Exception.Message -match 'Authentication operation active') "Unexpected helper failure: $_"
  $Rejected=$true
 }
 Assert $Rejected 'Failed asynchronous purge was reported as successful'
 Assert-Installed
 Remove-Item -LiteralPath $Lock
 # A failed helper intentionally retains its script for diagnosis; dispose only
 # this attempt's scratch script once the process has stopped.
 Get-ChildItem -LiteralPath $Helpers -Filter 'tofa-uninstall-*.ps1' | Remove-Item
 Write-Host 'PASS: asynchronous helper failure is observable and retryable'

 # Exercise deadline/cancellation detection with the real recovery helper held
 # at its public -WaitPid boundary. It must never reach destructive cleanup.
 foreach($Mode in @('timeout','cancel')) {
  $Blocker=Start-Process -FilePath $PowerShell -ArgumentList @('-NoProfile','-Command','Start-Sleep -Seconds 60') -PassThru -NoNewWindow
  $Helper=$null
  try {
   $Path=Join-Path $Helpers 'tofa-uninstall-blocked.ps1'
   Copy-Item -LiteralPath (Join-Path $Dist 'uninstall.ps1') -Destination $Path
   $Out=Join-Path $Temp "$Mode.out";$Err=Join-Path $Temp "$Mode.err"
   $Helper=Start-Process -FilePath $PowerShell -ArgumentList @('-NoProfile','-File',('"'+$Path+'"'),'-WaitPid',$Blocker.Id) -PassThru -NoNewWindow -RedirectStandardOutput $Out -RedirectStandardError $Err
   Start-Sleep -Milliseconds 500
   Assert (!$Helper.HasExited) "Blocked helper exited early: $(Read-Log $Err)"
   if($Mode -eq 'cancel'){$Helper.Kill();Assert ($Helper.WaitForExit(5000)) 'Cancelled helper did not exit'}
   $Rejected=$false
   try{$null=Wait-Cleanup $Out $Err -TimeoutSeconds 1}catch{
    $Expected=if($Mode -eq 'timeout'){'helper timeout'}else{'cancelled; cleanup incomplete'}
    Assert ($_.Exception.Message.Contains($Expected)) "Unexpected ${Mode} result: $_"
    $Rejected=$true
   }
   Assert $Rejected "Helper $Mode was reported as successful"
   Assert-Installed
  }finally{
   if($Helper -and !$Helper.HasExited){$Helper.Kill();$Helper.WaitForExit(5000) | Out-Null}
   if(!$Blocker.HasExited){$Blocker.Kill();$Blocker.WaitForExit(5000) | Out-Null}
   if($Helper){$Helper.Dispose()};$Blocker.Dispose()
   Remove-Item -LiteralPath $Path -ErrorAction SilentlyContinue
  }
 }
 Write-Host 'PASS: helper timeout and cancellation remain observable, with state preserved'
 Uninstall-Candidate -Purge
 Assert-Removed -Purge
 Write-Host 'PASS: explicit purge removes owned state and retains unrelated files/credentials'
} finally {
 # Stop outstanding helpers before restoring PATH so they cannot mutate it later.
 try{Stop-Helpers}finally{
  [Environment]::SetEnvironmentVariable('Path',$OriginalUserPath,'User')
  foreach($Name in $OriginalEnv.Keys){[Environment]::SetEnvironmentVariable($Name,$OriginalEnv[$Name],'Process')}
  if(Test-Path -LiteralPath $Temp){Remove-Item -LiteralPath $Temp -Recurse -Force}
 }
}
Write-Host 'Native Windows candidate lifecycle passed; test files and user PATH restored.'
