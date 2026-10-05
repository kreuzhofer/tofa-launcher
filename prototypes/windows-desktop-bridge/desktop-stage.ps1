# PROTOTYPE: run only in the recorded, disposable VM clone.
$ErrorActionPreference='Stop'
$r=[ordered]@{started_utc=[DateTime]::UtcNow.ToString('o');mode=$Mode;status='running';turns_submitted_by_stage=0}
try {
  $session=[Diagnostics.Process]::GetCurrentProcess().SessionId
  if($session -eq 0){throw 'interactive user required'}
  $principal=[Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
  if($principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){throw 'limited user required'}
  $package=@(Get-AppxPackage OpenAI.Codex)
  if($package.Count -ne 1 -or $package[0].Status -ne 'Ok' -or $package[0].Architecture -ne 'Arm64'){throw 'ambiguous or incompatible package'}
  $package=$package[0]
  $r.package=$package.PackageFullName
  $executable=Join-Path $package.InstallLocation 'app\ChatGPT.exe'
  $engine=Join-Path $env:LOCALAPPDATA 'OpenAI\Codex\bin\adbebd79223f9e27\codex.exe'
  $hash=(Get-FileHash $engine -Algorithm SHA256).Hash.ToLowerInvariant()
  if($hash -ne 'c98b873f74c4c2ae392c9b90474d9d4a17405a1d893951b4893305002bb7582a'){throw 'engine changed'}
  if((Get-FileHash (Join-Path $package.InstallLocation 'app\resources\codex.exe') -Algorithm SHA256).Hash.ToLowerInvariant() -ne $hash){throw 'registered package engine mismatch'}
  $r.engine_sha256=$hash
  $apps=@(Get-Process -Name ChatGPT -ErrorAction SilentlyContinue|Where-Object {$_.SessionId -eq $session})
  if($Mode -in @('baseline','registered','bridge')) {
    if($apps.Count -gt 0){throw 'ordinary app running; refusing launch'}
    if($Mode -eq 'bridge') {
      $owned=Join-Path $env:LOCALAPPDATA ('tofa-prototype\'+$Run)
      if(Test-Path $owned){throw 'owned directory already exists'}
      New-Item -ItemType Directory -Path $owned|Out-Null
      Copy-Item (Join-Path $Root 'bridge.exe') (Join-Path $owned 'bridge.exe')
      $r.bridge_sha256=(Get-FileHash (Join-Path $owned 'bridge.exe') -Algorithm SHA256).Hash.ToLowerInvariant()
      @{engine=$engine;sha256=$hash;evidence_dir=$owned}|ConvertTo-Json|Set-Content -Encoding UTF8 (Join-Path $owned 'bridge.json')
      # Go's JSON decoder expects UTF-8 without a BOM.
      $config=@{engine=$engine;sha256=$hash;evidence_dir=$owned}|ConvertTo-Json
      [IO.File]::WriteAllText((Join-Path $owned 'bridge.json'),$config,(New-Object Text.UTF8Encoding $false))
      $env:TOFA_PROTOTYPE_CONFIG=Join-Path $owned 'bridge.json'
      $env:CODEX_CLI_PATH=Join-Path $owned 'bridge.exe'
      $r.owned_directory_created=$true
    }
    if($Mode -eq 'registered') {
      $applications=@(Get-StartApps|Where-Object {$_.AppID -eq ($package.PackageFamilyName+'!App')})
      if($applications.Count -ne 1){throw 'ambiguous registered application'}
      $launched=Start-Process explorer.exe -ArgumentList ('shell:AppsFolder\'+$applications[0].AppID) -PassThru
      $r.activation_route='registered_AppsFolder'
    } else {
      $launched=Start-Process -FilePath $executable -PassThru
      $r.activation_route='direct_executable'
    }
    $r.activation_pid=$launched.Id
    Start-Sleep -Seconds 15
  } elseif($Mode -eq 'close') {
    # Only applies to this owned clone; request normal window closure, never kill.
    $r.close_requests=@($apps|Where-Object {$_.MainWindowHandle -ne 0}|ForEach-Object {[ordered]@{pid=$_.Id;requested=$_.CloseMainWindow()}})
    Start-Sleep -Seconds 8
  } elseif($Mode -ne 'observe') {throw 'unknown mode'}
  $r.processes=@(Get-CimInstance Win32_Process|Where-Object {$_.SessionId -eq $session -and $_.Name -in @('ChatGPT.exe','codex.exe','bridge.exe')}|ForEach-Object {
    $path=$null;if($null -ne $_.ExecutablePath){$path=$_.ExecutablePath.Replace($env:USERPROFILE,'%USERPROFILE%')}
    [ordered]@{pid=$_.ProcessId;parent_pid=$_.ParentProcessId;name=$_.Name;path=$path;path_available=($null -ne $_.ExecutablePath);command_line_available=($null -ne $_.CommandLine);app_server_argument=($_.CommandLine -match 'app-server');sandbox_service_argument=($_.CommandLine -match 'features.windows_sandbox_service=true')}
  })
  $r.vendor_service=@(Get-Service 'CodexSandboxService.OpenAI.Codex'|Select-Object Name,Status)
  $r.profile_candidates=@(@((Join-Path $env:APPDATA 'Codex'),(Join-Path $env:LOCALAPPDATA ('Packages\'+$package.PackageFamilyName+'\LocalCache\Roaming\Codex')))|ForEach-Object {
    [ordered]@{path=$_.Replace($env:USERPROFILE,'%USERPROFILE%');exists=(Test-Path $_)}
  })
  $r.bridge_runs=@(Get-ChildItem (Join-Path $env:LOCALAPPDATA 'tofa-prototype') -Directory -ErrorAction SilentlyContinue|Where-Object {$_.Name -like 'tofa77-desktop-*'}|ForEach-Object {
    [ordered]@{run=$_.Name;events=@(Get-ChildItem $_.FullName -Filter 'bridge-*.jsonl'|ForEach-Object {Get-Content $_.FullName|ForEach-Object {$_|ConvertFrom-Json}})}
  })
  $workspace='C:\Users\Public\tofa77-approval-workspace'
  $r.scratch_marker_exists=Test-Path (Join-Path $workspace 'sandbox-marker.txt')
  # Inspect only experiment-owned session bodies, identified by exact metadata cwd.
  # No unrelated conversation content, IDs, commands or account data is exported.
  $r.scratch_session_errors=@();$r.scratch_sessions_matched=0;$r.scratch_session_event_types=@()
  $sessions=Join-Path $env:USERPROFILE '.codex\sessions\2026\10\05'
  $r.session_directory_available=Test-Path $sessions
  if($r.session_directory_available) {
    foreach($file in (Get-ChildItem $sessions -Filter '*.jsonl'|Where-Object {$_.LastWriteTimeUtc -gt [DateTime]'2026-10-05T13:01:00Z'})) {
      $meta=Get-Content $file.FullName -TotalCount 1|ConvertFrom-Json
      if($meta.type -ne 'session_meta' -or $meta.payload.cwd -ne $workspace){continue}
      $r.scratch_sessions_matched++
      foreach($line in (Get-Content $file.FullName)) {
        $event=$line|ConvertFrom-Json
        if($event.type -eq 'response_item' -and $event.payload.type -in @('function_call','function_call_output','custom_tool_call','custom_tool_call_output')){$r.scratch_session_event_types+=([string]$event.payload.type)}
        if($event.type -eq 'response_item' -and $event.payload.type -in @('function_call_output','custom_tool_call_output')) {
          $output=$event.payload.output|ConvertTo-Json -Depth 8 -Compress
          if($output -match 'exec_command failed|Failed to create unified exec') {
            $r.scratch_session_errors+=([string]$output).Replace($env:USERPROFILE.Replace('\','\\'),'%USERPROFILE%')
          }
        }
      }
    }
  }
  $r.other_prototype_tasks=@(Get-ScheduledTask -TaskName 'tofa77*' -ErrorAction SilentlyContinue|Where-Object {$_.TaskName -ne $Run}|Select-Object TaskName,State)
  $r.status='completed';$r.exit_code=0
} catch {$r.status='failed';$r.exit_code=1;$r.error=$_.Exception.Message}
$r.finished_utc=[DateTime]::UtcNow.ToString('o')
$r|ConvertTo-Json -Depth 15|Set-Content -Encoding UTF8 (Join-Path $Root 'result.json')
exit $r.exit_code
