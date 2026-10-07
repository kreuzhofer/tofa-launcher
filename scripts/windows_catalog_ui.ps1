# Synthetic picker only; scope every operation to the owned, verified app.
$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
$request=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('__REQUEST__'))|ConvertFrom-Json
$result=@{ok=$false;stage='identity';choices=@();controls=@()}
try {
  Add-Type -AssemblyName UIAutomationClient
  Add-Type -AssemblyName UIAutomationTypes
  $process=Get-Process -Id $request.pid
  if($process.StartTime.ToUniversalTime().Ticks -ne $request.started_ticks -or $process.Path -ne $request.executable){throw 'identity'}
  $condition=New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty,[int]$request.pid)
  function Elements {
    $process.Refresh()
    $scope=[System.Windows.Automation.AutomationElement]::FromHandle($process.MainWindowHandle)
    return @($scope.FindAll([System.Windows.Automation.TreeScope]::Descendants,$condition)|Where-Object {$_.Current.IsEnabled -and !$_.Current.IsOffscreen})
  }
  function Activate($element) {
    $pattern=$null
    if($element.TryGetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern,[ref]$pattern)){$pattern.Expand();return}
    if($element.TryGetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern,[ref]$pattern)){$pattern.Select();return}
    $element.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
  }
  $deadline=[DateTime]::UtcNow.AddSeconds(25)
  $result.stage='model_button'
  do {
    $all=Elements
    $button=@($all|Where-Object {$_.Current.ControlType -eq [System.Windows.Automation.ControlType]::Button -and $_.Current.Name -match 'tofa-catalog-a'})
    if($button.Count -eq 1){break}
    Start-Sleep -Milliseconds 300
  } while([DateTime]::UtcNow -lt $deadline)
  $result.controls=@($all|Where-Object {$_.Current.Name -match '^(tofa-catalog-[ab]|Model|Choose model|Select model|Reasoning|Low|High|Medium|Change model|Set up|Continue|Get started|Sign in)' -and $_.Current.Name.Length -lt 100}|ForEach-Object {@{name=$_.Current.Name;kind=$_.Current.ControlType.ProgrammaticName}}|Select-Object -First 24)
  if($button.Count -ne 1){throw 'missing'}
  Activate $button[0]
  Start-Sleep -Milliseconds 500
  $result.stage='model_choice'
  $all=Elements
  $modelList=@($all|Where-Object {$_.Current.Name -eq 'Select model' -and $_.Current.ControlType -eq [System.Windows.Automation.ControlType]::MenuItem})
  if($modelList.Count -eq 1){Activate $modelList[0];Start-Sleep -Milliseconds 500;$all=Elements}
  $result.choices=@($all|Where-Object {$_.Current.Name -match '^tofa-catalog-[ab]' }|ForEach-Object {if($_.Current.Name -match '^(tofa-catalog-[ab])'){$Matches[1]}}|Select-Object -Unique)
  $choice=@($all|Where-Object {$_.Current.Name -match '^tofa-catalog-b' -and $_.Current.ControlType -in @([System.Windows.Automation.ControlType]::MenuItem,[System.Windows.Automation.ControlType]::RadioButton,[System.Windows.Automation.ControlType]::ListItem,[System.Windows.Automation.ControlType]::Button)})
  if($choice.Count -ne 1){throw 'missing'}
  Activate $choice[0]
  Start-Sleep -Milliseconds 500
  $result.stage='reasoning_button'
  $selectionDeadline=[DateTime]::UtcNow.AddSeconds(10)
  do {
    $all=Elements
    $power=@($all|Where-Object {$_.Current.Name -eq 'Power' -and $_.Current.ControlType -eq [System.Windows.Automation.ControlType]::MenuItem})
    $reasoning=@($all|Where-Object {$_.Current.ControlType -eq [System.Windows.Automation.ControlType]::Button -and $_.Current.Name -match '^tofa-catalog-b'})
    if($power.Count -eq 1 -or $reasoning.Count -eq 1){break}
    Start-Sleep -Milliseconds 300
  } while([DateTime]::UtcNow -lt $selectionDeadline)
  if($power.Count -ne 1){
    if($reasoning.Count -ne 1){throw 'missing'}
    Activate $reasoning[0]
    Start-Sleep -Milliseconds 500
  }
  $result.stage='reasoning_choice'
  $all=Elements
  $power=@($all|Where-Object {$_.Current.Name -eq 'Power' -and $_.Current.ControlType -eq [System.Windows.Automation.ControlType]::MenuItem})
  if($power.Count -eq 1){
    # The native Power menu item is a keyboard slider, not a submenu.
    # Send keys only after verifying focus still belongs to this owned app.
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class CatalogFocus {
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr window, out uint process);
}
'@
    $power[0].SetFocus()
    foreach($key in @('{RIGHT}','{ENTER}','{ESC}')){
      [uint32]$focusedProcess=0
      [CatalogFocus]::GetWindowThreadProcessId([CatalogFocus]::GetForegroundWindow(),[ref]$focusedProcess)|Out-Null
      if($focusedProcess -ne $request.pid){throw 'focus changed'}
      [System.Windows.Forms.SendKeys]::SendWait($key)
      Start-Sleep -Milliseconds 300
    }
  } else {
    $high=@($all|Where-Object {$_.Current.Name -match '^High' -and $_.Current.ControlType -in @([System.Windows.Automation.ControlType]::MenuItem,[System.Windows.Automation.ControlType]::RadioButton,[System.Windows.Automation.ControlType]::ListItem,[System.Windows.Automation.ControlType]::Button)})
    if($high.Count -ne 1){throw 'missing'}
    Activate $high[0]
  }
  $result.ok=$true
  $result.stage='complete'
} catch {
  $result.error=$_.Exception.GetType().Name
  try {$result.controls=@((Elements)|Where-Object {$_.Current.Name -and $_.Current.Name.Length -lt 160 -and $_.Current.Name -notmatch '[@\\/]' }|ForEach-Object {@{name=$_.Current.Name;kind=$_.Current.ControlType.ProgrammaticName}}|Select-Object -First 96)}catch{}
}
$result|ConvertTo-Json -Depth 5 -Compress
