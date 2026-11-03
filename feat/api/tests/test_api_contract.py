import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from feat.api.acm_api.auth_service import hash_password
from feat.api.acm_api.database import connect_db
from feat.api.acm_api.crawler import _store_cf_attempts
from feat.api.acm_api.backend_api import _clear_platform_records
from feat.api.app import create_app


class ApiContractTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"
        self.env = patch.dict(
            os.environ,
            {
                "ACM_DATABASE_PATH": str(self.db_path),
                "ACM_WEBUI_SECRET_KEY": "test-only-secret-key",
                "ACM_BOT_API_TOKEN": "test-only-bot-token",
            },
        )
        self.env.start()
        self.app = create_app()

    async def asyncTearDown(self):
        self.env.stop()
        self.temp_dir.cleanup()

    async def account_login(self, client, role="root", change=0):
        db = await connect_db(self.db_path)
        try:
            now = int(time.time())
            await db.execute("INSERT INTO users(qq_id,name,status) VALUES('12345678','测试账号','现役')")
            await db.execute("INSERT INTO web_accounts(qq_id,password_hash,role,must_change_password,is_active,credential_version,created_at,updated_at) VALUES('12345678',?,?,?,1,1,?,?)", (hash_password("Test-Password-123!"), role, change, now, now))
            await db.commit()
        finally:
            await db.close()
        response = await client.post("/api/auth/login", json={"qq_id": "12345678", "password": "Test-Password-123!"})
        self.assertEqual(response.status_code, 200)
        return {"X-CSRF-Token": (await response.get_json())["csrf_token"]}

    async def test_admin_entry_role_redirect_and_full_login_target(self):
        async with self.app.test_app():
            client = self.app.test_client()
            target = "/admin.html?section=cf-practice&tab=check"
            response = await client.get(target)
            self.assertEqual(parse_qs(urlsplit(response.headers["Location"]).query)["next"], [target])
            await self.account_login(client, role="admin", change=1)
            response = await client.get(target)
            self.assertEqual(parse_qs(urlsplit(response.headers["Location"]).query)["next"], [target])
            db = await connect_db(self.db_path)
            try:
                await db.execute("UPDATE web_accounts SET must_change_password=0 WHERE qq_id='12345678'")
                await db.commit()
            finally:
                await db.close()
            response = await client.get("/member.html?qq_id=12345678")
            params = parse_qs(urlsplit(response.headers["Location"]).query)
            self.assertEqual(params, {"section": ["members"], "qq_id": ["12345678"]})
            for old, section in [("problem-bank", "problems")]:
                response = await client.get("/" + old + ".html")
                self.assertEqual(parse_qs(urlsplit(response.headers["Location"]).query)["section"], [section])

    async def test_member_is_denied_admin_but_keeps_frontend_tools_and_retired_notice(self):
        async with self.app.test_app():
            client = self.app.test_client()
            headers = await self.account_login(client, role="member")
            self.assertEqual((await client.get("/admin.html?section=members")).status_code, 403)
            self.assertEqual((await client.get("/api/admin/members")).status_code, 403)
            for page in ("challenge", "problem-bank", "contest-review"):
                self.assertEqual((await client.get("/" + page + ".html")).status_code, 200)
            for page in ("reviews", "submissions", "workspace"):
                response = await client.get("/" + page + ".html")
                self.assertEqual(response.status_code, 200)
                self.assertIn("功能已下线", await response.get_data(as_text=True))
            for route in ("/me/reviews", "/me/reviews/drafts", "/me/workspace/items", "/me/study-plan", "/me/submissions/attempts", "/me/submissions/analytics"):
                self.assertEqual((await client.get("/api" + route)).status_code, 410)
            for route, method in [("/me/workspace/items", "POST"), ("/me/workspace/items/1", "PATCH"), ("/me/workspace/items/1", "DELETE"), ("/me/study-plan", "POST"), ("/me/reviews/feedback", "POST")]:
                self.assertEqual((await client.open("/api" + route, method=method, json={}, headers=headers)).status_code, 410)

    async def test_admin_cannot_grant_web_role_or_change_bot_admin_configuration(self):
        async with self.app.test_app():
            client = self.app.test_client()
            headers = await self.account_login(client, role="admin")
            response = await client.patch("/api/admin/web-accounts/12345678", json={"role": "root"}, headers=headers)
            self.assertEqual(response.status_code, 403)
            self.assertEqual((await client.put("/api/admins", json={"admins": ["12345678"]}, headers=headers)).status_code, 403)
            detail = await (await client.get("/api/member/12345678")).get_json()
            self.assertEqual(detail["permissions"]["role"], "admin")
            self.assertEqual((await client.put("/api/member/12345678/permissions", json={"role": "member"}, headers=headers)).status_code, 410)

    async def test_member_search_pagination_and_preferences_cannot_hide_admin(self):
        async with self.app.test_app():
            client = self.app.test_client()
            headers = await self.account_login(client)
            db = await connect_db(self.db_path)
            try:
                await db.executemany("INSERT INTO users(qq_id,name,status,school) VALUES(?,?,'现役','SearchSchool')", [(str(20000000 + i), "成员" + str(i)) for i in range(25)])
                await db.execute("INSERT INTO settings VALUES('webui_preferences',?)", ('{"nav_hidden":["admin"],"nav_order":["workspace"],"font_scale":1.1}',))
                await db.commit()
            finally:
                await db.close()
            result = await (await client.get("/api/admin/members?search=SearchSchool&page=2&page_size=20")).get_json()
            self.assertEqual((result["total"], len(result["items"]), result["page"]), (25, 5, 2))
            detail = await (await client.get("/api/member/20000000")).get_json()
            self.assertIsNone(detail["permissions"]["role"])
            preferences = await (await client.get("/api/ui/preferences")).get_json()
            self.assertEqual(preferences, {"font_scale": 1.1})
            self.assertEqual((await client.put("/api/ui/preferences", json={"font_scale": 1}, headers=headers)).status_code, 200)

    async def test_contest_status_is_partial_and_does_not_create_review_or_plan(self):
        async with self.app.test_app():
            client = self.app.test_client()
            headers = await self.account_login(client)
            db = await connect_db(self.db_path)
            try:
                await db.execute("INSERT INTO contest_problem_reviews VALUES('12345678','1843','cf_1843A','WRONG_ANSWER',800,'archived note','unsolved',1)")
                await db.commit()
            finally:
                await db.close()
            base = {"owner_qq_id": "12345678", "contest_id": "1843", "problem_id": "cf_1843A"}
            self.assertEqual((await client.put("/api/contest/reviews", json={**base, "status": "reviewed"}, headers=headers)).status_code, 200)
            self.assertEqual((await client.put("/api/contest/reviews", json={**base, "verdict": "OK"}, headers=headers)).status_code, 200)
            self.assertEqual((await client.put("/api/contest/reviews", json={**base, "status": "queued"}, headers=headers)).status_code, 200)
            self.assertEqual((await client.put("/api/contest/reviews", json={**base, "note_md": "new note"}, headers=headers)).status_code, 410)
            self.assertEqual((await client.put("/api/contest/reviews", json={**base, "status": "solved"})).status_code, 403)
            db = await connect_db(self.db_path)
            try:
                row = await (await db.execute("SELECT verdict,rating,note_md,status FROM contest_problem_reviews")).fetchone()
                self.assertEqual(tuple(row), ("OK", 800, "archived note", "queued"))
                for table in ("review_states", "study_plan_items"):
                    self.assertEqual((await (await db.execute("SELECT COUNT(*) FROM " + table)).fetchone())[0], 0)
            finally:
                await db.close()

    async def test_web_retirement_keeps_archive_and_bot_submission_storage(self):
        async with self.app.test_app():
            client = self.app.test_client()
            headers = await self.account_login(client)
            for route in ("/workspace/items", "/review/queue", "/study-plan", "/submissions/attempts"):
                self.assertEqual((await client.get("/api" + route)).status_code, 410)
            self.assertEqual((await client.post("/api/review/feedback", json={}, headers=headers)).status_code, 410)
            db = await connect_db(self.db_path)
            try:
                await db.execute("INSERT INTO user_problem_state VALUES('12345678','codeforces','cf_1843A',0,'review','archived note',1)")
                await db.commit()
            finally:
                await db.close()
            response = await client.put("/api/problems/codeforces/cf_1843A/state", json={"owner_qq_id": "12345678", "is_favorite": True}, headers=headers)
            self.assertEqual(response.status_code, 200)
            db = await connect_db(self.db_path)
            try:
                row = await (await db.execute("SELECT is_favorite,state,note_md FROM user_problem_state")).fetchone()
                self.assertEqual(tuple(row), (1, "review", "archived note"))
            finally:
                await db.close()
            response = await client.post("/internal/v1/submissions/batch", json={"items": [{"qq_id": "12345678", "platform": "codeforces", "problem_id": "cf_1843B", "submit_time": int(time.time())}]}, headers={"Authorization": "Bearer test-only-bot-token"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual((await response.get_json())["inserted"], 1)

    async def test_problem_catalog_is_unique_and_paginated_without_notes(self):
        async with self.app.test_app():
            client = self.app.test_client()
            await self.account_login(client)
            db = await connect_db(self.db_path)
            try:
                await db.execute("INSERT INTO recommendations(platform,problem_id,problem_name,problem_rating,problem_url,tags) VALUES('codeforces','cf_1843A','Catalog name','800','https://codeforces.com/contest/1843/problem/A','math')")
                await db.execute("INSERT INTO users(qq_id,name) VALUES('87654321','另一成员')")
                await db.executemany("INSERT INTO submissions(user_qq_id,platform,problem_id,problem_name,submit_time) VALUES(?,'codeforces','cf_1843A','Old name',1)", [("12345678",), ("87654321",)])
                await db.commit()
            finally:
                await db.close()
            data = await (await client.get("/api/problems?owner_qq_id=12345678&page_size=1")).get_json()
            self.assertEqual((data["total"], len(data["items"])), (1, 1))
            self.assertEqual(data["items"][0]["problem_name"], "Catalog name")
            self.assertNotIn("note_md", data["items"][0])
            self.assertEqual((await (await client.get("/api/problems?page=2&page_size=1")).get_json())["items"], [])

    async def test_sync_keeps_submission_evidence_without_learning_linkage_and_binding_keeps_archive(self):
        async with self.app.test_app():
            db = await connect_db(self.db_path)
            try:
                await db.execute("INSERT INTO users(qq_id,name) VALUES('12345678','测试成员')")
                await _store_cf_attempts(db, "12345678", [{"id": 100, "problem": {"contestId": 1843, "index": "B"}, "creationTimeSeconds": 1, "verdict": "WRONG_ANSWER"}])
                self.assertEqual((await (await db.execute("SELECT COUNT(*) FROM submission_attempts")).fetchone())[0], 1)
                self.assertEqual((await (await db.execute("SELECT status FROM contest_problem_reviews")).fetchone())[0], "unsolved")
                for table in ("review_states", "study_plan_items"):
                    self.assertEqual((await (await db.execute("SELECT COUNT(*) FROM " + table)).fetchone())[0], 0)
                await db.execute("INSERT INTO user_problem_state VALUES('12345678','luogu','P1000',1,'review','archived',1)")
                await db.execute("INSERT INTO review_states(owner_qq_id,platform,problem_id,review_count) VALUES('12345678','luogu','P1000',5)")
                await db.execute("INSERT INTO study_plan_items(owner_qq_id,platform,problem_id,added_at) VALUES('12345678','luogu','P1000',1)")
                await db.execute("INSERT INTO submissions(user_qq_id,platform,problem_id,submit_time) VALUES('12345678','luogu','P1000',1)")
                await _clear_platform_records(db, "12345678", "luogu")
                for table in ("user_problem_state", "review_states", "study_plan_items"):
                    self.assertEqual((await (await db.execute("SELECT COUNT(*) FROM " + table)).fetchone())[0], 1)
                self.assertEqual((await (await db.execute("SELECT COUNT(*) FROM submissions WHERE platform='luogu'")).fetchone())[0], 0)
            finally:
                await db.close()

    async def test_health_and_internal_token_authentication(self):
        async with self.app.test_app():
            client = self.app.test_client()

            health = await client.get("/health")
            self.assertEqual(health.status_code, 200)
            self.assertEqual(await health.get_json(), {"status": "ok"})

            denied = await client.get("/internal/v1/health")
            self.assertEqual(denied.status_code, 401)

            allowed = await client.get(
                "/internal/v1/health",
                headers={"Authorization": "Bearer test-only-bot-token"},
            )
            self.assertEqual(allowed.status_code, 200)
            self.assertEqual(await allowed.get_json(), {"status": "ok"})

    async def test_forum_read_is_public_but_writes_require_login_and_csrf(self):
        async with self.app.test_app():
            client = self.app.test_client()

            categories = await client.get("/api/forum/categories")
            self.assertEqual(categories.status_code, 200)
            self.assertTrue(await categories.get_json())

            unauthenticated = await client.post(
                "/api/forum/posts",
                json={"title": "测试帖子标题", "body": "测试帖子正文内容", "category_id": 1},
            )
            self.assertEqual(unauthenticated.status_code, 401)

            db = await connect_db(self.db_path)
            now = int(time.time())
            await db.execute(
                "INSERT INTO users(qq_id,name) VALUES(?,?)", ("12345678", "测试成员")
            )
            await db.execute(
                "INSERT INTO web_accounts"
                "(qq_id,password_hash,role,must_change_password,is_active,credential_version,created_at,updated_at) "
                "VALUES(?,?, 'member',0,1,1,?,?)",
                ("12345678", hash_password("test-password-123"), now, now),
            )
            await db.commit()
            await db.close()

            login = await client.post(
                "/api/auth/login",
                json={"qq_id": "12345678", "password": "test-password-123"},
            )
            self.assertEqual(login.status_code, 200)
            csrf_token = (await login.get_json())["csrf_token"]

            missing_csrf = await client.post(
                "/api/forum/posts",
                json={"title": "测试帖子标题", "body": "测试帖子正文内容", "category_id": 1},
            )
            self.assertEqual(missing_csrf.status_code, 403)

            created = await client.post(
                "/api/forum/posts",
                headers={"X-CSRF-Token": csrf_token},
                json={"title": "测试帖子标题", "body": "测试帖子正文内容", "category_id": 1},
            )
            self.assertEqual(created.status_code, 201)
            self.assertEqual((await created.get_json())["status"], "pending")


    async def test_forum_viewer_states_are_isolated_after_logout_and_account_switch(self):
        async with self.app.test_app():
            client = self.app.test_client()
            headers = await self.account_login(client, role="member")
            created = await client.post(
                "/api/forum/posts",
                headers=headers,
                json={"title": "会话隔离测试", "body": "仅用于测试的帖子", "category_id": 1},
            )
            self.assertEqual(created.status_code, 201)
            post_id = (await created.get_json())["id"]
            db = await connect_db(self.db_path)
            try:
                await db.execute("UPDATE forum_posts SET status='published' WHERE id=?", (post_id,))
                await db.execute("INSERT INTO users(qq_id,name) VALUES('87654321','第二个测试账号')")
                now = int(time.time())
                await db.execute(
                    "INSERT INTO web_accounts"
                    "(qq_id,password_hash,role,must_change_password,is_active,credential_version,created_at,updated_at) "
                    "VALUES('87654321',?,'member',0,1,1,?,?)",
                    (hash_password("Test-Password-123!"), now, now),
                )
                await db.commit()
            finally:
                await db.close()
            for action in ("like", "bookmark"):
                toggled = await client.post(f"/api/forum/posts/{post_id}/{action}", headers=headers)
                self.assertEqual(toggled.status_code, 200)
                self.assertTrue((await toggled.get_json())["active"])

            async def assert_viewer_states(expected):
                for sort in ("latest", "hot", "unanswered"):
                    result = await client.get(f"/api/forum/posts?sort={sort}")
                    self.assertEqual(result.status_code, 200)
                    row = (await result.get_json())["rows"][0]
                    self.assertEqual(bool(row["viewer_liked"]), expected)
                    self.assertEqual(bool(row["viewer_bookmarked"]), expected)
                    self.assertEqual(row["likes_count"], 1)
                detail = await client.get(f"/api/forum/posts/{post_id}")
                self.assertEqual(detail.status_code, 200)
                row = await detail.get_json()
                self.assertEqual(bool(row["viewer_liked"]), expected)
                self.assertEqual(bool(row["viewer_bookmarked"]), expected)

            await assert_viewer_states(True)
            self.assertEqual((await client.post("/api/auth/logout", headers=headers)).status_code, 200)
            await assert_viewer_states(False)
            login = await client.post(
                "/api/auth/login", json={"qq_id": "87654321", "password": "Test-Password-123!"},
            )
            self.assertEqual(login.status_code, 200)
            headers = {"X-CSRF-Token": (await login.get_json())["csrf_token"]}
            await assert_viewer_states(False)
            self.assertEqual((await client.post("/api/auth/logout", headers=headers)).status_code, 200)
            login = await client.post(
                "/api/auth/login", json={"qq_id": "12345678", "password": "Test-Password-123!"},
            )
            self.assertEqual(login.status_code, 200)
            await assert_viewer_states(True)


if __name__ == "__main__":
    unittest.main()
