import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlencode, urlsplit

from feat.api.acm_api.auth_service import hash_password
from feat.api.acm_api.database import connect_db
from feat.api.app import create_app


class WebAccessTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.path = self.root / "access.db"
        self.env = patch.dict(os.environ, {
            "ACM_DATABASE_PATH": str(self.path), "ACM_WEBUI_SECRET_KEY": "access-tests-only",
            "ACM_BOOTSTRAP_ROOT_QQ_ID": "", "ACM_BOOTSTRAP_ROOT_PASSWORD": "",
        })
        self.env.start()
        self.app = create_app()
        self.dist = self.root / "dist"
        self.dist.mkdir()
        (self.dist / "index.html").write_text('<html><div id="app">Vue application</div></html>', encoding="utf-8")
        self.app.config["WEBUI_DIST_DIR"] = self.dist
        self.client = self.app.test_client()

    async def asyncTearDown(self):
        self.env.stop()
        self.directory.cleanup()

    async def login(self, *, change=False):
        db = await connect_db(self.path)
        try:
            await db.execute("INSERT INTO users(qq_id,name) VALUES('12345678','测试成员')")
            await db.execute(
                "INSERT INTO web_accounts(qq_id,password_hash,role,must_change_password,created_at,updated_at) "
                "VALUES('12345678',?,'member',?,?,?)",
                (hash_password("Access-tests-only!2026"), int(change), int(time.time()), int(time.time())),
            )
            await db.commit()
        finally:
            await db.close()
        response = await self.client.post("/api/auth/login", json={
            "qq_id": "12345678", "password": "Access-tests-only!2026",
        })
        self.assertEqual(response.status_code, 200)

    async def test_signed_in_login_rejects_loops_and_external_targets(self):
        await self.login()
        for target in [
            "/login.html", "/login.html?next=/post.html", "/auth-unavailable.html",
            "/forbidden.html", "/x/../login.html", "/%6cogin.html", "/%2flogin.html", "/%5cexample.org",
            "//example.org", "https://example.org", "/post.html%00",
        ]:
            response = await self.client.get("/login.html?" + urlencode({"next": target}))
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.headers["Location"], "/index.html", target)

    async def test_signed_in_login_keeps_query_and_anchor(self):
        await self.login()
        for target in ["/post.html?id=9&comment_id=21#comment-21", "/change-password.html"]:
            response = await self.client.get("/login.html?" + urlencode({"next": target}))
            self.assertEqual(response.headers["Location"], target)

    async def test_password_change_preserves_actual_login_destination_and_home_filter(self):
        await self.login(change=True)
        for source, target in [
            ("/login.html?" + urlencode({"next": "/compose.html?draft_id=12#editor"}), "/compose.html?draft_id=12#editor"),
            ("/login.html?next=/login.html", "/index.html"),
            ("/?category=help&sort=unanswered", "/?category=help&sort=unanswered"),
        ]:
            response = await self.client.get(source)
            location = urlsplit(response.headers["Location"])
            self.assertEqual(location.path, "/change-password.html")
            self.assertEqual(parse_qs(location.query)["next"], [target])

    async def test_direct_forbidden_and_unknown_pages_use_the_application_shell(self):
        await self.login()
        for url, status in [("/admin.html?section=members", 403), ("/forbidden.html", 200), ("/missing.html", 404), ("/missing/path", 404)]:
            response = await self.client.get(url)
            self.assertEqual(response.status_code, status)
            self.assertIn('id="app"', await response.get_data(as_text=True))
            self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertEqual((await self.client.get("/api/admin/members")).status_code, 403)

    async def test_page_fallback_does_not_mask_missing_api_or_asset_routes(self):
        for url in ["/api/missing", "/internal/missing", "/assets/missing.js", "/uploads/missing.png", "/missing.json"]:
            response = await self.client.get(url)
            self.assertEqual(response.status_code, 404)
            self.assertNotIn('id="app"', await response.get_data(as_text=True))
        response = await self.client.get("/missing.html")
        self.assertEqual(response.status_code, 404)
        self.assertIn('id="app"', await response.get_data(as_text=True))

    async def test_missing_build_stays_a_service_error_instead_of_a_broken_shell(self):
        self.app.config["WEBUI_DIST_DIR"] = self.root / "missing-dist"
        self.assertEqual((await self.client.get("/missing.html")).status_code, 503)
        self.assertEqual((await self.client.get("/")).status_code, 503)
