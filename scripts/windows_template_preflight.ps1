# tofa-template-preflight -- read-only discovery under the guest agent identity.
$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
$requestJson='__REQUEST__'
$request=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($requestJson))|ConvertFrom-Json
$result=@{run=$request.run;phase='preflight';ok=$false;outcome='missing_prerequisites';reason='guest_discovery_failed'}
try {
  $os=Get-CimInstance Win32_OperatingSystem
  $processors=@(Get-CimInstance Win32_Processor)
  if($os.Caption -notmatch 'Windows 11' -or !$processors.Count -or @($processors|Where-Object {$_.Architecture -ne 12}).Count) {
    $result.reason='unsupported_guest';throw 'stop'
  }
  $result.os=@{name='Windows 11';version=$os.Version;build=$os.BuildNumber;architecture='ARM64'}
  $account=if($request.user -match '\\'){$request.user}else{$env:COMPUTERNAME+'\'+$request.user}
  try {$sid=([Security.Principal.NTAccount]$account).Translate([Security.Principal.SecurityIdentifier]).Value}
  catch {$result.reason='test_user_missing';throw 'stop'}
  $local=@(Get-LocalUser|Where-Object {$_.SID.Value -eq $sid -and $_.Enabled})
  if($local.Count -ne 1){$result.reason='test_user_missing';throw 'stop'}
  $sessions=@(Get-CimInstance Win32_Process -Filter "Name='explorer.exe'"|Where-Object {
    (Invoke-CimMethod -InputObject $_ -MethodName GetOwnerSid).Sid -eq $sid
  }|Select-Object -ExpandProperty SessionId -Unique)
  if($sessions.Count -ne 1 -or $sessions[0] -eq 0) {
    $result.outcome='bootstrap_required';$result.reason='test_user_sign_in_required';throw 'stop'
  }
  $package=@(Get-AppxPackage -User $sid -Name OpenAI.Codex)
  if($package.Count -eq 0 -and $request.operation -eq 'prepare') {
    $package=@(Get-AppxPackage -AllUsers -Name OpenAI.Codex)
    if($package.Count -eq 1){$result.register_package=$package[0].InstallLocation}
  }
  if($package.Count -ne 1 -or $package[0].Status -ne 'Ok' -or $package[0].Architecture -ne 'Arm64') {
    $result.reason='native_client_missing_or_ambiguous';throw 'stop'
  }
  $python=@(Get-ChildItem 'HKLM:\SOFTWARE\Python\PythonCore\*\InstallPath' -ErrorAction SilentlyContinue|ForEach-Object {
    (Get-ItemProperty $_.PSPath).ExecutablePath
  }|Where-Object {$_ -and (Test-Path -LiteralPath $_ -PathType Leaf)}|Select-Object -Unique)
  if($python.Count -ne 1){$result.reason='python_runtime_missing_or_ambiguous';throw 'stop'}
  $result.user=@{sid=$sid;session=[int]$sessions[0]}
  $result.python=$python[0]
  $result.ok=$true;$result.reason='prerequisites_discovered';$result.outcome='discovered'
} catch {}
$result|ConvertTo-Json -Depth 5 -Compress|Set-Content -Encoding UTF8 -LiteralPath ('C:\Users\Public\'+$request.run+'\preflight.json')
