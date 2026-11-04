"""Mobile API contracts against the repository service, using only temporary data.

Run from the repository root with API dependencies installed:
python -B -m unittest discover -s Android_APP/tests -v
This checks backend contracts; it does not replace device HTTPS integration.
"""
import io
import os
import tempfile
import time
from datetime import datetime, timedelta, timezone
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import quote

from PIL import Image
from werkzeug.datastructures import FileStorage
from feat.api.app import create_app
from feat.api.acm_api.auth_service import hash_password
from feat.api.acm_api.database import connect_db


class MobileApiContracts(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="acmforever-mobile-api-")
        self.db_path = Path(self.temp.name) / "test.db"
        self.env = patch.dict(os.environ, {
            "ACM_DATABASE_PATH": str(self.db_path),
            "ACM_WEBUI_SECRET_KEY": "synthetic-mobile-test-secret",
            "ACM_WEBUI_COOKIE_SECURE": "false",
            "ACM_BOT_API_TOKEN": "",
            "ACM_BOOTSTRAP_ROOT_QQ_ID": "",
            "ACM_BOOTSTRAP_ROOT_PASSWORD": "",
            "ACM_ROOT_QQ_IDS": "",
            "ACM_ADMIN_QQ_IDS": "",
            "ACM_WEBUI_LEGACY_ADMIN_LOGIN": "false",
        })
        self.env.start()
        self.app = create_app()
        self.context = self.app.test_app()
        await self.context.__aenter__()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.env.stop)
        self.addAsyncCleanup(self.context.__aexit__, None, None, None)
        self.client = self.app.test_client()
        db = await connect_db(self.db_path)
        try:
            now = int(time.time())
            for index, role in enumerate(("member", "admin", "root")):
                qq = str(90000001 + index)
                await db.execute("INSERT INTO users(qq_id,name,status) VALUES(?,?,'现役')", (qq, "合成成员" + role))
                await db.execute(
                    "INSERT INTO web_accounts(qq_id,password_hash,role,must_change_password,is_active,credential_version,created_at,updated_at) VALUES(?,?,?,0,1,1,?,?)",
                    (qq, hash_password("Synthetic-Password-123!"), role, now, now),
                )
            await db.execute(
                "INSERT INTO submissions(user_qq_id,platform,problem_id,problem_name,submit_time) VALUES('90000001','luogu','P1001','合成题目',?)", (now,)
            )
            async with db.execute("SELECT id FROM forum_categories ORDER BY id LIMIT 1") as cursor:
                self.category = (await cursor.fetchone())["id"]
            cursor = await db.execute(
                "INSERT INTO forum_posts(author_qq_id,category_id,title,body,status,created_at,updated_at) VALUES('90000001',?,'合成公开话题','仅用于本地接口验证','published',?,?)",
                (self.category, now, now),
            )
            self.post_id = cursor.lastrowid
            await db.execute("INSERT INTO forum_bookmarks(post_id,qq_id,created_at) VALUES(?,'90000001',?)", (self.post_id, now))
            await db.execute("INSERT INTO forum_drafts(author_qq_id,category_id,title,body,created_at,updated_at) VALUES('90000001',?,'合成草稿','私有草稿内容',?,?)", (self.category, now, now))
            await db.commit()
        finally:
            await db.close()

    async def login(self, qq="90000001"):
        response = await self.client.post("/api/auth/login", json={"qq_id": qq, "password": "Synthetic-Password-123!"})
        self.assertEqual(response.status_code, 200)
        result = await response.get_json()
        self.assertTrue(result["csrf_token"])
        return {"X-CSRF-Token": result["csrf_token"]}

    async def get_json(self, path, kind=dict):
        response = await self.client.get(path)
        self.assertEqual(response.status_code, 200, path)
        result = await response.get_json()
        self.assertIsInstance(result, kind, path)
        return result

    async def test_public_reads_and_private_boundary(self):
        categories = await self.get_json("/api/forum/categories", list)
        self.assertTrue(all({"id", "name"} <= row.keys() for row in categories))
        for sort in ("latest", "hot", "unanswered"):
            posts = await self.get_json("/api/forum/posts?page=1&page_size=12&sort=" + sort)
            self.assertTrue({"rows", "total", "page", "page_size"} <= posts.keys())
        posts = await self.get_json("/api/forum/posts?q=" + quote("合成公开"))
        self.assertEqual(len(posts["rows"]), 1)
        detail = await self.get_json("/api/forum/posts/" + str(self.post_id))
        self.assertTrue({"body", "author_name", "comments"} <= detail.keys())
        for days in ("7", "30", "all"):
            ranks = await self.get_json("/api/community/leaderboard?days=" + days + "&page_size=20&sort=total_count")
            self.assertTrue({"rows", "total", "page", "page_size"} <= ranks.keys())
            for row in ranks["rows"]:
                self.assertTrue({"name", "cf_count", "luogu_count", "total_count"} <= row.keys())
                self.assertFalse({"qq_id", "real_name", "school", "recent_ac", "public_member_id"} & row.keys())
        self.assertEqual((await self.client.get("/api/me/problems")).status_code, 401)
        self.assertEqual((await self.client.get("/api/me/profile")).status_code, 401)
        self.assertEqual((await self.client.get("/api/forum/posts/99999999")).status_code, 404)

    async def test_today_ranking_positive_filter_and_paging(self):
        midnight = datetime(2026, 10, 15, tzinfo=timezone(timedelta(hours=8)))
        start = int(midnight.timestamp())
        db = await connect_db(self.db_path)
        try:
            await db.execute("DELETE FROM submissions")
            for owner, problem, timestamp in [
                ("90000001", "yesterday", start-1), ("90000001", "today", start),
                ("90000001", "tomorrow", start+86400),
                ("90000002", "yesterday", start-1), ("90000003", "today-root", start+1),
            ]:
                await db.execute("INSERT INTO submissions(user_qq_id,platform,problem_id,problem_name,submit_time) VALUES(?,'luogu',?,'Test',?)", (owner, problem, timestamp))
            for index in range(8):
                owner = str(91000000+index)
                await db.execute("INSERT INTO users(qq_id,name,status) VALUES(?,?,'现役')", (owner, "Rank test "+str(index)))
                await db.execute("INSERT INTO submissions(user_qq_id,platform,problem_id,problem_name,submit_time) VALUES(?,'luogu','today','Test',?)", (owner,start+1))
            await db.commit()
        finally:
            await db.close()
        with patch("feat.api.acm_api.forum_api.datetime", wraps=datetime) as clock:
            clock.now.return_value = midnight + timedelta(seconds=1)
            for prefix in ("/api/community/leaderboard", "/api/mobile/v1/leaderboard"):
                for size in (5,10,20,100):
                    result = await self.get_json(prefix+f"?period=today&days=all&positive_only=1&page_size={size}")
                    self.assertEqual(result["total"],10)
                    self.assertEqual(len(result["rows"]),min(size,10))
                    self.assertTrue(all(row["total_count"]==1 for row in result["rows"]))
                    self.assertEqual((result["start_time"],result["end_time"]),(start,start+86400))
                    self.assertEqual((result["period"],result["timezone"],result["positive_only"]),("today","Asia/Shanghai",True))
                    self.assertFalse(any("qq_id" in row for row in result["rows"]))
                second = await self.get_json(prefix+"?period=today&positive_only=1&page_size=5&page=2")
                first = await self.get_json(prefix+"?period=today&positive_only=1&page_size=5&page=1")
                self.assertEqual(len(second["rows"]),5)
                self.assertFalse({r["name"] for r in first["rows"]}&{r["name"] for r in second["rows"]})
                for invalid in ("0","-1","abc","99999999999999999999999","1.5"):
                    result = await self.get_json(prefix+"?period=today&positive_only=1&page_size=5&page="+invalid)
                    self.assertEqual(result["page"],1)
                zero = await self.get_json(prefix+"?period=today&positive_only=1&platforms=codeforces")
                self.assertEqual((zero["total"],zero["rows"]),(0,[]))
                legacy = await self.get_json(prefix+"?period=today")
                self.assertEqual(legacy["total"],11)  # Existing clients still include zero rows by default.

    async def test_member_reads_writes_and_session(self):
        headers = await self.login()
        me = await self.get_json("/api/auth/me")
        self.assertTrue(me["authenticated"])
        self.assertEqual(me["role"], "member")
        profile = await self.get_json("/api/me/profile")
        self.assertTrue({"user", "total_count", "platform_counts", "recent_ac"} <= profile.keys())
        self.assertEqual(profile["total_count"], 1)
        problems = await self.get_json("/api/me/problems?page=1&page_size=20&platform=&tag=")
        self.assertTrue({"items", "total", "page", "page_size"} <= problems.keys())
        self.assertEqual(problems["total"], 1)
        self.assertEqual(len(await self.get_json("/api/forum/mine/bookmarks", list)), 1)
        self.assertEqual(len(await self.get_json("/api/forum/drafts", list)), 1)
        self.assertEqual((await self.client.put("/api/me/profile", json={"name": "不应保存"})).status_code, 403)
        self.assertEqual((await self.client.put("/api/me/profile", json={"name": "合成新昵称"}, headers=headers)).status_code, 200)
        self.assertEqual((await self.get_json("/api/me/profile"))["user"]["name"], "合成新昵称")
        response = await self.client.post("/api/forum/posts", json={"category_id": self.category, "title": "合成审核话题", "body": "仅用于本地接口审核验证"}, headers=headers)
        self.assertEqual(response.status_code, 201)
        post_id = (await response.get_json())["id"]
        mine = await self.get_json("/api/forum/mine/posts", list)
        self.assertEqual(next(row["status"] for row in mine if row["id"] == post_id), "pending")
        self.assertFalse(any(row["id"] == post_id for row in (await self.get_json("/api/forum/posts"))["rows"]))
        self.assertEqual((await self.client.get("/api/forum/posts/" + str(post_id))).status_code, 404)
        image = io.BytesIO()
        Image.new("RGB", (8, 8), "green").save(image, format="PNG")
        image.seek(0)
        response = await self.client.post("/api/me/avatar", files={"avatar": FileStorage(stream=image, filename="synthetic.png", content_type="image/png")}, headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertTrue((await response.get_json())["avatar_url"].startswith("/uploads/avatars/"))
        self.assertEqual((await self.client.delete("/api/me/avatar", json={}, headers=headers)).status_code, 200)
        response = await self.client.post("/api/auth/change-password", json={"old_password": "Synthetic-Password-123!", "new_password": "Synthetic-New-Password-456!"}, headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual((await self.client.post("/api/auth/logout", json={}, headers=headers)).status_code, 200)
        self.assertFalse((await self.get_json("/api/auth/me"))["authenticated"])
        self.assertEqual((await self.client.get("/api/forum/mine/posts")).status_code, 401)

    async def test_administrator_role_and_module_routes(self):
        sections = ("accounts", "members", "training", "problems", "cf-practice", "contests", "tasks", "moderation", "settings")
        headers = await self.login()
        self.assertEqual((await self.client.get("/admin.html")).status_code, 403)
        await self.client.post("/api/auth/logout", json={}, headers=headers)
        for qq, role in (("90000002", "admin"), ("90000003", "root")):
            headers = await self.login(qq)
            self.assertEqual((await self.get_json("/api/auth/me"))["role"], role)
            for section in sections:
                self.assertEqual((await self.client.get("/admin.html?section=" + section)).status_code, 200)
            await self.client.post("/api/auth/logout", json={}, headers=headers)

    async def test_legacy_proposal_paths_remain_unused(self):
        await self.login()
        for path in ("/api/me/public-profile", "/api/community/members/synthetic-public-id", "/api/community/members/synthetic-public-id/posts"):
            self.assertEqual((await self.client.get(path)).status_code, 404)
        self.assertEqual((await self.client.put("/api/me/public-profile", json={"motto": "合成座右铭"})).status_code, 405)

    async def test_forum_interactions_enforce_session_csrf_and_reply_depth(self):
        path = "/api/forum/posts/" + str(self.post_id)
        self.assertEqual((await self.client.post(path + "/like", json={})).status_code, 401)
        headers = await self.login()
        self.assertEqual((await self.client.post(path + "/like", json={})).status_code, 403)
        self.assertEqual((await self.client.post(path + "/like", json={}, headers=headers)).status_code, 200)
        detail = await self.get_json(path)
        self.assertTrue(detail["viewer_liked"])
        self.assertEqual(detail["likes_count"], 1)
        self.assertEqual((await self.client.post(path + "/bookmark", json={}, headers=headers)).status_code, 200)
        self.assertFalse((await self.get_json(path))["viewer_bookmarked"])
        self.assertEqual((await self.client.post(path + "/bookmark", json={}, headers=headers)).status_code, 200)
        response = await self.client.post(path + "/comments", json={"body": "合成根评论", "parent_id": 0}, headers=headers)
        self.assertEqual(response.status_code, 201)
        parent = (await response.get_json())["id"]
        response = await self.client.post(path + "/comments", json={"body": "合成回复", "parent_id": parent}, headers=headers)
        self.assertEqual(response.status_code, 201)
        child = (await response.get_json())["id"]
        self.assertEqual((await self.client.post(path + "/comments", json={"body": "不应嵌套三级", "parent_id": child}, headers=headers)).status_code, 404)
        self.assertEqual((await self.client.post(path + "/report", json={"reason": "合成测试举报原因"}, headers=headers)).status_code, 201)
        detail = await self.get_json(path)
        self.assertEqual(len(detail["comments"]), 2)
        self.assertFalse(any("qq_id" in field for row in detail["comments"] for field in row))
        await self.client.post("/api/auth/logout", json={}, headers=headers)
        self.assertFalse((await self.get_json(path))["viewer_liked"])

    async def test_draft_edit_submit_and_cross_account_isolation(self):
        headers = await self.login()
        response = await self.client.post("/api/forum/drafts", json={"title": "", "body": "", "category_id": None}, headers=headers)
        self.assertEqual(response.status_code, 201)
        draft_id = (await response.get_json())["id"]
        path = "/api/forum/drafts/" + str(draft_id)
        self.assertEqual((await self.client.post(path + "/submit", json={}, headers=headers)).status_code, 400)
        await self.get_json(path)
        payload = {"title": "合成新草稿标题", "body": "# 标题\n\n仅在临时库中保存。\n\n" + "😀" * 5, "category_id": self.category}
        self.assertEqual((await self.client.put(path, json=payload)).status_code, 403)
        self.assertEqual((await self.client.put(path, json=payload, headers=headers)).status_code, 200)
        self.assertEqual((await self.get_json(path))["body"], payload["body"])
        other = self.app.test_client()
        response = await other.post("/api/auth/login", json={"qq_id": "90000002", "password": "Synthetic-Password-123!"})
        token = (await response.get_json())["csrf_token"]
        self.assertEqual((await other.get(path)).status_code, 404)
        self.assertEqual((await other.put(path, json=payload, headers={"X-CSRF-Token": token})).status_code, 404)
        response = await self.client.post(path + "/submit", json={}, headers=headers)
        self.assertEqual(response.status_code, 201)
        post = await response.get_json()
        self.assertEqual(post["status"], "pending")
        self.assertEqual((await self.client.get(path)).status_code, 404)
        self.assertEqual((await self.client.post(path + "/submit", json={}, headers=headers)).status_code, 404)
        self.assertFalse(any(row["id"] == post["id"] for row in (await self.get_json("/api/forum/posts"))["rows"]))
        remaining = await self.get_json("/api/forum/drafts", list)
        self.assertEqual(len(remaining), 1)  # Existing fixture was not removed.
        self.assertEqual((await self.client.delete("/api/forum/drafts/" + str(remaining[0]["id"]), json={}, headers=headers)).status_code, 200)

    async def test_problem_favorites_training_and_contest_state_use_member_scope(self):
        headers = await self.login()
        path = "/api/me/problems/luogu/P1001"
        detail = await self.get_json(path)
        self.assertFalse(detail["content_available"])
        self.assertEqual(detail["samples"], [])
        self.assertEqual((await self.client.put(path + "/state", json={"is_favorite": True})).status_code, 403)
        self.assertEqual((await self.client.put(path + "/state", json={"is_favorite": True}, headers=headers)).status_code, 200)
        favorite = await self.get_json("/api/me/problems?state=favorite")
        self.assertEqual([row["problem_id"] for row in favorite["items"]], ["P1001"])
        other = self.app.test_client()
        await other.post("/api/auth/login", json={"qq_id": "90000002", "password": "Synthetic-Password-123!"})
        self.assertEqual((await (await other.get("/api/me/problems?state=favorite")).get_json())["items"], [])
        self.assertEqual((await self.client.put(path + "/state", json={"is_favorite": False}, headers=headers)).status_code, 200)
        self.assertEqual((await self.get_json("/api/me/problems?state=favorite"))["items"], [])
        await self.get_json("/api/me/training/challenges", list)
        calls = []
        async def provider(platform, tag, difficulty, owner_qq_id=None):
            calls.append((platform, tag, difficulty, owner_qq_id))
            return {"success": True, "platform": platform, "problem_id": "synthetic"}
        self.app.config["PLUGIN_CONFIG"]["_challenge_provider"] = provider
        response = await self.client.post("/api/me/challenge/start", json={"platform": "codeforces", "tag": "dp", "difficulty": 1000, "owner_qq_id": "90000002"}, headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(calls, [("codeforces", "dp", 1000, "90000001")])
        payload = {"contest_id": "synthetic-contest", "problem_id": "A", "status": "queued", "owner_qq_id": "90000002"}
        self.assertEqual((await self.client.put("/api/me/contest/reviews", json=payload, headers=headers)).status_code, 200)
        mine = await self.get_json("/api/me/contest/reviews?contest_id=synthetic-contest", list)
        self.assertEqual([(row["owner_qq_id"], row["status"]) for row in mine], [("90000001", "queued")])
        self.assertEqual(await (await other.get("/api/me/contest/reviews?contest_id=synthetic-contest")).get_json(), [])
        payload["status"] = "invalid"
        self.assertEqual((await self.client.put("/api/me/contest/reviews", json=payload, headers=headers)).status_code, 400)


if __name__ == "__main__":
    unittest.main()
