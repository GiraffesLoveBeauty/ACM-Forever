import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { JSDOM } from 'jsdom';
import { renderStatementMarkdown } from '../src/lib/statement-math.js';

// Python tests assert these Markdown values come from html_statement(), and also
// survive the real translation protocol with an offline echo. No real OJ text.
const fixtures = JSON.parse(readFileSync(new URL(
  '../../../experiments/tags/ACM_Forever_Chinese_Tags_V0.3/tests/fixtures/statement_literals.json',
  import.meta.url), 'utf8'));
for (const row of fixtures) {
  test(`converted HTML text stays literal: ${row.name}`, () => {
    const dom = new JSDOM('<body/>', { url: 'http://localhost' });
    const root = dom.window.document.createElement('div');
    root.innerHTML = renderStatementMarkdown(row.markdown, dom.window.document);
    assert.equal(root.textContent.trim(), row.visible);
    assert.equal(root.querySelectorAll('br').length, row.breaks);
    assert.equal(root.querySelectorAll('script,img,a,math,pre,li,h1,em,del').length, 0);
    assert.equal(root.querySelectorAll('code').length, row.code || 0);
    dom.window.close();
  });
}
