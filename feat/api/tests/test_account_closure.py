"""Closure transactions against real temporary SQLite databases and cookies."""
import asyncio
import json
from pathlib import Path
import sqlite3
import threading
import tempfile
import time
import unittest
from unittest.mock import AsyncMock, patch

import test_api_contract as contract
from feat.api.acm_api import account_closure_service as service
from feat.api.acm_api.auth_service import hash_password, password_hash_usable
from feat.api.acm_api.cf_practice_jobs import open_db
from feat.api.acm_api.account_closure_cleanup import ClosureCleanup, UnsafeResource, remove_resource
from feat.api.acm_api.account_lifecycle_service import AccountLifecycleError

QQ = "12345678"
OTHER = "87654321"
PASSWORD = "Test-Password-123!"


class ClosureTests(unittest.IsolatedAsyncioTestCase):
    account_login = contract.ApiContractTests.account_login

    async def asyncSetUp(self):
        await contract.ApiContractTests.asyncSetUp(self)
        self.app.config["ACCOUNT_CLOSURE_ENABLED"] = True
        self.context = self.app.test_app()
        await self.context.__aenter__()
        # Deterministic outbox tests explicitly drive the real worker.
        await self.app.extensions["account_closure_cleanup"].close()
        self.client = self.app.test_client()
        self.headers = await self.account_login(self.client, role="member")

    async def asyncTearDown(self):
        await self.context.__aexit__(None, None, None)
        await contract.ApiContractTests.asyncTearDown(self)

    async def sql(self, query, args=()):
        db = await open_db(self.db_path)
        try:
            async with db.execute(query, args) as cursor:
                result = [dict(row) for row in await cursor.fetchall()]
            await db.commit()
            return result
        finally:
            await db.close()

    async def other_user(self, *, role="member"):
        await self.sql("INSERT INTO users(qq_id,name,cf_handle) VALUES(?, 'Other member', 'OtherHandle')", (OTHER,))
        await self.sql("INSERT INTO web_accounts(qq_id,password_hash,role,must_change_password,is_active,created_at,updated_at) VALUES(?,?,?,0,1,1,1)", (OTHER, hash_password(PASSWORD), role))

    async def preview(self, client=None):
        response = await (client or self.client).get("/api/me/account-closure/preview")
        self.assertEqual(response.status_code, 200, await response.get_json())
        return await response.get_json()

    def body(self, preview, **changes):
        return {"current_password": PASSWORD, "confirm_text": "注销账号", "policy_version": preview["policy_version"], "expected_account_epoch": preview["account_epoch"], **changes}

    async def close(self, preview, *, client=None, headers=None, **changes):
        return await (client or self.client).post("/api/me/account-closure", json=self.body(preview, **changes), headers={**(self.headers if headers is None else headers), "Idempotency-Key": preview["request_id"], "X-Closure-Receipt": preview["receipt_token"]})

    async def admin_session(self):
        if not await self.sql("SELECT 1 FROM users WHERE qq_id=?", (OTHER,)):
            await self.other_user(role="root")
        else:
            await self.sql("UPDATE web_accounts SET role='root' WHERE qq_id=?", (OTHER,))
        client = self.app.test_client()
        response = await client.post("/api/auth/login", json={"qq_id": OTHER, "password": PASSWORD})
        self.assertEqual(response.status_code, 200)
        return client, {"X-CSRF-Token": (await response.get_json())["csrf_token"]}

    async def new_account(self, *, change_password=True):
        admin, headers = await self.admin_session()
        response = await admin.post("/api/admin/web-accounts", json={
            "qq_id": QQ, "name": "Fresh member", "initial_password": "Fresh-Password-83!",
        }, headers=headers)
        self.assertEqual(response.status_code, 201, await response.get_json())
        self.assertTrue((await response.get_json())["new_generation"])
        client = self.app.test_client()
        login = await client.post("/api/auth/login", json={"qq_id": QQ, "password": "Fresh-Password-83!"})
        self.assertEqual(login.status_code, 200, await login.get_json())
        auth_headers = {"X-CSRF-Token": (await login.get_json())["csrf_token"]}
        if change_password:
            changed = await client.post("/api/auth/change-password", json={
                "old_password": "Fresh-Password-83!", "new_password": PASSWORD,
            }, headers=auth_headers)
            self.assertEqual(changed.status_code, 200, await changed.get_json())
        return client, auth_headers

    async def assert_active(self):
        user = (await self.sql("SELECT account_state,account_epoch FROM users WHERE qq_id=?", (QQ,)))[0]
        self.assertEqual(user, {"account_state": "active", "account_epoch": 1})

    async def test_closed_qq_can_create_fresh_account_with_monotonic_versions(self):
        await self.sql("UPDATE users SET real_name='Old name',cf_handle='OldHandle',school='Old school' WHERE qq_id=?", (QQ,))
        await self.sql("INSERT INTO submissions(user_qq_id,platform,problem_id,submit_time) VALUES(?,'codeforces','1A',1)", (QQ,))
        preview = await self.preview()
        self.assertTrue(preview["retention_notice"]["qq_reuse_supported"])
        self.assertTrue(preview["retention_notice"]["reopen_supported"])
        self.assertEqual(preview["policy_version"], "closure-v2")
        self.assertEqual((await self.close(preview)).status_code, 200)
        versions = (await self.sql("SELECT cf_binding_version FROM users WHERE qq_id=?", (QQ,)))[0]
        client, headers = await self.new_account(change_password=False)
        account = (await self.sql("SELECT * FROM web_accounts WHERE qq_id=?", (QQ,)))[0]
        self.assertEqual((account["role"], account["is_active"], account["must_change_password"], account["credential_version"]), ("member", 1, 1, 3))
        user = (await self.sql("SELECT * FROM users WHERE qq_id=?", (QQ,)))[0]
        self.assertEqual((user["account_state"], user["account_epoch"], user["closed_at"], user["name"]), ("active", 3, None, "Fresh member"))
        self.assertEqual(user["cf_binding_version"], versions["cf_binding_version"])
        for field in ("real_name", "avatar_url", "cf_handle", "luogu_id", "school"):
            self.assertIsNone(user[field], field)
        self.assertEqual(await self.sql("SELECT * FROM submissions WHERE user_qq_id=?", (QQ,)), [])
        me = await (await client.get("/api/auth/me")).get_json()
        self.assertEqual(me["account_epoch"], 3)
        self.assertEqual((await client.get("/api/me/profile")).status_code, 428)
        self.assertEqual((await client.get("/api/admin/web-accounts")).status_code, 428)
        anon = self.app.test_client()
        self.assertEqual((await anon.post("/api/auth/login", json={"qq_id": QQ, "password": PASSWORD})).status_code, 401)

    async def test_re_registration_needs_a_new_name_and_keeps_active_duplicate_protected(self):
        self.assertEqual((await self.close(await self.preview())).status_code, 200)
        admin, headers = await self.admin_session()
        missing = await admin.post("/api/admin/web-accounts", json={"qq_id": QQ, "initial_password": PASSWORD}, headers=headers)
        self.assertEqual(missing.status_code, 400)
        self.assertEqual((await self.sql("SELECT account_state FROM users WHERE qq_id=?", (QQ,)))[0]["account_state"], "closed")
        self.assertEqual(await self.sql("SELECT * FROM account_registrations"), [])
        await self.new_account()
        before = await self.sql("SELECT * FROM web_accounts WHERE qq_id=?", (QQ,))
        duplicate = await admin.post("/api/admin/web-accounts", json={"qq_id": QQ, "name": "Overwrite", "initial_password": PASSWORD}, headers=headers)
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(await self.sql("SELECT * FROM web_accounts WHERE qq_id=?", (QQ,)), before)

    async def test_old_session_and_old_receipt_cannot_affect_new_account(self):
        stale = self.app.test_client()
        login = await stale.post("/api/auth/login", json={"qq_id": QQ, "password": PASSWORD})
        stale_headers = {"X-CSRF-Token": (await login.get_json())["csrf_token"]}
        preview = await self.preview()
        self.assertEqual((await self.close(preview)).status_code, 200)
        client, headers = await self.new_account()
        self.assertEqual((await stale.put("/api/me/profile", json={"name": "Old session"}, headers=stale_headers)).status_code, 401)
        replay = await self.close(preview, client=client, headers=headers)
        self.assertEqual(replay.status_code, 200, await replay.get_json())
        self.assertTrue((await (await client.get("/api/auth/me")).get_json())["authenticated"])
        self.assertEqual((await client.get("/api/me/profile")).status_code, 200)
        self.assertEqual((await self.sql("SELECT account_epoch,name FROM users WHERE qq_id=?", (QQ,)))[0], {"account_epoch": 3, "name": "Fresh member"})

    async def test_committed_v1_receipt_still_replays_after_policy_upgrade(self):
        preview = await self.preview()
        self.assertEqual((await self.close(preview)).status_code, 200)
        legacy = {**preview, "policy_version": "closure-v1"}
        await self.sql("UPDATE account_closure_requests SET policy_version=?,intent_fingerprint=? WHERE request_id=?", ("closure-v1", service.intent(self.body(legacy)), preview["request_id"]))
        client, headers = await self.new_account()
        self.app.config["ACCOUNT_CLOSURE_ENABLED"] = False
        replay = await self.close(legacy, client=client, headers=headers)
        self.assertEqual(replay.status_code, 200, await replay.get_json())
        self.assertEqual((await replay.get_json())["policy_version"], "closure-v1")
        self.assertTrue((await (await client.get("/api/auth/me")).get_json())["authenticated"])
        result = await client.get("/api/account-closures/" + preview["request_id"], headers={"X-Closure-Receipt": preview["receipt_token"]})
        self.assertEqual((await result.get_json())["status"], "closed")

    async def test_shared_old_content_stays_anonymous_and_is_not_owned_by_new_account(self):
        post = await self.seed_post()
        await self.seed_wiki()
        await self.sql("INSERT INTO forum_comments(post_id,author_qq_id,body,created_at) VALUES(?,?,'Old comment',1)", (post, QQ))
        await self.sql("INSERT INTO forum_reports(post_id,reporter_qq_id,reason,created_at) VALUES(?,?,'Old report',1)", (post, QQ))
        self.assertEqual((await self.close(await self.preview())).status_code, 200)
        client, headers = await self.new_account()
        public = await (await client.get(f"/api/forum/posts/{post}")).get_json()
        self.assertEqual(public["author_name"], "已注销用户")
        self.assertTrue(public["author_closed"])
        self.assertFalse(public["viewer_is_author"])
        self.assertEqual(public["comments"][0]["author_name"], "已注销用户")
        listing = await (await client.get("/api/forum/posts")).get_json()
        self.assertEqual(listing["rows"][0]["author_name"], "已注销用户")
        wiki = await (await client.get("/api/wiki/pages/closure-test")).get_json()
        self.assertEqual(wiki["maintainer"], "已注销用户")
        self.assertTrue(wiki["author_closed"])
        self.assertEqual((await self.sql("SELECT author FROM wiki_revisions"))[0]["author"], QQ)
        self.assertEqual(await (await client.get("/api/forum/mine/posts")).get_json(), [])
        self.assertEqual((await client.get(f"/api/forum/mine/posts/{post}")).status_code, 404)
        self.assertEqual((await client.post(f"/api/forum/mine/posts/{post}/edit", json={}, headers=headers)).status_code, 404)
        self.assertEqual((await client.delete(f"/api/forum/posts/{post}", headers=headers)).status_code, 403)
        admin, admin_headers = await self.admin_session()
        reports = await (await admin.get("/api/forum/moderation/reports")).get_json()
        self.assertEqual(reports[0]["reporter_name"], "已注销用户")
        # New posts do belong to the new account and use its new display name.
        new_post = await self.seed_post(title="New generation post")
        new_public = await (await client.get(f"/api/forum/posts/{new_post}")).get_json()
        self.assertEqual(new_public["author_name"], "Fresh member")
        self.assertTrue(new_public["viewer_is_author"])
        self.assertEqual((await client.post(f"/api/forum/mine/posts/{new_post}/edit", json={}, headers=headers)).status_code, 201)

    async def test_replies_to_old_content_do_not_notify_re_registered_qq(self):
        post = await self.seed_post()
        comment = (await self.sql("INSERT INTO forum_comments(post_id,author_qq_id,body,created_at) VALUES(?,?,'Old comment',1) RETURNING id", (post, QQ)))[0]["id"]
        self.assertEqual((await self.close(await self.preview())).status_code, 200)
        client, headers = await self.new_account()
        admin, admin_headers = await self.admin_session()
        response = await admin.post(f"/api/forum/posts/{post}/comments", json={"body": "Reply after registration", "parent_id": comment}, headers=admin_headers)
        self.assertEqual(response.status_code, 201, await response.get_json())
        self.assertEqual(await self.sql("SELECT * FROM forum_notifications WHERE recipient_qq_id=?", (QQ,)), [])
        new_post = await self.seed_post(title="Fresh content")
        self.assertEqual((await admin.post(f"/api/forum/posts/{new_post}/comments", json={"body": "New author notification"}, headers=admin_headers)).status_code, 201)
        self.assertEqual(len(await self.sql("SELECT * FROM forum_notifications WHERE recipient_qq_id=?", (QQ,))), 1)

    async def test_repeated_close_and_registration_keep_generations_and_plans_separate(self):
        old = await self.seed_post()
        await self.seed_wiki()
        self.assertEqual((await self.close(await self.preview())).status_code, 200)
        client, headers = await self.new_account()
        new = await self.seed_post(title="Second generation")
        preview = await self.preview(client)
        self.assertEqual(preview["retain_counts"], {"posts": 1, "comments": 0, "wiki_revisions": 0, "public_resources": 0})
        self.assertEqual((await self.close(preview, client=client, headers=headers)).status_code, 200)
        client, _ = await self.new_account()
        self.assertEqual((await self.sql("SELECT account_epoch FROM users WHERE qq_id=?", (QQ,)))[0]["account_epoch"], 5)
        self.assertEqual(await self.sql("SELECT closed_epoch,new_epoch FROM account_registrations ORDER BY closed_epoch"), [{"closed_epoch": 2, "new_epoch": 3}, {"closed_epoch": 4, "new_epoch": 5}])
        for post in (old, new):
            public = await (await client.get(f"/api/forum/posts/{post}")).get_json()
            self.assertEqual(public["author_name"], "已注销用户")
            self.assertFalse(public["viewer_is_author"])

    async def test_concurrent_registration_creates_only_one_new_generation(self):
        self.assertEqual((await self.close(await self.preview())).status_code, 200)
        admin, headers = await self.admin_session()
        body = {"qq_id": QQ, "name": "New account", "initial_password": PASSWORD}
        results = await asyncio.gather(*[admin.post("/api/admin/web-accounts", json=body, headers=headers) for _ in range(2)])
        self.assertEqual(sorted(r.status_code for r in results), [201, 409])
        self.assertEqual(len(await self.sql("SELECT * FROM account_registrations")), 1)
        self.assertEqual((await self.sql("SELECT account_epoch FROM users WHERE qq_id=?", (QQ,)))[0]["account_epoch"], 3)

    async def test_failed_registration_rolls_back_generation_and_credentials(self):
        self.assertEqual((await self.close(await self.preview())).status_code, 200)
        admin, headers = await self.admin_session()
        before = await self.sql("SELECT * FROM web_accounts WHERE qq_id=?", (QQ,))
        await self.sql("CREATE TRIGGER fail_registration BEFORE UPDATE ON web_accounts WHEN NEW.qq_id='12345678' AND NEW.is_active=1 BEGIN SELECT RAISE(ABORT,'synthetic registration failure'); END")
        response = await admin.post("/api/admin/web-accounts", json={"qq_id": QQ, "name": "New", "initial_password": PASSWORD}, headers=headers)
        self.assertEqual(response.status_code, 409)
        self.assertEqual((await self.sql("SELECT account_state FROM users WHERE qq_id=?", (QQ,)))[0]["account_state"], "closed")
        self.assertEqual(await self.sql("SELECT * FROM web_accounts WHERE qq_id=?", (QQ,)), before)
        self.assertEqual(await self.sql("SELECT * FROM account_registrations"), [])

    async def test_old_sync_task_and_cf_member_cannot_reacquire_re_registered_qq(self):
        await self.seed_jobs()
        from feat.api.service_runtime import WebTaskManager
        manager = WebTaskManager(self.app.sync_engine)
        started, release = asyncio.Event(), asyncio.Event()
        original = self.app.sync_engine.sync_account
        async def paused(*args, **kwargs):
            started.set()
            await release.wait()
            return await original(*args, **kwargs)
        with patch.object(self.app.sync_engine, "sync_account", side_effect=paused), patch.object(self.app.sync_engine, "sync_single_platform_for_days", new=AsyncMock()) as fetch:
            task = await manager.submit_account_sync(QQ, ["codeforces"])
            await started.wait()
            try:
                self.assertEqual((await self.close(await self.preview())).status_code, 200)
                await self.new_account()
                public = await manager.public_snapshots()
                self.assertIsNone(public[0]["qq_id"])
                self.assertNotIn("SecretHandle", json.dumps(public))
                await self.sql("UPDATE users SET cf_handle='SecretHandle' WHERE qq_id=?", (QQ,))
            finally:
                release.set()
            await manager.tasks[task["id"]]["_task"]
            fetch.assert_not_awaited()
        self.assertEqual(manager.tasks[task["id"]]["status"], "cancelled")
        jobs = self.app.config["CF_PRACTICE_JOBS"]
        self.assertFalse(await jobs._member_update("sync-job", QQ, "completed"))
        public = await jobs.get("sync-job")
        self.assertFalse(any(member["qq_id"] == QQ for member in public["members"]))

    async def test_v1_tombstone_is_backfilled_and_old_private_post_assets_are_not_owned(self):
        post = await self.seed_post()
        await self.seed_wiki()
        image, asset = "a" * 32, "b" * 32
        await self.sql("INSERT INTO forum_images VALUES(?,?,1,1,10,1)", (image, QQ))
        await self.sql("INSERT INTO forum_image_links(image_id,post_id) VALUES(?,?)", (image, post))
        await self.sql("INSERT INTO markdown_assets VALUES(?,?,'image/png',10,1,1,?,'forum_draft',1,1)", (asset, asset + ".png", QQ))
        await self.sql("INSERT INTO markdown_asset_references VALUES(?,'forum_post',?,0)", (asset, post))
        self.assertEqual((await self.close(await self.preview())).status_code, 200)
        # Simulate a v1 database whose content ledger did not exist at closure.
        await self.sql("DELETE FROM account_closed_content")
        client, headers = await self.new_account()
        self.assertTrue((await (await client.get("/api/wiki/pages/closure-test")).get_json())["author_closed"])
        admin, admin_headers = await self.admin_session()
        self.assertEqual((await admin.delete(f"/api/forum/posts/{post}", headers=admin_headers)).status_code, 200)
        for path in ("/api/forum/images/" + image, "/api/markdown/assets/" + asset):
            self.assertEqual((await client.get(path)).status_code, 404)
        from feat.api.acm_api.forum_images import sync_image_links
        from feat.api.acm_api.markdown_content import record_assets, ContentError
        db = await open_db(self.db_path)
        try:
            async with self.app.test_request_context("/"):
                with self.assertRaises(ValueError):
                    await sync_image_links(db, QQ, "![image](/api/forum/images/" + image + ")", None, post_id=post)
            with self.assertRaises(ContentError):
                await record_assets(db, "![asset](/api/markdown/assets/" + asset + ")", "forum_draft", 1, 0, QQ)
        finally:
            await db.close()

    async def test_all_account_sync_captures_generations_before_queue_execution(self):
        from feat.api.service_runtime import WebTaskManager
        await self.sql("UPDATE users SET cf_handle='SameHandle' WHERE qq_id=?", (QQ,))
        manager = WebTaskManager(self.app.sync_engine)
        started, release = asyncio.Event(), asyncio.Event()
        original = self.app.sync_engine.sync_all_accounts
        async def paused(*args, **kwargs):
            started.set()
            await release.wait()
            return await original(*args, **kwargs)
        with patch.object(self.app.sync_engine, "sync_all_accounts", side_effect=paused), patch.object(self.app.sync_engine, "_fetch_platform_with_limit", new=AsyncMock(return_value=0)) as fetch:
            task = await manager.submit_all_accounts_sync()
            await started.wait()
            try:
                self.assertEqual((await self.close(await self.preview())).status_code, 200)
                await self.new_account()
                await self.sql("UPDATE users SET cf_handle='SameHandle' WHERE qq_id=?", (QQ,))
            finally:
                release.set()
            await manager.tasks[task["id"]]["_task"]
            fetch.assert_not_awaited()
        public = await manager.public_snapshots()
        self.assertNotIn(QQ, json.dumps(public))

    async def test_active_upsert_preserves_new_generation_but_replace_cannot_reset_it(self):
        self.assertEqual((await self.close(await self.preview())).status_code, 200)
        await self.new_account()
        await self.sql("INSERT INTO users(qq_id,name) VALUES(?,'Updated fresh member') ON CONFLICT(qq_id) DO UPDATE SET name=excluded.name", (QQ,))
        before = await self.sql("SELECT * FROM web_accounts WHERE qq_id=?", (QQ,))
        with self.assertRaises(sqlite3.IntegrityError):
            await self.sql("INSERT OR REPLACE INTO users(qq_id,name) VALUES(?,'Old generation')", (QQ,))
        self.assertEqual((await self.sql("SELECT account_epoch,name FROM users WHERE qq_id=?", (QQ,)))[0], {"account_epoch": 3, "name": "Updated fresh member"})
        self.assertEqual(await self.sql("SELECT * FROM web_accounts WHERE qq_id=?", (QQ,)), before)

    async def test_concurrent_all_sync_submissions_reserve_one_snapshot(self):
        from feat.api.service_runtime import WebTaskManager
        manager = WebTaskManager(self.app.sync_engine)
        release = asyncio.Event()
        async def paused(*args, **kwargs):
            await release.wait()
        try:
            with patch.object(self.app.sync_engine, "sync_all_accounts", side_effect=paused):
                results = await asyncio.gather(manager.submit_all_accounts_sync(), manager.submit_all_accounts_sync())
                self.assertEqual(sum(result is not None for result in results), 1)
                self.assertEqual(len(manager.tasks), 1)
        finally:
            release.set()
            await manager.close()

    async def test_intake_off_by_default_does_not_create_intents(self):
        self.app.config["ACCOUNT_CLOSURE_ENABLED"] = False
        self.assertEqual((await self.client.get("/api/me/account-closure/preview")).status_code, 404)
        self.assertEqual((await self.client.post("/api/me/account-closure", json={})).status_code, 404)
        self.assertEqual(await self.sql("SELECT * FROM account_closure_requests"), [])
        me = await (await self.client.get("/api/auth/me")).get_json()
        self.assertFalse(me["account_closure_enabled"])

    async def test_success_revokes_login_and_preserves_only_tombstone_credentials(self):
        await self.sql("UPDATE users SET real_name='Secret name',school='Secret school',cf_handle='SecretHandle',avatar_url='/uploads/avatars/" + "a" * 32 + ".png' WHERE qq_id=?", (QQ,))
        preview = await self.preview()
        response = await self.close(preview)
        self.assertEqual(response.status_code, 200, await response.get_json())
        self.assertEqual((await response.get_json())["status"], "closed")
        user = (await self.sql("SELECT * FROM users WHERE qq_id=?", (QQ,)))[0]
        self.assertEqual((user["account_state"], user["account_epoch"], user["name"]), ("closed", 2, "已注销用户"))
        for field in ("real_name", "school", "status", "avatar_url", "cf_handle", "luogu_id", "nowcoder_id", "atcoder_handle", "cjlu_username"):
            self.assertIsNone(user[field], field)
        for field in ("cf", "luogu", "nowcoder", "atcoder", "cjlu"):
            self.assertGreaterEqual(user[field + "_binding_version"], 1)
        account = (await self.sql("SELECT * FROM web_accounts WHERE qq_id=?", (QQ,)))[0]
        self.assertEqual((account["is_active"], account["credential_version"], account["role"]), (0, 2, "member"))
        self.assertFalse(password_hash_usable(account["password_hash"]))
        self.assertFalse((await (await self.client.get("/api/auth/me")).get_json())["authenticated"])
        self.assertEqual((await self.client.post("/api/auth/login", json={"qq_id": QQ, "password": PASSWORD})).status_code, 401)
        audit = await self.sql("SELECT result_code FROM account_lifecycle_audit")
        self.assertEqual(audit, [{"result_code": "CLOSED"}])

    async def test_preview_and_execution_use_same_private_rules_and_preserve_other_user(self):
        await self.other_user()
        fixtures = [
            ("submissions", "user_qq_id,platform,problem_id,submit_time", "?,'codeforces','1A',1"),
            ("submission_attempts", "owner_qq_id,platform,problem_id,submitted_at,created_at,source_code", "?,'codeforces','1A',1,1,'private source'"),
            ("user_problem_state", "owner_qq_id,platform,problem_id,updated_at", "?,'codeforces','1A',1"),
            ("review_states", "owner_qq_id,platform,problem_id", "?,'codeforces','1A'"),
            ("contest_problem_reviews", "owner_qq_id,contest_id,problem_id,updated_at", "?,'1','1A',1"),
            ("study_plan_items", "owner_qq_id,platform,problem_id,added_at", "?,'codeforces','1A',1"),
            ("workspace_items", "owner_qq_id,kind,title,created_at,updated_at", "?,'note','Private',1,1"),
            ("review_drafts", "owner_qq_id,context_type,context_id,created_at,updated_at", "?,'problem','1A',1,1"),
            ("random_challenges", "qq_id,platform,problem_id,problem_url,challenge_rating,time_limit_minutes,created_at,expires_at", "?,'codeforces','1A','https://example.test',800,60,1,2"),
            ("notification_preferences", "qq_id", "?"),
        ]
        for table, columns, values in fixtures:
            for owner in (QQ, OTHER):
                await self.sql(f"INSERT INTO {table}({columns}) VALUES({values})", (owner,))
        preview = await self.preview()
        for table, _, _ in fixtures:
            self.assertEqual(preview["delete_counts"][table], 1, table)
        self.assertEqual((await self.close(preview)).status_code, 200)
        for table, _, _ in fixtures:
            owner = service.PRIVATE_TABLES[table]
            self.assertEqual(await self.sql(f"SELECT {owner} owner FROM {table}"), [{"owner": OTHER}], table)

    async def test_no_target_or_unknown_fields_can_redirect_closure(self):
        preview = await self.preview()
        for key in ("qq_id", "owner_qq_id", "target_qq_id", "unknown"):
            response = await self.close(preview, **{key: OTHER})
            self.assertEqual(response.status_code, 400)
        self.assertEqual((await self.client.get("/api/me/account-closure/preview?qq_id=" + OTHER)).status_code, 400)
        await self.assert_active()

    async def test_fixed_confirmation_policy_and_epoch_are_required(self):
        preview = await self.preview()
        for changes, code in [({"confirm_text": "注销"}, "INVALID_CONFIRMATION"), ({"policy_version": "old"}, "POLICY_CHANGED"), ({"expected_account_epoch": True}, "INVALID_REQUEST"), ({"expected_account_epoch": 2}, "IDEMPOTENCY_CONFLICT")]:
            response = await self.close(preview, **changes)
            self.assertEqual((await response.get_json())["code"], code)
        await self.assert_active()

    async def test_csrf_and_password_are_independent_of_preview_secret(self):
        preview = await self.preview()
        self.assertEqual((await self.close(preview, headers={})).status_code, 403)
        response = await self.close(preview, current_password="wrong")
        self.assertEqual((await response.get_json())["code"], "REAUTH_FAILED")
        anon = self.app.test_client()
        response = await self.close(preview, client=anon, headers={})
        self.assertEqual(response.status_code, 401)
        await self.assert_active()
        snapshot = json.dumps(await self.sql("SELECT * FROM account_closure_requests"))
        self.assertNotIn(preview["receipt_token"], snapshot)
        self.assertNotIn("wrong", snapshot)
        self.assertNotIn(PASSWORD, snapshot)

    async def test_password_whitespace_is_not_trimmed(self):
        await self.sql("UPDATE web_accounts SET password_hash=? WHERE qq_id=?", (hash_password(" " + PASSWORD + " "), QQ))
        preview = await self.preview()
        self.assertEqual((await self.close(preview)).status_code, 403)
        self.assertEqual((await self.close(preview, current_password=" " + PASSWORD + " ")).status_code, 200)

    async def test_reauthentication_budget_is_shared_between_connections(self):
        preview = await self.preview()
        for _ in range(5):
            self.assertEqual((await self.close(preview, current_password="wrong")).status_code, 403)
        response = await self.close(preview, current_password=PASSWORD)
        self.assertEqual(response.status_code, 429)
        self.assertEqual((await response.get_json())["code"], "RATE_LIMITED")
        stored = json.dumps(await self.sql("SELECT * FROM account_sensitive_action_limits"))
        self.assertNotIn(QQ, stored)
        self.assertNotIn("127.0.0.1", stored)
        await self.assert_active()

    async def test_admin_and_last_root_require_handover(self):
        for role, code in [("admin", "ROLE_HANDOVER_REQUIRED"), ("root", "LAST_ROOT_PROTECTED")]:
            await self.sql("UPDATE web_accounts SET role=? WHERE qq_id=?", (role, QQ))
            preview = await self.preview()
            self.assertFalse(preview["can_close"])
            self.assertEqual((await (await self.close(preview)).get_json())["code"], code)
        await self.other_user(role="root")
        preview = await self.preview()
        self.assertEqual(preview["blockers"][0]["code"], "ROLE_HANDOVER_REQUIRED")
        await self.assert_active()

    async def test_forced_password_change_is_a_blocker(self):
        await self.sql("UPDATE web_accounts SET must_change_password=1 WHERE qq_id=?", (QQ,))
        preview = await self.preview()
        self.assertFalse(preview["can_close"])
        response = await self.close(preview)
        self.assertEqual((await response.get_json())["code"], "MUST_CHANGE_PASSWORD")

    async def test_committed_replay_and_receipt_do_not_require_a_live_session(self):
        preview = await self.preview()
        first = await self.close(preview)
        self.assertEqual(first.status_code, 200)
        self.app.config["ACCOUNT_CLOSURE_ENABLED"] = False
        anon = self.app.test_client()
        replay = await self.close(preview, client=anon, headers={}, current_password="not retained")
        self.assertEqual(await first.get_json(), await replay.get_json())
        receipt = await anon.get("/api/account-closures/" + preview["request_id"], headers={"X-Closure-Receipt": preview["receipt_token"]})
        self.assertEqual(await receipt.get_json(), await first.get_json())
        self.assertNotIn(QQ, await receipt.get_data(as_text=True))
        self.assertEqual(len(await self.sql("SELECT * FROM account_lifecycle_audit WHERE result_code='CLOSED'")), 1)
        conflict = await self.close(preview, client=anon, headers={}, expected_account_epoch=2)
        self.assertEqual(conflict.status_code, 409)

    async def test_invalid_and_expired_receipts_are_indistinguishable(self):
        preview = await self.preview()
        path = "/api/account-closures/" + preview["request_id"]
        invalid = await self.client.get(path, headers={"X-Closure-Receipt": "x" * 43})
        await self.sql("UPDATE account_closure_requests SET receipt_expires_at=1")
        expired = await self.client.get(path, headers={"X-Closure-Receipt": preview["receipt_token"]})
        self.assertEqual(invalid.status_code, 404)
        self.assertEqual(await invalid.get_json(), await expired.get_json())
        self.assertEqual((await self.client.get(path + "?qq_id=" + QQ)).status_code, 400)

    async def test_same_request_concurrent_replay_commits_once(self):
        preview = await self.preview()
        responses = await asyncio.gather(self.close(preview), self.close(preview))
        self.assertEqual([r.status_code for r in responses], [200, 200])
        self.assertEqual(len(await self.sql("SELECT * FROM account_lifecycle_audit WHERE result_code='CLOSED'")), 1)
        self.assertEqual((await self.sql("SELECT account_epoch FROM users WHERE qq_id=?", (QQ,)))[0]["account_epoch"], 2)

    async def test_distinct_requests_for_same_account_cannot_commit_twice(self):
        first, second = await self.preview(), await self.preview()
        responses = await asyncio.gather(self.close(first), self.close(second))
        self.assertEqual(sum(r.status_code == 200 for r in responses), 1)
        self.assertEqual(len(await self.sql("SELECT * FROM account_lifecycle_audit WHERE result_code='CLOSED'")), 1)

    async def test_storage_failure_rolls_back_all_account_and_data_changes(self):
        await self.sql("INSERT INTO submissions(user_qq_id,platform,problem_id,submit_time) VALUES(?,'codeforces','1A',1)", (QQ,))
        preview = await self.preview()
        original = service.audit
        async def fail_success(db, subject, result, **kwargs):
            if result == "CLOSED":
                raise sqlite3.OperationalError("synthetic failure")
            return await original(db, subject, result, **kwargs)
        with patch.object(service, "audit", side_effect=fail_success):
            response = await self.close(preview)
        self.assertEqual(response.status_code, 503)
        await self.assert_active()
        self.assertEqual(len(await self.sql("SELECT * FROM submissions")), 1)
        self.assertIsNone((await self.sql("SELECT committed_at FROM account_closure_requests"))[0]["committed_at"])
        self.assertEqual((await self.sql("SELECT result_code FROM account_lifecycle_audit"))[0]["result_code"], "STORAGE_UNAVAILABLE")

    async def test_password_change_during_hash_verification_invalidates_final_write(self):
        preview = await self.preview()
        loop, started, release = asyncio.get_running_loop(), asyncio.Event(), threading.Event()
        def slow_verify(*_):
            loop.call_soon_threadsafe(started.set)
            release.wait(5)
            return True
        with patch("feat.api.acm_api.account_closure_api.verify_password", side_effect=slow_verify):
            task = asyncio.create_task(self.close(preview))
            await asyncio.wait_for(started.wait(), 5)
            try:
                await self.sql("UPDATE web_accounts SET credential_version=credential_version+1 WHERE qq_id=?", (QQ,))
            finally:
                release.set()
            response = await task
        self.assertIn(response.status_code, (401, 409))
        await self.assert_active()

    async def seed_post(self, status="published", title="Public post"):
        return (await self.sql("INSERT INTO forum_posts(author_qq_id,category_id,title,body,status,created_at,updated_at) VALUES(?,1,?,'Public body',?,1,1) RETURNING id", (QQ, title, status)))[0]["id"]

    async def test_unpublished_edit_attachment_is_cleaned_while_public_history_image_stays(self):
        post = await self.seed_post("pending", "New private revision")
        public_id, private_id = "e" * 32, "f" * 32
        for asset_id in (public_id, private_id):
            await self.sql("INSERT INTO forum_images VALUES(?,?,1,1,10,1)", (asset_id, QQ))
        await self.sql("INSERT INTO forum_post_history(post_id,content_version,title,body,category_id,status,review_reason,saved_at) VALUES(?,1,'Public history',?,1,'published','',1)", (post, "![public](/api/forum/images/" + public_id + ")"))
        await self.sql("INSERT INTO forum_image_links(image_id,post_id) VALUES(?,?)", (private_id, post))
        self.assertEqual((await self.close(await self.preview())).status_code, 200)
        remaining = await self.sql("SELECT id FROM forum_images ORDER BY id")
        self.assertEqual(remaining, [{"id": public_id}])

    async def test_public_post_comment_and_notification_survive_anonymously(self):
        await self.other_user()
        post = await self.seed_post()
        comment = (await self.sql("INSERT INTO forum_comments(post_id,author_qq_id,body,created_at) VALUES(?,?,'Public comment',1) RETURNING id", (post, QQ)))[0]["id"]
        await self.sql("INSERT INTO forum_notifications(recipient_qq_id,actor_qq_id,kind,post_id,comment_id,created_at) VALUES(?,?,'comment',?,?,1)", (OTHER, QQ, post, comment))
        await self.sql("INSERT INTO forum_bookmarks VALUES(?,?,1)", (post, QQ))
        await self.sql("INSERT INTO forum_post_likes VALUES(?,?,1)", (post, QQ))
        self.assertEqual((await self.close(await self.preview())).status_code, 200)
        anon = self.app.test_client()
        public = await (await anon.get("/api/forum/posts/" + str(post))).get_json()
        self.assertEqual(public["author_name"], "已注销用户")
        self.assertTrue(public["author_closed"])
        self.assertIsNone(public["author_avatar_url"])
        self.assertNotIn(QQ, json.dumps(public))
        self.assertEqual((await self.sql("SELECT actor_qq_id FROM forum_notifications"))[0]["actor_qq_id"], None)
        self.assertEqual(await self.sql("SELECT * FROM forum_post_likes"), [])
        self.assertEqual(await self.sql("SELECT * FROM forum_bookmarks"), [])

    async def test_private_posts_drafts_and_history_are_removed_without_republishing(self):
        never_public = await self.seed_post("pending", "Secret pending")
        edited = await self.seed_post("pending", "Secret new edit")
        await self.sql("INSERT INTO forum_post_history(post_id,content_version,title,body,category_id,status,review_reason,saved_at) VALUES(?,1,'Previous public','Public version',1,'published','',1)", (edited,))
        await self.sql("INSERT INTO forum_post_history(post_id,content_version,title,body,category_id,status,review_reason,saved_at) VALUES(?,2,'Secret revision','Secret body',1,'rejected','',1)", (edited,))
        await self.sql("INSERT INTO forum_drafts(author_qq_id,category_id,title,body,created_at,updated_at,source_post_id) VALUES(?,1,'Secret draft','Secret body',1,1,?)", (QQ, never_public))
        self.assertEqual((await self.close(await self.preview())).status_code, 200)
        self.assertEqual(await self.sql("SELECT * FROM forum_drafts"), [])
        self.assertEqual(await self.sql("SELECT * FROM forum_posts WHERE id=?", (never_public,)), [])
        retained = (await self.sql("SELECT status,title,body FROM forum_posts WHERE id=?", (edited,)))[0]
        self.assertEqual(retained, {"status": "removed", "title": "Previous public", "body": "Public version"})
        self.assertEqual(len(await self.sql("SELECT * FROM forum_post_history")), 1)

    async def seed_wiki(self):
        await self.sql("INSERT INTO wiki_categories(id,name,name_key) VALUES(1,'Top','top')")
        await self.sql("INSERT INTO wiki_categories(id,parent_id,name,name_key) VALUES(2,1,'Child','child')")
        await self.sql("INSERT INTO wiki_pages(id,slug,category_id,created_at,updated_at) VALUES(1,'closure-test',2,1,1)")
        await self.sql("INSERT INTO wiki_revisions(id,page_id,title,body,metadata,author,created_at,published_at) VALUES(1,1,'Wiki title','Public wiki body',?, ?,1,1)", (json.dumps({"aliases": [], "tags": [], "summary": "", "exercises": []}), QQ))
        await self.sql("UPDATE wiki_pages SET published_revision_id=1,draft_revision_id=1 WHERE id=1")

    async def test_wiki_warm_caches_and_old_etag_are_invalidated_without_mutating_author(self):
        await self.seed_wiki()
        anon = self.app.test_client()
        old = await anon.get("/api/wiki/pages/closure-test")
        self.assertEqual(old.status_code, 200)
        await anon.get("/api/wiki/pages/closure-test")
        from feat.api.app import create_app
        other_worker = create_app().test_client()
        warm = await other_worker.get("/api/wiki/pages/closure-test")
        self.assertEqual(warm.status_code, 200)
        version = (await self.sql("SELECT public_content_version FROM wiki_settings"))[0]["public_content_version"]
        self.assertEqual((await self.close(await self.preview())).status_code, 200)
        updated = await anon.get("/api/wiki/pages/closure-test", headers={"If-None-Match": old.headers["ETag"]})
        self.assertEqual(updated.status_code, 200)
        self.assertEqual((await updated.get_json())["maintainer"], "已注销用户")
        self.assertTrue((await updated.get_json())["author_closed"])
        self.assertNotEqual(old.headers["ETag"], updated.headers["ETag"])
        other_response = await other_worker.get("/api/wiki/pages/closure-test", headers={"If-None-Match": warm.headers["ETag"]})
        self.assertEqual(other_response.status_code, 200)
        self.assertEqual((await other_response.get_json())["maintainer"], "已注销用户")
        self.assertGreater((await self.sql("SELECT public_content_version FROM wiki_settings"))[0]["public_content_version"], version)
        self.assertEqual((await self.sql("SELECT author FROM wiki_revisions"))[0]["author"], QQ)
        with self.assertRaises(sqlite3.IntegrityError):
            await self.sql("UPDATE wiki_revisions SET author='anonymous'")

    async def test_revoked_assets_deny_access_before_physical_cleanup(self):
        folder = self.app.config["FORUM_UPLOAD_DIR"]
        folder.mkdir(parents=True)
        for token in ("a" * 32, "b" * 32):
            (folder / (token + ".webp")).write_bytes(b"synthetic-image")
            await self.sql("INSERT INTO forum_images VALUES(?,?,1,1,15,1)", (token, QQ))
        post = await self.seed_post()
        await self.sql("INSERT INTO forum_image_links(image_id,post_id) VALUES(?,?)", ("b" * 32, post))
        preview = await self.preview()
        self.assertEqual(preview["retain_counts"]["public_resources"], 1)
        self.assertEqual((await self.close(preview)).status_code, 200)
        self.assertTrue((folder / ("a" * 32 + ".webp")).exists())
        self.assertEqual((await self.client.get("/api/forum/images/" + "a" * 32)).status_code, 404)
        self.assertEqual((await self.client.get("/api/forum/images/" + "b" * 32)).status_code, 200)
        worker = self.app.extensions["account_closure_cleanup"]
        while await worker.run_once():
            pass
        self.assertFalse((folder / ("a" * 32 + ".webp")).exists())
        self.assertTrue((folder / ("b" * 32 + ".webp")).exists())
        self.assertEqual((await self.sql("SELECT cleanup_state FROM account_closure_requests WHERE committed_at IS NOT NULL"))[0]["cleanup_state"], "completed")

    async def test_markdown_48_character_storage_names_are_revoked_and_cleaned(self):
        folder = self.app.config["MARKDOWN_UPLOAD_DIR"]
        folder.mkdir(parents=True)
        asset_id, name = "c" * 32, "d" * 48 + ".png"
        (folder / name).write_bytes(b"synthetic-image")
        await self.sql("INSERT INTO markdown_assets VALUES(?,?,'image/png',15,1,1,?,'forum_draft',1,1)", (asset_id, name, QQ))
        self.assertEqual((await self.close(await self.preview())).status_code, 200)
        self.assertEqual((await self.client.get("/api/markdown/assets/" + asset_id)).status_code, 404)
        self.assertTrue(await self.app.extensions["account_closure_cleanup"].run_once())
        self.assertFalse((folder / name).exists())
        from feat.api.acm_api.maintenance import diagnose
        self.assertTrue((await asyncio.to_thread(diagnose, self.db_path))["ok"])

    async def seed_jobs(self):
        await self.other_user()
        payload = json.dumps({"statuses": [], "exclude_qq_ids": [QQ], "note": "测试账号"})
        result = json.dumps({"by_member": {QQ: {"handle": "SecretHandle"}, OTHER: {"handle": "OtherHandle"}}, "members": [{"qq_id": QQ, "name": "测试账号", "cf_handle": "SecretHandle"}, {"qq_id": OTHER, "cf_handle": "OtherHandle"}]})
        await self.sql("UPDATE users SET cf_handle='SecretHandle' WHERE qq_id=?", (QQ,))
        for job_id, kind in [("sync-job", "sync"), ("check-job", "check")]:
            await self.sql("INSERT INTO cf_practice_jobs(id,kind,status,payload,scope_fingerprint,created_at,result,error_message) VALUES(?,?,'running',?,'scope',1,?,?)", (job_id, kind, payload, result, "failure for " + QQ + " SecretHandle"))
        for owner, handle in [(QQ, "SecretHandle"), (OTHER, "OtherHandle")]:
            await self.sql("INSERT INTO cf_practice_job_members(job_id,qq_id,handle,binding_key,status,account_epoch) VALUES('sync-job',?,?,?,'running',1)", (owner, handle, handle))

    async def test_cf_snapshots_redact_identities_and_late_updates_cannot_restore_them(self):
        await self.seed_jobs()
        self.assertEqual((await self.close(await self.preview())).status_code, 200)
        jobs = self.app.config["CF_PRACTICE_JOBS"]
        self.assertIn(OTHER, json.dumps(await self.sql("SELECT payload,result FROM cf_practice_jobs")))
        self.assertFalse(await jobs._member_update("sync-job", QQ, "completed"))
        self.assertTrue(await jobs._member_update("sync-job", OTHER, "completed"))
        await jobs._update("check-job", "completed", result={"qq_id": QQ, "cf_handle": "SecretHandle"})
        await jobs._update("sync-job", "completed", result={"qq_id": QQ, "cf_handle": "SecretHandle", "success_count": 1})
        stored = json.dumps(await self.sql("SELECT payload,result,error_message FROM cf_practice_jobs"))
        for identifier in (QQ, "SecretHandle", "测试账号"):
            self.assertNotIn(identifier, stored)
        self.assertEqual((await self.sql("SELECT handle,status FROM cf_practice_job_members WHERE qq_id=?", (OTHER,)))[0], {"handle": "OtherHandle", "status": "completed"})
        member = (await self.sql("SELECT status,handle,binding_key FROM cf_practice_job_members WHERE qq_id=?", (QQ,)))[0]
        self.assertEqual(member, {"status": "cancelled", "handle": None, "binding_key": None})
        self.assertEqual((await self.sql("SELECT status FROM cf_practice_jobs WHERE id='check-job'"))[0]["status"], "failed")

    async def test_closure_does_not_stop_other_members_in_the_same_sync_job(self):
        await self.seed_jobs()
        from feat.api.acm_api.cf_client import binding_key
        db = await open_db(self.db_path)
        try:
            other = await service.one(db, "SELECT * FROM users WHERE qq_id=?", (OTHER,))
        finally:
            await db.close()
        await self.sql("UPDATE cf_practice_job_members SET binding_key=? WHERE qq_id=?", (binding_key(other), OTHER))
        self.assertEqual((await self.close(await self.preview())).status_code, 200)
        jobs = self.app.config["CF_PRACTICE_JOBS"]
        called = []
        async def sync(qq_id, platforms, task, **kwargs):
            called.append(qq_id)
            task["status"] = "completed"
        with patch.object(jobs.engine, "sync_account", side_effect=sync), patch.object(jobs, "refresh_metadata", new=AsyncMock(return_value=[])):
            await jobs._run_sync("sync-job", {"expected_scope_fingerprint": "scope"})
        self.assertEqual(called, [OTHER])
        public = await jobs.get("sync-job")
        self.assertEqual(public["members"][0]["qq_id"], None)
        self.assertNotIn(QQ, json.dumps(public))

    async def test_other_workers_task_snapshots_hide_closed_identities(self):
        manager = self.app.task_manager
        manager.tasks["synthetic"] = {"id": "synthetic", "kind": "account", "qq_id": QQ, "status": "completed", "bindings": {"codeforces": {"account": "SecretHandle"}}, "result": {"error": "SecretHandle"}}
        await self.close(await self.preview())
        public = await manager.public_snapshots()
        self.assertIsNone(public[0]["qq_id"])
        self.assertNotIn(QQ, json.dumps(public))
        self.assertNotIn("SecretHandle", json.dumps(public))

    async def test_cf_legacy_task_without_epoch_never_acquires_a_current_identity(self):
        await self.seed_jobs()
        await self.sql("UPDATE cf_practice_job_members SET account_epoch=0")
        self.assertFalse(await self.app.config["CF_PRACTICE_JOBS"]._member_update("sync-job", QQ, "completed"))

    async def test_cleanup_failure_retries_with_lease_and_does_not_restore_account(self):
        await self.sql("UPDATE users SET avatar_url=? WHERE qq_id=?", ("/uploads/avatars/" + "a" * 32 + ".png", QQ))
        preview = await self.preview()
        self.assertEqual((await self.close(preview)).status_code, 200)
        worker = self.app.extensions["account_closure_cleanup"]
        with patch("feat.api.acm_api.account_closure_cleanup.remove_resource", side_effect=PermissionError()):
            self.assertTrue(await worker.run_once())
        row = (await self.sql("SELECT * FROM account_closure_cleanup_tasks"))[0]
        self.assertEqual((row["state"], row["last_error_code"]), ("pending", "file_unavailable"))
        self.assertGreater(row["next_at"], time.time())
        # Simulate a dead worker's abandoned lease, then reconstruct the worker.
        await self.sql("UPDATE account_closure_cleanup_tasks SET state='running',lease_token='dead',lease_until=1")
        restarted = ClosureCleanup(self.db_path, worker.folders)
        self.assertTrue(await restarted.run_once())
        self.assertEqual((await self.sql("SELECT state FROM account_closure_cleanup_tasks"))[0]["state"], "done")
        self.assertEqual((await self.sql("SELECT account_state FROM users"))[0]["account_state"], "closed")

    async def test_audit_expiry_is_enforced_and_only_root_can_read_masked_subjects(self):
        await self.sql("INSERT INTO account_lifecycle_audit(subject_qq_id,action,result_code,policy_version,created_at) VALUES(?,'self_close','REAUTH_FAILED','closure-v1',1)", (QQ,))
        self.assertEqual((await self.client.get("/api/admin/account-closures/audit")).status_code, 403)
        await self.app.extensions["account_closure_cleanup"].run_once()
        self.assertEqual(await self.sql("SELECT * FROM account_lifecycle_audit"), [])
        await self.sql("UPDATE web_accounts SET role='root' WHERE qq_id=?", (QQ,))
        await self.sql("INSERT INTO account_lifecycle_audit(subject_qq_id,action,result_code,policy_version,created_at) VALUES(?,'self_close','REAUTH_FAILED','closure-v1',?)", (QQ, int(time.time())))
        response = await self.client.get("/api/admin/account-closures/audit")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(QQ, await response.get_data(as_text=True))

    async def test_post_closure_backup_and_restore_preserve_tombstone_and_revoked_credentials(self):
        from feat.api.acm_api.maintenance import backup, restore, diagnose
        self.assertEqual((await self.close(await self.preview())).status_code, 200)
        with tempfile.TemporaryDirectory() as directory:
            snapshot, restored = Path(directory) / "snapshot", Path(directory) / "restored"
            await asyncio.to_thread(backup, self.db_path, snapshot, writers_stopped=True)
            await asyncio.to_thread(restore, snapshot, restored)
            database = restored / "database.sqlite3"
            self.assertTrue((await asyncio.to_thread(diagnose, database))["ok"])
            db = await open_db(database)
            try:
                user = await service.one(db, "SELECT account_state,account_epoch FROM users WHERE qq_id=?", (QQ,))
                self.assertEqual(user, {"account_state": "closed", "account_epoch": 2})
                account = await service.one(db, "SELECT is_active,password_hash FROM web_accounts WHERE qq_id=?", (QQ,))
                self.assertEqual(account["is_active"], 0)
                self.assertFalse(password_hash_usable(account["password_hash"]))
                with self.assertRaises(sqlite3.IntegrityError):
                    await db.execute("UPDATE users SET account_state='active' WHERE qq_id=?", (QQ,))
            finally:
                await db.close()

    async def test_cleanup_rejects_traversal_and_non_files(self):
        folder = Path(self.temp_dir.name)
        for key in ("../outside.png", "x.png", "a" * 32 + ".png/../other", "C:/outside.png"):
            with self.subTest(key=key), self.assertRaises(UnsafeResource):
                remove_resource(folder, key, "avatar")
        directory = folder / ("a" * 32 + ".png")
        directory.mkdir()
        with self.assertRaises(UnsafeResource):
            remove_resource(folder, directory.name, "avatar")


if __name__ == "__main__":
    unittest.main()
