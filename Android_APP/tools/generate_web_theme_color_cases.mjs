// Generate independent expected native colours with the actual Web algorithm.
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {deriveTokens} from '../../feat/web/src/lib/theme-colors.js';
import {DESIGN_TEMPLATES,templateTheme} from '../../feat/web/src/lib/design-template.js';
const schemes=DESIGN_TEMPLATES.map(x=>({id:x.id,...templateTheme(x.id)}));
const colors=JSON.parse(readFileSync(new URL('../app/app/src/main/assets/themes/web-presets.json',import.meta.url),'utf8'));
for(const p of colors.presets.filter(x=>x.id!=='industrial'))schemes.push({id:p.id,...Object.fromEntries(['light','dark'].map(mode=>[mode,{colors:Object.fromEntries(['primary','background','surface','accent'].map((key,i)=>[key,p[mode][i]])),overrides:{}}]))});
const cases=[];
for(const scheme of schemes)for(const dark of [false,true])for(const overrides of [true,false]){
  const profile=structuredClone(scheme[dark?'dark':'light']);if(!overrides)profile.overrides={};
  cases.push({name:`${scheme.id}/${dark?'dark':'light'}/${overrides?'overrides':'derived'}`,dark,profile,tokens:deriveTokens(profile,dark)});
}
const target=new URL('../app/app/src/test/resources/web-theme-colors.json',import.meta.url);mkdirSync(new URL('.',target),{recursive:true});writeFileSync(target,JSON.stringify(cases,null,2)+'\n');
console.log(`Generated ${cases.length} cases from the real Web colour solver.`);
