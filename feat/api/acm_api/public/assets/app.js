const $=selector=>document.querySelector(selector);
const esc=value=>String(value??'').replace(/[&<>'"]/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
let csrf='';
let AUTH={authenticated:false,role:null,qq_id:null,must_change_password:false};

function mapMemberRequest(path,opt={}){
  if(!AUTH.authenticated||AUTH.role!=='member')return {path,opt};
  const [pathname,query='']=path.split('?',2);
  const params=new URLSearchParams(query);
  params.delete('owner_qq_id');params.delete('qq_id');
  const routes=[
    ['/challenge/list','/me/training/challenges'],
    ['/challenge/start','/me/challenge/start'],
    ['/challenge/rating','/me/challenge/rating'],
    ['/problems','/me/problems'],
    ['/training/weak-tags','/me/reviews/weak-tags'],
    ['/training/summary','/me/training/summary'],
    ['/contest/reviews','/me/contest/reviews']
  ];
  let mapped=pathname;
  for(const [from,to] of routes){
    if(pathname===from||pathname.startsWith(from+'/')){mapped=to+pathname.slice(from.length);break}
  }
  let body=opt.body;
  if(typeof body==='string'){
    try{const data=JSON.parse(body);if(data&&typeof data==='object'&&!Array.isArray(data)){delete data.qq_id;delete data.owner_qq_id;body=JSON.stringify(data)}}catch{}
  }
  const suffix=params.toString();
  return {path:mapped+(suffix?'?'+suffix:''),opt:{...opt,body}};
}

async function api(path,opt={}){
  ({path,opt}=mapMemberRequest(path,opt));
  const requestTimeoutMs=Number(opt.timeoutMs)||15000;
  const {timeoutMs,...fetchOptions}=opt;
  const externalSignal=fetchOptions.signal;
  const controller=fetchOptions.keepalive?null:new AbortController();
  const abort=()=>controller?.abort();
  if(controller&&externalSignal?.aborted)abort();
  else if(controller)externalSignal?.addEventListener('abort',abort,{once:true});
  const timer=controller?setTimeout(()=>controller.abort(),requestTimeoutMs):null;
  try{
    const isMultipart=typeof FormData!=='undefined'&&fetchOptions.body instanceof FormData;
    const requestHeaders={...(isMultipart?{}:{'Content-Type':'application/json'}),'X-CSRF-Token':csrf,...(fetchOptions.headers||{})};
    const response=await fetch('/api'+path,{credentials:'same-origin',...fetchOptions,...(controller?{signal:controller.signal}:{}),headers:requestHeaders});
    const data=await response.json().catch(()=>({}));
    if(response.status===401&&!path.startsWith('/auth/login')){location.href='/login.html?next='+encodeURIComponent(location.pathname+location.search);throw Error('请先登录')}
    if(response.status===428){location.href='/change-password.html?next='+encodeURIComponent(location.pathname+location.search);throw Error('请先修改初始密码')}
    if(!response.ok){const error=Error(data.message||data.error||`HTTP ${response.status}`);error.status=response.status;error.code=data.code||data.error_code||null;error.details=data;throw error}
    return data;
  }finally{if(timer)clearTimeout(timer);if(controller)externalSignal?.removeEventListener('abort',abort)}
}

function canManage(){return AUTH.authenticated&&['admin','root'].includes(AUTH.role)}

function navItems(){
  const common=[['forum','⌂ 论坛','/index.html'],['leaderboard','♛ 排行榜','/leaderboard.html'],['home','◉ 个人中心','/home.html']];
  if(!AUTH.authenticated)return [...common.slice(0,2),['login','登录','/login.html']];
  if(!canManage())return common;
  return [...common,['admin','⚙ 管理后台','/admin.html']];
}

async function renderNav(){
  const items=navItems();
  let order=items.map(item=>item[0]),hidden=new Set();
  if(canManage()){
    try{const preferences=await api('/ui/preferences');if(preferences.font_scale)document.documentElement.style.setProperty('--font-scale',preferences.font_scale)}catch{}
    if(!order.includes('admin'))order.push('admin');
  }
  const byId=new Map(items.map(item=>[item[0],item]));
  const primary=['forum','leaderboard','home'];
  document.querySelectorAll('.nav').forEach(nav=>{
    const visibleOrder=nav.classList.contains('primary-nav')?primary:order;
    const core=['forum','leaderboard','home'];
    const ids=nav.classList.contains('primary-nav')?visibleOrder:core.concat(visibleOrder.filter(id=>!core.includes(id)));
    nav.innerHTML=ids.map(id=>byId.get(id)).filter(item=>item&&(!hidden.has(item[0])||core.includes(item[0]))).map(item=>{
      const active=item[0]==='forum'?(location.pathname==='/'||location.pathname.endsWith('/index.html')):location.pathname.endsWith(item[2]);
      return `<a class="${active?'active':''}" href="${item[2]}">${item[1]}</a>`
    }).join('')
  });
}

function mountHeaderAvatar(){
  if(!AUTH.authenticated)return;
  const actions=document.querySelector('.forum-header-actions');
  if(!actions)return;
  let link=$('#login-link');
  if(!link){
    link=document.createElement('a');
    link.id='login-link';
    link.className='btn';
    const logout=$('#logout');
    actions.insertBefore(link,logout||null);
  }
  link.href=AUTH.role==='member'?'/home.html':'/admin.html';
  const label=AUTH.role==='member'?'个人中心':'管理中心';
  link.classList.add('account-avatar-button');
  link.setAttribute('aria-label',label);
  link.title=label;
  link.innerHTML=avatarMarkup(AUTH.avatar_url,label,'header-account-avatar');
}

function setAccountAvatar(url){
  const source=typeof url==='string'&&/^\/uploads\/avatars\/[a-f0-9]{32}\.(?:png|jpg|webp)$/.test(url)?url:null;
  AUTH.avatar_url=source;
  const label=AUTH.role==='member'?'个人中心':'管理中心';
  document.querySelectorAll('.header-account-avatar').forEach(image=>{
    image.src=source||'/assets/default-avatar.png';
    image.alt=`${label} 的头像`;
  });
}

function lockOwnerInputs(){
  if(AUTH.role!=='member'||!AUTH.qq_id)return;
  document.querySelectorAll('#owner').forEach(input=>{input.value=AUTH.qq_id;input.readOnly=true;input.setAttribute('aria-hidden','true');input.style.display='none'});
  document.querySelectorAll('[data-owner-qq]').forEach(input=>{input.value=AUTH.qq_id;input.readOnly=true;input.style.display='none'});
}

function showLogin(){const box=$('#login');if(box)box.style.display='grid'}
function avatarMarkup(url,name,classes=''){
  const source=typeof url==='string'&&/^\/uploads\/avatars\/[a-f0-9]{32}\.(?:png|jpg|webp)$/.test(url)?url:'/assets/default-avatar.png';
  return `<img class="user-avatar ${classes}" src="${source}" alt="${esc(name||'计量 ACMer')} 的头像" loading="lazy" onerror="this.onerror=null;this.src='/assets/default-avatar.png'">`;
}
function mountPalettePicker(){window.ACMTheme?.init()}
function toggleTheme(){window.ACMTheme?.toggle()}
function animateNumbers(root=document){
  if(window.matchMedia?.('(prefers-reduced-motion: reduce)').matches)return;
  root.querySelectorAll('.profile-stat-card .value,.rank-total').forEach((node,index)=>{
    const target=Number(node.textContent.replaceAll(',','').trim());
    if(!Number.isFinite(target)||target<0)return;
    const format=new Intl.NumberFormat('zh-CN');
    node.setAttribute('aria-label',format.format(target));
    if(target===0||index>=10){node.textContent=format.format(target);return}
    node.classList.add('is-counting');
    const start=performance.now()+index*38;
    const duration=680;
    const frame=now=>{
      const progress=Math.max(0,Math.min(1,(now-start)/duration));
      const eased=1-Math.pow(1-progress,3);
      node.textContent=format.format(Math.round(target*eased));
      if(progress<1)requestAnimationFrame(frame);
      else node.classList.remove('is-counting');
    };
    requestAnimationFrame(frame);
  });
}
async function login(event){
  event.preventDefault();
  const identifier=$('#username').value.trim(),password=$('#password').value;
  try{
    const data=await api('/auth/login',{method:'POST',body:JSON.stringify({qq_id:/^\d{4,12}$/.test(identifier)?identifier:'',username:identifier,password})});
    csrf=data.csrf_token||'';
    const next=new URLSearchParams(location.search).get('next')||'/index.html';
    const safeNext=localNext(next,'/index.html');
    location.href=data.must_change_password?'/change-password.html?next='+encodeURIComponent(safeNext):safeNext;
  }catch(error){const message=$('#login-message');if(message)message.textContent=error.message}
}
async function logout(){try{await api('/auth/logout',{method:'POST'})}catch{}location.href='/index.html'}

async function init(){
  try{
    if(!window.ACMTheme)await new Promise((resolve,reject)=>{
      const script=document.createElement('script');
      script.src='/assets/theme-editor.js?v=industrial-theme-4';
      script.onload=resolve;script.onerror=reject;document.head.append(script);
    });
    mountPalettePicker();
  }catch(error){console.error('自助调色加载失败',error)}
  try{const response=await fetch('/api/auth/me',{credentials:'same-origin'});AUTH=await response.json();}catch{AUTH={authenticated:false}}
  window.AUTH=AUTH;
  const page=location.pathname.split('/').pop()||'index.html';
  if(!AUTH.authenticated){
    if(['index.html','post.html','leaderboard.html','login.html'].includes(page)){
      if(page==='login.html')return;
      await renderNav();
      if(typeof window.PAGE_LOAD==='function')await window.PAGE_LOAD();
      return;
    }
    location.replace('/login.html?next='+encodeURIComponent(location.pathname+location.search));return;
  }
  csrf=AUTH.csrf_token||'';
  if(AUTH.must_change_password&&page!=='change-password.html'){const target=page==='login.html'?localNext(new URLSearchParams(location.search).get('next'),'/home.html'):location.pathname+location.search;location.replace('/change-password.html?next='+encodeURIComponent(target));return}
  if(page==='login.html'){location.replace(localNext(new URLSearchParams(location.search).get('next'),'/index.html'));return}
  if(page==='change-password.html')return;
  await renderNav();lockOwnerInputs();
  const requestedMember=new URLSearchParams(location.search).get('qq_id');
  const pageLoad=typeof window.PAGE_LOAD==='function'?window.PAGE_LOAD(AUTH.role==='member'?undefined:requestedMember):null;
  if(document.querySelector('.forum-header-actions'))mountHeaderAvatar();
  if(pageLoad)await pageLoad;
  if(document.querySelector('.profile-stat-card'))animateNumbers(document);
}

document.addEventListener('DOMContentLoaded',()=>{
  const form=$('#login-form');if(form)form.addEventListener('submit',login);
  const theme=$('#theme-toggle');if(theme)theme.onclick=toggleTheme;
  const exit=$('#logout');if(exit)exit.onclick=logout;
  init();
});
function localNext(value,fallback='/home.html'){return typeof value==='string'&&value.startsWith('/')&&!value.startsWith('//')&&!/[\\\x00-\x1f]/.test(value)&&new URL(value,location.origin).origin===location.origin?value:fallback}
window.api=api;window.esc=esc;window.AUTH=AUTH;window.avatarMarkup=avatarMarkup;window.setAccountAvatar=setAccountAvatar;window.animateNumbers=animateNumbers;window.localNext=localNext;
