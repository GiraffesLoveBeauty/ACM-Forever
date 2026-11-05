import assert from 'node:assert/strict';
import { test } from 'node:test';
import { credentialsWorkbook } from '../src/lib/account-import-credentials.js';
import { readStoredWorkbook } from './helpers/xlsx.mjs';

test('credential Excel contains QQ, real name, login and initial password as text', async () => {
  const input = [
    {
      qq_id: '123456789012',
      real_name: '合成姓名<&>😀',
      name: '不是姓名',
      username: '123456789012',
      temporary_password: 'Synthetic-only!2026',
    },
  ];
  const blob = credentialsWorkbook(input);
  assert.equal(blob.type, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');
  const { rows, files } = await readStoredWorkbook(blob);
  assert.deepEqual(rows, [
    ['QQ号', '姓名', '账号', '初始密码'],
    ['123456789012', '合成姓名<&>😀', '123456789012', 'Synthetic-only!2026'],
  ]);
  assert.equal(files.size, 6);
  assert.match(files.get('xl/styles.xml').data, /numFmtId="49"/);
  assert.deepEqual(input[0].name, '不是姓名');
});
test('formula-like names and passwords remain literal; missing real name never uses nickname', async () => {
  const credentials = [
    {
      qq_id: '10000084',
      real_name: '=HYPERLINK("https://invalid.example")',
      temporary_password: '+@-Synthetic<&>',
    },
    { qq_id: '10000085', name: '只有昵称', temporary_password: 'Synthetic-secret' },
  ];
  const { rows } = await readStoredWorkbook(credentialsWorkbook(credentials));
  assert.deepEqual(rows[1], ['10000084', credentials[0].real_name, '10000084', '+@-Synthetic<&>']);
  assert.deepEqual(rows[2], ['10000085', '', '10000085', 'Synthetic-secret']);
});
test('all 200 received credentials survive Unicode, ZIP CRC and directory checks', async () => {
  const input = Array.from({ length: 200 }, (_, i) => ({
    qq_id: String(10000084 + i),
    real_name: `合成${i}`,
    temporary_password: `Synthetic${i}!`,
  }));
  const { rows } = await readStoredWorkbook(credentialsWorkbook(input));
  assert.equal(rows.length, 201);
  assert.deepEqual(rows[200], ['10000283', '合成199', '10000283', 'Synthetic199!']);
});
