param([string]$Version='latest', [switch]$NoModifyPath)
$ErrorActionPreference='Stop'
$Repo='kreuzhofer/tofa-launcher'
if ($Version -notmatch '^[A-Za-z0-9._-]+$') { throw 'Invalid release tag' }
$Root=Join-Path $env:LOCALAPPDATA 'tofa\install'
if ($env:TOFA_INSTALL_DIR) {$Root=$env:TOFA_INSTALL_DIR}
if (![IO.Path]::IsPathRooted($Root)) {throw 'Install directory must be absolute'}
function Assert-NotLink([string]$Path) {
 if ((Test-Path -LiteralPath $Path) -and ((Get-Item -Force -LiteralPath $Path).Attributes -band [IO.FileAttributes]::ReparsePoint)) {throw "Refusing reparse point: $Path"}
}
Assert-NotLink $Root
$Manifest=Join-Path $Root '.tofa-install'
if ((Test-Path -LiteralPath $Root) -and !(Test-Path -LiteralPath $Manifest) -and @(Get-ChildItem -Force -LiteralPath $Root).Count) {throw 'Existing directory is not owned by tofa'}
if ((Test-Path -LiteralPath $Manifest) -and ((Get-Content -Raw -LiteralPath $Manifest).Trim() -ne 'tofa-install-v1')) {throw 'Unknown install manifest'}
# Process environment and GetNativeSystemInfo can report the emulated x64
# architecture on ARM64. Query the host machine explicitly instead.
if (-not ('Tofa.InstallArchitecture' -as [type])) {
 Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
namespace Tofa {
 public static class InstallArchitecture {
  [DllImport("kernel32.dll", SetLastError = true)]
  [return: MarshalAs(UnmanagedType.Bool)]
  public static extern bool IsWow64Process2(IntPtr process, out ushort processMachine, out ushort nativeMachine);
 }
}
'@
}
[UInt16]$ProcessMachine=0
[UInt16]$NativeMachine=0
if (![Tofa.InstallArchitecture]::IsWow64Process2([IntPtr]::new(-1),[ref]$ProcessMachine,[ref]$NativeMachine)) {
 throw [ComponentModel.Win32Exception]::new([Runtime.InteropServices.Marshal]::GetLastWin32Error())
}
$Arch=switch ($NativeMachine) {0xAA64 {'arm64'} 0x8664 {'amd64'} default {throw "Unsupported native Windows architecture: $NativeMachine"}}
if ($Version -eq 'latest') {
 try {$Release=Invoke-RestMethod "https://api.github.com/repos/$Repo/releases/latest" -TimeoutSec 60}
 catch {throw 'Could not resolve latest stable release; retry or select an existing -Version'}
 if ($Release.tag_name -isnot [string] -or
     $Release.tag_name -cnotmatch '\Av(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\z' -or
     $Release.prerelease -isnot [bool] -or $Release.prerelease -or
     $Release.draft -isnot [bool] -or $Release.draft) {
  throw 'Invalid latest stable release metadata'
 }
 $Version=$Release.tag_name
}
if ($Version -notmatch '^[A-Za-z0-9._-]+$') {throw 'Invalid resolved release tag'}
$Asset="tofa_${Version}_windows_${Arch}.exe"
$Base="https://github.com/$Repo/releases/download/$Version"
if ($env:TOFA_RELEASE_BASE_URL) {$Base=$env:TOFA_RELEASE_BASE_URL}
if ($Base -notmatch '^https://') {throw 'Release URL must use HTTPS'}
$Temp=Join-Path ([IO.Path]::GetTempPath()) ([Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $Temp | Out-Null
try {
 Invoke-WebRequest -UseBasicParsing "$Base/$Asset" -OutFile (Join-Path $Temp 'tofa.exe')
 Invoke-WebRequest -UseBasicParsing "$Base/SHA256SUMS" -OutFile (Join-Path $Temp 'SHA256SUMS')
 # Count all entries for this asset before validating the digest, so a malformed
 # duplicate cannot be hidden by filtering only for well-formed hashes.
 $Lines=@(Get-Content (Join-Path $Temp 'SHA256SUMS') | Where-Object {
  $Fields=$_.Trim() -split '\s+'
  $Fields.Count -ge 2 -and $Fields[1] -ceq $Asset
 })
 if ($Lines.Count -ne 1 -or $Lines[0] -cnotmatch ('^[a-fA-F0-9]{64}\s+'+[regex]::Escape($Asset)+'\s*$')) {throw 'Missing, invalid or ambiguous checksum'}
 $Expected=($Lines[0].Trim() -split '\s+')[0]
 if ((Get-FileHash (Join-Path $Temp 'tofa.exe') -Algorithm SHA256).Hash -ne $Expected) {throw 'Checksum mismatch; existing installation retained'}
 $Bin=Join-Path $Root 'bin'; Assert-NotLink $Bin
 New-Item -ItemType Directory -Force -Path $Bin | Out-Null
 $Target=Join-Path $Bin 'tofa.exe';Assert-NotLink $Target;Assert-NotLink $Manifest
 Set-Content -LiteralPath $Manifest -Value 'tofa-install-v1' -Encoding Ascii
 $Staged=Join-Path $Bin ([Guid]::NewGuid().ToString('N')+'.tmp')
 Copy-Item -LiteralPath (Join-Path $Temp 'tofa.exe') -Destination $Staged
 try {Move-Item -Force -LiteralPath $Staged -Destination $Target} finally {if(Test-Path -LiteralPath $Staged){Remove-Item -LiteralPath $Staged}}
 $PathMarker=Join-Path $Root '.path-owned';Assert-NotLink $PathMarker
 $PathSetupFailed=$false
 if (!$NoModifyPath) {
  try {
  $UserPath=[Environment]::GetEnvironmentVariable('Path','User')
  $Entries=@($UserPath -split ';' | Where-Object {$_})
  if ($Entries -notcontains $Bin) {
   [Environment]::SetEnvironmentVariable('Path',(($Entries+$Bin)-join ';'),'User')
   Set-Content -LiteralPath $PathMarker -Value $Bin -Encoding UTF8
  }
  } catch { $PathSetupFailed=$true; Write-Warning "Automatic PATH setup failed: $($_.Exception.Message)" }
 }
 $Quoted=$Bin.Replace("'","''")
 Write-Host "Installed tofa $Version in $Bin"
 Write-Host "Activate in this PowerShell session:"
 Write-Host "  `$env:Path = '$Quoted;' + `$env:Path"
 if($NoModifyPath -or $PathSetupFailed){Write-Host "Persist and activate in one line:"
 Write-Host "  [Environment]::SetEnvironmentVariable('Path', '$Quoted;' + [Environment]::GetEnvironmentVariable('Path','User'), 'User'); `$env:Path = '$Quoted;' + `$env:Path"}
 Write-Host 'Then run: tofa auth login'
} finally {Remove-Item -Recurse -Force -LiteralPath $Temp}
