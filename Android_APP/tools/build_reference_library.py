"""Local reference catalogue only. Never writes to Android sources or downloads data."""
import argparse
import hashlib
import html
import io
import json
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from PIL import Image
from extract_skland_icons import decode, ANDROID


def svg(data):
    root = ET.fromstring(data)
    attr = lambda node, key, default=None: node.get('{' + ANDROID + '}' + key, default)
    w, h = float(attr(root, 'viewportWidth')), float(attr(root, 'viewportHeight'))
    if max(w, h) > 256:
        raise ValueError('Not a small icon')
    def node(item):
        if item.tag == 'group':
            sx, sy = attr(item, 'scaleX', '1'), attr(item, 'scaleY', '1')
            px, py = attr(item, 'pivotX', '0'), attr(item, 'pivotY', '0')
            tx, ty = attr(item, 'translateX', '0'), attr(item, 'translateY', '0')
            transform = f'translate({tx} {ty}) translate({px} {py}) rotate({attr(item,"rotation","0")}) scale({sx} {sy}) translate({-float(px)} {-float(py)})'
            return '<g transform="' + transform + '">' + ''.join(node(child) for child in item) + '</g>'
        if item.tag != 'path':
            raise ValueError('Complex vector; original retained only')
        attrs = {'d': attr(item, 'pathData'), 'fill': attr(item, 'fillColor', 'none'),
                 'stroke': attr(item, 'strokeColor', 'none'), 'stroke-width': attr(item, 'strokeWidth', '0'),
                 'stroke-linecap': attr(item, 'strokeLineCap', 'butt'), 'stroke-linejoin': attr(item, 'strokeLineJoin', 'miter'),
                 'fill-opacity': attr(item, 'fillAlpha', '1'), 'stroke-opacity': attr(item, 'strokeAlpha', '1'),
                 'fill-rule': 'evenodd' if attr(item, 'fillType') == 'evenOdd' else 'nonzero'}
        for key in ('fill', 'stroke'):
            value = attrs[key]
            if value.startswith('#') and len(value) == 9:
                attrs[key + '-opacity'] = str(int(value[1:3], 16) / 255 * float(attrs[key + '-opacity']))
                attrs[key] = '#' + value[3:]
        return '<path ' + ' '.join(key + '="' + html.escape(str(value), quote=True) + '"' for key, value in attrs.items()) + '/>'
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}">' + ''.join(node(item) for item in root) + '</svg>'


def category(name):
    for title, pattern in [('导航', 'nav|tab_|forum|home|rank'), ('互动', 'like|praise|comment|collection|share|follow|chat'),
                           ('账号', 'avatar|user|account|login|password'), ('编辑工具', 'edit|post|draft|article|copy|search|filter'),
                           ('状态', 'empty|loading|notification|error|success|warn')]:
        if re.search(pattern, name):
            return title
    return '通用'


