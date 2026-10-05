$ErrorActionPreference = 'Stop'
$result = [ordered]@{started_utc=[DateTime]::UtcNow.ToString('o'); status='running'}
try {
  $result.identity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
  $result.os = Get-CimInstance Win32_OperatingSystem | Select-Object Caption,Version,BuildNumber,OSArchitecture
  $result.cpu = @(Get-CimInstance Win32_Processor | Select-Object Name,Architecture)
  $result.packages = @(Get-AppxPackage -AllUsers | Where-Object {$_.Name -match 'Codex|OpenAI|ChatGPT'} | Select-Object Name,Version,Architecture,PackageFullName,InstallLocation,Status)
  $result.processes = @(Get-Process | Where-Object {$_.ProcessName -match 'codex|chatgpt'} | Select-Object Id,ProcessName,Path)
  $result.users = @(Get-CimInstance Win32_UserProfile | Where-Object {-not $_.Special} | Select-Object LocalPath,Loaded)
  $result.desktop_links = @(Get-ChildItem 'C:\Users\SabreTest\Desktop','C:\Users\Public\Desktop','C:\ProgramData\Microsoft\Windows\Start Menu\Programs','C:\Users\SabreTest\AppData\Roaming\Microsoft\Windows\Start Menu\Programs' -Recurse -Filter '*.lnk' | Where-Object {$_.Name -match 'Codex|ChatGPT|OpenAI'} | Select-Object FullName)
  $result.uninstall = @(Get-ItemProperty 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*','HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*' | Where-Object {$_.DisplayName -match 'Codex|ChatGPT|OpenAI'} | Select-Object DisplayName,DisplayVersion,InstallLocation)
  $result.machine_policy_present = Test-Path 'C:\ProgramData\OpenAI\Codex\requirements.toml'
  $result.status='completed'; $result.exit_code=0
} catch { $result.status='failed'; $result.exit_code=1; $result.error=$_.Exception.Message }
$result.finished_utc=[DateTime]::UtcNow.ToString('o')
$result | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 'C:\Windows\Temp\tofa76-inventory.json'
exit $result.exit_code
