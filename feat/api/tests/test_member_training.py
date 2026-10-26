import asyncio
import time
import unittest
import aiosqlite
from urllib.parse import urlencode
from unittest.mock import AsyncMock, patch
import aiohttp

import test_api_contract as contract
from feat.api.acm_api import binding_service
from feat.api.acm_api.binding_guard import BindingGuard, BindingChanged
from feat.api.acm_api.database import connect_db
from feat.api.service_runtime import SyncEngine


class MemberTrainingTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = contract.ApiContractTests.asyncSetUp
    asyncTearDown = contract.ApiContractTests.asyncTearDown
    account_login = contract.ApiContractTests.account_login

    async def sql(self, sql, args=()):
        db = await aiosqlite.connect(self.db_path)
        try:
            cursor = await db.execute(sql, args)
            rows = await cursor.fetchall()
            await db.commit()
            return rows
        finally:
            await db.close()

    async def pending(self, client, headers, account="NewHandle"):
        with patch.object(binding_service, "validate_account", AsyncMock(return_value=account)):
            response = await client.post("/api/me/bindings/cf/verification", headers=headers, json={"account": account})
        self.assertEqual(response.status_code, 200, await response.get_json())
        return await response.get_json()

    async def test_solved_scope_is_session_owned_stable_paginated_and_keeps_catalog(self):
        async with self.app.test_app():
            client = self.app.test_client(); await self.account_login(client, role="member")
            for owner, pid, stamp in [("12345678", "A", 20), ("12345678", "B", 20), ("12345678", "C", 10), ("99999999", "Other", 50)]:
                await self.sql("INSERT INTO submissions(user_qq_id,platform,problem_id,problem_name,submit_time) VALUES(?,'atcoder',?,?,?)", (owner, pid, "题目" + pid, stamp))
            await self.sql("INSERT INTO recommendations(platform,problem_id,problem_name,problem_url) VALUES('atcoder','CatalogOnly','目录题','https://atcoder.jp')")
            first = await (await client.get("/api/me/problems?scope=solved&page_size=2&qq_id=99999999&owner_qq_id=99999999")).get_json()
            self.assertEqual(first["total"], 3); self.assertEqual([r["problem_id"] for r in first["items"]], ["A", "B"])
            second = await (await client.get("/api/me/problems?scope=solved&page=2&page_size=2")).get_json()
            self.assertEqual([r["problem_id"] for r in second["items"]], ["C"])
            filtered = await (await client.get("/api/me/problems?" + urlencode({"scope":"solved","platform":"atcoder","tag":"题目A"}))).get_json()
            self.assertEqual(filtered["total"], 1)
            self.assertEqual((await (await client.get("/api/me/problems")).get_json())["total"], 5)
            await self.sql("INSERT INTO user_problem_state(owner_qq_id,platform,problem_id,is_favorite,updated_at) VALUES('12345678','atcoder','B',1,1)")
            favorites = await (await client.get("/api/me/problems?scope=solved&state=favorite")).get_json()
            self.assertEqual([item["problem_id"] for item in favorites["items"]], ["B"])
            self.assertEqual((await (await client.get("/api/me/problems?scope=solved&state=inbox")).get_json())["total"], 3)
            self.assertEqual((await client.get("/api/me/problems?scope=other")).status_code, 400)
            self.assertEqual((await client.get("/api/me/problems?scope=solved&page=x")).status_code, 400)
            self.assertEqual((await (await client.get("/api/me/problems?scope=solved")).get_json())["page_size"], 20)
            self.assertEqual((await (await client.get("/api/me/problems?scope=solved&page_size=9999")).get_json())["page_size"], 100)

    async def test_binding_endpoints_require_session_csrf_and_ignore_other_owner(self):
        async with self.app.test_app():
            client = self.app.test_client()
            self.assertEqual((await client.post("/api/me/bindings/cf/verification", json={"account": "A"})).status_code, 401)
            headers = await self.account_login(client, role="member")
            self.assertEqual((await client.post("/api/me/bindings/cf/verification", json={"account": "A"})).status_code, 403)
            with patch.object(binding_service, "validate_account", AsyncMock(return_value="NewHandle")):
                response = await client.post("/api/me/bindings/codeforces/verification?qq_id=99999999", headers=headers, json={"account": "NewHandle", "qq_id": "99999999"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual((await self.sql("SELECT qq_id FROM account_bind_verifications"))[0][0], "12345678")
            self.assertEqual((await client.post("/api/me/bindings/invalid/verification", headers=headers, json={})).status_code, 400)

    async def test_first_binding_consumes_verification_and_does_not_trust_client_proof(self):
        async with self.app.test_app():
            client=self.app.test_client();headers=await self.account_login(client, role="member")
            pending=await self.pending(client, headers)
            with patch.object(binding_service, "verify_ownership", AsyncMock(return_value=False)):
                rejected=await client.post("/api/me/bindings/cf/confirm", headers=headers, json={"verification_id": pending["verification_id"], "verified": True})
            self.assertEqual(rejected.status_code, 400)
            self.assertIsNone((await self.sql("SELECT cf_handle FROM users WHERE qq_id='12345678'"))[0][0])
            await self.sql("DELETE FROM binding_rate_limits WHERE action='confirm'")
            self.app.config["PLUGIN_CONFIG"]["_account_sync_submitter"]=lambda qq, platforms: {"id":"synthetic-job"}
            with patch.object(binding_service, "verify_ownership", AsyncMock(return_value=True)):
                accepted=await client.post("/api/me/bindings/codeforces/confirm", headers=headers, json={"verification_id":pending["verification_id"]})
            self.assertEqual(accepted.status_code, 202); self.assertEqual((await accepted.get_json())["sync_status"], "queued")
            self.assertEqual((await self.sql("SELECT cf_handle FROM users WHERE qq_id='12345678'"))[0][0], "NewHandle")
            self.assertEqual(len(await self.sql("SELECT * FROM account_bind_verifications")), 0)
            await self.sql("DELETE FROM binding_rate_limits WHERE action='confirm'")
            self.assertEqual((await client.post("/api/me/bindings/cf/confirm", headers=headers, json={"verification_id":pending["verification_id"]})).status_code,409)

    async def test_expiry_conflict_and_rate_limit_have_explicit_errors(self):
        async with self.app.test_app():
            client=self.app.test_client();headers=await self.account_login(client, role="member")
            pending=await self.pending(client, headers)
            self.assertEqual((await client.post("/api/me/bindings/cf/verification", headers=headers, json={"account":"Second"})).status_code,429)
            await self.sql("UPDATE account_bind_verifications SET expires_at=0")
            expired=await client.post("/api/me/bindings/cf/confirm",headers=headers,json={"verification_id":pending["verification_id"]})
            self.assertEqual((await expired.get_json())["code"],"verification_expired")
            await self.sql("DELETE FROM binding_rate_limits")
            await self.sql("INSERT INTO users(qq_id,name,cf_handle) VALUES('99999999','Other','Occupied')")
            conflict=await client.post("/api/me/bindings/cf/verification",headers=headers,json={"account":"Occupied"})
            self.assertEqual((await conflict.get_json())["code"],"account_occupied")

    async def test_rebind_failure_keeps_original_and_password_confirmation_is_required(self):
        async with self.app.test_app():
            client=self.app.test_client();headers=await self.account_login(client,role="member")
            await self.sql("UPDATE users SET cf_handle='Original' WHERE qq_id='12345678'")
            await self.sql("INSERT INTO submissions(user_qq_id,platform,problem_id,submit_time) VALUES('12345678','codeforces','cf_1A',1)")
            pending=await self.pending(client,headers)
            with patch.object(binding_service,"verify_ownership",AsyncMock(return_value=False)):
                response=await client.post("/api/me/bindings/cf/confirm",headers=headers,json={"verification_id":pending["verification_id"],"password":"Test-Password-123!","confirmed":True,"current_account":"Original"})
            self.assertEqual(response.status_code,400)
            self.assertEqual((await self.sql("SELECT cf_handle FROM users WHERE qq_id='12345678'"))[0][0],"Original")
            self.assertEqual(len(await self.sql("SELECT * FROM submissions")),1)
            denied=await client.delete("/api/me/bindings/cf",headers=headers,json={"confirmed":True,"current_account":"Original","password":"wrong"})
            self.assertEqual(denied.status_code,403)
            await self.sql("DELETE FROM binding_rate_limits WHERE action='unbind'")
            denied=await client.delete("/api/me/bindings/cf",headers=headers,json={"password":"Test-Password-123!"})
            self.assertEqual((await denied.get_json())["code"],"confirmation_required")

    async def test_unbind_is_platform_scoped_and_preserves_learning_archive(self):
        async with self.app.test_app():
            client=self.app.test_client();headers=await self.account_login(client,role="member")
            await self.sql("UPDATE users SET atcoder_handle='OldAt',cf_handle='KeepCF' WHERE qq_id='12345678'")
            for owner,platform in [('12345678','atcoder'),('12345678','codeforces'),('99999999','atcoder')]:
                await self.sql("INSERT INTO submissions(user_qq_id,platform,problem_id,submit_time) VALUES(?,?, 'A',1)",(owner,platform))
            await self.sql("INSERT INTO user_problem_state(owner_qq_id,platform,problem_id,is_favorite,note_md,updated_at) VALUES('12345678','atcoder','A',1,'Archived',1)")
            result=await client.delete('/api/me/bindings/atcoder',headers=headers,json={"password":"Test-Password-123!","confirmed":True,"current_account":"OldAt"})
            self.assertEqual(result.status_code,200)
            self.assertEqual(len(await self.sql('SELECT * FROM submissions')),2)
            self.assertEqual((await self.sql('SELECT note_md FROM user_problem_state'))[0][0],'Archived')
            self.assertEqual((await self.sql("SELECT atcoder_binding_version FROM users WHERE qq_id='12345678'"))[0][0],2)
            self.assertEqual((await self.sql("SELECT action FROM binding_audit WHERE result='success'"))[0][0],'unbind')

    async def test_concurrent_binding_change_during_network_verification_rejects_old_result(self):
        async with self.app.test_app():
            client=self.app.test_client();headers=await self.account_login(client,role='member')
            pending=await self.pending(client,headers);entered=asyncio.Event();release=asyncio.Event()
            async def slow(*args): entered.set();await release.wait();return True
            with patch.object(binding_service,'verify_ownership',slow):
                request=asyncio.create_task(client.post('/api/me/bindings/cf/confirm',headers=headers,json={'verification_id':pending['verification_id']}))
                await entered.wait();await self.sql("UPDATE users SET cf_handle='NewerBinding' WHERE qq_id='12345678'");release.set();result=await request
            self.assertEqual(result.status_code,409)
            self.assertEqual((await self.sql("SELECT cf_handle FROM users WHERE qq_id='12345678'"))[0][0],'NewerBinding')

    async def test_non_cf_aba_rebind_discards_old_batch_and_cannot_mark_new_state(self):
        async with self.app.test_app():
            client=self.app.test_client();await self.account_login(client,role='member')
            await self.sql("UPDATE users SET atcoder_handle='Original' WHERE qq_id='12345678'")
            engine=SyncEngine(self.db_path,{});await engine.start()
            try:
                async with engine.db.execute("SELECT * FROM users WHERE qq_id='12345678'") as cursor: old=await cursor.fetchone()
                await engine._get_platform_sync_state('12345678','atcoder',user=old)
                await self.sql("UPDATE users SET atcoder_handle='Second' WHERE qq_id='12345678'")
                await self.sql("UPDATE users SET atcoder_handle='Original' WHERE qq_id='12345678'")
                await self.sql("INSERT INTO user_platform_sync_state(user_qq_id,platform,last_status) VALUES('12345678','atcoder','never')")
                db=await connect_db(self.db_path)
                try:
                    with self.assertRaises(BindingChanged):
                        await BindingGuard(db,old,'atcoder').executemany("INSERT INTO submissions(user_qq_id,platform,problem_id,submit_time) VALUES(?,?,?,?)",[('12345678','atcoder','stale',1)])
                finally: await db.close()
                await engine._mark_platform_sync('12345678','atcoder','failed',int(time.time()),error_code='old-job')
                self.assertEqual((await self.sql("SELECT last_status FROM user_platform_sync_state WHERE platform='atcoder'"))[0][0],'never')
                self.assertEqual(len(await self.sql('SELECT * FROM submissions')),0)
            finally: await engine.close()

    async def test_profile_detects_lost_running_task_and_recovery_pages_are_directly_accessible(self):
        async with self.app.test_app():
            client=self.app.test_client();headers=await self.account_login(client,role='member')
            await self.sql("UPDATE users SET cf_handle='Handle' WHERE qq_id='12345678'")
            await self.sql("INSERT INTO user_platform_sync_state(user_qq_id,platform,last_status) VALUES('12345678','codeforces','running')")
            profile=await (await client.get('/api/me/profile')).get_json()
            cf=next(row for row in profile['bindings'] if row['platform']=='codeforces')
            self.assertEqual(cf['sync_status'],'failed');self.assertTrue(cf['self_service'])
            self.assertTrue(all(not row['self_service'] for row in profile['bindings'] if row['platform']!='codeforces'))
            for url in ['/auth-unavailable.html?next=%2Fhome.html','/forbidden.html']:
                self.assertEqual((await client.get(url)).status_code,200)
            denied=await client.get('/admin.html');self.assertEqual(denied.status_code,403);self.assertIn('返回个人中心',await denied.get_data(as_text=True))

    async def test_admin_binding_changes_require_confirmation_snapshot_and_audit(self):
        async with self.app.test_app():
            client=self.app.test_client();headers=await self.account_login(client,role='root')
            body={'qq_id':'12345678','name':'Member','cf_handle':'AdminHandle'}
            result=await client.put('/api/user',headers=headers,json=body)
            self.assertEqual(result.status_code,400)
            body.update(confirm_bindings=True,expected_bindings={'cf_handle':''},binding_versions={'codeforces':0})
            self.app.config['PLUGIN_CONFIG']['_account_sync_submitter']=lambda *args:None
            result=await client.put('/api/user',headers=headers,json=body)
            self.assertEqual(result.status_code,200,await result.get_json())
            self.assertEqual((await self.sql("SELECT actor_qq_id FROM binding_audit WHERE action='admin_binding_update'"))[0][0],'12345678')
            stale=await client.put('/api/user',headers=headers,json={**body,'cf_handle':'Another'})
            self.assertEqual(stale.status_code,409)

    async def test_cf_proof_checks_only_the_target_profile_editable_fields(self):
        async with self.app.test_app(), self.app.app_context():
            with patch.object(binding_service,'cf_request',AsyncMock(return_value=[{'handle':'Handle','firstName':'ACM-proof'}])):
                self.assertTrue(await binding_service.verify_ownership('codeforces','Handle','ACM-proof'))
            with patch.object(binding_service,'cf_request',AsyncMock(return_value=[{'handle':'Handle','firstName':'Someone','comments':'ACM-proof'}])):
                self.assertFalse(await binding_service.verify_ownership('codeforces','Handle','ACM-proof'))
            with patch.object(binding_service,'cf_request',AsyncMock(return_value=[{'handle':'Other','organization':'ACM-proof'}])):
                with self.assertRaises(binding_service.BindingError): await binding_service.verify_ownership('codeforces','Handle','ACM-proof')
    async def test_successful_rebind_is_atomic_and_sync_dispatch_failure_is_separate(self):
        async with self.app.test_app():
            client = self.app.test_client()
            headers = await self.account_login(client, role="member")
            await self.sql("UPDATE users SET cf_handle='Original',atcoder_handle='KeepAt' WHERE qq_id='12345678'")
            for platform in ("codeforces", "atcoder"):
                await self.sql("INSERT INTO submissions(user_qq_id,platform,problem_id,submit_time) VALUES('12345678',?,'A',1)", (platform,))
            await self.sql("INSERT INTO user_problem_state(owner_qq_id,platform,problem_id,is_favorite,note_md,updated_at) VALUES('12345678','codeforces','A',1,'Keep archive',1)")
            pending = await self.pending(client, headers)
            def unavailable(*args):
                raise RuntimeError("simulated queue unavailable")
            self.app.config["PLUGIN_CONFIG"]["_account_sync_submitter"] = unavailable
            with patch.object(binding_service, "verify_ownership", AsyncMock(return_value=True)):
                result = await client.post("/api/me/bindings/cf/confirm", headers=headers, json={"verification_id": pending["verification_id"], "password": "Test-Password-123!", "confirmed": True, "current_account": "Original"})
            payload = await result.get_json()
            self.assertEqual(result.status_code, 200, payload)
            self.assertTrue(payload["success"])
            self.assertEqual(payload["sync_status"], "failed")
            self.assertEqual((await self.sql("SELECT cf_handle,cf_binding_version FROM users WHERE qq_id='12345678'"))[0], ("NewHandle", 2))
            self.assertEqual((await self.sql("SELECT platform FROM submissions")), [("atcoder",)])
            self.assertEqual((await self.sql("SELECT note_md FROM user_problem_state"))[0][0], "Keep archive")
            self.assertFalse(await self.sql("SELECT * FROM account_bind_verifications"))
            profile = await (await client.get("/api/me/profile")).get_json()
            status = next(item for item in profile["bindings"] if item["platform"] == "codeforces")
            self.assertEqual(status["sync_status"], "failed")
            self.assertEqual(status["binding_status"], "bound")

    async def test_replaced_verification_during_network_cannot_commit(self):
        async with self.app.test_app():
            client = self.app.test_client()
            headers = await self.account_login(client, role="member")
            original = await self.pending(client, headers)
            entered, release = asyncio.Event(), asyncio.Event()
            async def slow(*args):
                entered.set()
                await release.wait()
                return True
            with patch.object(binding_service, "verify_ownership", slow):
                task = asyncio.create_task(client.post("/api/me/bindings/cf/confirm", headers=headers, json={"verification_id": original["verification_id"]}))
                await entered.wait()
                await self.sql("DELETE FROM binding_rate_limits WHERE action='verification'")
                newer = await self.pending(client, headers, "NewerHandle")
                release.set()
                result = await task
            self.assertEqual(result.status_code, 409)
            self.assertNotEqual(newer["verification_id"], original["verification_id"])
            self.assertEqual((await self.sql("SELECT account FROM account_bind_verifications"))[0][0], "NewerHandle")
            self.assertIsNone((await self.sql("SELECT cf_handle FROM users WHERE qq_id='12345678'"))[0][0])

    async def test_upstream_unavailable_preserves_binding_and_removes_partial_challenge(self):
        async with self.app.test_app():
            client = self.app.test_client()
            headers = await self.account_login(client, role="member")
            await self.sql("UPDATE users SET cf_handle='Original' WHERE qq_id='12345678'")
            with patch.object(binding_service, "validate_account", AsyncMock(side_effect=aiohttp.ClientError("offline"))):
                result = await client.post("/api/me/bindings/cf/verification", headers=headers, json={"account": "NewHandle"})
            self.assertEqual(result.status_code, 503)
            self.assertEqual((await result.get_json())["code"], "upstream_unavailable")
            self.assertFalse(await self.sql("SELECT * FROM account_bind_verifications"))
            self.assertEqual((await self.sql("SELECT cf_handle FROM users WHERE qq_id='12345678'"))[0][0], "Original")

    async def test_parallel_sync_state_transactions_and_current_guarded_write(self):
        async with self.app.test_app():
            client = self.app.test_client()
            await self.account_login(client, role="member")
            await self.sql("UPDATE users SET atcoder_handle='First' WHERE qq_id='12345678'")
            await self.sql("INSERT INTO users(qq_id,name,atcoder_handle) VALUES('99999999','Other','Second')")
            engine = SyncEngine(self.db_path, {})
            await engine.start()
            try:
                async with engine.db.execute("SELECT * FROM users ORDER BY qq_id") as cursor:
                    users = await cursor.fetchall()
                states = await asyncio.gather(*(engine._get_platform_sync_state(user["qq_id"], "atcoder", user=user) for user in users))
                self.assertEqual(len(states), 2)
                db = await connect_db(self.db_path)
                try:
                    await BindingGuard(db, users[0], "atcoder").executemany("INSERT INTO submissions(user_qq_id,platform,problem_id,submit_time) VALUES(?,?,?,?)", [("12345678", "atcoder", "current", 1)])
                    await db.commit()
                finally:
                    await db.close()
                self.assertEqual(len(await self.sql("SELECT * FROM submissions")), 1)
                self.assertTrue(await engine._mark_platform_sync("12345678", "atcoder", "backfill", 100))
                self.assertEqual((await self.sql("SELECT last_status,last_success_at,cursor_timestamp FROM user_platform_sync_state WHERE user_qq_id='12345678' AND platform='atcoder'"))[0], ("backfill", 100, 0))
                await self.sql("UPDATE users SET atcoder_handle='Changed' WHERE qq_id='12345678'")
                self.assertFalse(await engine._mark_user_synced(users[0], 999))
                self.assertEqual((await self.sql("SELECT last_sync_timestamp FROM users WHERE qq_id='12345678'"))[0][0], 0)
            finally:
                await engine.close()

    async def test_old_task_does_not_display_running_for_a_new_binding(self):
        async with self.app.test_app():
            client = self.app.test_client()
            await self.account_login(client, role="member")
            await self.sql("UPDATE users SET cf_handle='New' WHERE qq_id='12345678'")
            self.app.config["PLUGIN_CONFIG"]["_task_provider"] = lambda: [{"qq_id": "12345678", "platform": "codeforces", "status": "running", "bindings": {"codeforces": {"account": "Old", "version": 0}}}]
            profile = await (await client.get("/api/me/profile")).get_json()
            status = next(item for item in profile["bindings"] if item["platform"] == "codeforces")
            self.assertEqual(status["sync_status"], "never")

    async def test_late_success_cannot_finish_or_mark_backfill_after_rebind(self):
        async with self.app.test_app():
            client = self.app.test_client()
            await self.account_login(client, role="member")
            engine = SyncEngine(self.db_path, {})
            await engine.start()
            try:
                for days in (0, 7):
                    with self.subTest(days=days):
                        await self.sql("UPDATE users SET atcoder_handle='Original' WHERE qq_id='12345678'")
                        async def late_fetch(*args):
                            await self.sql("UPDATE users SET atcoder_handle='Replacement' WHERE qq_id='12345678'")
                            return 0
                        with patch.object(engine, "_fetch_platform_with_limit", late_fetch):
                            result = await engine.sync_single_platform_for_days("12345678", "atcoder", days)
                        self.assertEqual(result, -4)
                        self.assertFalse(await self.sql("SELECT * FROM user_platform_sync_state WHERE platform='atcoder'"))
            finally:
                await engine.close()

    async def test_queued_task_expected_generation_rejects_aba_without_fetch(self):
        async with self.app.test_app():
            client = self.app.test_client()
            await self.account_login(client, role="member")
            await self.sql("UPDATE users SET atcoder_handle='Original' WHERE qq_id='12345678'")
            engine = SyncEngine(self.db_path, {})
            await engine.start()
            try:
                await self.sql("UPDATE users SET atcoder_handle=NULL WHERE qq_id='12345678'")
                await self.sql("UPDATE users SET atcoder_handle='Original' WHERE qq_id='12345678'")
                with patch.object(engine, "_fetch_platform_with_limit", AsyncMock()) as fetch:
                    result = await engine.sync_single_platform_for_days("12345678", "atcoder", 0, expected_binding={"account": "Original", "version": 1})
                    self.assertEqual(result, -4)
                    fetch.assert_not_awaited()
            finally:
                await engine.close()
