/* Saved statements are untrusted HTML, even when collected from a public OJ. */
(() => {
  const $ = selector => document.querySelector(selector);
  const mathOptions = {
    output: 'mathml', trust: false, throwOnError: false, maxExpand: 1000, maxSize: 20,
    delimiters: [
      {left: '$$$$$$', right: '$$$$$$', display: true},
      {left: '$$$', right: '$$$', display: false},
      {left: '$$', right: '$$', display: true},
      {left: '\\(', right: '\\)', display: false},
      {left: '\\[', right: '\\]', display: true},
    ],
  };
  function cleanStatement(html) {
    const fragment = DOMPurify.sanitize(html, {
      RETURN_DOM_FRAGMENT: true,
      ALLOWED_TAGS: ['div','span','section','p','h1','h2','h3','h4','h5','h6','br','hr','pre','code','var','b','strong','i','em','u','s','sub','sup','ul','ol','li','dl','dt','dd','table','caption','thead','tbody','tfoot','tr','th','td','blockquote','a','img'],
      ALLOWED_ATTR: ['class','href','src','alt','title','colspan','rowspan','start','lang'],
      ALLOW_DATA_ATTR: false, ALLOW_ARIA_ATTR: false,
    });
    for (const image of fragment.querySelectorAll('img')) {
      let url;
      try { url = new URL(image.getAttribute('src')); } catch { image.remove(); continue; }
      if (!['http:','https:'].includes(url.protocol) || url.username || url.password || url.port ||
          !(url.hostname === 'codeforces.com' || url.hostname.endsWith('.codeforces.com') || ['atcoder.jp','img.atcoder.jp'].includes(url.hostname))) {
        image.replaceWith(document.createTextNode(image.alt || '[图片未保存]')); continue;
      }
      url.protocol = 'https:'; image.src = url.href;
      image.loading = 'lazy'; image.referrerPolicy = 'no-referrer';
    }
    for (const link of fragment.querySelectorAll('a')) {
      const href = link.getAttribute('href') || '';
      if (!/^https?:\/\//i.test(href)) link.removeAttribute('href');
      else { link.target = '_blank'; link.rel = 'noopener noreferrer'; }
    }
    // Only retain classes used to lay out statement sections and sample lines.
    const allowedClasses = new Set(['header','title','property-title','time-limit','memory-limit','input-file','output-file','section-title','input-specification','output-specification','sample-tests','sample-test','input','output','test-example-line','note','part','lang-en','lang-ja']);
    for (const node of fragment.querySelectorAll('[class]')) {
      const names = [...node.classList].filter(name => allowedClasses.has(name));
      if (names.length) node.className = names.join(' '); else node.removeAttribute('class');
    }
    return fragment;
  }
  function copyButton(pre, text, label) {
    const button = document.createElement('button');
    button.type = 'button'; button.className = 'btn problem-copy'; button.textContent = label;
    button.addEventListener('click', async () => {
      try { await navigator.clipboard.writeText(text); button.textContent = '已复制'; }
      catch { $('#problem-message').textContent = '复制失败，请选择样例文本后手动复制。'; }
    });
    pre.after(button);
  }
  function renderSamples(statement, samples, platform) {
    let inputs = [], outputs = [];
    if (platform === 'codeforces') {
      inputs = [...statement.querySelectorAll('.sample-test .input pre')];
      outputs = [...statement.querySelectorAll('.sample-test .output pre')];
    } else {
      for (const heading of statement.querySelectorAll('h3')) {
        const pre = heading.nextElementSibling;
        if (pre?.tagName !== 'PRE') continue;
        if (/^(Sample Input|入力例)\s*\d*/i.test(heading.textContent.trim())) inputs.push(pre);
        if (/^(Sample Output|出力例)\s*\d*/i.test(heading.textContent.trim())) outputs.push(pre);
      }
    }
    const fallback = $('#problem-samples');
    fallback.replaceChildren(); fallback.hidden = true;
    const embedded = samples.length && inputs.length === samples.length && outputs.length === samples.length;
    if (!embedded && samples.length) {
      fallback.hidden = false;
      const title = document.createElement('h2'); title.textContent = '样例'; fallback.append(title);
    }
    samples.forEach((sample, index) => {
      let grid;
      if (!embedded) { grid = document.createElement('div'); grid.className = 'problem-sample-grid'; fallback.append(grid); }
      for (const [kind, title, nodes] of [['input','输入',inputs], ['output','输出',outputs]]) {
        const text = String(sample[kind] ?? '');
        const pre = embedded ? nodes[index] : document.createElement('pre');
        if (!embedded) {
          const cell = document.createElement('div'), heading = document.createElement('h3');
          heading.textContent = `样例 ${index + 1} · ${title}`; cell.append(heading, pre); grid.append(cell);
        }
        // Use the stored sample text so spaces, newlines and literal markup survive.
        pre.textContent = text; copyButton(pre, text, `复制样例 ${index + 1} ${title}`);
      }
    });
  }
  async function load() {
    const query = new URLSearchParams(location.search), platform = query.get('platform'), id = query.get('problem_id');
    const message = $('#problem-message'), statement = $('#problem-statement'), empty = $('#problem-empty');
    const original = $('#problem-original'); original.hidden = true; original.removeAttribute('href');
    statement.hidden = true; empty.hidden = true; $('#problem-samples').hidden = true;
    const button = $('#problem-reload'); button.disabled = true;
    message.textContent = '正在读取已采集题目…';
    try {
      if (!platform || !id) throw Error('缺少题目平台或题号，请从题库打开题目。');
      const data = await window.api(`/problems/${encodeURIComponent(platform)}/${encodeURIComponent(id)}`);
      $('#problem-title').textContent = data.problem_name || id;
      document.title = `${data.problem_name || id} · ACM Forever`;
      const labels = [({codeforces:'Codeforces',atcoder:'AtCoder'})[platform] || platform, id,
        `难度 ${data.problem_rating ?? '未知'}`, ...data.tags];
      if (data.statement_language) labels.push(data.statement_language === 'ja' ? '日文题面' : '英文题面');
      $('#problem-meta').replaceChildren(...labels.map(label => {
        const chip = document.createElement('span'); chip.className = 'chip'; chip.textContent = label; return chip;
      }));
      try {
        const url = new URL(data.problem_url);
        if (['https:', 'http:'].includes(url.protocol) && !url.username && !url.password) {
          original.href = url.href; original.hidden = false;
        }
      } catch { /* Keep the link hidden when the catalog has no valid original URL. */ }
      if (!data.content_available) {
        empty.hidden = false;
        message.textContent = '已收录题目目录，正文与样例尚未就绪。';
        $('#problem-empty-message').textContent = data.last_fetch_status === 'failed'
          ? '这道题目上次采集失败，请管理员在题库管理中重新拉取。'
          : '如果正在拉取该平台全部题目，请等待任务处理到这道题目后重新检查。也可请管理员按比赛或题号采集。';
        return;
      }
      statement.replaceChildren();
      if (data.statement_html) statement.append(cleanStatement(data.statement_html));
      else { const pre = document.createElement('pre'); pre.className = 'problem-plain'; pre.textContent = data.statement_text; statement.append(pre); }
      renderSamples(statement, data.samples, platform);
      if (window.renderMathInElement) window.renderMathInElement(statement, mathOptions);
      if (platform === 'atcoder' && window.katex) {
        for (const variable of statement.querySelectorAll('var')) {
          if (!variable.querySelector('math') && !variable.closest('pre,code')) window.katex.render(variable.textContent, variable, mathOptions);
        }
      }
      statement.hidden = false;
      const fetched = data.statement_fetched_at ? new Date(data.statement_fetched_at).toLocaleString('zh-CN') : '';
      message.textContent = `已采集题面 · ${data.samples.length} 组样例${fetched ? ' · 采集于 '+fetched : ''}${data.last_fetch_status === 'failed' ? ' · 最近更新失败，展示上次保存的内容' : ''}`;
    } catch (error) { message.textContent = '无法打开题目：' + error.message; }
    finally { button.disabled = false; }
  }
  window.PAGE_LOAD = async () => {
    if (['admin','root'].includes(window.AUTH.role)) $('#problem-back').href = '/admin.html?section=problems';
    $('#problem-reload').addEventListener('click', load);
    await load();
  };
})();
