"""Ensure the reviewed offline renderer still corresponds to its actual source resources."""
import hashlib
import json
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[2]
ASSETS=ROOT/'Android_APP/module-resources/official-themes/payload/themes/renderer'

class ThemeRendererAssetsTest(unittest.TestCase):
    def test_source_fingerprints_match(self):
        data=json.loads((ASSETS/'sources.json').read_text(encoding='utf-8'))
        self.assertEqual(data['version'],1)
        self.assertEqual(data['textLineEndings'],'LF')
        self.assertGreater(len(data['sources']),20)
        for name, expected in data['sources'].items():
            with self.subTest(source=name):
                source=(ROOT/name).read_bytes()
                if Path(name).suffix.lower() in {'.vue','.css','.js','.mjs','.html','.svg','.yaml','.txt','.md'}:
                    source=source.replace(b'\r\n',b'\n')
                self.assertEqual(hashlib.sha256(source).hexdigest(),expected,'Rebuild with Android_APP/tools/build_theme_renderer.py')

    def test_all_entry_assets_and_licenses_are_bundled(self):
        html=(ASSETS/'index.html').read_text(encoding='utf-8')
        for path in re.findall(r'(?:src|href)="(\./assets/[^\"]+)"',html):
            self.assertTrue((ASSETS/path).is_file(),path)
        css='\n'.join(path.read_text(encoding='utf-8') for path in (ASSETS/'assets').glob('*.css'))
        self.assertIn('data-design-template=phase',css)
        self.assertIn('minecraft',css)
        self.assertIn('angel-city',css)
        self.assertNotIn('/assets/hero-halftone.svg',css)
        self.assertTrue((ASSETS/'licenses/fusion-pixel-OFL.txt').is_file())
        self.assertTrue((ASSETS/'licenses/vue-LICENSE.txt').is_file())
        for notice in ['README.md','OFL.txt','LICENSES/ark-pixel/OFL.txt','LICENSES/cubic-11/OFL.txt','LICENSES/galmuri/LICENSE.txt']:
            self.assertTrue((ASSETS/'licenses/fusion-pixel'/notice).is_file(),notice)

if __name__=='__main__':unittest.main()
