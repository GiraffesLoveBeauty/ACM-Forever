$ErrorActionPreference='Stop'
$buildRoot=Join-Path $env:TEMP 'acmforever-build-v0.2.0'
$buildCopy=Join-Path $buildRoot 'local-v0211'
$repoRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$qa=Join-Path $repoRoot 'app\app\build\qa-v0211'
$dist=Join-Path $repoRoot 'dist'
$env:JAVA_HOME=Join-Path $buildRoot 'jdk17-verified-v021\jdk-17.0.20.1+1'
$modes=@('polish','navigation','localthemes','web','spacefeatures','settings','appearance','community','login')
foreach($mode in $modes){$result=Get-Content -LiteralPath (Join-Path $qa "$mode.txt") -Raw;if($result -notmatch 'PASS:' -or $result -match 'FAIL:'){throw "Unverified UI mode: $mode"}}
$source=Join-Path $repoRoot 'app\app\src'
foreach($file in Get-ChildItem -LiteralPath $source -Recurse -File){$relative=[IO.Path]::GetRelativePath($source,$file.FullName);$copy=Join-Path $buildCopy "app\src\$relative";if((Get-FileHash -LiteralPath $file.FullName).Hash -ne (Get-FileHash -LiteralPath $copy).Hash){throw "Stale build: $relative"}}
if((Get-FileHash -LiteralPath (Join-Path $repoRoot 'app\app\build.gradle')).Hash -ne (Get-FileHash -LiteralPath (Join-Path $buildCopy 'app\build.gradle')).Hash){throw 'Stale version configuration'}
$metadata=Get-Content -LiteralPath (Join-Path $buildCopy 'app\build\outputs\apk\debug\output-metadata.json') -Raw | ConvertFrom-Json
if($metadata.elements[0].versionCode -ne 25 -or $metadata.elements[0].versionName -ne '0.2.11'){throw 'Incorrect version'}
$tests=0;$failures=0;$errors=0
foreach($file in Get-ChildItem -LiteralPath (Join-Path $buildCopy 'app\build\test-results\testDebugUnitTest') -Filter 'TEST-*.xml'){
    [xml]$suite=Get-Content -LiteralPath $file.FullName -Raw
    $tests += [int]$suite.testsuite.tests;$failures += [int]$suite.testsuite.failures;$errors += [int]$suite.testsuite.errors
    Copy-Item -LiteralPath $file.FullName -Destination $qa -Force
}
if($tests -lt 44 -or $failures -ne 0 -or $errors -ne 0){throw 'Unit tests did not pass'}
$lint=Join-Path $buildCopy 'app\build\intermediates\lint_intermediate_text_report\debug\lintReportDebug\lint-results-debug.txt'
$lintText=Get-Content -LiteralPath $lint -Raw
if($lintText -notmatch '0 errors, (\d+) warnings'){throw 'Lint errors or missing result'}
$warnings=[int]$Matches[1]
$apk=Join-Path $buildCopy 'app\build\outputs\apk\debug\app-debug.apk'
$signature=& (Join-Path $buildRoot 'sdk\build-tools\35.0.0\apksigner.bat') verify --verbose --print-certs $apk
if($LASTEXITCODE -ne 0){throw 'APK signature verification failed'}
$certificate='88c9f163cbf379aeca7bc110f66c542a838d0d8e3970f24fd96582bec8e93fe4'
if(($signature -join "`n") -notmatch "Signer #1 certificate SHA-256 digest: $certificate"){throw 'Signing certificate differs from previous APK'}
$signature | Set-Content -LiteralPath (Join-Path $qa 'signing-v0211.txt') -Encoding utf8
$destination=Join-Path $dist 'acmforever-0.2.11-debug.apk'
Copy-Item -LiteralPath $apk -Destination $destination -Force
$digest=(Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant()
"$digest  acmforever-0.2.11-debug.apk" | Set-Content -LiteralPath "$destination.sha256" -Encoding utf8
Copy-Item -LiteralPath $lint -Destination (Join-Path $dist 'lint-v0.2.11.txt') -Force
$report=[ordered]@{version='0.2.11';versionCode=25;bytes=(Get-Item -LiteralPath $destination).Length;sha256=$digest;certificate_sha256=$certificate;unit_tests=@{tests=$tests;failures=$failures;errors=$errors};lint_errors=0;lint_warnings=$warnings;ui_checks=$modes;source_copy_identical=$true;publication='local only';production_update_server_tested=$false}
$report | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $qa 'package-verification.json') -Encoding utf8
$report | ConvertTo-Json -Depth 5
