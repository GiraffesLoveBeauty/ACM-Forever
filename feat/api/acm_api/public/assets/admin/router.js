import {context} from './common.js';

const modules={accounts:['成员账号','发放社区账号，维护登录权限。'],members:['成员资料','搜索成员，维护个人资料和 OJ 绑定。'],training:['训练管理','为成员选择平台和难度，生成训练并查看挑战历史。'],problems:['题库管理','拉取公开比赛题目，查询、筛选和收藏题库。'],'cf-practice':['CF 练习赛选题','近期刷题、候选查重和成员证据。'],contests:['赛事复盘','查看比赛题目，维护逐题状态。'],tasks:['同步任务','查看执行进度、失败信息和同步队列。'],moderation:['内容审核','审核社区话题并处理举报。'],settings:['全局设置','外观、比赛播报和 QQBot 管理员配置。']};
const memories=new Map();let active=null,sequence=0;
const notice=text=>{document.getElementById('admin-notice').textContent=text||''};
function route(url){
  const params=new URL(url,location.origin).searchParams;let section=params.get('section')||'accounts',warning='';
  if(!Object.hasOwn(modules,section)){warning='未知的后台模块，已返回成员账号。';section='accounts';params.delete('section');params.delete('tab');params.delete('qq_id')}
  const allowed=section==='cf-practice'?['recent','check']:section==='moderation'?['posts','reports']:null;
  if(params.has('tab')&&(!allowed||!allowed.includes(params.get('tab')))){params.delete('tab');warning='无效的分区参数，已打开默认分区。'}
  if(params.has('qq_id')&&!/^\d{4,12}$/.test(params.get('qq_id'))){params.delete('qq_id');warning='无效的成员 QQ 参数，已返回列表。'}
  return {section,params,warning,url:'/admin.html'+(params.size?'?'+params.toString():'')};
}
function chrome(section,params){
  const [title,lede]=modules[section],detail=section==='members'&&params.has('qq_id');
  document.title=(detail?'成员详情':title)+' · ACM Forever 管理后台';
  document.getElementById('admin-title').textContent=detail?'成员详情':title;
  document.getElementById('admin-lede').textContent=lede;
  document.getElementById('admin-breadcrumb').textContent='管理后台 / '+title+(detail?' / '+params.get('qq_id'):'');
  document.getElementById('admin-password').href='/change-password.html?next='+encodeURIComponent(location.pathname+location.search);
  document.querySelectorAll('[data-section]').forEach(link=>{const selected=link.dataset.section===section;link.classList.toggle('active',selected);if(selected)link.setAttribute('aria-current','page');else link.removeAttribute('aria-current')});
}
async function open(url,{replace=false,pop=false}={}){
  const target=route(url);
  if(active?.beforeLeave&&await active.beforeLeave()===false){if(pop)history.pushState({},'',active.url);return;}
  const version=++sequence;
  active?.exit?.();active?.ctx.dispose();
  if(!pop)history[replace?'replaceState':'pushState']({},'',target.url);
  else if(location.pathname+location.search!==target.url)history.replaceState({},'',target.url);
  chrome(target.section,target.params);notice(target.warning);
  const root=document.createElement('div');root.className='admin-module';
  if(target.section==='cf-practice')root.classList.add('cf-main','cf-practice-page');
  root.innerHTML='<div class="empty" role="status">正在加载模块…</div>';
  document.getElementById('admin-content').replaceChildren(root);
  const memory=memories.get(target.section)||{};memories.set(target.section,memory);
  const ctx=context(root,target.params,memory,{notice,navigate:(changes)=>{
    const params=new URLSearchParams(target.params);for(const [key,value] of Object.entries(changes)){if(value==null)params.delete(key);else params.set(key,String(value))}return open('/admin.html'+(params.size?'?'+params:''));
  },updateParams:(changes,{replace=false}={})=>{
    if(version!==sequence)return;
    for(const [key,value] of Object.entries(changes)){if(value==null)target.params.delete(key);else target.params.set(key,String(value))}
    const next='/admin.html'+(target.params.size?'?'+target.params:'');
    if(next!==location.pathname+location.search)history[replace?'replaceState':'pushState']({},'',next);
    active.url=next;chrome(target.section,target.params);
  }});
  active={ctx,url:target.url,exit:()=>ctx.cleanup?.(),beforeLeave:()=>ctx.beforeLeave?.()??true};
  try{
    const module=await import('./'+target.section+'.js?v=unified-admin-4');
    if(version!==sequence)return;
    const lifecycle=await module.enter(ctx);
    if(version!==sequence){ctx.dispose();return;}
    Object.assign(active,lifecycle||{});
  }catch(error){if(version===sequence&&error.name!=='AbortError'){root.innerHTML='<p class="empty">模块加载失败，请刷新重试。</p>';notice(error.message)}}
}
window.PAGE_LOAD=async()=>{
  if(!['admin','root'].includes(window.AUTH.role))return;
  document.querySelector('.admin-nav').addEventListener('click',event=>{const link=event.target.closest('a[data-section]');if(!link||event.ctrlKey||event.metaKey||event.shiftKey||event.button!==0)return;event.preventDefault();open(link.href)});
  window.addEventListener('popstate',()=>open(location.href,{pop:true}));
  window.addEventListener('pagehide',()=>{active?.exit?.();active?.ctx.dispose()});
  await open(location.href,{replace:true});
};
