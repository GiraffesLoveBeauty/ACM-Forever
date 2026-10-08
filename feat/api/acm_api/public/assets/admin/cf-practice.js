export async function enter(ctx) {
  const {root, $, api, esc, auth: AUTH, document, setTimeout, clearTimeout} = ctx;
  root.innerHTML = `<div class="cf-intro"><div><span class="cf-eyebrow">CODEFORCES · PRACTICE</span><h2>先了解进度，再确认候选。</h2><p>近期 AC 帮助了解成员进度；候选题使用全部历史查重。仅“可用”题目可以加入本页候选清单。</p></div><span class="cf-intro-mark" aria-hidden="true">{ AC }</span></div>
      <p id="page-message" class="cf-message" role="status" aria-live="polite"></p>
      <section class="card cf-scope" aria-labelledby="scope-heading">
        <div class="cf-section-heading"><div><h2 id="scope-heading">参与成员</h2><p class="muted">按实际身份选择成员，并排除本次不参赛的人。未绑定 CF 的成员仍计入范围。</p></div><div class="cf-actions"><button class="btn" id="refresh-scope">刷新概况</button><button class="btn primary" id="sync-cf" disabled>补齐 / 刷新数据</button></div></div>
        <fieldset class="cf-fieldset"><legend>成员身份</legend><div id="status-options" class="cf-status-options">正在读取身份…</div></fieldset>
        <div class="cf-metrics" id="scope-metrics" aria-live="polite"></div>
        <p class="muted cf-coverage" id="scope-coverage"></p>
        <details class="cf-members"><summary id="scope-members-summary">查看参与成员与待处理项</summary><div id="scope-members" class="cf-member-list"></div></details>
      </section>
      <section class="card cf-job" id="job-panel" hidden aria-labelledby="job-heading"><h2 id="job-heading">后台任务</h2><p id="job-message" role="status" aria-live="polite"></p><progress id="job-progress" max="1" value="0" aria-label="成员同步进度"></progress><div id="job-members" class="cf-job-members"></div></section>
      <div class="cf-tabs" role="tablist" aria-label="选题工具"><button id="tab-recent" role="tab" aria-selected="true" aria-controls="panel-recent" tabindex="0">近期刷题</button><button id="tab-check" role="tab" aria-selected="false" aria-controls="panel-check" tabindex="-1">候选题查重</button></div>
      <section class="card" id="panel-recent" role="tabpanel" aria-labelledby="tab-recent">
        <form id="recent-form" class="cf-recent-filters">
          <label>时间范围<select id="recent-days"><option value="7">近 7 天</option><option value="30">近 30 天</option><option value="custom">自定义日期</option></select></label>
          <div id="custom-dates" class="cf-custom-dates" hidden><label>起始日期<input id="date-from" type="date"></label><label>结束日期<input id="date-to" type="date"></label></div>
          <label>最低 Rating<input id="rating-min" type="number" min="0" max="5000" step="100" placeholder="不限"></label>
          <label>最高 Rating<input id="rating-max" type="number" min="0" max="5000" step="100" placeholder="不限"></label>
          <label>标签<select id="recent-tag"><option value="">全部标签</option></select></label>
          <label>展示方式<select id="recent-view"><option value="problems">按题目汇总</option><option value="members">按成员展开</option></select></label>
          <label class="cf-search">搜索<input id="recent-search" placeholder="题号或题名" maxlength="200"></label><button class="btn primary" type="submit">查询</button>
        </form>
        <div class="cf-result-heading"><h2>近期 AC</h2><span class="muted" id="recent-summary"></span></div><div id="recent-results" class="table-wrap"><p class="empty">请选择成员身份。</p></div>
        <div class="cf-pagination"><button class="btn" id="recent-prev" disabled>上一页</button><span id="recent-page" class="muted">—</span><button class="btn" id="recent-next" disabled>下一页</button></div>
        <p class="muted cf-footnote">同一成员同一道题只计一次。历史 AC 人数不受近期日期筛选影响；待处理成员可能使统计不完整。</p>
      </section>
      <section class="card" id="panel-check" role="tabpanel" aria-labelledby="tab-check" hidden>
        <form id="check-form">
          <div class="cf-check-controls"><label>输入方式<select id="candidate-kind"><option value="problems">批量题号 / CF 链接</option><option value="contest">整场比赛</option></select></label><label>查重口径<select id="check-mode"><option value="any_submission">排除所有提交过的题</option><option value="ac_only">仅排除已 AC 的题</option></select></label></div>
          <label id="candidate-list-label" class="cf-input-label">候选题<textarea id="candidate-input" rows="5" maxlength="102400" placeholder="1843A&#10;https://codeforces.com/contest/1843/problem/B&#10;1843C" aria-describedby="candidate-help"></textarea></label>
          <label id="contest-id-label" class="cf-input-label" hidden>CF 比赛 ID<input id="contest-id" type="number" min="1" max="9999999" placeholder="1843"></label>
          <div class="cf-check-submit"><p id="candidate-help" class="muted">每行一个题号或链接，最多 100 条；也可用逗号分隔。查重使用全部历史，不受上方近期筛选影响。</p><button class="btn primary" id="start-check" type="submit" disabled>开始查重</button></div>
        </form>
        <div class="cf-result-heading"><h2>查重结果</h2><span id="check-summary" class="muted" role="status"></span></div><p class="muted" id="check-coverage"></p>
        <div id="check-results" class="table-wrap"><p class="empty">输入候选题后开始查重。</p></div>
        <div class="cf-copy-bar"><span id="selected-count">已选 0 题</span><div class="cf-actions"><button class="btn" id="copy-ids" disabled>复制题号</button><button class="btn primary" id="copy-links" disabled>复制 CF 链接</button></div></div>
        <label class="cf-input-label" id="copy-fallback-label" hidden>复制内容<textarea id="copy-fallback" rows="4" readonly></textarea></label>
        <p class="muted cf-footnote">结论仅截至数据覆盖时间，无法识别只看过题但未提交的情况。候选清单只保存在当前页面，不创建练习赛。</p>
      </section><dialog id="evidence-dialog" class="cf-dialog" aria-labelledby="evidence-heading"><div class="cf-section-heading"><h2 id="evidence-heading">成员证据</h2><button class="btn" id="close-evidence">关闭</button></div><p class="muted" id="evidence-caption"></p><div class="table-wrap" id="evidence-results"></div><div class="cf-pagination"><button class="btn" id="evidence-prev">上一页</button><span id="evidence-page"></span><button class="btn" id="evidence-next">下一页</button></div></dialog>`;

  const state={statuses:new Set(),excluded:new Set(),scope:null,recentPage:1,recent:null,result:null,selected:new Set(),overviewVersion:0,checkVersion:0,detailVersion:0,syncVersion:0,overviewBusy:false,checkBusy:false,syncBusy:false,copyBusy:false,detail:null};
  const controllers=new Map();
  const labels={eligible:'可用',excluded_ac:'有人 AC，排除',excluded_attempted:'有人提交，排除',unknown:'未知，待处理',invalid:'输入无效 / 题目不存在'};
  const jobLabels={queued:'排队中',running:'执行中',completed:'成功',partial:'部分完成',failed:'失败',interrupted:'已中断'};
  const terminal=new Set(['completed','partial','failed','interrupted']);
  const timeFormatter=new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false});
  const time=value=>value?timeFormatter.format(new Date(value)):'暂无完整覆盖时间';
  const rating=value=>value==null?'未知':String(value);
  const scopeSpec=()=>({statuses:[...state.statuses],exclude_qq_ids:[...state.excluded]});
  const notice=text=>{$('#page-message').textContent=text};
  function stop(name){controllers.get(name)?.abort();controllers.delete(name)}
  function controller(name){stop(name);const value=new AbortController();controllers.set(name,value);return value}
  function abortError(){return new DOMException('请求已取消','AbortError')}
  function wait(ms,signal){return new Promise((resolve,reject)=>{if(signal.aborted)return reject(abortError());const abort=()=>{clearTimeout(timer);reject(abortError())};const timer=setTimeout(()=>{signal.removeEventListener('abort',abort);resolve()},ms);signal.addEventListener('abort',abort,{once:true})})}
  function post(path,body,signal){return api('/admin/cf/'+path,{method:'POST',body:JSON.stringify(body),signal})}
  function controls(){
    const members=Boolean(state.scope?.member_count),busy=state.overviewBusy||state.syncBusy||state.checkBusy||state.copyBusy;
    $('#sync-cf').disabled=!members||busy;
    $('#start-check').disabled=!members||state.overviewBusy||state.syncBusy||state.copyBusy;
    $('#copy-ids').disabled=$('#copy-links').disabled=!state.selected.size||!state.result||busy;
    $('#selected-count').textContent=`已选 ${state.selected.size} 题`;
  }
  function invalidateCheck(message='范围或输入已改变，请重新查重。'){
    ctx.memory.recheckOnReturn=false;
    state.checkVersion++;stop('check');stop('copy');state.checkBusy=false;state.copyBusy=false;state.result=null;state.selected.clear();
    if(state.jobKind==='check')$('#job-panel').hidden=true;
    $('#check-results').innerHTML=`<p class="empty">${esc(message)}</p>`;$('#check-summary').textContent='';$('#check-coverage').textContent='';$('#copy-fallback-label').hidden=true;controls();
  }
  async function handleError(error){
    if(error.name==='AbortError')return;
    if(error.code==='scope_changed'){
      invalidateCheck('成员范围或 CF 绑定已变化，请重新查重。');state.scope=null;state.excluded.clear();notice('成员范围已变化，旧结果已失效。请重新核对排除名单。');
      await loadOptions();await loadOverview(true);return;
    }
    notice(error.message||'请求失败，请重试。');
  }
  async function loadOptions(){
    const request=controller('options');
    const data=await api('/admin/cf/options',{signal:request.signal});
    const values=new Set(data.statuses.map(row=>row.value));
    state.statuses=new Set([...state.statuses].filter(value=>values.has(value)));
    if(!state.statuses.size&&data.statuses.length)state.statuses.add(values.has('现役')?'现役':data.statuses[0].value);
    $('#status-options').innerHTML=data.statuses.map(row=>`<label class="cf-status-option"><input type="checkbox" value="${esc(row.value)}" ${state.statuses.has(row.value)?'checked':''}><span>${esc(row.label)} · ${row.member_count} 人</span></label>`).join('')||'<span class="muted">暂无成员，请先在管理中心添加成员。</span>';
  }
  function recentFilters(){
    const data={view:$('#recent-view').value,page:state.recentPage,page_size:20,search:$('#recent-search').value.trim(),tag:$('#recent-tag').value};
    const days=$('#recent-days').value;
    if(days==='custom'){
      if(!$('#date-from').value||!$('#date-to').value)throw Error('请选择完整的自定义日期范围。');
      data.date_from=$('#date-from').value+'T00:00:00+08:00';data.date_to=$('#date-to').value+'T23:59:59+08:00';
    }else data.days=Number(days);
    if($('#rating-min').value!=='')data.rating_min=$('#rating-min').value;
    if($('#rating-max').value!=='')data.rating_max=$('#rating-max').value;
    return data;
  }
  function renderScope(scope){
    $('#scope-metrics').innerHTML=[[scope.member_count,'参与成员'],[scope.bound_member_count,'CF 已绑定'],[scope.ready_member_count,'数据就绪'],[scope.unknown_member_count,'待处理成员']].map(([value,label])=>`<div class="cf-metric"><strong>${value}</strong><span>${label}</span></div>`).join('');
    $('#scope-coverage').textContent=`数据共同覆盖截至：${time(scope.coverage_as_of)}（北京时间）。数据有效期 ${Math.round((state.recent?.data_ttl_seconds||86400)/3600)} 小时。`;
    $('#scope-members-summary').textContent=`查看参与成员与待处理项 · 已排除 ${scope.exclude_qq_ids.length} 人`;
    $('#scope-members').innerHTML=scope.members.map(member=>`<label class="cf-member-row"><input class="cf-member-include" type="checkbox" data-qq="${esc(member.qq_id)}" ${member.excluded?'':'checked'} aria-label="${esc(member.name)} 参加本次练习赛"><span><b>${esc(member.name)} · ${esc(member.cf_handle||'未绑定 CF')}</b><small>${member.excluded?'已排除 · ':''}${esc(member.reason_label)}${member.error_message?' · '+esc(member.error_message):''}</small><small>最近成功：${time(member.last_success_at)}</small></span></label>`).join('')||'<p class="muted">当前身份下没有成员。</p>';
  }
  function evidenceButton(pid,period,label){return `<button class="btn" type="button" data-evidence="${esc(pid)}" data-period="${period}">${label}</button>`}
  function renderRecent(data){
    $('#recent-summary').textContent=`共 ${data.total} ${data.view==='members'?'位成员':'道题目'} · ${data.scope.unknown_member_count?'统计可能不完整':'成员数据就绪'}`;
    if(!data.rows.length){$('#recent-results').innerHTML='<p class="empty">当前范围和筛选下暂无近期 AC。</p>'}
    else if(data.view==='members'){
      $('#recent-results').innerHTML='<ul class="cf-member-results">'+data.rows.map(member=>`<li><details><summary><b>${esc(member.name)}</b> · ${esc(member.cf_handle)} · 近期 AC ${member.recent_ac_count} 题</summary><div class="cf-member-problems">${member.problems.map(problem=>`<div><span><a href="${esc(problem.url)}" target="_blank" rel="noopener">${esc(problem.display_id)} · ${esc(problem.name)}</a> · Rating ${rating(problem.rating)}<br><span class="muted">${time(problem.ac_at)}</span></span><span>${problem.submission_url?`<a href="${esc(problem.submission_url)}" target="_blank" rel="noopener">AC 提交 ↗</a>`:'旧 AC 记录，无提交链接'} ${evidenceButton(problem.display_id,'history','历史证据')}</span></div>`).join('')}</div></details></li>`).join('')+'</ul>';
    }else{
      $('#recent-results').innerHTML='<table class="cf-desktop-results"><thead><tr><th>题号 / 题名</th><th>Rating / 标签</th><th>近期 AC 人</th><th>历史 AC 人</th><th>最近 AC（北京时间）</th><th>证据</th></tr></thead><tbody>'+data.rows.map(row=>`<tr><td><a href="${esc(row.url)}" target="_blank" rel="noopener"><b>${esc(row.display_id)}</b> · ${esc(row.name)} ↗</a></td><td>${rating(row.rating)}<small>${esc(row.tags.join(' · ')||'暂无标签')}</small></td><td>${row.recent_ac_count} 人</td><td>${row.history_ac_count} 人</td><td>${time(row.last_ac_at)}</td><td>${evidenceButton(row.display_id,'recent','近期成员')} ${evidenceButton(row.display_id,'history','历史证据')}</td></tr>`).join('')+'</tbody></table>';
      $('#recent-results').insertAdjacentHTML('beforeend','<ul class="cf-mobile-results">'+data.rows.map(row=>`<li><details><summary><b>${esc(row.display_id)}</b> · ${esc(row.name)}<small>近期 AC ${row.recent_ac_count} 人 · 历史 AC ${row.history_ac_count} 人</small></summary><div class="cf-mobile-detail"><a href="${esc(row.url)}" target="_blank" rel="noopener">打开 CF 题目 ↗</a><p>Rating ${rating(row.rating)} · ${esc(row.tags.join(' · ')||'暂无标签')}</p><p>最近 AC：${time(row.last_ac_at)}</p><div class="cf-actions">${evidenceButton(row.display_id,'recent','近期成员')} ${evidenceButton(row.display_id,'history','历史证据')}</div></div></details></li>`).join('')+'</ul>');
    }
    const pages=Math.max(1,Math.ceil(data.total/data.page_size));$('#recent-page').textContent=`第 ${data.page} / ${pages} 页`;
    $('#recent-prev').disabled=data.page<=1;$('#recent-next').disabled=data.page>=pages;
    const previous=$('#recent-tag').value;
    $('#recent-tag').innerHTML='<option value="">全部标签</option>'+[...new Set([...data.available_tags,...(previous?[previous]:[])])].map(tag=>`<option value="${esc(tag)}">${esc(tag)}</option>`).join('');$('#recent-tag').value=previous;
  }
  async function loadOverview(reset=false){
    if(reset)state.recentPage=1;
    const version=++state.overviewVersion,request=controller('overview');state.overviewBusy=true;controls();
    if(!state.statuses.size){state.scope=null;$('#scope-metrics').innerHTML='';$('#scope-members').innerHTML='';$('#scope-coverage').textContent='';$('#recent-summary').textContent='';$('#recent-page').textContent='—';$('#recent-prev').disabled=$('#recent-next').disabled=true;$('#recent-results').innerHTML='<p class="empty">请至少选择一个成员身份。</p>';state.overviewBusy=false;controls();return}
    try{
      const data=await post('overview',{scope:scopeSpec(),...recentFilters()},request.signal);
      if(version!==state.overviewVersion)return;
      if(state.scope&&state.scope.fingerprint!==data.scope.fingerprint)invalidateCheck('成员范围或绑定已变化，请重新查重。');
      state.scope=data.scope;state.recent=data;renderScope(data.scope);renderRecent(data);
    }catch(error){if(version===state.overviewVersion)await handleError(error)}
    finally{if(version===state.overviewVersion){state.overviewBusy=false;controls()}}
  }
  function candidatePayload(){
    if(!state.scope?.member_count)throw Error('请先选择至少一名参与成员。');
    const data={scope:scopeSpec(),expected_scope_fingerprint:state.scope.fingerprint,mode:$('#check-mode').value};
    if($('#candidate-kind').value==='contest')data.contest_id=$('#contest-id').value;
    else data.candidates=$('#candidate-input').value.split(/[\n,;，；]+/).map(line=>line.trim()).filter(Boolean);
    return data;
  }
  function canSelect(row){return row.eligible&&row.decision==='eligible'&&state.result?.scope.fingerprint===state.scope?.fingerprint&&!state.scope.unknown_member_count&&state.scope.member_count>0}
  function renderCheck(data,preview=false){
    if(!preview)ctx.memory.recheckOnReturn=true;
    if(!preview){state.result=data;state.scope=data.scope;state.selected.clear();renderScope(data.scope)}
    const counts=data.counts;
    $('#check-summary').textContent=`共 ${data.total} 题 · 可用 ${counts.eligible} · 排除 ${counts.excluded_ac+counts.excluded_attempted} · 未知 ${counts.unknown} · 无效 ${counts.invalid}${preview?' · 题目核实中':''}`;
    $('#check-coverage').textContent=`${data.mode==='ac_only'?'仅排除已 AC':'排除所有提交过的题'} · 全部历史 · 数据覆盖截至 ${time(data.coverage_as_of)} · 查重时间 ${time(data.checked_at)}（北京时间）`;
    if(!data.rows.length){$('#check-results').innerHTML='<p class="empty">没有可展示的候选题；请检查比赛 ID 或成员范围。</p>';controls();return}
    $('#check-results').innerHTML='<table class="cf-desktop-results"><thead><tr><th>选择</th><th>题号 / 题名</th><th>Rating</th><th>AC 人数</th><th>提交人数</th><th>判定 / 原因</th><th>详情</th></tr></thead><tbody>'+data.rows.map(row=>`<tr><td><input class="cf-candidate-select" type="checkbox" data-pid="${esc(row.display_id)}" aria-label="选择 ${esc(row.display_id)}" ${!preview&&canSelect(row)?'':'disabled'}></td><td>${row.url?`<a href="${esc(row.url)}" target="_blank" rel="noopener"><b>${esc(row.display_id)}</b> ↗</a><small>${esc(row.name)}</small>`:esc(row.display_id)}</td><td>${rating(row.rating)}</td><td>${row.ac_count}</td><td>${row.attempt_count}</td><td><span class="cf-state cf-state-${esc(row.decision)}">${labels[row.decision]}</span><small>${esc(row.reason)}</small></td><td>${row.url?evidenceButton(row.display_id,'history','涉及成员'):'—'}</td></tr>`).join('')+'</tbody></table>';
    $('#check-results').insertAdjacentHTML('beforeend','<ul class="cf-mobile-results">'+data.rows.map(row=>`<li class="cf-mobile-card"><input class="cf-candidate-select" type="checkbox" data-pid="${esc(row.display_id)}" aria-label="选择 ${esc(row.display_id)}" ${!preview&&canSelect(row)?'':'disabled'}><details><summary><b>${esc(row.display_id)}</b><span class="cf-state cf-state-${esc(row.decision)}">${labels[row.decision]}</span></summary><div class="cf-mobile-detail">${row.url?`<a href="${esc(row.url)}" target="_blank" rel="noopener">${esc(row.name)} ↗</a>`:''}<p>Rating ${rating(row.rating)} · AC ${row.ac_count} 人 · 提交 ${row.attempt_count} 人</p><p>${esc(row.reason)}</p>${row.tags.length?`<p class="muted">${esc(row.tags.join(' · '))}</p>`:''}${row.url?evidenceButton(row.display_id,'history','涉及成员'):''}</div></details></li>`).join('')+'</ul>');
    controls();
  }
  function showJob(job){
    state.jobKind=job.kind;
    $('#job-panel').hidden=false;$('#job-heading').textContent=job.kind==='sync'?'CF 历史补齐 / 刷新':'候选题资料核实';
    $('#job-message').textContent=`${jobLabels[job.status]||job.status}${job.message?' · '+job.message:''}`;
    const members=job.members||[],finished=members.filter(row=>terminal.has(row.status)).length;
    if(members.length){$('#job-progress').max=members.length;$('#job-progress').value=finished}else $('#job-progress').removeAttribute('value');
    $('#job-members').innerHTML=members.map(member=>`<div><b>${esc(member.handle||member.qq_id)}</b> · ${jobLabels[member.status]||member.status}${member.error_message?'<br>'+esc(member.error_message):''}</div>`).join('');
    if(terminal.has(job.status)&&!members.length){$('#job-progress').max=1;$('#job-progress').value=1}
  }
  async function pollJob(jobId,signal,current){
    ctx.memory.job={id:jobId,kind:state.jobKind};
    while(true){
      const job=await api('/admin/cf/jobs/'+encodeURIComponent(jobId),{signal});
      if(!current()||signal.aborted)throw abortError();showJob(job);
      if(terminal.has(job.status)){ctx.memory.job=null;return job;}
      await wait(2500,signal);
    }
  }
  async function checkedResult(payload,signal,current){
    let data=await post('check',payload,signal);
    if(!current()||signal.aborted)throw abortError();
    if(data.status==='queued'){
      const job=await pollJob(data.job_id,signal,current);
      if(!job.result){const error=Error(job.message||'题目核实未完成，请重试。');error.code=job.error_code;throw error}
      data=job.result;
    }
    return data;
  }
  async function checkCandidates(){
    const version=++state.checkVersion,request=controller('check');state.checkBusy=true;state.result=null;state.selected.clear();controls();
    if(state.jobKind==='check')$('#job-panel').hidden=true;
    $('#check-results').innerHTML='<p class="empty">正在使用全部历史查重；需要核实题目时会显示后台进度。</p>';$('#check-summary').textContent='查询中…';
    try{
      const data=await checkedResult(candidatePayload(),request.signal,()=>version===state.checkVersion);
      if(version!==state.checkVersion)return;
      if(data.scope.fingerprint!==state.scope?.fingerprint)throw Object.assign(Error('成员范围已变化'),{code:'scope_changed'});
      renderCheck(data);notice(data.metadata_warnings?.length?'部分 CF 题目资料未能核实，相关题目保留为未知。':'查重完成。仅“可用”题目允许勾选。');
    }catch(error){if(version===state.checkVersion){$('#check-summary').textContent='查重未完成';await handleError(error)}}
    finally{if(version===state.checkVersion){state.checkBusy=false;controls()}}
  }
  async function syncData(){
    const recheck=Boolean(state.result),version=++state.syncVersion,request=controller('sync');
    invalidateCheck('数据更新中，旧查重结果已失效。');state.syncBusy=true;controls();
    ctx.memory.recheckOnReturn=recheck;
    const checkVersion=state.checkVersion;
    try{
      const data=await post('sync',{scope:scopeSpec(),expected_scope_fingerprint:state.scope.fingerprint},request.signal);
      const job=await pollJob(data.job_id,request.signal,()=>version===state.syncVersion);
      await loadOverview(false);
      notice(job.status==='completed'?'CF 历史刷新完成。':'刷新结束，仍有需处理成员或未核实资料，请查看任务详情。');
      if(recheck&&checkVersion===state.checkVersion&&version===state.syncVersion&&state.scope?.member_count)await checkCandidates();
    }catch(error){if(version===state.syncVersion)await handleError(error)}
    finally{if(version===state.syncVersion){state.syncBusy=false;controls()}}
  }
  async function copySelection(kind){
    if(!state.result||!state.selected.size)return;
    const selectedRows=state.result.rows.filter(row=>state.selected.has(row.display_id)&&canSelect(row));
    const version=state.checkVersion,request=controller('copy');state.copyBusy=true;controls();
    try{
      // Revalidate immediately before copying so expired or externally changed data cannot be silently reused.
      const data=await checkedResult({scope:scopeSpec(),expected_scope_fingerprint:state.scope.fingerprint,mode:state.result.mode,candidates:selectedRows.map(row=>row.display_id)},request.signal,()=>version===state.checkVersion);
      if(data.rows.length!==selectedRows.length||data.rows.some(row=>!row.eligible)){
        invalidateCheck('所选题目的数据或结论已变化，请重新查重。');notice('候选清单未复制，请重新查重。');return;
      }
      const text=selectedRows.map(row=>kind==='links'?row.url:row.display_id).join('\n');
      if(version!==state.checkVersion||request.signal.aborted)throw abortError();
      try{await navigator.clipboard.writeText(text);notice(`已复制 ${selectedRows.length} 道题的${kind==='links'?'CF 链接':'题号'}。`)}
      catch{if(version!==state.checkVersion)return;$('#copy-fallback-label').hidden=false;$('#copy-fallback').value=text;$('#copy-fallback').focus();$('#copy-fallback').select();notice('自动复制未成功，可从下方文本框手动复制。')}
    }catch(error){if(version===state.checkVersion)await handleError(error)}
    finally{if(version===state.checkVersion){state.copyBusy=false;controls()}}
  }
  async function showEvidence(pid,period,page=1){
    const version=++state.detailVersion,request=controller('details');state.detail={pid,period,page};
    $('#evidence-heading').textContent=pid+' · 成员证据';$('#evidence-caption').textContent=period==='recent'?'当前日期范围内的 AC，时间按北京时间展示。':'全部历史提交与 AC，不受近期筛选影响。';$('#evidence-results').innerHTML='<p class="empty">正在查询证据…</p>';
    if(!$('#evidence-dialog').open)$('#evidence-dialog').showModal();
    try{
      const data=await post('problem-members',{...(period==='recent'?recentFilters():{}),scope:scopeSpec(),expected_scope_fingerprint:state.scope.fingerprint,problem_id:pid,period,page,page_size:20},request.signal);
      if(version!==state.detailVersion)return;
      $('#evidence-results').innerHTML=data.rows.length?'<table><thead><tr><th>成员 / CF handle</th><th>证据</th><th>最近 AC</th><th>最近提交</th><th>提交链接</th></tr></thead><tbody>'+data.rows.map(row=>`<tr><td>${esc(row.name)}<br>${esc(row.cf_handle)}</td><td>${row.has_ac?'有 AC 证据':'仅有提交证据'}</td><td>${row.ac_at?time(row.ac_at):'—'}</td><td>${time(row.last_attempt_at)}</td><td>${row.ac_submission_url?`<a href="${esc(row.ac_submission_url)}" target="_blank" rel="noopener">AC 提交 ↗</a><br>`:''}${row.attempt_submission_url?`<a href="${esc(row.attempt_submission_url)}" target="_blank" rel="noopener">最近提交 ↗</a>`:'旧记录无提交链接'}</td></tr>`).join('')+'</tbody></table>':'<p class="empty">当前参与成员没有该口径下的记录。</p>';
      const pages=Math.max(1,Math.ceil(data.total/data.page_size));$('#evidence-page').textContent=`第 ${data.page} / ${pages} 页 · ${data.total} 人`;
      $('#evidence-prev').disabled=data.page<=1;$('#evidence-next').disabled=data.page>=pages;
    }catch(error){if(version===state.detailVersion){$('#evidence-results').innerHTML=`<p class="empty">${esc(error.message)}</p>`;await handleError(error)}}
  }
  function switchTab(id){
    ctx.updateParams({tab:id});
    for(const name of ['recent','check']){const active=name===id;$('#tab-'+name).setAttribute('aria-selected',String(active));$('#tab-'+name).tabIndex=active?0:-1;$('#panel-'+name).hidden=!active}
  }
  function scopeChanged(){state.syncVersion++;stop('sync');state.syncBusy=false;state.scope=null;invalidateCheck();$('#job-panel').hidden=true;state.jobKind=null;$('#evidence-dialog').close();state.detailVersion++;stop('details');loadOverview(true)}
  ctx.on($('#status-options'),'change',()=>{state.statuses=new Set([...$('#status-options').querySelectorAll('input:checked')].map(input=>input.value));state.excluded.clear();scopeChanged()});
  ctx.on($('#scope-members'),'change',event=>{const input=event.target.closest('.cf-member-include');if(!input)return;if(input.checked)state.excluded.delete(input.dataset.qq);else state.excluded.add(input.dataset.qq);scopeChanged()});
  $('#refresh-scope').onclick=async()=>{try{await loadOptions();await loadOverview(true)}catch(error){await handleError(error)}};
  $('#recent-form').onsubmit=event=>{event.preventDefault();loadOverview(true)};
  $('#recent-days').onchange=()=>{$('#custom-dates').hidden=$('#recent-days').value!=='custom'};
  $('#recent-prev').onclick=()=>{state.recentPage--;loadOverview()};$('#recent-next').onclick=()=>{state.recentPage++;loadOverview()};
  $('#sync-cf').onclick=syncData;
  $('#check-form').onsubmit=event=>{event.preventDefault();checkCandidates()};
  for(const id of ['candidate-input','contest-id'])ctx.on($('#'+id),'input',()=>invalidateCheck('候选输入已改变，请重新查重。'));
  $('#check-mode').onchange=()=>invalidateCheck('查重口径已改变，请重新查重。');
  $('#candidate-kind').onchange=()=>{const contest=$('#candidate-kind').value==='contest';$('#candidate-list-label').hidden=contest;$('#contest-id-label').hidden=!contest;invalidateCheck('输入方式已改变，请重新查重。')};
  ctx.on($('#check-results'),'change',event=>{const input=event.target.closest('.cf-candidate-select');if(!input)return;const row=state.result?.rows.find(row=>row.display_id===input.dataset.pid);if(!row||!canSelect(row)){input.checked=false;return}if(input.checked)state.selected.add(row.display_id);else state.selected.delete(row.display_id);$('#check-results').querySelectorAll('.cf-candidate-select').forEach(box=>{if(box.dataset.pid===row.display_id)box.checked=input.checked});controls()});
  for(const id of ['recent-results','check-results'])ctx.on($('#'+id),'click',event=>{const button=event.target.closest('[data-evidence]');if(button)showEvidence(button.dataset.evidence,button.dataset.period)});
  $('#close-evidence').onclick=()=>$('#evidence-dialog').close();ctx.on($('#evidence-dialog'),'close',()=>{state.detailVersion++;stop('details')});
  $('#evidence-prev').onclick=()=>{const d=state.detail;showEvidence(d.pid,d.period,d.page-1)};$('#evidence-next').onclick=()=>{const d=state.detail;showEvidence(d.pid,d.period,d.page+1)};
  $('#copy-ids').onclick=()=>copySelection('ids');$('#copy-links').onclick=()=>copySelection('links');
  for(const id of ['recent','check']){
    $('#tab-'+id).onclick=()=>switchTab(id);
    $('#tab-'+id).onkeydown=event=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(event.key)){event.preventDefault();const target=event.key==='Home'?'recent':event.key==='End'?'check':id==='recent'?'check':'recent';switchTab(target);$('#tab-'+target).focus()}};
  }
  ctx.onWindow('pagehide',()=>{for(const value of controllers.values())value.abort();controllers.clear();state.overviewVersion++;state.checkVersion++;state.detailVersion++;state.syncVersion++});
  ctx.load=async()=>{
    if(!['admin','root'].includes(AUTH.role)){notice('此页面仅供管理员使用。');return}
    const date=value=>new Date(value).toLocaleDateString('en-CA',{timeZone:'Asia/Shanghai'});
    $('#date-from').value=date(Date.now()-7*86400000);$('#date-to').value=date(Date.now());
    try{await loadOptions();await loadOverview(true)}catch(error){await handleError(error)}
  };


