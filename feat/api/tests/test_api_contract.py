import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from feat.api.acm_api.auth_service import hash_password
from feat.api.acm_api.database import connect_db
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


if __name__ == "__main__":
    unittest.main()
