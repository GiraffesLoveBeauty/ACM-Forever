// Copy only literal sample blocks, never rendered formula templates or innerText.
export function addStatementSampleButtons(root) {
  for (const heading of root.querySelectorAll('h1,h2,h3,h4,h5,h6,p')) {
    if (heading.closest('pre,code,details,.statement-io-format') || heading.querySelector('button')) continue;
    const label = heading.textContent.trim().replace(/[：:]$/, '').trim();
    const match = label.match(/^(样例输入|样例输出|输入样例|输出样例|输入示例|输出示例|Sample Input|Sample Output|入力例|出力例)\s*(\d+)?$/i);
    const pre = heading.nextElementSibling;
    if (!match || pre?.tagName !== 'PRE') continue;
    const kind = /输入|Input|入力/i.test(match[1]) ? '输入' : '输出';
    const index = match[2] || '1';
    const button = root.ownerDocument.createElement('button');
    button.type = 'button'; button.className = 'btn statement-sample-copy';
    button.dataset.statementSample = 'true';
    button.textContent = '复制'; button.setAttribute('aria-label', `复制样例${kind} ${index}`);
    const status = root.ownerDocument.createElement('span');
    status.className = 'statement-sample-copy-status'; status.setAttribute('role','status');
    status.setAttribute('aria-live','polite');
    heading.classList.add('statement-sample-heading'); heading.append(button,status);
  }
}

export async function copyStatementSample(event) {
  const container = event.currentTarget;
  const button = event.target.closest?.('button[data-statement-sample="true"]');
  if (!button || !container?.contains(button) || button.disabled) return false;
  const heading = button.closest('.statement-sample-heading'), pre = heading?.nextElementSibling;
  if (!heading || pre?.tagName !== 'PRE' || pre.closest('.statement-io-format')) return false;
  const original = pre.textContent;
  const status = heading.querySelector('.statement-sample-copy-status');
  button.disabled = true;
  try {
    await navigator.clipboard.writeText(original);
    if (container.contains(button)) {
      button.textContent = '已复制';
      if (status) status.textContent = '复制成功';
    }
    return true;
  } catch {
    if (container.contains(button)) {
      button.textContent = '重试复制';
      if (status) status.textContent = '复制失败，请选择样例文本手动复制。';
    }
    return false;
  } finally { button.disabled = false; }
}
