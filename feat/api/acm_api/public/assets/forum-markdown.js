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
  const markRawHtmlCodeRanges = () => {
    const htmlTokens = [];
    const collectHtmlTokens = tokens => {
      for (const token of tokens || []) {
        if (token.type === "html") htmlTokens.push(token.raw);
        if (token.tokens) collectHtmlTokens(token.tokens);
        if (token.items) for (const item of token.items) collectHtmlTokens(item.tokens);
      }
    };
    collectHtmlTokens(window.marked.lexer(text, { gfm: true }));

    const codeElements = [];
    let sourceCursor = 0;
    for (const raw of htmlTokens) {
      if (!raw) continue;
      const tokenStart = text.indexOf(raw, sourceCursor);
      if (tokenStart < 0) continue;
      const tagPattern = /<\/?(code|pre)\b[^>]*>/gi;
      let tag;
      while ((tag = tagPattern.exec(raw))) {
        codeElements.push({
          name: tag[1].toLowerCase(),
          closing: /^<\//.test(tag[0]),
          selfClosing: /\/\s*>$/.test(tag[0]),
          start: tokenStart + tag.index,
          end: tokenStart + tag.index + tag[0].length
        });
      }
      sourceCursor = tokenStart + raw.length;
    }

    const openElements = [];
    let rangeStart = -1;
    for (const element of codeElements) {
      if (!element.closing && !element.selfClosing) {
        if (!openElements.length) rangeStart = element.start;
        openElements.push(element.name);
      } else if (element.closing) {
        const matchingIndex = openElements.lastIndexOf(element.name);
        if (matchingIndex < 0) continue;
        openElements.length = matchingIndex;
        if (!openElements.length) {
          codeMask.fill(1, rangeStart, element.end);
          rangeStart = -1;
        }
      }
    }
    if (rangeStart >= 0) codeMask.fill(1, rangeStart);
  };
  markRawHtmlCodeRanges();
  const indentationColumns = value => {
    let columns = 0;
    for (const character of value) columns = character === "\t" ? columns + 4 - columns % 4 : columns + 1;
    return columns;
  };
  let fence = null;
  let listContentIndents = [];
  let listContextQuoteDepth = 0;
  for (let lineStart = 0; lineStart < text.length;) {
    const newline = text.indexOf("\n", lineStart);
    const lineEnd = newline < 0 ? text.length : newline;
    const line = text.slice(lineStart, lineEnd);
    const containerPrefix = line.match(/^(?:(?: {0,3}>[\t ]?| {0,3}(?:[-+*]|\d{1,9}[.)])[\t ]+))*/)[0];
    const quoteDepth = (containerPrefix.match(/>/g) || []).length;
    const contentIndent = indentationColumns(containerPrefix + (line.slice(containerPrefix.length).match(/^[\t ]*/)?.[0] || ""));
    const listMarkers = [...containerPrefix.matchAll(/([-+*]|\d{1,9}[.)])[\t ]+/g)];
    if (listMarkers.length) {
      if (listContextQuoteDepth !== quoteDepth) listContentIndents = [];
      const nextListIndents = listContentIndents.filter(indent => indent <= indentationColumns(containerPrefix.slice(0, listMarkers[0].index)));
      for (const marker of listMarkers) {
        const markerIndent = indentationColumns(containerPrefix.slice(0, marker.index));
        while (nextListIndents.length && nextListIndents[nextListIndents.length - 1] > markerIndent) nextListIndents.pop();
        const contentColumn = indentationColumns(containerPrefix.slice(0, marker.index + marker[0].length));
        if (nextListIndents[nextListIndents.length - 1] !== contentColumn) nextListIndents.push(contentColumn);
      }
      listContentIndents = nextListIndents;
      listContextQuoteDepth = quoteDepth;
    } else {
      if (quoteDepth < listContextQuoteDepth) { listContentIndents = []; listContextQuoteDepth = quoteDepth; }
      const nestedListMarker = line.match(/^([\t ]+)([-+*]|\d{1,9}[.)])[\t ]+/);
      let recognizedNestedListMarker = false;
      if (nestedListMarker && listContentIndents.length && quoteDepth === listContextQuoteDepth) {
        const markerIndent = indentationColumns(nestedListMarker[1]);
        if (markerIndent >= listContentIndents[listContentIndents.length - 1]) {
          recognizedNestedListMarker = true;
          while (listContentIndents.length && listContentIndents[listContentIndents.length - 1] > markerIndent) listContentIndents.pop();
          const contentColumn = markerIndent + indentationColumns(nestedListMarker[2] + nestedListMarker[0].slice(nestedListMarker[1].length + nestedListMarker[2].length));
          if (listContentIndents[listContentIndents.length - 1] !== contentColumn) listContentIndents.push(contentColumn);
        }
      }
      if (!recognizedNestedListMarker && line.trim()) while (listContentIndents.length && contentIndent < listContentIndents[listContentIndents.length - 1]) listContentIndents.pop();
    }
    const listIndent = listContentIndents[listContentIndents.length - 1] || 0;
    const fenceMatch = line.match(/^(?:(?: {0,3}>[\t ]?| {0,3}(?:[-+*]|\d{1,9}[.)])[\t ]+))* {0,3}(`{3,}|~{3,})/);
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
    if (!fence && !codeMask[lineStart]) {
      if (contentIndent - listIndent >= 4) codeMask.fill(1, lineStart, lineLimit);
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
  const syntaxMask = new Uint8Array(text.length);
  const maskSyntax = (start, end) => syntaxMask.fill(1, start, end);
  // Formula delimiters inside link destinations and markup attributes are data,
  // not visible Markdown text. Keep link labels available for formula rendering.
  for (let index = 0; index < text.length; index++) {
    if (text[index] !== "<" || codeMask[index] || isEscapedAt(text, index)) continue;
    const end = text.indexOf(">", index + 1);
    if (end < 0 || text.slice(index, end).includes("\n")) continue;
    const contents = text.slice(index + 1, end);
    if (/^(?:\/?[a-z][\w:-]*(?:\s[^<>]*|\s*\/)?|!--[\s\S]*|![A-Z][^<>]*)$/i.test(contents)
        || /^(?:[a-z][a-z\d+.-]{1,31}:[^ <>]*|[^ <>@]+@[^ <>@]+\.[^ <>@]+)$/i.test(contents)) {
      maskSyntax(index, end + 1);
      index = end;
    }
  }
  for (let index = 0; index < text.length; index++) {
    if (text[index] !== "]" || codeMask[index] || syntaxMask[index] || isEscapedAt(text, index)
        || text[index + 1] !== "(") continue;
    let depth = 0;
    for (let cursor = index + 2; cursor < text.length; cursor++) {
      if (codeMask[cursor] || isEscapedAt(text, cursor)) continue;
      if (text[cursor] === "(") depth++;
      else if (text[cursor] === ")") {
        if (depth === 0) {
          maskSyntax(index + 1, cursor + 1);
          index = cursor;
          break;
        }
        depth--;
      }
    }
  }
  const maskMatches = pattern => {
    let match;
    while ((match = pattern.exec(text))) {
      let hasCode = false;
      for (let index = match.index; index < pattern.lastIndex; index++) {
        if (codeMask[index]) { hasCode = true; break; }
      }
      if (!hasCode) maskSyntax(match.index, pattern.lastIndex);
    }
  };
  maskMatches(/\b(?:https?:\/\/|www\.)[^\s<>]+/gi);
  maskMatches(/\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/gi);
  maskMatches(/^[\t ]{0,3}\[[^\]\n]+\]:[^\n]*/gm);
  const findClosingDelimiter = (value, start, delimiter, singleLine) => {
    for (let cursor = start; cursor < value.length; cursor++) {
      if (singleLine && value[cursor] === "\n") return -1;
      if (!codeMask[cursor] && !syntaxMask[cursor] && value.startsWith(delimiter, cursor) && !isEscapedAt(value, cursor)) return cursor;
    }
    return -1;
  };
  const noCloserThrough = new Map();
  let protectedText = "";
  for (let index = 0; index < text.length;) {
    if (codeMask[index] || syntaxMask[index]) {
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
