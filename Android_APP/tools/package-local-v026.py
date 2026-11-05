"""Package the verified offline build; never publish, sign anew, or change sources."""
from pathlib import Path
import hashlib
import io
import json
import os
import shutil
import xml.etree.ElementTree as ET
import zipfile
from PIL import Image

root = Path(__file__).resolve().parents[1]
build = Path(os.environ['TEMP']) / 'acmforever-build-v0.2.0/local-v026'
for source in (root / 'app/app/src').rglob('*'):
    if source.is_file():
        built = build / 'app/src' / source.relative_to(root / 'app/app/src')
        assert built.read_bytes() == source.read_bytes(), f'Build copy is stale: {source}'
assert (build / 'app/build.gradle').read_bytes() == (root / 'app/app/build.gradle').read_bytes()
apk = build / 'app/build/outputs/apk/debug/app-debug.apk'
lint = build / 'app/build/intermediates/lint_intermediate_text_report/debug/lintReportDebug/lint-results-debug.txt'
assert '0 errors,' in lint.read_text(encoding='utf-8')
totals = dict(tests=0, failures=0, errors=0)
for report in (build / 'app/build/test-results/testDebugUnitTest').glob('*.xml'):
    suite = ET.parse(report).getroot()
    for key in totals:
        totals[key] += int(suite.attrib[key])
assert totals['tests'] > 0 and totals['failures'] == totals['errors'] == 0
with zipfile.ZipFile(apk) as archive:
    assert archive.testzip() is None
    assert not any(name.startswith('assets/admin/') for name in archive.namelist())
    for name in archive.namelist():
        if name.endswith('.dex'):
            code = archive.read(name)
            for fixture in (b'WebFeaturesUiSmoke', b'AppearanceUiSmoke', b'features.test.invalid', b'appearance.test.invalid', b'Synthetic-Test!'):
                assert fixture not in code, f'Test fixture in main APK: {fixture!r}'
    themes = json.loads(archive.read('assets/themes/web-designs.json'))
    assert len(themes['presets']) == 4
    assert len(json.loads(archive.read('assets/themes/web-presets.json'))['presets']) == 5
    icon_name = next(name for name in archive.namelist() if name.endswith('/launcher_silhouette.png'))
    icon = Image.open(io.BytesIO(archive.read(icon_name))).convert('RGBA')
    assert all((r, g, b) == (0, 0, 0) for r, g, b, a in icon.getdata() if a)
dist = root / 'dist'
dist.mkdir(exist_ok=True)
destination = dist / 'acmforever-0.2.6-debug.apk'
shutil.copy2(apk, destination)
digest = hashlib.sha256(destination.read_bytes()).hexdigest()
assert digest == hashlib.sha256(apk.read_bytes()).hexdigest()
destination.with_suffix('.apk.sha256').write_text(f'{digest}  {destination.name}\n', encoding='utf-8')
shutil.copy2(lint, dist / 'lint-v0.2.6.txt')
qa = root / 'app/app/build/qa-v026'
qa.mkdir(parents=True, exist_ok=True)
for report in (build / 'app/build/test-results/testDebugUnitTest').glob('*.xml'):
    shutil.copy2(report, qa / report.name)
(qa / 'package-verification.json').write_text(json.dumps({
    'version': '0.2.6', 'versionCode': 20, 'apk_sha256': digest,
    'bytes': destination.stat().st_size, 'unit_tests': totals,
    'source_copy_identical': True, 'test_fixtures_in_main_apk': False,
    'web_designs': 4, 'web_palettes': 5, 'launcher_foreground': 'black',
    'publication': 'local only',
}, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'apk': str(destination), 'sha256': digest, 'bytes': destination.stat().st_size, 'tests': totals['tests']}, ensure_ascii=False))
