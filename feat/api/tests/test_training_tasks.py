import asyncio
import json
import time
import unittest

import test_api_contract as contract
from feat.api.acm_api.database import connect_db
from feat.api.acm_api import training_task_service as service


class TrainingTaskTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await contract.ApiContractTests.asyncSetUp(self)
        self.app.config["TRAINING_TASKS_ENABLED"] = True
        self.lifespan = self.app.test_app()
        await self.lifespan.__aenter__()
        self.client = self.app.test_client()
        self.headers = await contract.ApiContractTests.account_login(self, self.client)
        await self.sql("UPDATE users SET status='管理组' WHERE qq_id='12345678'")
        await self.seed("22345678")
        self.now = int(time.time())

    async def asyncTearDown(self):
        await self.lifespan.__aexit__(None, None, None)
        await contract.ApiContractTests.asyncTearDown(self)

    async def sql(self, query, values=()):
        db = await connect_db(self.db_path)
        try:
            cursor = await db.execute(query, values)
            result = [dict(r) for r in await cursor.fetchall()]
            await db.commit()
            return result
        finally:
            await db.close()

    async def seed(self, qq, *, active=1, account=True, status="训练组"):
        await self.sql("INSERT INTO users(qq_id,name,status) VALUES(?,?,?)", (qq, "合成成员" + qq[-2:], status))
        if account:
            await self.sql("INSERT INTO web_accounts(qq_id,password_hash,role,must_change_password,is_active,created_at,updated_at) SELECT ?,password_hash,'member',0,?,1,1 FROM web_accounts WHERE qq_id='12345678'", (qq, active))

    def draft(self, **changes):
        return {"title": "图论周训练", "description": "完成固定题单", "statuses": ["训练组"], "starts_at": self.now - 100, "due_at": self.now + 100, "rule": "period_ac", "problems": [{"platform": "codeforces", "problem_id": "1A"}], **changes}

    async def create(self, **changes):
        response = await self.client.post('/api/admin/training-tasks', headers=self.headers, json=self.draft(**changes))
        self.assertEqual(response.status_code, 201, await response.get_json())
        return await response.get_json()

    async def preview(self, task):
        response = await self.client.post(f'/api/admin/training-tasks/{task["id"]}/audience-preview', headers=self.headers, json={"version": task["version"]})
        self.assertEqual(response.status_code, 200, await response.get_json())
        return await response.get_json()

    async def publish(self, task, preview=None, **changes):
        preview = preview or await self.preview(task)
        payload = {"version": task["version"], "preview_token": preview["preview_token"], "confirm_exclusions": True, **changes}
        return await self.client.post(f'/api/admin/training-tasks/{task["id"]}/publish', headers={**self.headers, "Idempotency-Key": "training-publish-key-123"}, json=payload)

    async def test_dynamic_union_exclusions_atomic_publish_and_retry(self):
        await self.seed("32345678", active=0)
        await self.seed("42345678", account=False)
        await self.seed("52345678", status="新身份")
        options = await (await self.client.get('/api/admin/training-tasks/options')).get_json()
        self.assertIn("新身份", options["statuses"])
        task = await self.create(statuses=["训练组", "训练组", "新身份"])
        preview = await self.preview(task)
        self.assertEqual((preview['total'], preview['recipient_count'], preview['excluded_count'], preview['unbound_count']), (4, 2, 2, 2))
        denied = await self.publish(task, preview, confirm_exclusions=False)
        self.assertEqual(denied.status_code, 400)
        first, retry = await self.publish(task, preview), await self.publish(task, preview)
        self.assertEqual((first.status_code, retry.status_code), (200, 200))
        self.assertEqual((await first.get_json())['recipient_count'], 2)
        self.assertEqual(len(await self.sql('SELECT * FROM training_task_recipients')), 2)
        self.assertEqual(len(await self.sql("SELECT * FROM training_task_audit WHERE action='published'")), 1)

    async def test_changed_audience_and_stale_draft_require_reconfirmation(self):
        task = await self.create()
        preview = await self.preview(task)
        await self.sql("UPDATE users SET cf_handle='Changed' WHERE qq_id='22345678'")
        response = await self.publish(task, preview)
        self.assertEqual((response.status_code, (await response.get_json())['code']), (409, 'audience_changed'))
        update = await self.client.patch(f'/api/admin/training-tasks/{task["id"]}', headers=self.headers, json={**self.draft(), 'version': 1})
        self.assertEqual(update.status_code, 200)
        stale = await self.client.patch(f'/api/admin/training-tasks/{task["id"]}', headers=self.headers, json={**self.draft(), 'version': 1})
        self.assertEqual((stale.status_code, (await stale.get_json())['code']), (409, 'version_conflict'))

    async def test_validation_dedup_and_unsupported_draft(self):
        task = await self.create(problems=[{'problem_id': '1a'}, {'problem_id': 'cf_1A'}])
        self.assertEqual(len(task['problems']), 1)
        resolved = await self.client.post('/api/admin/training-tasks/resolve-problems', headers=self.headers, json={'problems': [{'problem_id': 'https://evil.invalid/1A'}, {'problem_id': '2B'}]})
        self.assertEqual(len((await resolved.get_json())['errors']), 1)
        other = await self.create(problems=[{'platform': 'atcoder', 'problem_id': 'abc300_a'}])
        blocked = await self.client.post(f'/api/admin/training-tasks/{other["id"]}/audience-preview', headers=self.headers, json={'version': 1})
        self.assertEqual((blocked.status_code, (await blocked.get_json())['code']), (400, 'unsupported_capability'))
        empty = await self.create(statuses=['不存在身份'])
        self.assertEqual((await self.publish(empty)).status_code, 400)
        invalid = await self.client.post('/api/admin/training-tasks', headers=self.headers, json=self.draft(due_at=self.now-101))
        self.assertEqual(invalid.status_code, 400)

    async def test_published_immutable_extend_cancel_and_migration_restart(self):
        task = await self.create()
        published = await (await self.publish(task)).get_json()
        base = f'/api/admin/training-tasks/{task["id"]}'
        for method in (self.client.patch, self.client.delete):
            response = await method(base, headers=self.headers, json={**self.draft(), 'version': published['version']})
            self.assertEqual(response.status_code, 409)
        shorten = await self.client.post(base+'/extend-deadline', headers=self.headers, json={'version': 2, 'due_at': self.now, 'reason': '缩短'})
        self.assertEqual(shorten.status_code, 400)
        extended = await (await self.client.post(base+'/extend-deadline', headers=self.headers, json={'version': 2, 'due_at': self.now+200, 'reason': '延期一天'})).get_json()
        self.assertEqual((extended['original_due_at'], extended['due_at']), (self.now+100, self.now+200))
        cancelled = await self.client.post(base+'/cancel', headers=self.headers, json={'version': 3, 'reason': '训练安排调整'})
        self.assertEqual((await cancelled.get_json())['state'], 'cancelled')
        reopened = await self.sql('SELECT state,version FROM training_tasks')
        self.assertEqual(reopened, [{'state': 'cancelled', 'version': 4}])

    async def test_permissions_csrf_switch_and_frozen_denominator_privacy(self):
        no_csrf = await self.client.post('/api/admin/training-tasks', json=self.draft())
        self.assertEqual(no_csrf.status_code, 403)
        task = await self.create()
        self.app.config['TRAINING_TASKS_ENABLED'] = False
        self.assertEqual((await self.publish(task)).status_code, 503)
        self.app.config['TRAINING_TASKS_ENABLED'] = True
        await self.publish(task)
        await self.sql("UPDATE users SET account_state='closed',account_epoch=account_epoch+1 WHERE qq_id='22345678'")
        recipient = (await self.sql('SELECT * FROM training_task_recipients'))[0]
        self.assertIsNone(recipient['qq_id'])
        self.assertEqual((recipient['closed'], recipient['name'], recipient['bindings_json']), (1, '已注销成员', '{}'))
        await self.sql("UPDATE web_accounts SET role='member' WHERE qq_id='12345678'")
        self.assertEqual((await self.client.get('/api/admin/training-tasks')).status_code, 403)

    async def test_partial_draft_update_keeps_rules_and_concurrent_publish_is_single(self):
        task = await self.create(problems=[{'problem_id':'1A'},{'problem_id':'2A'}], rule='historical_ac')
        patched = await self.client.patch(f'/api/admin/training-tasks/{task["id"]}', headers=self.headers, json={'version':1,'title':'仅改标题'})
        updated = await patched.get_json()
        self.assertEqual((updated['rule'], len(updated['problems']), updated['statuses']), ('historical_ac',2,['训练组']))
        checked = await self.preview(updated)
        first, second = await asyncio.gather(self.publish(updated,checked),self.publish(updated,checked))
        self.assertEqual((first.status_code,second.status_code),(200,200))
        self.assertEqual(len(await self.sql('SELECT * FROM training_task_recipients')),1)
        self.assertEqual(len(await self.sql('SELECT * FROM training_task_progress')),2)
        await self.sql("UPDATE users SET status='身份已调整' WHERE qq_id='22345678'")
        self.assertEqual((await (await self.client.get(f'/api/admin/training-tasks/{task["id"]}')).get_json())['recipient_count'],1)

    async def test_preview_expiry_and_duplicate_inputs_near_limit(self):
        task = await self.create()
        checked = await self.preview(task)
        await self.sql('UPDATE training_tasks SET preview_expires_at=0')
        response = await self.publish(task, checked)
        self.assertEqual((response.status_code,(await response.get_json())['code']),(409,'audience_changed'))
        response = await self.client.post('/api/admin/training-tasks/resolve-problems', headers=self.headers,json={'problems':[{'problem_id':'1A'}]*51})
        result = await response.get_json()
        self.assertEqual((response.status_code,len(result['items']),result['duplicates']),(200,1,50))


if __name__ == '__main__':
    unittest.main()
