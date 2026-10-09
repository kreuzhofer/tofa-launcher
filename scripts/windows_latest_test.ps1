# Native Windows public installer checks. Synthetic state; no user PATH or vault changes.
$ErrorActionPreference='Stop'
$Temp=Join-Path ([IO.Path]::GetTempPath()) ('tofa-latest-'+[Guid]::NewGuid().ToString('N'))
$SavedLocal=$env:LOCALAPPDATA; $SavedRoot=$env:TOFA_INSTALL_DIR; $SavedBase=$env:TOFA_RELEASE_BASE_URL
$HostArchitectures=@(Get-CimInstance Win32_Processor | Select-Object -ExpandProperty Architecture -Unique)
if($HostArchitectures.Count -ne 1){throw 'Expected one native architecture'}
$Arch=switch($HostArchitectures[0]) {9 {'amd64'} 12 {'arm64'} default {throw 'Unsupported architecture'}}
function Assert($Condition,[string]$Message){if(!$Condition){throw $Message}}
$global:TofaLatestCalls=0
$global:TofaLatestDownloads=0
$global:TofaLatestMode='prerelease'
$global:TofaLatestTag='v1.2.3'
$global:TofaLatestAsset="tofa_v1.2.3_windows_${Arch}.exe"
function global:Invoke-RestMethod {
 param([string]$Uri,[int]$TimeoutSec)
 Assert ($Uri -eq 'https://api.github.com/repos/kreuzhofer/tofa-launcher/releases/latest') 'Unexpected metadata URL'
 $global:TofaLatestCalls++
 if($global:TofaLatestMode -eq 'unavailable'){throw 'Fixture API unavailable'}
 $Tag=if($global:TofaLatestCalls -eq 1){$global:TofaLatestTag}else{'v9.9.9'}
 $Result=@{tag_name=$Tag;draft=$false;prerelease=$false}
 switch($global:TofaLatestMode){
  'prerelease' {$Result.prerelease=$true}
  'draft' {$Result.draft=$true}
  'missing' {$Result.Remove('tag_name')}
  'wrong-type' {$Result.tag_name=123}
  'string-flag' {$Result.prerelease='false'}
 }
 return [PSCustomObject]$Result
}
function global:Invoke-WebRequest {
 param([string]$Uri,[string]$OutFile,[switch]$UseBasicParsing)
 $global:TofaLatestDownloads++
 $Base="https://github.com/kreuzhofer/tofa-launcher/releases/download/$global:TofaLatestTag"
 Assert ($Uri -in @("$Base/$global:TofaLatestAsset","$Base/SHA256SUMS")) 'Download was not pinned to the resolved tag'
 if($global:TofaLatestMode -eq 'download-failure'){throw 'Fixture download failed'}
 $Bytes=[Text.Encoding]::UTF8.GetBytes('new fixture binary')
 if($Uri.EndsWith('/SHA256SUMS')){
  $Hasher=[Security.Cryptography.SHA256]::Create()
  try{$Hash=([BitConverter]::ToString($Hasher.ComputeHash($Bytes))).Replace('-','').ToLower()}finally{$Hasher.Dispose()}
  if($global:TofaLatestMode -eq 'checksum-mismatch'){$Hash='0'*64}
  [IO.File]::WriteAllText($OutFile,"$Hash  $global:TofaLatestAsset`n")
 }else{[IO.File]::WriteAllBytes($OutFile,$Bytes)}
}
try{
 $env:LOCALAPPDATA=$Temp; $env:TOFA_INSTALL_DIR=Join-Path $Temp 'install'; $env:TOFA_RELEASE_BASE_URL=$null
 $Bin=Join-Path $env:TOFA_INSTALL_DIR 'bin/tofa.exe'
 New-Item -ItemType Directory -Path (Split-Path $Bin) -Force | Out-Null
 [IO.File]::WriteAllText((Join-Path $env:TOFA_INSTALL_DIR '.tofa-install'),'tofa-install-v1')
 [IO.File]::WriteAllText($Bin,'old fixture binary')
 $Sentinel=Join-Path $env:TOFA_INSTALL_DIR 'unrelated.txt'
 [IO.File]::WriteAllText($Sentinel,'preserve me')
 $Config=Join-Path $env:LOCALAPPDATA 'tofa/config.yml'
 New-Item -ItemType Directory -Path (Split-Path $Config) -Force | Out-Null
 [IO.File]::WriteAllText($Config,"version: 1`nproject_id: synthetic-project`nmodel: synthetic-model`n")
 $ConfigBefore=[Convert]::ToBase64String([IO.File]::ReadAllBytes($Config))
 foreach($Mode in @('prerelease','draft','missing','wrong-type','string-flag','unavailable','download-failure','checksum-mismatch')){
  $global:TofaLatestMode=$Mode; $global:TofaLatestCalls=0; $global:TofaLatestDownloads=0; $Rejected=$false
  try{& "$PSScriptRoot/install.ps1" -NoModifyPath}catch{$Rejected=$true}
  Assert $Rejected "Invalid latest response accepted: $Mode"
  if($Mode -notin @('download-failure','checksum-mismatch')){Assert ($global:TofaLatestDownloads -eq 0) 'Invalid metadata reached asset download'}
  Assert ([IO.File]::ReadAllText($Bin) -eq 'old fixture binary') "Failed latest install changed binary: $Mode"
  Assert ([IO.File]::ReadAllText($Sentinel) -eq 'preserve me') 'Unrelated state changed'
  Assert ([Convert]::ToBase64String([IO.File]::ReadAllBytes($Config)) -eq $ConfigBefore) "Failed latest install changed settings: $Mode"
 }
 $global:TofaLatestMode='ok'
 foreach($Tag in @('v1.2.3-rc.1','v01.2.3','v1.2','../escape',"v1.2.3`nv2.3.4")){
  $global:TofaLatestTag=$Tag; $global:TofaLatestCalls=0; $global:TofaLatestDownloads=0; $Rejected=$false
  try{& "$PSScriptRoot/install.ps1" -NoModifyPath}catch{$Rejected=$true}
  Assert $Rejected "Invalid latest tag accepted: $Tag"
  Assert ($global:TofaLatestDownloads -eq 0) 'Invalid tag reached asset download'
  Assert ([IO.File]::ReadAllText($Bin) -eq 'old fixture binary') 'Invalid tag changed installation'
  Assert ([Convert]::ToBase64String([IO.File]::ReadAllBytes($Config)) -eq $ConfigBefore) 'Invalid tag changed settings'
 }
 $global:TofaLatestTag='v1.2.3'; $global:TofaLatestCalls=0
 & "$PSScriptRoot/install.ps1" -NoModifyPath
 Assert ($global:TofaLatestCalls -eq 1) 'Latest must be resolved once even if it moves'
 Assert ([IO.File]::ReadAllText($Bin) -eq 'new fixture binary') 'Omitted-version installation failed'
 $global:TofaLatestTag='v1.2.3-rc.1'; $global:TofaLatestAsset="tofa_v1.2.3-rc.1_windows_${Arch}.exe"; $global:TofaLatestCalls=0
 & "$PSScriptRoot/install.ps1" -Version v1.2.3-rc.1 -NoModifyPath
 Assert ($global:TofaLatestCalls -eq 0) 'Explicit version queried latest'
 Write-Host 'Latest stable and explicit-version Windows installer checks passed.'
}finally{
 Remove-Item Function:\Invoke-RestMethod,Function:\Invoke-WebRequest
 Remove-Variable TofaLatestCalls,TofaLatestDownloads,TofaLatestMode,TofaLatestTag,TofaLatestAsset -Scope Global
 $env:LOCALAPPDATA=$SavedLocal; $env:TOFA_INSTALL_DIR=$SavedRoot; $env:TOFA_RELEASE_BASE_URL=$SavedBase
 if(Test-Path -LiteralPath $Temp){Remove-Item -LiteralPath $Temp -Recurse -Force}
}
