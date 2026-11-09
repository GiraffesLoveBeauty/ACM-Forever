/* Saved content is untrusted. Keep the same text/code/table allowlist as Web. */
const acmMathDelimiters = [
  {left:'$$$$$$',right:'$$$$$$',display:true}, {left:'$$$',right:'$$$',display:false},
  {left:'$$',right:'$$',display:true}, {left:'\\[',right:'\\]',display:true},
  {left:'\\(',right:'\\)',display:false}, {left:'$',right:'$',display:false},
];

// Tokenize TeX before Markdown can eat its backslashes, underscores or line breaks.
// Marked still owns code spans/fences, links and HTML; this is not a global replacement.
function acmMathToken(source, block) {
  const indent = block ? (/^ {0,3}/.exec(source)[0].length) : 0;
  const input = source.slice(indent);
  const delimiter = acmMathDelimiters.find(item => input.startsWith(item.left));
  if (!delimiter || (block && !delimiter.display)) return;
  let braces = 0;
  for (let i = delimiter.left.length; i < input.length; i++) {
    if (braces <= 0 && input.startsWith(delimiter.right, i)) {
      const end = i + delimiter.right.length;
      if (block && !/^[ \t]*(?:\n|$)/.test(input.slice(end))) return;
      return {type:block ? 'acmMathBlock' : 'acmMathInline', raw:source.slice(0, indent + end)};
    }
    if (input[i] === '\\') i++;
    else if (input[i] === '{') braces++;
    else if (input[i] === '}') braces--;
  }
}
function acmMathHtml(token) {
  const text = token.raw.replace(/[&<>"']/g, value => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[value]));
  const tag = token.type === 'acmMathBlock' ? 'div' : 'span';
  return `<${tag} class="acm-math-source">${text}</${tag}>`;
}
const acmMarkdown = new marked.Marked({gfm:true, breaks:true}, {
  // Markdown leaves HTML blocks intact; keep their existing math support too.
  // The entire output still passes through DOMPurify before entering the DOM.
  renderer:{html(token) { return token.block ? `<div class="acm-math-source">${token.text}</div>` : token.text; }},
  extensions:[
  {name:'acmMathBlock', level:'block',
    start(source) { const match = /\n {0,3}(?:\$\$|\\\[)/.exec(source); return match ? match.index + 1 : undefined; },
    tokenizer(source) { return acmMathToken(source, true); }, renderer:acmMathHtml},
  {name:'acmMathInline', level:'inline',
    start(source) { const match = /\$|\\(?:\(|\[)/.exec(source); return match ? match.index : undefined; },
    tokenizer(source) { return acmMathToken(source, false); }, renderer:acmMathHtml},
]});
window.AcmReader = {
  html(source, format = 'markdown', base, localAnchors = false) {
    const clean = DOMPurify.sanitize(format === 'html' ? String(source || '') : acmMarkdown.parse(String(source || '')), {
      ALLOWED_TAGS: ['div','span','section','p','h1','h2','h3','h4','h5','h6','br','hr','pre','code','var','b','strong','i','em','u','s','del','sub','sup','ul','ol','li','dl','dt','dd','table','caption','thead','tbody','tfoot','tr','th','td','blockquote','a','img'],
      ALLOWED_ATTR: ['class','href','src','alt','title','start','colspan','rowspan'],
    });
    const template = document.createElement('template'); template.innerHTML = clean;
    template.content.querySelectorAll('a').forEach(node => {
      if (localAnchors && (node.getAttribute('href') || '').startsWith('#')) return;
      try { const url = new URL(node.getAttribute('href'), base || undefined); if (url.protocol !== 'https:' || url.username || url.password) throw Error(); node.href=url.href;node.rel = 'noopener noreferrer'; }
      catch { node.removeAttribute('href'); }
    });
    template.content.querySelectorAll('img').forEach(node => {
      try { const url = new URL(node.getAttribute('src'), base || undefined); if (url.protocol !== 'https:' || url.username || url.password) throw Error(); node.src=url.href;node.referrerPolicy = 'no-referrer'; }
      catch { node.remove(); }
    });
    return template.innerHTML;
  },
  math(container, format = 'html') {
    if (typeof renderMathInElement !== 'function') return;
    const options = {output:'mathml',trust:false,throwOnError:false,maxExpand:1000,maxSize:20,delimiters:acmMathDelimiters};
    if (format === 'html') renderMathInElement(container, options);
    else container.querySelectorAll('.acm-math-source').forEach(node => {
      // Escaped literal delimiters and code examples must never become formulas later.
      if (!node.closest('pre,code,kbd,samp,script,style,textarea')) renderMathInElement(node, options);
    });
  },
  outline(container) {
    const counts = new Map(), used = new Set();
    container.querySelectorAll('h1,h2,h3,h4,h5,h6').forEach((node, index) => {
      const base = node.textContent.normalize('NFKC').toLowerCase().replace(/[^\p{L}\p{N}\s-]/gu, '').trim().replace(/\s+/g, '-') || `section-${index + 1}`;
      let count = counts.get(base) || 0, id = count ? `${base}-${count + 1}` : base;
      while (used.has(id)) { count++; id = `${base}-${count + 1}`; }
      counts.set(base, count + 1); used.add(id); node.id = id;
    });
    container.addEventListener('click', event => {
      const link = event.target.closest('a');
      if (!link || !(link.getAttribute('href') || '').startsWith('#')) return;
      event.preventDefault();
      try { location.href = 'acm-wiki-anchor:' + encodeURIComponent(decodeURIComponent(link.getAttribute('href').slice(1))); } catch {}
    });
  },
  layout() {
    const article = document.getElementById('article'), rect = article.getBoundingClientRect();
    return {height:Math.ceil(rect.height),headings:[...article.querySelectorAll('h1,h2,h3,h4,h5,h6')].map(node=>({id:node.id,title:node.textContent,level:Number(node.tagName[1]),top:Math.max(0,node.getBoundingClientRect().top - rect.top)}))};
  },
};
function renderContent(source, format, base, wiki = false, problem = false) {
  const article = document.getElementById('article');
  article.classList.toggle('problem-reader', problem);
  article.innerHTML = AcmReader.html(source, format, base, wiki); AcmReader.math(article, format);
  if (wiki) AcmReader.outline(article);
  article.querySelectorAll('img').forEach(image=>{try{const url=new URL(image.src),origin=new URL(base);if(url.origin===origin.origin&&/^\/api\/forum\/images\/[a-f0-9]{32}$/.test(url.pathname)&&!url.search){image.tabIndex=0;image.setAttribute('role','button');image.setAttribute('aria-label','放大查看图片');const open=()=>{location.href='acm-image:'+encodeURIComponent(url.href);};image.addEventListener('click',open);image.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();open();}});}}catch{}});
}
