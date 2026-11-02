import { codeLanguage } from './markdown-code.js';

async function copyText(text) {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return;
    }
  } catch {
    // HTTP deployments and denied Clipboard API access can still use native copy.
  }
  const active = document.activeElement;
  const selection = window.getSelection();
  const ranges = Array.from({ length: selection?.rangeCount || 0 }, (_, i) =>
    selection.getRangeAt(i).cloneRange(),
  );
  const input = document.createElement('textarea');
  input.value = text;
  input.readOnly = true;
  input.setAttribute('aria-label', '复制代码临时内容');
  input.style.cssText = 'position:fixed;left:-9999px;top:0;font-size:16px;';
  document.body.append(input);
  input.focus({ preventScroll: true });
  input.select();
  try {
    if (!document.execCommand?.('copy')) throw Error('Clipboard unavailable');
  } finally {
    input.remove();
    active?.focus?.({ preventScroll: true });
    selection?.removeAllRanges();
    ranges.forEach((range) => selection?.addRange(range));
  }
}

const roots = new WeakMap();
function enhance(root) {
  let controls = roots.get(root);
  if (!controls) roots.set(root, (controls = new Map()));
  for (const [code, control] of controls) {
    if (root.contains(code)) continue;
    control.active = false;
    controls.delete(code);
  }
  for (const code of root.querySelectorAll('pre > code')) {
    if (controls.has(code)) continue;
    const pre = code.parentElement;
    pre.classList.add('markdown-code-block');
    code.tabIndex = 0;
    const toolbar = document.createElement('span');
    toolbar.className = 'markdown-code-toolbar';
    const label = document.createElement('span');
    label.className = 'markdown-code-language';
    label.textContent = codeLanguage(code).label;
    const status = document.createElement('span');
    status.className = 'code-copy-status';
    status.setAttribute('role', 'status');
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'code-copy';
    button.textContent = '复制代码';
    const control = { active: true, copying: false };
    controls.set(code, control);
    button.addEventListener('click', async (event) => {
      event.stopPropagation();
      if (control.copying) return;
      control.copying = true;
      button.setAttribute('aria-busy', 'true');
      status.textContent = '';
      try {
        await copyText(code.textContent);
        if (!control.active) return;
        button.textContent = '已复制';
        status.textContent = '代码已复制。';
      } catch {
        if (!control.active) return;
        button.textContent = '重试复制';
        status.textContent = '复制失败，请选中代码后手动复制。';
      } finally {
        control.copying = false;
        button.removeAttribute('aria-busy');
      }
    });
    toolbar.append(label, status, button);
    pre.prepend(toolbar);
  }
}

export const codeBlocks = {
  mounted: enhance,
  updated: enhance,
  beforeUnmount(root) {
    for (const control of roots.get(root)?.values() || []) control.active = false;
    roots.delete(root);
  },
};
