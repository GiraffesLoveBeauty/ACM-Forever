import assert from 'node:assert/strict';
import { test } from 'node:test';
import { JSDOM } from 'jsdom';
import {
  createProfileDraft,
  changeDraft,
  draftKey,
  profileDraftStore,
  forkProfileDraft,
  clearSavedDraft,
  rebaseSavedDraft,
} from '../src/lib/member-profile-drafts.js';
import {
  profilePayload,
  validateProfile,
  saveProfileBatch as savePreparedProfileBatch,
  prepareProfileBatch,
  matchesSubmission,
} from '../src/lib/member-profiles.js';
const saveProfileBatch = (records, options) =>
  savePreparedProfileBatch(prepareProfileBatch(records), options);
const scope = 'a'.repeat(64),
  otherScope = 'b'.repeat(64);
const member = (qq = '20000001') => ({
  qq_id: qq,
  account_epoch: 1,
  account_state: 'active',
  profile_revision: 'c'.repeat(64),
  binding_versions: { codeforces: 1, atcoder: 2, luogu: 3, nowcoder: 4, cjlu: 5 },
  name: '合成昵称',
  real_name: '',
  school: '学校甲',
  status: '现役',
  cf_handle: 'OldCF',
  atcoder_handle: 'OldAC',
  luogu_id: '60001',
  nowcoder_id: '70001',
  password: 'must-not-persist',
  recent_ac: [{ source: 'never store' }],
});
const draft = (qq) => {
  const record = createProfileDraft(scope, member(qq));
  changeDraft(record, 'school', '新学校');
  return record;
};
function fixture() {
  const dom = new JSDOM('', { url: 'https://acm.test' });
  return {
    storage: dom.window.localStorage,
    store: profileDraftStore(scope, () => dom.window.localStorage),
  };
}
function callbacks(extra = {}) {
  return { status() {}, success() {}, conflict() {}, ...extra };
}