const remembered=ctx.memory;
for(const key of ['candidate-input','contest-id','candidate-kind','check-mode'])if(remembered[key]!=null)$('#'+key).value=remembered[key];
$('#candidate-list-label').hidden=$('#candidate-kind').value==='contest';$('#contest-id-label').hidden=!$('#candidate-list-label').hidden;
state.statuses=new Set(remembered.statuses||[]);state.excluded=new Set(remembered.excluded||[]);
const initial=ctx.load;
ctx.load=async()=>{switchTab(ctx.params.get('tab')==='check'?'check':'recent');await initial();if(remembered.job){try{const request=controller('resume');const job=await pollJob(remembered.job.id,request.signal,()=>!ctx.signal.aborted);await loadOverview();if(job.kind==='check'&&job.result||remembered.recheckOnReturn)await checkCandidates()}catch(error){await handleError(error)}}else if(remembered.recheckOnReturn&&state.scope?.member_count)await checkCandidates();};
ctx.cleanup=()=>{for(const key of ['candidate-input','contest-id','candidate-kind','check-mode'])remembered[key]=$('#'+key).value;remembered.statuses=[...state.statuses];remembered.excluded=[...state.excluded];$('#evidence-dialog').close();for(const value of controllers.values())value.abort();controllers.clear();state.overviewVersion++;state.checkVersion++;state.detailVersion++;state.syncVersion++;};

  await ctx.load?.();
  return {exit:()=>ctx.cleanup?.(), beforeLeave:()=>ctx.beforeLeave?.() ?? true};
}
