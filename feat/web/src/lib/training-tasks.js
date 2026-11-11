export const phases = {
  draft: '草稿',
  active: '进行中',
  upcoming: '未开始',
  ended: '已结束',
  cancelled: '已取消',
};
export const completions = {
  on_time: '按时完成',
  late: '逾期完成',
  incomplete: '待完成',
  not_started: '未开始',
  history_ac: '历史已做',
  pending: '尚无有效 AC 证据',
};
export const verifications = {
  verified: '已核验',
  pending: '待核验',
  pending_sync: '等待更新证据',
  coverage_missing: '历史覆盖不足，待同步',
  unbound: '待绑定 Codeforces',
  binding_changed: '绑定已变化，待核验',
  sync_failed: '同步失败，已有证据保留',
  sync_paused: '平台暂停同步',
  account_closed: '账号已注销',
  account_changed: '账号代际已变化',
  account_disabled: '账号已停用',
};
export const exclusions = {
  no_web_account: '未开通网页账号',
  account_disabled: '网页账号已停用',
  account_closed: '账号已注销',
  account_unavailable: '账号不可用或临时密码已过期',
};
export const ruleName = (rule) => (rule === 'historical_ac' ? '历史 AC 可计入' : '周期内 AC');
export const platformName = (platform) =>
  ({
    codeforces: 'Codeforces',
    atcoder: 'AtCoder',
    luogu: '洛谷',
    nowcoder: '牛客',
    cjlu: '校 OJ',
  })[platform] || platform;
export function localTime(value) {
  return value ? new Date(value * 1000 + 8 * 3600000).toISOString().slice(0, 16) : '';
}
export function utcTime(value) {
  if (!value) return null;
  const stamp = Date.parse(value + ':00+08:00') / 1000;
  return Number.isFinite(stamp) ? stamp : null;
}
export function newDraft() {
  const now = Math.floor(Date.now() / 1000);
  return {
    title: '',
    description: '',
    statuses: [],
    starts_at: localTime(now),
    due_at: localTime(now + 7 * 86400),
    rule: 'period_ac',
    problems: [],
  };
}
export function taskForm(task) {
  return {
    title: task.title,
    description: task.description,
    statuses: [...task.statuses],
    starts_at: localTime(task.starts_at),
    due_at: localTime(task.due_at),
    rule: task.rule,
    problems: [...task.problems],
  };
}
export function taskPayload(form, version) {
  return {
    ...form,
    version,
    starts_at: utcTime(form.starts_at),
    due_at: utcTime(form.due_at),
    problems: form.problems.map((p) => ({ platform: p.platform, problem_id: p.problem_id })),
  };
}
export const fraction = (done, total) =>
  Math.min(100, Math.max(0, total ? (100 * done) / total : 0));
export const tagList = (value) =>
  Array.isArray(value)
    ? value
    : String(value || '')
        .split(',')
        .filter(Boolean);
export function trainingReturn(value) {
  if (
    typeof value !== 'string' ||
    !value.startsWith('/') ||
    value.startsWith('//') ||
    /[\\\x00-\x1f]/.test(value)
  )
    return null;
  try {
    const url = new URL(value, 'https://acm.invalid');
    if (
      url.origin !== 'https://acm.invalid' ||
      !['/training-tasks.html', '/admin.html'].includes(url.pathname)
    )
      return null;
    if (url.pathname === '/admin.html' && url.searchParams.get('section') !== 'training')
      return null;
    const query = new URLSearchParams();
    if (url.pathname === '/admin.html') query.set('section', 'training');
    for (const key of ['task_id', 'recipient_id', 'page', 'step']) {
      const val = url.searchParams.get(key);
      if (val && (/^[1-9][0-9]{0,9}$/.test(val) || (key === 'task_id' && val === 'new')))
        query.set(key, val);
    }
    const tab = url.searchParams.get('tab');
    if (['edit', 'overview', 'progress', 'active', 'upcoming', 'history'].includes(tab))
      query.set('tab', tab);
    return url.pathname + (query.size ? '?' + query : '');
  } catch {
    return null;
  }
}
