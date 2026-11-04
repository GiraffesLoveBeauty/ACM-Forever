"""Package the local verified v0.2.9 build. No publishing or network access."""
from pathlib import Path
import hashlib
import io
import json
import os
import re
import shutil
import xml.etree.ElementTree as ET
import zipfile
from PIL import Image

root=Path(__file__).resolve().parents[1]
build=Path(os.environ['TEMP'])/'acmforever-build-v0.2.0/local-v029'
qa=root/'app/app/build/qa-v029'
modes=('localthemes','spacefeatures','settings','appearance','community','login')
for mode in modes:
    assert 'PASS:' in (qa/f'{mode}.txt').read_text(encoding='utf-8-sig'),f'UI check incomplete: {mode}'
for source in (root/'app/app/src').rglob('*'):
    if source.is_file():
        assert source.read_bytes()==(build/'app/src'/source.relative_to(root/'app/app/src')).read_bytes(),f'Stale build: {source}'
assert (root/'app/app/build.gradle').read_bytes()==(build/'app/build.gradle').read_bytes()
metadata=json.loads((build/'app/build/outputs/apk/debug/output-metadata.json').read_text(encoding='utf-8'))['elements'][0]
assert metadata['versionCode']==23 and metadata['versionName']=='0.2.9'
lint=build/'app/build/intermediates/lint_intermediate_text_report/debug/lintReportDebug/lint-results-debug.txt'
lint_text=lint.read_text(encoding='utf-8')
assert '0 errors,' in lint_text
warnings=int(re.search(r'0 errors, (\d+) warnings',lint_text)[1])
totals=dict(tests=0,failures=0,errors=0)
for path in (build/'app/build/test-results/testDebugUnitTest').glob('*.xml'):
    suite=ET.parse(path).getroot()
    for key in totals:totals[key]+=int(suite.attrib[key])
    shutil.copy2(path,qa/path.name)
assert totals['tests']>=39 and totals['failures']==totals['errors']==0
certificate='88c9f163cbf379aeca7bc110f66c542a838d0d8e3970f24fd96582bec8e93fe4'
signature=(qa/'signing-v029.txt').read_text(encoding='utf-8-sig')
assert f'Signer #1 certificate SHA-256 digest: {certificate}' in signature
assert 'Verified using v2 scheme (APK Signature Scheme v2): true' in signature
apk=build/'app/build/outputs/apk/debug/app-debug.apk'
with zipfile.ZipFile(apk) as archive,zipfile.ZipFile(root/'dist/acmforever-0.2.6-debug.apk') as legacy,zipfile.ZipFile(root/'dist/acmforever-0.2.7-debug.apk') as previous:
    assert archive.testzip() is None
    for name in archive.namelist():
        assert not name.startswith('assets/admin/')
        if name.endswith('.dex'):
            data=archive.read(name)
            for marker in (b'.test.invalid',b'UiSmoke',b'Synthetic-Test!'):
                assert marker not in data,f'Test fixture in main APK: {marker!r}'
        if name.startswith('assets/character/'):
            assert archive.read(name)==previous.read(name),f'Colour layers changed: {name}'
    for name in ('catgirl_mask.png','launcher_silhouette.png','ic_cat_notification.png'):
        new_name=next(n for n in archive.namelist() if n.endswith('/'+name))
        old_name=next(n for n in legacy.namelist() if n.endswith('/'+name))
        a=Image.open(io.BytesIO(archive.read(new_name))).convert('RGBA')
        b=Image.open(io.BytesIO(legacy.read(old_name))).convert('RGBA')
        assert a.size==b.size and a.tobytes()==b.tobytes(),f'Legacy silhouette mismatch: {name}'
dist=root/'dist';destination=dist/'acmforever-0.2.9-debug.apk'
shutil.copy2(apk,destination);digest=hashlib.sha256(destination.read_bytes()).hexdigest()
assert digest==hashlib.sha256(apk.read_bytes()).hexdigest()
destination.with_suffix('.apk.sha256').write_text(f'{digest}  {destination.name}\n',encoding='utf-8')
shutil.copy2(lint,dist/'lint-v0.2.9.txt')
report=dict(version='0.2.9',versionCode=23,bytes=destination.stat().st_size,sha256=digest,certificate_sha256=certificate,
            unit_tests=totals,lint_errors=0,lint_warnings=warnings,ui_checks=list(modes),legacy_silhouette='0.2.6',
            colour_layers_unchanged_from='0.2.7',test_fixtures_in_main_apk=False,source_copy_identical=True,
            publication='local only',production_update_server_tested=False)
(qa/'package-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
