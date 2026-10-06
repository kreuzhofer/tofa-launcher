# Native accessibility actions, restricted to the verified owned app process.
$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
$request=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('__REQUEST__'))|ConvertFrom-Json
$result=@{ok=$false;reason='desktop_control_unsupported'}
try {
  Add-Type -AssemblyName UIAutomationClient
  Add-Type -AssemblyName UIAutomationTypes
  $process=Get-Process -Id $request.pid
  if($process.StartTime.ToUniversalTime().Ticks -ne $request.started_ticks -or $process.Path -ne $request.executable){throw 'identity changed'}
  $condition=New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty,[int]$request.pid)
  function Find-Control($names,$kind) {
    $elements=[System.Windows.Automation.AutomationElement]::RootElement.FindAll([System.Windows.Automation.TreeScope]::Descendants,$condition)
    $matches=@($elements|Where-Object {$_.Current.ControlType -eq $kind -and $_.Current.Name -in $names -and $_.Current.IsEnabled -and !$_.Current.IsOffscreen})
    if($matches.Count -ne 1){return $null}
    return $matches[0]
  }
  function Invoke-Control($element) {
    if($null -eq $element){throw 'control unavailable'}
    $pattern=$element.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
    $pattern.Invoke()
  }
  if($request.action -eq 'submit') {
    $deadline=[DateTime]::UtcNow.AddSeconds(15)
    do {
      $button=Find-Control @('Send','Send message','Send prompt','Submit') ([System.Windows.Automation.ControlType]::Button)
      if($null -ne $button){break}
      Start-Sleep -Milliseconds 300
    } while([DateTime]::UtcNow -lt $deadline)
    Invoke-Control $button
  } elseif($request.action -eq 'quit') {
    $deadline=[DateTime]::UtcNow.AddSeconds(15)
    do {
      $menu=Find-Control @('File','&File') ([System.Windows.Automation.ControlType]::MenuItem)
      if($null -ne $menu){break}
      Start-Sleep -Milliseconds 300
    } while([DateTime]::UtcNow -lt $deadline)
    if($null -eq $menu){throw 'file menu unavailable'}
    $expand=$null
    if($menu.TryGetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern,[ref]$expand)){$expand.Expand()}
    else {Invoke-Control $menu}
    do {
      $quit=Find-Control @('Quit ChatGPT','Quit ChatGPT Ctrl+Q','Quit Codex','Quit','Exit','Exit ChatGPT') ([System.Windows.Automation.ControlType]::MenuItem)
      if($null -ne $quit){break}
      Start-Sleep -Milliseconds 300
    } while([DateTime]::UtcNow -lt $deadline)
    Invoke-Control $quit
  } else {throw 'unsupported action'}
  $result.ok=$true
  $result.reason='invoked'
} catch {}
$result|ConvertTo-Json -Compress
