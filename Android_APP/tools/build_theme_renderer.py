"""Compile the repository's original official theme components for the offline Android layer."""
import hashlib
import json
from pathlib import Path
import subprocess
import shutil

root = Path(__file__).resolve().parents[2]
vite = root / 'feat/web/node_modules/vite/bin/vite.js'
if not vite.is_file():
    raise SystemExit('First run: pnpm --dir feat/web install --frozen-lockfile')
subprocess.run(['node', str(vite), 'build', '--config', 'Android_APP/theme-renderer/vite.config.mjs'], cwd=root, check=True)
output = root / 'Android_APP/app/app/src/main/assets/themes/renderer'
sources = list((root / 'Android_APP/theme-renderer').glob('*'))
sources += list((root / 'feat/web/src/components').glob('*Art.vue'))
sources += [root / f'feat/web/src/components/Minecraft{x}.vue' for x in ('Podium', 'Journey')]
sources += list((root / 'feat/web/src').glob('*theme.css'))
sources += [root / 'feat/web/src/lib/theme-colors.js', root / 'feat/web/src/lib/design-template.js', root / 'feat/web/src/style.css', root / 'feat/web/pnpm-lock.yaml']
sources += [root / ('feat/api/acm_api/public/assets/' + name) for name in ('app.css','forum-graph.css','community-art.css','endfield-theme.css','hero-halftone.svg')]
sources += list((root / 'feat/web/src/assets/minecraft').glob('*'))
sources += list((root / 'feat/web/src/assets/fonts/fusion-pixel').rglob('*'))
def fingerprint(path):
    data = path.read_bytes()
    if path.suffix.lower() in {'.vue', '.css', '.js', '.mjs', '.html', '.svg', '.yaml', '.txt', '.md'}:
        data = data.replace(b'\r\n', b'\n')
    return hashlib.sha256(data).hexdigest()

hashes = {p.relative_to(root).as_posix():fingerprint(p) for p in sorted(set(sources)) if p.is_file()}
(output / 'sources.json').write_text(json.dumps({'version':1,'textLineEndings':'LF','sources':hashes},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
licenses = output / 'licenses'
licenses.mkdir(exist_ok=True)
for name, source in [('fusion-pixel-OFL.txt',root / 'feat/web/src/assets/fonts/fusion-pixel/OFL.txt'),('vue-LICENSE.txt',root / 'feat/web/node_modules/vue/LICENSE')]:
    (licenses / name).write_bytes(source.read_bytes())
print(f'Bundled {len(hashes)} source fingerprints and font/Vue licenses; no artwork was redrawn.')

shutil.copytree(root / 'feat/web/src/assets/fonts/fusion-pixel', licenses / 'fusion-pixel', ignore=shutil.ignore_patterns('*.woff2'), dirs_exist_ok=True)
