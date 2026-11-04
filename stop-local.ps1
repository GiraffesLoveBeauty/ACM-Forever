$ErrorActionPreference = 'Stop'
$statePath = Join-Path $PSScriptRoot 'local_demo\runtime\server.json'
if (-not (Test-Path -LiteralPath $statePath)) { Write-Output 'No recorded local service.'; exit }
$state = Get-Content -Raw -LiteralPath $statePath | ConvertFrom-Json
$process = Get-Process -Id $state.pid -ErrorAction SilentlyContinue
if (-not $process) { Write-Output 'Local service already stopped.'; exit }
$recordedStart = ([datetime]$state.start_time).ToUniversalTime()
if ($process.Path -ne $state.executable -or $process.StartTime.ToUniversalTime().Ticks -ne $recordedStart.Ticks) {
    throw 'Process identity differs; refusing to stop an unrelated process.'
}
& "$env:SystemRoot\System32\taskkill.exe" /PID $process.Id /T /F
if ($LASTEXITCODE -ne 0) { throw 'Could not stop the recorded local process tree.' }
Write-Output "Stopped isolated local service PID $($process.Id)."
