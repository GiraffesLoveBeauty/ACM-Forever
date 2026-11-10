// Generate a small, uncompressed XLSX locally: plaintext credentials never leave this page.
const mime = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
const encoder = new TextEncoder();
const crcTable = Uint32Array.from({ length: 256 }, (_, value) => {
  for (let i = 0; i < 8; i++) value = (value >>> 1) ^ (value & 1 ? 0xedb88320 : 0);
  return value >>> 0;
});
function crc32(bytes) {
  let value = 0xffffffff;
  for (const byte of bytes) value = (value >>> 8) ^ crcTable[(value ^ byte) & 255];
  return (value ^ 0xffffffff) >>> 0;
}
function xml(value) {
  return String(value ?? '')
    .replace(/[^\u0009\u000a\u000d\u0020-\ud7ff\ue000-\ufffd\u{10000}-\u{10ffff}]/gu, '')
    .replace(
      /[&<>"']/g,
      (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&apos;' })[c],
    );
}
function zip(files) {
  const local = [],
    central = [];
  let offset = 0;
  for (const [path, content] of Object.entries(files)) {
    const name = encoder.encode(path),
      data = encoder.encode(content),
      crc = crc32(data);
    const header = new Uint8Array(30 + name.length),
      view = new DataView(header.buffer);
    view.setUint32(0, 0x04034b50, true);
    view.setUint16(4, 20, true);
    view.setUint16(6, 0x0800, true);
    view.setUint16(12, 0x21, true); // 1980-01-01, for deterministic archives.
    view.setUint32(14, crc, true);
    view.setUint32(18, data.length, true);
    view.setUint32(22, data.length, true);
    view.setUint16(26, name.length, true);
    header.set(name, 30);
    local.push(header, data);
    const entry = new Uint8Array(46 + name.length),
      index = new DataView(entry.buffer);
    index.setUint32(0, 0x02014b50, true);
    index.setUint16(4, 20, true);
    index.setUint16(6, 20, true);
    index.setUint16(8, 0x0800, true);
    index.setUint16(14, 0x21, true);
    index.setUint32(16, crc, true);
    index.setUint32(20, data.length, true);
    index.setUint32(24, data.length, true);
    index.setUint16(28, name.length, true);
    index.setUint32(42, offset, true);
    entry.set(name, 46);
    central.push(entry);
    offset += header.length + data.length;
  }
  const footer = new Uint8Array(22),
    end = new DataView(footer.buffer);
  end.setUint32(0, 0x06054b50, true);
  end.setUint16(8, central.length, true);
  end.setUint16(10, central.length, true);
  end.setUint32(
    12,
    central.reduce((size, part) => size + part.length, 0),
    true,
  );
  end.setUint32(16, offset, true);
  return new Blob([...local, ...central, footer], { type: mime });
}
export function credentialsWorkbook(
  credentials,
  { passwordLabel = '初始密码', nameLabel = '姓名', sheetName = '开户凭据' } = {},
) {
  const values = [
    ['QQ号', nameLabel, '账号', passwordLabel],
    ...credentials.map((row) => [
      row.qq_id,
      row.real_name || '',
      row.username || row.qq_id,
      row.temporary_password,
    ]),
  ];
  const sheet = values
    .map(
      (row, r) =>
        `<row r="${r + 1}">${row
          .map(
            (value, c) =>
              `<c r="${String.fromCharCode(65 + c)}${r + 1}" s="1" t="inlineStr"><is><t xml:space="preserve">${xml(value)}</t></is></c>`,
          )
          .join('')}</row>`,
    )
    .join('');
  // Inline strings + text styles prevent formula/URL interpretation and QQ rounding.
  return zip({
    '[Content_Types].xml': `<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>`,
    '_rels/.rels': `<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>`,
    'xl/workbook.xml': `<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="${xml(sheetName)}" sheetId="1" r:id="rId1"/></sheets></workbook>`,
    'xl/_rels/workbook.xml.rels': `<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>`,
    'xl/styles.xml': `<?xml version="1.0" encoding="UTF-8"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts><fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="49" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>`,
    'xl/worksheets/sheet1.xml': `<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><cols><col min="1" max="3" width="22" customWidth="1"/><col min="4" max="4" width="34" customWidth="1"/></cols><sheetData>${sheet}</sheetData><autoFilter ref="A1:D${values.length}"/></worksheet>`,
  });
}
