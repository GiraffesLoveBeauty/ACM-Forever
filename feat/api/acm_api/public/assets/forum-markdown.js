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
  const protectedText = text.replace(/(\$\$[\s\S]+?\$\$|\\\[[\s\S]+?\\\]|\\\([\s\S]+?\\\)|\$[^$\n]+\$)/g, (formula, _match, offset, original) => {
    let slashCount = 0;
    for (let index = offset - 1; index >= 0 && original[index] === "\\"; index--) slashCount++;
    if (slashCount % 2) return formula;
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
  return formulas.reduce((result, item) => result.split(item.placeholder).join(escapeHtml(item.formula)), safeHtml);
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
  });
};
