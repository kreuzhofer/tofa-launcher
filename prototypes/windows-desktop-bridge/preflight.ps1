# PROTOTYPE: read-only ownership gate. Does not launch, adopt or terminate apps.
$ErrorActionPreference='Stop'
$r=[ordered]@{utc=[DateTime]::UtcNow.ToString('o');launched=$false}
try {
  $session=[Diagnostics.Process]::GetCurrentProcess().SessionId
  if ($session -eq 0) {throw 'interactive session required'}
  $apps=@(Get-Process -Name ChatGPT -ErrorAction SilentlyContinue | Where-Object {$_.SessionId -eq $session})
  $r.incumbent_count=$apps.Count
  if ($apps.Count -gt 0) {$r.reason='ordinary_app_running';$r.exit_code=41}
  else {$r.reason='no_incumbent_observed_not_launch_authorization';$r.exit_code=42}
} catch {$r.reason='discovery_failed';$r.exit_code=43}
$r|ConvertTo-Json -Depth 4|Set-Content -Encoding UTF8 (Join-Path $PSScriptRoot 'preflight.json')
exit $r.exit_code
