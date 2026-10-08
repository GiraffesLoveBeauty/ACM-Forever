const states={todo:'待处理',unsolved:'未通过',queued:'待补题',solved:'已解决',reviewed:'已复盘',ignored:'忽略'};
export async function enter(ctx){
  const {root,$,api,esc,auth}=ctx;let version=0;
  root.innerHTML=`<section class="admin-panel"><form class="filters" id="contest-filters"><label id="contest-owner-label">成员 QQ<input id="owner" value="${esc(ctx.params.get('qq_id')||auth.qq_id||'')}" inputmode="numeric"></label><label>比赛 ID<input id="contest" value="${esc(ctx.params.get('contest_id')||'')}"></label><button class="btn primary">查询比赛题目</button></form><p id="contest-message" role="status"></p><div id="contest-list" class="list"><p class="empty">请输入比赛 ID。</p></div></section>`;
  if(auth.role==='member'){$('#owner').value=auth.qq_id;$('#contest-owner-label').hidden=true;}
  async function load(){const owner=$('#owner').value.trim(),contest=$('#contest').value.trim();if(!owner||!contest)return;const current=++version;
    const rows=await api('/contest/reviews?'+new URLSearchParams({owner_qq_id:owner,contest_id:contest}));if(current!==version)return;
    $('#contest-list').innerHTML=rows.map(row=>`<article class="list-item"><span><b>${esc(row.problem_id)}</b><br><small>${esc(row.verdict||'未记录结果')} · 难度 ${esc(row.rating??'未知')}</small></span><label>逐题状态<select data-contest-status data-owner="${esc(owner)}" data-contest="${esc(contest)}" data-problem="${esc(row.problem_id)}">${Object.entries(states).map(([value,label])=>`<option value="${value}" ${value===row.status?'selected':''}>${label}</option>`).join('')}</select></label></article>`).join('')||'<p class="empty">该比赛暂无题目记录，请先同步提交数据。</p>';
  }
  ctx.on($('#contest-filters'),'submit',event=>{event.preventDefault();load().catch(error=>{if(error.name!=='AbortError')ctx.notice(error.message)})});
  ctx.on(root,'change',async event=>{const input=event.target.closest('[data-contest-status]');if(!input)return;
    try{await api('/contest/reviews',{method:'PUT',body:JSON.stringify({owner_qq_id:input.dataset.owner,contest_id:input.dataset.contest,problem_id:input.dataset.problem,status:input.value})});$('#contest-message').textContent='逐题状态已保存。'}catch(error){if(error.name!=='AbortError')$('#contest-message').textContent=error.message}
  });
  await load();return {};
}
