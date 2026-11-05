const {pathToFileURL}=require('node:url'),path=require('node:path');
module.exports=async({evaluate,check,cdp,screenshot})=>{
  let removed=false;
  const url=pathToFileURL(path.resolve('Android_APP/app/app/src/main/assets/admin/index.html')).href;
  const injection=await cdp('Page.addScriptToEvaluateOnNewDocument',{source:`
    window.testCalls=[];window.confirm=()=>true;
    window.testRole=new URLSearchParams(location.search).get('role')||'admin';
    window.testStatus=200;
    window.AcmAdminNative={close(){},copyText(text){window.testCopy=text},saveDocument(name,text){window.testExport={name,text}},request(id,method,raw,body){
      const p=raw.split('?')[0];testCalls.push({method,path:p,body});
      let data=[],status=window.testStatus;
      if(p==='/api/auth/me'){data={authenticated:true,role:testRole,csrf_token:'test-only',qq_id:'90000001'};status=200;}
      else if(p.includes('candidates')||p==='/api/admin/members')data={items:[],total:0,page:1,page_size:20};
      else if(p==='/api/problems')data={items:[],total:0};
      else if(p==='/api/admin/cf/options')data={statuses:[]};
      else if(p==='/api/admin/database')data={initialized:true};
      else if(p==='/api/ui/preferences')data={font_scale:1};
      else if(p==='/api/settings/contest-report')data={time:'',group_id:''};
      else if(p==='/api/admins')data={root:[],admins:[],can_manage:testRole==='root'};
      else if(p==='/api/forum/moderation/posts')data=[{id:1,title:'Test-only topic',body:'**Test-only body**',author_name:'Test author'}];
      if(method!=='GET')data={success:true};
      setTimeout(()=>window.__acmAdminResponse(id,{status,data,title:status===404?'无API接口':status===0?'无网络':''}),5);
    }};
  `});
  const pause=()=>new Promise(resolve=>setTimeout(resolve,100));
  async function load(query){await cdp('Page.navigate',{url:url+query});for(let i=0;i<80;i++){if(await evaluate("!!document.querySelector('.mobile-admin') && !document.querySelector('.mobile-loading')"))return;await pause();}throw Error('Admin UI did not initialize');}
  async function section(key){await evaluate(`document.querySelector('.module-picker select').value=${JSON.stringify(key)};document.querySelector('.module-picker select').dispatchEvent(new Event('change'))`);await pause();await pause();}
  try{
    await load('?role=member');
    await check("document.querySelector('[role=alert]').textContent.includes('无访问权限') && !document.querySelector('.admin-module') && testCalls.length===1",'Member cannot load management modules or issue their requests');
    await load('?role=admin');
    await check("document.querySelectorAll('.mobile-admin-nav a').length===9 && !document.querySelector('[role=alert]') && !document.querySelector('.admin-create-grid option[value=root]')",'Administrator sees nine modules without Root role control');
    const modules=['members','training','problems','cf-practice','contests','tasks','moderation','settings'];
    for(const key of modules){await section(key);await check("!!document.querySelector('.admin-module') && !document.querySelector('[role=alert]') && document.documentElement.scrollWidth<=window.innerWidth",key+' renders within mobile viewport');}
    await check("testCalls.some(c=>c.path==='/api/admin/members') && testCalls.some(c=>c.path==='/api/admin/database') && testCalls.some(c=>c.path==='/api/admin/cf/options') && testCalls.some(c=>c.path==='/api/tasks') && testCalls.some(c=>c.path==='/api/admins')",'Modules invoke existing management endpoints');
    await section('moderation');
    await evaluate("Array.from(document.querySelectorAll('.admin-module button')).find(b=>b.textContent.includes('通过')).click()");await pause();
    await check("testCalls.some(c=>c.method==='POST' && c.path==='/api/forum/moderation/posts/1' && JSON.parse(c.body).decision==='publish')",'Moderation submits actual existing decision request');
    await section('accounts');
    await evaluate("document.querySelector('.admin-create').open=true;const inputs=document.querySelectorAll('.admin-create-grid input');inputs[0].value='90000002';inputs[0].dispatchEvent(new Event('input'));inputs[2].value='Synthetic-Only-Password!';inputs[2].dispatchEvent(new Event('input'));document.querySelector('.admin-create-body').dispatchEvent(new Event('submit',{cancelable:true}))");await pause();
    await check("testCalls.some(c=>c.method==='POST' && c.path==='/api/admin/web-accounts' && JSON.parse(c.body).qq_id==='90000002')",'Account creation uses existing authenticated request');
    await evaluate("const a=document.createElement('a');a.href=URL.createObjectURL(new Blob(['test-only']));a.download='test-only.csv';a.click()");await pause();
    await check("testExport?.name==='test-only.csv' && testExport.text==='test-only'",'Detached anchor exports reach native document picker bridge');
    await evaluate("testStatus=404");await section('members');
    await check("document.querySelector('[role=alert]').textContent.includes('无API接口') && document.querySelector('.admin-module').classList.contains('module-hidden')",'Missing endpoint replaces module with red error panel');
    await evaluate("testStatus=0");await section('tasks');
    await check("document.querySelector('[role=alert]').textContent.includes('无网络')",'Native offline response shows no network');
    await load('?role=root');
    await check("!!document.querySelector('.admin-create-grid option[value=root]')",'Root-only controls follow confirmed server role');
    // Capture a real missing endpoint state without any synthetic response or role.
    await cdp('Page.removeScriptToEvaluateOnNewDocument',{identifier:injection.identifier});
    removed=true;
    await load('');await screenshot('admin-error-preview.png');
    await check("document.querySelector('[role=alert]').textContent.includes('无API接口') && !document.querySelector('.admin-module')",'Unconfigured preview contains no synthetic administrator data');
    console.log('Administrator UI checks passed: roles, nine modules, mobile width, management writes, native export and failures.');
  }finally{if(!removed)await cdp('Page.removeScriptToEvaluateOnNewDocument',{identifier:injection.identifier});}
};
