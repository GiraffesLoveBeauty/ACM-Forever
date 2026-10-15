/* Saved content is untrusted. Keep the same text/code/table allowlist as Web. */
window.AcmReader = {
  html(source, format = 'markdown') {
    const clean = DOMPurify.sanitize(format === 'html' ? String(source || '') : marked.parse(String(source || ''), {gfm:true,breaks:true}), {
      ALLOWED_TAGS: ['div','span','section','p','h1','h2','h3','h4','h5','h6','br','hr','pre','code','var','b','strong','i','em','u','s','del','sub','sup','ul','ol','li','dl','dt','dd','table','caption','thead','tbody','tfoot','tr','th','td','blockquote','a','img'],
      ALLOWED_ATTR: ['class','href','src','alt','title','start','colspan','rowspan'],
    });
    const template = document.createElement('template'); template.innerHTML = clean;
    template.content.querySelectorAll('a').forEach(node => {
      try { const url = new URL(node.getAttribute('href')); if (url.protocol !== 'https:' || url.username || url.password) throw Error(); node.rel = 'noopener noreferrer'; }
      catch { node.removeAttribute('href'); }
    });
    template.content.querySelectorAll('img').forEach(node => {
      try { const url = new URL(node.getAttribute('src')); if (url.protocol !== 'https:' || url.username || url.password) throw Error(); node.referrerPolicy = 'no-referrer'; }
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
function renderContent(source, format) {
  const article = document.getElementById('article');
  article.innerHTML = AcmReader.html(source, format); AcmReader.math(article);
}
