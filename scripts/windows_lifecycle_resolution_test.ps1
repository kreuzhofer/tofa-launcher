# Exercise the lifecycle script's actual assignments with multiple PATH matches.
param([Parameter(Mandatory=$true)][string]$PythonExecutable)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$OriginalPath=$env:PATH
$Temp=Join-Path ([IO.Path]::GetTempPath()) ('tofa-resolution-'+[Guid]::NewGuid().ToString('N'))
try {
 $Shadow=Join-Path $Temp 'shadow'
 $First=Join-Path $Temp 'first'
 New-Item -ItemType Directory -Path $Shadow,$First | Out-Null
 if ([Environment]::OSVersion.Platform -eq 'Win32NT') {
  $ExpectedPython=(Resolve-Path -LiteralPath $PythonExecutable).Path
  $ExpectedPowerShell=(Get-Command powershell.exe -CommandType Application | Select-Object -First 1).Source
  $PythonName='python.exe'
  $Prefix=@((Split-Path $ExpectedPython),(Split-Path $ExpectedPowerShell))
 } else {
  # Portable PowerShell can exercise discovery without launching Windows code.
  $ExpectedPython=Join-Path $First 'python'
  $ExpectedPowerShell=Join-Path $First 'powershell.exe'
  New-Item -ItemType SymbolicLink -Path $ExpectedPython -Target $PythonExecutable | Out-Null
  New-Item -ItemType SymbolicLink -Path $ExpectedPowerShell -Target (Join-Path $PSHOME 'pwsh') | Out-Null
  $PythonName='python'
  $Prefix=@($First)
 }
 foreach($Name in @($PythonName,'powershell.exe')) {
  $Path=Join-Path $Shadow $Name
  [IO.File]::WriteAllText($Path,'must never execute this later PATH match')
  if ([Environment]::OSVersion.Platform -ne 'Win32NT') { & chmod +x $Path }
 }
 $env:PATH=(@($Prefix)+@($Shadow,$OriginalPath)) -join [IO.Path]::PathSeparator
 $Tokens=$null; $Errors=$null
 $Ast=[Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot 'windows_lifecycle_test.ps1'),[ref]$Tokens,[ref]$Errors)
 if($Errors){throw 'Lifecycle script parse failure'}
 foreach($Case in @(@{Variable='Python';Command='python';Expected=$ExpectedPython},@{Variable='PowerShell';Command='powershell.exe';Expected=$ExpectedPowerShell})) {
  if(@(Get-Command $Case.Command -CommandType Application -All).Count -lt 2){throw 'Fixture needs multiple executable matches'}
  $Assignments=@($Ast.FindAll({param($Node) $Node -is [Management.Automation.Language.AssignmentStatementAst] -and $Node.Left.Extent.Text -eq ('$'+$Case.Variable)},$true))
  if($Assignments.Count -ne 1){throw 'Expected one lifecycle executable assignment'}
  Invoke-Expression $Assignments[0].Extent.Text
  $Selected=Get-Variable -Name $Case.Variable -ValueOnly
  if($Selected -isnot [string] -or $Selected -cne $Case.Expected){throw "Lifecycle $($Case.Variable) must select the first executable, not combine PATH matches"}
 }
 $Output=& $Python -c 'print("resolution-ok")'
 if($LASTEXITCODE -ne 0 -or $Output -cne 'resolution-ok'){throw 'Selected Python did not execute'}
 Write-Host 'Lifecycle executable resolution passed with multiple PATH matches.'
} finally {
 $env:PATH=$OriginalPath
 Remove-Item -LiteralPath $Temp -Recurse -Force -ErrorAction SilentlyContinue
}
