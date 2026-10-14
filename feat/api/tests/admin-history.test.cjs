'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const assets=path.join(__dirname,'../acm_api/public/assets/admin');

function shell(start='/admin.html'){
  class Element{
    constructor(){this.nodes=new Map();this.events=new Map();this.attributes=new Map();this.value='';this.dataset={};this.classList={add(){},toggle(){}};}
    querySelector(selector){if(!this.nodes.has(selector))this.nodes.set(selector,new Element());return this.nodes.get(selector)}
    querySelectorAll(){return []}
    addEventListener(name,handler){this.events.set(name,handler)}
    setAttribute(name,value){this.attributes.set(name,value)}
    getAttribute(name){return this.attributes.get(name)}
    removeAttribute(name){this.attributes.delete(name)}
    replaceChildren(root){this.root=root}
    close(){} focus(){}
  }
  const document=new Element();document.getElementById=id=>document.querySelector('#'+id);document.createElement=()=>new Element();
  let address=new URL(start,'https://admin.test'),index=0;const entries=[address.href],events=new Map();
  const location={get href(){return address.href},get origin(){return address.origin},get pathname(){return address.pathname},get search(){return address.search}};
  const history={get length(){return entries.length},pushState(_state,_title,url){address=new URL(url,address);entries.splice(++index);entries.push(address.href)},replaceState(_state,_title,url){address=new URL(url,address);entries[index]=address.href}};
  const window={AUTH:{role:'root'},esc:String,api:async()=>({statuses:[]}),addEventListener:(name,handler)=>events.set(name,handler),removeEventListener:(name)=>events.delete(name),setTimeout,clearTimeout};
  const sandbox={window,document,location,history,URL,URLSearchParams,AbortController,DOMException,CSS:{escape:String}};
  const common=fs.readFileSync(path.join(assets,'common.js'),'utf8').replace('export function context','function context');
  // Keep the real lifecycle/router bodies; substitute only module loading and DOM/API boundaries.
  const cf=fs.readFileSync(path.join(assets,'cf-practice.js'),'utf8').replace(/^import [^\r\n]*\r?\n/,'').replace('export async function enter','async function enter');
  const router=fs.readFileSync(path.join(assets,'router.js'),'utf8').replace(/^import [^\r\n]*\r?\n/,'').replace(/await import\('\.\/'\+target\.section\+'\.js\?v=[^']+'\)/,'await loadModule(target.section)');
  vm.createContext(sandbox);vm.runInContext(common+'\n'+cf+'\n'+router,sandbox);
  sandbox.loadModule=async section=>section==='cf-practice'?{enter:sandbox.enter}:{enter:async()=>({})};
  const view=()=>document.getElementById('admin-content').root;
  return {window,location,history,view,open:url=>sandbox.open(url),async back(){assert(index>0);address=new URL(entries[--index]);await events.get('popstate')()},async forward(){assert(index<entries.length-1);address=new URL(entries[++index]);await events.get('popstate')()}};
}

test('real CF initialization replaces the default tab; one Back returns to accounts',async()=>{
  const app=shell();await app.window.PAGE_LOAD();await app.open('/admin.html?section=cf-practice');
  assert.equal(app.history.length,2);assert.equal(app.location.search,'?section=cf-practice&tab=recent');
  await app.back();assert.equal(app.location.search,'');
  await app.forward();assert.equal(app.location.search,'?section=cf-practice&tab=recent');assert.equal(app.history.length,2);
});

test('real CF user tab changes push history and Back/Forward restores selected panels',async()=>{
  const app=shell();await app.window.PAGE_LOAD();await app.open('/admin.html?section=cf-practice');
  app.view().querySelector('#tab-check').onclick();assert.equal(app.history.length,3);
  await app.back();assert.equal(app.view().querySelector('#tab-recent').getAttribute('aria-selected'),'true');assert.equal(app.location.search,'?section=cf-practice&tab=recent');
  await app.forward();assert.equal(app.view().querySelector('#tab-check').getAttribute('aria-selected'),'true');assert.equal(app.location.search,'?section=cf-practice&tab=check');
  assert.equal(app.history.length,3);
});

test('direct default and explicit CF tab URLs do not add startup history',async()=>{
  for(const tab of ['', '&tab=check']){
    const app=shell('/admin.html?section=cf-practice'+tab);await app.window.PAGE_LOAD();assert.equal(app.history.length,1);
    assert.equal(new URL(app.location.href).searchParams.get('tab'),tab?'check':'recent');
  }
});
