export async function enter(ctx){
  const {root,$,api,esc,auth}=ctx;let page=1,version=0;
  root.innerHTML=`<section class="admin-panel"><form id="problem-filters" class="filters"><label id="problem-owner-label">成员 QQ<input id="owner" value="${esc(ctx.params.get('qq_id')||auth.qq_id||'')}" inputmode="numeric"></label><label>平台<select id="platform"><option value="">全部平台</option><option value="codeforces">Codeforces</option><option value="luogu">洛谷</option><option value="atcoder">AtCoder</option><option value="nowcoder">牛客</option></select></label><label>搜索<input id="query" placeholder="题号、题名或标签"></label><label>收藏<select id="state"><option value="">全部题目</option><option value="favorite">已收藏</option></select></label><button class="btn primary">筛选题目</button></form><p id="problem-count" class="muted" role="status"></p><div id="problem-list" class="list"></div><div class="admin-pagination"><button class="btn" id="problem-prev">上一页</button><span id="problem-page"></span><button class="btn" id="problem-next">下一页</button></div></section>`;
  if(auth.role==='member'){$('#owner').value=auth.qq_id;$('#problem-owner-label').hidden=true;}
  async function load(){const current=++version,owner=$('#owner').value.trim();
    const data=await api('/problems?'+new URLSearchParams({owner_qq_id:owner,platform:$('#platform').value,tag:$('#query').value,state:$('#state').value,page,page_size:20}));
    if(current!==version)return;
    const items=Array.isArray(data)?data:data.items;
    $('#problem-count').textContent=`共 ${data.total??items.length} 道题目 · 数据来自本地同步库`;
    $('#problem-page').textContent=`第 ${page} / ${Math.max(1,Math.ceil((data.total??items.length)/20))} 页`;
    $('#problem-prev').disabled=page<=1;$('#problem-next').disabled=page*20>=(data.total??items.length);
    $('#problem-list').innerHTML=items.map(row=>`<article class="list-item"><span><b>${esc(row.platform)} · ${esc(row.problem_id)}</b><br>${esc(row.problem_name||'未命名题目')}<br><small class="muted">难度 ${esc(row.problem_rating||'未知')} · ${esc(row.tags||'无标签')}</small></span><span class="chips"><button class="btn" data-favorite="${row.is_favorite?0:1}" data-platform="${esc(row.platform)}" data-problem="${esc(row.problem_id)}" data-owner="${esc(owner)}">${row.is_favorite?'取消收藏':'收藏'}</button><a class="btn" href="${esc(row.problem_url)}" target="_blank" rel="noopener">打开题目</a></span></article>`).join('')||'<p class="empty">没有匹配题目，请调整筛选或同步数据。</p>';
  }
  const run=()=>load().catch(error=>{if(error.name!=='AbortError')ctx.notice(error.message)});
  ctx.on($('#problem-filters'),'submit',event=>{event.preventDefault();page=1;run()});
  $('#problem-prev').onclick=()=>{page--;run()};$('#problem-next').onclick=()=>{page++;run()};
  ctx.on(root,'click',async event=>{const button=event.target.closest('[data-favorite]');if(!button)return;
    if(!/^\d{4,12}$/.test(button.dataset.owner)){ctx.notice('请填写成员 QQ 后保存收藏。');return;}
    try{await api('/problems/'+encodeURIComponent(button.dataset.platform)+'/'+encodeURIComponent(button.dataset.problem)+'/state',{method:'PUT',body:JSON.stringify({owner_qq_id:button.dataset.owner,is_favorite:button.dataset.favorite==='1'})});await load()}catch(error){if(error.name!=='AbortError')ctx.notice(error.message)}
  });
  await load();return {};
}
