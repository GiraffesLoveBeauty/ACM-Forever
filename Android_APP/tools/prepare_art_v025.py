"""Convert checked local Web presets and prepare region masks without AI or uploads."""
from pathlib import Path
from PIL import Image, ImageDraw
import colorsys, hashlib, json, re
from collections import deque

ROOT=Path(__file__).resolve().parents[1]
RES=ROOT/'app/app/src/main/res/drawable-nodpi'
ASSETS=ROOT/'app/app/src/main/assets/themes'
ASSETS.mkdir(parents=True,exist_ok=True)
source=ROOT.parent/'feat/web/src/lib/theme-colors.js'
code=source.read_text(encoding='utf-8')
block=code[code.index('const PRESETS'):code.index('function presetProfile')]
presets=[]
for match in re.finditer(r"id:\s*'([^']+)'.*?name:\s*'([^']+)'.*?light:\s*\[([^]]+)\].*?dark:\s*\[([^]]+)\]",block,re.S):
    ident,name,light,dark=match.groups()
    presets.append(dict(id=ident,name=name,light=re.findall(r"'([^']+)'",light),dark=re.findall(r"'([^']+)'",dark)))
assert len(presets)==5
(ASSETS/'web-presets.json').write_text(json.dumps(dict(version=1,source='feat/web/src/lib/theme-colors.js',sha256=hashlib.sha256(source.read_bytes()).hexdigest(),presets=presets),ensure_ascii=False,indent=2),encoding='utf-8')

for name,output in [('avatar_catgirl','avatar_color_mask'),('catgirl_loading','loading_color_mask')]:
    im=Image.open(RES/(name+'.png')).convert('RGBA');w,h=im.size
    protected=Image.new('L',im.size);draw=ImageDraw.Draw(protected)
    polygons=([[(.04,0),(.24,0),(.37,.125),(.25,.175),(.075,.315),(.025,.30)],[(.60,.12),(.82,.08),(.89,.11),(.89,.22),(.84,.32),(.78,.335),(.76,.25),(.70,.22)],[(0,.945),(.20,.94),(.30,1),(0,1)]] if name=='avatar_catgirl' else
              [[(.16,.09),(.28,.07),(.37,.15),(.26,.29),(.16,.26)],[(.53,.02),(.72,0),(.75,.16),(.64,.21),(.58,.12)],
               [(.47,.65),(.57,.66),(.63,.66),(.77,.64),(.80,.67),(.70,.755),(.58,.762),(.49,.72)],
               [(.622,.824),(.655,.823),(.690,.842),(.716,.876),(.700,.917),(.650,.913),(.650,.87)],
               [(.446,.795),(.490,.800),(.520,.835),(.503,.861),(.454,.848)]])
    for poly in polygons:draw.polygon([(round(x*w),round(y*h)) for x,y in poly],fill=255)
    mask=Image.new('RGB',im.size)
    for y in range(h):
        for x in range(w):
            r,g,b,a=im.getpixel((x,y));hue,sat,value=colorsys.rgb_to_hsv(r/255,g/255,b/255);hue*=360
            if a<20:continue
            decor=(310<hue<360 and sat>.12 and value>.62 and ((x>w*.65 and y<h*.42) or (name=='catgirl_loading' and .42*w<x<.7*w and .65*h<y<.85*h)))
            if decor:mask.putpixel((x,y),(0,0,255));continue
            if protected.getpixel((x,y)):continue
            hair=((hue>255 and value<.78 and sat<.45) or (value<.38 and sat<.24) or (y<h*.28 and sat<.5 and value<.85))
            if name=='catgirl_loading':hair=hair and (y<h*.66 or x>w*.68)
            if hair:mask.putpixel((x,y),(255,0,0));continue
            clothing=(205<hue<255 and sat>.08 and value>.5 and y>h*(.73 if name=='avatar_catgirl' else .58))
            if clothing:mask.putpixel((x,y),(0,255,0))
    mask.save(RES/(output+'.png'),optimize=True)

# Clear only near-white regions connected to an official mark's outer edge.
# Enclosed white details, original colours and shapes stay intact.
for path in RES.glob('platform_*.png'):
    im=Image.open(path).convert('RGBA');w,h=im.size;seen=set();q=deque()
    for x in range(w):q.append((x,0));q.append((x,h-1))
    for y in range(h):q.append((0,y));q.append((w-1,y))
    while q:
        x,y=q.popleft()
        if x<0 or y<0 or x>=w or y>=h or (x,y) in seen:continue
        seen.add((x,y));r,g,b,a=im.getpixel((x,y))
        if a==0 or min(r,g,b)>242:
            im.putpixel((x,y),(r,g,b,0));q.extend([(x-1,y),(x+1,y),(x,y-1),(x,y+1)])
    im.save(path,optimize=True)

mask=Image.open(RES/'catgirl_mask.png').getchannel('A')
logo=Image.new('RGBA',mask.size,'#000000');logo.putalpha(mask);logo.thumbnail((272,272),Image.Resampling.LANCZOS)
canvas=Image.new('RGBA',(432,432));canvas.alpha_composite(logo,((432-logo.width)//2,(432-logo.height)//2));canvas.save(RES/'launcher_silhouette.png',optimize=True)
print('Prepared 5 Web themes, 2 region masks, transparent official marks and silhouette launcher.')

# Reproduce the runtime HSV mapping to inspect three distinct groups before packaging.
qa=ROOT/'app/app/build/qa-v025';qa.mkdir(parents=True,exist_ok=True)
preview=Image.new('RGB',(1120,720),'#f4f5f7')
for column,tone in enumerate(('#c8eb21','#83b8e5','#ebafc5','#baa4df')):
    target=colorsys.rgb_to_hsv(*(int(tone[i:i+2],16)/255 for i in (1,3,5)))
    for row,(name,mask_name) in enumerate((('avatar_catgirl','avatar_color_mask'),('catgirl_loading','loading_color_mask'))):
        art=Image.open(RES/(name+'.png')).convert('RGBA');mask=Image.open(RES/(mask_name+'.png')).convert('RGB')
        for y in range(art.height):
            for x in range(art.width):
                group=mask.getpixel((x,y));r,g,b,a=art.getpixel((x,y))
                if not a or group==(0,0,0):continue
                hue,sat,value=colorsys.rgb_to_hsv(r/255,g/255,b/255)
                if group[0]>128:hue=target[0];sat=0 if target[1]<.05 else .25+.3*target[1]
                elif group[1]>128:hue=target[0];sat=0 if target[1]<.05 else .15+.35*target[1]
                else:hue=(target[0]+35/360)%1;sat=0 if target[1]<.05 else .25+.18*target[1]
                rgb=colorsys.hsv_to_rgb(hue,sat,value);art.putpixel((x,y),(*[round(channel*255) for channel in rgb],a))
        art.thumbnail((256,320),Image.Resampling.LANCZOS)
        preview.paste(art,(column*280+(280-art.width)//2,row*360+(360-art.height)//2),art)
preview.save(qa/'character-theme-preview.png')
