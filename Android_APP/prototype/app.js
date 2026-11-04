// Real responses only. Local storage never contains passwords, cookies or CSRF tokens.
const OFFLINE_PREVIEW = new URLSearchParams(location.search).get('offline') === '1';
const OFFLINE_MESSAGE = '离线预览：未连接后端';
const state = {view:'forum',category:'',sort:'latest',days:'7',platform:'',query:'',user:null,role:'',csrf:'',serial:0,memberId:'',postId:0,loginBusy:false,loginIdentifier:'',loginDestination:'account',mustChangePassword:false,actionBusy:false,problemState:'',rankSort:'total_count',rankPlatforms:['codeforces','luogu','atcoder','nowcoder','cjlu']};
const compose = {id:0,title:'',body:'',category:0,revision:0,saved:0};
const comment = {postId:0,body:'',parent:0};
let composeSaving = null;
let sessionRevision = 0, detailRevision = 0;
let searchScope = 'forum', searchReturn = 'forum', filterRevision = 0;
state.loginIdentifier = localStorage.getItem('acm_remembered_account') || '';
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const DEFAULT_API_BASE = 'https://cjluacmpanel.tail1b9e55.ts.net';
let apiBase = DEFAULT_API_BASE, updateUrl = localStorage.getItem('acm_update_url') || '';
let capabilities = null, checkedAt = 0, categories = [];
const APP_VERSION_CODE = 13;
let updateChecking = false;
class RequestFailure extends Error { constructor(title) { super(title); this.title = title; } }
function failure(title) { return new RequestFailure(title); }
function failureTitle(error) { return error?.title || '请求失败'; }
function errorBox(title, height = 320, retry = true) {
  return `<div class="error-box" role="alert" style="min-height:${height}px"><strong>${esc(title)}</strong>${retry ? '<button class="retry-button">重试</button>' : ''}</div>`;
}
function bindRetry(container) { container.querySelectorAll('.retry-button').forEach(button => button.onclick = () => show(state.view)); }
function replaceError(container, error, height = 320) {
  const retained = Math.max(height, container.getBoundingClientRect().height);
  container.innerHTML = errorBox(failureTitle(error), retained); bindRetry(container);
}
function checkedHttps(value, root = false) {
  if (!value.trim()) return '';
  let url; try { url = new URL(value.trim()); } catch { throw failure('地址格式错误'); }
  if (url.protocol !== 'https:' || url.username || url.password || url.hash || root && (url.pathname !== '/' || url.search)) throw failure('请输入有效的HTTPS地址');
  return root ? url.origin : url.href;
}
try { apiBase = checkedHttps(localStorage.getItem('acm_api_base') || '', true) || DEFAULT_API_BASE; }
catch { localStorage.removeItem('acm_api_base'); }
async function request(path, method = 'GET', body) {
  if (OFFLINE_PREVIEW) throw failure(OFFLINE_MESSAGE);
  if (!navigator.onLine) throw failure('无网络');
  if (!apiBase) throw failure('未配置服务器');
  const controller = new AbortController(), timer = setTimeout(() => controller.abort(), 15000);
  const revision = sessionRevision, base = apiBase;
  try {
    const headers = {Accept: 'application/json'};
    if (body !== undefined) { if(!(body instanceof FormData))headers['Content-Type'] = 'application/json'; if (state.csrf) headers['X-CSRF-Token'] = state.csrf; }
    const response = await fetch(apiBase + path, {method, headers, credentials: 'include', redirect: 'error', signal: controller.signal, ...(body === undefined ? {} : {body: body instanceof FormData ? body : JSON.stringify(body)})});
    if(revision!==sessionRevision||base!==apiBase)throw failure('会话已改变，请重试');
    if (!response.ok) {
      const status = response.status;
      if (status === 401) clearAccount();
      if (status === 428) state.mustChangePassword = true;
      const content = status === 404 && /\/(members\/[A-Za-z0-9_-]{32}(\/posts)?|posts\/\d+)(\?|$)/.test(path);
      let message = ''; try { message = (await response.json()).message || ''; } catch {}
      throw failure(content ? '内容不存在' : status === 404 || status === 405 ? '无API接口' : status === 401 ? path === '/api/auth/login' ? message || '账号或密码错误' : '未登录或登录已失效' : status === 403 ? '无访问权限' : status === 428 ? '请修改初始密码' : status === 429 ? '请求过于频繁' : status === 410 ? '功能已下线' : status >= 500 ? '服务器异常' : message || '请求失败');
    }
    try { return await response.json(); } catch { throw failure('数据格式异常'); }
  } catch (error) {
    if (error instanceof RequestFailure) throw error;
    throw failure(!navigator.onLine ? '无网络' : error.name === 'AbortError' ? '请求超时' : '无法连接服务器');
  } finally { clearTimeout(timer); }
}
async function supports(feature) {
  if (!capabilities || Date.now() - checkedAt > 60000) {
    try {
      const result = await request('/api/mobile/v1/capabilities');
      if (result.api_version !== 1 || !result.features || typeof result.features !== 'object') throw failure('数据格式异常');
      capabilities = result.features;
    } catch (error) { if (failureTitle(error) !== '无API接口') throw error; capabilities = {}; }
    checkedAt = Date.now();
  }
  return capabilities[feature] === true;
}
async function mobile(feature, path, method = 'GET', body) {
  if (!await supports(feature)) throw failure('无API接口');
  return request('/api/mobile/v1' + path, method, body);
}
function rows(result, key = 'rows') {
  if (!Array.isArray(result?.[key])) throw failure('数据格式异常');
  return result[key];
}
function empty(text) { return `<div class="empty">${esc(text)}</div>`; }
function showInfo(title, message) {
  if(document.getElementById('info-dialog').open&&document.getElementById('info-title').textContent===title)return;
  document.getElementById('info-title').textContent = title;
  document.getElementById('info-text').textContent = message;
  document.getElementById('info-dialog').showModal();
}
function showFailure(error) {
  document.getElementById('account-detail-title').textContent = '请求失败';
  document.getElementById('account-detail-content').innerHTML = errorBox(failureTitle(error), 180, false);
  document.getElementById('account-detail-dialog').showModal();
}
async function show(view) {
  if (state.loginBusy) return;
  if(view==='admin')return;
  if(state.view==='compose'&&view!=='compose'&&compose.revision!==compose.saved&&state.csrf){
    if(confirm('保存当前草稿后离开？点击取消则保留本次编辑并离开。')){try{await saveCompose();}catch(error){showFailure(error);return;}}
  }
  state.view = view; const serial = ++state.serial;
  if (view !== 'forum') document.getElementById('filter-dialog').close();
  document.querySelectorAll('.view').forEach(node => node.classList.toggle('active', node.id === view + '-view'));
  document.querySelectorAll('.bottom button').forEach(node => node.classList.toggle('active', node.dataset.view === view));
  const search = document.getElementById('global-search'); search.disabled = !['forum','rank','problems','search'].includes(view);
  search.placeholder = ({forum:'搜索论坛话题',rank:'搜索公开昵称',problems:'搜索题名或标签',account:'账号设置',mine:'个人中心',compose:'发帖编辑',member:'成员主页'}[view] || '搜索');
  if (view === 'search') { renderSearch(); return; }
  const container = document.getElementById(({forum:'posts',rank:'ranks',problems:'problems',mine:'profile-area',account:'account-area',member:'member-area',detail:'detail-card',compose:'compose-area'})[view]);
  container.style.minHeight = ['mine','member'].includes(view) ? '440px' : view === 'compose' ? '600px' : '320px';
  container.innerHTML = '<div class="empty" style="min-height:320px">正在加载…</div>';
  window.scrollTo(0, 0);
  try {
    const result = await ({forum:renderForum,rank:renderRank,problems:renderProblems,mine:()=>renderProfile(true),member:()=>renderProfile(false),account:renderAccount,compose:renderCompose,detail:renderDetail})[view]();
    if (serial !== state.serial) return;
    container.innerHTML = (state.query && ['forum','rank','problems'].includes(view) ? `<h3>搜索结果 · ${esc(state.query)}</h3>` : '') + result; bindActions(container); bindRetry(container); readerMath(container);
    if (view === 'compose') bindCompose();
    if (view === 'account') { bindLogin(); bindPasswordForm(); }
    if (view === 'detail') bindPostDetail();
    if (view === 'rank') bindRankPager();
  } catch (error) {
    if (serial !== state.serial) return;
    replaceError(container, error, ['mine','member'].includes(view) ? 440 : view === 'compose' ? 600 : 320);
    if (view === 'account') { container.insertAdjacentHTML('beforeend', accountRow('connection','检查更新','检查新版本')); bindActions(container); }
  }
}
async function renderForum() {
  const suffix = '?' + new URLSearchParams({q:state.query, category:state.category, sort:state.sort, page:'1', page_size:'12'});
  const path = await supports('public_member_ids') ? '/api/mobile/v1/forum/posts' : '/api/forum/posts';
  const result = await request(path + suffix), posts = rows(result);
  return posts.map(post => `<article class="card"><button class="card-link" data-post="${esc(post.id)}"><span class="tag">${esc(post.category_name)}</span><h3>${esc(post.title)}</h3><p>${esc(post.excerpt)}</p></button><div class="foot"><button class="link" data-member="${esc(post.author_public_member_id || '')}">${esc(post.author_name)}</button><span>${esc(post.comments_count)} 评论</span><span>${esc(post.likes_count)} 赞</span></div></article>`).join('') || empty('暂无符合条件的话题');
}
async function renderRank() {
  const path = await supports('public_member_ids') ? '/api/mobile/v1/leaderboard' : '/api/community/leaderboard';
  const range=state.days,size=state.rankPageSize||20,page=state.rankPage||1;
  const base=path+'?'+new URLSearchParams({days:range==='today'?'7':range,period:range==='today'?'today':'',positive_only:'1',sort:state.rankSort,platforms:state.rankPlatforms.join(','),search:state.query});
  let result=await request(base+`&page=${page}&page_size=${size}`);
  if(range==='today'&&(result.period!=='today'||result.timezone!=='Asia/Shanghai'))throw failure('无API接口');
  if(!Number.isInteger(result.total)||result.total<0)throw failure('数据格式异常');
  if(result.positive_only!==true){
    const all=[];
    for(let i=1;i<=Math.max(1,Math.ceil(result.total/100));i++){
      const chunk=await request(base+`&page=${i}&page_size=100`);
      all.push(...rows(chunk).filter(member=>Number.isInteger(member.total_count)&&member.total_count>0));
    }
    const current=rankPageNumber(page,Math.max(1,Math.ceil(all.length/size)));
    result={rows:all.slice((current-1)*size,current*size),total:all.length,page:current,positive_only:true};
  }
  const pages=Math.max(1,Math.ceil(result.total/size)),current=rankPageNumber(result.page??page,pages);
  state.rankPage=current;
  const list=rows(result).filter(member=>member.total_count>0).map((member,i) => `<button class="card rank-row" style="width:100%;text-align:left" data-member="${esc(member.public_member_id || '')}"><span class="rank-number">${(current-1)*size+i+1}</span><span class="rank-copy"><b>${esc(member.name)}</b><small>${esc(member.status)}</small></span><span class="rank-total">${esc(member.total_count)}<small>AC题</small></span></button>`).join('')||empty('暂无符合条件的成员');
  return list+`<div class="rank-pager" aria-label="排行榜分页"><button id="rank-prev" ${current===1?'disabled':''}>上一页</button><label class="rank-position">第<input id="rank-page" aria-label="输入排行榜页码" inputmode="numeric" value="${current}">页<span>（共${pages}页）</span></label><label class="rank-size">一页<select id="rank-page-size" aria-label="排行榜每页数量">${[5,10,20,100].map(value=>`<option ${value===size?'selected':''}>${value}</option>`).join('')}</select>项</label><button id="rank-next" ${current===pages?'disabled':''}>下一页</button></div>`;
}
function rankPageNumber(value,pages){const raw=String(value).trim();const number=/^[0-9]+$/.test(raw)?Number(raw):NaN;return Number.isSafeInteger(number)&&number>=1&&number<=pages?number:1;}
function bindRankPager(){
  const input=document.getElementById('rank-page');if(!input)return;
  const pages=Math.max(1,Number(input.closest('.rank-pager').querySelector('.rank-position span').textContent.match(/[0-9]+/)[0]));
  const jump=()=>{const target=rankPageNumber(input.value,pages);input.value=target;if(target!==(state.rankPage||1)){state.rankPage=target;show('rank');}};
  input.onkeydown=event=>{if(event.key==='Enter'){event.preventDefault();jump();}};input.onchange=jump;
  document.getElementById('rank-prev').onclick=()=>{if(state.rankPage>1){state.rankPage--;show('rank');}};
  document.getElementById('rank-next').onclick=()=>{if(state.rankPage<pages){state.rankPage++;show('rank');}};
  document.getElementById('rank-page-size').onchange=event=>{state.rankPageSize=Number(event.target.value);state.rankPage=1;show('rank');};
}
async function renderProblems() {
  if (OFFLINE_PREVIEW) throw failure(OFFLINE_MESSAGE);
  if (!navigator.onLine) throw failure('无网络'); if (!apiBase) throw failure('未配置服务器'); if (!state.csrf) throw failure('未登录');
  const result = await request('/api/me/problems?' + new URLSearchParams({page:'1',page_size:'20',platform:state.platform,tag:state.query,state:state.problemState}));
  return rows(result,'items').map(problem => `<article class="card"><h3>${esc(problem.problem_name || problem.problem_id)}</h3><p>${esc(problem.platform)} · ${esc(problem.problem_rating ?? '难度未知')}</p><p>${esc(problem.tags)}</p><button class="link" data-problem="${esc(problem.problem_id)}" data-problem-platform="${esc(problem.platform)}">查看题面与样例</button><button class="menu-action" data-favorite="${esc(problem.problem_id)}" data-problem-platform="${esc(problem.platform)}" data-current="${!!problem.is_favorite}">${problem.is_favorite?'★ 已收藏 · 取消':'☆ 收藏题目'}</button></article>`).join('') || empty('暂无符合条件的题目');
}
function stats(profile, sparse = false) {
  const names = {codeforces:'Codeforces',luogu:'洛谷',atcoder:'AtCoder',nowcoder:'牛客',cjlu:'校 OJ'};
  // The existing private statistics API omits platforms with no submissions.
  if (!profile?.platform_counts || Object.keys(names).some(key => !(sparse && !(key in profile.platform_counts)) && (!Number.isInteger(profile.platform_counts[key]) || profile.platform_counts[key] < 0)) || !Number.isInteger(profile.total_count)) throw failure('数据格式异常');
  return '<div class="stat-grid">' + [...Object.entries(names).map(([key,name]) => [name,profile.platform_counts[key] ?? 0]),['合计',profile.total_count]].map(([name,count]) => `<div class="stat-card"><small>${name}</small><strong>${count}</strong></div>`).join('') + '</div>';
}
async function renderProfile(own) {
  const prefix = own ? 'profile' : 'member';
  document.getElementById(own ? 'public-name' : 'member-name').textContent = '资料不可用';
  const cover = document.querySelector('#' + (own ? 'mine' : 'member') + '-view .public-cover p');
  cover.textContent = '';
  let profile = null, profileError = null, posts = null, postsError = null, mottoError = null;
  try {
    if (OFFLINE_PREVIEW) throw failure(OFFLINE_MESSAGE);
    if (own && !state.csrf) { if (!navigator.onLine) throw failure('无网络'); throw failure(apiBase ? '未登录' : '未配置服务器'); }
    if (!own && !state.memberId) throw failure('无API接口');
    if (own) {
      const result = await request('/api/me/profile');
      if (!result.user?.name) throw failure('数据格式异常');
      profile = {name:result.user.name, avatar_url:result.user.avatar_url, platform_counts:result.platform_counts,total_count:result.total_count};
    } else {
      profile = await mobile('member_profiles', '/members/' + encodeURIComponent(state.memberId));
      if (!profile.public_member_id || !profile.name) throw failure('数据格式异常');
    }
  } catch (error) { profileError = error; }
  if (profile && !profileError) {
    document.getElementById(own ? 'public-name' : 'member-name').textContent = profile.name;
  }
  try {
    if (OFFLINE_PREVIEW) throw failure(OFFLINE_MESSAGE);
    if (own) {
      if (!state.csrf) throw failure('未登录');
      const result = await request('/api/forum/mine/posts');
      if (!Array.isArray(result)) throw failure('数据格式异常');
      posts = result.filter(post => post.status === 'published');
    } else if (profile) posts = rows(await mobile('member_posts', '/members/' + encodeURIComponent(profile.public_member_id) + '/posts?page=1&page_size=12'));
    else throw profileError;
  } catch (error) { postsError = error; }
  if (profile) {
    try { if (own) profile.motto = (await mobile('own_public_profile','/me/public-profile')).motto; if (typeof profile.motto !== 'string') throw failure('数据格式异常'); }
    catch (error) { mottoError = error; }
    if (mottoError) cover.innerHTML = errorBox(failureTitle(mottoError),64,false);
    else cover.textContent = profile.motto ? '座右铭 · ' + profile.motto : '暂无座右铭';
  }
  let counts; try { counts = profileError ? errorBox(failureTitle(profileError),264) : stats(profile,own); } catch (error) { counts = errorBox(failureTitle(error),264); }
  if (profileError) cover.innerHTML = errorBox(failureTitle(profileError),64,false);
  return `<article class="card"><h3>各平台通过题数</h3>${counts}</article><article class="card"><h3>发布的论坛话题</h3>${posts === null ? errorBox(failureTitle(postsError),180) : posts.map(post => `<button class="menu-action" data-post="${esc(post.id)}">${esc(post.title)}</button>`).join('') || empty('暂无已发布话题')}</article>${own ? accountRow('account','账号设置','资料与安全') : ''}`;
}
function accountRow(action, name, subtitle = '') { return `<button class="account-row" data-account-action="${esc(action)}"><span>${esc(name)}</span><small>${esc(subtitle)} ›</small></button>`; }
const privateResults = {};
async function renderAccount() {
  if (!state.csrf) return `<div class="card"><h3>账号登录</h3>${!apiBase || !navigator.onLine ? errorBox(!navigator.onLine ? '无网络' : '未配置服务器',180,false) : `<form id="login-form" class="login-demo"><label>用户名 / QQ</label><input id="qq" value="${esc(state.loginIdentifier)}" autocomplete="username" required><label>密码</label><input id="password" type="password" autocomplete="current-password" required><label><input id="remember-me" type="checkbox" style="width:auto" ${localStorage.getItem('acm_remember_account')==='1'?'checked':''}>记住我（记住账号）</label><label><input id="save-password" type="checkbox" style="width:auto">保存密码</label><label><input id="auto-login" type="checkbox" style="width:auto" ${localStorage.getItem('acm_auto_login')===apiBase?'checked':''}>自动登录</label><p class="notice">安卓 App 使用设备密钥加密保存密码；浏览器预览使用浏览器密码管理器，不支持时该选项禁用。自动登录仅恢复有效会话。</p><button class="solid">登录</button></form>`}</div>` + accountRow('connection','检查更新','检查新版本');
  const session = await request('/api/auth/me');
  if (!session.authenticated) { state.csrf = ''; state.role = ''; throw failure('未登录或登录已失效'); }
  state.role = session.role; state.csrf = session.csrf_token;
  state.mustChangePassword=!!session.must_change_password;
  if(state.mustChangePassword)return '<div class="card"><h3>首次登录，请修改初始密码</h3>'+passwordForm()+accountRow('logout','退出登录')+'</div>';
  const results = await Promise.allSettled(['/api/me/profile','/api/forum/mine/posts','/api/forum/mine/bookmarks','/api/forum/drafts'].map(path => request(path)));
  let html = ['admin','root'].includes(state.role) ? '<div class="card admin-section"><h3>管理员栏</h3>'+accountRow('admin','管理后台','成员、训练、社区与系统管理')+'</div>' : '';
  const account = results[0];
  if (account.status === 'fulfilled' && account.value.user) {
    state.user = account.value;
    html += '<div class="account-group"><h3>个人资料</h3>' + accountRow('rename','修改昵称',account.value.user.name) + accountRow('avatar','社区头像') + accountRow('motto','座右铭') + accountRow('bindings','OJ账号绑定','只读') + '</div><div class="account-group"><h3>我的学习</h3>' + accountRow('stats','通过题数') + accountRow('recent','最近AC') + accountRow('training','今日训练','三个训练区与挑战历史') + accountRow('contests','赛事复盘','逐题补题状态') + accountRow('problem-favorites','我的题目收藏') + '</div>';
  } else html += errorBox(account.status === 'rejected' ? failureTitle(account.reason) : '数据格式异常',300);
  html += '<div class="account-group"><h3>我的社区 · 仅自己可见</h3>';
  ['posts','bookmarks','drafts'].forEach((action,index) => {
    const name = ['我的话题','我的收藏','草稿'][index], result = results[index+1];
    if (result.status === 'fulfilled' && Array.isArray(result.value)) { privateResults[action] = result.value; html += accountRow(action,name,result.value.length+' 条'); }
    else html += `<p>${name}</p>` + errorBox(result.status === 'rejected' ? failureTitle(result.reason) : '数据格式异常',64);
  });
  return html + '</div><div class="account-group"><h3>账号与应用</h3>' + accountRow('password','修改密码') + accountRow('connection','检查更新') + accountRow('about','关于ACMforever','0.1.12') + accountRow('logout','退出登录') + '</div>';
}
function bindLogin() {
  const form = document.getElementById('login-form'); if (!form) return;
  if (OFFLINE_PREVIEW) {
    form.onsubmit = event => event.preventDefault();
    form.querySelectorAll('input,button').forEach(node => node.disabled = true);
    form.insertAdjacentHTML('afterbegin', errorBox(OFFLINE_MESSAGE, 100, false));
    return;
  }
  const remember = document.getElementById('remember-me'), auto = document.getElementById('auto-login');
  const savePassword = document.getElementById('save-password');
  savePassword.disabled = typeof PasswordCredential !== 'function' || !navigator.credentials?.store;
  savePassword.onchange=()=>{if(savePassword.checked)remember.checked=true;};
  auto.onchange=()=>{if(auto.checked)remember.checked=true;else localStorage.removeItem('acm_auto_login');};
  remember.onchange=()=>{if(!remember.checked){auto.checked=false;savePassword.checked=false;localStorage.removeItem('acm_auto_login');localStorage.removeItem('acm_remembered_account');localStorage.removeItem('acm_remember_account');}};
  form.onsubmit = async event => {
    event.preventDefault(); if(state.loginBusy)return;
    const identifier = document.getElementById('qq').value.trim(), password = document.getElementById('password').value;
    if(!identifier||!password)return;
    localStorage.setItem('acm_remember_account',remember.checked?'1':'0');
    if(remember.checked)localStorage.setItem('acm_remembered_account',identifier);else localStorage.removeItem('acm_remembered_account');
    // Enable restoration only after the server confirms this login.
    const autoLogin=auto.checked, saveToManager=savePassword.checked;
    localStorage.removeItem('acm_auto_login');
    state.loginIdentifier=identifier; document.getElementById('password').value=''; form.querySelector('button').disabled=true;
    loginWaiting(true);
    const timer=setTimeout(()=>{if(state.loginBusy)document.getElementById('login-wait-message').textContent='网络响应较慢，请稍候；超时后可重试。请确认手机已接入 Tailscale 网络。';},12000);
    try {
      clearAccount();
      await request('/api/auth/login','POST',{username:identifier,...(/^[0-9]{4,12}$/.test(identifier)?{qq_id:identifier}:{}),password});
      const session=await request('/api/auth/me');
      if(!session.authenticated||typeof session.csrf_token!=='string'||!session.csrf_token)throw failure('数据格式异常');
      state.csrf=session.csrf_token;state.role=session.role;state.mustChangePassword=!!session.must_change_password;
      if(autoLogin)localStorage.setItem('acm_auto_login',apiBase);
      loginWaiting(false);await show(state.mustChangePassword?'account':state.loginDestination);
      if(saveToManager){try{await navigator.credentials.store(new PasswordCredential({id:identifier,password,name:identifier}));}catch{showInfo('密码未保存','浏览器未能安全保存密码。安卓 App 使用设备密钥加密保存。');}}
    } catch (error) {
      clearAccount();loginWaiting(false);await show('account');
      document.getElementById('account-area').insertAdjacentHTML('beforeend',errorBox(failureTitle(error),160,false));
    } finally {clearTimeout(timer);document.getElementById('login-wait-message').textContent='正在验证账号与会话，成功后自动跳转。';}
  };
}
function clearAccount() {
  ++sessionRevision;
  state.csrf='';state.role='';state.user=null;state.mustChangePassword=false;
  for(const key of Object.keys(privateResults))delete privateResults[key];
}

