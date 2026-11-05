"""Read a Git revision's real Web theme catalogue without checking out Web files."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument('--ref', default='origin/main')
args = parser.parse_args()
root = Path(__file__).resolve().parents[2]
paths = ['feat/web/src/lib/theme-colors.js', 'feat/web/src/lib/design-template.js']
sources = [subprocess.check_output(['git', 'show', f'{args.ref}:{p}'], cwd=root) for p in paths]
uri = lambda value: 'data:text/javascript;base64,' + base64.b64encode(value).decode('ascii')
design = sources[1].decode('utf-8').replace("'./theme-colors.js'", json.dumps(uri(sources[0])))
program = f"const m=await import({json.dumps(uri(design.encode('utf-8')))}); console.log(JSON.stringify({{categories:m.TEMPLATE_CATEGORIES,presets:m.DESIGN_TEMPLATES.map(t=>({{...t,design_template:t.id,theme:m.templateTheme(t.id)}}))}}));"
catalog = json.loads(subprocess.check_output(['node', '--input-type=module'], input=program.encode('utf-8'), cwd=root))
catalog.update(version=1, revision=subprocess.check_output(['git', 'rev-parse', args.ref], cwd=root).decode().strip(),
               sources={path: hashlib.sha256(data).hexdigest() for path, data in zip(paths, sources)})
target = root / 'Android_APP/app/app/src/main/assets/themes/web-designs.json'
target.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding='utf-8')
print(f'Converted {len(catalog["presets"])} real Web templates at {catalog["revision"][:7]}')
