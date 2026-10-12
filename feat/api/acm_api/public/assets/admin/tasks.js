export async function enter(ctx){
  const {root,$,api,esc}=ctx;
  root.innerHTML='<section class="admin-panel"><div class="filters"><button class="btn primary" id="refresh-tasks">刷新任务</button><span class="muted">离开此模块停止刷新，后台任务继续执行。</span></div><p id="tasks-message" role="status"></p><div id="tasks-list" class="list"></div></section>';
  async function load(){
    const rows=await api('/tasks');
    const describe=result=>result==null?'':typeof result==='object'?Object.entries(result).map(([key,value])=>key+'：'+describe(value)).join('；'):typeof result==='number'?(result>=0?'新增 '+result+' 条':({[-1]:'成员不存在',[-2]:'未绑定账号',[-3]:'抓取失败'})[result]||'同步失败'):String(result);
    const time=value=>value?new Date(value*1000).toLocaleString():'尚未开始';
    $('#tasks-list').innerHTML=rows.slice().reverse().map(task=>`<article class="list-item"><span><b>${esc(task.kind)} · #${esc(task.id)}</b><br><small>成员 ${esc(task.qq_id||'全部')} · 平台 ${esc(task.platform||'全部')} · ${esc(task.status)}</small><br><small class="muted">${esc(describe(task.result))} · ${esc(time(task.finished_at||task.started_at))}</small></span>${['queued','running'].includes(task.status)?`<button class="btn" data-cancel="${esc(task.id)}">取消任务</button>`:''}</article>`).join('')||'<p class="empty">暂无同步任务。</p>';
  }
  const refresh=()=>load().catch(error=>{if(error.name!=='AbortError')$('#tasks-message').textContent=error.message});
  $('#refresh-tasks').onclick=refresh;
  ctx.on(root,'click',async event=>{const button=event.target.closest('[data-cancel]');if(!button)return;try{await api('/tasks/'+encodeURIComponent(button.dataset.cancel)+'/cancel',{method:'POST'});await load()}catch(error){if(error.name!=='AbortError')ctx.notice(error.message)}});
  async function poll(){await refresh();if(!ctx.signal.aborted)ctx.setTimeout(poll,5000)}
  await poll();return {};
}
