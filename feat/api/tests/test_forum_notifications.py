import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from feat.api.acm_api.auth_service import hash_password
from feat.api.acm_api.database import connect_db
from feat.api.app import create_app


class ForumNotificationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "notifications.db"
        self.env = patch.dict(os.environ, {
            "ACM_DATABASE_PATH": str(self.path), "ACM_WEBUI_SECRET_KEY": "notification-tests-only",
            "ACM_BOT_API_TOKEN": "notification-bot-tests-only",
            "ACM_BOOTSTRAP_ROOT_QQ_ID": "", "ACM_BOOTSTRAP_ROOT_PASSWORD": "",
        })
        self.env.start()
        self.app = create_app()
        self.password = "Notification-tests!2026"
        db = await connect_db(self.path)
        try:
            encoded = hash_password(self.password)
            for qq, role in [("10000001", "member"), ("10000002", "member"), ("10000003", "admin"), ("10000004", "member")]:
                await db.execute("INSERT INTO users(qq_id,name) VALUES(?,?)", (qq, f"成员{qq[-1]}"))
                await db.execute(
                    "INSERT INTO web_accounts(qq_id,password_hash,role,must_change_password,created_at,updated_at) "
                    "VALUES(?,?,?,0,?,?)", (qq, encoded, role, int(time.time()), int(time.time())),
                )
            await db.commit()
        finally:
            await db.close()
        self.owner, self.other, self.admin, self.third, self.public = [self.app.test_client() for _ in range(5)]
        self.headers = {}
        for index, client in enumerate([self.owner, self.other, self.admin, self.third], 1):
            response = await client.post("/api/auth/login", json={"qq_id": f"1000000{index}", "password": self.password})
            self.assertEqual(response.status_code, 200)
            self.headers[client] = {"X-CSRF-Token": (await response.get_json())["csrf_token"]}

    async def asyncTearDown(self):
        self.env.stop()
        self.directory.cleanup()

    async def post(self, publish=True):
        response = await self.owner.post("/api/forum/posts", headers=self.headers[self.owner], json={
            "title": "求助：如何理解最短路", "body": "这是一个需要讨论的算法问题。", "category_id": 2,
        })
        self.assertEqual(response.status_code, 201)
        post_id = (await response.get_json())["id"]
        if publish:
            response = await self.admin.post(f"/api/forum/moderation/posts/{post_id}", headers=self.headers[self.admin], json={"decision": "publish"})
            self.assertEqual(response.status_code, 200)
        return post_id

    async def comment(self, post_id, client=None, parent=None):
        client = client or self.other
        response = await client.post(f"/api/forum/posts/{post_id}/comments", headers=self.headers[client], json={"body": "可以先画图分析，再考虑转移。", "parent_id": parent})
        self.assertEqual(response.status_code, 201)
        return (await response.get_json())["id"]

    async def inbox(self, client=None, query=""):
        response = await (client or self.owner).get("/api/me/notifications" + query)
        self.assertEqual(response.status_code, 200)
        return await response.get_json()

    async def sql(self, statement, args=()):
        db = await connect_db(self.path)
        try:
            cursor = await db.execute(statement, args)
            rows = [dict(row) for row in await cursor.fetchall()]
            await db.commit()
            return rows
        finally:
            await db.close()

    async def test_private_routes_auth_csrf_and_owner_only_submission(self):
        post_id = await self.post(publish=False)
        for url in ["/api/me/notifications", "/api/me/notifications/count", f"/api/forum/mine/posts/{post_id}"]:
            self.assertEqual((await self.public.get(url)).status_code, 401)
        for client in [self.other, self.admin]:
            self.assertEqual((await client.get(f"/api/forum/mine/posts/{post_id}")).status_code, 404)
        self.assertEqual((await self.public.get(f"/api/forum/posts/{post_id}")).status_code, 404)
        for url in ["/api/me/notifications/1/read", "/api/me/notifications/read-all"]:
            self.assertEqual((await self.public.post(url, json={})).status_code, 401)
            self.assertEqual((await self.owner.post(url, json={})).status_code, 403)
        for url in ["/notifications.html?unread=1", f"/my-post.html?id={post_id}"]:
            response = await self.public.get(url)
            self.assertEqual(response.status_code, 302)
            self.assertIn("/login.html?next=", response.headers["Location"])
        response = await self.owner.get("/api/me/notifications")
        self.assertIn("no-store", response.headers["Cache-Control"])

    async def test_rejection_requires_reason_and_feedback_stays_private(self):
        post_id = await self.post(publish=False)
        progress = await (await self.owner.get(f"/api/forum/mine/posts/{post_id}")).get_json()
        self.assertEqual(progress["status"], "pending")
        self.assertIsNone(progress["reviewed_at"])
        for reason in [None, 123, " ", "x" * 1001]:
            response = await self.admin.post(f"/api/forum/moderation/posts/{post_id}", headers=self.headers[self.admin], json={"decision": "reject", "reason": reason})
            self.assertEqual(response.status_code, 400)
        reason = "请补充题目链接和已尝试的思路。\n不要只贴截图。"
        response = await self.admin.post(f"/api/forum/moderation/posts/{post_id}", headers=self.headers[self.admin], json={"decision": "reject", "reason": reason})
        self.assertEqual(response.status_code, 200)
        progress = await (await self.owner.get(f"/api/forum/mine/posts/{post_id}")).get_json()
        self.assertEqual((progress["status"], progress["review_reason"]), ("rejected", reason))
        self.assertIsInstance(progress["reviewed_at"], int)
        listing = await (await self.owner.get("/api/forum/mine/posts")).get_json()
        self.assertEqual(listing[0]["review_reason"], reason)
        inbox = await self.inbox()
        self.assertEqual(inbox["unread_count"], 1)
        self.assertEqual((inbox["rows"][0]["kind"], inbox["rows"][0]["review_reason"]), ("rejected", reason))
        self.assertEqual(inbox["rows"][0]["target_url"], f"/my-post.html?id={post_id}")
        self.assertEqual((await self.inbox(self.other))["total"], 0)
        self.assertEqual((await self.public.get(f"/api/forum/posts/{post_id}")).status_code, 404)
        response = await self.admin.post(f"/api/forum/moderation/posts/{post_id}", headers=self.headers[self.admin], json={"decision": "publish"})
        self.assertEqual(response.status_code, 404)
        self.assertEqual((await self.inbox())["total"], 1)

    async def test_publish_notifies_once_and_member_cannot_moderate(self):
        post_id = await self.post(publish=False)
        response = await self.other.post(f"/api/forum/moderation/posts/{post_id}", headers=self.headers[self.other], json={"decision": "publish"})
        self.assertEqual(response.status_code, 403)
        for expected in [200, 404]:
            response = await self.admin.post(f"/api/forum/moderation/posts/{post_id}", headers=self.headers[self.admin], json={"decision": "publish"})
            self.assertEqual(response.status_code, expected)
        self.assertEqual([row["kind"] for row in (await self.inbox())["rows"]], ["published"])
        public = await (await self.public.get(f"/api/forum/posts/{post_id}")).get_json()
        self.assertNotIn("review_reason", public)

    async def test_comment_and_reply_recipients_deduplication_and_no_self_notification(self):
        post_id = await self.post()
        owner_comment = await self.comment(post_id, self.owner)
        self.assertEqual((await self.inbox())["total"], 1)  # Only the publication result.
        other_comment = await self.comment(post_id)
        reply = await self.comment(post_id, self.third, owner_comment)
        rows = (await self.inbox())["rows"]
        self.assertEqual(len([row for row in rows if row["comment_id"] == reply]), 1)
        self.assertEqual(rows[0]["kind"], "reply")
        admin_reply = await self.comment(post_id, self.admin, other_comment)
        self.assertEqual((await self.inbox())["rows"][0]["kind"], "comment")
        other = await self.inbox(self.other)
        self.assertEqual(other["total"], 1)
        self.assertEqual(other["rows"][0]["kind"], "reply")
        self.assertIn(f"comment_id={admin_reply}#comment-{admin_reply}", other["rows"][0]["target_url"])
        await self.comment(post_id, self.other, other_comment)
        self.assertEqual((await self.inbox(self.other))["total"], 1)
        response = await self.other.post(f"/api/forum/posts/{post_id}/comments", headers=self.headers[self.other], json={"body": "错误回复", "parent_id": 99999})
        self.assertEqual(response.status_code, 404)
        self.assertEqual((await self.inbox(self.third))["total"], 0)

    async def test_read_state_is_owned_idempotent_and_persistent(self):
        post_id = await self.post()
        await self.comment(post_id)
        item = (await self.inbox())["rows"][0]
        url = f"/api/me/notifications/{item['id']}/read"
        response = await self.other.post(url, headers=self.headers[self.other])
        self.assertEqual(response.status_code, 404)
        response = await self.owner.post(url, headers=self.headers[self.owner])
        self.assertEqual(response.status_code, 200)
        first = (await self.inbox())["rows"][0]["read_at"]
        response = await self.owner.post(url, headers=self.headers[self.owner])
        self.assertEqual(response.status_code, 200)
        self.assertEqual((await self.inbox())["rows"][0]["read_at"], first)
        self.assertEqual((await self.inbox(query="?unread=1"))["total"], 1)
        count = await (await self.owner.get("/api/me/notifications/count?qq_id=10000002")).get_json()
        self.assertEqual(count["unread_count"], 1)
        other = await self.inbox(self.other, "?qq_id=10000001")
        self.assertEqual(other["total"], 0)

    async def test_read_all_does_not_consume_notifications_arriving_after_snapshot(self):
        post_id = await self.post()
        snapshot = await self.inbox()
        comment = await self.comment(post_id)
        response = await self.owner.post("/api/me/notifications/read-all", headers=self.headers[self.owner], json={"through_id": snapshot["latest_id"], "qq_id": "10000002"})
        self.assertEqual(response.status_code, 200)
        unread = await self.inbox(query="?unread=1")
        self.assertEqual(unread["total"], 1)
        self.assertEqual(unread["rows"][0]["comment_id"], comment)
        for through in [None, -1, True, "1", 10**30]:
            response = await self.owner.post("/api/me/notifications/read-all", headers=self.headers[self.owner], json={"through_id": through})
            self.assertEqual(response.status_code, 400)

    async def test_pagination_and_parameter_validation(self):
        post_id = await self.post()
        await self.comment(post_id)
        await self.comment(post_id)
        first = await self.inbox(query="?page_size=2")
        second = await self.inbox(query="?page=2&page_size=2")
        self.assertEqual((first["total"], len(first["rows"]), len(second["rows"])), (3, 2, 1))
        self.assertGreater(first["rows"][-1]["id"], second["rows"][0]["id"])
        for query in ["?page=bad", "?page_size=bad", "?page=1000001"]:
            self.assertEqual((await self.owner.get("/api/me/notifications" + query)).status_code, 400)

    async def test_hidden_comment_and_removed_post_do_not_expose_private_content(self):
        post_id = await self.post()
        root = await self.comment(post_id)
        reply = await self.comment(post_id, self.admin, root)
        await self.sql("UPDATE forum_comments SET status='hidden' WHERE id=?", (reply,))
        other = (await self.inbox(self.other))["rows"][0]
        self.assertEqual(other["target_url"], f"/post.html?id={post_id}#comments")
        response = await self.owner.delete(f"/api/forum/posts/{post_id}", headers=self.headers[self.owner])
        self.assertEqual(response.status_code, 200)
        other = (await self.inbox(self.other))["rows"][0]
        self.assertIsNone(other["target_url"])
        self.assertEqual(other["post_title"], "原话题已不可访问")
        self.assertNotIn("body", other)
        self.assertEqual((await self.public.get(f"/api/forum/posts/{post_id}")).status_code, 404)

    async def test_notification_failure_rolls_back_comment(self):
        post_id = await self.post()
        await self.sql("CREATE TRIGGER fail_notification BEFORE INSERT ON forum_notifications BEGIN SELECT RAISE(ABORT,'test notification failure'); END")
        response = await self.other.post(f"/api/forum/posts/{post_id}/comments", headers=self.headers[self.other], json={"body": "这条评论应整体回滚"})
        self.assertEqual(response.status_code, 500)
        self.assertEqual(await self.sql("SELECT id FROM forum_comments"), [])
        self.assertEqual((await self.inbox())["total"], 1)

    async def test_notification_failure_rolls_back_moderation(self):
        post_id = await self.post(publish=False)
        await self.sql("CREATE TRIGGER fail_notification BEFORE INSERT ON forum_notifications BEGIN SELECT RAISE(ABORT,'test notification failure'); END")
        response = await self.admin.post(f"/api/forum/moderation/posts/{post_id}", headers=self.headers[self.admin], json={"decision": "reject", "reason": "这个决定应整体回滚"})
        self.assertEqual(response.status_code, 500)
        post = (await self.sql("SELECT status,reviewed_at,review_reason FROM forum_posts WHERE id=?", (post_id,)))[0]
        self.assertEqual(post, {"status": "pending", "reviewed_at": None, "review_reason": ""})
        self.assertEqual((await self.inbox())["total"], 0)

    async def test_notification_target_beyond_first_500_comments_includes_parent(self):
        post_id = await self.post()
        db = await connect_db(self.path)
        try:
            await db.executemany("INSERT INTO forum_comments(post_id,author_qq_id,body,created_at) VALUES(?,'10000002','已有评论',1)", [(post_id,)] * 501)
            await db.commit()
        finally:
            await db.close()
        reply = await self.comment(post_id, self.admin, 501)
        response = await self.public.get(f"/api/forum/posts/{post_id}?comment_id={reply}")
        self.assertEqual(response.status_code, 200)
        comments = (await response.get_json())["comments"]
        self.assertEqual(len(comments), 502)
        self.assertEqual({row["id"] for row in comments[-2:]}, {501, reply})
        for value in ["bad", "-1", str(10**30)]:
            self.assertEqual((await self.public.get(f"/api/forum/posts/{post_id}?comment_id={value}")).status_code, 400)

    async def test_upgrade_preserves_posts_without_inventing_old_notifications(self):
        post_id = await self.post(publish=False)
        await self.sql("ALTER TABLE forum_posts DROP COLUMN review_reason")
        for _ in range(2):
            db = await connect_db(self.path)
            try:
                async with db.execute("SELECT review_reason,body FROM forum_posts WHERE id=?", (post_id,)) as cursor:
                    row = await cursor.fetchone()
                self.assertEqual(row["review_reason"], "")
                self.assertEqual(row["body"], "这是一个需要讨论的算法问题。")
                self.assertEqual(await db.execute_fetchall("PRAGMA foreign_key_check"), [])
            finally:
                await db.close()
        self.assertEqual((await self.inbox())["total"], 0)

    async def test_deleting_moderator_preserves_notification_without_new_user_delete_blocker(self):
        await self.post()
        response = await self.public.delete("/internal/v1/users/10000003", headers={"Authorization": "Bearer notification-bot-tests-only"})
        self.assertEqual(response.status_code, 200)
        rows = await self.sql("SELECT actor_qq_id FROM forum_notifications")
        self.assertEqual(rows, [{"actor_qq_id": None}])
        self.assertEqual((await self.inbox())["total"], 1)
