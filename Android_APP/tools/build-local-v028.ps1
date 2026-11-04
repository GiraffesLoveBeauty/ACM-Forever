$ErrorActionPreference = 'Stop'
$buildRoot = Join-Path $env:TEMP 'acmforever-build-v0.2.0'
$repoApp = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\app'))
$buildCopy = Join-Path $buildRoot 'local-v028'
$env:JAVA_HOME = Join-Path $buildRoot 'jdk17-verified-v021\jdk-17.0.20.1+1'
$env:ANDROID_HOME = Join-Path $buildRoot 'sdk'
$env:ANDROID_USER_HOME = Join-Path $buildRoot 'android-home'
$env:GRADLE_USER_HOME = Join-Path $buildRoot 'gradle-home-v021'
$env:PATH = (Join-Path $env:JAVA_HOME 'bin') + ';' + $env:PATH
New-Item -ItemType Directory -Path (Join-Path $buildCopy 'app') -Force | Out-Null
foreach ($name in @('build.gradle','settings.gradle','gradle.properties')) { Copy-Item -LiteralPath (Join-Path $repoApp $name) -Destination $buildCopy -Force }
Copy-Item -LiteralPath (Join-Path $repoApp 'app\build.gradle') -Destination (Join-Path $buildCopy 'app\build.gradle') -Force
$source = Join-Path $repoApp 'app\src'
$target = Join-Path $buildCopy 'app\src'
foreach ($file in Get-ChildItem -LiteralPath $source -Recurse -File) {
    $relative = [System.IO.Path]::GetRelativePath($source,$file.FullName)
    $destination = Join-Path $target $relative
    New-Item -ItemType Directory -Path ([System.IO.Path]::GetDirectoryName($destination)) -Force | Out-Null
    Copy-Item -LiteralPath $file.FullName -Destination $destination -Force
}
$signing = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\dist\signing\debug.keystore'))
Push-Location $buildCopy
try {
    & (Join-Path $buildRoot 'gradle\gradle-8.9\bin\gradle.bat') --offline --no-daemon "-PlocalDebugKeystore=$signing" :app:assembleDebug :app:lintDebug :app:testDebugUnitTest :app:assembleDebugAndroidTest
    if ($LASTEXITCODE -ne 0) { throw "Gradle failed: $LASTEXITCODE" }
} finally { Pop-Location }
