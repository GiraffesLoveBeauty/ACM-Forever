export const rangeKeys = ['rating_min', 'rating_max', 'start_at', 'end_at', 'time_basis'];
export function rangeFilters(query = {}) {
  const result = Object.fromEntries(rangeKeys.map((key) => [key, '']));
  if (query.view === 'tracker') return result;
  for (const key of ['rating_min', 'rating_max'])
    if (
      ['atcoder', 'codeforces'].includes(query.platform) &&
      /^[0-9]{1,6}$/.test(String(query[key] ?? ''))
    )
      result[key] = String(Number(query[key]));
  for (const key of ['start_at', 'end_at'])
    if (/^[0-9]{1,12}$/.test(String(query[key] ?? ''))) result[key] = String(Number(query[key]));
  if (result.start_at || result.end_at)
    result.time_basis =
      ['auto', 'contest', 'first_seen'].includes(query.time_basis) &&
      !(query.platform === 'luogu' && query.time_basis === 'contest')
        ? query.time_basis
        : query.platform === 'luogu'
          ? 'first_seen'
          : 'auto';
  return result;
}
export function rangeParams(query) {
  return Object.fromEntries(
    Object.entries(rangeFilters(query)).filter(([, value]) => value !== ''),
  );
}
export function localTime(value) {
  if (value === '' || value == null) return '';
  const time = new Date((Number(value) + 8 * 3600) * 1000);
  return Number.isNaN(time.getTime()) ? '' : time.toISOString().slice(0, 16);
}
export function timeValue(value) {
  if (!value) return '';
  const seconds = Date.parse(value + ':00+08:00') / 1000;
  if (!Number.isSafeInteger(seconds) || seconds < 0) throw Error('请选择有效的北京时间。');
  return String(seconds);
}
export function collectionTime(form) {
  if (form.scope !== 'platform' || form.range_mode !== 'time') return {};
  const result = {};
  for (const key of ['start_at', 'end_at']) {
    if (form[key] === '' || form[key] == null) continue;
    if (!/^[0-9]{1,12}$/.test(String(form[key]))) throw Error('请选择有效的同步时间。');
    result[key] = Number(form[key]);
  }
  if (!Object.keys(result).length) throw Error('请至少选择开始或结束时间。');
  if (result.start_at != null && result.end_at != null && result.start_at >= result.end_at)
    throw Error('结束时间必须晚于开始时间。');
  result.time_basis = form.platform === 'luogu' ? 'first_seen' : form.time_basis || 'contest';
  return result;
}
export function timeLabel(row) {
  return (
    { contest: '比赛时间', first_seen: '首次收录', unknown: '时间未知' }[row.time_basis] ||
    '时间未知'
  );
}
