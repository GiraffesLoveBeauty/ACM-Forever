import assert from 'node:assert/strict';
import { beforeEach, afterEach, test } from 'node:test';
import { JSDOM } from 'jsdom';
import { renderStatementMarkdown } from '../src/lib/statement-math.js';
import { addStatementSampleButtons, copyStatementSample } from '../src/lib/statement-samples.js';
const previous = Object.getOwnPropertyDescriptor(globalThis,'navigator');
let dom,root,copied;
beforeEach(()=>{
  dom=new JSDOM('<body/>',{url:'http://localhost'});root=dom.window.document.createElement('article');
  copied=[];Object.defineProperty(globalThis,'navigator',{configurable:true,value:{clipboard:{writeText:async text=>copied.push(text)}}});
});
afterEach(()=>{dom.window.close();if(previous)Object.defineProperty(globalThis,'navigator',previous);else delete globalThis.navigator;});
const render=text=>{root.innerHTML=renderStatementMarkdown(text,dom.window.document);return root;};
const click=button=>copyStatementSample({target:button,currentTarget:root});
test('buttons appear beside input and output sample labels, not after their code',()=>{
  render('样例输入 1\n\n```\n1 2\n```\n\n样例输出 1\n\n```\n3\n```');
  const buttons=root.querySelectorAll('button');assert.equal(buttons.length,2);
  assert.equal(buttons[0].getAttribute('aria-label'),'复制样例输入 1');
  for(const button of buttons)assert.equal(button.parentElement.nextElementSibling.tagName,'PRE');
});
test('copy preserves all original spaces, blank lines, markup and literal TeX',async()=>{
  render('样例输入 2\n\n```\n 1 2  \n\n<answer> \\vdots A_1\n\n```');
  assert.equal(await click(root.querySelector('button')),true);
  assert.deepEqual(copied,[' 1 2  \n\n<answer> \\vdots A_1\n\n']);
  assert.equal(root.querySelector('button').textContent,'已复制');
});
test('input and output copies stay isolated across multiple samples',async()=>{
  render('Sample Input 1\n\n```\n1\n```\n\nSample Output 1\n\n```\n2\n```\n\n入力例 2\n\n```\n3\n```');
  const buttons=root.querySelectorAll('button');await click(buttons[2]);await click(buttons[1]);await click(buttons[0]);
  assert.deepEqual(copied,['3\n','2\n','1\n']);
});
test('templates, ordinary programs and omitted output descriptions have no copy buttons',()=>{
  render('输入\n\n```\nN\nA_1\n```\n\n样例输出 1\n\n输出省略。\n\n```js\nconsole.log(1)\n```');
  assert.equal(root.querySelectorAll('button').length,0);
});
test('repeated decoration is idempotent',()=>{
  render('## 出力例 1\n\n```\nYes\n```');addStatementSampleButtons(root);addStatementSampleButtons(root);
  assert.equal(root.querySelectorAll('button').length,1);
});
test('clipboard failure reports safely and permits explicit retry',async()=>{
  render('样例输入 1\n\n```\n1\n```');navigator.clipboard.writeText=async()=>{throw Error('denied');};
  const button=root.querySelector('button');assert.equal(await click(button),false);assert.equal(button.disabled,false);
  assert.ok(root.textContent.includes('复制失败'));navigator.clipboard.writeText=async value=>copied.push(value);
  assert.equal(await click(button),true);assert.deepEqual(copied,['1\n']);
});
test('missing clipboard support shows a manual-copy notice',async()=>{
  render('样例输出 1\n\n```\n1\n```');delete navigator.clipboard;
  assert.equal(await click(root.querySelector('button')),false);assert.ok(root.textContent.includes('手动复制'));
});
test('a pending copy cannot be submitted twice by rapid clicks',async()=>{
  render('样例输入 1\n\n```\n1\n```');let finish;
  navigator.clipboard.writeText=text=>{copied.push(text);return new Promise(resolve=>finish=resolve);};
  const button=root.querySelector('button'),pending=click(button);assert.equal(button.disabled,true);
  assert.equal(await click(button),false);finish();await pending;assert.deepEqual(copied,['1\n']);
});
test('copy rejects foreign targets and unsafe sample control markup',async()=>{
  render('<button data-statement-sample="true">fake</button>\n\n样例输入 1\n\n```\n1\n```');
  const foreign=dom.window.document.createElement('button');foreign.dataset.statementSample='true';
  assert.equal(await click(foreign),false);assert.equal(root.querySelectorAll('[data-statement-sample]').length,1);
  assert.deepEqual(copied,[]);
});
test('a sample label without a literal adjacent code block has no copy control',()=>{
  render('### Sample Output 1\n\nSee the official archive.\n\n```\n1\n```');
  assert.equal(root.querySelectorAll('button').length,0);
});
