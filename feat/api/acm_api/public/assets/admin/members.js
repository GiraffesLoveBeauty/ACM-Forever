const fields=[['name','昵称'],['real_name','真实姓名'],['school','学校'],['status','身份 / 年级'],['cf_handle','Codeforces'],['luogu_id','洛谷'],['nowcoder_id','牛客'],['atcoder_handle','AtCoder'],['cjlu_username','校 OJ']];
export async function enter(ctx){
  const {root,$,api,esc,params}=ctx,qq=params.get('qq_id');
  const listParams=new URLSearchParams(params);listParams.delete('qq_id');
  if(!qq){
    root.innerHTML=`<section class="admin-panel"><form id="member-search-form" class="filters"><label>搜索成员<input id="member-search" type="search" value="${esc(params.get('search')||'')}" placeholder="QQ、昵称、身份、学校或 OJ 账号"></label><button class="btn primary">搜索</button></form><p id="member-summary" class="muted" role="status">正在读取成员…</p><div class="table-wrap" id="member-list"></div><div class="admin-pagination"><button class="btn" id="member-prev">上一页</button><span id="member-page"></span><button class="btn" id="member-next">下一页</button></div></section>`;
    const page=Math.max(1,Number(params.get('page'))||1);
    ctx.on($('#member-search-form'),'submit',event=>{event.preventDefault();ctx.navigate({search:$('#member-search').value.trim(),page:1})});
    $('#member-prev').onclick=()=>ctx.navigate({page:page-1});$('#member-next').onclick=()=>ctx.navigate({page:page+1});
    const data=await api('/admin/members?'+new URLSearchParams({search:params.get('search')||'',page,page_size:20}));
    $('#member-summary').textContent=`共 ${data.total} 位成员`;
    $('#member-page').textContent=`第 ${data.page} / ${Math.max(1,Math.ceil(data.total/data.page_size))} 页`;
    $('#member-prev').disabled=data.page<=1;$('#member-next').disabled=data.page*data.page_size>=data.total;
    $('#member-list').innerHTML=data.items.length?`<table><thead><tr><th>成员</th><th>QQ</th><th>学校 / 身份</th><th>OJ 账号</th><th>Web 角色</th><th>操作</th></tr></thead><tbody>${data.items.map(row=>{const next=new URLSearchParams(listParams);next.set('qq_id',row.qq_id);return `<tr><td>${esc(row.name)}</td><td>${esc(row.qq_id)}</td><td>${esc(row.school||'—')}<br>${esc(row.status||'—')}</td><td>${esc(row.cf_handle||row.luogu_id||row.atcoder_handle||row.nowcoder_id||'未绑定')}</td><td>${esc(({root:'Web Root',admin:'Web 管理员',member:'普通成员'})[row.role]||'未开通 Web 账号')}</td><td><a class="btn" data-member-link href="/admin.html?${esc(next.toString())}">查看资料</a></td></tr>`}).join('')}</tbody></table>`:'<p class="empty">没有匹配成员。</p>';
    ctx.on(root,'click',event=>{const link=event.target.closest('[data-member-link]');if(link&&!event.ctrlKey&&!event.metaKey){event.preventDefault();ctx.navigate({qq_id:new URL(link.href).searchParams.get('qq_id')})}});
    return {};
  }
  root.innerHTML='<button class="btn" id="back-members">← 返回成员列表</button><div id="member-detail" class="empty">正在加载成员资料…</div>';
  $('#back-members').onclick=()=>ctx.navigate({qq_id:null});
  async function load(){
    const data=await api('/member/'+encodeURIComponent(qq)),user=data.user;
    $('#member-detail').className='';
    $('#member-detail').innerHTML=`<section class="admin-panel"><h2>${esc(user.name||qq)} · ${esc(qq)}</h2><p class="muted">Web 角色：${esc(({root:'Web Root',admin:'Web 管理员',member:'普通成员'})[data.permissions?.role]||'未开通 Web 账号')}。<a href="/admin.html">到成员账号维护 Web 权限</a></p><form id="member-profile-form"><div class="admin-create-grid">${fields.map(([key,label])=>`<label>${label}<input name="${key}" value="${esc(user[key]||'')}"></label>`).join('')}</div><p class="muted">OJ 账号变更后会清理旧账号提交证据并重新同步；历史学习资料保留存档。</p><button class="btn primary">保存资料与绑定</button><p id="member-profile-message" role="status"></p></form></section><section class="admin-panel"><h2>平台统计</h2><div class="chips">${Object.entries(data.platform_counts||{}).map(([platform,count])=>`<span class="chip">${esc(platform)} · ${count} 题</span>`).join('')||'暂无记录'}</div><p class="muted">CF Rating ${esc(data.cf?.rating??'—')} · AtCoder Rating ${esc(data.atcoder?.rating??'—')} · 挑战 Rating ${esc(data.challenge_rating??'—')}</p></section><section class="admin-panel"><h2>最近 AC 摘要</h2><div class="list">${(data.recent_ac||[]).map(row=>`<article class="list-item"><span><b>${esc(row.problem_name||row.problem_id)}</b><br><small>${esc(row.platform)} · ${esc(row.problem_rating||'未知')}</small></span>${row.problem_url?`<a class="btn" href="${esc(row.problem_url)}" target="_blank" rel="noopener">打开题目</a>`:''}</article>`).join('')||'<p class="empty">暂无 AC 记录。</p>'}</div></section>`;
    ctx.on($('#member-profile-form'),'submit',async event=>{
      event.preventDefault();const body={qq_id:qq,...Object.fromEntries(new FormData(event.target))};
      try{const result=await api('/user',{method:'PUT',body:JSON.stringify(body)});await load();$('#member-profile-message').textContent=result.message}catch(error){if(error.name!=='AbortError')$('#member-profile-message').textContent=error.message}
    });
  }
  await load();return {};
}
