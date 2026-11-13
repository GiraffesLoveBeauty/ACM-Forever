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

    async def test_admin_real_name_search_paging_and_member_privacy(self):
        await self.sql("UPDATE users SET real_name='  合成实名甲  ' WHERE qq_id='22345678'")
        await self.seed('32345678')
        task = await self.create()
        await self.publish(task)
        base = f'/api/admin/training-tasks/{task["id"]}/progress'
        members = (await self.info(task['id']))['items']
        self.assertEqual([m['real_name'] for m in members], ['合成实名甲', None])
        self.assertEqual(members[0]['name'], '合成成员78')
        for search in ['合成实名甲', '22345678']:
            response = await self.client.get(base, query_string={'search': search})
            data = await response.get_json()
            self.assertEqual((data['total'], data['items'][0]['qq_id']), (1, '22345678'))
            self.assertEqual(data['summary']['recipient_count'], 2)
        nicknames = await (await self.client.get(base, query_string={'search': '合成成员'})).get_json()
        self.assertEqual(nicknames['total'], 2)
        page = await (await self.client.get(base, query_string={'page_size': 1, 'page': 2})).get_json()
        self.assertEqual((page['total'], len(page['items']), page['items'][0]['real_name']), (2, 1, None))
        detail = await (await self.client.get(base + '/' + str(members[0]['id']))).get_json()
        self.assertEqual(detail['recipient']['real_name'], '合成实名甲')
        await self.sql("UPDATE users SET real_name='合成改名甲' WHERE qq_id='22345678'")
        renamed = await (await self.client.get(base, query_string={'search': '合成改名甲'})).get_json()
        self.assertEqual(renamed['items'][0]['real_name'], '合成改名甲')
        member = self.app.test_client()
        login = await member.post('/api/auth/login', json={'qq_id': '22345678', 'password': 'Test-Password-123!'})
        self.assertEqual(login.status_code, 200)
        for url in ['/api/me/training-tasks', f'/api/me/training-tasks/{task["id"]}']:
            response = await member.get(url)
            self.assertEqual(response.status_code, 200)
            data = await response.get_json()
            self.assertNotIn('real_name', json.dumps(data, ensure_ascii=False))
            self.assertNotIn('合成改名甲', json.dumps(data, ensure_ascii=False))
        self.assertEqual((await member.get(base)).status_code, 403)
        self.assertEqual((await member.get(base + '/' + str(members[0]['id']))).status_code, 403)

    async def test_real_name_isolation_for_changed_closed_and_reused_accounts(self):
        await self.sql("UPDATE users SET real_name='合成旧姓名' WHERE qq_id='22345678'")
        task = await self.create()
        await self.publish(task)
        recipient = (await self.info(task['id']))['items'][0]
        self.assertEqual(recipient['real_name'], '合成旧姓名')
        await self.sql("UPDATE users SET account_epoch=account_epoch+1,real_name='新代际姓名' WHERE qq_id='22345678'")
        changed = (await self.info(task['id']))['items'][0]
        self.assertEqual(changed['account_status'], 'changed')
        self.assertIsNone(changed['real_name'])
        await self.sql("UPDATE users SET account_state='closed',account_epoch=account_epoch+1 WHERE qq_id='22345678'")
        reopened = await self.client.post('/api/admin/web-accounts', headers=self.headers, json={
            'qq_id': '22345678', 'name': '重新开户昵称', 'initial_password': 'New-Password-123!', 'role': 'member',
        })
        self.assertEqual(reopened.status_code, 201, await reopened.get_json())
        self.assertTrue((await reopened.get_json())['new_generation'])
        await self.sql("UPDATE users SET real_name='重新开户姓名' WHERE qq_id='22345678'")
        base = f'/api/admin/training-tasks/{task["id"]}/progress'
        closed = (await self.info(task['id']))['items'][0]
        self.assertEqual((closed['account_status'], closed['name'], closed['qq_id']), ('closed', '已注销成员', None))
        self.assertIsNone(closed['real_name'])
        detail = await (await self.client.get(base + '/' + str(recipient['id']))).get_json()
        self.assertIsNone(detail['recipient']['real_name'])
        for name in ['新代际姓名', '重新开户姓名']:
            response = await self.client.get(base, query_string={'search': name})
            self.assertEqual((await response.get_json())['total'], 0)

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


    async def test_closed_evidence_is_anonymous_and_new_generation_cannot_inherit(self):
        await self.bind()
        await self.ac(self.now-1, external='22345678:801')
        task = await self.create()
        await self.publish(task)
        await self.sql("UPDATE users SET account_state='closed',account_epoch=account_epoch+1 WHERE qq_id='22345678'")
        record = (await self.sql('SELECT * FROM training_task_progress'))[0]
        self.assertIsNone(record['binding_key'])
        proof = json.loads(record['on_time_json'])
        self.assertNotIn('external_submission_id', proof)
        self.assertEqual(proof['accepted_at'],self.now-1)
        info = await self.info(task['id'])
        self.assertEqual((info['summary']['recipient_count'],info['summary']['on_time_count'],info['summary']['abnormal_count']),(1,1,1))
        await self.sql("INSERT INTO account_registrations(qq_id,closed_epoch,new_epoch,created_at) VALUES('22345678',2,3,?)",(self.now,))
        await self.sql("UPDATE users SET account_state='active',account_epoch=3,name='新一代成员' WHERE qq_id='22345678'")
        await self.client.post('/api/auth/login',json={'qq_id':'22345678','password':'Test-Password-123!'})
        mine = await (await self.client.get('/api/me/training-tasks?tab=all')).get_json()
        self.assertEqual(mine['total'],0)
        self.assertEqual((await self.client.get(f'/api/me/training-tasks/{task["id"]}')).status_code,404)

    async def test_first_binding_read_enables_refresh_without_reconciling_or_adopting_rebinds(self):
        task = await self.create()
        await self.publish(task)
        recipient = (await self.info(task['id']))['items'][0]
        url = f'/api/admin/training-tasks/{task["id"]}/progress/{recipient["id"]}'
        self.assertEqual((await (await self.client.get(url)).get_json())['problems'][0]['verification'], 'unbound')
        stored = await self.sql('SELECT * FROM training_task_progress')
        await self.sql("UPDATE users SET cf_handle='FirstWhileWaiting' WHERE qq_id='22345678'")
        first = await (await self.client.get(url)).get_json()
        self.assertEqual(first['problems'][0]['verification'], 'coverage_missing')
        self.assertTrue(first['recipient']['pending'])
        self.assertEqual(await self.sql('SELECT * FROM training_task_progress'), stored)
        response = await self.client.post('/api/auth/login', json={'qq_id':'22345678','password':'Test-Password-123!'})
        headers = {'X-CSRF-Token':(await response.get_json())['csrf_token']}
        personal = f'/api/me/training-tasks/{task["id"]}'
        self.assertEqual((await (await self.client.get(personal)).get_json())['problems'][0]['verification'], 'coverage_missing')
        submitter = AsyncMock(return_value={'id':'first-bound-refresh'})
        self.app.config['PLUGIN_CONFIG'].update(_account_sync_submitter=submitter, _task_provider=lambda: [])
        self.assertEqual((await self.client.post(personal+'/refresh', headers=headers, json={})).status_code, 202)
        submitter.assert_awaited_once_with('22345678', ['codeforces'], 0, expected_epoch=1)
        # An initially empty snapshot may not silently adopt a second binding generation.
        await self.sql("UPDATE users SET cf_handle='SecondWhileWaiting' WHERE qq_id='22345678'")
        changed = await (await self.client.get(personal)).get_json()
        self.assertEqual(changed['problems'][0]['verification'], 'binding_changed')
        self.assertTrue(changed['recipient']['pending'])
        self.assertEqual(await self.sql('SELECT * FROM training_task_progress'), stored)

    async def test_elapsed_coverage_is_derived_on_every_read_without_mutating_evidence(self):
        await self.bind()
        await self.sql("UPDATE user_platform_sync_state SET coverage_through_at=? WHERE user_qq_id='22345678'", (self.now,))
        await self.ac(self.now-1)
        task = await self.create(title='Coverage stops before deadline')
        await self.publish(task)
        covered = await self.create(title='Coverage includes the whole interval', due_at=self.now)
        await self.publish(covered)
        recipient = (await self.info(task['id']))['items'][0]
        self.assertEqual((await self.info(task['id']))['summary']['pending_count'], 0)
        progress_before = await self.sql('SELECT * FROM training_task_progress ORDER BY recipient_id,problem_id')
        sync_before = await self.sql('SELECT * FROM user_platform_sync_state')
        network = AsyncMock(side_effect=AssertionError('GET must not request Codeforces'))
        submitter = AsyncMock()
        self.app.config['PLUGIN_CONFIG']['_account_sync_submitter'] = submitter
        with patch('time.time', return_value=self.now+4000), patch.object(cf_history, 'cf_request', network):
            listing = await (await self.client.get('/api/admin/training-tasks')).get_json()
            summaries = {item['id']:item['summary'] for item in listing['items']}
            self.assertEqual(summaries[task['id']]['pending_count'], 1)
            self.assertEqual(summaries[covered['id']]['pending_count'], 0)
            detail = await (await self.client.get(f'/api/admin/training-tasks/{task["id"]}')).get_json()
            self.assertEqual(detail['summary']['pending_count'], 1)
            info = await self.info(task['id'])
            self.assertEqual((info['summary']['pending_count'], info['summary']['on_time_count']), (1, 1))
            individual = await (await self.client.get(f'/api/admin/training-tasks/{task["id"]}/progress/{recipient["id"]}')).get_json()
            self.assertEqual(individual['problems'][0]['verification'], 'pending_sync')
            self.assertEqual(individual['problems'][0]['evidence']['accepted_at'], self.now-1)
        await self.client.post('/api/auth/login', json={'qq_id':'22345678','password':'Test-Password-123!'})
        with patch('time.time', return_value=self.now+4000), patch.object(cf_history, 'cf_request', network):
            listing = await (await self.client.get('/api/me/training-tasks?tab=history')).get_json()
            recipients = {item['id']:item['recipient'] for item in listing['items']}
            self.assertTrue(recipients[task['id']]['pending'])
            self.assertFalse(recipients[covered['id']]['pending'])
            personal = await (await self.client.get(f'/api/me/training-tasks/{task["id"]}')).get_json()
            self.assertTrue(personal['recipient']['pending'])
            self.assertEqual((personal['problems'][0]['verification'], personal['problems'][0]['status']), ('pending_sync', 'on_time'))
        network.assert_not_awaited()
        submitter.assert_not_awaited()
        self.assertEqual(await self.sql('SELECT * FROM training_task_progress ORDER BY recipient_id,problem_id'), progress_before)
        self.assertEqual(await self.sql('SELECT * FROM user_platform_sync_state'), sync_before)

    async def test_live_sync_failures_and_missing_coverage_update_summary_and_details_together(self):
        await self.bind()
        task = await self.create()
        await self.publish(task)
        recipient = (await self.info(task['id']))['items'][0]
        stored = await self.sql('SELECT * FROM training_task_progress')
        for status, full, expected in [('failed', self.now, 'sync_failed'), ('paused', self.now, 'sync_paused'), ('success', 0, 'coverage_missing')]:
            with self.subTest(status=status, full=full):
                await self.sql("UPDATE user_platform_sync_state SET last_status=?,full_history_at=? WHERE user_qq_id='22345678'", (status,full))
                info = await self.info(task['id'])
                self.assertEqual(info['summary']['pending_count'], 1)
                detail = await (await self.client.get(f'/api/admin/training-tasks/{task["id"]}/progress/{recipient["id"]}')).get_json()
                self.assertEqual(detail['problems'][0]['verification'], expected)
                self.assertTrue(detail['recipient']['pending'])
        self.assertEqual(await self.sql('SELECT * FROM training_task_progress'), stored)
