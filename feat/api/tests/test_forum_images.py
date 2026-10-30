import io
import mimetypes
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image, PngImagePlugin
from werkzeug.datastructures import FileStorage

from feat.api.acm_api.auth_service import hash_password
from feat.api.acm_api.database import connect_db
from feat.api.app import create_app


def png(size=(48, 32)):
    output = io.BytesIO()
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("Private note", "must not be served")
    Image.new("RGB", size, (50, 100, 150)).save(output, "PNG", pnginfo=metadata)
    return output.getvalue()


class ForumImageTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "forum.db"
        self.env = patch.dict(os.environ, {
            "ACM_DATABASE_PATH": str(self.path), "ACM_WEBUI_SECRET_KEY": "forum-image-test-only",
            "ACM_BOT_API_TOKEN": "forum-image-bot-test-only",
            "ACM_BOOTSTRAP_ROOT_QQ_ID": "", "ACM_BOOTSTRAP_ROOT_PASSWORD": "",
        })
        self.env.start()
        self.app = create_app()
        self.password = "Forum-image-password!123"
        db = await connect_db(self.path)
        try:
            encoded = hash_password(self.password)
            for qq, role in [("10000001", "member"), ("10000002", "member"), ("10000003", "admin")]:
                await db.execute("INSERT INTO users(qq_id,name) VALUES(?,?)", (qq, qq))
                await db.execute(
                    "INSERT INTO web_accounts(qq_id,password_hash,role,must_change_password,is_active,created_at,updated_at) "
                    "VALUES(?,?,?,0,1,?,?)", (qq, encoded, role, int(time.time()), int(time.time())),
                )
            await db.commit()
        finally:
            await db.close()
        self.owner, self.other, self.admin, self.public = [self.app.test_client() for _ in range(4)]
        self.headers = []
        for client, qq in [(self.owner, "10000001"), (self.other, "10000002"), (self.admin, "10000003")]:
            response = await client.post("/api/auth/login", json={"qq_id": qq, "password": self.password})
            self.assertEqual(response.status_code, 200)
            self.headers.append({"X-CSRF-Token": (await response.get_json())["csrf_token"]})

    async def asyncTearDown(self):
        self.env.stop()
        self.directory.cleanup()

    async def upload(self, client=None, headers=None, data=None):
        return await (client or self.owner).post(
            "/api/forum/images", headers=self.headers[0] if headers is None else headers,
            files={"image": FileStorage(io.BytesIO(png() if data is None else data), filename="untrusted.png", content_type="image/png")},
        )

    async def test_upload_authentication_validation_and_metadata(self):
        self.assertEqual((await self.upload(self.public, {})).status_code, 401)
        self.assertEqual((await self.upload(headers={})).status_code, 403)
        self.assertEqual((await self.upload(data=b"not an image")).status_code, 400)
        self.assertEqual((await self.upload(data=b"x" * (5 * 1024 * 1024 + 1))).status_code, 413)
        self.assertEqual((await self.upload(data=png((10001, 1)))).status_code, 400)
        response = await self.upload()
        self.assertEqual(response.status_code, 201)
        uploaded = await response.get_json()
        preview = await self.owner.get(uploaded["url"])
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.content_type, "image/webp")
        self.assertIn("no-store", preview.headers["Cache-Control"])
        with Image.open(io.BytesIO(await preview.get_data())) as image:
            self.assertEqual(image.format, "WEBP")
            self.assertEqual(image.size, (48, 32))
            self.assertNotIn("Private note", image.info)
        for client in [self.public, self.other, self.admin]:
            self.assertEqual((await client.get(uploaded["url"])).status_code, 404)

    async def test_upload_preview_policy_and_stylesheet_mime(self):
        dist = Path(self.directory.name) / "dist"
        (dist / "assets").mkdir(parents=True)
        (dist / "assets" / "test.css").write_text("body { color: black; }", encoding="utf-8")
        self.app.config["WEBUI_DIST_DIR"] = dist
        mimetypes.init()
        with patch.dict(mimetypes.types_map, {".css": "application/x-css"}):
            response = await self.public.get("/assets/test.css")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "text/css")
        self.assertIn("img-src 'self' data: blob:", response.headers["Content-Security-Policy"])

    async def test_cover_body_draft_moderation_publication_and_removal(self):
        cover = await (await self.upload()).get_json()
        inline = await (await self.upload()).get_json()
        data = {"title": "带封面和插图的帖子", "body": f"正文说明\n\n![样例图]({inline['url']})", "category_id": 1, "cover_image_id": cover["id"]}
        response = await self.owner.post("/api/forum/drafts", json=data, headers=self.headers[0])
        self.assertEqual(response.status_code, 201)
        draft_id = (await response.get_json())["id"]
        draft = await (await self.owner.get(f"/api/forum/drafts/{draft_id}")).get_json()
        self.assertEqual(draft["cover_image_id"], cover["id"])
        self.assertEqual(draft["cover_url"], cover["url"])
        self.assertEqual(draft["body"], data["body"])
        response = await self.owner.post(f"/api/forum/drafts/{draft_id}/submit", headers=self.headers[0])
        self.assertEqual(response.status_code, 201)
        post_id = (await response.get_json())["id"]
        self.assertEqual((await self.owner.get(f"/api/forum/drafts/{draft_id}")).status_code, 404)
        pending = await (await self.admin.get("/api/forum/moderation/posts")).get_json()
        self.assertEqual(pending[0]["cover_url"], cover["url"])
        for image in [cover, inline]:
            self.assertEqual((await self.public.get(image["url"])).status_code, 404)
            self.assertEqual((await self.other.get(image["url"])).status_code, 404)
            self.assertEqual((await self.admin.get(image["url"])).status_code, 200)
        self.assertEqual((await self.admin.post(f"/api/forum/moderation/posts/{post_id}", json={"decision": "publish"}, headers=self.headers[2])).status_code, 200)
        for image in [cover, inline]:
            self.assertEqual((await self.public.get(image["url"])).status_code, 200)
        listing = await (await self.public.get("/api/forum/posts")).get_json()
        self.assertEqual(listing["rows"][0]["cover_url"], cover["url"])
        detail = await (await self.public.get(f"/api/forum/posts/{post_id}")).get_json()
        self.assertEqual(detail["cover_url"], cover["url"])
        self.assertEqual(detail["body"], data["body"])
        await self.owner.delete(f"/api/forum/posts/{post_id}", headers=self.headers[0])
        for image in [cover, inline]:
            self.assertEqual((await self.public.get(image["url"])).status_code, 404)
            self.assertEqual((await self.owner.get(image["url"])).status_code, 200)

    async def test_private_reference_rejected_and_failed_update_is_atomic(self):
        image = await (await self.upload()).get_json()
        fields = {"title": "正常的草稿标题", "body": "正常的草稿正文", "category_id": 1}
        response = await self.other.post("/api/forum/drafts", json=fields, headers=self.headers[1])
        draft_id = (await response.get_json())["id"]
        for change in [{"cover_image_id": image["id"]}, {"body": f"![私有图片]({image['url']})"}]:
            response = await self.other.put(f"/api/forum/drafts/{draft_id}", json={**fields, **change}, headers=self.headers[1])
            self.assertEqual(response.status_code, 400)
        draft = await (await self.other.get(f"/api/forum/drafts/{draft_id}")).get_json()
        self.assertEqual(draft["body"], fields["body"])
        self.assertIsNone(draft["cover_image_id"])
        response = await self.other.post("/api/forum/posts", json={**fields, "cover_image_id": image["id"]}, headers=self.headers[1])
        self.assertEqual(response.status_code, 400)
        db = await connect_db(self.path)
        try:
            async with db.execute("SELECT COUNT(*) FROM forum_posts") as cursor:
                self.assertEqual((await cursor.fetchone())[0], 0)
            self.assertEqual(await db.execute_fetchall("PRAGMA foreign_key_check"), [])
        finally:
            await db.close()

    async def test_public_image_reuse_survives_original_post_removal(self):
        image = await (await self.upload()).get_json()
        fields = {"title": "公开图片复用测试", "body": f"说明 ![示意图]({image['url']})", "category_id": 1}
        response = await self.owner.post("/api/forum/posts", json=fields, headers=self.headers[0])
        post_id = (await response.get_json())["id"]
        await self.admin.post(f"/api/forum/moderation/posts/{post_id}", json={"decision": "publish"}, headers=self.headers[2])
        response = await self.other.post("/api/forum/drafts", json=fields, headers=self.headers[1])
        self.assertEqual(response.status_code, 201)
        draft_id = (await response.get_json())["id"]
        await self.owner.delete(f"/api/forum/posts/{post_id}", headers=self.headers[0])
        self.assertEqual((await self.public.get(image["url"])).status_code, 404)
        self.assertEqual((await self.other.get(image["url"])).status_code, 200)
        response = await self.other.put(f"/api/forum/drafts/{draft_id}", json={**fields, "title": "继续修改引用图片的草稿"}, headers=self.headers[1])
        self.assertEqual(response.status_code, 200)
        response = await self.other.post(f"/api/forum/drafts/{draft_id}/submit", headers=self.headers[1])
        self.assertEqual(response.status_code, 201)

    async def test_code_samples_do_not_publish_images_and_reference_style_images_do(self):
        image = await (await self.upload()).get_json()
        example = f"![代码示例]({image['url']})"
        fields = {"title": "Markdown 图片语法示例", "body": f"`{example}`\n\n```md\n{example}\n```", "category_id": 1}
        response = await self.other.post("/api/forum/posts", json=fields, headers=self.headers[1])
        self.assertEqual(response.status_code, 201)
        post_id = (await response.get_json())["id"]
        await self.admin.post(f"/api/forum/moderation/posts/{post_id}", json={"decision": "publish"}, headers=self.headers[2])
        self.assertEqual((await self.public.get(image["url"])).status_code, 404)
        response = await self.owner.post("/api/forum/posts", json={**fields, "body": f"![引用图片][diagram]\n\n[diagram]: {image['url']}"}, headers=self.headers[0])
        self.assertEqual(response.status_code, 201)
        post_id = (await response.get_json())["id"]
        await self.admin.post(f"/api/forum/moderation/posts/{post_id}", json={"decision": "publish"}, headers=self.headers[2])
        self.assertEqual((await self.public.get(image["url"])).status_code, 200)

    async def test_cover_removal_preserves_body_image_and_draft_deletion_cascades(self):
        image = await (await self.upload()).get_json()
        fields = {"title": "共用同一张图片", "body": f"正文中还有这张图 ![插图]({image['url']})", "category_id": 1, "cover_image_id": image["id"]}
        draft = await (await self.owner.post("/api/forum/drafts", json=fields, headers=self.headers[0])).get_json()
        response = await self.owner.put(f"/api/forum/drafts/{draft['id']}", json={**fields, "cover_image_id": None}, headers=self.headers[0])
        self.assertEqual(response.status_code, 200)
        db = await connect_db(self.path)
        try:
            async with db.execute("SELECT COUNT(*) FROM forum_image_links") as cursor:
                self.assertEqual((await cursor.fetchone())[0], 1)
        finally:
            await db.close()
        await self.owner.delete(f"/api/forum/drafts/{draft['id']}", headers=self.headers[0])
        db = await connect_db(self.path)
        try:
            async with db.execute("SELECT COUNT(*) FROM forum_image_links") as cursor:
                self.assertEqual((await cursor.fetchone())[0], 0)
        finally:
            await db.close()

    async def test_delete_uploader_with_unused_images_and_drafts(self):
        unused = await (await self.upload()).get_json()
        image = await (await self.upload()).get_json()
        fields = {"title": "仅保存在草稿中的图片", "body": f"![草稿图片]({image['url']})", "category_id": 1, "cover_image_id": image["id"]}
        response = await self.owner.post("/api/forum/drafts", json=fields, headers=self.headers[0])
        self.assertEqual(response.status_code, 201)
        response = await self.public.delete(
            "/internal/v1/users/10000001", headers={"Authorization": "Bearer forum-image-bot-test-only"},
        )
        self.assertEqual(response.status_code, 200)
        db = await connect_db(self.path)
        try:
            for table in ["users", "web_accounts", "forum_drafts", "forum_image_links"]:
                async with db.execute(f"SELECT COUNT(*) FROM {table}" + (" WHERE qq_id='10000001'" if table in {"users", "web_accounts"} else "")) as cursor:
                    self.assertEqual((await cursor.fetchone())[0], 0)
            rows = await db.execute_fetchall("SELECT owner_qq_id FROM forum_images")
            self.assertEqual([row[0] for row in rows], [None, None])
            self.assertEqual(await db.execute_fetchall("PRAGMA foreign_key_check"), [])
            # Reusing the deleted QQ number must not restore private upload access.
            await db.execute("INSERT INTO users(qq_id,name) VALUES('10000001','新账号')")
            await db.execute(
                "INSERT INTO web_accounts(qq_id,password_hash,role,must_change_password,created_at,updated_at) "
                "VALUES('10000001',?,'member',0,?,?)", (hash_password(self.password), int(time.time()), int(time.time())),
            )
            await db.commit()
        finally:
            await db.close()
        response = await self.owner.post("/api/auth/login", json={"qq_id": "10000001", "password": self.password})
        self.assertEqual(response.status_code, 200)
        self.app.config["PLUGIN_CONFIG"].update({
            "webui_admin_username": "legacy-image-admin", "webui_admin_password": "legacy-image-password",
            "webui_legacy_admin_login": True,
        })
        legacy_admin = self.app.test_client()
        response = await legacy_admin.post("/api/auth/login", json={"username": "legacy-image-admin", "password": "legacy-image-password"})
        self.assertEqual(response.status_code, 200)
        for uploaded in [unused, image]:
            self.assertTrue((Path(self.app.config["FORUM_UPLOAD_DIR"]) / f"{uploaded['id']}.webp").is_file())
            for client in [self.owner, self.other, self.admin, legacy_admin, self.public]:
                self.assertEqual((await client.get(uploaded["url"])).status_code, 404)

    async def test_delete_uploader_preserves_shared_post_and_draft_images(self):
        image = await (await self.upload()).get_json()
        fields = {"title": "其他成员继续使用图片", "body": f"![共享图片]({image['url']})", "category_id": 1, "cover_image_id": image["id"]}
        response = await self.owner.post("/api/forum/posts", json=fields, headers=self.headers[0])
        original_id = (await response.get_json())["id"]
        await self.admin.post(f"/api/forum/moderation/posts/{original_id}", json={"decision": "publish"}, headers=self.headers[2])
        response = await self.other.post("/api/forum/posts", json=fields, headers=self.headers[1])
        self.assertEqual(response.status_code, 201)
        shared_id = (await response.get_json())["id"]
        await self.admin.post(f"/api/forum/moderation/posts/{shared_id}", json={"decision": "publish"}, headers=self.headers[2])
        response = await self.other.post("/api/forum/drafts", json=fields, headers=self.headers[1])
        self.assertEqual(response.status_code, 201)
        draft_id = (await response.get_json())["id"]
        db = await connect_db(self.path)
        try:
            # Existing post-author foreign keys require the original content to be
            # purged before its author can be deleted; shared references remain.
            await db.execute("DELETE FROM forum_posts WHERE id=?", (original_id,))
            await db.commit()
        finally:
            await db.close()
        response = await self.public.delete(
            "/internal/v1/users/10000001", headers={"Authorization": "Bearer forum-image-bot-test-only"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual((await self.public.get(image["url"])).status_code, 200)
        post = await (await self.public.get(f"/api/forum/posts/{shared_id}")).get_json()
        self.assertEqual(post["cover_url"], image["url"])
        response = await self.other.delete(f"/api/forum/posts/{shared_id}", headers=self.headers[1])
        self.assertEqual(response.status_code, 200)
        self.assertEqual((await self.public.get(image["url"])).status_code, 404)
        self.assertEqual((await self.other.get(image["url"])).status_code, 200)
        response = await self.other.put(f"/api/forum/drafts/{draft_id}", json=fields, headers=self.headers[1])
        self.assertEqual(response.status_code, 200)
        response = await self.other.post(f"/api/forum/drafts/{draft_id}/submit", headers=self.headers[1])
        self.assertEqual(response.status_code, 201)
        db = await connect_db(self.path)
        try:
            self.assertIsNone((await db.execute_fetchall("SELECT owner_qq_id FROM forum_images WHERE id=?", (image["id"],)))[0][0])
            self.assertEqual(await db.execute_fetchall("PRAGMA foreign_key_check"), [])
        finally:
            await db.close()

    async def test_legacy_image_schema_migration_preserves_references_and_is_repeatable(self):
        db = await connect_db(self.path)
        try:
            await db.execute("DROP TABLE forum_image_links")
            await db.execute("DROP TABLE forum_images")
            await db.execute(
                "CREATE TABLE forum_images (id TEXT PRIMARY KEY, owner_qq_id TEXT NOT NULL REFERENCES users(qq_id), "
                "width INTEGER NOT NULL, height INTEGER NOT NULL, size_bytes INTEGER NOT NULL, created_at INTEGER NOT NULL)"
            )
            await db.execute(
                "CREATE TABLE forum_image_links (image_id TEXT NOT NULL REFERENCES forum_images(id), "
                "draft_id INTEGER REFERENCES forum_drafts(id) ON DELETE CASCADE, "
                "post_id INTEGER REFERENCES forum_posts(id) ON DELETE CASCADE, "
                "CHECK((draft_id IS NULL) <> (post_id IS NULL)), UNIQUE(image_id,draft_id), UNIQUE(image_id,post_id))"
            )
            await db.commit()
        finally:
            await db.close()
        image = await (await self.upload()).get_json()
        fields = {"title": "升级前的图片与引用", "body": f"![图片]({image['url']})", "category_id": 1, "cover_image_id": image["id"]}
        response = await self.owner.post("/api/forum/drafts", json=fields, headers=self.headers[0])
        self.assertEqual(response.status_code, 201)
        draft_id = (await response.get_json())["id"]
        response = await self.owner.post("/api/forum/posts", json=fields, headers=self.headers[0])
        self.assertEqual(response.status_code, 201)
        post_id = (await response.get_json())["id"]
        for _ in range(2):
            db = await connect_db(self.path)
            try:
                columns = {row["name"]: row for row in await db.execute_fetchall("PRAGMA table_info(forum_images)")}
                self.assertEqual(columns["owner_qq_id"]["notnull"], 0)
                foreign_keys = await db.execute_fetchall("PRAGMA foreign_key_list(forum_images)")
                self.assertEqual(foreign_keys[0]["on_delete"], "SET NULL")
                rows = await db.execute_fetchall("SELECT * FROM forum_images WHERE id=?", (image["id"],))
                self.assertEqual((rows[0]["owner_qq_id"], rows[0]["width"], rows[0]["height"], rows[0]["size_bytes"]), ("10000001", 48, 32, image["size_bytes"]))
                links = await db.execute_fetchall("SELECT image_id,draft_id,post_id FROM forum_image_links")
                self.assertCountEqual([tuple(row) for row in links], [(image["id"], draft_id, None), (image["id"], None, post_id)])
                self.assertEqual(await db.execute_fetchall("PRAGMA foreign_key_check"), [])
            finally:
                await db.close()
        self.assertEqual((await self.owner.get(image["url"])).status_code, 200)
        self.assertEqual((await self.public.get(image["url"])).status_code, 404)
        response = await self.admin.post(f"/api/forum/moderation/posts/{post_id}", json={"decision": "publish"}, headers=self.headers[2])
        self.assertEqual(response.status_code, 200)
        self.assertEqual((await self.public.get(image["url"])).status_code, 200)
