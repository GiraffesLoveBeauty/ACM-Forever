'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../acm_api/public/assets/theme-editor.js'),'utf8');
function load(){
 const window={document:{}};
 const instrumented=source.replace('  window.ACMTheme =', '  window.__caches = {luminanceCache, tokenCache, readableCache, candidateCache};\n  window.ACMTheme =');
 vm.runInNewContext(instrumented,{window});return window;
}
const window=load(), api=window.ACMTheme;
let seed=0x51a7c0de;
const color=()=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return '#'+(seed>>>8).toString(16).padStart(6,'0')};
const plain=value=>JSON.parse(JSON.stringify(value));
function luminance(hex){const c=[1,3,5].map(i=>parseInt(hex.slice(i,i+2),16)/255).map(n=>n<=.04045?n/12.92:((n+.055)/1.055)**2.4);return c[0]*.2126+c[1]*.7152+c[2]*.0722}
test('lookup luminance preserves reference contrast for 512 color pairs',()=>{
 for(let i=0;i<512;i++){
  const a=color(),b=color(),x=luminance(a),y=luminance(b);
  assert.equal(api.getContrast(a,b),(Math.max(x,y)+.05)/(Math.min(x,y)+.05));
 }
});
test('five presets return independent editable profiles and safe light/dark defaults',()=>{
 for(const id of ['industrial','mint','gray','sunshine','rose'])for(const mode of ['light','dark']){
  const p=api.presetProfile(id,mode),original=JSON.stringify(p);
  assert.ok(api.contrastChecks(p,mode==='dark').every(c=>c.pass),id+'/'+mode);
  p.colors.primary='#123456';p.overrides.text='#ff0000';
  assert.equal(JSON.stringify(api.presetProfile(id,mode)),original);
 }
 assert.throws(()=>api.presetProfile('__proto__','light'));
 assert.throws(()=>api.presetProfile('mint','system'));
});
test('random profiles remain repairable; overrides and inputs are not silently modified',()=>{
 for(let i=0;i<160;i++){
  const p={colors:{primary:color(),background:color(),surface:color(),accent:color()},overrides:{text:'#123456',hero:'#777777',border:'#345678'}};
  const original=JSON.stringify(p);
  for(const dark of [false,true]){
   const t=api.deriveTokens(p,dark);
   assert.equal(t['--text'],p.overrides.text);assert.equal(t['--line'],p.overrides.border);
   assert.ok(api.contrastChecks(api.repairProfile(p,dark),dark).every(c=>c.pass));
   assert.equal(JSON.stringify(p),original);
  }
 }
});
test('bounded caches preserve tokens after eviction and do not bypass public validation',()=>{
 const expected=plain(api.deriveTokens(api.createDefaultTheme().light,false));
 for(let i=0;i<180;i++){
  const p=api.createDefaultTheme().light;for(const k of Object.keys(p.colors))p.colors[k]=color();api.deriveTokens(p,!!(i%2));
 }
 for(const [name,limit] of Object.entries({luminanceCache:4096,tokenCache:80,readableCache:512,candidateCache:32}))assert.ok(window.__caches[name].size<=limit,name);
 assert.deepEqual(plain(api.deriveTokens(api.createDefaultTheme().light,false)),expected);
 const bad=api.createDefaultTheme().light;
 api.deriveTokens(bad,false);
 Object.defineProperty(bad.colors,'primary',{enumerable:true,get(){throw new Error('must not evaluate getter')}});
 assert.throws(()=>api.deriveTokens(bad,false),/访问器/);
});
