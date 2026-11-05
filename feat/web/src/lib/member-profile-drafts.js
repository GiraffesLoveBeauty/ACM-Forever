import { profileFields, ojFields, normalized } from './member-profiles.js';
const prefix = 'acm-member-profile:';
export const draftVersion = 1;
export const editSessionId = () =>
  globalThis.crypto?.randomUUID?.() ||
  Date.now().toString(36) + '-' + Math.random().toString(36).slice(2);
export function profileBase(member) {
  return {
    qq_id: member.qq_id,
    account_epoch: member.account_epoch,
    account_state: member.account_state,
    profile_revision: member.profile_revision,
    binding_versions: { ...member.binding_versions },
    ...Object.fromEntries(Object.keys(profileFields).map((key) => [key, member[key] || ''])),
  };
}
export function createProfileDraft(scope, member, session = editSessionId()) {
  return {
    version: 1,
    scope,
    qq_id: member.qq_id,
    account_epoch: member.account_epoch,
    session,
    base: profileBase(member),
    changes: {},
    revision: 0,
    updated_at: Date.now(),
    drawer: null,
    sources: [],
  };
}
export function draftKey(record) {
  return `${prefix}v1:${record.scope}:${record.qq_id}:${record.account_epoch}:${record.session}`;
}
export function changeDraft(record, field, value) {
  if (!Object.hasOwn(profileFields, field)) throw Error('不允许的资料字段');
  if (normalized(value) === normalized(record.base[field])) delete record.changes[field];
  else record.changes[field] = String(value ?? '');
  record.revision++;
  record.updated_at = Date.now();
}
function valid(record, scope, key) {
  return (
    record?.version === 1 &&
    record.scope === scope &&
    /^[a-f0-9]{64}$/.test(scope) &&
    /^\d{4,12}$/.test(record.qq_id) &&
    Number.isInteger(record.account_epoch) &&
    record.account_epoch > 0 &&
    typeof record.session === 'string' &&
    /^[a-zA-Z0-9-]{5,100}$/.test(record.session) &&
    Number.isInteger(record.revision) &&
    record.revision >= 0 &&
    Number.isFinite(record.updated_at) &&
    record.base?.qq_id === record.qq_id &&
    record.base.account_epoch === record.account_epoch &&
    /^[a-f0-9]{64}$/.test(record.base.profile_revision) &&
    record.base.account_state === 'active' &&
    Object.keys(profileFields).every((field) => typeof record.base[field] === 'string') &&
    record.base.binding_versions &&
    ['codeforces', 'atcoder', 'luogu', 'nowcoder', 'cjlu'].every(
      (platform) =>
        Number.isInteger(record.base.binding_versions[platform]) &&
        record.base.binding_versions[platform] >= 0,
    ) &&
    Array.isArray(record.sources || []) &&
    (record.sources || []).every(
      (source) =>
        typeof source.key === 'string' &&
        source.key.startsWith(`${prefix}v1:${scope}:${record.qq_id}:${record.account_epoch}:`) &&
        Number.isInteger(source.revision),
    ) &&
    typeof record.changes === 'object' &&
    record.changes !== null &&
    Object.entries(record.changes).every(
      ([field, value]) => Object.hasOwn(profileFields, field) && typeof value === 'string',
    ) &&
    (!record.drawer ||
      (typeof record.drawer.text === 'string' && typeof record.drawer.creating === 'boolean')) &&
    draftKey(record) === key
  );
}
// Store only the minimal edit schema, never request/authentication payloads.
function clean(record) {
  return {
    version: 1,
    scope: record.scope,
    qq_id: record.qq_id,
    account_epoch: record.account_epoch,
    session: record.session,
    base: profileBase(record.base),
    changes: { ...record.changes },
    revision: record.revision,
    updated_at: record.updated_at,
    drawer: record.drawer
      ? { creating: Boolean(record.drawer.creating), text: String(record.drawer.text || '') }
      : null,
    sources: (record.sources || []).map((source) => ({
      key: source.key,
      revision: source.revision,
    })),
  };
}
export function profileDraftStore(scope, getStorage = () => window.localStorage) {
  const owns = (key) => key.startsWith(prefix) && key.split(':')[2] === scope;
  return {
    list() {
      const records = [],
        errors = [];
      try {
        const storage = getStorage();
        for (let i = 0; i < storage.length; i++) {
          const key = storage.key(i);
          if (!owns(key)) continue;
          try {
            const record = JSON.parse(storage.getItem(key));
            if (!valid(record, scope, key)) throw Error('草稿格式损坏或版本不支持');
            records.push({ key, record: clean(record) });
          } catch (error) {
            errors.push({ key, message: error.message });
          }
        }
      } catch {
        errors.push({ message: '无法读取浏览器草稿，请检查浏览器存储权限。' });
      }
      return { records, errors };
    },
    save(record) {
      try {
        const value = clean(record),
          key = draftKey(value);
        if (!valid(value, scope, key)) throw Error('草稿格式不正确');
        getStorage().setItem(key, JSON.stringify(value));
        return { ok: true };
      } catch {
        return { ok: false, message: '本地草稿保存失败，请勿关闭页面；请检查存储权限或空间。' };
      }
    },
    remove(key, revision) {
      if (!owns(key)) return { ok: false };
      try {
        const storage = getStorage(),
          raw = storage.getItem(key);
        if (raw === null) return { ok: true, removed: true };
        const current = JSON.parse(raw);
        if (current.revision !== revision || !valid(current, scope, key))
          return { ok: true, removed: false };
        storage.removeItem(key);
        return { ok: true, removed: true };
      } catch {
        return { ok: false, message: '无法清理本地草稿，已保留记录。' };
      }
    },
    clear() {
      try {
        const storage = getStorage(),
          keys = [];
        for (let i = 0; i < storage.length; i++)
          if (owns(storage.key(i))) keys.push(storage.key(i));
        keys.forEach((key) => storage.removeItem(key));
        return { ok: true };
      } catch {
        return { ok: false, message: '无法清空本账号的资料草稿。' };
      }
    },
  };
}
export function forkProfileDraft(record, session) {
  const copy = clean(record);
  copy.sources = [...(record.sources || []), { key: draftKey(record), revision: record.revision }];
  copy.session = session;
  copy.revision++;
  copy.updated_at = Date.now();
  return copy;
}
export function clearSavedDraft(store, current, submitted) {
  if (current.revision !== submitted.revision || draftKey(current) !== draftKey(submitted))
    return false;
  const result = store.remove(draftKey(submitted), submitted.revision);
  if (!result.ok || !result.removed) return false;
  for (const source of submitted.sources || []) store.remove(source.key, source.revision);
  return true;
}

// A successful snapshot becomes the new base; only input made after it stays dirty.
export function rebaseSavedDraft(record, submitted, member) {
  const changes = {};
  const value = (draft, key) =>
    Object.hasOwn(draft.changes, key) ? draft.changes[key] : draft.base[key];
  const comparable = (key, raw) =>
    ojFields[key] ? normalized(raw).toLowerCase() : normalized(raw);
  for (const key of Object.keys(profileFields)) {
    const latest = value(record, key);
    if (
      comparable(key, latest) !== comparable(key, value(submitted, key)) &&
      comparable(key, latest) !== comparable(key, member[key])
    )
      changes[key] = String(latest ?? '');
  }
  record.base = profileBase(member);
  record.changes = changes;
  record.revision++;
  record.updated_at = Date.now();
}
