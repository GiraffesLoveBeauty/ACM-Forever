export async function enter(ctx){
  const {root,$,api,esc}=ctx;
  root.innerHTML='<section class="admin-panel"><form class="filters" id="task-filters"><label>成员身份<select id="task-member-status"><option value="">全部身份</option><option value="__empty__">未设置身份</option></select></label><button class="btn primary">刷新任务</button><a class="btn" href="/admin.html?section=problems">拉取题目</a><span class="muted">离开此模块停止刷新，后台任务继续执行。</span></form><div id="luogu-restricted"></div><p id="tasks-message" role="status"></p><div id="tasks-list" class="list"></div></section>';
  const statusSelect=$('#task-member-status');
  let status='';
  function describe(result){
    if(result==null)return '';
    if(typeof result==='object')return Object.entries(result).map(([key,value])=>key+'：'+describe(value)).join('；');
    if(typeof result==='number')return result>=0?'新增 '+result+' 条':({[-1]:'成员不存在或抓取失败',[-2]:'未绑定账号',[-3]:'抓取失败',[-5]:'已暂停，保留已有记录',[-6]:'洛谷访问受限，已停用，等待管理员重新开启'})[result]||'同步失败';
    return String(result);
  }
  function matches(value){return status==='__empty__'?!String(value||'').trim():value===status}
  function visibleResult(task){
    if(!status||task.qq_id!=='*'||!task.member_statuses||!task.result||typeof task.result!=='object')return task.result;
    const result=Object.fromEntries(Object.entries(task.result).filter(([qq])=>qq==='error'||matches(task.member_statuses[qq])));
    return Object.keys(result).length?result:null;
  }
  async function loadOptions(){
    try{const options=await api('/admin/members/options');for(const value of options.statuses||[]){if(![...statusSelect.options].some(option=>option.value===value)){const option=document.createElement('option');option.value=value;option.textContent=value;statusSelect.append(option)}}}
    catch(error){if(error.name!=='AbortError')statusSelect.innerHTML='<option value="">全部身份</option><option value="__empty__">未设置身份</option>'}
  }
  async function load(){
    const [rows,restricted]=await Promise.all([api('/tasks'),api('/admin/luogu-sync').catch(()=>[])]);
    const filtered=rows.slice().reverse().filter(task=>!status||(task.member&&matches(task.member.status)||task.member_statuses&&Object.values(task.member_statuses).some(matches)));
    $('#luogu-restricted').innerHTML=restricted.filter(row=>!status||matches(row.status)).map(row=>`<article class="list-item"><span><b>洛谷访问受限</b><br><small class="muted">${esc(row.name)} · QQ ${esc(row.qq_id)} · 身份 ${esc(row.status||'未设置')} · UID ${esc(row.luogu_id)}</small></span><button class="btn" data-enable-luogu="${esc(row.qq_id)}">重新开启</button></article>`).join('');
    const time=value=>value?new Date(value*1000).toLocaleString():'尚未开始';
    $('#tasks-list').innerHTML=filtered.map(task=>{
      const problem=task.kind==='题目采集', result=visibleResult(task);
      const taskStatus=problem?({queued:'等待拉取',running:'正在拉取',completed:'拉取完成',partial:'部分题目拉取失败',failed:'拉取失败',cancelled:'已取消'}[task.status]||task.status):task.status;
      return `<article class="list-item"><span><b>${esc(task.kind)} · #${esc(task.id)}</b><br><small>${problem?'':'成员 '+esc(task.qq_id||'全部')+' · '}平台 ${esc(task.platform||'全部')} · ${esc(taskStatus)}</small><br><small class="muted">${esc(problem?'':describe(result))} · ${esc(time(task.finished_at||task.started_at))}</small></span>${['queued','running'].includes(task.status)?`<button class="btn" data-cancel="${esc(task.id)}">取消任务</button>`:''}</article>`;
    }).join('')||'<p class="empty">暂无符合条件的同步任务。</p>';
  }
  statusSelect.onchange=()=>{status=statusSelect.value;load().catch(error=>{if(error.name!=='AbortError')$('#tasks-message').textContent=error.message})};
  $('#task-filters').onsubmit=event=>{event.preventDefault();load().catch(error=>{if(error.name!=='AbortError')$('#tasks-message').textContent=error.message})};
  ctx.on(root,'click',async event=>{const cancel=event.target.closest('[data-cancel]'),enable=event.target.closest('[data-enable-luogu]');try{if(cancel){await api('/tasks/'+encodeURIComponent(cancel.dataset.cancel)+'/cancel',{method:'POST'})}else if(enable){await api('/admin/luogu-sync/'+encodeURIComponent(enable.dataset.enableLuogu)+'/enable',{method:'POST'})}else return;await load()}catch(error){if(error.name!=='AbortError')ctx.notice(error.message)}});
  async function poll(){await load();if(!ctx.signal.aborted)ctx.setTimeout(poll,5000)}
  await loadOptions();await poll();return {};
}
