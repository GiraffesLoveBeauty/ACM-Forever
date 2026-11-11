import json
import time
import unittest
from unittest.mock import AsyncMock, patch

import test_training_tasks as task_contract
from feat.api.acm_api.database import connect_db
from feat.api.acm_api import training_task_progress as progress
from feat.api.acm_api import cf_history
from feat.api.service_runtime import SyncEngine


class TrainingProgressTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = task_contract.TrainingTaskTests.asyncSetUp
    asyncTearDown = task_contract.TrainingTaskTests.asyncTearDown
    sql = task_contract.TrainingTaskTests.sql
    seed = task_contract.TrainingTaskTests.seed
    draft = task_contract.TrainingTaskTests.draft
    create = task_contract.TrainingTaskTests.create
    preview = task_contract.TrainingTaskTests.preview
    publish = task_contract.TrainingTaskTests.publish

    async def bind(self, handle='FirstHandle'):
        await self.sql("UPDATE users SET cf_handle=? WHERE qq_id='22345678'", (handle,))
        row = (await self.sql("SELECT cf_binding_version FROM users WHERE qq_id='22345678'"))[0]
        key = handle.casefold() + ':' + str(row['cf_binding_version'])
        await self.sql("INSERT INTO user_platform_sync_state(user_qq_id,platform,binding_key,full_history_at,coverage_through_at,last_status,last_success_at) VALUES('22345678','codeforces',?,?,?,'success',?) ON CONFLICT(user_qq_id,platform) DO UPDATE SET binding_key=excluded.binding_key,full_history_at=excluded.full_history_at,coverage_through_at=excluded.coverage_through_at,last_status='success',last_success_at=excluded.last_success_at", (key, self.now, self.now+2000, self.now))

    async def ac(self, stamp, pid='cf_1A', external='one'):
        await self.sql("INSERT INTO submission_attempts(owner_qq_id,platform,external_submission_id,problem_id,verdict,submitted_at,created_at) VALUES('22345678','codeforces',?,?, 'OK',?,?)", (external, pid, stamp, self.now))

    async def reconcile(self, task_id):
        db = await connect_db(self.db_path)
        try:
            await db.execute('BEGIN IMMEDIATE')
            await progress.reconcile(db, task_id=task_id)
            await db.commit()
        finally:
            await db.close()

    async def info(self, task_id):
        response = await self.client.get(f'/api/admin/training-tasks/{task_id}/progress')
        self.assertEqual(response.status_code, 200, await response.get_json())
        return await response.get_json()

    async def test_repeated_ac_inclusive_boundaries_and_late_backfill(self):
        await self.bind()
        await self.ac(self.now-300, external='old')
        task = await self.create(starts_at=self.now-100, due_at=self.now-10)
        await self.publish(task)
        self.assertEqual((await self.info(task['id']))['summary']['on_time_count'], 0)
        # Fetched after the deadline; actual accepted_at is exactly the deadline.
        await self.ac(self.now-10, external='deadline')
        await self.ac(self.now-100, external='start')
        await self.reconcile(task['id'])
        self.assertEqual((await self.info(task['id']))['summary']['on_time_count'], 1)
        await self.reconcile(task['id'])
        self.assertEqual((await self.info(task['id']))['summary']['completed_problem_count'], 1)

    async def test_all_problems_late_extension_and_history_rule(self):
        await self.bind()
        await self.ac(self.now-50)
        task = await self.create(due_at=self.now-60, starts_at=self.now-100, problems=[{'problem_id':'1A'}, {'problem_id':'2A'}])
        published = await (await self.publish(task)).get_json()
        self.assertEqual((await self.info(task['id']))['summary']['late_count'], 0)
        await self.ac(self.now-30, pid='cf_2A', external='two')
        await self.reconcile(task['id'])
        self.assertEqual((await self.info(task['id']))['summary']['late_count'], 1)
        response = await self.client.post(f'/api/admin/training-tasks/{task["id"]}/extend-deadline', headers=self.headers, json={'version':2,'due_at':self.now+100,'reason':'补充训练时间'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual((await self.info(task['id']))['summary']['on_time_count'], 1)
        historic = await self.create(starts_at=self.now-10, rule='historical_ac')
        await self.publish(historic)
        self.assertEqual((await self.info(historic['id']))['summary']['on_time_count'], 1)
        future = await self.create(starts_at=self.now+100, due_at=self.now+300, rule='historical_ac')
        await self.publish(future)
        self.assertEqual((await self.info(future['id']))['summary']['completed_problem_count'], 0)

    async def test_binding_fence_retains_confirmed_evidence_but_never_inherits_new_handle(self):
        await self.bind()
        await self.ac(self.now-1)
        confirmed = await self.create()
        await self.publish(confirmed)
        pending = await self.create(problems=[{'problem_id':'2A'}])
        await self.publish(pending)
        await self.bind('SomeoneElse')
        await self.ac(self.now-1, pid='cf_2A', external='other')
        for task in (confirmed, pending):
            await self.reconcile(task['id'])
        self.assertEqual((await self.info(confirmed['id']))['summary']['on_time_count'], 1)
        self.assertEqual((await self.info(pending['id']))['summary']['on_time_count'], 0)
        self.assertEqual((await self.info(pending['id']))['summary']['pending_count'], 1)

    async def test_initially_unbound_can_bind_and_sync_pipeline_updates_progress(self):
        task = await self.create()
        await self.publish(task)
        self.assertEqual((await self.info(task['id']))['summary']['pending_count'], 1)
        await self.sql("UPDATE users SET cf_handle='FirstHandle' WHERE qq_id='22345678'")
        engine = SyncEngine(self.db_path, {})
        await engine.start()
        page = [{'id': 801, 'creationTimeSeconds':self.now-1,'verdict':'OK','problem':{'contestId':1,'index':'A','name':'合成题','tags':[]}}]
        try:
            with patch.object(cf_history, 'cf_request', AsyncMock(return_value=page)):
                result = await engine.sync_single_platform_for_days('22345678','codeforces',0)
            self.assertGreaterEqual(result, 0)
        finally:
            await engine.close()
        self.assertEqual((await self.info(task['id']))['summary']['on_time_count'], 1)

    async def test_failed_coverage_and_paused_sync_remain_explicit(self):
        await self.bind()
        task = await self.create()
        await self.publish(task)
        for status, expected in [('failed','sync_failed'),('paused','sync_paused'),('success','coverage_missing')]:
            await self.sql("UPDATE user_platform_sync_state SET last_status=?,full_history_at=0 WHERE user_qq_id='22345678'", (status,))
            await self.reconcile(task['id'])
            info = await self.info(task['id'])
            self.assertEqual(info['summary']['on_time_count'], 0)
            recipient_id = info['items'][0]['id']
            result = await (await self.client.get(f'/api/admin/training-tasks/{task["id"]}/progress/{recipient_id}')).get_json()
            self.assertEqual(result['problems'][0]['verification'], expected)

    async def test_member_scope_csrf_async_refresh_dedup_and_limit(self):
        await self.bind()
        task = await self.create()
        await self.publish(task)
        other = await self.create(statuses=['管理组'])
        await self.publish(other)
        response = await self.client.post('/api/auth/login', json={'qq_id':'22345678','password':'Test-Password-123!'})
        headers = {'X-CSRF-Token':(await response.get_json())['csrf_token']}
        self.assertEqual((await self.client.get(f'/api/me/training-tasks/{other["id"]}')).status_code,404)
        mine = await (await self.client.get('/api/me/training-tasks?tab=all&qq_id=12345678')).get_json()
        self.assertEqual([t['id'] for t in mine['items']], [task['id']])
        self.assertEqual((await self.client.post(f'/api/me/training-tasks/{task["id"]}/refresh', json={})).status_code,403)
        config = self.app.config['PLUGIN_CONFIG']
        config['_account_sync_submitter'] = AsyncMock(return_value={'id':'local-sync'})
        config['_task_provider'] = lambda: []
        url = f'/api/me/training-tasks/{task["id"]}/refresh'
        self.assertEqual((await self.client.post(url, headers=headers,json={})).status_code,202)
        self.assertEqual((await self.client.post(url, headers=headers,json={})).status_code,429)
        config['_task_provider'] = lambda: [{'id':'local-sync','qq_id':'22345678','account_epoch':1,'platform':'codeforces','status':'running'}]
        self.assertEqual((await self.client.post(url, headers=headers,json={})).status_code,202)
        config['_account_sync_submitter'].assert_awaited_once()
        self.assertEqual((await self.client.post(url, headers=headers,json={'qq_id':'12345678'})).status_code,400)
        self.assertEqual((await self.client.get('/api/admin/training-tasks')).status_code,403)
        detail = await (await self.client.get(f'/api/me/training-tasks/{task["id"]}')).get_json()
        self.assertEqual(detail['refresh']['status'], 'running')
        self.assertNotIn('creator_qq_id', detail)
