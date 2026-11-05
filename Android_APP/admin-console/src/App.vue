<script setup>
import { computed, ref, provide, watch, defineAsyncComponent, onMounted, onBeforeUnmount } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { api, auth, setAuth, notification, logoutSession } from '../../../feat/web/src/lib/api.js';
import ThemeEditor from '../../../feat/web/src/components/ThemeEditor.vue';
import { markdown } from '../../../feat/web/src/lib/markdown.js';
const route=useRoute(), router=useRouter(), ready=ref(false), error=ref(''), theme=ref(), revision=ref(0), requests=ref(0);
const sections={accounts:'成员账号',members:'成员资料',training:'训练管理',problems:'题库管理','cf-practice':'CF 练习赛选题',contests:'赛事复盘',tasks:'同步任务',moderation:'内容审核',settings:'全局设置'};
const modules={
  accounts:defineAsyncComponent(()=>import('../../../feat/web/src/admin/Accounts.vue')),
  members:defineAsyncComponent(()=>import('../../../feat/web/src/admin/Members.vue')),
  training:defineAsyncComponent(()=>import('../../../feat/web/src/admin/Training.vue')),
  problems:defineAsyncComponent(()=>import('../../../feat/web/src/admin/Problems.vue')),
  'cf-practice':defineAsyncComponent(()=>import('../../../feat/web/src/admin/CfPractice.vue')),
  contests:defineAsyncComponent(()=>import('../../../feat/web/src/admin/Contests.vue')),
  tasks:defineAsyncComponent(()=>import('../../../feat/web/src/admin/Tasks.vue')),
  moderation:defineAsyncComponent(()=>import('../../../feat/web/src/admin/Moderation.vue')),
  settings:defineAsyncComponent(()=>import('../../../feat/web/src/admin/Settings.vue')),
};
const section=computed(()=>Object.hasOwn(sections,route.query.section)?route.query.section:'accounts');
let leaveGuard=()=>true;
const post=ref(null);
watch(notification,value=>{if(value.startsWith('请求超时'))error.value='请求超时';});
provide('registerLeaveGuard',handler=>{leaveGuard=handler;return()=>{if(leaveGuard===handler)leaveGuard=()=>true;};});
provide('openTheme',()=>theme.value?.open());provide('toggleTheme',()=>theme.value?.toggle());
window.__acmAdminCanLeave=()=>leaveGuard();
const removeGuard=router.beforeEach(async(to,from)=>{
  if(to.path==='/post.html'){
    if(!await leaveGuard())return false;
    try{post.value=await api('/forum/posts/'+Number(to.query.id));}catch{}
    return false;
  }
  if((to.query.section||'accounts')!==(from.query.section||'accounts')){
    if(!await leaveGuard())return false;
    error.value='';
    post.value=null;
  }
});
function requestError(event){error.value=event.detail.title;if([401,403,428].includes(event.detail.status))ready.value=false;}
const start=()=>requests.value++, end=()=>requests.value=Math.max(0,requests.value-1);
window.addEventListener('acm-request-error',requestError);window.addEventListener('acm-request-start',start);window.addEventListener('acm-request-end',end);
async function initialize(){
  error.value='';ready.value=false;
  try {
    const session=await api('/auth/me');setAuth(session,true);
    if(!session.authenticated){error.value='未登录或登录已失效';return;}
    if(session.must_change_password){error.value='请返回账号设置修改初始密码';return;}
    if(!['admin','root'].includes(session.role)){error.value='无访问权限';return;}
    ready.value=true;
  }catch(e){error.value=error.value||e.title||'无法连接服务器';}
}
async function retry(){if(!await leaveGuard())return;leaveGuard=()=>true;revision.value++;await initialize();}
async function exit(){if(!await leaveGuard())return;if(window.AcmAdminNative)window.AcmAdminNative.close();else window.parent.postMessage({type:'acm-admin-close'},location.origin==='null'?'*':location.origin);}
async function logout(){if(!await leaveGuard()||!confirm('退出当前账号？'))return;try{await logoutSession();ready.value=false;error.value='已退出登录';}catch{}}
onMounted(initialize);
onBeforeUnmount(()=>{removeGuard();delete window.__acmAdminCanLeave;window.removeEventListener('acm-request-error',requestError);window.removeEventListener('acm-request-start',start);window.removeEventListener('acm-request-end',end);});
</script>
<template>
  <main class="mobile-admin">
    <header class="mobile-admin-header"><div><p>ACMforever</p><h1>管理中心</h1><small v-if="ready">{{auth.role==='root'?'Root 管理员':'管理员'}}</small></div><button class="btn" @click="exit">返回账号</button></header>
    <template v-if="ready">
      <label class="module-picker">管理模块<select aria-label="管理模块" :value="section" @change="router.push({path:'/admin.html',query:{section:$event.target.value}})"><option v-for="(name,key) in sections" :value="key" :key="key">{{name}}</option></select></label>
      <nav class="mobile-admin-nav" aria-label="九个管理模块"><RouterLink v-for="(name,key) in sections" :key="key" :class="{selected:key===section}" :to="{path:'/admin.html',query:{section:key}}">{{name}}</RouterLink></nav>
      <div class="mobile-admin-tools"><h2>{{sections[section]}}</h2><button class="btn" @click="retry">刷新</button><button class="btn" @click="theme?.open()">外观</button><button class="btn" @click="logout">退出账号</button></div>
    </template>
    <section class="module-region" :aria-busy="requests>0">
      <div v-if="error" class="mobile-error" role="alert"><strong>{{error}}</strong><button class="btn" @click="retry">重试</button><button class="btn" @click="exit">返回账号设置</button></div>
      <p v-else-if="!ready" class="mobile-loading">正在验证管理员身份…</p>
      <div v-if="ready" class="admin-module" :class="{'module-hidden':!!error}"><component :is="modules[section]" :key="section+':'+revision"/></div>
    </section>
    <section v-if="post" class="admin-post-overlay" role="dialog" aria-modal="true" aria-label="举报话题详情"><button class="btn" @click="post=null">返回内容审核</button><h2>{{post.title}}</h2><article v-html="markdown(post.body||'')"></article><h3>评论</h3><p v-for="comment in post.comments||[]" :key="comment.id">{{comment.author_name}}：{{comment.body}}</p></section>
    <ThemeEditor ref="theme"/><div class="forum-toast" :class="{visible:notification}" role="status">{{notification}}</div>
  </main>
</template>