def main():
    p = argparse.ArgumentParser()
    for key in ('apk', 'table', 'aapt2', 'output'):
        p.add_argument('--' + key, type=Path, required=True)
    args = p.parse_args()
    out = args.output.resolve()
    if 'src' in out.parts or 'res' in out.parts:
        raise ValueError('Reference catalogue must stay outside application sources')
    for directory in ('original', 'preview'):
        (out / directory).mkdir(parents=True, exist_ok=True)
    table = args.table.read_text(encoding='utf-8-sig')
    items, skipped = [], []
    with zipfile.ZipFile(args.apk) as archive:
        for match in re.finditer(r'    resource (0x[0-9a-f]+) drawable/([^\n]+)\n(.*?)(?=    resource|\Z)', table, re.S):
            resource, name, variants = match.groups()
            if not re.search(r'icon|ic_|nav_|entry_|tab_|logo|avatar|empty|loading|notification', name):
                continue
            entry = re.search(r'\(file\) (\S+)', variants)
            if not entry:
                continue
            entry = entry[1]
            safe = re.sub(r'[^A-Za-z0-9_-]', '_', name)
            raw = archive.read(entry)
            extension = Path(entry).suffix.lower()
            if extension not in ('.png', '.webp', '.jpg', '.xml'):
                continue
            try:
                if extension == '.xml':
                    tree = subprocess.run([str(args.aapt2), 'dump', 'xmltree', str(args.apk), '--file', entry], check=True, capture_output=True, encoding='utf-8').stdout
                    converted = decode(tree, table)
                    preview = svg(converted).encode()
                    suffix = '.svg'
                else:
                    with Image.open(io.BytesIO(raw)) as image:
                        if max(image.size) > 512:
                            continue
                        buffer = io.BytesIO(); image.convert('RGBA').save(buffer, 'PNG'); preview = buffer.getvalue()
                    suffix = '.png'
                original = 'original/' + safe + ('.axml' if extension == '.xml' else extension)
                preview_path = 'preview/' + safe + suffix
                (out / original).write_bytes(raw); (out / preview_path).write_bytes(preview)
                items.append(dict(name=name, category=category(name), resource=resource, apk_entry=entry,
                                  original=original, preview=preview_path, sha256=hashlib.sha256(raw).hexdigest()))
            except Exception as error:
                skipped.append(dict(name=name, apk_entry=entry, reason=str(error)))
    manifest = dict(source_app='com.hypergryph.skland', source_version='2.3.0',
                    apk_sha256=hashlib.sha256(args.apk.read_bytes()).hexdigest(),
                    usage='本机排版与风格参考；不得打包到 ACMforever。原创图标在 AppIcons.java 中绘制。预览为近似转换，原始字节保留用于比对。',
                    icons=items, skipped=skipped)
    (out / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    (out / 'catalog.js').write_text('const CATALOG=' + json.dumps(items, ensure_ascii=False) + ';', encoding='utf-8')
    (out / 'index.html').write_text('''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>森空岛 · 本地参考素材库</title>
<style>body{background:#f4f5f7;color:#1e211c;font:15px system-ui;max-width:1200px;margin:auto;padding:30px}h1{font-size:25px}input,select,button{padding:12px;border:1px solid #dde3d3;border-radius:10px;background:white}#grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:12px;margin:20px 0}article{background:white;border-radius:16px;padding:16px;overflow-wrap:anywhere}img{width:64px;height:64px;object-fit:contain;display:block;margin:12px auto;background:#f4f5ed}small{color:#66705d}footer{display:flex;gap:15px;align-items:center}p{line-height:1.6}</style>
<h1>森空岛 · 本地参考素材库</h1><p>仅用于本机学习排版与美术风格。参考素材不打入 ACMforever 安装包；App 中使用原创猫娘图标。矢量预览为近似转换，完整来源与校验见 manifest.json。</p>
<input id="q" placeholder="搜索资源名称"><select id="category"><option>全部</option></select><span id="count"></span><div id="grid"></div><footer><button id="prev">上一页</button><span id="page"></span><button id="next">下一页</button></footer><script src="catalog.js"></script>
<script>let current=1;const q=document.querySelector('#q'),cat=document.querySelector('#category');for(const c of new Set(CATALOG.map(x=>x.category))){const o=document.createElement('option');o.textContent=c;cat.append(o)}function render(){const list=CATALOG.filter(x=>x.name.includes(q.value.toLowerCase())&&(cat.value==='全部'||cat.value===x.category));let pages=Math.max(1,Math.ceil(list.length/60));current=Math.min(current,pages);document.querySelector('#grid').replaceChildren();for(const item of list.slice((current-1)*60,current*60)){let card=document.createElement('article'),img=document.createElement('img'),name=document.createElement('div'),info=document.createElement('small');img.src=item.preview;img.loading='lazy';name.textContent=item.name;info.textContent=item.category;card.append(img,name,info);document.querySelector('#grid').append(card)}document.querySelector('#count').textContent=' '+list.length+' 个';document.querySelector('#page').textContent=current+' / '+pages;document.querySelector('#prev').disabled=current===1;document.querySelector('#next').disabled=current===pages}q.oninput=cat.onchange=()=>{current=1;render()};document.querySelector('#prev').onclick=()=>{current--;render()};document.querySelector('#next').onclick=()=>{current++;render()};render()</script></html>''', encoding='utf-8')
    print(json.dumps(dict(icons=len(items), skipped=len(skipped), output=str(out)), ensure_ascii=False))


if __name__ == '__main__':
    main()
