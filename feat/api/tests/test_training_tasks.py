import asyncio
import json
import os
import time
import unittest
from unittest.mock import AsyncMock, patch

import test_api_contract as contract
from feat.api.acm_api.database import connect_db
from feat.api.app import create_app
from feat.api.acm_api import training_task_service as service


class TrainingTaskTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        environment = self.enterContext(patch.dict(os.environ))
        environment.pop("ACM_TRAINING_TASKS_ENABLED", None)
        await contract.ApiContractTests.asyncSetUp(self)
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

    async def test_default_configuration_exposes_member_entry_and_allows_publish(self):
        self.assertNotIn("ACM_TRAINING_TASKS_ENABLED", os.environ)
        options = await (await self.client.get('/api/admin/training-tasks/options')).get_json()
        self.assertIs(options["enabled"], True)
        member = self.app.test_client()
        login = await member.post('/api/auth/login', json={"qq_id": "22345678", "password": "Test-Password-123!"})
        self.assertEqual(login.status_code, 200, await login.get_json())
        identity = await (await member.get('/api/auth/me')).get_json()
        self.assertEqual(identity["role"], "member")
        self.assertIs(identity["training_tasks_enabled"], True)
        task = await self.create()
        published = await self.publish(task)
        self.assertEqual(published.status_code, 200, await published.get_json())

    async def test_explicit_environment_switch_overrides_default(self):
        for setting, expected in [("false", False), ("true", True)]:
            with self.subTest(setting=setting), patch.dict(os.environ, {"ACM_TRAINING_TASKS_ENABLED": setting}):
                self.assertIs(create_app().config["TRAINING_TASKS_ENABLED"], expected)

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
        conflict = await stale.get_json()
        self.assertEqual((stale.status_code, conflict['code'], conflict['version']), (409, 'version_conflict', 2))
        self.assertTrue(conflict['request_id'])

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
        identity = await (await self.client.get('/api/auth/me')).get_json()
        options = await (await self.client.get('/api/admin/training-tasks/options')).get_json()
        self.assertIs(identity['training_tasks_enabled'], False)
        self.assertIs(options['enabled'], False)
        disabled = await self.publish(task)
        self.assertEqual((disabled.status_code, (await disabled.get_json())['code']), (503, 'feature_disabled'))
        self.app.config['TRAINING_TASKS_ENABLED'] = True
        await self.publish(task)
        self.app.config['TRAINING_TASKS_ENABLED'] = False
        self.assertEqual((await self.client.get(f'/api/admin/training-tasks/{task["id"]}')).status_code, 200)
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


    async def test_luogu_resolution_dedup_metadata_and_publish_capability(self):
        await self.sql("INSERT INTO recommendations(platform,problem_id,problem_name,problem_url,tags) VALUES('luogu','P1001','合成 A+B 题','https://www.luogu.com.cn/problem/P1001','[]')")
        await self.sql("INSERT INTO crawler_problems(platform,problem_id,contest_id,problem_name,problem_url,metadata_json,statement_html,created_at,updated_at) VALUES('luogu','P1001','','合成 A+B 题','https://www.luogu.com.cn/problem/P1001',?, '<p>合成题面</p>','2026-11-17','2026-11-17')", (json.dumps({'luogu': {'difficulty': 1, 'tag_ids': []}}),))
        options = await (await self.client.get('/api/admin/training-tasks/options')).get_json()
        luogu = next(p for p in options['capabilities'] if p['platform'] == 'luogu')
        self.assertTrue(luogu['can_publish'])
        self.assertFalse(luogu['period_ac'])
        self.assertTrue(luogu['historical_ac'])
        self.assertTrue(luogu['snapshot_ac'])
        response = await self.client.post('/api/admin/training-tasks/resolve-problems', headers=self.headers,
            json={'problems': [{'platform': 'luogu', 'problem_id': pid} for pid in ['p1001', 'P1001', 'P1002', 'B1001', 'T1', 'P0', 'https://www.luogu.com.cn/problem/P1001']]})
        result = await response.get_json()
        self.assertEqual((response.status_code, result['duplicates'], len(result['errors'])), (200, 1, 4))
        self.assertEqual([p['problem_id'] for p in result['items']], ['P1001', 'P1002'])
        first, missing = result['items']
        self.assertEqual(first['problem_name'], '合成 A+B 题')
        self.assertTrue(first['content_available'])
        self.assertEqual(first['native_difficulty']['id'], 1)
        self.assertTrue(first['can_publish'])
        self.assertTrue(first['supported'])
        self.assertFalse(missing['content_available'])
        self.assertEqual(missing['problem_url'], 'https://www.luogu.com.cn/problem/P1002')
        task = await self.create(luogu_snapshot=True, problems=[{'platform': 'luogu', 'problem_id': 'p1001'}])
        checked = await self.preview(task)
        self.assertEqual((checked['recipient_count'], checked['unbound_count']), (1, 1))
        first_publish, retry = await self.publish(task, checked), await self.publish(task, checked)
        self.assertEqual((first_publish.status_code, retry.status_code), (200, 200))
        published = await first_publish.get_json()
        self.assertEqual((published['state'], published['problems'][0]['problem_name']), ('published', '合成 A+B 题'))
        self.assertEqual(len(await self.sql('SELECT * FROM training_task_recipients')), 1)

    async def test_luogu_task_is_visible_only_to_recipient_without_oj_binding(self):
        task = await self.create(luogu_snapshot=True, problems=[{'platform': 'luogu', 'problem_id': 'P1001'}])
        self.assertEqual((await self.publish(task)).status_code, 200)
        # Preserve the pre-upgrade publication policy: old period tasks did not opt in.
        await self.sql("UPDATE training_tasks SET luogu_snapshot=0 WHERE id=?", (task['id'],))
        await self.sql("UPDATE training_task_recipients SET bindings_json='{}' WHERE task_id=?", (task['id'],))
        member = self.app.test_client()
        login = await member.post('/api/auth/login', json={'qq_id': '22345678', 'password': 'Test-Password-123!'})
        headers = {'X-CSRF-Token': (await login.get_json())['csrf_token']}
        result = await (await member.get(f'/api/me/training-tasks/{task["id"]}')).get_json()
        problem = result['problems'][0]
        self.assertEqual((problem['platform'], problem['problem_id'], problem['verification'], problem['status']), ('luogu', 'P1001', 'unsupported', 'unverified'))
        self.assertIsNone(problem['evidence'])
        self.assertEqual((result['recipient']['completed_problems'], result['recipient']['binding_warnings'], result['recipient']['unsupported_problems']), (0, 0, 1))
        listing = await (await member.get('/api/me/training-tasks?tab=all')).get_json()
        self.assertEqual([t['id'] for t in listing['items']], [task['id']])
        submitter = self.app.config['PLUGIN_CONFIG']['_account_sync_submitter'] = AsyncMock()
        response = await member.post(f'/api/me/training-tasks/{task["id"]}/refresh', headers=headers, json={})
        self.assertEqual((response.status_code, (await response.get_json())['code']), (409, 'unsupported_verification'))
        submitter.assert_not_called()
        self.assertEqual((await member.get(f'/api/admin/training-tasks/{task["id"]}')).status_code, 403)
        await self.seed('32345678', status='其他组')
        stranger = self.app.test_client()
        await stranger.post('/api/auth/login', json={'qq_id': '32345678', 'password': 'Test-Password-123!'})
        self.assertEqual((await stranger.get(f'/api/me/training-tasks/{task["id"]}')).status_code, 404)

    async def test_luogu_historical_catalog_alias_keeps_its_name(self):
        await self.sql("INSERT INTO recommendations(platform,problem_id,problem_name,problem_url,tags) VALUES('luogu','luogu_P1003','合成历史洛谷题','https://www.luogu.com.cn/problem/P1003','[]')")
        task = await self.create(luogu_snapshot=True, problems=[{'platform': 'luogu', 'problem_id': 'P1003'}])
        self.assertEqual(task['problems'][0]['problem_name'], '合成历史洛谷题')
        self.assertEqual(task['problems'][0]['problem_id'], 'P1003')


    async def add_luogu_statement(self, alias, *, html='<p>合成题面</p>', text=None, pdf=None):
        await self.sql("INSERT INTO crawler_problems(platform,problem_id,contest_id,problem_name,problem_url,metadata_json,statement_html,statement_text,statement_pdf,created_at,updated_at) VALUES('luogu',?,'','合成洛谷题',?,'{}',?,?,?,'2026-11-17','2026-11-17')",
                       (alias, 'https://www.luogu.com.cn/problem/' + alias.rsplit('_', 1)[-1].upper(), html, text, pdf))

    async def test_luogu_case_and_prefix_aliases_resolve_name_and_statement(self):
        aliases = ['p1001', 'luogu_p1002', 'luogu_P1003', 'P1004', 'LUOGU_p1005', 'p1006']
        for number, alias in enumerate(aliases, 1001):
            await self.sql("INSERT INTO recommendations(platform,problem_id,problem_name,problem_url,tags) VALUES('luogu',?,?,?,'[]')",
                           (alias, f'历史题名 {number}', f'https://www.luogu.com.cn/problem/P{number}'))
            formats = {1002: {'html': None, 'text': '合成纯文本题面'},
                       1003: {'html': None, 'pdf': b'%PDF-1.4 fixture'},
                       1006: {'html': '', 'text': '', 'pdf': b''}}
            await self.add_luogu_statement(alias, **formats.get(number, {}))
        inputs = [{'platform': 'luogu', 'problem_id': f'p{number}'} for number in range(1001, 1007)]
        response = await self.client.post('/api/admin/training-tasks/resolve-problems', headers=self.headers,
                                          json={'problems': inputs})
        self.assertEqual(response.status_code, 200)
        resolved = (await response.get_json())['items']
        task = await self.create(luogu_snapshot=True, problems=inputs)
        for items in (resolved, task['problems']):
            self.assertEqual([p['problem_id'] for p in items], [f'P{n}' for n in range(1001, 1007)])
            self.assertEqual([p['problem_name'] for p in items], [f'历史题名 {n}' for n in range(1001, 1007)])
            self.assertEqual([p['content_available'] for p in items], [True] * 5 + [False])
            self.assertTrue(all(p['can_publish'] for p in items))
            self.assertTrue(all(p['supported'] for p in items))

    async def test_legacy_non_p_drafts_are_rechecked_at_preview_and_publish(self):
        for pid in ['B1001', 'T1', 'U1', 'P0']:
            with self.subTest(problem_id=pid):
                task = await self.create(luogu_snapshot=True, problems=[{'platform': 'luogu', 'problem_id': 'P1001'}])
                checked = await self.preview(task)
                # Simulate a persisted pre-upgrade draft, including an existing preview token.
                await self.sql("UPDATE training_task_problems SET problem_id=? WHERE task_id=?", (pid, task['id']))
                detail = await (await self.client.get(f'/api/admin/training-tasks/{task["id"]}')).get_json()
                self.assertFalse(detail['problems'][0]['can_publish'])
                preview = await self.client.post(f'/api/admin/training-tasks/{task["id"]}/audience-preview',
                                                headers=self.headers, json={'version': task['version']})
                publish = await self.publish(task, checked)
                for response in (preview, publish):
                    self.assertEqual((response.status_code, (await response.get_json())['code']), (400, 'unsupported_capability'))
                stored = await self.sql("SELECT state,version FROM training_tasks WHERE id=?", (task['id'],))
                self.assertEqual(stored, [{'state': 'draft', 'version': task['version']}])
        self.assertEqual(await self.sql('SELECT * FROM training_task_recipients'), [])
        self.assertEqual(await self.sql("SELECT * FROM training_task_audit WHERE action='published'"), [])

    async def test_legacy_p_alias_is_still_publishable(self):
        task = await self.create(luogu_snapshot=True, problems=[{'platform': 'luogu', 'problem_id': 'P1001'}])
        await self.sql("UPDATE training_task_problems SET problem_id='luogu_p1001' WHERE task_id=?", (task['id'],))
        checked = await self.preview(task)
        response = await self.publish(task, checked)
        self.assertEqual(response.status_code, 200)
        problem = (await response.get_json())['problems'][0]
        self.assertEqual(problem['problem_id'], 'P1001')
        self.assertTrue(problem['can_publish'])

    async def test_statement_availability_is_live_without_rewriting_frozen_task(self):
        task = await self.create(luogu_snapshot=True, problems=[{'platform': 'luogu', 'problem_id': pid} for pid in ['P1004', 'P1005']])
        self.assertEqual([p['content_available'] for p in task['problems']], [False, False])
        # Collection before publication must already be reflected in the draft/preview.
        await self.add_luogu_statement('p1004')
        draft = await (await self.client.get(f'/api/admin/training-tasks/{task["id"]}')).get_json()
        self.assertEqual([p['content_available'] for p in draft['problems']], [True, False])
        published = await self.publish(task)
        self.assertEqual(published.status_code, 200)
        frozen_problems = await self.sql('SELECT * FROM training_task_problems WHERE task_id=? ORDER BY position', (task['id'],))
        frozen_task = await self.sql('SELECT * FROM training_tasks WHERE id=?', (task['id'],))
        member = self.app.test_client()
        await member.post('/api/auth/login', json={'qq_id': '22345678', 'password': 'Test-Password-123!'})
        member_url = f'/api/me/training-tasks/{task["id"]}'
        before = await (await member.get(member_url)).get_json()
        self.assertEqual([p['content_available'] for p in before['problems']], [True, False])
        # Collection after publication restores the member and administrator statement links.
        await self.add_luogu_statement('luogu_p1005')
        await self.sql("INSERT INTO recommendations(platform,problem_id,problem_name,problem_url,tags) VALUES('luogu','P1005','后续变更题名','https://www.luogu.com.cn/problem/P1005','[\"新标签\"]')")
        recipient_id = before['recipient']['id']
        for client, url in [(self.client, f'/api/admin/training-tasks/{task["id"]}'),
                            (self.client, f'/api/admin/training-tasks/{task["id"]}/progress/{recipient_id}'),
                            (member, member_url)]:
            response = await client.get(url)
            self.assertEqual(response.status_code, 200)
            result = await response.get_json()
            self.assertEqual([p['content_available'] for p in result['problems']], [True, True])
            self.assertEqual([p['problem_name'] for p in result['problems']], ['P1004', 'P1005'])
            self.assertEqual([p['position'] for p in result['problems']], [1, 2])
        statement = await member.get('/api/me/problems/luogu/P1005')
        self.assertEqual(statement.status_code, 200)
        self.assertTrue((await statement.get_json())['content_available'])
        # Removing local content also clears the derived availability without changing the task.
        await self.sql("UPDATE crawler_problems SET statement_html=NULL,statement_pdf=NULL WHERE platform='luogu' AND problem_id='p1004'")
        after = await (await member.get(member_url)).get_json()
        self.assertEqual([p['content_available'] for p in after['problems']], [False, True])
        self.assertEqual(await self.sql('SELECT * FROM training_task_problems WHERE task_id=? ORDER BY position', (task['id'],)), frozen_problems)
        self.assertEqual(await self.sql('SELECT * FROM training_tasks WHERE id=?', (task['id'],)), frozen_task)


if __name__ == '__main__':
    unittest.main()
