'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const assets=path.join(__dirname,'../acm_api/public/assets/admin');

async function fixture({role='root',problems=[],tasks=()=>[],submit=()=>({task:{id:'sync-1'}})}={}){
  class Element{
    constructor(){this.nodes=new Map();this.events=new Map();this.value='';this.textContent='';this.innerHTML='';this.disabled=false;this.hidden=false;this.checked=false;}
    querySelector(selector){if(!this.nodes.has(selector))this.nodes.set(selector,new Element());return this.nodes.get(selector);}
    querySelectorAll(){return [];}
    insertAdjacentHTML(_position,html){this.innerHTML=html+this.innerHTML;}
    addEventListener(name,handler,{signal}={}){this.events.set(name,handler);signal?.addEventListener('abort',()=>this.events.delete(name),{once:true});}
    removeAttribute(){}
    reportValidity(){return true;}
    async fire(name){await this.events.get(name)?.({preventDefault(){},target:this});}
  }
  const root=new Element(),timers=new Map(),calls=[];let timerId=0;
  const $=selector=>root.querySelector(selector);
  $('#sync-platform').value='atcoder';$('#sync-scope').value='contest';$('#sync-language').value='en';$('#sync-limit').value='20';$('#owner').value='12345678';
  const window={AUTH:{role,qq_id:'12345678'},esc:value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),
    setTimeout:fn=>{timers.set(++timerId,fn);return timerId;},clearTimeout:id=>timers.delete(id),
    api:async(url,options={})=>{
      calls.push({url,options});
      if(url==='/tasks')return tasks();
      if(url==='/admin/problems/sync')return submit(JSON.parse(options.body));
      if(url==='/admin/database'||url==='/admin/database/init')return {initialized:true,message:'数据库初始化完成，已有数据已保留。',platforms:[{platform:'atcoder',total:2,collected:2,failed:0,samples:6}]};
      if(url.startsWith('/problems?'))return {items:problems,total:problems.length};
      throw Error('Unexpected API '+url);
    }};
  const common=fs.readFileSync(path.join(assets,'common.js'),'utf8').replace('export function context','function context');
  const problemsModule=fs.readFileSync(path.join(assets,'problems.js'),'utf8').replace('export async function enter','async function enter');
  const sandbox={window,URLSearchParams,AbortController,DOMException,CSS:{escape:String}};
  vm.createContext(sandbox);vm.runInContext(common+'\n'+problemsModule,sandbox);
  const ctx=sandbox.context(root,new URLSearchParams(),{}, {notice:text=>$('#notice').textContent=text});
  await sandbox.enter(ctx);
  return {$,ctx,calls,timers,async tick(){const [id,callback]=timers.entries().next().value;timers.delete(id);callback();await new Promise(resolve=>setImmediate(resolve));}};
}

const task=(status,extra={})=>({id:'sync-1',kind:'题目采集',platform:'atcoder',status,progress:{done:0,total:2},result:{contest_id:'abc370'},...extra});

test('administrator and member problem links open the stored local statement',async()=>{
  for(const role of ['root','member']){
    const view=await fixture({role,problems:[{platform:'codeforces',problem_id:'cf_2273B',problem_name:'Robot Championship',problem_url:'https://codeforces.com/contest/2273/problem/B'}]});
    const html=view.$('#problem-list').innerHTML;
    assert.match(html,/href="\/problem\.html\?platform=codeforces&amp;problem_id=cf_2273B"/);
    assert.doesNotMatch(html,/https:\/\/codeforces\.com/);
    view.ctx.dispose();
  }
});

test('AtCoder submission normalizes IDs, locks duplicate submission and refreshes the list on completion',async()=>{
  let accepted=false,finished=false;
  const view=await fixture({submit:()=>{accepted=true;return {task:{id:'sync-1'}};},tasks:()=>accepted?[task(finished?'completed':'running',{progress:{done:finished?2:0,total:2},result:{contest_id:'abc370',success_count:finished?2:0,sample_count:finished?6:0}})]:[]});
  view.$('#sync-contest').value='abc370';view.$('#sync-limit').value='2';view.$('#sync-problems').value='abc370_a， abc370_b abc370_a';view.$('#sync-refresh').checked=true;
  await view.$('#problem-sync-form').fire('submit');await view.$('#problem-sync-form').fire('submit');
  const posts=view.calls.filter(call=>call.url==='/admin/problems/sync');assert.equal(posts.length,1);
  assert.deepEqual(JSON.parse(posts[0].options.body),{platform:'atcoder',scope:'contest',contest_id:'abc370',limit:2,problem_ids:['abc370_a','abc370_b'],language:'en',refresh:true});
  assert.equal(view.$('#problem-sync-fields').disabled,true);assert.equal(view.timers.size,1);
  finished=true;await view.tick();
  assert.equal(view.$('#problem-sync-fields').disabled,false);assert.match(view.$('#sync-summary').textContent,/成功 2 题.*样例 6 组/);
  assert.equal(view.calls.filter(call=>call.url.startsWith('/problems?')).length,2);assert.equal(view.timers.size,0);view.ctx.dispose();
});

