param([switch]$Background, [int]$Port = 18088)
$ErrorActionPreference = 'Stop'
$demoRoot = $PSScriptRoot
$pythonPath = Join-Path $demoRoot '.venv\Scripts\python.exe'
$runtimePath = Join-Path $demoRoot 'local_demo\runtime'
New-Item -ItemType Directory -Force -Path $runtimePath | Out-Null
if ($Port -lt 1024 -or $Port -gt 65535) { throw 'Invalid local port.' }
$listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $Port)
try { $listener.Start() } finally { $listener.Stop() }
if ($Background) {
    $process = Start-Process -FilePath $pythonPath -ArgumentList '-B','-X','utf8','local_demo/server.py','--port',"$Port" -WorkingDirectory $demoRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runtimePath 'server.stdout.log') -RedirectStandardError (Join-Path $runtimePath 'server.stderr.log') -PassThru
    @{pid=$process.Id; start_time=$process.StartTime.ToUniversalTime().ToString('o'); executable=$process.Path; port=$Port} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runtimePath 'server.json') -Encoding utf8
    Write-Output "Local forum PID $($process.Id): http://127.0.0.1:$Port/index.html"
} else {
    Push-Location $demoRoot
    try { & $pythonPath -B -X utf8 local_demo/server.py --port $Port } finally { Pop-Location }
}
