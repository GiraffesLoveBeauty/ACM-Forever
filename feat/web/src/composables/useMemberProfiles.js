import { ref, reactive, computed, watch, onBeforeUnmount, onMounted } from 'vue';
import { useRoute, onBeforeRouteUpdate } from 'vue-router';
import { api, auth, useRequests, notify } from '../lib/api.js';
import { useParams, useLeaveGuard, adminSessionVersion } from '../lib/admin.js';
import {
  profileFields,
  normalized,
  bindingChanges,
  validateProfile,
  sameGeneration,
  matchesSubmission,
  saveProfileBatch,
  prepareProfileBatch,
} from '../lib/member-profiles.js';
import {
  profileBase,
  createProfileDraft,
  changeDraft,
  draftKey,
  editSessionId,
  profileDraftStore,
  forkProfileDraft,
  clearSavedDraft,
  rebaseSavedDraft,
} from '../lib/member-profile-drafts.js';
export function useMemberProfiles() {
  const route = useRoute(),
    update = useParams(),
    request = useRequests();
  const filters = reactive({ search: '', school: '', status: '' }),
    data = ref(),
    options = ref({ schools: [], statuses: [] }),
    loading = ref(false),
    loadError = ref('');
  const editing = ref(false),
    saving = ref(false),
    message = ref(''),
    storageError = ref(''),
    storageWarnings = ref([]),
    candidates = ref([]),
    pendingOpen = ref(false),
    drawerQQ = ref(null),
    conflictQQ = ref(null);
  const drafts = reactive({}),
    session = editSessionId(),
    ownerSession = adminSessionVersion();
  let store = null,
    alive = true,
    loadVersion = 0,
    recovering = false;
  const active = () =>
    alive && ownerSession === adminSessionVersion() && ['admin', 'root'].includes(auth.role);
  const records = computed(() => Object.values(drafts));
  const dirty = computed(() =>
    records.value.filter((record) => Object.keys(record.changes).length),
  );
  const pendingStatuses = computed(() => [
    ...new Set(records.value.map((record) => normalized(record.changes.status)).filter(Boolean)),
  ]);
  const drawerRecord = computed(() => drafts[drawerQQ.value]);
  const conflictRecord = computed(() => drafts[conflictQQ.value]);
  const localSummary = computed(
    () =>
      storageError.value ||
      (storageWarnings.value.length
        ? '部分历史草稿无法读取，请核对存储提示。'
        : '本地草稿已保存，仅当前浏览器可恢复。'),
  );
  function refreshCandidates() {
    if (!store) return;
    const found = store.list(),
      used = new Map(
        records.value.flatMap((record) => [
          [draftKey(record), record.revision],
          ...(record.sources || []).map((source) => [source.key, source.revision]),
        ]),
      );
    candidates.value = found.records.filter((item) => used.get(item.key) !== item.record.revision);
    storageWarnings.value = found.errors;
  }
  function persist(record) {
    if (!active() || !store) return false;
    if (record.state === 'saved' && !Object.keys(record.changes).length && !record.drawer?.creating)
      return true;
    let result = store.save(record);
    if (result.ok && !Object.keys(record.changes).length && !record.drawer?.creating) {
      result = store.remove(draftKey(record), record.revision);
      if (result.ok)
        for (const source of record.sources || []) store.remove(source.key, source.revision);
    }
    record.persisted = result.ok;
    if (!result.ok) storageError.value = result.message;
    else if (records.value.every((item) => item.persisted !== false)) storageError.value = '';
    return result.ok;
  }
  function flush() {
    for (const record of records.value) persist(record);
  }
  function leave() {
    flush();
    return (
      !storageError.value || confirm('本地草稿保存失败。继续离开可能丢失尚未保存的输入，是否离开？')
    );
  }
  useLeaveGuard(leave);
  onBeforeRouteUpdate((to) => {
    if ((to.query.section || 'accounts') === 'members') return leave();
  });
  function beforeUnload(event) {
    flush();
    if (storageError.value) {
      event.preventDefault();
      event.returnValue = '';
    }
  }
  function storageChanged(event) {
    if (event.key?.startsWith('acm-member-profile:')) {
      refreshCandidates();
      if (candidates.value.length) message.value = '其他编辑副本有草稿更新；各副本不会自动覆盖。';
    }
  }
  onMounted(() => {
    window.addEventListener('pagehide', flush);
    window.addEventListener('beforeunload', beforeUnload);
    window.addEventListener('storage', storageChanged);
  });
  onBeforeUnmount(() => {
    flush();
    alive = false;
    window.removeEventListener('pagehide', flush);
    window.removeEventListener('beforeunload', beforeUnload);
    window.removeEventListener('storage', storageChanged);
  });
  function ensure(row) {
    const existing = drafts[row.qq_id];
    if (existing) return existing;
    if (!store) throw Error('请等待管理员草稿作用域确认。');
    return (drafts[row.qq_id] = {
      ...createProfileDraft(options.value.draft_scope, row, session),
      state: 'pending',
      fieldErrors: {},
      persisted: true,
    });
  }
  function value(row, key) {
    return editing.value && drafts[row.qq_id] && Object.hasOwn(drafts[row.qq_id].changes, key)
      ? drafts[row.qq_id].changes[key]
      : row[key] || '';
  }
  function editRecord(record, key, text) {
    changeDraft(record, key, text);
    record.fieldErrors = {};
    record.error = '';
    if (!record.current && !['saving', 'queued', 'blocked', 'uncertain'].includes(record.state))
      record.state = 'pending';
    persist(record);
  }
  function input(row, key, text) {
    const record = ensure(row);
    if (record.state === 'saving') return;
    editRecord(record, key, text);
  }
  function dirtyField(row, key) {
    return editing.value && Object.hasOwn(drafts[row.qq_id]?.changes || {}, key);
  }
  function permission(row) {
    return row.role ? `${row.role}${row.is_active ? '' : ' · 已停用'}` : '未开通';
  }
  function stateLabel(record) {
    return (
      {
        pending: '待保存',
        saving: '保存中',
        queued: '排队中',
        saved: '成功',
        failed: '保存失败',
        conflict: '需要核对',
        blocked: '不可应用',
        uncertain: '结果待确认',
      }[record?.state] || ''
    );
  }
  async function load() {
    const version = ++loadVersion;
    loadError.value = '';
    Object.assign(filters, {
      search: String(route.query.search || ''),
      school: String(route.query.school || ''),
      status: String(route.query.status || ''),
    });
    if (route.query.qq_id) {
      loading.value = false;
      return;
    }
    loading.value = true;
    data.value = null;
    try {
      const [all, result] = await Promise.all([
        request('/admin/members/options', {}, 'member-options'),
        request(
          '/admin/members?' +
            new URLSearchParams({ ...filters, page: route.query.page || 1, page_size: 20 }),
          {},
          'member-list',
        ),
      ]);
      if (!active() || version !== loadVersion) return;
      if (!store || options.value.draft_scope !== all.draft_scope) {
        for (const key of Object.keys(drafts)) delete drafts[key];
        store = profileDraftStore(all.draft_scope);
      }
      options.value = all;
      data.value = result;
      refreshCandidates();
      if (Number(route.query.page || 1) !== result.page) await update({ page: result.page }, true);
    } catch (error) {
      if (active() && version === loadVersion && error.name !== 'AbortError')
        loadError.value = error.message;
    } finally {
      if (version === loadVersion) loading.value = false;
    }
  }
  function applyFilters(reset = false) {
    flush();
    update(
      reset
        ? { search: null, school: null, status: null, page: 1 }
        : {
            search: filters.search.trim(),
            school: filters.school,
            status: filters.status,
            page: 1,
          },
    );
  }
  function openDrawer(row) {
    ensure(row);
    drawerQQ.value = row.qq_id;
  }
  function rememberDrawer(info) {
    const record = drawerRecord.value;
    record.drawer = info;
    record.revision++;
    record.updated_at = Date.now();
    persist(record);
  }
  function selectStatus(status) {
    const record = drawerRecord.value;
    record.drawer = null;
    editRecord(record, 'status', status);
    drawerQQ.value = null;
  }
  function cancelDrawer() {
    const record = drawerRecord.value;
    record.drawer = null;
    record.revision++;
    persist(record);
    drawerQQ.value = null;
  }
  async function recover() {
    if (recovering) return;
    recovering = true;
    editing.value = true;
    pendingOpen.value = true;
    try {
      for (const item of [...candidates.value]) {
        if (!active()) break;
        if (drafts[item.record.qq_id]) {
          message.value = '同一成员存在多个副本，请先处理当前副本，再恢复其他副本。';
          continue;
        }
        const record = {
          ...forkProfileDraft(item.record, session),
          state: 'pending',
          fieldErrors: {},
          persisted: true,
        };
        drafts[record.qq_id] = record;
        try {
          const current = await request('/admin/members/' + encodeURIComponent(record.qq_id));
          if (!active()) break;
          if (!sameGeneration(record, current)) {
            record.state = 'blocked';
            record.error = '该 QQ 已更换账号代际，旧草稿不可应用。';
          } else if (record.base.profile_revision !== current.profile_revision) {
            record.current = current;
            record.state = 'conflict';
            record.error = '服务端资料已变化，请逐字段核对。';
          }
        } catch (error) {
          if (!active()) break;
          record.state = ['ACCOUNT_CLOSED', 'ACCOUNT_CHANGED', 'MEMBER_NOT_FOUND'].includes(
            error.code,
          )
            ? 'blocked'
            : 'uncertain';
          record.error = error.message;
        }
        persist(record);
        if (record.drawer?.creating && !drawerQQ.value) drawerQQ.value = record.qq_id;
      }
      refreshCandidates();
    } finally {
      recovering = false;
    }
  }
  function discard(record) {
    if (
      record.state === 'saving' ||
      !confirm(`放弃 QQ ${record.qq_id} 的当前资料草稿？其他副本不受影响。`)
    )
      return;
    const result = store.remove(draftKey(record), record.revision);
    if (!result.ok) {
      storageError.value = result.message;
      return;
    }
    for (const source of record.sources || []) store.remove(source.key, source.revision);
    delete drafts[record.qq_id];
    if (drawerQQ.value === record.qq_id) drawerQQ.value = null;
    if (conflictQQ.value === record.qq_id) conflictQQ.value = null;
    refreshCandidates();
  }
  function discardAll() {
    if (
      saving.value ||
      !confirm(
        '清空本账号在此浏览器中的全部成员资料草稿？包括其他编辑副本，服务端已保存资料保持原样。',
      )
    )
      return;
    const result = store.clear();
    if (!result.ok) {
      storageError.value = result.message;
      return;
    }
    for (const key of Object.keys(drafts)) delete drafts[key];
    candidates.value = [];
    storageError.value = '';
    storageWarnings.value = [];
    drawerQQ.value = null;
    conflictQQ.value = null;
  }
  function onStatus(record, state, error = '', fieldErrors = {}) {
    record.state = state;
    record.error = error;
    record.fieldErrors = fieldErrors;
  }
  function onConflict(record, current, error) {
    if (current && !sameGeneration(record, current)) {
      onStatus(record, 'blocked', '账号代际已变化，旧草稿不可应用。');
      return;
    }
    record.current = current;
    onStatus(record, 'conflict', error || '请核对服务端变化。');
    pendingOpen.value = true;
  }
  function onSuccess(record, submitted, result) {
    if (draftKey(record) !== draftKey(submitted)) return;
    if (record.revision === submitted.revision && !clearSavedDraft(store, record, submitted)) {
      record.state = 'saved';
      record.error = '服务端已保存，但本地草稿未清理，请核对后清理。';
      storageError.value = record.error;
      return;
    }
    const sources = record.sources;
    rebaseSavedDraft(record, submitted, result.member);
    record.sources = [];
    record.state = 'pending';
    record.current = null;
    record.error = (result.warnings || []).join(' ');
    record.fieldErrors = {};
    if (persist(record)) {
      for (const source of submitted.sources || []) store.remove(source.key, source.revision);
    } else record.sources = sources;
    record.state = Object.keys(record.changes).length ? 'pending' : 'saved';
    if (result.warnings?.length) notify(result.warnings.join(' '));
  }
  async function saveAll(single = null) {
    if (saving.value || !active()) return;
    const targets = single ? [single] : dirty.value;
    const rows = targets.filter(
      (record) => !['saving', 'blocked', 'conflict', 'uncertain'].includes(record.state),
    );
    const skipped = targets.length - rows.length;
    const eligible = [];
    for (const submission of prepareProfileBatch(rows)) {
      const errors = validateProfile(submission.record);
      if (Object.keys(errors).length)
        onStatus(submission.source, 'failed', '请检查标出的字段。', errors);
      else eligible.push(submission);
    }
    const invalid = rows.length - eligible.length;
    const deferred = invalid + skipped;
    if (!eligible.length) {
      pendingOpen.value = true;
      message.value = '没有可直接保存的修改，请检查字段错误、冲突或待确认结果。';
      return;
    }
    const bindings = eligible.flatMap(({ record }) =>
      bindingChanges(record).map(
        ([key, text]) =>
          `QQ ${record.qq_id} · ${profileFields[key]}：${record.base[key] || '未绑定'} → ${normalized(text) || '解绑'}`,
      ),
    );
    if (
      bindings.length &&
      !confirm(
        `本次保存 ${eligible.length} 人${deferred ? `，另 ${deferred} 人需先处理错误、冲突或待确认结果，暂不提交` : ''}。确认以下 OJ 绑定变更？\n受影响平台 AC、提交证据与同步状态将清理，进行中的挑战结束；收藏和历史资料保留。\n` +
          bindings.join('\n'),
      )
    )
      return;
    if (
      !bindings.length &&
      deferred &&
      !confirm(
        `本次保存 ${eligible.length} 位合法成员，另 ${deferred} 人需先处理错误、冲突或待确认结果，暂不提交。继续？`,
      )
    )
      return;
    saving.value = true;
    flush();
    for (const { source } of eligible) onStatus(source, 'queued');
    try {
      const totals = await saveProfileBatch(eligible, {
        request: api,
        active,
        valid: (record, submitted) =>
          drafts[record.qq_id] === record && draftKey(record) === draftKey(submitted),
        status: onStatus,
        success: onSuccess,
        conflict: onConflict,
        limit: 3,
      });
      if (!active()) return;
      message.value = `成功 ${totals.saved} 人，失败 ${totals.failed + invalid} 人，冲突 ${totals.conflicts} 人。${skipped ? ` 另 ${skipped} 人未提交，草稿保留。` : ''}${totals.cancelled ? ` 已取消排队 ${totals.cancelled} 人。` : ''}${totals.authorizationLost ? '权限已变化，已停止后续保存。' : ''}`;
      pendingOpen.value = true;
      refreshCandidates();
      if (totals.saved) {
        await load();
        if (filters.school || filters.status || filters.search)
          message.value += ' 列表已按当前条件刷新，不再符合筛选的成员会移出列表。';
      }
    } finally {
      for (const { source } of eligible) if (source.state === 'queued') onStatus(source, 'pending');
      saving.value = false;
    }
  }
  async function check(record) {
    try {
      const current = await request('/admin/members/' + encodeURIComponent(record.qq_id));
      if (!active()) return;
      if (!sameGeneration(record, current)) {
        onStatus(record, 'blocked', '账号已更换代际，旧草稿不可应用。');
        return;
      }
      if (matchesSubmission(record, current)) {
        onSuccess(record, JSON.parse(JSON.stringify(record)), { member: current });
        await load();
        return;
      }
      onConflict(record, current, '请核对最新资料。');
      conflictQQ.value = record.qq_id;
    } catch (error) {
      if (active())
        onStatus(
          record,
          ['ACCOUNT_CLOSED', 'ACCOUNT_CHANGED', 'MEMBER_NOT_FOUND'].includes(error.code)
            ? 'blocked'
            : 'uncertain',
          error.message,
        );
    }
  }
  function merge(values) {
    const record = conflictRecord.value,
      current = record.current;
    record.base = profileBase(current);
    record.changes = {};
    record.current = null;
    record.state = 'pending';
    record.error = '';
    for (const [field, text] of Object.entries(values)) changeDraft(record, field, text);
    record.revision++;
    persist(record);
    conflictQQ.value = null;
  }
  function leaveEditing() {
    flush();
    editing.value = false;
    drawerQQ.value = null;
    conflictQQ.value = null;
  }
  watch(() => route.query, load, { immediate: true });
  watch(
    () => [auth.qq_id, auth.account_epoch, auth.role, auth.authenticated],
    () => {
      if (!active()) {
        alive = false;
        for (const key of Object.keys(drafts)) delete drafts[key];
        candidates.value = [];
        store = null;
        drawerQQ.value = null;
        conflictQQ.value = null;
      }
    },
  );

  const ready = computed(() => Boolean(options.value.draft_scope));
  return {
    ready,
    route,
    update,
    filters,
    data,
    options,
    loading,
    loadError,
    editing,
    saving,
    message,
    storageError,
    storageWarnings,
    candidates,
    pendingOpen,
    drawerQQ,
    conflictQQ,
    records,
    drafts,
    dirty,
    pendingStatuses,
    drawerRecord,
    conflictRecord,
    localSummary,
    load,
    applyFilters,
    openDrawer,
    rememberDrawer,
    selectStatus,
    cancelDrawer,
    recover,
    discard,
    discardAll,
    stateLabel,
    permission,
    dirtyField,
    value,
    input,
    saveAll,
    check,
    merge,
    leaveEditing,
    flush,
  };
}
