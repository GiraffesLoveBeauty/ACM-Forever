"""Validate the supplied layered art, then prepare local Android assets without network calls."""
from pathlib import Path
import hashlib, json, shutil
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT.parent.parent / 'ACMforever_猫娘素材包_v2'
RES = ROOT / 'app/app/src/main/res/drawable-nodpi'
OUT = ROOT / 'app/app/src/main/assets/character'
QA = ROOT / 'app/app/build/qa-v027'
DOC = ROOT / 'docs/artwork-v2'
for folder in (OUT, QA, DOC): folder.mkdir(parents=True, exist_ok=True)
manifest = json.loads((PACK/'manifest.json').read_text(encoding='utf-8-sig'))
report = {}
catalog = {'version': 2, 'assets': {}}

for name, size, resource, mask_resource in [('avatar',512,'avatar_catgirl','avatar_color_mask'),('loading',640,'catgirl_loading','loading_color_mask')]:
    item = manifest['assets'][name]
    reference = Image.open(PACK/item['reference']).convert('RGBA')
    assert reference.size == (item['width'], item['height'])
    assert reference.getextrema()[3][0] == 0 and reference.getextrema()[3][1] == 255
    rebuilt = Image.new('RGBA', reference.size)
    layers=[]
    runtime_reference=Image.new('RGBA',(size,size))
    for layer in item['layers']:
        original = Image.open(PACK/layer['file']).convert('RGBA')
        assert original.size == reference.size
        rebuilt = Image.alpha_composite(rebuilt, original)
        runtime_reference=Image.alpha_composite(runtime_reference,original.resize((size,size),Image.Resampling.LANCZOS))
        selected = Image.open(PACK/layer.get('neutral',layer['file'])).convert('RGBA')
        assert selected.size == original.size
        assert np.array_equal(np.asarray(selected.getchannel('A')), np.asarray(original.getchannel('A')))
        destination = OUT/name/Path(layer['file']).name
        destination.parent.mkdir(parents=True, exist_ok=True)
        selected.resize((size,size), Image.Resampling.LANCZOS).save(destination,optimize=True)
        layers.append(dict(file=f'{name}/{destination.name}',group=layer['group'],name=layer['name']))
    assert np.array_equal(np.asarray(reference),np.asarray(rebuilt)),f'{name}: original layers do not reconstruct reference'
    # Original reference remains available for comparison. Runtime tinting uses the actual layers.
    runtime_reference.save(RES/(resource+'.png'),optimize=True)
    # A compatibility diagnostic mask: mark every visible recolourable contribution,
    # including anti-aliased boundaries; black means fully protected fixed content.
    coverage=np.ones((size,size),np.float32);weights=np.zeros((size,size,3),np.float32)
    for layer in reversed(layers):
        alpha=np.asarray(Image.open(OUT/layer['file']).getchannel('A'),dtype=np.float32)/255
        group=layer['group']
        if group!='fixed': weights[:,:,{'hair_eyes':0,'clothes':1,'decor':2}[group]]+=alpha*coverage
        coverage*=1-alpha
    maximum=weights.max(axis=2);indices=weights.argmax(axis=2)
    mask=np.zeros((size,size,3),np.uint8)
    for index in range(3): mask[:,:,index]=np.where((indices==index)&(maximum>0),255,0)
    Image.fromarray(mask).save(RES/(mask_resource+'.png'),optimize=True)
    catalog['assets'][name]={'width':size,'height':size,'layers':layers}
    report[name]={'original_size':reference.size,'runtime_size':size,'layers':len(layers),'reconstruction_max_difference':0,'sha256':hashlib.sha256((PACK/item['reference']).read_bytes()).hexdigest()}

# The user kept the v2 colour layers but requested the pre-v2 silhouette.
# Preserve the exact v0.2.6 exports so importing colour art cannot change it again.
legacy=ROOT/'docs/artwork-v2/legacy-silhouette'
silhouette_report={}
for filename in ('catgirl_mask.png','launcher_silhouette.png','ic_cat_notification.png'):
    source=legacy/filename
    assert source.is_file(),f'Missing preserved v0.2.6 silhouette: {source}'
    shutil.copy2(source,RES/filename)
    silhouette_report[filename]=hashlib.sha256(source.read_bytes()).hexdigest()
report['silhouette']={'source_version':'0.2.6','files':silhouette_report}
avatar=Image.open(RES/'avatar_catgirl.png');avatar.thumbnail((384,384),Image.Resampling.LANCZOS);avatar.save(RES/'launcher_portrait.png',optimize=True)
(OUT/'catalog.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2),encoding='utf-8')
shutil.copy2(PACK/'manifest.json',DOC/'source-manifest.json')
shutil.copy2(PACK/'README.md',DOC/'source-README.md')
(QA/'artwork-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))
