# Read-only, current-user discovery. No credential or conversation contents.
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public class OwnershipNative {
 [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
 public static extern IntPtr CreateFile(string name, uint access, uint share, IntPtr security, uint creation, uint flags, IntPtr template);
 [DllImport("kernel32.dll", SetLastError=true)]
 public static extern bool GetNamedPipeServerProcessId(IntPtr handle, out uint pid);
 [DllImport("advapi32.dll")]
 public static extern uint GetSecurityInfo(IntPtr handle, int type, uint information, out IntPtr owner, out IntPtr group, out IntPtr dacl, out IntPtr sacl, out IntPtr descriptor);
 [DllImport("advapi32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
 public static extern bool ConvertSecurityDescriptorToStringSecurityDescriptor(IntPtr descriptor, uint revision, uint information, out IntPtr text, out uint size);
 [DllImport("kernel32.dll")] public static extern IntPtr LocalFree(IntPtr value);
 [DllImport("kernel32.dll")] public static extern bool CloseHandle(IntPtr value);
 [DllImport("shell32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
 public static extern IntPtr CommandLineToArgvW(string command, out int count);
 public static string[] Arguments(string command) {
  int count; IntPtr memory=CommandLineToArgvW(command, out count);
  if(memory==IntPtr.Zero) throw new Exception("argv unavailable");
  try { string[] args=new string[count]; for(int i=0;i<count;i++) args[i]=Marshal.PtrToStringUni(Marshal.ReadIntPtr(memory,i*IntPtr.Size)); return args; }
  finally { LocalFree(memory); }
 }
}
'@
function SafePath([string]$path) {
 $item=Get-Item -LiteralPath $path -Force
 while($null -ne $item) {
  if($item.Attributes -band [IO.FileAttributes]::ReparsePoint){return $false}
  $item=$item.Parent
  if($null -eq $item -and $path -and [IO.File]::Exists($path)) { $item=(Get-Item -LiteralPath $path).Directory; $path=$null }
 }
 return $true
}
$pathsSafe=$true
$packages=@(Get-AppxPackage -Name OpenAI.Codex|ForEach-Object {
 $p=$_; $m=Get-AppxPackageManifest -Package $p.PackageFullName
 $apps=@($m.Package.Applications.Application|Where-Object {$_.Id -eq 'App'})
 if($apps.Count -ne 1){throw 'ambiguous manifest'}
 $app=Join-Path $p.InstallLocation $apps[0].Executable
 $engine=Join-Path $p.InstallLocation 'app\resources\codex.exe'
 if(!(SafePath $app) -or !(SafePath $engine)){$pathsSafe=$false}
 @{name=$p.PackageFullName;root=$p.InstallLocation;status=[string]$p.Status;architecture=[string]$p.Architecture;
   app=$app;engine_sha256=(Get-FileHash -LiteralPath $engine -Algorithm SHA256).Hash.ToLowerInvariant()}
})
$engines=@(Get-ChildItem (Join-Path $env:LOCALAPPDATA 'OpenAI\Codex\bin') -Filter codex.exe -Recurse|ForEach-Object {
 if(!(SafePath $_.FullName)){$pathsSafe=$false}
 $stream=[IO.File]::OpenRead($_.FullName)
 try {$bytes=New-Object byte[] 4096; $count=$stream.Read($bytes,0,4096)} finally {$stream.Dispose()}
 $offset=[BitConverter]::ToInt32($bytes,60)
 $arch='Unknown'
 if($offset -ge 64 -and $offset+6 -lt $count -and [BitConverter]::ToUInt32($bytes,$offset) -eq 17744) {
  $machine=[BitConverter]::ToUInt16($bytes,$offset+4)
  if($machine -eq 43620){$arch='ARM64'}elseif($machine -eq 34404){$arch='AMD64'}
 }
 @{path=$_.FullName;architecture=$arch;sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}
})
$session=[Diagnostics.Process]::GetCurrentProcess().SessionId
$processes=@(Get-CimInstance Win32_Process|Where-Object {$_.SessionId -eq $session -and $_.Name -eq 'ChatGPT.exe'})
$incumbents=@($processes|Where-Object {$_.CommandLine -notmatch '--type='}|ForEach-Object {
 @{pid=[int]$_.ProcessId;path=$_.ExecutablePath;created=[string]$_.CreationDate.ToUniversalTime().Ticks}
})
$profiles=@($processes|ForEach-Object {
 if($_.CommandLine) {
  [OwnershipNative]::Arguments($_.CommandLine)|Where-Object {$_.StartsWith('--user-data-dir=')}|ForEach-Object {$_.Substring(16)}
 }
}|Sort-Object -Unique)
$pipe=@{name='codex-ipc';open_error=0;server_pid=0;sddl=$null;security_error=0}
$handle=[OwnershipNative]::CreateFile('\\.\pipe\codex-ipc',131072,3,[IntPtr]::Zero,3,0,[IntPtr]::Zero)
if($handle -eq [IntPtr](-1)) {$pipe.open_error=[Runtime.InteropServices.Marshal]::GetLastWin32Error()}
else {
 try {
  [uint32]$server=0
  if([OwnershipNative]::GetNamedPipeServerProcessId($handle,[ref]$server)){$pipe.server_pid=[int]$server}
  $owner=$group=$dacl=$sacl=$descriptor=[IntPtr]::Zero
  $pipe.security_error=[OwnershipNative]::GetSecurityInfo($handle,6,5,[ref]$owner,[ref]$group,[ref]$dacl,[ref]$sacl,[ref]$descriptor)
  if($pipe.security_error -eq 0) {
   try {
    $text=[IntPtr]::Zero;[uint32]$size=0
    if([OwnershipNative]::ConvertSecurityDescriptorToStringSecurityDescriptor($descriptor,1,5,[ref]$text,[ref]$size)) {
     try {$pipe.sddl=[Runtime.InteropServices.Marshal]::PtrToStringUni($text)} finally {[void][OwnershipNative]::LocalFree($text)}
    }
   } finally {[void][OwnershipNative]::LocalFree($descriptor)}
  }
 } finally {[void][OwnershipNative]::CloseHandle($handle)}
}
$service=Get-CimInstance Win32_Service -Filter "Name='CodexSandboxService.OpenAI.Codex'"
$pathProbe=$null
if('__PROBE_PATH__'){$pathProbe=SafePath '__PROBE_PATH__'}
@{path_probe=$pathProbe;packages=$packages;engines=$engines;paths_safe=$pathsSafe;
  process_inventory_complete=(@($processes|Where-Object {!$_.ExecutablePath -or !$_.CommandLine}).Count -eq 0);
  incumbents=$incumbents;profiles=$profiles;pipe=$pipe;sid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value;
  service=@{pid=[int]$service.ProcessId;state=$service.State};
  standalone=@(Get-Command codex -All -ErrorAction SilentlyContinue|ForEach-Object {$_.Source})
}|ConvertTo-Json -Depth 8 -Compress
