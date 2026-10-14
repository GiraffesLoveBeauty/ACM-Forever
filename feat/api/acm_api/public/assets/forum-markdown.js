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
  const isEscapedAt = (value, index) => {
    let slashCount = 0;
    for (let cursor = index - 1; cursor >= 0 && value[cursor] === "\\"; cursor--) slashCount++;
    return slashCount % 2 === 1;
  };
  const codeMask = new Uint8Array(text.length);
  let fence = null;
  for (let lineStart = 0; lineStart < text.length;) {
    const newline = text.indexOf("\n", lineStart);
    const lineEnd = newline < 0 ? text.length : newline;
    const line = text.slice(lineStart, lineEnd);
    const containerPrefix = line.match(/^(?:(?: {0,3}>[\t ]?| {0,3}(?:[-+*]|\d{1,9}[.)])[\t ]+))*/)[0];
    const quoteDepth = (containerPrefix.match(/>/g) || []).length;
    const listIndent = /(?:[-+*]|\d{1,9}[.)])[\t ]+/.test(containerPrefix) ? containerPrefix.length : 0;
    const contentIndent = containerPrefix.length + (line.slice(containerPrefix.length).match(/^[\t ]*/)?.[0].length || 0);
    const fenceMatch = line.match(/^(?:(?: {0,3}>[\t ]?| {0,3}(?:[-+*]|\d{1,9}[.)])[\t ]+))*[\t ]{0,3}(`{3,}|~{3,})/);
    const lineLimit = newline < 0 ? lineEnd : newline + 1;
    if (fence && (quoteDepth < fence.quoteDepth || line.trim() && fence.listIndent > contentIndent)) fence = null;
    if (fence) {
      codeMask.fill(1, lineStart, lineLimit);
      if (fenceMatch && fenceMatch[1][0] === fence.character && fenceMatch[1].length >= fence.length
          && !line.slice(fenceMatch[0].length).trim()) fence = null;
    } else if (fenceMatch && (fenceMatch[1][0] !== "`" || !line.slice(fenceMatch[0].length).includes("`"))) {
      codeMask.fill(1, lineStart, lineLimit);
      fence = { character: fenceMatch[1][0], length: fenceMatch[1].length, quoteDepth, listIndent };
    }
    lineStart = lineLimit;
  }
  const backtickRuns = new Map();
  for (let index = 0; index < text.length;) {
    if (text[index] !== "`" || codeMask[index] || isEscapedAt(text, index)) { index++; continue; }
    let end = index + 1;
    while (end < text.length && text[end] === "`") end++;
    const length = end - index;
    if (!backtickRuns.has(length)) backtickRuns.set(length, []);
    backtickRuns.get(length).push(index);
    index = end;
  }
  for (const [length, runs] of backtickRuns) {
    let closingIndex = 0;
    for (const opening of runs) {
      if (codeMask[opening]) continue;
      while (closingIndex < runs.length && (runs[closingIndex] <= opening || codeMask[runs[closingIndex]])) closingIndex++;
      if (closingIndex < runs.length) {
        codeMask.fill(1, opening, runs[closingIndex] + length);
        closingIndex++;
      }
    }
  }
  const findClosingDelimiter = (value, start, delimiter, singleLine) => {
    for (let cursor = start; cursor < value.length; cursor++) {
      if (singleLine && value[cursor] === "\n") return -1;
      if (!codeMask[cursor] && value.startsWith(delimiter, cursor) && !isEscapedAt(value, cursor)) return cursor;
    }
    return -1;
  };
  const noCloserThrough = new Map();
  let protectedText = "";
  for (let index = 0; index < text.length;) {
    if (codeMask[index]) {
      protectedText += text[index];
      index++;
      continue;
    }
    let openingDelimiter = null;
    let closingDelimiter = null;
    let singleLine = false;
    if (text.startsWith("$$", index) && !isEscapedAt(text, index)) {
      openingDelimiter = closingDelimiter = "$$";
    } else if (text[index] === "$" && !isEscapedAt(text, index)) {
      openingDelimiter = closingDelimiter = "$";
      singleLine = true;
    } else if (text.startsWith("\\[", index) && !isEscapedAt(text, index)) {
      openingDelimiter = "\\[";
      closingDelimiter = "\\]";
    } else if (text.startsWith("\\(", index) && !isEscapedAt(text, index)) {
      openingDelimiter = "\\(";
      closingDelimiter = "\\)";
    }
    if (openingDelimiter) {
      const cachedBoundary = noCloserThrough.get(closingDelimiter);
      const closingIndex = cachedBoundary !== undefined && index < cachedBoundary
        ? -1
        : findClosingDelimiter(text, index + openingDelimiter.length, closingDelimiter, singleLine);
      if (closingIndex > index + openingDelimiter.length) {
        const formula = text.slice(index, closingIndex + closingDelimiter.length);
        const placeholder = `${placeholderPrefix}${formulas.length}TOKEN`;
        formulas.push({ placeholder, formula });
        protectedText += placeholder;
        noCloserThrough.delete(closingDelimiter);
        index = closingIndex + closingDelimiter.length;
        continue;
      }
      if (closingIndex < 0) {
        const newlineIndex = singleLine ? text.indexOf("\n", index + openingDelimiter.length) : -1;
        noCloserThrough.set(closingDelimiter, newlineIndex < 0 ? text.length : newlineIndex);
      }
    }
    protectedText += text[index];
    index++;
  }
  const escapedLiterals = [];
  const markdownSafeText = protectedText.replace(/(\\*)\$/g, (delimiter, slashes) => {
    if (slashes.length % 2 === 0) return delimiter;
    const placeholder = `${placeholderPrefix}${escapedLiterals.length}LITERAL`;
    escapedLiterals.push({ placeholder, text: "$", codeText: "\\$" });
    return `${slashes.slice(0, -1)}${placeholder}`;
  }).replace(/\\\\([()[\]])/g, (delimiter, bracket) => {
    const placeholder = `${placeholderPrefix}${escapedLiterals.length}LITERAL`;
    escapedLiterals.push({ placeholder, text: `\\${bracket}`, codeText: delimiter });
    return placeholder;
  });
  const html = window.marked.parse(markdownSafeText, { gfm: true, breaks: true });
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
  const formulaPattern = new RegExp(`${placeholderPrefix}(\\d+)TOKEN`, "g");
  const formulaInCode = new Set();
  const formulaBlockquoteDepth = new Map();
  if (formulas.length) {
    const formulaProbe = document.createElement("div");
    formulaProbe.innerHTML = safeHtml;
    const walker = document.createTreeWalker(formulaProbe, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
      const node = walker.currentNode;
      const inCode = Boolean(node.parentElement?.closest("code, pre"));
      let blockquoteDepth = 0;
      for (let parent = node.parentElement; parent; parent = parent.parentElement) {
        if (parent.tagName === "BLOCKQUOTE") blockquoteDepth++;
      }
      if (!inCode && !blockquoteDepth) continue;
      formulaPattern.lastIndex = 0;
      let match;
      while ((match = formulaPattern.exec(node.nodeValue))) {
        const index = Number(match[1]);
        if (inCode) formulaInCode.add(index);
        if (blockquoteDepth) formulaBlockquoteDepth.set(index, blockquoteDepth);
      }
    }
  }
  formulaPattern.lastIndex = 0;
  const withFormulas = safeHtml.replace(formulaPattern, (placeholder, index) => {
    const formula = formulas[Number(index)];
    if (!formula) return placeholder;
    const code = formulaInCode.has(Number(index));
    const blockquoteDepth = formulaBlockquoteDepth.get(Number(index)) || 0;
    const normalizedFormula = blockquoteDepth && !code
      ? formula.formula.replace(/\n([\t ]*)((?:>[\t ]?)+)/g, (line, indentation, quoteMarkers) => {
        let remaining = quoteMarkers;
        for (let depth = 0; depth < blockquoteDepth; depth++) {
          const prefix = remaining.match(/^>[\t ]?/);
          if (!prefix) break;
          remaining = remaining.slice(prefix[0].length);
        }
        return `\n${remaining}`;
      })
      : formula.formula;
    return escapeHtml(normalizedFormula);
  });
  if (!escapedLiterals.length) return withFormulas;
  const container = document.createElement("div");
  container.innerHTML = withFormulas;
  const placeholderPattern = new RegExp(`${placeholderPrefix}(\\d+)LITERAL`, "g");
  const restoreLiteralAttribute = value => value.replace(placeholderPattern, (placeholder, index) => escapedLiterals[Number(index)]?.text ?? placeholder);
  container.querySelectorAll("[href], [title]").forEach(element => {
    ["href", "title"].forEach(attribute => {
      if (element.hasAttribute(attribute)) element.setAttribute(attribute, restoreLiteralAttribute(element.getAttribute(attribute)));
    });
  });
  const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
  const textNodes = [];
  while (walker.nextNode()) textNodes.push(walker.currentNode);
  textNodes.forEach(node => {
    placeholderPattern.lastIndex = 0;
    let match;
    let previousIndex = 0;
    let foundPlaceholder = false;
    const fragment = document.createDocumentFragment();
    const insideCode = Boolean(node.parentElement?.closest("code, pre"));
    while ((match = placeholderPattern.exec(node.nodeValue))) {
      const literal = escapedLiterals[Number(match[1])];
      if (!literal) continue;
      foundPlaceholder = true;
      if (match.index > previousIndex) {
        fragment.appendChild(document.createTextNode(node.nodeValue.slice(previousIndex, match.index)));
      }
      if (literal) {
        if (insideCode) {
          fragment.appendChild(document.createTextNode(literal.codeText));
        } else {
          const dollar = document.createElement("span");
          dollar.className = "tex2jax_ignore";
          dollar.textContent = literal.text;
          fragment.appendChild(dollar);
        }
      }
      previousIndex = placeholderPattern.lastIndex;
    }
    if (!foundPlaceholder) return;
    if (previousIndex < node.nodeValue.length) {
      fragment.appendChild(document.createTextNode(node.nodeValue.slice(previousIndex)));
    }
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
    maxSize: 20,
    maxExpand: 1000,
    ignoredClasses: ["tex2jax_ignore"],
  });
};