function searchHistory() {
  try { const items=JSON.parse(localStorage.getItem('acm_search_history')||'[]'); return Array.isArray(items)?[...new Set(items.filter(item=>typeof item==='string'&&item.trim()))].slice(0,10):[]; }
  catch { return []; }
}
function openSearch() {
  if(!['forum','rank','problems'].includes(state.view)||state.loginBusy)return;
  searchScope=state.view;searchReturn=state.view;show('search');
}
function submitSearch(value) {
  const term=value.trim();if(!term)return;
  if(localStorage.getItem('acm_record_search')!=='0')localStorage.setItem('acm_search_history',JSON.stringify([term,...searchHistory().filter(item=>item!==term)].slice(0,10)));
  state.rankPage=1;state.query=term;const input=document.getElementById('global-search');input.value=term;input.blur();return show(searchScope);
}
function renderSearch() {
  const area=document.getElementById('search-area'), history=searchHistory();
  area.innerHTML=`<h2>搜索${({forum:'话题',rank:'排名',problems:'题库'})[searchScope]}</h2><p>输入关键词后点击搜索，或点选历史搜索。</p><button class="solid" id="submit-search">搜索</button><article class="card"><h3>最近 10 条搜索</h3><div class="history-grid">${history.map((term,index)=>`<button class="history-chip" data-history="${index}">${esc(term)}</button>`).join('')||empty('暂无历史搜索')}</div></article><button class="menu-action" id="search-records">历史记录</button><button class="menu-action" id="search-history-settings">历史记录设置</button><button class="back" id="cancel-search">取消搜索</button>`;
  area.querySelectorAll('[data-history]').forEach(button=>button.onclick=()=>submitSearch(history[Number(button.dataset.history)]));
  document.getElementById('submit-search').onclick=()=>submitSearch(document.getElementById('global-search').value);
  document.getElementById('cancel-search').onclick=()=>{document.getElementById('global-search').blur();state.query='';document.getElementById('global-search').value='';show(searchReturn);};
  document.getElementById('search-records').onclick=()=>{
    detail('历史记录 · 最近 10 条',history.map((term,index)=>`<div class="account-row"><span>${esc(term)}</span><button class="link" data-delete-history="${index}">删除</button></div>`).join('')||empty('暂无历史搜索'));
    document.querySelectorAll('[data-delete-history]').forEach(button=>button.onclick=()=>{localStorage.setItem('acm_search_history',JSON.stringify(history.filter((_,index)=>index!==Number(button.dataset.deleteHistory))));document.getElementById('account-detail-dialog').close();renderSearch();});
  };
  document.getElementById('search-history-settings').onclick=()=>{
    detail('历史记录设置',`<label><input id="record-search" type="checkbox" ${localStorage.getItem('acm_record_search')!=='0'?'checked':''}>记录搜索历史（仅此设备，最多10条）</label><button class="menu-action" id="clear-search-history">清空记录</button>`);
    document.getElementById('record-search').onchange=event=>localStorage.setItem('acm_record_search',event.target.checked?'1':'0');
    document.getElementById('clear-search-history').onclick=()=>{localStorage.removeItem('acm_search_history');document.getElementById('account-detail-dialog').close();renderSearch();};
  };
}
function loginWaiting(active) {
  state.loginBusy=active;
  document.querySelector('.top').hidden=active;document.querySelector('.bottom').hidden=active;
  if(active){++state.serial;document.querySelectorAll('.view').forEach(node=>node.classList.toggle('active',node.id==='login-wait-view'));}
}
async function renderCompose() {
  const result = OFFLINE_PREVIEW ? [] : await request('/api/forum/categories'); if (!Array.isArray(result)) throw failure('数据格式异常');
  categories = result;
  if (!categories.length && !OFFLINE_PREVIEW) return empty('暂无可用分类');
  return `<form class="card compose-form" id="compose-form"><label>话题分类</label><select id="compose-category">${categories.map(item=>`<option value="${esc(item.id)}" ${Number(item.id)===compose.category?'selected':''}>${esc(item.name)}</option>`).join('')}</select><label>标题（4–120字）</label><input id="compose-title" maxlength="120" value="${esc(compose.title)}" required><label>正文（5–20000字）</label><textarea id="compose-body" maxlength="20000" required>${esc(compose.body)}</textarea><div class="format-bar"><button type="button" data-format="bold">加粗</button><button type="button" data-format="code">代码块</button><button type="button" data-format="quote">引用</button><button type="button" id="preview-compose">预览</button></div><p id="draft-state" class="notice">${compose.id&&compose.revision===compose.saved?'草稿已保存':'编辑内容尚未保存到账号'}</p><button type="button" class="menu-action" id="save-draft">保存草稿</button>${compose.id?'<button type="button" class="menu-action" id="delete-draft">删除当前草稿</button>':''}<button class="solid">提交审核</button><p class="notice">支持Markdown；提交后进入人工审核，通过后展示。</p></form>`;
}
function bindCompose() {
  const form = document.getElementById('compose-form'); if (!form) return;
  if (OFFLINE_PREVIEW) {
    const category = document.getElementById('compose-category');
    category.innerHTML = '<option value="0">离线预览：分类不可用</option>';
    category.disabled = true;
    form.insertAdjacentHTML('afterbegin', errorBox('离线预览：可编辑、预览正文；不能保存或发布', 100, false));
    document.getElementById('save-draft').disabled = true;
    form.querySelector('button.solid').disabled = true;
  }
  const sync=()=>{compose.title=document.getElementById('compose-title').value;compose.body=document.getElementById('compose-body').value;compose.category=Number(document.getElementById('compose-category').value);++compose.revision;document.getElementById('draft-state').textContent='有未保存的修改';};
  compose.category=Number(document.getElementById('compose-category').value);
  ['compose-title','compose-body','compose-category'].forEach(id=>document.getElementById(id).addEventListener('input',sync));
  form.querySelectorAll('[data-format]').forEach(button=>button.onclick=()=>{const node=document.getElementById('compose-body'),start=node.selectionStart,end=node.selectionEnd,[before,after]=({bold:['**','**'],code:['\n```\n','\n```\n'],quote:['> ','']})[button.dataset.format];node.setRangeText(before+node.value.slice(start,end)+after,start,end,'select');sync();node.focus();});
  document.getElementById('preview-compose').onclick=()=>detail('正文预览',`<div class="reader">${AcmReader.html(compose.body)}</div>`);
  document.getElementById('save-draft').onclick=event=>perform(event.currentTarget,async()=>{if(!requireLogin('compose'))return;await saveCompose();});
  const remove=document.getElementById('delete-draft');if(remove)remove.onclick=()=>{if(!confirm('删除当前草稿？删除后无法恢复。'))return;perform(remove,async()=>{await request('/api/forum/drafts/'+compose.id,'DELETE',{});resetCompose();await show('compose');});};
  form.onsubmit = async event => {
    event.preventDefault();if(!requireLogin('compose'))return;
    if([...compose.title.trim()].length<4||[...compose.body.trim()].length<5){showInfo('内容不完整','标题至少4字，正文至少5字');return;}
    perform(form.querySelector('button.solid'),async()=>{await saveCompose();const result=await request('/api/forum/drafts/'+compose.id+'/submit','POST',{});resetCompose();await show('forum');showInfo('已提交审核',result.message||'审核通过后会出现在主页');});
  };
}
function resetCompose(){Object.assign(compose,{id:0,title:'',body:'',category:0,revision:0,saved:0});}
async function saveCompose(){
  if(composeSaving)return composeSaving;
  const status=()=>document.getElementById('draft-state');
  composeSaving=(async()=>{
    do{
      const revision=compose.revision,payload={title:compose.title,body:compose.body,category_id:compose.category||null};
      if(status())status().textContent='正在保存草稿…';
      const result=await request('/api/forum/drafts'+(compose.id?'/'+compose.id:''),compose.id?'PUT':'POST',payload);
      if(!Number.isInteger(result.id)||result.id<=0)throw failure('数据格式异常');
      compose.id=result.id;compose.saved=revision;
    }while(compose.revision!==compose.saved);
    if(status())status().textContent='草稿已保存';
  })();
  try{await composeSaving;}catch(error){if(status())status().textContent='保存失败，编辑内容仍保留';throw error;}finally{composeSaving=null;}
}
async function renderDetail() {
  const base = await supports('public_member_ids') ? '/api/mobile/v1/forum/posts/' : '/api/forum/posts/';
  const post = await request(base + state.postId);
  if (!post.title || typeof post.body !== 'string' || !Array.isArray(post.comments)) throw failure('数据格式异常');
  if(comment.postId!==state.postId)Object.assign(comment,{postId:state.postId,body:'',parent:0});
  return `<span class="tag">${esc(post.category_name)}</span><h2>${esc(post.title)}</h2><button class="link" data-member="${esc(post.author_public_member_id||'')}">${esc(post.author_name)}</button><div class="reader">${AcmReader.html(post.body)}</div><div class="post-actions"><button class="chip" data-post-action="like">${post.viewer_liked?'♥':'♡'} ${esc(post.likes_count)} 赞</button><button class="chip" data-post-action="bookmark">${post.viewer_bookmarked?'★ 已收藏':'☆ 收藏'}</button><button class="chip" data-post-action="report">举报</button><span class="notice">${esc(post.views_count)} 阅读</span></div><h3>讨论区</h3><form id="comment-form" class="login-demo"><textarea id="comment-body" maxlength="5000" placeholder="写下你的问题、想法或补充（2–5000字）" required>${esc(comment.body)}</textarea><p class="reply-note" id="reply-note">${comment.parent?'正在回复评论 #'+esc(comment.parent):'发布新的评论'}</p><button type="button" class="link" id="cancel-reply">取消回复</button><button class="solid">发布评论</button></form>` + post.comments.map(item=>`<div class="card"><b>${esc(item.author_name)}</b>${item.parent_id?`<p>↳ 回复评论 #${esc(item.parent_id)}</p>`:''}<p>${esc(item.body)}</p>${!item.parent_id?`<button class="link" data-reply="${esc(item.id)}">回复</button>`:''}</div>`).join('');
}
function readerMath(container){container.querySelectorAll('.reader').forEach(node=>AcmReader.math(node));}
function requireLogin(destination){if(state.csrf)return true;state.loginDestination=destination;show('account');return false;}
async function perform(button,work){
  if(state.actionBusy)return;state.actionBusy=true;const label=button.textContent;button.disabled=true;button.textContent='处理中…';
  const serial=state.serial,revision=detailRevision;
  try{await work();}catch(error){if(serial===state.serial&&revision===detailRevision)showFailure(error);}finally{state.actionBusy=false;button.disabled=false;button.textContent=label;}
}
function bindPostDetail(){
  const form=document.getElementById('comment-form');if(!form)return;
  document.getElementById('comment-body').oninput=event=>{comment.body=event.target.value;};
  document.getElementById('cancel-reply').onclick=()=>{comment.parent=0;document.getElementById('reply-note').textContent='发布新的评论';};
  document.querySelectorAll('[data-reply]').forEach(button=>button.onclick=()=>{if(!requireLogin('detail'))return;comment.parent=Number(button.dataset.reply);document.getElementById('reply-note').textContent='正在回复评论 #'+comment.parent;document.getElementById('comment-body').focus();});
  document.querySelectorAll('[data-post-action]').forEach(button=>button.onclick=()=>{
    if(!requireLogin('detail'))return;const kind=button.dataset.postAction,target=state.postId,serial=state.serial;
    let body={};if(kind==='report'){const reason=prompt('请说明举报原因（3–500字）');if(!reason)return;if([...reason.trim()].length<3||[...reason].length>500){showInfo('原因不完整','举报原因需要3–500字');return;}body={reason};}
    perform(button,async()=>{await request('/api/forum/posts/'+target+'/'+kind,'POST',body);if(serial!==state.serial)return;if(kind==='report')showInfo('已提交举报','管理员将进行核查');else await show('detail');});
  });
  form.onsubmit=event=>{event.preventDefault();if(!requireLogin('detail'))return;if([...comment.body.trim()].length<2){showInfo('评论不完整','评论至少2字');return;}const target=state.postId,serial=state.serial,payload={body:comment.body,parent_id:comment.parent};perform(form.querySelector('button.solid'),async()=>{await request('/api/forum/posts/'+target+'/comments','POST',payload);if(serial===state.serial){comment.body='';comment.parent=0;await show('detail');}});};
}
function bindActions(container) {
  container.querySelectorAll('[data-account-action]').forEach(button => button.onclick = () => accountAction(button.dataset.accountAction));
  container.querySelectorAll('[data-member]').forEach(button => button.onclick = () => { state.memberId = button.dataset.member; show('member'); });
  container.querySelectorAll('[data-post]').forEach(button => button.onclick = () => { state.postId = button.dataset.post; document.getElementById('account-detail-dialog').close(); show('detail'); });
  container.querySelectorAll('[data-url]').forEach(button => button.onclick = () => openLink(button.dataset.url));
  container.querySelectorAll('[data-problem]').forEach(button=>button.onclick=()=>openProblem(button.dataset.problemPlatform,button.dataset.problem));
  container.querySelectorAll('[data-favorite]').forEach(button=>button.onclick=()=>perform(button,async()=>{await request('/api/me/problems/'+encodeURIComponent(button.dataset.problemPlatform)+'/'+encodeURIComponent(button.dataset.favorite)+'/state','PUT',{is_favorite:button.dataset.current!=='true'});await show('problems');}));
  container.querySelectorAll('[data-draft]').forEach(button=>button.onclick=()=>perform(button,async()=>{if(compose.revision!==compose.saved){if(!confirm('保存当前修改后读取另一份草稿？'))return;await saveCompose();}const data=await request('/api/forum/drafts/'+button.dataset.draft);Object.assign(compose,{id:data.id,title:data.title||'',body:data.body||'',category:data.category_id||0,revision:0,saved:0});document.getElementById('account-detail-dialog').close();await show('compose');}));
  container.querySelectorAll('[data-copy]').forEach(button=>button.onclick=async()=>{try{await navigator.clipboard.writeText(button.dataset.copy);button.textContent='已复制';}catch{showInfo('复制失败','可长按选择样例文字复制。');}});
}
function detail(title, html, replace=false) {
  if(!replace&&document.getElementById('account-detail-dialog').open&&document.getElementById('account-detail-title').textContent===title)return false;
  ++detailRevision;
  document.getElementById('account-detail-dialog').dataset.action='';
  document.getElementById('account-detail-title').textContent = title;
  document.getElementById('account-detail-content').innerHTML = html; bindActions(document.getElementById('account-detail-content'));
  document.getElementById('account-detail-dialog').showModal();
  readerMath(document.getElementById('account-detail-content'));
  return true;
}
async function editText(title, initial, save) {
  detail(title,'<form id="edit-form" class="login-demo"><input id="edit-value"><button class="solid">保存</button></form>');
  document.getElementById('edit-value').value = initial;
  document.getElementById('edit-form').onsubmit = async event => { event.preventDefault(); try { await save(document.getElementById('edit-value').value.trim()); document.getElementById('account-detail-dialog').close(); show('account'); } catch(error) { document.getElementById('account-detail-content').innerHTML=errorBox(failureTitle(error),180,false); } };
}
async function accountAction(action){
  const dialog=document.getElementById('account-detail-dialog');
  if(dialog.open&&dialog.dataset.action===action)return;
  await AcmUiGuard.run('account:'+action,()=>accountActionImpl(action));
  if(dialog.open)dialog.dataset.action=action;
}
async function accountActionImpl(action) {
  try {
    if (action === 'account') return show('account');
    if (action === 'connection') return checkForUpdates();
    if (action === 'logout') { await request('/api/auth/logout','POST',{}); localStorage.removeItem('acm_auto_login');clearAccount();resetCompose();comment.body='';comment.parent=0;state.loginDestination='account';return show('account'); }
    if (action === 'about') return showInfo('关于ACMforever','打一辈子爱臭美 · 0.1.12 调试版');
    if (action === 'rename') return editText('修改昵称',state.user.user.name,value=>request('/api/me/profile','PUT',{name:value}));
    if (action === 'motto') { const profile=await mobile('own_public_profile','/me/public-profile');return editText('修改座右铭',profile.motto,value=>mobile('edit_motto','/me/public-profile','PUT',{motto:value})); }
    if (action === 'stats') return detail('我的学习统计',stats(state.user,true));
    if (action === 'recent') { const items=rows(state.user,'recent_ac');return detail('最近AC',items.map(item=>`<p>${esc(item.problem_name||item.problem_id)} · ${esc(item.platform)}</p>`).join('')||empty('暂无AC记录')); }
    if (action === 'bindings') return detail('OJ账号绑定',['cf_handle','luogu_id','atcoder_handle','nowcoder_id','cjlu_username'].map(key=>`<p>${esc(key)} · ${esc(state.user.user[key]||'未绑定')}</p>`).join(''));
    if (privateResults[action]) return detail({posts:'我的话题',bookmarks:'我的收藏',drafts:'草稿'}[action],privateResults[action].map(item=>`<div class="card"><b>${esc(item.title||'未命名草稿')}</b><p>${esc(({pending:'待审核',published:'已发布',rejected:'未通过'})[item.status]||item.status||'')}</p>${action==='drafts'?`<button class="menu-action" data-draft="${esc(item.id)}">继续编辑草稿</button>`:action==='bookmarks'||item.status==='published'?`<button class="menu-action" data-post="${esc(item.id)}">查看话题与讨论</button>`:''}</div>`).join('')||empty('暂无内容'));
    if (action === 'admin') return openAdmin();
    if(action==='problem-favorites'){state.problemState='favorite';return show('problems');}
    if(action==='training')return openTraining();
    if(action==='contests')return openContests();
    if(action==='password'){detail('修改密码',passwordForm());bindPasswordForm();return;}
    if(action==='avatar'){
      detail('社区头像','<form id="avatar-form" class="login-demo"><label>选择PNG、JPEG或WebP图片（最多2MB）</label><input id="avatar-file" type="file" accept="image/png,image/jpeg,image/webp" required><button class="solid">上传头像</button><button type="button" class="menu-action" id="reset-avatar">恢复默认</button></form>');
      const form=document.getElementById('avatar-form');form.onsubmit=event=>{event.preventDefault();const file=document.getElementById('avatar-file').files[0];if(!file)return;if(file.size>2*1024*1024){showInfo('图片太大','请选择不超过2MB的图片');return;}perform(form.querySelector('button'),async()=>{const body=new FormData();body.append('avatar',file,file.name);await request('/api/me/avatar','POST',body);document.getElementById('account-detail-dialog').close();await show('account');});};
      document.getElementById('reset-avatar').onclick=event=>perform(event.currentTarget,async()=>{await request('/api/me/avatar','DELETE',{});document.getElementById('account-detail-dialog').close();await show('account');});return;
    }
  } catch(error) { showFailure(error); }
}
async function openAdmin() {
  const session=await request('/api/auth/me');
  if(!session.authenticated||!['admin','root'].includes(session.role))throw failure('无访问权限');
  state.role=session.role;state.csrf=session.csrf_token;
  if(session.must_change_password)throw failure('请修改初始密码');
  const frame=document.getElementById('admin-frame');
  frame.src='../app/app/src/main/assets/admin/index.html?apiBase='+encodeURIComponent(apiBase);
  document.querySelectorAll('.view').forEach(node=>node.classList.toggle('active',node.id==='admin-view'));
  state.view='admin';++state.serial;document.getElementById('global-search').disabled=true;
  document.querySelector('.top').hidden=true;document.querySelector('.bottom').hidden=true;
}
async function checkForUpdates() {
  if(updateChecking)return;
  if(OFFLINE_PREVIEW){showFailure(failure(OFFLINE_MESSAGE));return;}
  if(!navigator.onLine){showFailure(failure('无网络'));return;}
  if(!updateUrl){showFailure(failure('无API接口'));return;}
  updateChecking=true;detail('检查更新',empty('正在检查新版本…'),true);
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),15000);
  try {
    const address=checkedHttps(updateUrl), response=await fetch(address,{credentials:'omit',redirect:'error',signal:controller.signal,headers:{Accept:'application/json'}});
    if(!response.ok)throw failure(response.status===404||response.status===405?'无API接口':response.status>=500?'服务器异常':'检查更新失败');
    const manifest=await response.json();
    if(manifest.packageName!=='com.giraffeslovebeauty.acmforever'||!Number.isSafeInteger(manifest.versionCode)||manifest.versionCode<1||typeof manifest.versionName!=='string'||!/^\d+\.\d+(?:\.\d+)?(?:[-+][\w.-]+)?$/.test(manifest.versionName)||!/^[a-fA-F0-9]{64}$/.test(manifest.sha256))throw failure('更新信息无效');
    const apk=checkedHttps(manifest.apkUrl||'');if(!apk)throw failure('更新信息无效');
    if(manifest.versionCode<=APP_VERSION_CODE){detail('检查更新',empty('已是最新版'),true);return;}
    detail('发现新版本',`<p>${esc(manifest.notes||'有新版本可用。')}</p><a class="solid" id="download-update" href="${esc(apk)}" download="acmforever-${esc(manifest.versionName)}.apk" target="_blank" rel="noopener noreferrer">更新${esc(manifest.versionName)}版本</a><p>下载后在安卓系统中打开安装包；安卓 App 会校验后请求安装。</p>`);
  } catch(error) { detail('检查更新',errorBox(error instanceof RequestFailure?failureTitle(error):error.name==='AbortError'?'请求超时':!navigator.onLine?'无网络':'无法连接更新服务',180,false),true); }
  finally{clearTimeout(timer);updateChecking=false;}
}
window.addEventListener('message',event=>{
  const frame=document.getElementById('admin-frame');
  if(event.source===frame?.contentWindow&&event.data?.type==='acm-admin-close'){frame.src='about:blank';document.querySelector('.top').hidden=false;document.querySelector('.bottom').hidden=false;show('account');}
});
function passwordForm(){return '<form id="password-form" class="login-demo"><label>当前密码</label><input id="old-password" type="password" autocomplete="current-password" required><label>新密码（12–128位）</label><input id="new-password" type="password" autocomplete="new-password" minlength="12" maxlength="128" required><label>确认新密码</label><input id="confirm-password" type="password" autocomplete="new-password" minlength="12" maxlength="128" required><button class="solid">保存新密码</button><p class="notice">至少包含三类字符，不含空格。</p></form>';}
function bindPasswordForm(){
  const form=document.getElementById('password-form');if(!form)return;
  form.onsubmit=event=>{event.preventDefault();const old=document.getElementById('old-password').value,next=document.getElementById('new-password').value,confirmation=document.getElementById('confirm-password').value;if(next!==confirmation){showInfo('密码不一致','两次输入的新密码必须相同');return;}
    perform(form.querySelector('button'),async()=>{await request('/api/auth/change-password','POST',{old_password:old,new_password:next});form.reset();state.mustChangePassword=false;document.getElementById('account-detail-dialog').close();await show('account');});};
}
function openProblem(platform,id){return AcmUiGuard.run('problem:'+platform+':'+id,()=>loadProblem(platform,id));}
async function loadProblem(platform,id){
  const serial=state.serial,revision=detailRevision;
  try{
    const problem=await request('/api/me/problems/'+encodeURIComponent(platform)+'/'+encodeURIComponent(id));
    if(serial!==state.serial||revision!==detailRevision)return;
    const source=problem.statement_html||problem.statement_text||'';
    let html=problem.content_available?`<div class="reader">${AcmReader.html(source,problem.statement_html?'html':'markdown')}</div>`:empty('题库已有目录，题面与样例尚未采集；可先打开原题。');
    if(!Array.isArray(problem.samples))throw failure('数据格式异常');
    html+=problem.samples.map((sample,i)=>`<div class="card"><h3>样例${i+1}</h3><p>输入</p><pre class="sample-text">${esc(sample.input)}</pre><button class="link" data-copy="${esc(sample.input)}">复制输入</button><p>输出</p><pre class="sample-text">${esc(sample.output)}</pre><button class="link" data-copy="${esc(sample.output)}">复制输出</button></div>`).join('');
    if(problem.problem_url)html+=`<button class="menu-action" data-url="${esc(problem.problem_url)}">打开原题</button>`;
    detail(problem.problem_name||id,html);
  }catch(error){if(serial===state.serial&&revision===detailRevision)showFailure(error);}
}
function trainingLevels(platform){
  if(platform==='luogu')return ['未评定','入门','普及-','普及/提高-','普及+/提高','提高+/省选-','省选/NOI-','NOI/NOI+/CTSC'];
  if(platform==='nowcoder')return ['1星','2星','3星','4星','5星'];
  if(!platform)return ['不限难度'];
  const result=[];for(let value=platform==='codeforces'?800:0;value<=(platform==='codeforces'?3500:4000);value+=100)result.push(value);return result;
}
async function openTraining(){
  detail('今日训练','<form id="training-form" class="login-demo"><label>平台</label><select id="training-platform"><option value="">全部平台</option><option value="codeforces">Codeforces</option><option value="luogu">洛谷</option><option value="atcoder">AtCoder</option><option value="nowcoder">牛客</option></select><label>算法标签、题名或题号</label><input id="training-tag"><label>难度</label><select id="training-difficulty"><option>不限难度</option></select><label><input type="checkbox" id="training-weak" style="width:auto">按我的弱项训练</label><button class="solid">生成今日训练</button></form><div id="training-zones"></div><h3>挑战历史</h3><div id="training-history">正在加载…</div>');
  const form=document.getElementById('training-form'),platform=document.getElementById('training-platform'),difficulty=document.getElementById('training-difficulty');
  platform.onchange=()=>{difficulty.innerHTML=trainingLevels(platform.value).map(value=>`<option>${esc(value)}</option>`).join('');difficulty.selectedIndex=({codeforces:2,atcoder:8,luogu:2,nowcoder:1})[platform.value]||0;};
  const history=async()=>{const slot=document.getElementById('training-history');if(!slot)return;try{const items=await request('/api/me/training/challenges');if(!Array.isArray(items))throw failure('数据格式异常');slot.innerHTML=items.map(item=>`<div class="card"><b>${esc(item.problem_name||item.problem_id)}</b><p>${esc(item.platform)} · ${esc(item.status)}</p></div>`).join('')||empty('暂无挑战记录');}catch(error){slot.innerHTML=errorBox(failureTitle(error),220,false);}};
  form.onsubmit=event=>{event.preventDefault();const chosen=platform.value,values=trainingLevels(chosen),index=difficulty.selectedIndex,tag=document.getElementById('training-tag').value,weak_tag=document.getElementById('training-weak').checked;
    perform(form.querySelector('button'),async()=>{const slots=document.getElementById('training-zones');slots.innerHTML=['稳定基础','主训练','突破上限'].map((label,index)=>`<div class="card"><h3>${label}</h3><div id="training-zone-${index}">正在生成…</div></div>`).join('');for(let i=0;i<3;i++){const slot=slots.querySelector('#training-zone-'+i);try{const target=!chosen?null:typeof values[index]==='number'?Math.max(values[0],Math.min(values.at(-1),values[index]+(i-1)*150)):values[Math.max(0,Math.min(values.length-1,index+i-1))];const row=await request('/api/me/challenge/start','POST',{platform:chosen,tag,weak_tag,difficulty:target});slot.innerHTML=`<b>${esc(row.problem_name||row.problem_id)}</b><p>${esc(row.platform)} · ${esc(row.problem_rating??'难度未知')}</p><p>${esc(row.recommendation_reason)}</p>${row.problem_url?`<button class="link" data-url="${esc(row.problem_url)}">打开题目</button>`:''}`;bindActions(slot);}catch(error){slot.innerHTML=errorBox(failureTitle(error),180,false);}}await history();});};
  await history();
}
function openContests(){
  detail('赛事复盘','<form id="contest-form" class="login-demo"><label>比赛ID</label><input id="contest-id" required><button class="solid">查询比赛题目</button></form><div id="contest-results"><p>请输入比赛ID查询自己的题目记录。</p></div>');
  const form=document.getElementById('contest-form');form.onsubmit=event=>{event.preventDefault();const contest_id=document.getElementById('contest-id').value.trim();perform(form.querySelector('button'),async()=>{
    const items=await request('/api/me/contest/reviews?'+new URLSearchParams({contest_id}));if(!Array.isArray(items))throw failure('数据格式异常');const labels={todo:'待处理',unsolved:'未通过',queued:'待补题',solved:'已解决',reviewed:'已复盘',ignored:'忽略'};
    const area=document.getElementById('contest-results');if(!area)return;area.innerHTML=items.map((row,index)=>`<form class="card login-demo" data-review="${index}"><b>${esc(row.problem_id)}</b><p>${esc(row.verdict||'未记录结果')} · ${esc(row.rating??'难度未知')}</p><select>${Object.entries(labels).map(([key,label])=>`<option value="${key}" ${row.status===key?'selected':''}>${label}</option>`).join('')}</select><button class="solid">保存本题状态</button></form>`).join('')||empty('暂无题目记录，请先同步数据');
    area.querySelectorAll('[data-review]').forEach(editor=>editor.onsubmit=event=>{event.preventDefault();perform(editor.querySelector('button'),async()=>{await request('/api/me/contest/reviews','PUT',{contest_id,problem_id:items[Number(editor.dataset.review)].problem_id,status:editor.querySelector('select').value});showInfo('已保存','本题补题状态已更新');});});
  });};
}
function openLink(address) { try { const url=checkedHttps(address); if(confirm('打开网页：\n'+url)) window.open(url,'_blank','noopener,noreferrer'); } catch(error){showFailure(error);} }
document.querySelectorAll('[data-view]').forEach(button=>button.onclick=()=>{state.query='';document.getElementById('global-search').value='';show(button.dataset.view);});
document.getElementById('avatar-button').onclick=()=>show('account');
document.getElementById('profile-avatar').onclick=()=>show('account');
document.getElementById('back-profile').onclick=()=>show('mine');
document.getElementById('back-member').onclick=()=>show('rank');
document.getElementById('back-forum').onclick=()=>show('forum');
document.getElementById('global-search').onfocus=openSearch;
document.getElementById('global-search').onclick=openSearch;
document.getElementById('global-search').onkeydown=event=>{if(event.key==='Enter'){event.preventDefault();submitSearch(event.target.value);}};
document.querySelectorAll('[data-days]').forEach(button=>button.onclick=()=>{state.days=button.dataset.days;state.rankPage=1;document.querySelectorAll('[data-days]').forEach(node=>node.classList.toggle('active',node===button));show('rank');});
document.getElementById('rank-filter').onclick=()=>{
  const platforms={codeforces:'Codeforces',luogu:'洛谷',atcoder:'AtCoder',nowcoder:'牛客',cjlu:'校 OJ'},sorts={total_count:'总 AC 数',cf_count:'Codeforces',luogu_count:'洛谷',atcoder_count:'AtCoder',nowcoder_count:'牛客',cjlu_count:'校 OJ'};
  detail('排名筛选',`<form id="rank-form" class="login-demo"><label>统计平台（至少一个）</label>${Object.entries(platforms).map(([key,label])=>`<label><input type="checkbox" style="width:auto" name="platform" value="${key}" ${state.rankPlatforms.includes(key)?'checked':''}>${label}</label>`).join('')}<label>排序方式</label><select id="rank-sort">${Object.entries(sorts).map(([key,label])=>`<option value="${key}" ${state.rankSort===key?'selected':''}>${label}</option>`).join('')}</select><button class="solid">应用筛选</button></form>`);
  document.getElementById('rank-form').onsubmit=event=>{event.preventDefault();const selected=[...event.target.querySelectorAll('[name=platform]:checked')].map(node=>node.value);if(!selected.length){showInfo('请选择平台','至少选择一个统计平台');return;}state.rankPage=1;state.rankPlatforms=selected;state.rankSort=document.getElementById('rank-sort').value;document.getElementById('account-detail-dialog').close();show('rank');};
};
document.querySelectorAll('[data-platform]').forEach(button=>button.onclick=()=>{state.platform=button.dataset.platform==='全部'?'':button.dataset.platform.toLowerCase();document.querySelectorAll('[data-platform]').forEach(node=>node.classList.toggle('active',node===button));show('problems');});
document.querySelectorAll('[data-problem-state]').forEach(button=>button.onclick=()=>{state.problemState=button.dataset.problemState;document.querySelectorAll('[data-problem-state]').forEach(node=>node.classList.toggle('active',node===button));show('problems');});
document.getElementById('forum-filter-button').onclick=async()=>{
  const dialog=document.getElementById('filter-dialog'), container=document.getElementById('categories');
  if(dialog.open)return;
  const revision=++filterRevision;dialog.showModal();container.innerHTML=empty('正在加载分类…');
  try{const result=await request('/api/forum/categories');if(revision!==filterRevision||!dialog.open)return;if(!Array.isArray(result))throw failure('数据格式异常');container.innerHTML=[{slug:'',name:'全部'},...result].map(item=>`<button class="chip ${state.category===item.slug?'active':''}" data-category="${esc(item.slug)}">${esc(item.name)}</button>`).join('');container.querySelectorAll('[data-category]').forEach(button=>button.onclick=()=>{state.category=button.dataset.category;container.querySelectorAll('button').forEach(node=>node.classList.toggle('active',node===button));});}
  catch(error){if(revision===filterRevision&&dialog.open)container.innerHTML=errorBox(failureTitle(error),100,false);}
};
document.getElementById('filter-dialog').addEventListener('close',()=>++filterRevision);
document.querySelectorAll('[data-sort]').forEach(button=>button.onclick=()=>{state.sort=button.dataset.sort;document.querySelectorAll('[data-sort]').forEach(node=>node.classList.toggle('active',node===button));});
document.getElementById('cancel-filter').onclick=()=>document.getElementById('filter-dialog').close();
document.getElementById('apply-filter').onclick=()=>{document.getElementById('filter-dialog').close();show('forum');};
document.getElementById('top-tools-button').onclick=()=>{const dialog=document.getElementById('tools-dialog');if(!dialog.open)dialog.showModal();};
document.getElementById('close-tools').onclick=()=>document.getElementById('tools-dialog').close();
document.getElementById('close-info').onclick=()=>document.getElementById('info-dialog').close();
document.getElementById('close-account-detail').onclick=()=>{++detailRevision;document.getElementById('account-detail-dialog').close();};
document.getElementById('scan-action').onclick=()=>{document.getElementById('tools-dialog').close();showInfo('扫一扫','相机识别尚未实现。可在Android应用内粘贴HTTPS链接打开网页。');};
document.getElementById('check-update-action').onclick=()=>{document.getElementById('tools-dialog').close();checkForUpdates();};
window.addEventListener('offline',()=>show(state.view));
window.addEventListener('online',()=>show(state.view));
window.addEventListener('beforeunload',event=>{if(compose.revision!==compose.saved||composeSaving){event.preventDefault();event.returnValue='';}});
const requestedView=new URLSearchParams(location.search).get('view');
async function startApp(view) {
  if (OFFLINE_PREVIEW) {
    const notice = document.createElement('p');
    notice.className = 'notice';
    notice.textContent = '离线界面预览 · 不请求 API · 数据、登录与发布不可用';
    document.querySelector('.top').append(notice);
    return show(view);
  }
  if(localStorage.getItem('acm_auto_login')!==apiBase)return show(view);
  loginWaiting(true);
  try {
    const session=await request('/api/auth/me');
    if(!session.authenticated||!session.csrf_token){localStorage.removeItem('acm_auto_login');throw failure('登录已失效，请重新登录');}
    state.csrf=session.csrf_token;state.role=session.role;state.mustChangePassword=!!session.must_change_password;
    loginWaiting(false);return show(state.mustChangePassword?'account':view);
  } catch(error) {
    clearAccount();loginWaiting(false);await show('account');
    document.getElementById('account-area').insertAdjacentHTML('beforeend',errorBox(failureTitle(error),120,false));
  }
}
startApp(['forum','rank','compose','problems','mine','account','member'].includes(requestedView)?requestedView:'forum');
