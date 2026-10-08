const difficultySpecs={
  codeforces:{kind:'number',min:800,max:3500,step:100,value:1000,unit:'Rating',help:'Codeforces 使用数字 Rating，单区间匹配目标值 ±100。'},
  luogu:{kind:'select',values:['未评定','入门','普及-','普及/提高-','普及+/提高','提高+/省选-','省选/NOI-','NOI/NOI+/CTSC'],value:'普及-',help:'洛谷使用官方难度标签，三个训练区对应相邻等级。'},
  atcoder:{kind:'number',min:0,max:4000,step:100,value:800,unit:'Difficulty',help:'AtCoder 使用 AtCoder Problems 估算 Difficulty，单区间匹配目标值 ±100。'},
  nowcoder:{kind:'select',values:['1星','2星','3星','4星','5星'],value:'2星',help:'牛客使用题目难度星级，三个训练区对应相邻星级。'}
};

export async function enter(ctx){
  const {root,$,api,esc,auth}=ctx;let historyVersion=0;
  root.innerHTML=`<section class="admin-panel"><form id="training-filters" class="filters">
    <label id="training-owner-label">成员 QQ<input id="owner" inputmode="numeric" value="${esc(ctx.params.get('qq_id')||auth.qq_id||'')}"></label>
    <label>平台<select id="platform"><option value="">全部平台（不筛难度）</option><option value="codeforces">Codeforces</option><option value="luogu">洛谷</option><option value="atcoder">AtCoder</option><option value="nowcoder">牛客</option></select></label>
    <label>算法标签 / 题名 / 题号<input id="tag"></label>
    <label class="chip"><input id="weak-tag" type="checkbox"> 按弱项训练</label>
    <label>难度<span id="difficulty-wrap"></span></label>
    <button class="btn primary" id="generate">重新生成今日训练</button>
    </form><p class="muted" id="difficulty-help"></p><p id="training-message" role="status"></p></section>
    <section class="grid three">
      <article class="card"><div class="label" id="foundation-label"></div><h2>稳定基础</h2><p class="muted">低于目标难度，练习速度与完整度。</p><div id="foundation" class="empty">等待生成</div></article>
      <article class="card"><div class="label" id="core-label"></div><h2>主训练</h2><p class="muted">贴近目标难度，完成今天的核心训练。</p><div id="core" class="empty">等待生成</div></article>
      <article class="card"><div class="label" id="challenge-label"></div><h2>突破上限</h2><p class="muted">略高于目标难度，试探新的能力边界。</p><div id="challenge" class="empty">等待生成</div></article>
    </section><section class="admin-panel"><h2>挑战历史</h2><div id="history" class="list"></div></section>`;
  if(auth.role==='member'){$('#owner').value=auth.qq_id;$('#training-owner-label').hidden=true;}
  function zones(){
    const spec=difficultySpecs[$('#platform').value];if(!spec)return [null,null,null];
    const value=$('#difficulty').value;
    if(spec.kind==='number'){const base=Math.max(spec.min,Math.min(spec.max,Number(value)||spec.value));return [Math.max(spec.min,base-150),base,Math.min(spec.max,base+150)];}
    const index=spec.values.indexOf(value);return [spec.values[Math.max(0,index-1)],value,spec.values[Math.min(spec.values.length-1,index+1)]];
  }
  function labels(){zones().forEach((value,i)=>{$('#'+['foundation','core','challenge'][i]+'-label').textContent=['巩固区','同段区','挑战区'][i]+' · '+(value??'不限');});}
  function difficulty(){
    const spec=difficultySpecs[$('#platform').value];
    $('#difficulty-wrap').innerHTML=!spec?'<select id="difficulty" disabled><option value="">不限难度</option></select>':spec.kind==='number'?`<input id="difficulty" type="number" min="${spec.min}" max="${spec.max}" step="${spec.step}" value="${spec.value}" aria-label="${spec.unit}">`:`<select id="difficulty">${spec.values.map(value=>`<option ${value===spec.value?'selected':''}>${esc(value)}</option>`).join('')}</select>`;
    $('#difficulty-help').textContent=spec?.help||'全部平台模式不应用难度筛选。';labels();
  }
  async function history(){
    const version=++historyVersion;
    try{const rows=await api('/challenge/list?qq_id='+encodeURIComponent($('#owner').value.trim()));if(version!==historyVersion)return;
      $('#history').innerHTML=rows.map(row=>`<article class="list-item"><span><b>${esc(row.problem_name||row.problem_id)}</b><br><small class="muted">${esc(row.platform)} · ${esc(row.status)} · 难度 ${esc(row.problem_rating??'未知')}</small></span><span class="muted">${esc(row.created_at)}</span></article>`).join('')||'<p class="empty">暂无挑战记录。</p>';
    }catch(error){if(error.name!=='AbortError'&&version===historyVersion)$('#history').textContent=error.message;}
  }
  ctx.on($('#platform'),'change',difficulty);ctx.on($('#difficulty-wrap'),'input',labels);ctx.on($('#owner'),'change',history);
  ctx.on($('#training-filters'),'submit',async event=>{
    event.preventDefault();const button=$('#generate');if(button.disabled)return;
    const owner=$('#owner').value.trim(),platform=$('#platform').value,weak=$('#weak-tag').checked;let tag=$('#tag').value;
    if(!/^\d{4,12}$/.test(owner)){$('#training-message').textContent='请填写有效的成员 QQ。';return;}
    if(platform&&!$('#difficulty').value)return;
    button.disabled=true;$('#training-message').textContent='正在生成训练…';labels();const values=zones();
    try{for(const [i,id] of ['foundation','core','challenge'].entries()){
      if(ctx.signal.aborted)return;
      $('#'+id).textContent='正在生成…';
      try{const row=await api('/challenge/start',{method:'POST',body:JSON.stringify({platform,tag,difficulty:values[i],owner_qq_id:owner,weak_tag:weak})});
        if(weak&&row.weak_tag)tag=row.weak_tag;
        $('#'+id).innerHTML=`<b>${esc(row.problem_name||row.problem_id)}</b><br><span class="chip">${esc(row.platform)}</span> <span class="chip">难度 ${esc(row.problem_rating??'未知')}</span><p class="muted">${esc(row.recommendation_reason||'符合训练条件')}</p><a class="btn primary" href="${esc(row.problem_url)}" target="_blank" rel="noopener">打开题目 →</a>`;
      }catch(error){if(error.name==='AbortError')return;$('#'+id).textContent=error.message;}
    }await history();$('#training-message').textContent='训练已生成，挑战历史已刷新。';
    }finally{button.disabled=false;}
  });
  difficulty();await history();return {};
}
