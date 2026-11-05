export const profileFields = {
  real_name: '真实姓名',
  name: '昵称',
  school: '学校',
  status: '身份',
  cf_handle: 'Codeforces',
  atcoder_handle: 'AtCoder',
  luogu_id: '洛谷 UID',
  nowcoder_id: '牛客 UID',
};
export const ojFields = {
  cf_handle: 'codeforces',
  atcoder_handle: 'atcoder',
  luogu_id: 'luogu',
  nowcoder_id: 'nowcoder',
};
export const normalized = (value) => String(value ?? '').trim();
export function bindingChanges(record) {
  return Object.entries(record.changes).filter(
    ([key, value]) =>
      ojFields[key] &&
      normalized(value).toLowerCase() !== normalized(record.base[key]).toLowerCase(),
  );
}
export function validateProfile(record) {
  const errors = {};
  for (const [key, raw] of Object.entries(record.changes)) {
    const value = normalized(raw),
      limit = key === 'status' || ojFields[key] ? 64 : 128;
    if (value.length > limit) errors[key] = `最多 ${limit} 字符。`;
    else if (key === 'name' && !value) errors[key] = '昵称不能为空。';
    else if (
      ojFields[key] &&
      value &&
      normalized(record.base[key]).toLowerCase() !== value.toLowerCase() &&
      !(
        key === 'luogu_id' || key === 'nowcoder_id'
          ? /^[1-9][0-9]{0,19}$/
          : /^[A-Za-z0-9_.-]{1,64}$/
      ).test(value)
    )
      errors[key] = '请输入账号标识，不要填写网址。';
  }
  return errors;
}
export function profilePayload(record) {
  return {
    ...Object.fromEntries(
      Object.entries(record.changes).map(([key, value]) => [key, normalized(value)]),
    ),
    expected_account_epoch: record.account_epoch,
    profile_revision: record.base.profile_revision,
    confirm_bindings: bindingChanges(record).length > 0,
    expected_bindings: Object.fromEntries(
      Object.keys(ojFields).map((key) => [key, normalized(record.base[key])]),
    ),
    binding_versions: { ...record.base.binding_versions },
  };
}
export function sameGeneration(record, current) {
  return (
    current?.account_state === 'active' &&
    current.qq_id === record.qq_id &&
    current.account_epoch === record.account_epoch
  );
}
export function matchesSubmission(record, current) {
  return (
    sameGeneration(record, current) &&
    Object.entries(record.changes).every(([key, value]) => {
      const left = normalized(value),
        right = normalized(current[key]);
      return ojFields[key] ? left.toLowerCase() === right.toLowerCase() : left === right;
    })
  );
}
// Each request is an independent transaction. Never replay an uncertain binding write.
export async function saveProfileBatch(
  records,
  { request, active = () => true, status, success, conflict, limit = 3 },
) {
  let index = 0,
    authorized = true;
  const totals = { saved: 0, failed: 0, conflicts: 0 };
  async function worker() {
    while (authorized && active() && index < records.length) {
      const source = records[index++],
        record = JSON.parse(JSON.stringify(source));
      if (!Object.keys(record.changes).length) continue;
      const errors = validateProfile(record);
      if (Object.keys(errors).length) {
        totals.failed++;
        status(source, 'failed', '请检查标出的字段。', errors);
        continue;
      }
      status(source, 'saving');
      try {
        const result = await request('/admin/members/' + encodeURIComponent(record.qq_id), {
          method: 'PATCH',
          body: profilePayload(record),
        });
        if (!active()) return;
        totals.saved++;
        success(source, record, result);
      } catch (error) {
        if (!active()) return;
        if ([401, 403, 428].includes(error.status)) authorized = false;
        if (error.code === 'profile_conflict' || error.code === 'binding_changed') {
          totals.conflicts++;
          conflict(source, error.details?.current, error.message);
          continue;
        }
        if (['ACCOUNT_CLOSED', 'ACCOUNT_CHANGED', 'MEMBER_NOT_FOUND'].includes(error.code)) {
          totals.failed++;
          status(source, 'blocked', error.message);
          continue;
        }
        if (!error.status && error.name !== 'AbortError') {
          try {
            const current = await request('/admin/members/' + encodeURIComponent(record.qq_id));
            if (!active()) return;
            if (matchesSubmission(record, current)) {
              totals.saved++;
              success(source, record, { member: current, message: '已对账确认资料保存成功。' });
              continue;
            }
            totals.conflicts++;
            conflict(source, current, '保存结果与当前资料不一致，请核对后再保存。');
            continue;
          } catch (checkError) {
            if (!active()) return;
            if ([401, 403, 428].includes(checkError.status)) authorized = false;
            totals.failed++;
            status(source, 'uncertain', '保存结果待确认，草稿已保留。请先核对服务端状态。');
            continue;
          }
        }
        totals.failed++;
        status(
          source,
          'failed',
          error.message || '保存失败，输入已保留。',
          error.details?.field_errors || {},
        );
      }
    }
  }
  await Promise.all(Array.from({ length: Math.min(limit, records.length) }, worker));
  return { ...totals, authorizationLost: !authorized };
}
