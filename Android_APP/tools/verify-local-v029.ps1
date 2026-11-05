param([string[]]$Modes=@('localthemes','spacefeatures','settings','appearance','community','login'))
$ErrorActionPreference='Stop'
$adb=Join-Path $env:TEMP 'acmforever-build-v0.2.0\sdk\platform-tools\adb.exe'
$qa=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\app\app\build\qa-v029'))
New-Item -ItemType Directory -Path $qa -Force | Out-Null
& $adb -s emulator-5554 shell wm size 900x1920
try {
    foreach($mode in $Modes){
        $result=& $adb -s emulator-5554 shell am instrument -w -e mode $mode com.giraffeslovebeauty.acmforever.test/com.giraffeslovebeauty.acmforever.ReaderSmoke
        $result | Set-Content -LiteralPath (Join-Path $qa "$mode.txt") -Encoding utf8
        Write-Output "$mode verification:"
        $result
        if(($result -join "`n") -notmatch 'PASS:'){throw "$mode verification failed"}
    }
} finally { & $adb -s emulator-5554 shell wm size reset }
