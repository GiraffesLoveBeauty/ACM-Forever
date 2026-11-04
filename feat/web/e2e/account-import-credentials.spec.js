import { test, expect } from '@playwright/test';
import { spawnSync } from 'node:child_process';
const python = process.env.ACM_E2E_PYTHON || 'python';
function runPython(script, input) {
  const result = spawnSync(python, ['-c', script], {
    cwd: new URL('../../../', import.meta.url),
    input,
    maxBuffer: 2 * 1024 * 1024,
    timeout: 15000,
  });
  expect(result.status, result.stderr?.toString()).toBe(0);
  return result.stdout;
}

test('WPS-style upload skips bad OJ fields, creates QQ accounts and exports received credentials', async ({
  page,
  context,
}, testInfo) => {
  const base = testInfo.project.name === 'mobile' ? 202611040200 : 202611040100;
  const upload = runPython(`
import io,sys,zipfile
from openpyxl import load_workbook
from openpyxl.packaging.custom import StringProperty
from feat.api.acm_api.account_import_excel import template_bytes
book=load_workbook(io.BytesIO(template_bytes()))
for i in range(12):
    for col,value in enumerate([str(${base}+i),'合成昵称'+str(i),'合成姓名'+str(i)],1):
        book['导入数据'].cell(i+2,col,value)
book['导入数据']['F2']='Has\\u2006Space'
book['导入数据']['F3']=1234567890
book['导入数据']['G3']='not_a_uid'
book['导入数据']['F4']='Synthetic${testInfo.project.name}'
book.custom_doc_props.append(StringProperty(name='KSOProductBuildVer',value='Synthetic-only'))
out=io.BytesIO();book.save(out)
with zipfile.ZipFile(out,'a') as z:
    for name in ['_rels/','docProps/','xl/','xl/_rels/','xl/theme/','xl/worksheets/']:
        z.writestr(name,b'')
sys.stdout.buffer.write(out.getvalue())
`);
  const login = await context.request.post('/api/auth/login', {
    data: { qq_id: '10000003', password: 'Browser-fixture-only!2026' },
  });
  expect(login.status()).toBe(200);
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('dialog', (dialog) => dialog.accept());
  await page.goto('/admin.html?section=accounts&tab=import');
  const toggle = page.getByRole('switch', { name: 'Excel 导入开关' });
  if (!(await toggle.isChecked())) await toggle.click();
  await page.locator('#import-file').setInputFiles({
    name: 'synthetic-wps.xlsx',
    mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    buffer: upload,
  });
  await page.getByRole('button', { name: '上传并校验' }).click();
  await expect(page.getByRole('button', { name: '选中本页' })).toBeVisible();
  await expect(page.getByText(/已跳过绑定/).first()).toBeVisible();
  await page.getByRole('button', { name: '选中本页' }).click();
  await page.getByRole('checkbox', { name: /我已核对将录入的 OJ/ }).check();
  await page.getByRole('button', { name: '确认创建所选账号' }).click();
  const exportButton = page.getByRole('button', { name: '导出开户 Excel（含初始密码）' });
  await expect(page.getByText(/本页已领取\s*12\s*份/)).toBeVisible({ timeout: 30000 });
  const received = page.waitForEvent('download');
  await exportButton.click();
  const download = await received;
  expect(download.suggestedFilename()).toBe('account-import-credentials.xlsx');
  const parts = [];
  for await (const part of await download.createReadStream()) parts.push(part);
  const exported = Buffer.concat(parts);
  const data = JSON.parse(
    runPython(
      `
import io,json,sys,zipfile
from openpyxl import load_workbook
content=sys.stdin.buffer.read()
with zipfile.ZipFile(io.BytesIO(content)) as z:
    assert z.testzip() is None
book=load_workbook(io.BytesIO(content),data_only=False)
assert book.sheetnames==['开户凭据']
assert all(c.data_type=='s' and c.number_format=='@' and not c.hyperlink for row in book.active for c in row)
print(json.dumps(list(book.active.values),ensure_ascii=True))
`,
      exported,
    ).toString(),
  );
  expect(data[0]).toEqual(['QQ号', '姓名', '账号', '初始密码']);
  expect(data).toHaveLength(13);
  for (let i = 0; i < 12; i++) {
    expect(data[i + 1].slice(0, 3)).toEqual([String(base + i), `合成姓名${i}`, String(base + i)]);
    expect(data[i + 1][3].length).toBeGreaterThanOrEqual(16);
  }
  expect(new Set(data.slice(1).map((row) => row[3])).size).toBe(12);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await page.screenshot({
    path: testInfo.outputPath('account-import-credentials.png'),
    fullPage: true,
  });
  await page.reload();
  await expect(page.getByText(/本页未领取其初始密码/)).toBeVisible();
  await expect(exportButton).toHaveCount(0);
  expect(errors).toEqual([]);
});
