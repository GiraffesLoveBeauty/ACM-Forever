import assert from 'node:assert/strict';
import { after, afterEach, beforeEach, test } from 'node:test';
import { JSDOM } from 'jsdom';
import { h } from 'vue';
import { RouterView } from 'vue-router';
import { setAuth } from '../src/lib/api.js';
import { localTime, utcTime, trainingReturn } from '../src/lib/training-tasks.js';
import { cleanupCompiled, find, loadSfc, mount, settle, textOf } from './helpers/vue-harness.mjs';
const Training = (await import(await loadSfc('src/admin/Training.vue'))).default;
const Root = { render: () => h(RouterView) };
const keys = ['window','document','Document','Node','ShadowRoot','navigator','location','history','fetch'];
const originals = new Map(keys.map(k=>[k,Object.getOwnPropertyDescriptor(globalThis,k)]));
let dom, mounted, calls, guard, stored, conflict;
const response = (data,status=200)=>new Response(JSON.stringify(data),{status});
beforeEach(()=>{
  dom = new JSDOM('<!doctype html><body></body>', {url:'http://127.0.0.1/admin.html?section=training'});
  for(const key of keys.filter(k=>k!=='fetch')) Object.defineProperty(globalThis,key,{value:dom.window[key],configurable:true,writable:true});
  setAuth({authenticated:true,role:'admin',qq_id:'12345678',csrf_token:'synthetic'},true);
  calls=[];guard=null;stored=null;conflict=false;dom.window.confirm=()=>false;
  globalThis.fetch=async(url,options={})=>{
    const body=options.body ? JSON.parse(options.body) : null;calls.push({url,body,options});
    if(url.endsWith('/options')) return response({enabled:true,statuses:['动态实验组'],capabilities:[{platform:'codeforces',label:'Codeforces'}],max_problems:50});
    if(url.includes('/resolve-problems')) return response({items:body.problems.map((p,i)=>({...p,problem_name:'合成题'+i,problem_id:p.problem_id.startsWith('cf_')?p.problem_id:'cf_'+p.problem_id,tags:[],supported:true})),errors:[],duplicates:0});
    if(options.method==='POST' && url==='/api/admin/training-tasks') {stored={...body,id:17,version:1,state:'draft',creator_name:'管理员',audit:[]};return response(stored,201);}
    if(options.method==='PATCH'){stored={...stored,...body,version:stored.version+1};return response(stored);}
    if(url.includes('/audience-preview')) return response({preview_token:'preview-proof',recipient_count:2,excluded_count:1,unbound_count:1,total:3,page:1,items:[{qq_id:'22345678',name:'合成成员',status:'动态实验组',unbound:true}]});
    if(url.endsWith('/publish')) return conflict ? response({code:'audience_changed',message:'名单已变化，请重新预览'},409) : response({...stored,state:'published',version:2,phase:'active',problems:stored.problems});
    if(url==='/api/admin/training-tasks/17') return response({...stored,phase:stored.state==='draft'?'draft':'active'});
    if(url.startsWith('/api/admin/training-tasks?')) return response({items:[],total:0});
    throw Error('Unexpected request '+url);
  };
});
afterEach(async()=>{mounted?.unmount();await settle();dom.window.close();for(const[key,descriptor] of originals) if(descriptor)Object.defineProperty(globalThis,key,descriptor);else delete globalThis[key];setAuth({authenticated:false},true);});
after(cleanupCompiled);
const buttons = word=>find(mounted.root,n=>n.type==='button'&&textOf(n).includes(word));
const click=async word=>{const button=buttons(word)[0];assert(button,'button: '+word);await button.props.onClick({button:0,preventDefault(){}});await settle();};
const control=(label,type='input')=>{const wrapper=find(mounted.root,n=>n.type==='label'&&textOf(n).startsWith(label))[0];assert(wrapper,label);return find(wrapper,n=>n.type===type)[0];};
const set=async(label,value,type)=>{control(label,type).props['onUpdate:modelValue'](value);await settle();};
async function setupEditor(){mounted=await mount(Root,[{path:'/admin.html',component:Training}],'/admin.html?section=training&task_id=new&tab=edit&step=1', {registerLeaveGuard:fn=>{guard=fn;return()=>{guard=null;};}});await set('任务标题','真实接口训练');await set('标准题号','1A 2A','textarea');await click('校验并添加');}
async function preview(){await setupEditor();await click('下一步');await set('动态实验组',['动态实验组']);await click('保存并预览');}

test('Shanghai time and return targets preserve task identity and reject unsafe destinations',()=>{
  const stamp=1794391200;assert.equal(utcTime(localTime(stamp)),stamp);
  assert.equal(trainingReturn('/training-tasks.html?task_id=17&tab=history&qq_id=evil'),'/training-tasks.html?task_id=17&tab=history');
  assert.equal(trainingReturn('/admin.html?section=training&task_id=17&tab=progress'),'/admin.html?section=training&task_id=17&tab=progress');
  for(const value of ['//evil.test','/admin.html?section=accounts','https://evil.test/training-tasks.html','/\\evil']) assert.equal(trainingReturn(value),null);
});
test('admin uses dynamic identities, preserves order, and requires exclusion confirmation before publish',async()=>{
  await preview();
  assert.equal(mounted.router.currentRoute.value.query.step,'3');
  assert(textOf(mounted.root).includes('未绑定也可接收'));
  const create=calls.find(c=>c.options.method==='POST'&&c.url==='/api/admin/training-tasks');
  assert.deepEqual(create.body.problems.map(p=>p.problem_id),['cf_1A','cf_2A']);
  assert.deepEqual(create.body.statuses,['动态实验组']);
  assert(buttons('确认发布任务')[0].props.disabled);
  await set('我已确认以上排除原因',true);
  assert(!buttons('确认发布任务')[0].props.disabled);
  await click('确认发布任务');
  const publish=calls.find(c=>c.url.endsWith('/publish'));
  assert.equal(publish.body.preview_token,'preview-proof');assert(publish.options.headers['Idempotency-Key']);
  assert.equal(mounted.router.currentRoute.value.query.tab,'overview');
});
test('unsaved internal navigation is guarded and changed audiences discard publish proof',async()=>{
  await setupEditor();
  assert.equal(guard({path:'/admin.html',query:{section:'members'}}),false);
  assert.equal(guard({path:'/admin.html',query:{section:'training',task_id:'new',tab:'edit',step:2}}),true);
  await click('下一步');await set('动态实验组',['动态实验组']);await click('保存并预览');await set('我已确认以上排除原因',true);
  conflict=true;await click('确认发布任务');
  assert(textOf(mounted.root).includes('名单已变化'));assert(buttons('确认发布任务')[0].props.disabled);
  assert(textOf(mounted.root).includes('预览尚未生成或已失效'));
});
