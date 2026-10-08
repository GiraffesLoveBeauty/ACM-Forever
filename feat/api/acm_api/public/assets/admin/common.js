// A module owns a detached content root, requests, listeners and timers for its lifetime.
export function context(root, params, memory, navigation) {
  const lifetime=new AbortController(), requests=new Set(), timers=new Set(), listeners=[];
  let passwordRequests=0, disposed=false;
  const ctx={root,params,memory,auth:window.AUTH,signal:lifetime.signal,esc:window.esc,
    $:selector=>root.querySelector(selector), ...navigation};
  ctx.document={getElementById:id=>root.querySelector('#'+CSS.escape(id)),querySelector:ctx.$,
    querySelectorAll:selector=>root.querySelectorAll(selector),createElement:tag=>document.createElement(tag),
    body:root,execCommand:(...args)=>document.execCommand(...args)};
  ctx.api=async(path,options={})=>{
    const controller=new AbortController(), source=options.signal;
    const cancel=()=>controller.abort();
    lifetime.signal.addEventListener('abort',cancel,{once:true});
    source?.addEventListener('abort',cancel,{once:true});
    if(lifetime.signal.aborted||source?.aborted)cancel();
    requests.add(controller);
    const passwords=options.method==='POST'&&(/\/web-accounts\/batch$/.test(path)||/reset-temporary-password$/.test(path));
    if(passwords)passwordRequests++;
    try{const data=await window.api(path,{...options,signal:controller.signal});if(controller.signal.aborted)throw new DOMException('模块已退出','AbortError');return data}
    catch(error){if(error.name==='AbortError'&&!lifetime.signal.aborted&&!source?.aborted)throw Error('请求超时，请重试。');throw error;}
    finally{requests.delete(controller);lifetime.signal.removeEventListener('abort',cancel);source?.removeEventListener('abort',cancel);if(passwords)passwordRequests--;}
  };
  ctx.pendingPasswords=()=>passwordRequests;
  ctx.on=(target,event,handler)=>{target.addEventListener(event,handler,{signal:lifetime.signal});};
  ctx.onWindow=(event,handler)=>{window.addEventListener(event,handler);listeners.push(()=>window.removeEventListener(event,handler));};
  ctx.setTimeout=(handler,ms)=>{if(disposed)return null;const id=window.setTimeout(()=>{timers.delete(id);if(!disposed)handler()},ms);timers.add(id);return id};
  ctx.clearTimeout=id=>{window.clearTimeout(id);timers.delete(id)};
  ctx.actions=handlers=>{
    const dispatch=async event=>{
      const node=event.target.closest('[data-action]');
      if(!node||!root.contains(node)||(event.type==='change')!==(node.tagName==='SELECT'))return;
      const fn=handlers[node.dataset.action];if(!fn)return;
      const text=node.dataset.args||'', tokens=text.match(/'(?:[^'\\]|\\.)*'|true|false|null|-?\d+|__VALUE__/g)||[];
      if(text.replace(/'(?:[^'\\]|\\.)*'|true|false|null|-?\d+|__VALUE__/g,'').replace(/[\s,]/g,''))return;
      const args=tokens.map(value=>value==='__VALUE__'?node.value:value.startsWith("'")?value.slice(1,-1).replace(/\\'/g,"'"):JSON.parse(value));
      try{await fn(...args)}catch(error){if(error.name!=='AbortError')ctx.notice(error.message)}
    };
    ctx.on(root,'click',dispatch);ctx.on(root,'change',dispatch);
  };
  ctx.on(root,'click',event=>{const link=event.target.closest('a[href^="#"]');if(!link)return;const id=link.getAttribute('href').slice(1),target=root.querySelector('#'+CSS.escape(id));if(target){event.preventDefault();target.scrollIntoView({behavior:'auto',block:'start'})}});
  ctx.dispose=()=>{
    if(disposed)return;disposed=true;lifetime.abort();
    requests.forEach(request=>request.abort());timers.forEach(id=>window.clearTimeout(id));listeners.forEach(remove=>remove());
    for(const node of [root,...root.querySelectorAll('*')])for(const event of ['onclick','onchange','onsubmit','onkeydown'])node[event]=null;
  };
  return ctx;
}
