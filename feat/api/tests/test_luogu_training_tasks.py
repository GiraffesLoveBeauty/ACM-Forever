"""Assigned Luogu tasks use guarded snapshots, never fake submission times."""
import asyncio
import json
import time
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import test_training_tasks as task_contract
from test_luogu_user_sync import page
from feat.api.acm_api import luogu_user_sync as luogu
from feat.api.acm_api import training_task_progress as progress
from feat.api.acm_api.database import connect_db
from feat.api.service_runtime import SyncEngine, WebTaskManager


class LuoguTrainingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self):
        if getattr(self, "extra_manager", None):
            await self.extra_manager.close()
            await self.extra_engine.close()
        await task_contract.TrainingTaskTests.asyncTearDown(self)

    sql = task_contract.TrainingTaskTests.sql
    seed = task_contract.TrainingTaskTests.seed
    draft = task_contract.TrainingTaskTests.draft
    create = task_contract.TrainingTaskTests.create
    preview = task_contract.TrainingTaskTests.preview
    publish = task_contract.TrainingTaskTests.publish

    async def asyncSetUp(self):
        await task_contract.TrainingTaskTests.asyncSetUp(self)
        await self.sql("UPDATE users SET luogu_id='1234' WHERE qq_id='22345678'")

    async def task(self, **changes):
        return await self.create(problems=[{"platform":"luogu","problem_id":"P1001"}],
                                 luogu_snapshot=True, **changes)

    async def snapshot(self, passed, at=None, *, uid="1234"):
        at = self.now if at is None else at
        db=await connect_db(self.db_path)
        try:
            user=(await (await db.execute("SELECT * FROM users WHERE qq_id='22345678'")).fetchone())
            with patch.object(luogu,"luogu_get",new=AsyncMock(return_value=page(passed,account=uid))), patch.object(luogu,"time",SimpleNamespace(time=lambda:at)):
                return await luogu.sync_public_practice(None,user,db,{})
        finally:
            await db.close()

    async def info(self, task_id):
        data=await (await self.client.get(f"/api/admin/training-tasks/{task_id}/progress")).get_json()
        member=data["items"][0]
        detail=await (await self.client.get(f"/api/admin/training-tasks/{task_id}/progress/{member['id']}")).get_json()
        return data,detail

    async def scheduler_for_members(self, count=1):
        qq_ids = [str(22345678 + i) for i in range(count)]
        db = await connect_db(self.db_path)
        try:
            for i, qq in enumerate(qq_ids[1:], 1):
                await db.execute("INSERT INTO users(qq_id,name,status,luogu_id) VALUES(?,?,'训练组',?)",
                                 (qq, "调度测试成员" + str(i), str(1234 + i)))
                await db.execute("INSERT INTO web_accounts(qq_id,password_hash,role,must_change_password,is_active,created_at,updated_at) SELECT ?,password_hash,'member',0,1,1,1 FROM web_accounts WHERE qq_id='12345678'", (qq,))
            await db.commit()
        finally:
            await db.close()
        task = await self.task(due_at=self.now + 3600)
        self.assertEqual((await self.publish(task)).status_code, 200)
        engine = SyncEngine(self.db_path, {})
        await engine.start()
        manager = WebTaskManager(engine)
        self.extra_engine, self.extra_manager = engine, manager
        manager.submit_account_sync = AsyncMock(return_value={"id": "scheduled-snapshot"})
        return manager, qq_ids

    async def test_publish_uses_history_without_opt_in_and_only_public_p_problems(self):
        options=await (await self.client.get('/api/admin/training-tasks/options')).get_json()
        capability=next(c for c in options['capabilities'] if c['platform']=='luogu')
        self.assertEqual((capability['historical_ac'],capability['period_ac'],capability['snapshot_ac']),(True,False,False))
        task=await self.create(problems=[{'platform':'luogu','problem_id':'luogu_p1001'}])
        self.assertEqual(task['problems'][0]['problem_id'],'P1001')
        blocked=await self.client.post(f"/api/admin/training-tasks/{task['id']}/audience-preview",headers=self.headers,json={'version':task['version']})
        self.assertEqual(blocked.status_code, 200)
        self.assertFalse(task['luogu_snapshot'])
        for pid in ['B1001','T1001','U1001']:
            blocked = await self.client.post('/api/admin/training-tasks', headers=self.headers,
                json=self.draft(problems=[{'platform':'luogu','problem_id':pid}],rule='historical_ac'))
            self.assertEqual(blocked.status_code, 400)
        history=await self.create(problems=[{'platform':'luogu','problem_id':'P1001'}],rule='historical_ac')
        self.assertEqual((await self.publish(history)).status_code,200)

    async def test_zero_new_sync_sets_baseline_and_one_snapshot_updates_multiple_tasks(self):
        task=await self.task()
        other=await self.task()
        await self.publish(task)
        await self.publish(other)
        self.assertEqual(await self.snapshot([],self.now-50),0)
        self.assertEqual(await self.snapshot(['P1001'],self.now-20),1)
        for item in [task,other]:
            overview,detail=await self.info(item['id'])
            self.assertEqual(overview['summary']['on_time_count'],1)
            proof=detail['problems'][0]['evidence']
            self.assertEqual((proof['accepted_at'],proof['observed_at'],proof['evidence_type']),(None,self.now-20,'historical_ac'))
        rows=await self.sql("SELECT submit_time FROM submissions WHERE platform='luogu'")
        self.assertEqual(rows,[{'submit_time':0}])
        self.assertEqual(await self.sql('SELECT * FROM submission_attempts'),[])
        before=await self.sql('SELECT * FROM training_task_progress ORDER BY recipient_id')
        submitter=AsyncMock()
        self.app.config['PLUGIN_CONFIG']['_account_sync_submitter']=submitter
        with patch.object(luogu,'luogu_get',new=AsyncMock()) as network:
            await self.info(task['id'])
        network.assert_not_awaited()
        submitter.assert_not_awaited()
        self.assertEqual(await self.sql('SELECT * FROM training_task_progress ORDER BY recipient_id'),before)

    async def test_deadline_unknown_and_late_are_separate_and_extension_reuses_evidence(self):
        task=await self.create(problems=[{'platform':'luogu','problem_id':'P1001'},{'platform':'luogu','problem_id':'P1002'}],luogu_snapshot=True,starts_at=self.now-100,due_at=self.now-10)
        await self.publish(task)
        await self.snapshot([],self.now-50)
        await self.snapshot(['P1001'],self.now-5)
        await self.snapshot(['P1001','P1002'],self.now)
        overview,detail=await self.info(task['id'])
        self.assertEqual([p['status'] for p in detail['problems']],['on_time','on_time'])
        self.assertEqual((overview['summary']['uncertain_problem_count'],overview['summary']['completed_problem_count']),(0,2))
        filtered=await (await self.client.get(f"/api/admin/training-tasks/{task['id']}/progress?status=timing_unknown")).get_json()
        self.assertEqual(filtered['total'],0)
        response=await self.client.post(f"/api/admin/training-tasks/{task['id']}/extend-deadline",headers=self.headers,json={'version':2,'due_at':self.now+100,'reason':'延长周期'})
        self.assertEqual(response.status_code,200)
        self.assertEqual((await self.info(task['id']))[0]['summary']['on_time_count'],1)

    async def test_first_positive_without_baseline_and_historical_mode(self):
        new=await self.task()
        historical=await self.task(rule='historical_ac')
        await self.publish(new)
        await self.publish(historical)
        await self.snapshot(['P1001'])
        self.assertEqual((await self.info(new['id']))[1]['problems'][0]['status'],'on_time')
        self.assertEqual((await self.info(historical['id']))[1]['problems'][0]['status'],'on_time')
        # A later empty but structurally valid snapshot never turns this into a new AC.
        await self.snapshot([],self.now+1)
        _,detail=await self.info(new['id'])
        self.assertEqual((detail['problems'][0]['status'],detail['problems'][0]['verification']),('on_time','snapshot_conflict'))

    async def test_cached_unknown_time_ac_is_not_backdated(self):
        await self.sql("INSERT INTO submissions(user_qq_id,platform,problem_id,submit_time) VALUES('22345678','luogu','luogu_P1001',0)")
        task=await self.task(due_at=self.now-10,starts_at=self.now-100)
        await self.publish(task)
        _,detail=await self.info(task['id'])
        proof=detail['problems'][0]['evidence']
        self.assertEqual((detail['problems'][0]['status'],proof['source'],proof['accepted_at']),('on_time','local_luogu_ac_set',None))

    async def test_history_needs_no_date_review_and_the_endpoint_stays_protected(self):
        task=await self.task()
        await self.publish(task)
        await self.snapshot(['P1001'])
        _,detail=await self.info(task['id'])
        recipient,problem=detail['recipient'],detail['problems'][0]
        self.assertFalse(problem['can_review'])
        self.assertFalse(problem['can_clear_review'])
        self.assertEqual(problem['status'], 'on_time')
        url=f"/api/admin/training-tasks/{task['id']}/progress/{recipient['id']}/review"
        payload={'problem_id':problem['id'],'version':problem['progress_version'],'task_version':2,'decision':'on_time','reason':'旧客户端审核请求'}
        self.assertEqual((await self.client.post(url,json=payload)).status_code,403)
        member=self.app.test_client()
        login=await member.post('/api/auth/login',json={'qq_id':'22345678','password':'Test-Password-123!'})
        token=(await login.get_json())['csrf_token']
        self.assertEqual((await member.post(url,headers={'X-CSRF-Token':token},json=payload)).status_code,403)
        stale=await self.client.post(url,headers=self.headers,json={**payload,'version':-1})
        self.assertEqual((stale.status_code,(await stale.get_json())['code']),(409,'evidence_conflict'))
        response=await self.client.post(url,headers=self.headers,json=payload)
        self.assertEqual((response.status_code,(await response.get_json())['code']),(400,'historical_ac_only'))
        self.assertEqual(await self.sql("SELECT * FROM training_task_audit WHERE action='progress_reviewed'"), [])

    async def test_rebinding_preserves_credit_and_requires_explicit_reset_for_pending_problem(self):
        task=await self.create(problems=[{'platform':'luogu','problem_id':'P1001'},{'platform':'luogu','problem_id':'P1002'}],luogu_snapshot=True)
        await self.publish(task)
        await self.snapshot([],self.now-50)
        await self.snapshot(['P1001'],self.now-20)
        await self.sql("UPDATE users SET luogu_id='5678' WHERE qq_id='22345678'")
        await self.snapshot(['P1001','P1002'],uid='5678')
        _,detail=await self.info(task['id'])
        self.assertEqual([p['status'] for p in detail['problems']],['on_time','pending'])
        pending=detail['problems'][1]
        self.assertTrue(pending['can_reset_binding'])
        url=f"/api/admin/training-tasks/{task['id']}/progress/{detail['recipient']['id']}/review"
        response=await self.client.post(url,headers=self.headers,json={'problem_id':pending['id'],'version':pending['progress_version'],'task_version':2,'decision':'reset_binding','reason':'管理员核对账号更正'})
        self.assertEqual(response.status_code,200,await response.get_json())
        self.assertEqual((await response.get_json())['problems'][1]['verification'],'baseline_missing')
        # An accepted problem on the corrected UID counts immediately as historical AC.
        await self.snapshot(['P1001','P1002'],self.now+1,uid='5678')
        _,detail=await self.info(task['id'])
        self.assertEqual([p['status'] for p in detail['problems']],['on_time','on_time'])

    async def test_sync_failure_rolls_back_ac_and_progress_together(self):
        task=await self.task()
        await self.publish(task)
        before=await self.sql('SELECT * FROM training_task_progress')
        with patch.object(progress,'record_luogu_snapshot',new=AsyncMock(side_effect=RuntimeError('synthetic write failure'))):
            with self.assertRaisesRegex(RuntimeError,'synthetic'):
                await self.snapshot(['P1001'])
        self.assertEqual(await self.sql("SELECT * FROM submissions WHERE platform='luogu'"),[])
        self.assertEqual(await self.sql('SELECT * FROM training_task_progress'),before)

    async def test_scheduler_targets_assigned_accounts_and_respects_snapshot_retry_and_binding(self):
        await self.seed('32345678',status='其他组')
        await self.sql("UPDATE users SET luogu_id='9999' WHERE qq_id='32345678'")
        task=await self.task(due_at=self.now+3600)
        await self.publish(task)
        engine=SyncEngine(self.db_path,{})
        await engine.start()
        manager=WebTaskManager(engine)
        self.extra_engine, self.extra_manager = engine, manager
        manager.submit_account_sync=AsyncMock(return_value={'id':'scheduled-snapshot'})
        await self.sql("UPDATE training_tasks SET luogu_snapshot=0 WHERE id=?", (task['id'],))
        self.assertEqual(await manager.schedule_training_snapshots(now=self.now),1)
        manager.submit_account_sync.assert_awaited_once_with('22345678',['luogu'],expected_epoch=1)
        self.assertEqual(await manager.schedule_training_snapshots(now=self.now+1),0)
        await self.snapshot([],self.now)
        self.assertEqual(await manager.schedule_training_snapshots(now=self.now+61),0)
        await self.sql("UPDATE users SET luogu_id='5678' WHERE qq_id='22345678'")
        self.assertEqual(await manager.schedule_training_snapshots(now=self.now+1000),0)

    async def test_refresh_derives_luogu_platform_and_identity_from_the_session(self):
        task=await self.task()
        await self.publish(task)
        login=await self.client.post('/api/auth/login',json={'qq_id':'22345678','password':'Test-Password-123!'})
        headers={'X-CSRF-Token':(await login.get_json())['csrf_token']}
        config=self.app.config['PLUGIN_CONFIG']
        config['_account_sync_submitter']=AsyncMock(return_value={'id':'luogu-refresh'})
        config['_task_provider']=lambda:[]
        url=f"/api/me/training-tasks/{task['id']}/refresh"
        self.assertEqual((await self.client.post(url,headers=headers,json={})).status_code,202)
        config['_account_sync_submitter'].assert_awaited_once_with('22345678',['luogu'],0,expected_epoch=1)
        self.assertEqual((await self.client.post(url,headers=headers,json={'qq_id':'12345678'})).status_code,400)


    async def test_binding_reset_keeps_authorization_versions_and_lifecycle_fences(self):
        task = await self.task()
        await self.publish(task)
        await self.sql("UPDATE users SET luogu_id='5678' WHERE qq_id='22345678'")
        _, detail = await self.info(task["id"])
        problem = detail["problems"][0]
        url = f"/api/admin/training-tasks/{task['id']}/progress/{detail['recipient']['id']}/review"
        payload = {"problem_id": problem["id"], "version": problem["progress_version"],
                   "task_version": 2, "decision": "reset_binding", "reason": "核对更正绑定"}
        denied = await self.client.post(url, json=payload)
        self.assertEqual(denied.status_code, 403)
        member = self.app.test_client()
        login = await member.post('/api/auth/login', json={'qq_id': '22345678', 'password': 'Test-Password-123!'})
        denied = await member.post(url, headers={'X-CSRF-Token': (await login.get_json())['csrf_token']}, json=payload)
        self.assertEqual(denied.status_code, 403)
        stale = await self.client.post(url, headers=self.headers, json={**payload, "version": payload["version"] + 1})
        self.assertEqual((stale.status_code, (await stale.get_json())["code"]), (409, "evidence_conflict"))
        stale = await self.client.post(url, headers=self.headers, json={**payload, "task_version": 1})
        self.assertEqual((stale.status_code, (await stale.get_json())["code"]), (409, "version_conflict"))
        await self.sql("UPDATE training_tasks SET state='cancelled' WHERE id=?", (task["id"],))
        cancelled = await self.client.post(url, headers=self.headers, json=payload)
        self.assertEqual((cancelled.status_code, (await cancelled.get_json())["code"]), (409, "immutable_task"))
        await self.sql("UPDATE training_tasks SET state='published' WHERE id=?", (task["id"],))
        await self.sql("UPDATE users SET account_epoch=account_epoch+1 WHERE qq_id='22345678'")
        changed = await self.client.post(url, headers=self.headers, json=payload)
        self.assertEqual((changed.status_code, (await changed.get_json())["code"]), (409, "account_changed"))
        _, detail = await self.info(task["id"])
        self.assertFalse(detail["problems"][0]["can_clear_review"])
        await self.sql("UPDATE users SET account_state='closed',account_epoch=account_epoch+1 WHERE qq_id='22345678'")
        closed = await self.client.post(url, headers=self.headers, json=payload)
        self.assertEqual((closed.status_code, (await closed.get_json())["code"]), (409, "account_changed"))

    async def test_scheduler_moves_past_twenty_failed_accounts_and_limits_dispatched_work(self):
        manager, qq_ids = await self.scheduler_for_members(21)
        self.assertEqual(await manager.schedule_training_snapshots(now=self.now), 20)
        self.assertEqual([call.args[0] for call in manager.submit_account_sync.await_args_list], qq_ids[:20])
        db = await connect_db(self.db_path)
        try:
            await db.executemany("INSERT OR REPLACE INTO user_platform_sync_state(user_qq_id,platform,last_status,last_attempt_at,consecutive_failures) VALUES(?,'luogu','failed',?,1)", [(qq, self.now) for qq in qq_ids[:20]])
            await db.commit()
        finally:
            await db.close()
        manager.submit_account_sync.reset_mock()
        self.assertEqual(await manager.schedule_training_snapshots(now=self.now + 30), 1)
        manager.submit_account_sync.assert_awaited_once_with(qq_ids[-1], ["luogu"], expected_epoch=1)
        # The final account succeeded; repeated failures on others must back off.
        snapshot = json.dumps({"last_checked_at": self.now + 30, "last_request_at": self.now + 30})
        await self.sql("UPDATE training_task_progress SET snapshot_json=? WHERE recipient_id IN (SELECT id FROM training_task_recipients WHERE qq_id=?)", (snapshot, qq_ids[-1]))
        manager.submit_account_sync.reset_mock()
        self.assertEqual(await manager.schedule_training_snapshots(now=self.now + 60), 20)
        await self.sql("UPDATE user_platform_sync_state SET last_attempt_at=?,consecutive_failures=2 WHERE platform='luogu' AND last_status='failed'", (self.now + 60,))
        self.assertEqual(await manager.schedule_training_snapshots(now=self.now + 120), 0)
        self.assertEqual(await manager.schedule_training_snapshots(now=self.now + 180), 20)

    async def test_scheduler_fills_batch_around_queued_running_and_locked_accounts(self):
        manager, qq_ids = await self.scheduler_for_members(21)
        for i, qq in enumerate(qq_ids[:10]):
            manager.tasks[qq] = {"qq_id": qq, "status": "queued" if i % 2 else "running"}
        locks = []
        try:
            for qq in qq_ids[10:20]:
                lock = asyncio.Lock()
                await lock.acquire()
                manager.sync_engine._sync_user_locks[qq] = lock
                locks.append(lock)
            self.assertEqual(await manager.schedule_training_snapshots(now=self.now), 1)
            manager.submit_account_sync.assert_awaited_once_with(qq_ids[-1], ["luogu"], expected_epoch=1)
        finally:
            for lock in locks:
                lock.release()
            manager.tasks.clear()
        manager.submit_account_sync.reset_mock()
        self.assertEqual(await manager.schedule_training_snapshots(now=self.now + 30), 20)
        self.assertEqual([call.args[0] for call in manager.submit_account_sync.await_args_list], qq_ids[:20])

    async def test_scheduler_caps_failure_backoff_and_preserves_upstream_retry_time(self):
        manager, _ = await self.scheduler_for_members()
        await self.sql("INSERT OR REPLACE INTO user_platform_sync_state(user_qq_id,platform,last_status,last_attempt_at,consecutive_failures) VALUES('22345678','luogu','failed',?,100)", (self.now,))
        self.assertEqual(await manager.schedule_training_snapshots(now=self.now + 899), 0)
        self.assertEqual(await manager.schedule_training_snapshots(now=self.now + 900), 1)
        await self.sql("UPDATE user_platform_sync_state SET next_retry_at=? WHERE user_qq_id='22345678' AND platform='luogu'", (self.now + 2000,))
        self.assertEqual(await manager.schedule_training_snapshots(now=self.now + 1900), 0)
        self.assertEqual(await manager.schedule_training_snapshots(now=self.now + 2000), 1)


    async def test_upcoming_task_already_displays_known_luogu_ac(self):
        await self.sql("INSERT INTO submissions(user_qq_id,platform,problem_id,submit_time) VALUES('22345678','luogu','P1001',0)")
        task=await self.task(starts_at=self.now+3600,due_at=self.now+7200)
        await self.publish(task)
        _,detail=await self.info(task['id'])
        self.assertEqual(detail['recipient']['completed_problems'],1)
        self.assertEqual(detail['recipient']['completion'],'not_started')
        self.assertTrue(detail['problems'][0]['is_ac'])


    async def test_startup_reclassifies_old_tasks_and_uses_existing_local_ac_without_fetching(self):
        task=await self.task(due_at=self.now-86400,starts_at=self.now-172800)
        await self.publish(task)
        await self.sql("UPDATE training_task_recipients SET bindings_json=json_remove(bindings_json,'$.luogu') WHERE task_id=?",(task['id'],))
        await self.sql("UPDATE training_task_progress SET binding_key=NULL,snapshot_json=NULL WHERE problem_id IN (SELECT id FROM training_task_problems WHERE task_id=?)",(task['id'],))
        await self.sql("UPDATE users SET luogu_binding_version=7 WHERE qq_id='22345678'")
        await self.sql("INSERT INTO submissions(user_qq_id,platform,problem_id,submit_time) VALUES('22345678','luogu','luogu_P1001',0)")
        await self.lifespan.__aexit__(None,None,None)
        from feat.api.app import create_app
        self.app=create_app(member_sync=False,training_sync=True)
        self.lifespan=self.app.test_app()
        with patch.object(luogu,'luogu_get',new=AsyncMock()) as network, patch.object(WebTaskManager,'start_training_task_sync') as start:
            await self.lifespan.__aenter__()
        network.assert_not_awaited()
        start.assert_called_once()
        self.client=self.app.test_client()
        await self.client.post('/api/auth/login',json={'qq_id':'12345678','password':'Test-Password-123!'})
        overview,detail=await self.info(task['id'])
        self.assertEqual(overview['summary']['completed_problem_count'],1)
        self.assertEqual(overview['summary']['uncertain_problem_count'],0)
        self.assertEqual(detail['problems'][0]['evidence']['source'],'local_luogu_ac_set')
        self.assertEqual((await self.sql('SELECT binding_key FROM training_task_progress'))[0]['binding_key'],'1234:7')


    async def test_scheduler_includes_future_and_long_ended_tasks(self):
        for start,due in [(self.now+86400,self.now+172800),(self.now-172800,self.now-86400)]:
            task=await self.task(starts_at=start,due_at=due)
            await self.publish(task)
        engine=SyncEngine(self.db_path,{})
        await engine.start()
        manager=WebTaskManager(engine)
        self.extra_engine,self.extra_manager=engine,manager
        manager.submit_account_sync=AsyncMock(return_value={'id':'historical-sync'})
        self.assertEqual(await manager.schedule_training_snapshots(now=self.now),1)
        manager.submit_account_sync.assert_awaited_once_with('22345678',['luogu'],expected_epoch=1)