test('drafts persist immediately and return-to-original removes only the changed field', () => {
  const { store } = fixture(),
    record = draft();
  assert.equal(store.save(record).ok, true);
  assert.equal(store.list().records[0].record.changes.school, '新学校');
  changeDraft(record, 'school', '学校甲');
  assert.equal(Object.keys(record.changes).length, 0);
  assert.equal(store.save(record).ok, true);
});
test('only minimal profile fields are stored, never credentials, stats or arbitrary extras', () => {
  const { store, storage } = fixture(),
    record = draft();
  record.password = 'secret';
  record.csrf_token = 'secret';
  record.base.cookie = 'secret';
  store.save(record);
  const json = storage.getItem(draftKey(record));
  for (const word of ['password', 'csrf', 'cookie', 'recent_ac', 'source'])
    assert.equal(json.includes(word), word === 'source');
  assert.equal(store.list().records[0].record.base.name, '合成昵称');
});
test('different owners, member generations and tabs have isolated edit copies', () => {
  const { store, storage } = fixture(),
    first = draft(),
    second = draft();
  store.save(first);
  store.save(second);
  assert.equal(store.list().records.length, 2);
  const next = draft();
  next.account_epoch = 3;
  next.base.account_epoch = 3;
  store.save(next);
  assert.equal(store.list().records.length, 3);
  const other = profileDraftStore(otherScope, () => storage);
  assert.equal(other.list().records.length, 0);
  other.clear();
  assert.equal(store.list().records.length, 3);
});
test('restore forks a copy instead of overwriting another tab, and keeps unconfirmed identity input', () => {
  const { store } = fixture(),
    old = draft();
  old.drawer = { creating: true, text: '还没确认' };
  store.save(old);
  const copy = forkProfileDraft(old, 'session-another');
  store.save(copy);
  changeDraft(copy, 'real_name', '新姓名');
  store.save(copy);
  assert.notEqual(draftKey(old), draftKey(copy));
  assert.equal(
    store.list().records.find((item) => item.key === draftKey(old)).record.changes.real_name,
    undefined,
  );
  assert.equal(copy.drawer.text, '还没确认');
  assert.equal(copy.changes.status, undefined);
});
test('successful response only removes its exact local revision and source copy', () => {
  const { store } = fixture(),
    record = draft();
  store.save(record);
  const submitted = structuredClone(record);
  changeDraft(record, 'name', '后来输入');
  store.save(record);
  assert.equal(clearSavedDraft(store, record, submitted), false);
  assert.equal(store.list().records.length, 1);
  assert.equal(clearSavedDraft(store, record, structuredClone(record)), true);
  assert.equal(store.list().records.length, 0);
});
test('a stored newer version also survives an old success callback', () => {
  const { store } = fixture(),
    record = draft();
  store.save(record);
  const newer = structuredClone(record);
  changeDraft(newer, 'name', '另一个更新');
  store.save(newer);
  assert.equal(clearSavedDraft(store, record, record), false);
  assert.equal(store.list().records[0].record.changes.name, '另一个更新');
});
test('malformed, unsupported and unavailable storage show recovery errors without deleting records', () => {
  const { store, storage } = fixture(),
    record = draft();
  storage.setItem(draftKey(record), '{bad');
  assert.equal(store.list().errors.length, 1);
  assert.equal(storage.length, 1);
  storage.setItem(draftKey(record), JSON.stringify({ ...record, version: 9 }));
  assert.equal(store.list().errors.length, 1);
  const broken = profileDraftStore(scope, () => {
    throw Error('denied');
  });
  assert.equal(broken.list().errors.length, 1);
  assert.equal(broken.save(record).ok, false);
});
test('quota failure retains in-memory changes and is never reported as saved', () => {
  const record = draft(),
    store = profileDraftStore(scope, () => ({
      setItem() {
        throw Error('QuotaExceeded');
      },
    }));
  assert.equal(store.save(record).ok, false);
  assert.equal(record.changes.school, '新学校');
});
test('only OJ changes carry cleanup intent and omitted campus OJ is never sent', () => {
  const record = draft();
  let body = profilePayload(record);
  assert.equal(body.confirm_bindings, false);
  assert.equal('cjlu_username' in body, false);
  assert.equal('name' in body, false);
  changeDraft(record, 'cf_handle', 'FreshCF');
  body = profilePayload(record);
  assert.equal(body.confirm_bindings, true);
  assert.equal(body.expected_bindings.cf_handle, 'OldCF');
  assert.equal(body.binding_versions.codeforces, 1);
});
test('validation catches field errors while preserving invalid inputs', () => {
  const record = draft();
  changeDraft(record, 'name', ' ');
  changeDraft(record, 'cf_handle', 'https://invalid');
  changeDraft(record, 'status', 'x'.repeat(65));
  assert.deepEqual(Object.keys(validateProfile(record)).sort(), ['cf_handle', 'name', 'status']);
  assert.equal(record.changes.cf_handle, 'https://invalid');
});
test('save scheduler bounds concurrency, skips unchanged rows, and accepts 202 results', async () => {
  const records = Array.from({ length: 8 }, (_, i) => draft(String(20000001 + i))),
    empty = createProfileDraft(scope, member('20000099'));
  let live = 0,
    peak = 0,
    count = 0;
  const totals = await saveProfileBatch(
    [...records, empty],
    callbacks({
      request: async (path, { body }) => {
        live++;
        peak = Math.max(peak, live);
        await new Promise((resolve) => setTimeout(resolve, 5));
        live--;
        count++;
        return { member: { ...member(path.split('/').at(-1)), ...body } };
      },
    }),
  );
  assert.equal(count, 8);
  assert.equal(peak, 3);
  assert.equal(totals.saved, 8);
});
test('partial failure only clears successful members and leaves errors attached to the row', async () => {
  const records = [draft('20000001'), draft('20000002')],
    saved = [],
    failed = [];
  const totals = await saveProfileBatch(
    records,
    callbacks({
      request: async (path) => {
        if (path.endsWith('2'))
          throw Object.assign(Error('invalid'), {
            status: 400,
            details: { field_errors: { school: '过长' } },
          });
        return { member: member() };
      },
      success: (r) => saved.push(r.qq_id),
      status: (r, state, message, errors) => {
        if (state === 'failed') failed.push([r.qq_id, errors]);
      },
    }),
  );
  assert.deepEqual(saved, ['20000001']);
  assert.deepEqual(failed, [['20000002', { school: '过长' }]]);
  assert.equal(totals.failed, 1);
});
test('timeout reconciles with a fresh snapshot and never repeats the PATCH', async () => {
  const record = draft();
  let writes = 0,
    reads = 0,
    saved = 0;
  await saveProfileBatch(
    [record],
    callbacks({
      request: async (path, options) => {
        if (options) {
          writes++;
          throw Object.assign(Error('timeout'), { code: 'request_timeout' });
        }
        reads++;
        return { ...member(), school: '新学校' };
      },
      success: () => saved++,
    }),
  );
  assert.deepEqual([writes, reads, saved], [1, 1, 1]);
});
test('uncertain writes with different server values require comparison, never automatic replay', async () => {
  let conflicts = 0,
    writes = 0;
  await saveProfileBatch(
    [draft()],
    callbacks({
      request: async (path, options) => {
        if (options) {
          writes++;
          throw Error('network');
        }
        return member();
      },
      conflict: () => conflicts++,
    }),
  );
  assert.equal(conflicts, 1);
  assert.equal(writes, 1);
});
test('auth revocation stops queued saves and changed generations block old drafts', async () => {
  let writes = 0;
  const states = [];
  const result = await saveProfileBatch(
    [draft(), draft('20000002')],
    callbacks({
      limit: 1,
      request: async () => {
        writes++;
        throw Object.assign(Error('revoked'), { status: 403 });
      },
    }),
  );
  assert.equal(writes, 1);
  assert.equal(result.authorizationLost, true);
  await saveProfileBatch(
    [draft()],
    callbacks({
      request: async () => {
        throw Object.assign(Error('generation changed'), { status: 409, code: 'ACCOUNT_CHANGED' });
      },
      status: (_r, state) => states.push(state),
    }),
  );
  assert.ok(states.includes('blocked'));
  assert.equal(
    matchesSubmission(draft(), { ...member(), account_epoch: 3, school: '新学校' }),
    false,
  );
});
test('late responses after leaving or switching owners do not clear any draft', async () => {
  let active = true,
    saved = 0;
  await saveProfileBatch(
    [draft()],
    callbacks({
      active: () => active,
      request: async () => {
        active = false;
        return { member: member() };
      },
      success: () => saved++,
    }),
  );
  assert.equal(saved, 0);
});

