'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const window={document:{}};
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../acm_api/public/assets/theme-editor.js'),'utf8'),{window});
const api=window.ACMTheme;
const copy=x=>JSON.parse(JSON.stringify(x));
test('safe HEX normalization and contrast',()=>{
 assert.equal(api.normalizeColor('#AbC'),'#aabbcc');
 for(const v of ['url(x)','red','#1234','var(--x)',null])assert.equal(api.normalizeColor(v),null);
 assert.equal(api.getContrast('#000','#fff'),21);
});
test('strict schema rejects CSS and unknown keys',()=>{
 let t=copy(api.createDefaultTheme());t.light.colors.primary='url(x)';assert.throws(()=>api.validateTheme(t));
 t=copy(api.createDefaultTheme());t.extra=true;assert.throws(()=>api.validateTheme(t));
 assert.throws(()=>api.parseThemeJSON('{"__proto__":{}}'));
 assert.throws(()=>api.parseThemeJSON(' '.repeat(32769)));
 let called=false;t=copy(api.createDefaultTheme());Object.defineProperty(t,'mode',{enumerable:true,get(){called=true;return 'light'}});
 assert.throws(()=>api.validateTheme(t));assert.equal(called,false);
});
test('light/dark profiles independent and default contrast passes',()=>{
 const t=api.createDefaultTheme();
 for(const mode of ['light','dark'])assert.ok(api.contrastChecks(t[mode],mode==='dark').every(x=>x.pass));
 t.light.colors.primary='#123456';assert.notEqual(t.dark.colors.primary,'#123456');
 const tokens=api.deriveTokens(t.light,false);assert.equal(tokens['--brand'],'#123456');assert.ok(Object.isFrozen(tokens));
});
test('repair coordinates incompatible surfaces without mutating input',()=>{
 const p=copy(api.createDefaultTheme().light);p.colors.background='#000000';p.colors.surface='#ffffff';p.overrides.text='#ffffff';
 assert.ok(api.contrastChecks(p,false).some(x=>!x.pass));
 const fixed=api.repairProfile(p,false);assert.ok(api.contrastChecks(fixed,false).every(x=>x.pass));
 assert.equal(p.colors.surface,'#ffffff');
});

test('industrial presets match defaults with readable hero and accent foregrounds',()=>{
 const theme=api.createDefaultTheme();
 for(const mode of ['light','dark']){
  assert.deepEqual(copy(api.presetProfile('industrial',mode)),copy(theme[mode]));
  const tokens=api.deriveTokens(theme[mode],mode==='dark');
  assert.ok(api.getContrast(tokens['--hero-bg'],tokens['--hero-text'])>=4.5,mode+' hero text');
  assert.ok(api.getContrast(tokens['--hero-bg'],tokens['--hero-muted'])>=4.5,mode+' hero description');
  assert.ok(api.getContrast(theme[mode].colors.accent,tokens['--on-accent'])>=4.5,mode+' primary action');
 }
});

test('saved legacy profiles retain their colors and mode after parsing',()=>{
 const theme=copy(api.createDefaultTheme());
 theme.light=copy(api.presetProfile('mint','light'));
 theme.dark=copy(api.presetProfile('rose','dark'));
 theme.mode='dark';
 assert.deepEqual(copy(api.parseThemeJSON(JSON.stringify(theme))),theme);
});
test('extreme colors produce safe automatic foreground pairs',()=>{
 for(const c of ['#000000','#ffffff','#777777','#ff0000','#00ff00','#0000ff']){
  const p=copy(api.createDefaultTheme().dark);for(const k of Object.keys(p.colors))p.colors[k]=c;
  assert.ok(api.contrastChecks(api.repairProfile(p,true),true).every(x=>x.pass),c);
 }
});
