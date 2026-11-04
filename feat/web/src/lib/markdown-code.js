import hljs from 'highlight.js/lib/core';
import cpp from 'highlight.js/lib/languages/cpp';
import python from 'highlight.js/lib/languages/python';
import java from 'highlight.js/lib/languages/java';

hljs.registerLanguage('cpp', cpp);
hljs.registerLanguage('python', python);
hljs.registerLanguage('java', java);

const languages = {
  cpp: ['cpp', 'C++'],
  'c++': ['cpp', 'C++'],
  cc: ['cpp', 'C++'],
  cxx: ['cpp', 'C++'],
  python: ['python', 'Python'],
  py: ['python', 'Python'],
  python3: ['python', 'Python'],
  py3: ['python', 'Python'],
  java: ['java', 'Java'],
};

export function codeLanguage(code) {
  const declared = /(?:^|\s)language-([^\s]+)/i.exec(code.className)?.[1]?.toLowerCase() || '';
  const [language, label] = Object.hasOwn(languages, declared)
    ? languages[declared]
    : [null, declared.slice(0, 32) || '纯文本'];
  return { language, label };
}

// Highlight only declared, bundled languages. Unknown fences remain plain text.
export function highlightCode(root) {
  for (const code of root.querySelectorAll('pre > code')) {
    const { language } = codeLanguage(code);
    if (!language) continue;
    const source = code.textContent;
    // highlight.js escapes source text before inserting its own token spans.
    code.innerHTML = hljs.highlight(source, { language, ignoreIllegals: true }).value;
    code.classList.add('hljs');
  }
}