test('successful snapshot rebases later edits including a return to the original value', () => {
  const { store } = fixture(),
    record = draft();
  const submitted = prepareProfileBatch([record])[0].record;
  changeDraft(record, 'school', record.base.school);
  changeDraft(record, 'name', '后续昵称');
  record.drawer = { creating: true, text: '未确认身份' };
  const current = { ...member(), school: '新学校', profile_revision: 'd'.repeat(64) };
  rebaseSavedDraft(record, submitted, current);
  assert.deepEqual(record.changes, { name: '后续昵称', school: '学校甲' });
  assert.equal(record.base.school, '新学校');
  assert.equal(record.base.profile_revision, 'd'.repeat(64));
  assert.equal(record.drawer.text, '未确认身份');
  assert.equal(store.save(record).ok, true);
  assert.equal(profilePayload(record).profile_revision, current.profile_revision);
});

test('prepared payload and binding confirmation do not change with the queued draft', async () => {
  const record = draft();
  changeDraft(record, 'cf_handle', 'ConfirmedCF');
  const submissions = prepareProfileBatch([record]);
  changeDraft(record, 'cf_handle', 'LaterCF');
  record.base.profile_revision = 'e'.repeat(64);
  const payloads = [];
  await savePreparedProfileBatch(
    submissions,
    callbacks({
      request: async (_path, options) => {
        payloads.push(options.body);
        return { member: member() };
      },
    }),
  );
  assert.equal(payloads[0].cf_handle, 'ConfirmedCF');
  assert.equal(payloads[0].profile_revision, 'c'.repeat(64));
  assert.equal(payloads[0].confirm_bindings, true);
  assert.equal(payloads[0].expected_bindings.cf_handle, 'OldCF');
});
