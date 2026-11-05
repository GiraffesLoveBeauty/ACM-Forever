/* Saved content is untrusted. Keep the same text/code/table allowlist as Web. */
window.AcmReader = {
  html(source, format = 'markdown', base) {
    const clean = DOMPurify.sanitize(format === 'html' ? String(source || '') : marked.parse(String(source || ''), {gfm:true,breaks:true}), {
      ALLOWED_TAGS: ['div','span','section','p','h1','h2','h3','h4','h5','h6','br','hr','pre','code','var','b','strong','i','em','u','s','del','sub','sup','ul','ol','li','dl','dt','dd','table','caption','thead','tbody','tfoot','tr','th','td','blockquote','a','img'],
      ALLOWED_ATTR: ['class','href','src','alt','title','start','colspan','rowspan'],
    });
    const template = document.createElement('template'); template.innerHTML = clean;
    template.content.querySelectorAll('a').forEach(node => {
      try { const url = new URL(node.getAttribute('href'), base || undefined); if (url.protocol !== 'https:' || url.username || url.password) throw Error(); node.href=url.href;node.rel = 'noopener noreferrer'; }
      catch { node.removeAttribute('href'); }
    });
    template.content.querySelectorAll('img').forEach(node => {
      try { const url = new URL(node.getAttribute('src'), base || undefined); if (url.protocol !== 'https:' || url.username || url.password) throw Error(); node.src=url.href;node.referrerPolicy = 'no-referrer'; }
      catch { node.remove(); }
    });
    return template.innerHTML;
  },
  math(container) {
    if (typeof renderMathInElement !== 'function') return;
    renderMathInElement(container, {output:'mathml',trust:false,throwOnError:false,maxExpand:1000,maxSize:20,
      delimiters:[{left:'$$$$$$',right:'$$$$$$',display:true},{left:'$$$',right:'$$$',display:false},{left:'$$',right:'$$',display:true},{left:'\\[',right:'\\]',display:true},{left:'\\(',right:'\\)',display:false},{left:'$',right:'$',display:false}]});
  },
};
function renderContent(source, format, base) {
  const article = document.getElementById('article');
  article.innerHTML = AcmReader.html(source, format, base); AcmReader.math(article);
  article.querySelectorAll('img').forEach(image=>{try{const url=new URL(image.src),origin=new URL(base);if(url.origin===origin.origin&&/^\/api\/forum\/images\/[a-f0-9]{32}$/.test(url.pathname)&&!url.search){image.tabIndex=0;image.setAttribute('role','button');image.setAttribute('aria-label','放大查看图片');const open=()=>{location.href='acm-image:'+encodeURIComponent(url.href);};image.addEventListener('click',open);image.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();open();}});}}catch{}});
}
