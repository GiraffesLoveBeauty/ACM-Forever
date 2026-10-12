'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../acm_api/public/assets/admin/cf-sync.js'),'utf8');
const service=import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
function deferred(){let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no});return {promise,resolve,reject}}

test('pending sync acknowledgment survives page disposal and keeps the accepted job',async()=>{
  const {submitSync}=await service,reply=deferred(),memory={},page=new AbortController(),calls=[];
  global.window={api:(route,options)=>{calls.push({route,options});return reply.promise}};
  const payload={scope:{statuses:['active'],exclude_qq_ids:[]},expected_scope_fingerprint:'scope-1'};
  const operation=submitSync(memory,payload);
  page.abort();
  assert.equal(memory.syncSubmission,operation);
  assert.equal(calls[0].route,'/admin/cf/sync');
  assert.equal(calls[0].options.signal,undefined);
  assert.equal(calls[0].options.timeoutMs,30000);
  assert.deepEqual(JSON.parse(calls[0].options.body),payload);
  reply.resolve({job_id:'accepted-before-exit'});await operation.ready;
  assert.deepEqual(memory.job,{id:'accepted-before-exit',kind:'sync'});
  assert.equal(operation.error,null);
});

test('repeated returns reuse one submission, including a job completed before return',async()=>{
  const {submitSync,releaseSync}=await service,reply=deferred(),memory={};let calls=0;
  global.window={api:()=>{calls++;return reply.promise}};
  const operation=submitSync(memory,{scope:{statuses:['active']}});
  assert.equal(submitSync(memory,{}),operation);
  reply.resolve({job_id:'already-completed'});await operation.ready;
  assert.equal(submitSync(memory,{}),operation);
  assert.equal(calls,1);
  releaseSync(memory,operation);
  assert.equal(memory.syncSubmission,null);assert.equal(memory.job,null);
});

test('failed acknowledgment is retained without an unhandled rejection and can be retried',async()=>{
  const {submitSync,releaseSync}=await service,memory={},failure=Error('Sync refused');let calls=0;
  global.window={api:()=>{calls++;return calls===1?Promise.reject(failure):Promise.resolve({job_id:'retry'})}};
  const operation=submitSync(memory,{});await operation.ready;
  assert.equal(operation.error,failure);assert.equal(memory.job,undefined);
  assert.equal(submitSync(memory,{}),operation);
  releaseSync(memory,operation);
  const retry=submitSync(memory,{});await retry.ready;
  assert.equal(retry.id,'retry');assert.equal(calls,2);
});

test('timeout or malformed acknowledgment records a recoverable error',async()=>{
  const {submitSync}=await service;
  global.window={api:()=>Promise.reject(new DOMException('timeout','AbortError'))};
  const timedOut=submitSync({},{});await timedOut.ready;
  assert.match(timedOut.error.message,/确认超时/);
  global.window={api:()=>Promise.resolve({})};
  const malformed=submitSync({},{});await malformed.ready;
  assert.match(malformed.error.message,/任务编号/);assert.equal(malformed.id,null);
});

test('stale acknowledgment and release cannot overwrite a newer recovery record',async()=>{
  const {submitSync,releaseSync}=await service,reply=deferred(),memory={};
  global.window={api:()=>reply.promise};
  const previous=submitSync(memory,{}),current={id:'new-job'};
  memory.syncSubmission=current;memory.job={id:'new-job',kind:'sync'};
  reply.resolve({job_id:'old-job'});await previous.ready;releaseSync(memory,previous);
  assert.equal(memory.syncSubmission,current);
  assert.deepEqual(memory.job,{id:'new-job',kind:'sync'});
});
