import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';

export async function readStoredWorkbook(blob) {
  const bytes = new Uint8Array(await blob.arrayBuffer());
  const view = new DataView(bytes.buffer),
    decoder = new TextDecoder(),
    files = new Map();
  let offset = 0;
  while (view.getUint32(offset, true) === 0x04034b50) {
    assert.equal(view.getUint16(offset + 8, true), 0, 'ZIP_STORED');
    const size = view.getUint32(offset + 18, true),
      nameLength = view.getUint16(offset + 26, true);
    const start = offset + 30 + nameLength + view.getUint16(offset + 28, true);
    const name = decoder.decode(bytes.subarray(offset + 30, offset + 30 + nameLength));
    const data = bytes.subarray(start, start + size);
    let crc = 0xffffffff;
    for (const byte of data) {
      crc ^= byte;
      for (let i = 0; i < 8; i++) crc = (crc >>> 1) ^ (crc & 1 ? 0xedb88320 : 0);
    }
    assert.equal((crc ^ 0xffffffff) >>> 0, view.getUint32(offset + 14, true));
    assert.ok(!files.has(name));
    files.set(name, { offset, data: decoder.decode(data) });
    offset = start + size;
  }
  const centralStart = offset;
  for (const [name, file] of files) {
    assert.equal(view.getUint32(offset, true), 0x02014b50);
    assert.equal(view.getUint32(offset + 42, true), file.offset);
    const length = view.getUint16(offset + 28, true);
    assert.equal(decoder.decode(bytes.subarray(offset + 46, offset + 46 + length)), name);
    offset += 46 + length;
  }
  assert.equal(view.getUint32(offset, true), 0x06054b50);
  assert.equal(view.getUint16(offset + 10, true), files.size);
  assert.equal(view.getUint32(offset + 12, true), offset - centralStart);
  assert.equal(view.getUint32(offset + 16, true), centralStart);
  assert.equal(offset + 22, bytes.length);
  const xml = new JSDOM(files.get('xl/worksheets/sheet1.xml').data, { contentType: 'text/xml' });
  const document = xml.window.document;
  const rows = [...document.querySelectorAll('sheetData row')].map((row) =>
    [...row.querySelectorAll('c')].map((cell) => cell.textContent),
  );
  assert.ok(
    [...document.querySelectorAll('c')].every((cell) => cell.getAttribute('t') === 'inlineStr'),
  );
  assert.equal(document.querySelectorAll('f,hyperlink,externalReference').length, 0);
  xml.window.close();
  return { rows, files };
}
