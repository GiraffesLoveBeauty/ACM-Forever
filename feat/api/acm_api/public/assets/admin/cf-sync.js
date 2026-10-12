// Submission acknowledgments belong to the module cache, not to a mounted page.
export function submitSync(memory, payload) {
  if (memory.syncSubmission) return memory.syncSubmission;
  const operation = {id:null, error:null};
  memory.syncSubmission = operation;
  operation.ready = window.api('/admin/cf/sync', {
    method:'POST', body:JSON.stringify(payload), timeoutMs:30000
  }).then(data => {
    if (!data.job_id) throw Error('同步提交未返回任务编号，请重试。');
    operation.id = data.job_id;
    if (memory.syncSubmission === operation) memory.job = {id:operation.id, kind:'sync'};
  }).catch(error => {
    operation.error = error.name === 'AbortError' ? Error('同步提交确认超时，请刷新概况后重试。') : error;
  });
  return operation;
}

export function releaseSync(memory, operation) {
  if (memory.syncSubmission !== operation) return;
  memory.syncSubmission = null;
  if (memory.job?.id === operation.id) memory.job = null;
}
