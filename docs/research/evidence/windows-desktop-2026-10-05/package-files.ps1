$ErrorActionPreference='Stop'
$r=[ordered]@{started_utc=[DateTime]::UtcNow.ToString('o');status='running'}
try {
$root='C:\Program Files\WindowsApps\OpenAI.Codex_26.930.2377.0_arm64__2p2nqsd0c76g0'
$r.files=@('app\ChatGPT.exe','app\resources\codex.exe','app\resources\app.asar','app\resources\codex-windows-sandbox-service.exe' | ForEach-Object {
 $path=Join-Path $root $_; $item=Get-Item $path; $machine=$null
 if ($item.Extension -eq '.exe') {$f=[IO.File]::OpenRead($path);try{$br=[IO.BinaryReader]::new($f);$f.Position=60;$off=$br.ReadInt32();$f.Position=$off+4;$machine='0x{0:X4}' -f $br.ReadUInt16()}finally{$f.Dispose()}}
 [ordered]@{path=$_;bytes=$item.Length;pe_machine=$machine;file_version=$item.VersionInfo.FileVersion;sha256=(Get-FileHash $path -Algorithm SHA256).Hash}
})
$r.status='completed';$r.exit_code=0
}catch{$r.status='failed';$r.exit_code=1;$r.error=$_.Exception.Message}
$r.finished_utc=[DateTime]::UtcNow.ToString('o');$r|ConvertTo-Json -Depth 8|Set-Content -Encoding UTF8 'C:\Windows\Temp\tofa76-narrow.json';exit $r.exit_code
