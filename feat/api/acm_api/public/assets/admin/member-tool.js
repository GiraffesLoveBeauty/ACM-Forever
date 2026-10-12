import {context} from './common.js';
window.PAGE_LOAD=async()=>{
  const name=document.body.dataset.memberTool;
  if(!['training','problems','contests'].includes(name))return;
  const root=document.getElementById('member-tool');
  const ctx=context(root,new URLSearchParams(location.search),{},{notice:text=>{document.getElementById('tool-message').textContent=text},updateParams:()=>{}});
  let module;
  window.addEventListener('pagehide',()=>{module?.exit?.();ctx.dispose()},{once:true});
  try{module=await (await import('./'+name+'.js?v=unified-admin-1')).enter(ctx)}catch(error){if(error.name!=='AbortError')ctx.notice(error.message)}
};
