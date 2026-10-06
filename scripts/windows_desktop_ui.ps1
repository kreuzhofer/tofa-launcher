# Native accessibility actions, restricted to the verified owned app process.
$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
$request=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('__REQUEST__'))|ConvertFrom-Json
$result=@{ok=$false;reason='desktop_control_unsupported';stage='identity';error='other'}
try {
  Add-Type -AssemblyName UIAutomationClient
  Add-Type -AssemblyName UIAutomationTypes
  $process=Get-Process -Id $request.pid
  if($process.StartTime.ToUniversalTime().Ticks -ne $request.started_ticks -or $process.Path -ne $request.executable){$result.error='identity_mismatch';throw 'identity changed'}
  $condition=New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty,[int]$request.pid)
  function Find-Control($names,$kind) {
    $result.stage='search'
    $process.Refresh()
    $scope=[System.Windows.Automation.AutomationElement]::FromHandle($process.MainWindowHandle)
    if($request.action -eq 'quit'){$scope=[System.Windows.Automation.AutomationElement]::RootElement}
    $elements=$scope.FindAll([System.Windows.Automation.TreeScope]::Descendants,$condition)
    $matches=@($elements|Where-Object {$_.Current.ControlType -eq $kind -and $_.Current.Name -in $names -and $_.Current.IsEnabled -and !$_.Current.IsOffscreen})
    if($matches.Count -ne 1){return $null}
    return $matches[0]
  }
  function Invoke-Control($element) {
    if($null -eq $element){$result.error='missing_control';throw 'control unavailable'}
    $result.stage='pattern'
    $pattern=$element.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
    $result.stage='invoke'
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
  } elseif($request.action -eq 'configure') {
    $deadline=[DateTime]::UtcNow.AddSeconds(30)
    do {
      $permission=Find-Control @('Change permissions') ([System.Windows.Automation.ControlType]::Button)
      if($null -ne $permission){break}
      Start-Sleep -Milliseconds 300
    } while([DateTime]::UtcNow -lt $deadline)
    if($null -eq $permission){$result.error='missing_control';throw 'permission control unavailable'}
    $result.stage='pattern'
    $expand=$permission.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern)
    $result.stage='expand'
    $expand.Expand()
    do {
      $automatic=Find-Control @('Approve for me','Approve for me Only ask for actions detected as potentially unsafe') ([System.Windows.Automation.ControlType]::MenuItem)
      if($null -ne $automatic){break}
      Start-Sleep -Milliseconds 300
    } while([DateTime]::UtcNow -lt $deadline)
    if($null -eq $automatic){$result.error='missing_control';throw 'automatic review control unavailable'}
    $result.stage='select'
    $selection=$null
    if($automatic.TryGetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern,[ref]$selection)){$selection.Select()}
    else {Invoke-Control $automatic}
  } elseif($request.action -eq 'quit') {
    $deadline=[DateTime]::UtcNow.AddSeconds(15)
    do {
      $menu=Find-Control @('File','&File') ([System.Windows.Automation.ControlType]::MenuItem)
      if($null -ne $menu){break}
      Start-Sleep -Milliseconds 300
    } while([DateTime]::UtcNow -lt $deadline)
    if($null -eq $menu){$result.error='missing_control';throw 'file menu unavailable'}
    $result.stage='pattern'
    $expand=$null
    if($menu.TryGetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern,[ref]$expand)){$result.stage='expand';$expand.Expand()}
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
} catch {
  # Never retain exception messages or accessibility names from the user session.
  $controlException=$_.Exception
  while($null -ne $controlException) {
    switch($controlException.GetType().FullName) {
      'System.Windows.Automation.ElementNotAvailableException' {$result.error='stale_element'}
      'System.Windows.Automation.ElementNotEnabledException' {$result.error='element_not_enabled'}
      'System.InvalidOperationException' {if($result.error -eq 'other'){$result.error='invalid_operation'}}
    }
    $controlException=$controlException.InnerException
  }
}
$result|ConvertTo-Json -Compress
