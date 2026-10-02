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
    ['/leaderboard','/me/leaderboard'],
    ['/challenge/list','/me/training/challenges'],
    ['/challenge/start','/me/challenge/start'],
    ['/challenge/rating','/me/challenge/rating'],
    ['/workspace/items','/me/workspace/items'],
    ['/problems','/me/problems'],
    ['/submissions/attempts','/me/submissions/attempts'],
    ['/submissions/analytics','/me/submissions/analytics'],
    ['/reviews/drafts','/me/reviews/drafts'],
    ['/review/queue','/me/reviews'],
    ['/review/feedback','/me/reviews/feedback'],
    ['/training/weak-tags','/me/reviews/weak-tags'],
    ['/training/summary','/me/training/summary'],
    ['/contest/reviews','/me/contest/reviews'],
    ['/study-plan','/me/study-plan']
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
  const controller=new AbortController();
  const timer=setTimeout(()=>controller.abort(),requestTimeoutMs);
  try{
    const response=await fetch('/api'+path,{credentials:'same-origin',...fetchOptions,signal:controller.signal,headers:{'Content-Type':'application/json','X-CSRF-Token':csrf,...(fetchOptions.headers||{})}});
    const data=await response.json().catch(()=>({}));
    if(response.status===401&&!path.startsWith('/auth/login')){location.href='/index.html';throw Error('请先登录')}
    if(response.status===428){location.href='/change-password.html';throw Error('请先修改初始密码')}
    if(!response.ok)throw Error(data.message||data.error||`HTTP ${response.status}`);
    return data;
  }finally{clearTimeout(timer)}
}

function navItems(){
  const common=[['home','⌂ 我的首页','/home.html'],['leaderboard','♛ 排行榜','/leaderboard.html'],['challenge','◎ 今日训练','/challenge.html'],['reviews','✓ 待复盘','/reviews.html'],['problem-bank','▦ 题库','/problem-bank.html'],['submissions','◷ 提交时间线','/submissions.html'],['workspace','✎ 笔记与计划','/workspace.html'],['contest-review','◈ 赛事复盘','/contest-review.html']];
  if(AUTH.role==='member')return common;
  return [...common,['admin','⚙ 管理后台','/admin.html']];
}

async function renderNav(){
  const items=navItems();
  let order=items.map(item=>item[0]),hidden=new Set();
  if(AUTH.role==='admin'||AUTH.role==='root'){
    try{const preferences=await api('/ui/preferences');if(Array.isArray(preferences.nav_order)&&preferences.nav_order.length)order=preferences.nav_order;hidden=new Set(Array.isArray(preferences.nav_hidden)?preferences.nav_hidden:[]);if(preferences.font_scale)document.documentElement.style.setProperty('--font-scale',preferences.font_scale)}catch{}
    if(!order.includes('admin'))order.push('admin');
  }
  const byId=new Map(items.map(item=>[item[0],item]));
  document.querySelectorAll('.nav').forEach(nav=>{nav.innerHTML=order.map(id=>byId.get(id)).filter(item=>item&&!hidden.has(item[0])).map(item=>`<a class="${location.pathname.endsWith(item[2])?'active':''}" href="${item[2]}">${item[1]}</a>`).join('')});
}

function lockOwnerInputs(){
  if(AUTH.role!=='member'||!AUTH.qq_id)return;
  document.querySelectorAll('#owner').forEach(input=>{input.value=AUTH.qq_id;input.readOnly=true;input.setAttribute('aria-hidden','true');input.style.display='none'});
  document.querySelectorAll('[data-owner-qq]').forEach(input=>{input.value=AUTH.qq_id;input.readOnly=true;input.style.display='none'});
}

function showLogin(){const box=$('#login');if(box)box.style.display='grid'}
function toggleTheme(){const theme=document.body.dataset.theme==='dark'?'light':'dark';document.body.dataset.theme=theme;localStorage.theme=theme}
async function login(event){
  event.preventDefault();
  const identifier=$('#username').value.trim(),password=$('#password').value;
  try{
    const data=await api('/auth/login',{method:'POST',body:JSON.stringify({qq_id:/^\d{4,12}$/.test(identifier)?identifier:'',username:identifier,password})});
    csrf=data.csrf_token||'';
    location.href=data.must_change_password?'/change-password.html':(['admin','root'].includes(data.role)?'/admin.html':'/home.html');
  }catch(error){const message=$('#login-message');if(message)message.textContent=error.message}
}
async function logout(){try{await api('/auth/logout',{method:'POST'})}catch{}location.href='/index.html'}

async function init(){
  try{const response=await fetch('/api/auth/me',{credentials:'same-origin'});AUTH=await response.json();}catch{AUTH={authenticated:false}}
  window.AUTH=AUTH;
  if(!AUTH.authenticated){showLogin();return}
  csrf=AUTH.csrf_token||'';
  document.body.dataset.theme=localStorage.theme||'light';
  const page=location.pathname.split('/').pop()||'index.html';
  if(AUTH.must_change_password&&page!=='change-password.html'){location.replace('/change-password.html');return}
  if(page==='index.html'){
    location.replace(['admin','root'].includes(AUTH.role)?'/admin.html':'/home.html');return;
  }
  if(page==='change-password.html')return;
  await renderNav();lockOwnerInputs();
  const requestedMember=new URLSearchParams(location.search).get('qq_id');
  if(typeof window.PAGE_LOAD==='function')await window.PAGE_LOAD(AUTH.role==='member'?undefined:requestedMember);
}

document.addEventListener('DOMContentLoaded',()=>{
  const form=$('#login-form');if(form)form.addEventListener('submit',login);
  const theme=$('#theme-toggle');if(theme)theme.onclick=toggleTheme;
  const exit=$('#logout');if(exit)exit.onclick=logout;
  init();
});
window.api=api;window.esc=esc;window.AUTH=AUTH;
