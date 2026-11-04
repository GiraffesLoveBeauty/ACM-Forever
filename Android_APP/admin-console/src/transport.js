// Only packaged, trusted code receives this interface; cookies/passwords never cross it.
import '../../app/app/src/main/assets/ui-guard.js';
const realFetch = window.fetch.bind(window), pending = new Map();
let serial = 0;
const native = window.AcmAdminNative;
let base = '';
try {
  const value = new URLSearchParams(location.search).get('apiBase');
  if (value) { const url = new URL(value); if(url.protocol==='https:'&&!url.username&&!url.password&&url.pathname==='/'&&!url.search&&!url.hash) base=url.origin; }
} catch { /* An invalid preview URL is handled as an unavailable API. */ }
export function title(error) {
  const status = error?.status;
  return error?.title || (!navigator.onLine ? '无网络' : status===404||status===405?'无API接口':status===401?'未登录或登录已失效':status===403?'无访问权限':status===428?'请修改初始密码':status>=500?'服务器异常':error?.name==='AbortError'?'请求超时':'无法连接服务器');
}
function event(name, detail) { window.dispatchEvent(new CustomEvent(name, {detail})); }
window.__acmAdminResponse = (id, value) => {
  const task=pending.get(id);if(!task)return;pending.delete(id);task.cleanup();
  if(value.status===0) task.reject(Object.assign(new Error(value.title),{title:value.title}));
  else task.resolve(new Response(JSON.stringify(value.data),{status:value.status,headers:{'Content-Type':'application/json'}}));
};
window.fetch = async (input, options={}) => {
  const path=typeof input==='string'?input:'';
  if(!path.startsWith('/api/')) { if(native)throw Error('只允许管理 API 请求');return realFetch(input,options); }
  event('acm-request-start');
  try {
    let response;
    if(native) {
      response=await new Promise((resolve,reject)=>{
        const id=String(++serial), signal=options.signal;
        const abort=()=>{pending.delete(id);signal?.removeEventListener('abort',abort);reject(new DOMException('请求已取消','AbortError'));};
        if(signal?.aborted){abort();return;}
        signal?.addEventListener('abort',abort,{once:true});
        pending.set(id,{resolve,reject,cleanup:()=>signal?.removeEventListener('abort',abort)});
        native.request(id,options.method||'GET',path,typeof options.body==='string'?options.body:'');
      });
    } else {
      if(!navigator.onLine)throw Object.assign(Error('无网络'),{title:'无网络'});
      if(!base)throw Object.assign(Error('无API接口'),{title:'无API接口'});
      response=await realFetch(base+path,{...options,credentials:'include',redirect:'error'});
    }
    if(!response.ok) {
      const info={title:title({status:response.status}),status:response.status};event('acm-request-error',info);
      if([401,428].includes(response.status))throw Object.assign(Error(info.title),info);
    }
    return response;
  } catch(error) {
    if(error.name!=='AbortError')event('acm-request-error',{title:title(error),status:error.status});
    throw error;
  } finally { event('acm-request-end'); }
};
if(native) {
  // Native export uses Android's document picker; account credentials are not auto-saved.
  const originalClick=HTMLAnchorElement.prototype.click;
  HTMLAnchorElement.prototype.click=function(){
    if(!this.download||!this.href.startsWith('blob:'))return originalClick.call(this);
    exportDocument(this);
  };
  async function exportDocument(link){
    try { const text=await (await realFetch(link.href)).text();native.saveDocument(link.download,text); }
    catch { window.dispatchEvent(new CustomEvent('acm-request-error',{detail:{title:'导出失败'}})); }
  }
  document.addEventListener('click',event=>{const link=event.target.closest('a[download]');if(link?.href.startsWith('blob:')){event.preventDefault();exportDocument(link);}},true);
  try { Object.defineProperty(navigator,'clipboard',{value:{writeText:async text=>native.copyText(String(text))}}); } catch { /* Existing forms also provide manual copy. */ }
}
export function confirmExit() { return Promise.resolve(window.__acmAdminCanLeave?.() ?? true); }
