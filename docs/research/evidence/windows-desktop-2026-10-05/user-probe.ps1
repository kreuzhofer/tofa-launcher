$ErrorActionPreference='Stop'
$r=[ordered]@{started_utc=[DateTime]::UtcNow.ToString('o');status='running'}
try {
$r.identity=[Security.Principal.WindowsIdentity]::GetCurrent().Name
$r.session_id=[Diagnostics.Process]::GetCurrentProcess().SessionId
$r.packages=@(Get-AppxPackage OpenAI.Codex | Select-Object Name,Version,Architecture,Status,InstallLocation)
$r.profile_paths=@((Join-Path $env:USERPROFILE '.codex'),(Join-Path $env:APPDATA 'Codex') | ForEach-Object {[ordered]@{path=$_;exists=(Test-Path $_)}})
$r.python=@(Get-Command python.exe -ErrorAction SilentlyContinue | Select-Object Source)
$r.native_app_processes=@(Get-Process -Name ChatGPT -ErrorAction SilentlyContinue | Select-Object Id,SessionId,Path)
$r.status='completed';$r.exit_code=0
}catch{$r.status='failed';$r.exit_code=1;$r.error=$_.Exception.Message}
$r.finished_utc=[DateTime]::UtcNow.ToString('o');$r|ConvertTo-Json -Depth 8|Set-Content -Encoding UTF8 'C:\Windows\Temp\tofa76-user-probe.json';exit $r.exit_code
