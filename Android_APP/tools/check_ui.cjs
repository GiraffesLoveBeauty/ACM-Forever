// Run against a temporary headless Edge instance with CDP on port 9231.
// Synthetic responses exist only in this test; screenshots use unconfigured/offline states.
const fs = require('node:fs');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const assert = require('node:assert/strict');
(async () => {
  const targets = await (await fetch('http://127.0.0.1:9231/json/list')).json();
  const target = targets.find(item => item.type === 'page'); assert(target);
  const socket = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject;});
  let id=0; const pending=new Map(), exceptions=[];
  socket.onmessage=({data})=>{const result=JSON.parse(data);if(result.method==='Runtime.exceptionThrown')exceptions.push(result.params);const entry=pending.get(result.id);if(!entry)return;pending.delete(result.id);clearTimeout(entry.timer);result.error?entry.reject(Error(JSON.stringify(result.error))):entry.resolve(result.result);};
  function cdp(method,params={}) {return new Promise((resolve,reject)=>{const next=++id,timer=setTimeout(()=>reject(Error('Timeout '+method)),20000);pending.set(next,{resolve,reject,timer});socket.send(JSON.stringify({id:next,method,params}));});}
  async function evaluate(expression) {if(expression.includes('await ')&&!expression.startsWith('('))expression='(async()=>{'+expression+'})()';const result=await cdp('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(result.exceptionDetails)throw Error(result.exceptionDetails.exception?.description||result.exceptionDetails.text);return result.result.value;}
  const url=pathToFileURL(path.resolve('Android_APP/prototype/index.html')).href;
  async function navigate(query='') {await cdp('Page.navigate',{url:url+query});for(let n=0;n<80;n++){try{if(await evaluate(`location.href===${JSON.stringify(url+query)} && document.readyState==='complete' && typeof show==='function'`))return;}catch{}await new Promise(resolve=>setTimeout(resolve,50));}throw Error('Page did not load');}
  async function check(expression,message){assert.equal(await evaluate(expression),true,message);}
  async function screenshot(name){const data=await cdp('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});fs.writeFileSync(path.resolve('Android_APP/prototype',name),Buffer.from(data.data,'base64'));}
  await cdp('Page.enable');await cdp('Runtime.enable');await cdp('Network.enable');
  await cdp('Emulation.setDeviceMetricsOverride',{width:440,height:900,deviceScaleFactor:1,mobile:true});
  try {
    await navigate('?demoLogin=1&demoRole=admin');
    await evaluate("localStorage.clear();apiBase='';state.csrf='';await show('forum')");
    await check("document.querySelector('#posts .error-box').textContent.includes('未配置服务器') && document.querySelector('#posts .error-box').getBoundingClientRect().height>=320",'Unconfigured forum retains its data area');
    await check("!document.body.textContent.includes('示例成员') && !document.body.textContent.includes('合成') && !document.body.textContent.includes('接口接入记录')",'No fabricated content or interface inventory');
    await evaluate("await show('account')");
    await check("!state.csrf && !document.querySelector('.admin-section') && !document.querySelector('#demo-role')",'Query parameters cannot create a session or administrator role');
    await evaluate("apiBase='https://test.invalid';capabilities=null;window.fetch=async()=>new Response('{}',{status:404});await show('forum')");
    await check("document.querySelector('#posts .error-box').textContent.includes('无API接口')",'Missing API is red');
    await check("getComputedStyle(document.querySelector('#posts .error-box')).color==='rgb(183, 35, 35)'",'Error text is red');
    await evaluate("window.fetch=async()=>new Response('{}',{status:500});capabilities=null;await show('rank')");
    await check("document.querySelector('#ranks .error-box').textContent.includes('服务器异常')",'Server failure is distinct from missing API');
    await evaluate("window.fetch=async()=>{throw new DOMException('test','AbortError')};capabilities=null;await show('forum')");
    await check("document.querySelector('#posts .error-box').textContent.includes('请求超时')",'Timeout is distinct from missing API');
    assert.equal(await evaluate("(async()=>{window.fetch=async()=>new Response('{}',{status:404});try{await request('/api/forum/posts/123')}catch(error){return failureTitle(error)}})()"),'内容不存在');
    await evaluate("window.fetch=async address=>address.includes('capabilities')?new Response('{}',{status:404}):new Response(JSON.stringify({rows:[],total:0}),{status:200});capabilities=null;await show('rank')");
    await check("!document.querySelector('#ranks .error-box') && document.getElementById('ranks').textContent.includes('暂无')",'Successful empty data is not an error');
    await evaluate("window.fetch=async()=>new Response('{}',{status:200});capabilities={public_member_ids:false};checkedAt=Date.now();await show('forum')");
    await check("document.querySelector('#posts .error-box').textContent.includes('数据格式异常')",'Malformed successful response is not displayed as empty data');
    await evaluate(`state.csrf='test';capabilities={own_public_profile:true,member_posts:true};checkedAt=Date.now();window.fetch=async address=>address.endsWith('/me/profile')?new Response(JSON.stringify({user:{name:'Contract test'},platform_counts:{codeforces:3},total_count:3})):address.includes('/me/public-profile')?new Response(JSON.stringify({motto:''})):new Response('{}',{status:404});await show('mine')`);
    await check("document.querySelector('#profile-area .stat-card strong').textContent==='3' && document.querySelector('#profile-area .error-box').textContent.includes('无API接口')",'Profile remains visible when its posts fail');
    await evaluate(`capabilities=null;window.fetch=async address=>new Response(JSON.stringify(address.includes('/auth/me')?{authenticated:true,csrf_token:'test',role:'admin'}:address.endsWith('/me/profile')?{user:{name:'Contract test'},platform_counts:{},total_count:0,recent_ac:[]}:[]),{status:address.endsWith('/mine/bookmarks')?404:200});await show('account')`);
    await check("!!document.querySelector('.admin-section') && document.querySelector('#account-area .error-box').textContent.includes('无API接口')",'Administrator identity comes from API and a failed private list has its own panel');
    await require('./feature_checks.cjs')({evaluate,check,screenshot});
    await require('./navigation_checks.cjs')({evaluate,check});
    await require('./release_checks.cjs')({evaluate,check,cdp});
    await require('./ranking_checks.cjs')({evaluate,check,cdp});
    // Remove all fixtures before writing preview images.
    await navigate();await evaluate("localStorage.clear();apiBase='';state.csrf='';await show('forum')");await screenshot('preview.png');
    await evaluate("document.getElementById('top-tools-button').click()");await screenshot('tools-preview.png');
    await evaluate("document.getElementById('close-tools').click();document.getElementById('forum-filter-button').click()");await screenshot('filter-preview.png');
    await evaluate("document.getElementById('cancel-filter').click();await show('compose')");await screenshot('compose-preview.png');
    await evaluate("await show('mine')");await screenshot('profile-preview.png');
    await evaluate("await show('account')");await screenshot('account-preview.png');
    await evaluate("await show('member')");await screenshot('member-preview.png');
    await cdp('Network.emulateNetworkConditions',{offline:true,latency:0,downloadThroughput:0,uploadThroughput:0});
    await evaluate("await show('forum')");
    await check("document.querySelector('#posts .error-box').textContent.includes('无网络') && document.querySelectorAll('.bottom button').length===5",'Offline state preserves navigation and shows no network');
    await screenshot('network-error-preview.png');
    await cdp('Network.emulateNetworkConditions',{offline:false,latency:0,downloadThroughput:-1,uploadThroughput:-1});
    const readerUrl=pathToFileURL(path.resolve('Android_APP/app/app/src/main/assets/reader/index.html')).href;
    await cdp('Page.navigate',{url:readerUrl});
    for(let n=0;n<80;n++){if(await evaluate("typeof renderContent==='function'"))break;await new Promise(resolve=>setTimeout(resolve,50));}
    await evaluate("renderContent('# Reader heading\\n\\n**Safe body**\\n\\n$$x^2$$','markdown')");
    await check("document.querySelector('#article h1').textContent==='Reader heading' && !!document.querySelector('#article strong') && !!document.querySelector('#article math')",'Packaged local reader loads scripts under CSP and renders Markdown/math');
    await require('./admin_checks.cjs')({evaluate,check,cdp,screenshot});
    assert.equal(exceptions.length,0,'No browser exceptions');
    console.log('UI checks passed: login waiting, session confirmation, duplicate submits, draft serialization, safe content, API errors and role integrity; 9 previews refreshed.');
  } finally {await cdp('Browser.close');socket.close();}
})().catch(error=>{console.error(error);process.exit(1);});
