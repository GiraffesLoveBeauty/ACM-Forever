// Shared by the preview and packaged administrator UI. No server data is stored.
(() => {
  if(window.AcmUiGuard)return;
  const jobs=new Map(),original=HTMLDialogElement.prototype.showModal;
  HTMLDialogElement.prototype.showModal=function(){
    if(this.open)return;
    document.querySelectorAll('dialog[open]').forEach(dialog=>{if(dialog!==this)dialog.close();});
    original.call(this);
  };
  // Ignore queued clicks on the underlying page after a modal has opened.
  document.addEventListener('click',event=>{
    const dialog=document.querySelector('dialog[open]');
    if((dialog&&!dialog.contains(event.target))||(!dialog&&jobs.size)){event.preventDefault();event.stopImmediatePropagation();}
  },true);
  window.AcmUiGuard={async run(key,work){
    if(jobs.has(key))return jobs.get(key);
    if(jobs.size)return;
    const task=Promise.resolve().then(work);jobs.set(key,task);
    try{return await task;}finally{if(jobs.get(key)===task)jobs.delete(key);}
  }};
})();
