# tofa-template-protected-root -- no user-supplied paths or payloads are consumed.
$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
$root='C:\Users\Public\__RUN__'
foreach($path in @('C:\Users','C:\Users\Public')) {
  if((Get-Item -LiteralPath $path).Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'unsafe staging ancestor'}
}
if(Test-Path -LiteralPath $root){throw 'existing run root'}
New-Item -ItemType Directory -Path $root|Out-Null
& icacls.exe $root /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F'|Out-Null
if($LASTEXITCODE -ne 0){throw 'staging ACL failed'}
@{run='__RUN__';phase='staging';ok=$true}|ConvertTo-Json -Compress|
  Set-Content -Encoding UTF8 -LiteralPath ($root+'\staging.json')
