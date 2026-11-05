"""Mobile privacy, identity, migration and Web compatibility contracts."""
import asyncio
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from feat.api.app import create_app
from feat.api.acm_api.auth_service import hash_password
from feat.api.acm_api.database import connect_db
from feat.api.acm_api.mobile_profiles import initialize_mobile_profiles


class MobileApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "mobile.db"
        self.addCleanup(self.temp.cleanup)
        self.env = patch.dict(os.environ, {
            "ACM_DATABASE_PATH": str(self.db_path), "ACM_WEBUI_SECRET_KEY": "mobile-contract-test-secret",
            "ACM_WEBUI_COOKIE_SECURE": "false", "ACM_BOT_API_TOKEN": "test-only",
            "ACM_BOOTSTRAP_ROOT_QQ_ID": "", "ACM_BOOTSTRAP_ROOT_PASSWORD": "",
            "ACM_ROOT_QQ_IDS": "", "ACM_ADMIN_QQ_IDS": "", "ACM_WEBUI_LEGACY_ADMIN_LOGIN": "false",
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.app = create_app()
        self.context = self.app.test_app()
        await self.context.__aenter__()
        self.addAsyncCleanup(self.context.__aexit__, None, None, None)
        self.client = self.app.test_client()
        db = await connect_db(self.db_path)
        try:
            now = int(time.time())
            for qq, name, change in (("900001", "同名成员", 0), ("900002", "同名成员", 0), ("900003", "900003", 1)):
                await db.execute("INSERT INTO users(qq_id,name,status,real_name,school,cf_handle) VALUES(?,?,'现役','私密姓名','私密学校',?)", (qq, name, "handle-" + qq))
                await db.execute("INSERT INTO web_accounts(qq_id,password_hash,role,must_change_password,is_active,credential_version,created_at,updated_at) VALUES(?,?,'member',?,1,1,?,?)", (qq, hash_password("Test-Password-123!"), change, now, now))
            for platform, problem_id in (("codeforces", "100A"), ("luogu", "P1001"), ("atcoder", "abc001_a"), ("nowcoder", "123"), ("cjlu", "1001")):
                await db.execute("INSERT INTO submissions(user_qq_id,platform,problem_id,problem_name,submit_time) VALUES('900001',?,?,'私有逐题记录',?)", (platform, problem_id, now))
            async with db.execute("SELECT id FROM forum_categories ORDER BY id LIMIT 1") as cursor:
                self.category = (await cursor.fetchone())["id"]
            self.posts = {}
            for status in ("published", "pending", "rejected", "removed"):
                cursor = await db.execute("INSERT INTO forum_posts(author_qq_id,category_id,title,body,status,created_at,updated_at) VALUES('900001',?,'合成话题',?,?,?,?)", (self.category, "内容-" + status, status, now, now))
                self.posts[status] = cursor.lastrowid
            await db.execute("INSERT INTO forum_comments(post_id,author_qq_id,body,status,created_at) VALUES(?,'900002','公开评论','published',?)", (self.posts["published"], now))
            await db.execute("INSERT INTO forum_comments(post_id,author_qq_id,body,status,created_at) VALUES(?,'900002','隐藏评论','hidden',?)", (self.posts["published"], now))
            await db.commit()
        finally:
            await db.close()

    async def json_get(self, path, client=None):
        response = await (client or self.client).get(path)
        self.assertEqual(response.status_code, 200, path)
        return await response.get_json()

    async def login(self, qq="900001", client=None):
        client = client or self.client
        response = await client.post("/api/auth/login", json={"qq_id": qq, "password": "Test-Password-123!"})
        self.assertEqual(response.status_code, 200)
        return {"X-CSRF-Token": (await response.get_json())["csrf_token"]}

    async def test_identity_linking_counts_and_privacy(self):
        meta = await self.json_get("/api/mobile/v1/capabilities")
        self.assertEqual(meta["api_version"], 1)
        self.assertTrue(all(meta["features"].values()))
        ranks = await self.json_get("/api/mobile/v1/leaderboard?days=all")
        member = next(row for row in ranks["rows"] if row["total_count"] == 5)
        ids = [row["public_member_id"] for row in ranks["rows"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(len(value) == 32 for value in ids))
        self.assertNotIn("900001", member["public_member_id"])
        profile = await self.json_get("/api/mobile/v1/members/" + member["public_member_id"])
        self.assertEqual(profile["name"], "同名成员")
        self.assertEqual(profile["total_count"], 5)
        self.assertEqual(set(profile["platform_counts"].values()), {1})
        for row in ranks["rows"] + [profile]:
            self.assertFalse({"qq_id", "real_name", "school", "cf_handle", "recent_ac", "submissions", "web_role"} & row.keys())
        posts = await self.json_get("/api/mobile/v1/forum/posts")
        self.assertEqual(posts["total"], 1)
        self.assertEqual(posts["rows"][0]["author_public_member_id"], member["public_member_id"])
        detail = await self.json_get("/api/mobile/v1/forum/posts/" + str(self.posts["published"]))
        self.assertEqual(detail["author_public_member_id"], member["public_member_id"])
        self.assertEqual(len(detail["comments"]), 1)
        commenter = await self.json_get("/api/mobile/v1/members/" + detail["comments"][0]["author_public_member_id"])
        self.assertEqual(commenter["name"], "同名成员")
        self.assertNotEqual(commenter["public_member_id"], profile["public_member_id"])
        for status in ("pending", "rejected", "removed"):
            self.assertEqual((await self.client.get("/api/mobile/v1/forum/posts/" + str(self.posts[status]))).status_code, 404)

    async def test_member_posts_pagination_and_web_compatibility(self):
        ranks = await self.json_get("/api/mobile/v1/leaderboard?days=all")
        owner = next(row["public_member_id"] for row in ranks["rows"] if row["total_count"] == 5)
        result = await self.json_get("/api/mobile/v1/members/" + owner + "/posts?page=1&page_size=100")
        self.assertEqual((result["total"], len(result["rows"]), result["page_size"]), (1, 1, 30))
        self.assertEqual((await self.json_get("/api/mobile/v1/members/" + owner + "/posts?page=2"))["rows"], [])
        self.assertEqual((await self.client.get("/api/mobile/v1/members/" + owner + "/posts?page=bad")).status_code, 400)
        for suffix in ("", "/posts"):
            self.assertEqual((await self.client.get("/api/mobile/v1/members/nonexistent" + suffix)).status_code, 404)
        original = await self.json_get("/api/forum/posts")
        mobile = await self.json_get("/api/mobile/v1/forum/posts")
        self.assertEqual(original, {**mobile, "rows": [{k: v for k, v in row.items() if k != "author_public_member_id"} for row in mobile["rows"]]})
        old_rank = await self.json_get("/api/community/leaderboard?days=all")
        self.assertEqual(old_rank, {**ranks, "rows": [{k: v for k, v in row.items() if k != "public_member_id"} for row in ranks["rows"]]})
        self.assertNotIn("author_public_member_id", (await self.json_get("/api/forum/posts/" + str(self.posts["published"]))))

    async def test_motto_is_self_only_with_csrf_and_strict_input(self):
        self.assertEqual((await self.client.get("/api/mobile/v1/me/public-profile")).status_code, 401)
        headers = await self.login()
        own = await self.json_get("/api/mobile/v1/me/public-profile")
        path = "/api/mobile/v1/me/public-profile"
        self.assertEqual((await self.client.put(path, json={"motto": "拒绝写入"})).status_code, 403)
        for data in ({}, {"motto": None}, {"motto": 123}, {"motto": "字" * 101}, {"motto": "abc", "qq_id": "900002"}, {"motto": "abc", "public_member_id": "other"}):
            self.assertEqual((await self.client.put(path, json=data, headers=headers)).status_code, 400)
        other = self.app.test_client()
        await self.login("900002", other)
        other_profile = await self.json_get(path, other)
        self.assertEqual((await self.client.put("/api/mobile/v1/members/" + other_profile["public_member_id"], json={"motto": "无权修改"}, headers=headers)).status_code, 405)
        response = await self.client.put(path, json={"motto": "  每天进步 😀  "}, headers=headers)
        self.assertEqual(response.status_code, 200)
        public = await self.json_get("/api/mobile/v1/members/" + own["public_member_id"])
        self.assertEqual(public["motto"], "每天进步 😀")
        self.assertEqual((await self.json_get(path, other))["motto"], "")
        for value in ("😀" * 100, ""):
            self.assertEqual((await self.client.put(path, json={"motto": value}, headers=headers)).status_code, 200)
        db = await connect_db(self.db_path)
        try:
            await db.execute("UPDATE web_accounts SET is_active=0 WHERE qq_id='900001'")
            await db.commit()
        finally:
            await db.close()
        self.assertEqual((await self.client.put(path, json={"motto": "不可写"}, headers=headers)).status_code, 401)
        self.assertEqual((await self.json_get("/api/mobile/v1/members/" + own["public_member_id"]))["motto"], "")

    async def test_initial_password_permissions(self):
        await self.login("900003")
        self.assertEqual((await self.client.get("/api/mobile/v1/me/public-profile")).status_code, 428)
        self.assertEqual((await self.client.put("/api/mobile/v1/me/public-profile", json={"motto": "blocked"})).status_code, 428)
        self.assertEqual((await self.client.get("/api/mobile/v1/capabilities")).status_code, 200)

    async def test_migration_idempotence_and_concurrent_provisioning(self):
        # Drop only the newly added table in this temporary database to model an old DB.
        db = await connect_db(self.db_path)
        try:
            await db.execute("DROP TABLE mobile_public_profiles")
            await db.commit()
        finally:
            await db.close()

        db = await connect_db(self.db_path)
        try:
            async with db.execute("SELECT qq_id,public_member_id FROM mobile_public_profiles") as cursor:
                original = {row["qq_id"]: row["public_member_id"] for row in await cursor.fetchall()}
            self.assertEqual(len(original), 3)
            await db.execute("UPDATE mobile_public_profiles SET motto='保留座右铭' WHERE qq_id='900001'")
            await db.execute("INSERT INTO users(qq_id,name) VALUES('900004','新增成员')")
            await db.commit()
        finally:
            await db.close()
        clients = [self.app.test_client() for _ in range(3)]
        results = await asyncio.gather(*(self.json_get("/api/mobile/v1/leaderboard?days=all", client) for client in clients))
        self.assertTrue(all(len(result["rows"]) == 4 for result in results))
        db = await connect_db(self.db_path)
        try:
            async with db.execute("SELECT qq_id,public_member_id,motto FROM mobile_public_profiles") as cursor:
                rows = [dict(row) for row in await cursor.fetchall()]
            self.assertEqual(len(rows), 4)
            self.assertEqual({row["qq_id"]: row["public_member_id"] for row in rows if row["qq_id"] in original}, original)
            self.assertEqual(next(row["motto"] for row in rows if row["qq_id"] == "900001"), "保留座右铭")
            async with db.execute("SELECT COUNT(*) FROM submissions") as cursor:
                self.assertEqual((await cursor.fetchone())[0], 5)
        finally:
            await db.close()

    async def test_old_mobile_table_upgrades_without_linking_recreated_accounts(self):
        db = await connect_db(self.db_path)
        try:
            await db.execute("DROP TABLE mobile_public_profiles")
            await db.execute("CREATE TABLE mobile_public_profiles (qq_id TEXT PRIMARY KEY, public_member_id TEXT NOT NULL UNIQUE, motto TEXT NOT NULL DEFAULT '', updated_at INTEGER NOT NULL DEFAULT 0)")
            await db.executemany("INSERT INTO mobile_public_profiles(qq_id,public_member_id,motto) VALUES(?,?,?)", [
                ("900001", "first-identity", "保留"), ("900002", "retired-identity", "不继承"),
            ])
            await db.execute("UPDATE users SET account_epoch=2 WHERE qq_id='900002'")
            await initialize_mobile_profiles(db)
            await db.commit()
            async with db.execute("SELECT qq_id,public_member_id,motto,account_epoch FROM mobile_public_profiles") as cursor:
                first = {row["qq_id"]: dict(row) for row in await cursor.fetchall()}
            self.assertEqual((first["900001"]["public_member_id"], first["900001"]["motto"], first["900001"]["account_epoch"]), ("first-identity", "保留", 1))
            self.assertNotEqual(first["900002"]["public_member_id"], "retired-identity")
            self.assertEqual((first["900002"]["motto"], first["900002"]["account_epoch"]), ("", 2))
            await initialize_mobile_profiles(db)
            await db.commit()
            async with db.execute("SELECT qq_id,public_member_id,motto,account_epoch FROM mobile_public_profiles") as cursor:
                self.assertEqual({row["qq_id"]: dict(row) for row in await cursor.fetchall()}, first)
        finally:
            await db.close()

    async def test_closure_and_same_qq_registration_never_reuse_public_identity(self):
        self.app.config["ACCOUNT_CLOSURE_ENABLED"] = True
        headers = await self.login()
        own = await self.json_get("/api/mobile/v1/me/public-profile")
        old_id = own["public_member_id"]
        db = await connect_db(self.db_path)
        try:
            await db.execute("UPDATE web_accounts SET role='root' WHERE qq_id='900002'")
            await db.commit()
        finally:
            await db.close()
        admin = self.app.test_client()
        admin_headers = await self.login("900002", admin)
        preview = await self.json_get("/api/me/account-closure/preview")
        response = await self.client.post("/api/me/account-closure", json={
            "current_password": "Test-Password-123!", "confirm_text": "注销账号",
            "policy_version": preview["policy_version"], "expected_account_epoch": preview["account_epoch"],
        }, headers={**headers, "Idempotency-Key": preview["request_id"], "X-Closure-Receipt": preview["receipt_token"]})
        self.assertEqual(response.status_code, 200, await response.get_json())
        for suffix in ("", "/posts"):
            self.assertEqual((await self.client.get("/api/mobile/v1/members/" + old_id + suffix)).status_code, 404)
        detail = await self.json_get("/api/mobile/v1/forum/posts/" + str(self.posts["published"]))
        self.assertTrue(detail["author_closed"])
        self.assertIsNone(detail["author_public_member_id"])
        created = await admin.post("/api/admin/web-accounts", json={"qq_id": "900001", "name": "新身份", "initial_password": "Fresh-Password-456!"}, headers=admin_headers)
        self.assertEqual(created.status_code, 201, await created.get_json())
        self.assertEqual((await self.client.get("/api/mobile/v1/members/" + old_id)).status_code, 404)
        ranks = await self.json_get("/api/mobile/v1/leaderboard?days=all")
        new_id = next(row["public_member_id"] for row in ranks["rows"] if row["name"] == "新身份")
        self.assertNotEqual(new_id, old_id)
        profile = await self.json_get("/api/mobile/v1/members/" + new_id)
        self.assertEqual((profile["total_count"], profile["motto"]), (0, ""))
        self.assertEqual((await self.json_get("/api/mobile/v1/members/" + new_id + "/posts"))["total"], 0)
        detail = await self.json_get("/api/mobile/v1/forum/posts/" + str(self.posts["published"]))
        self.assertIsNone(detail["author_public_member_id"])
