/* Render Markdown as a small, safe subset suitable for member-authored forum posts. */
window.renderForumMarkdown = function renderForumMarkdown(source) {
  if (!window.marked || !window.DOMPurify) {
    return window.esc ? window.esc(source).replace(/\n/g, "<br>") : "";
  }
  const formulas = [];
  const text = String(source || "");
  let placeholderPrefix = `FORUMMATH${Date.now().toString(36)}${Math.random().toString(36).slice(2)}END`;
  while (text.includes(placeholderPrefix)) {
    placeholderPrefix = `FORUMMATH${Date.now().toString(36)}${Math.random().toString(36).slice(2)}END`;
  }
  const escapedDollars = [];
  const markdownSafeText = text.replace(/(\\*)\$/g, (delimiter, slashes) => {
    if (slashes.length % 2 === 0) return delimiter;
    const placeholder = `${placeholderPrefix}${escapedDollars.length}LITERALDOLLAR`;
    escapedDollars.push(placeholder);
    return `${slashes.slice(0, -1)}${placeholder}`;
  });
  const protectedText = markdownSafeText.replace(/(\$\$[\s\S]+?\$\$|\\\[[\s\S]+?\\\]|\\\([\s\S]+?\\\)|\$[^$\n]+\$)/g, formula => {
    const placeholder = `${placeholderPrefix}${formulas.length}TOKEN`;
    formulas.push({ placeholder, formula });
    return placeholder;
  });
  const html = window.marked.parse(protectedText, { gfm: true, breaks: true });
  const safeHtml = window.DOMPurify.sanitize(html, {
    ALLOWED_TAGS: [
      "a", "blockquote", "br", "code", "del", "em", "h1", "h2", "h3", "h4", "h5", "h6",
      "hr", "li", "ol", "p", "pre", "strong", "sub", "sup", "table", "tbody", "td", "th",
      "thead", "tr", "ul",
    ],
    ALLOWED_ATTR: ["href", "title", "class", "start"],
    FORBID_TAGS: ["style", "iframe", "img", "video", "audio", "form"],
  });
  const escapeHtml = value => value.replace(/[&<>"']/g, character => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[character]);
  const withFormulas = formulas.reduce((result, item) => result.split(item.placeholder).join(escapeHtml(item.formula)), safeHtml);
  if (!escapedDollars.length) return withFormulas;
  const container = document.createElement("div");
  container.innerHTML = withFormulas;
  const literalDollarPlaceholders = new Set(escapedDollars);
  const placeholderPattern = new RegExp(`(${escapedDollars.join("|")})`, "g");
  const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
  const textNodes = [];
  while (walker.nextNode()) textNodes.push(walker.currentNode);
  textNodes.forEach(node => {
    if (!placeholderPattern.test(node.nodeValue)) {
      placeholderPattern.lastIndex = 0;
      return;
    }
    placeholderPattern.lastIndex = 0;
    const fragment = document.createDocumentFragment();
    node.nodeValue.split(placeholderPattern).forEach(part => {
      if (literalDollarPlaceholders.has(part)) {
        const dollar = document.createElement("span");
        dollar.className = "tex2jax_ignore";
        dollar.textContent = "$";
        fragment.appendChild(dollar);
      } else if (part) {
        fragment.appendChild(document.createTextNode(part));
      }
    });
    node.parentNode.replaceChild(fragment, node);
  });
  return container.innerHTML;
};

window.renderForumMath = function renderForumMath(root) {
  if (!root || !window.renderMathInElement || !window.katex) return;
  window.renderMathInElement(root, {
    delimiters: [
      { left: "$$", right: "$$", display: true },
      { left: "\\[", right: "\\]", display: true },
      { left: "$", right: "$", display: false },
      { left: "\\(", right: "\\)", display: false },
    ],
    throwOnError: false,
    strict: "ignore",
    trust: false,
    maxExpand: 1000,
    ignoredClasses: ["tex2jax_ignore"],
  });
};
