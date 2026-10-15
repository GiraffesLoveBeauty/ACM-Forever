import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { api, useRequests } from './api.js';
import { adminSessionVersion, problemMemory } from './admin.js';

const active = (task) => task && ['queued', 'running'].includes(task.status);

export function useProblemCollection(published) {
  const request = useRequests();
  const database = ref(null),
    databaseMessage = ref('正在检查数据库…'),
    initializing = ref(false);
  const task = ref(null),
    message = ref('正在检查采集任务…'),
    stateKnown = ref(false);
  const submitting = ref(false),
    cancelling = ref(false);
  const locked = computed(
    () => !stateKnown.value || submitting.value || Boolean(active(task.value)),
  );
  let disposed = false,
    timer = null,
    revision = 0,
    lastPublished = '';
  const sessionVersion = adminSessionVersion();
  const current = () => !disposed && sessionVersion === adminSessionVersion();

  function clearPoll() {
    clearTimeout(timer);
    timer = null;
  }
  function poll(delay) {
    clearPoll();
    if (current()) timer = setTimeout(checkTask, delay);
  }
  async function checkDatabase() {
    try {
      const data = await request('/admin/database');
      database.value = data;
      databaseMessage.value = data.initialized
        ? '数据库已初始化。'
        : '缺少表结构，请先初始化数据库。';
    } catch (error) {
      if (error.name !== 'AbortError' && current())
        databaseMessage.value = '无法检查数据库：' + error.message;
    }
  }
  async function initialize() {
    if (initializing.value) return;
    initializing.value = true;
    databaseMessage.value = '正在初始化数据库…';
    try {
      database.value = await request('/admin/database/init', { method: 'POST', body: {} });
      databaseMessage.value = database.value.message || '数据库初始化完成，已有数据已保留。';
      await published();
    } catch (error) {
      if (error.name !== 'AbortError' && current())
        databaseMessage.value = '初始化失败：' + error.message;
    } finally {
      if (current()) initializing.value = false;
    }
  }
  async function checkTask() {
    clearPoll();
    if (!current()) return;
    const reading = ++revision;
    try {
      const tasks = await request('/tasks', {}, 'problem-collection-tasks');
      if (!current() || reading !== revision) return;
      const id = problemMemory.taskId;
      const saved = id ? tasks.find((row) => row.id === id) : null;
      // A new task from another admin may have started since the previous one finished.
      const next = tasks.find((row) => row.kind === '题目采集' && active(row)) || saved;
      stateKnown.value = true;
      if (!next) {
        if (id) {
          task.value = null;
          message.value =
            '任务记录已不可用，服务可能已重启。已入库题目会保留，可重新拉取未完成的题目。';
        } else if (!task.value) message.value = '';
        problemMemory.taskId = null;
        return;
      }
      task.value = next;
      problemMemory.taskId = active(next) ? next.id : null;
      message.value = '';
      const result = next.result || {};
      const publication = `${next.id}:${result.metadata_count || 0}:${result.completed_batches || 0}:${next.status}`;
      if (
        publication !== lastPublished &&
        (result.metadata_count || result.success_count || !active(next))
      ) {
        lastPublished = publication;
        await Promise.all([checkDatabase(), published()]);
      }
      if (current() && reading === revision && active(next)) poll(3000);
    } catch (error) {
      if (error.name === 'AbortError' || !current() || reading !== revision) return;
      stateKnown.value = false;
      message.value = '无法读取采集任务：' + error.message + '。正在重试，也可点击“刷新采集状态”。';
      poll(6000);
    }
  }
  async function finishSubmission(record) {
    submitting.value = true;
    await record.promise;
    if (!current()) return;
    if (problemMemory.submission === record) problemMemory.submission = null;
    submitting.value = false;
    // Always reconcile with /tasks after a failed or interrupted acknowledgement.
    await checkTask();
    if (record.error && current()) {
      message.value = active(task.value)
        ? '提交确认失败：' + record.error.message + '。已恢复后台采集任务进度。'
        : '提交失败：' + record.error.message;
    }
  }
  async function submit(payload) {
    if (locked.value || problemMemory.submission?.pending) return;
    clearPoll();
    task.value = null;
    message.value = '正在提交拉取任务…';
    const record = { pending: true, error: null, promise: null };
    problemMemory.submission = record;
    // POST acknowledgement survives navigation; it never starts another task automatically.
    record.promise = api('/admin/problems/sync', {
      method: 'POST',
      body: payload,
      timeoutMs: 30000,
    })
      .then((response) => {
        if (!response.task?.id) throw Error('接口未返回任务 ID，请在同步任务中确认。');
        if (sessionVersion === adminSessionVersion() && problemMemory.submission === record)
          problemMemory.taskId = response.task.id;
      })
      .catch((error) => {
        record.error = error;
      })
      .finally(() => {
        record.pending = false;
      });
    await finishSubmission(record);
  }
  async function cancel() {
    if (!active(task.value) || cancelling.value) return;
    cancelling.value = true;
    try {
      await request(`/tasks/${encodeURIComponent(task.value.id)}/cancel`, { method: 'POST' });
      await checkTask();
    } catch (error) {
      if (error.name !== 'AbortError' && current()) message.value = '取消失败：' + error.message;
    } finally {
      if (current()) cancelling.value = false;
    }
  }
  onMounted(() => {
    checkDatabase();
    const record = problemMemory.submission;
    if (record) finishSubmission(record);
    else checkTask();
  });
  onBeforeUnmount(() => {
    disposed = true;
    revision++;
    clearPoll();
  });
  return {
    database,
    databaseMessage,
    initializing,
    initialize,
    task,
    message,
    locked,
    submitting,
    submit,
    cancelling,
    cancel,
    checkTask,
  };
}
