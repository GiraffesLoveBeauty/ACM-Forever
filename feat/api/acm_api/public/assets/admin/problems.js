export async function enter(ctx){
  const {root,$,api,esc,auth}=ctx;let page=1,version=0;
  const manager=['admin','root'].includes(auth.role);
  root.innerHTML=`<section class="admin-panel"><form id="problem-filters" class="filters"><label id="problem-owner-label">成员 QQ<input id="owner" value="${esc(ctx.params.get('qq_id')||auth.qq_id||'')}" inputmode="numeric"></label><label>平台<select id="platform"><option value="">全部平台</option><option value="codeforces">Codeforces</option><option value="luogu">洛谷</option><option value="atcoder">AtCoder</option><option value="nowcoder">牛客</option></select></label><label>搜索<input id="query" placeholder="题号、题名或标签"></label><label>收藏<select id="state"><option value="">全部题目</option><option value="favorite">已收藏</option></select></label><button class="btn primary">筛选题目</button></form><p id="problem-count" class="muted" role="status"></p><div id="problem-list" class="list"></div><div class="admin-pagination"><button class="btn" id="problem-prev">上一页</button><span id="problem-page"></span><button class="btn" id="problem-next">下一页</button></div></section>`;
  if(auth.role==='member'){$('#owner').value=auth.qq_id;$('#problem-owner-label').hidden=true;}
  if(manager)root.insertAdjacentHTML('afterbegin',`
    <section class="admin-section" aria-labelledby="problem-db-heading">
      <div class="admin-section-heading"><div><h2 id="problem-db-heading">服务端数据库</h2><p>初始化 SQLite 表结构，保留已有题目与样例。</p></div></div>
      <div class="admin-panel"><div class="admin-form-footer"><p id="problem-db-message" class="admin-message" role="status" aria-live="polite">正在检查数据库…</p><button class="btn admin-button" id="problem-db-init" type="button">初始化数据库</button></div><div id="problem-db-counts" class="chips"></div></div>
    </section>
    <section class="admin-section problem-sync" aria-labelledby="problem-sync-heading">
      <div class="admin-section-heading"><div><h2 id="problem-sync-heading">拉取题目</h2><p>从公开比赛采集题面与样例，保存到题库。</p></div><a class="admin-jump" href="/admin.html?section=tasks">查看同步任务 →</a></div>
      <div class="admin-panel">
        <form id="problem-sync-form">
          <fieldset id="problem-sync-fields" disabled>
            <div class="admin-create-grid">
              <label>平台<select id="sync-platform"><option value="atcoder">AtCoder</option><option value="codeforces">Codeforces</option></select></label>
              <label>拉取范围<select id="sync-scope"><option value="contest">单场比赛</option><option value="platform">该平台全部题目</option></select></label>
              <label>题面语言<select id="sync-language"><option value="en">英文</option><option value="ja">日文</option></select></label>
              <label><span id="sync-limit-label">最多拉取题数</span><input id="sync-limit" type="number" min="1" max="100" step="1" value="20" required></label>
              <label id="sync-contest-label">比赛 ID<input id="sync-contest" required maxlength="100" placeholder="例如 abc370" aria-describedby="sync-contest-hint"><small id="sync-contest-hint">填写比赛 ID，例如 abc370。</small></label>
              <label id="sync-problems-label">指定题号（选填）<input id="sync-problems" placeholder="例如 abc370_a, abc370_b" aria-describedby="sync-problems-hint"><small id="sync-problems-hint">多个题号用逗号或空格分隔；留空则按比赛题序拉取。</small></label>
            </div>
            <div class="admin-form-footer"><label class="admin-toggle"><input id="sync-refresh" type="checkbox"><span>重新拉取已有题目</span></label><button class="btn primary admin-button" id="sync-submit" type="submit">开始拉取</button></div>
          </fieldset>
        </form>
        <p class="admin-form-note" id="sync-mode-note">默认跳过已采集的题目。题数为本次上限；离开页面后后台任务继续执行。</p>
        <div id="sync-status" class="problem-sync-status" hidden>
          <p id="sync-message" role="status" aria-live="polite"></p>
          <progress id="sync-progress" max="1" aria-label="题目拉取进度" hidden></progress>
          <p id="sync-summary" class="muted"></p>
          <details id="sync-errors" hidden><summary>查看失败原因</summary><ul id="sync-error-list"></ul></details>
        </div>
      </div>
    </section>`);
  async function load(){const current=++version,owner=$('#owner').value.trim();
    const data=await api('/problems?'+new URLSearchParams({owner_qq_id:owner,platform:$('#platform').value,tag:$('#query').value,state:$('#state').value,page,page_size:20}));
    if(current!==version)return;
    const items=Array.isArray(data)?data:data.items;
    $('#problem-count').textContent=`共 ${data.total??items.length} 道题目 · 数据来自本地同步库`;
    $('#problem-page').textContent=`第 ${page} / ${Math.max(1,Math.ceil((data.total??items.length)/20))} 页`;
    $('#problem-prev').disabled=page<=1;$('#problem-next').disabled=page*20>=(data.total??items.length);
    $('#problem-list').innerHTML=items.map(row=>`<article class="list-item"><span><b>${esc(row.platform)} · ${esc(row.problem_id)}</b><br>${esc(row.problem_name||'未命名题目')}<br><small class="muted">难度 ${esc(row.problem_rating||'未知')} · ${esc(row.tags||'无标签')}</small></span><span class="chips"><button class="btn" data-favorite="${row.is_favorite?0:1}" data-platform="${esc(row.platform)}" data-problem="${esc(row.problem_id)}" data-owner="${esc(owner)}">${row.is_favorite?'取消收藏':'收藏'}</button><a class="btn" href="/problem.html?${esc(new URLSearchParams({platform:row.platform,problem_id:row.problem_id}).toString())}" target="_blank" rel="noopener">打开题目</a></span></article>`).join('')||'<p class="empty">没有匹配题目，请调整筛选或同步数据。</p>';
  }
  const run=()=>load().catch(error=>{if(error.name!=='AbortError')ctx.notice(error.message)});
  ctx.on($('#problem-filters'),'submit',event=>{event.preventDefault();page=1;run()});
  $('#problem-prev').onclick=()=>{page--;run()};$('#problem-next').onclick=()=>{page++;run()};
  ctx.on(root,'click',async event=>{const button=event.target.closest('[data-favorite]');if(!button)return;
    if(!/^\d{4,12}$/.test(button.dataset.owner)){ctx.notice('请填写成员 QQ 后保存收藏。');return;}
    try{await api('/problems/'+encodeURIComponent(button.dataset.platform)+'/'+encodeURIComponent(button.dataset.problem)+'/state',{method:'PUT',body:JSON.stringify({owner_qq_id:button.dataset.owner,is_favorite:button.dataset.favorite==='1'})});await load()}catch(error){if(error.name!=='AbortError')ctx.notice(error.message)}
  });
  if(manager){
    let taskId=ctx.memory.problemSyncTaskId||null,timer=null,publishedMetadata=0,completedBatches=0;
    function databaseStatus(data,text=''){
      $('#problem-db-message').textContent=text||(data.initialized?'数据库已初始化。':'缺少表结构，请先初始化数据库。');
      $('#problem-db-counts').innerHTML=(data.platforms||[]).map(row=>`<span class="chip">${esc(row.platform==='codeforces'?'Codeforces':'AtCoder')} · 目录 ${esc(row.total)} 题 · 已采集 ${esc(row.collected)} 题 · 失败 ${esc(row.failed)} 题 · 样例 ${esc(row.samples)} 组</span>`).join('');
    }
    async function checkDatabase(){try{databaseStatus(await api('/admin/database'));}catch(error){if(error.name!=='AbortError')$('#problem-db-message').textContent='无法检查数据库：'+error.message;}}
    ctx.on($('#problem-db-init'),'click',async()=>{
      const button=$('#problem-db-init');if(button.disabled)return;button.disabled=true;button.textContent='正在初始化…';
      try{const data=await api('/admin/database/init',{method:'POST',body:'{}'});databaseStatus(data,data.message);page=1;await run();}
      catch(error){if(error.name!=='AbortError')$('#problem-db-message').textContent='初始化失败：'+error.message;}
      finally{if(!ctx.signal.aborted){button.disabled=false;button.textContent='初始化数据库';}}
    });
    const active=task=>['queued','running'].includes(task.status);
    const fullPlatform=()=>$('#sync-scope').value==='platform';
    function busy(value){$('#problem-sync-fields').disabled=value;$('#sync-submit').textContent=value?'正在拉取…':fullPlatform()?'拉取该平台全部题目':'开始拉取';}
    let previousFull=false;
    function scopeChanged(){
      const full=fullPlatform();
      $('#sync-contest-label').hidden=full;$('#sync-contest').disabled=full;$('#sync-contest').required=!full;
      $('#sync-problems-label').hidden=full;$('#sync-problems').disabled=full;
      $('#sync-limit-label').textContent=full?'每批处理题数':'最多拉取题数';
      if(full!==previousFull)$('#sync-limit').value=full?'100':'20';previousFull=full;
      $('#sync-submit').textContent=full?'拉取该平台全部题目':'开始拉取';
      $('#sync-mode-note').textContent=full?'先导入所选平台公开题目目录，再自动逐批拉取全部题面与样例；每批题数不是总数量上限。全量采集可能持续数小时，默认跳过已采集题目，可在同步任务取消；再次运行会继续未完成的题目。':'默认跳过已采集的题目。题数为本次上限；离开页面后后台任务继续执行。';
    }
    function message(text){$('#sync-status').hidden=false;$('#sync-message').textContent=text;}
    function platformChanged(){
      const cf=$('#sync-platform').value==='codeforces';
      $('#sync-contest').placeholder=cf?'例如 1843':'例如 abc370';
      $('#sync-contest').pattern=cf?'[1-9][0-9]{0,4}':'[A-Za-z0-9_-]{1,100}';
      $('#sync-contest').inputMode=cf?'numeric':'text';
      $('#sync-contest-hint').textContent=cf?'填写普通公开比赛 ID，例如 1843；暂不支持 Gym。':'填写比赛 ID，例如 abc370。';
      $('#sync-problems').placeholder=cf?'例如 1843A, 1843B':'例如 abc370_a, abc370_b';
      $('#sync-language').disabled=cf;
      if(cf)$('#sync-language').value='en';
    }
    function renderTask(task){
      const state={queued:'等待拉取',running:'正在拉取',completed:'拉取完成',partial:'部分题目拉取失败',failed:'拉取失败',cancelled:'已取消'}[task.status]||task.status;
      const result=task.result||{},progress=task.progress||{},name=task.platform==='codeforces'?'Codeforces':'AtCoder';
      message(`${name}${result.scope==='platform'?' · 全平台':result.contest_id?' · '+result.contest_id:''} · ${state} · 任务 #${task.id}`);
      const bar=$('#sync-progress');bar.hidden=!active(task)&&!progress.total;
      bar.max=Math.max(1,progress.total||0);
      if(progress.total)bar.value=progress.done||0;else bar.removeAttribute('value');
      $('#sync-summary').textContent=progress.phase==='metadata'?`正在导入题目目录 ${progress.metadata_done||0} / ${progress.metadata_total||0} 题`:task.result&&(!active(task)||progress.total)?`已处理 ${progress.done||0} / ${progress.total||0} 题 · 成功 ${result.success_count||0} 题 · 失败 ${result.failure_count||0} 题 · 样例 ${result.sample_count||0} 组 · 跳过 ${result.skipped_count||0} 题 · 剩余待拉取 ${result.remaining_count||0} 题${result.scope==='platform'?' · 批次 '+(progress.batch||0)+' / '+(result.batch_count||0):''}${active(task)&&progress.problem_id?' · 当前 '+progress.problem_id:''}`:result.scope==='platform'?'正在读取全平台题目目录…':'正在读取比赛题目列表…';
      const errors=[...(result.error?[result.error]:[]),...(result.failures||[]).map(row=>`${row.problem_id}：${row.error}`)];
      $('#sync-errors').hidden=!errors.length;
      $('#sync-error-list').innerHTML=errors.map(text=>`<li>${esc(text)}</li>`).join('');
      if(result.failure_details_truncated)$('#sync-error-list').innerHTML+='<li>仅显示前 100 条错误；完整失败记录保存在数据库中。</li>';
      busy(active(task));
    }
    async function checkTask(){
      if(timer!=null){ctx.clearTimeout(timer);timer=null;}
      try{
        const rows=await api('/tasks');
        const task=taskId?rows.find(row=>row.id===taskId):rows.find(row=>row.kind==='题目采集'&&active(row));
        if(!task){
          if(taskId){message('任务记录已不可用，服务可能已重启。已入库题目会保留，可重新拉取未完成的题目。');$('#sync-progress').hidden=true;}
          taskId=null;delete ctx.memory.problemSyncTaskId;busy(false);return;
        }
        taskId=task.id;ctx.memory.problemSyncTaskId=taskId;renderTask(task);
        if(active(task)){
          if((task.result?.metadata_count||0)>publishedMetadata||(task.result?.completed_batches||0)>completedBatches){
            publishedMetadata=task.result.metadata_count||0;completedBatches=task.result.completed_batches||0;
            await checkDatabase();await run();
          }
          timer=ctx.setTimeout(checkTask,3000);
        }
        else{taskId=null;delete ctx.memory.problemSyncTaskId;await checkDatabase();if(task.result?.success_count||task.result?.metadata_count){page=1;await run();}}
      }catch(error){
        if(error.name==='AbortError')return;
        message('无法读取任务进度：'+error.message+'。可前往同步任务查看。');
        if(taskId)timer=ctx.setTimeout(checkTask,6000);else busy(false);
      }
    }
    ctx.on($('#sync-platform'),'change',platformChanged);platformChanged();
    ctx.on($('#sync-scope'),'change',scopeChanged);scopeChanged();
    ctx.on($('#problem-sync-form'),'submit',async event=>{
      event.preventDefault();if($('#problem-sync-fields').disabled||!$('#problem-sync-form').reportValidity())return;
      const problemIds=fullPlatform()?[]:[...new Set($('#sync-problems').value.trim().split(/[\s,，]+/).filter(Boolean))];
      if(problemIds.length>100){message('最多指定 100 个题号。');return;}
      const payload={platform:$('#sync-platform').value,scope:$('#sync-scope').value,language:$('#sync-language').value,refresh:$('#sync-refresh').checked};
      if(fullPlatform())payload.batch_size=Number($('#sync-limit').value);
      else Object.assign(payload,{contest_id:$('#sync-contest').value.trim(),limit:Number($('#sync-limit').value),problem_ids:problemIds});
      busy(true);message('正在提交拉取任务…');$('#sync-submit').textContent='提交中…';
      $('#sync-progress').hidden=true;$('#sync-summary').textContent='';$('#sync-errors').hidden=true;
      try{
        const response=await api('/admin/problems/sync',{method:'POST',body:JSON.stringify(payload)});
        if(!response.task?.id)throw Error('接口未返回任务 ID，请在同步任务中确认。');
        taskId=response.task.id;ctx.memory.problemSyncTaskId=taskId;publishedMetadata=0;completedBatches=0;
        message(response.task.merged?'正在查看已有的拉取任务…':'任务已提交，正在获取进度…');
        await checkTask();
      }catch(error){
        if(error.name==='AbortError')return;
        message('提交失败：'+error.message);busy(false);
        if(error.status===409||!error.status)await checkTask();
      }
    });
    await Promise.all([checkTask(),checkDatabase()]);
  }
  await load();return {};
}
