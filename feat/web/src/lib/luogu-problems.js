const palette = {
  'grey-3': '#bfbfbf',
  'gray-3': '#bfbfbf',
  'pink-3': '#fe4c61',
  'red-3': '#e74c3c',
  'orange-3': '#f39c11',
  'gold-3': '#ffc116',
  'green-3': '#52c41a',
  'cyan-3': '#13c2c2',
  'blue-3': '#3498db',
  'lapis-3': '#2949b4',
  'lapis-4': '#0e1d69',
  'grey-5': '#262626',
  'purple-3': '#9d3dcf',
  'geekblue-3': '#0e1d69',
};
export function nativeColor(token) {
  return palette[token] || '#85928d';
}
export function nativeFilters(query = {}) {
  const result = { native_difficulty: '', native_tag: '' };
  if (query.platform !== 'luogu' || query.view === 'tracker') return result;
  for (const key of Object.keys(result)) {
    const value = query[key];
    if (
      typeof value === 'string' &&
      /^-?[0-9]{1,9}$/.test(value) &&
      (key !== 'native_difficulty' || Number(value) >= 0)
    )
      result[key] = String(Number(value));
  }
  return result;
}
export function nativeParams(query) {
  return Object.fromEntries(
    Object.entries(nativeFilters(query)).filter(([, value]) => value !== ''),
  );
}
export function luoguCollection(form) {
  if (!['problems', 'catalog', 'platform'].includes(form.scope))
    throw Error('请选择有效的洛谷采集范围。');
  const payload = {
    platform: 'luogu',
    scope: form.scope,
    language: 'zh-CN',
    refresh: Boolean(form.refresh),
  };
  if (form.scope === 'problems') {
    const ids = String(form.problem_ids || '')
      .trim()
      .split(/[\s,，]+/)
      .filter(Boolean);
    if (!ids.length || ids.length > 100) throw Error('请填写 1–100 个洛谷 P 题号。');
    if (ids.some((id) => !/^P[1-9][0-9]{0,8}$/i.test(id)))
      throw Error('仅支持 P 加正整数题号，例如 P1001；不要填写链接。');
    payload.problem_ids = [...new Set(ids.map((id) => id.toUpperCase()))];
  }
  if (form.scope === 'platform') {
    const limit = Number(form.limit);
    if (!Number.isInteger(limit) || limit < 1 || limit > 1000)
      throw Error('本次题面上限须为 1–1000 的整数。');
    payload.limit = limit;
  }
  if (form.scope !== 'problems') {
    const batch = Number(form.batch_size);
    if (!Number.isInteger(batch) || batch < 1 || batch > 100)
      throw Error('每批处理题数须为 1–100 的整数。');
    payload.batch_size = batch;
  }
  return payload;
}
