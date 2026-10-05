# Direct encoded command; does not bypass or change guest script execution policy.
$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
$root='__ROOT__'
$request=Get-Content -Raw -LiteralPath ($root+'\request.json')|ConvertFrom-Json
$failure=@{run=$request.run;phase='native';ok=$false;reason='native_prerequisites_failed'}
try {
  $sid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
  $session=[Diagnostics.Process]::GetCurrentProcess().SessionId
  if($sid -ne $request.sid -or $session -ne $request.session -or $session -eq 0){$failure.reason='wrong_user_session';throw 'stop'}
  if($request.register_package) {
    if(Get-AppxPackage -Name OpenAI.Codex){throw 'package registration changed since discovery'}
    $installation=Get-Item -LiteralPath $request.register_package
    if($installation.Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'unsafe package target'}
    Add-AppxPackage -DisableDevelopmentMode -Register ($installation.FullName+'\AppxManifest.xml')
  }
  $package=@(Get-AppxPackage -Name OpenAI.Codex)
  if($package.Count -ne 1 -or $package[0].Status -ne 'Ok' -or $package[0].Architecture -ne 'Arm64'){throw 'ambiguous native package'}
  $package=$package[0]
  $bundled=Join-Path $package.InstallLocation 'app\resources\codex.exe'
  $hash=(Get-FileHash -LiteralPath $bundled -Algorithm SHA256).Hash.ToLowerInvariant()
  $candidates=@(Get-ChildItem (Join-Path $env:LOCALAPPDATA 'OpenAI\Codex\bin') -Filter codex.exe -Recurse -ErrorAction SilentlyContinue|Where-Object {
    !($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -and (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant() -eq $hash
  })
  if($candidates.Count -eq 0){$failure.reason='native_client_first_launch_required';throw 'stop'}
  if($candidates.Count -ne 1){$failure.reason='engine_identity_mismatch';throw 'stop'}
  if(Get-Process ChatGPT,codex,bridge -ErrorAction SilentlyContinue|Where-Object {$_.SessionId -eq $session}){$failure.reason='native_client_busy';throw 'stop'}
  @{engine=$candidates[0].FullName;package=$package.PackageFullName;client_version=[string]$package.Version;
    architecture=[string]$package.Architecture;package_engine_sha256=$hash;sid=$sid;session=$session}|
    ConvertTo-Json|Set-Content -Encoding UTF8 ($root+'\output\identity.json')
  & $request.python ($root+'\probe.py')
  exit $LASTEXITCODE
} catch {
  $failure|ConvertTo-Json -Compress|Set-Content -Encoding UTF8 ($root+'\output\result.json')
  exit 2
}