test('Codeforces selects English and posts the selected contest and limit',async()=>{
  let accepted=false;
  const view=await fixture({submit:()=>{accepted=true;return {task:{id:'sync-1'}};},tasks:()=>accepted?[task('completed',{platform:'codeforces',result:{contest_id:'1843'}})]:[]});
  view.$('#sync-language').value='ja';view.$('#sync-platform').value='codeforces';await view.$('#sync-platform').fire('change');
  assert.equal(view.$('#sync-language').value,'en');assert.equal(view.$('#sync-language').disabled,true);
  view.$('#sync-contest').value='1843';view.$('#sync-limit').value='10';view.$('#sync-problems').value='1843A, cf_1843B';
  await view.$('#problem-sync-form').fire('submit');
  assert.deepEqual(JSON.parse(view.calls.find(call=>call.url==='/admin/problems/sync').options.body),{platform:'codeforces',scope:'contest',contest_id:'1843',limit:10,problem_ids:['1843A','cf_1843B'],language:'en',refresh:false});
  assert.equal(view.$('#problem-sync-fields').disabled,false);assert.equal(view.$('#sync-language').disabled,true);view.ctx.dispose();
});

test('existing jobs resume monitoring; exiting the module clears its polling timer',async()=>{
  const view=await fixture({tasks:()=>[task('running')]});
  assert.equal(view.$('#problem-sync-fields').disabled,true);assert.equal(view.ctx.memory.problemSyncTaskId,'sync-1');
  assert.equal(view.timers.size,1);view.ctx.dispose();assert.equal(view.timers.size,0);
  assert.equal(view.$('#problem-sync-form').events.size,0);assert.equal(view.calls.some(call=>call.url==='/admin/problems/sync'),false);
});

test('backend validation errors retain input and re-enable the form',async()=>{
  const view=await fixture({submit:()=>{throw Object.assign(Error('题号格式无效'),{status:400});}});
  view.$('#sync-contest').value='abc370';view.$('#sync-problems').value='invalid-id';await view.$('#problem-sync-form').fire('submit');
  assert.match(view.$('#sync-message').textContent,/提交失败：题号格式无效/);
  assert.equal(view.$('#sync-problems').value,'invalid-id');assert.equal(view.$('#problem-sync-fields').disabled,false);assert.equal(view.timers.size,0);view.ctx.dispose();
});

test('partial failure shows escaped errors and successful rows still refresh the catalog',async()=>{
  let accepted=false;
  const view=await fixture({submit:()=>{accepted=true;return {task:{id:'sync-1'}};},tasks:()=>accepted?[task('partial',{progress:{done:2,total:2},result:{contest_id:'abc370',success_count:1,failure_count:1,sample_count:3,failures:[{problem_id:'abc370_b',error:'<img src=x onerror=alert(1)>'}]}})]:[]});
  view.$('#sync-contest').value='abc370';await view.$('#problem-sync-form').fire('submit');
  assert.match(view.$('#sync-message').textContent,/部分题目拉取失败/);assert.equal(view.$('#sync-errors').hidden,false);
  assert.match(view.$('#sync-error-list').innerHTML,/&lt;img/);assert.doesNotMatch(view.$('#sync-error-list').innerHTML,/<img/);
  assert.equal(view.calls.filter(call=>call.url.startsWith('/problems?')).length,2);assert.equal(view.$('#problem-sync-fields').disabled,false);view.ctx.dispose();
});

test('members have no collection form or admin task requests',async()=>{
  const view=await fixture({role:'member'});
  assert.equal(view.calls.some(call=>call.url==='/tasks'||call.url.startsWith('/admin/')),false);assert.equal(view.$('#problem-sync-form').events.size,0);view.ctx.dispose();
});

test('full platform mode hides contest filters and sends a batch size without a total limit',async()=>{
  let accepted=false;
  const view=await fixture({submit:()=>{accepted=true;return {task:{id:'sync-1'}};},tasks:()=>accepted?[task('completed',{progress:{done:3,total:3,batch:3},result:{scope:'platform',metadata_count:3,success_count:3,batch_count:3}})]:[]});
  view.$('#sync-contest').value='abc370';view.$('#sync-problems').value='abc370_a';
  view.$('#sync-scope').value='platform';await view.$('#sync-scope').fire('change');
  assert.equal(view.$('#sync-contest').required,false);assert.equal(view.$('#sync-contest').disabled,true);assert.equal(view.$('#sync-problems-label').hidden,true);
  view.$('#sync-limit').value='1';await view.$('#problem-sync-form').fire('submit');
  assert.deepEqual(JSON.parse(view.calls.find(call=>call.url==='/admin/problems/sync').options.body),{platform:'atcoder',scope:'platform',language:'en',refresh:false,batch_size:1});
  assert.match(view.$('#sync-message').textContent,/全平台/);assert.match(view.$('#sync-summary').textContent,/批次 3 \/ 3/);view.ctx.dispose();
});

test('initialization uses the configured database endpoint and refreshes statistics',async()=>{
  const view=await fixture();await view.$('#problem-db-init').fire('click');
  const call=view.calls.find(call=>call.url==='/admin/database/init');
  assert.equal(call.options.method,'POST');assert.equal(call.options.body,'{}');
  assert.match(view.$('#problem-db-message').textContent,/已有数据已保留/);assert.match(view.$('#problem-db-counts').innerHTML,/目录 2 题/);
  assert.equal(view.$('#problem-db-init').disabled,false);view.ctx.dispose();
});
