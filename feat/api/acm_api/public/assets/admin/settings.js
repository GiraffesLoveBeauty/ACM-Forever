export async function enter(ctx){
  const {root,$,api,esc}=ctx;let admins={root:[],admins:[],can_manage:false};
  root.innerHTML='<section class="admin-panel"><h2>外观</h2><p class="muted">后台菜单固定。自助调色仅保存在当前浏览器。</p><button class="btn" id="appearance">打开自助调色</button><form id="appearance-form" class="filters"><label>字号比例<input id="font-scale" type="number" min="0.8" max="1.5" step="0.05" value="1"></label><button class="btn primary">保存字号</button></form></section><section class="admin-panel"><h2>比赛播报</h2><p class="muted">按北京时间每日播报近期 Codeforces 比赛，发送到 QQBot 通知群。</p><form id="report-form" class="filters"><label>时间<input id="contest-time" type="time"></label><button class="btn primary">保存时间</button><button class="btn" type="button" id="disable-report">关闭播报</button></form><p id="report-group" class="muted"></p></section><section class="admin-panel"><h2>QQBot 管理员</h2><p class="muted">仅用于 QQ 群中的 ACM 管理命令，与 Web 角色分别管理。全局 QQBot Root 不能从此处移除。</p><div id="bot-roots"></div><div id="bot-admins" class="list"></div><form id="bot-admin-form" class="filters"><label>管理员 QQ<input id="bot-admin-qq" inputmode="numeric" placeholder="4–12 位数字"></label><button class="btn" id="add-bot-admin">添加到名单</button></form><button class="btn primary" id="save-bot-admins">保存 QQBot 管理员</button></section><p id="settings-message" role="status"></p>';
  const message=text=>{$('#settings-message').textContent=text};
  const run=fn=>async event=>{event?.preventDefault();try{await fn()}catch(error){if(error.name!=='AbortError')message(error.message)}};
  function render(){
    $('#bot-roots').textContent='QQBot Root：'+(admins.root.join('、')||'尚未配置');
    $('#bot-admins').innerHTML=admins.admins.map((id,index)=>`<div class="list-item"><span>QQ ${esc(id)}</span><button class="btn" data-remove-admin="${index}" ${admins.can_manage?'':'disabled'}>移除</button></div>`).join('')||'<p class="muted">暂无额外 QQBot 管理员。</p>';
    $('#save-bot-admins').disabled=$('#add-bot-admin').disabled=!admins.can_manage;
  }
  $('#appearance').onclick=()=>window.ACMTheme.open();
  ctx.on($('#appearance-form'),'submit',run(async()=>{await api('/ui/preferences',{method:'PUT',body:JSON.stringify({font_scale:$('#font-scale').value})});document.documentElement.style.setProperty('--font-scale',$('#font-scale').value);message('字号已保存。')}));
  ctx.on($('#report-form'),'submit',run(async()=>{if(!$('#contest-time').value)throw Error('请选择时间或点击关闭播报。');await api('/settings/contest-report',{method:'PUT',body:JSON.stringify({time:$('#contest-time').value})});message('比赛播报时间已保存。')}));
  $('#disable-report').onclick=run(async()=>{await api('/settings/contest-report',{method:'PUT',body:JSON.stringify({time:''})});$('#contest-time').value='';message('比赛播报已关闭。')});
  ctx.on($('#bot-admin-form'),'submit',event=>{event.preventDefault();const qq=$('#bot-admin-qq').value.trim();if(!/^\d{4,12}$/.test(qq)){message('请输入有效 QQ 号。');return;}if(!admins.admins.includes(qq)&&!admins.root.includes(qq))admins.admins.push(qq);$('#bot-admin-qq').value='';render()});
  ctx.on(root,'click',event=>{const button=event.target.closest('[data-remove-admin]');if(button&&admins.can_manage){admins.admins.splice(Number(button.dataset.removeAdmin),1);render()}});
  $('#save-bot-admins').onclick=run(async()=>{const result=await api('/admins',{method:'PUT',body:JSON.stringify({admins:admins.admins})});admins={...admins,...result};render();message('QQBot 管理员配置已保存。')});
  const [preferences,report,config]=await Promise.all([api('/ui/preferences'),api('/settings/contest-report'),api('/admins')]);
  $('#font-scale').value=preferences.font_scale||1;$('#contest-time').value=report.time||'';$('#report-group').textContent='通知群：'+(report.group_id||'未配置，请在 QQ 中配置通知群');admins=config;render();return {};
}
