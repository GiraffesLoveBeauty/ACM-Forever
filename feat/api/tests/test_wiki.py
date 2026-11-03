"""Wiki integration contracts with real cookies, transactions and temporary assets."""

import io
import json
import sqlite3
from urllib.parse import quote
from pathlib import Path
from werkzeug.datastructures import FileStorage
from PIL import Image
import test_api_contract as contract
from feat.api.acm_api.database import connect_db
from feat.api.acm_api import wiki_service as svc


class WikiTests(contract.unittest.IsolatedAsyncioTestCase):
    account_login = contract.ApiContractTests.account_login

    async def asyncSetUp(self):
        await contract.ApiContractTests.asyncSetUp(self)
        self.context = self.app.test_app()
        await self.context.__aenter__()
        self.client = self.app.test_client()
        self.anon = self.app.test_client()
        self.headers = await self.account_login(self.client)
        self.app.config["MARKDOWN_UPLOAD_DIR"] = Path(self.temp_dir.name) / "assets"
        self.app.config["PUBLIC_BASE_URL"] = "https://wiki.example.test"

    async def asyncTearDown(self):
        await self.context.__aexit__(None, None, None)
        await contract.ApiContractTests.asyncTearDown(self)

    async def call(self, path, body=None, method=None, status=200, client=None):
        response = await (client or self.client).open(
            "/api" + quote(path, safe="/?=&"),
            method=method or ("POST" if body is not None else "GET"),
            json=body,
            headers=self.headers,
        )
        data = await response.get_json()
        self.assertEqual(response.status_code, status, data)
        return data

    async def cat(self, name, parent=None):
        state = await self.call("/admin/wiki/categories")
        return await self.call(
            "/admin/wiki/categories",
            {"name": name, "parent_id": parent, "version": state["navigation_version"]},
        )

    async def tree(self):
        top = await self.cat("知识总览")
        child = await self.cat("数据结构", top["id"])
        return top, child

    async def page(self, cid, slug="dsu", **extra):
        return await self.call(
            "/admin/wiki/pages",
            {
                "category_id": cid,
                "slug": slug,
                "title": "并查集入门",
                "body": "## 路径压缩\n中文算法正文 $a+b$\n```cpp\nfind(x);\n```",
                "aliases": ["DSU"],
                "tags": ["图论"],
                **extra,
            },
        )

    async def publish(self, p):
        return await self.call(
            f"/admin/wiki/revisions/{p['draft_revision_id']}/publish",
            {
                "version": p["version"],
                "idempotency_key": f"publish-{p['id']}-{p['version']}",
            },
        )

    async def upload(self, pid, kind="wiki", raw=None, status=201):
        if raw is None:
            f = io.BytesIO()
            Image.new("RGB", (16, 12), "yellow").save(f, format="PNG")
            raw = f.getvalue()
        response = await self.client.post(
            "/api/markdown/assets",
            form={"document_type": kind, "document_id": str(pid)},
            files={
                "file": FileStorage(
                    io.BytesIO(raw), filename="test.png", content_type="image/png"
                )
            },
            headers=self.headers,
        )
        data = await response.get_json()
        self.assertEqual(response.status_code, status, data)
        return data

    async def save(self, p, **extra):
        draft = p["draft"]
        return await self.call(
            f"/admin/wiki/pages/{p['id']}/revisions",
            {
                **draft,
                "version": p["version"],
                "base_revision_id": p["draft_revision_id"],
                **extra,
            },
        )

    async def test_anonymous_and_member_cannot_manage_or_download_private_sources(self):
        top, child = await self.tree()
        p = await self.page(child["id"])
        for path in [
            "/wiki/pages/dsu",
            "/wiki/pages/dsu/markdown",
            "/wiki/pages/dsu/revisions",
            f"/wiki/pages/dsu/revisions/{p['draft_revision_id']}",
        ]:
            await self.call(path, client=self.anon, status=404)
        self.assertEqual((await self.anon.get("/wiki.html?slug=dsu")).status_code, 200)
        self.assertEqual(
            (await self.anon.get("/api/admin/wiki/pages")).status_code, 401
        )
        self.assertEqual(
            (
                await self.client.post(
                    "/api/admin/wiki/categories", json={"name": "unsafe"}
                )
            ).status_code,
            403,
        )
        db = await connect_db(self.db_path)
        await db.execute("UPDATE web_accounts SET role='member' WHERE qq_id='12345678'")
        await db.commit()
        await db.close()
        self.assertEqual(
            (await self.client.get("/api/admin/wiki/pages")).status_code, 403
        )
        self.assertEqual(
            (
                await self.client.get(
                    f"/api/admin/wiki/revisions/{p['draft_revision_id']}/markdown"
                )
            ).status_code,
            403,
        )
        nav = await self.call("/wiki/navigation", client=self.anon)
        self.assertEqual(nav["categories"][1]["published_count"], 0)
        self.assertNotIn("draft_count", nav["categories"][1])

    async def test_publish_search_chinese_alias_and_draft_isolation(self):
        _, c = await self.tree()
        p = await self.page(c["id"])
        self.assertEqual(
            (await self.call("/wiki/search?q=DSU", client=self.anon))["total"], 0
        )
        p = await self.publish(p)
        for q in ["DSU", "中文", "图论", "并查集"]:
            self.assertEqual(
                (await self.call("/wiki/search?q=" + q, client=self.anon))["total"], 1
            )
        p2 = await self.save(p, title="未发布的秘密标题", body="尚未发布的内部关键词")
        self.assertEqual(
            (await self.call("/wiki/pages/dsu", client=self.anon))["title"],
            "并查集入门",
        )
        self.assertEqual(
            (await self.call("/wiki/search?q=内部关键词", client=self.anon))["total"], 0
        )
        self.assertEqual(
            len(await self.call("/wiki/pages/dsu/revisions", client=self.anon)), 1
        )
        p2 = await self.publish(p2)
        self.assertEqual(
            (await self.call("/wiki/search?q=内部关键词", client=self.anon))["total"], 1
        )
        self.assertEqual(
            (await self.call("/wiki/search?q=DSU", client=self.anon))["total"], 1
        )

    async def test_revision_conflict_idempotency_and_content_restore_keep_current_category(
        self,
    ):
        top, c = await self.tree()
        target = await self.cat("图论", top["id"])
        p = await self.page(c["id"])
        p = await self.publish(p)
        old = p
        p = await self.save(p, title="新版标题")
        await self.call(
            f"/admin/wiki/pages/{p['id']}/revisions",
            {
                **old["draft"],
                "version": old["version"],
                "base_revision_id": old["draft_revision_id"],
            },
            status=409,
        )
        body = {"version": p["version"], "idempotency_key": "same-publication-1"}
        rid = p["draft_revision_id"]
        first = await self.call(f"/admin/wiki/revisions/{rid}/publish", body)
        second = await self.call(f"/admin/wiki/revisions/{rid}/publish", body)
        self.assertEqual(first, second)
        await self.call(
            f"/admin/wiki/revisions/{rid}/publish", {**body, "version": 999}, status=409
        )
        p = await self.call(
            f"/admin/wiki/pages/{p['id']}",
            {"version": first["version"], "category_id": target["id"]},
            method="PATCH",
        )
        p = await self.call(
            f"/admin/wiki/pages/{p['id']}/restore",
            {
                "revision_id": old["draft_revision_id"],
                "version": p["version"],
                "base_revision_id": p["draft_revision_id"],
            },
        )
        self.assertEqual(p["category_id"], target["id"])
        self.assertNotEqual(p["draft_revision_id"], old["draft_revision_id"])
        self.assertEqual((await self.call("/wiki/pages/dsu"))["title"], "新版标题")
        await self.publish(p)
        public = await self.call("/wiki/pages/dsu")
        self.assertEqual(public["title"], "并查集入门")
        self.assertEqual(public["path"][1]["id"], target["id"])

    async def test_category_depth_names_order_default_and_rename_keep_slug(self):
        top, c = await self.tree()
        p = await self.publish(await self.page(c["id"]))
        state = await self.call("/admin/wiki/categories")
        for name, parent in [(" 知识总览 ", None), ("非法三级", c["id"])]:
            await self.call(
                "/admin/wiki/categories",
                {
                    "name": name,
                    "parent_id": parent,
                    "version": state["navigation_version"],
                },
                status=409 if parent is None else 400,
            )
        await self.call(
            "/admin/wiki/categories/order",
            {"version": state["navigation_version"], "parent_id": None, "ids": []},
            method="PUT",
            status=409,
        )
        await self.call(
            f"/admin/wiki/categories/{c['id']}",
            {"version": state["navigation_version"], "name": "数据结构新版"},
            method="PATCH",
        )
        self.assertEqual(
            (await self.call("/wiki/pages/dsu"))["path"][1]["name"], "数据结构新版"
        )
        state = await self.call("/admin/wiki/categories")
        self.assertEqual(state["default_category_id"], top["id"])
        await self.call(
            "/admin/wiki/settings",
            {"version": state["navigation_version"], "default_category_id": c["id"]},
            method="PUT",
            status=400,
        )

    async def test_delete_preview_rejects_late_article_and_atomic_move_restore(self):
        top, c = await self.tree()
        other = await self.cat("工程工具")
        p = await self.publish(await self.page(c["id"]))
        preview = await self.call(
            f"/admin/wiki/categories/{top['id']}/delete-preview", {}
        )
        await self.page(c["id"], "draft-only")
        payload = {
            "token": preview["token"],
            "target_id": other["id"],
            "default_category_id": other["id"],
            "idempotency_key": "delete-top-once",
        }
        await self.call(
            f"/admin/wiki/categories/{top['id']}/delete", payload, status=409
        )
        preview = await self.call(
            f"/admin/wiki/categories/{top['id']}/delete-preview", {}
        )
        self.assertEqual(preview["draft_count"], 1)
        self.assertEqual(preview["published_count"], 1)
        payload["token"] = preview["token"]
        result = await self.call(f"/admin/wiki/categories/{top['id']}/delete", payload)
        self.assertEqual(
            result,
            await self.call(f"/admin/wiki/categories/{top['id']}/delete", payload),
        )
        public = await self.call("/wiki/pages/dsu")
        self.assertEqual(public["path"][0]["id"], other["id"])
        self.assertEqual(public["path"][1]["id"], c["id"])
        await self.call(
            f"/admin/wiki/category-operations/{result['operation_id']}/restore", {}
        )
        self.assertEqual(
            (await self.call("/wiki/pages/dsu"))["path"][0]["id"], top["id"]
        )

    async def test_delete_name_collision_rolls_back_and_restore_rejects_later_edits(
        self,
    ):
        top, c = await self.tree()
        target = await self.cat("目标大类")
        await self.cat(c["name"], target["id"])
        p = await self.page(c["id"])
        preview = await self.call(
            f"/admin/wiki/categories/{top['id']}/delete-preview", {}
        )
        await self.call(
            f"/admin/wiki/categories/{top['id']}/delete",
            {
                "token": preview["token"],
                "target_id": target["id"],
                "default_category_id": target["id"],
                "idempotency_key": "collision-rollback",
            },
            status=409,
        )
        self.assertEqual(
            (await self.call("/admin/wiki/categories"))["default_category_id"],
            top["id"],
        )
        leaf = await self.cat("接收小类", target["id"])
        preview = await self.call(
            f"/admin/wiki/categories/{c['id']}/delete-preview", {}
        )
        op = await self.call(
            f"/admin/wiki/categories/{c['id']}/delete",
            {
                "token": preview["token"],
                "target_id": leaf["id"],
                "idempotency_key": "move-leaf-1",
            },
        )
        p = await self.call(f"/admin/wiki/pages/{p['id']}")
        await self.save(p, body="后续编辑不会被恢复覆盖")
        await self.call(
            f"/admin/wiki/category-operations/{op['operation_id']}/restore",
            {},
            status=409,
        )

    async def test_images_private_public_history_hidden_and_real_decode(self):
        _, c = await self.tree()
        p = await self.page(c["id"])
        asset = await self.upload(p["id"])
        self.assertEqual((await self.anon.get(asset["url"])).status_code, 404)
        self.assertEqual((await self.client.get(asset["url"])).status_code, 200)
        p = await self.save(p, body="图示\n![示意图](" + asset["url"] + ")")
        p = await self.publish(p)
        old = p["published_revision_id"]
        self.assertEqual((await self.anon.get(asset["url"])).status_code, 200)
        p = await self.publish(await self.save(p, body="新版本不再包含图片"))
        self.assertEqual((await self.anon.get(asset["url"])).status_code, 200)
        await self.call(
            f"/admin/wiki/revisions/{old}",
            {"version": p["version"], "hidden": True},
            method="PATCH",
        )
        self.assertEqual((await self.anon.get(asset["url"])).status_code, 404)
        await self.call(f"/wiki/pages/dsu/revisions/{old}", status=404)
        await self.upload(p["id"], raw=b'<svg onload="alert(1)"></svg>', status=400)
        await self.upload(p["id"], raw=b"x" * (2 * 1024 * 1024 + 1), status=413)

    async def test_markdown_download_sources_headers_permissions_and_literal_title(
        self,
    ):
        _, c = await self.tree()
        p = await self.page(
            c["id"],
            title="中文 [链接] *标题* &amp;",
            body="公式 $x^2$\n```cpp\n# fake\n```\n末行保留空格  \n\n",
        )
        url = f"/api/admin/wiki/revisions/{p['draft_revision_id']}/markdown"
        r = await self.client.get(url)
        self.assertEqual(r.status_code, 200)
        source = await r.get_data(as_text=True)
        self.assertIn("\\[链接\\]", source)
        self.assertIn("\\&amp;", source)
        self.assertIn("公式 $x^2$", source)
        self.assertTrue(source.endswith("末行保留空格  \n\n"))
        self.assertIn('filename="dsu.md"', r.headers["Content-Disposition"])
        self.assertEqual((await self.anon.get(url)).status_code, 401)
        await self.publish(p)
        public = await self.anon.get("/api/wiki/pages/dsu/markdown")
        self.assertEqual(public.status_code, 200)
        self.assertEqual(source, await public.get_data(as_text=True))

    async def test_etag_public_invalidation_and_paging_validation(self):
        _, c = await self.tree()
        p = await self.publish(await self.page(c["id"]))
        r = await self.anon.get("/api/wiki/navigation")
        tag = r.headers["ETag"]
        self.assertEqual(
            (
                await self.anon.get(
                    "/api/wiki/navigation", headers={"If-None-Match": tag}
                )
            ).status_code,
            304,
        )
        await self.publish(await self.save(p, title="公开的新版本"))
        self.assertEqual(
            (
                await self.anon.get(
                    "/api/wiki/navigation", headers={"If-None-Match": tag}
                )
            ).status_code,
            200,
        )
        for query in ["page=x", "page_size=51", "page=-1"]:
            await self.call("/wiki/pages?" + query, status=400)

    async def test_forum_uses_same_asset_service_and_keeps_moderation_privacy(self):
        draft = await self.call(
            "/forum/drafts",
            {"title": "论坛图片测试", "body": "还没有图片", "category_id": None},
            status=201,
        )
        asset = await self.upload(draft["id"], "forum_draft")
        categories = await self.call("/forum/categories")
        await self.call(
            f"/forum/drafts/{draft['id']}",
            {
                "title": "论坛图片测试",
                "body": "共享图片 ![图](" + asset["url"] + ")",
                "category_id": categories[0]["id"],
            },
            method="PUT",
        )
        post = await self.call(f"/forum/drafts/{draft['id']}/submit", {}, status=201)
        self.assertEqual((await self.anon.get(asset["url"])).status_code, 404)
        db = await connect_db(self.db_path)
        await db.execute(
            "UPDATE forum_posts SET status='published' WHERE id=?", (post["id"],)
        )
        await db.commit()
        await db.close()
        self.assertEqual((await self.anon.get(asset["url"])).status_code, 200)
        self.assertEqual(
            (
                await self.anon.get(f"/api/forum/posts/{post['id']}/markdown")
            ).status_code,
            200,
        )

    async def test_schema_reinitialization_preserves_content_and_prevents_cross_page_pointer(
        self,
    ):
        _, c = await self.tree()
        p = await self.page(c["id"])
        other = await self.page(c["id"], "other")
        for _ in range(2):
            db = await connect_db(self.db_path)
            await db.close()
        self.assertEqual(
            (await self.call(f"/admin/wiki/pages/{p['id']}"))["draft"]["body"],
            p["draft"]["body"],
        )
        db = await connect_db(self.db_path)
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                await db.execute(
                    "UPDATE wiki_pages SET draft_revision_id=? WHERE id=?",
                    (other["draft_revision_id"], p["id"]),
                )
        finally:
            await db.close()

    async def test_cleanup_grace_and_hidden_history_are_preserved(self):
        from feat.api.acm_api.markdown_cleanup import cleanup_assets

        _, c = await self.tree()
        p = await self.page(c["id"])
        retained = await self.upload(p["id"])
        p = await self.save(p, body="![历史图](" + retained["url"] + ")")
        p = await self.publish(p)
        historical_id = p["draft_revision_id"]
        p = await self.save(p, body="移除当前图片，但历史仍保留")
        p = await self.publish(p)
        await self.call(
            "/admin/wiki/revisions/" + str(historical_id),
            {"version": p["version"], "hidden": True},
            method="PATCH",
        )
        unused = await self.upload(p["id"])
        recent = await self.upload(p["id"])
        db = await connect_db(self.db_path)
        await db.execute(
            "UPDATE markdown_assets SET created_at=1 WHERE id IN (?,?)",
            (retained["id"], unused["id"]),
        )
        await db.commit()
        await db.close()
        folder = self.app.config["MARKDOWN_UPLOAD_DIR"]
        preview = await cleanup_assets(self.db_path, folder)
        self.assertFalse(preview["applied"])
        self.assertEqual([a["id"] for a in preview["assets"]], [unused["id"]])
        result = await cleanup_assets(self.db_path, folder, apply=True)
        self.assertEqual(result["assets"], preview["assets"])
        self.assertEqual((await self.client.get(unused["url"])).status_code, 404)
        self.assertEqual((await self.client.get(retained["url"])).status_code, 200)
        self.assertEqual((await self.client.get(recent["url"])).status_code, 200)

    async def test_malformed_metadata_and_preview_parameters_do_not_return_500(self):
        _, c = await self.tree()
        for extra in [
            {"exercises": [{"url": "https://[", "label": "错误链接"}]},
            {"tags": [None]},
            {"aliases": {}},
        ]:
            await self.call(
                "/admin/wiki/pages",
                {
                    "title": "输入校验",
                    "body": "正文",
                    "slug": "bad-input",
                    "category_id": c["id"],
                    **extra,
                },
                status=400,
            )
        await self.call(
            "/admin/wiki/categories/" + str(c["id"]) + "/delete",
            {"token": {}, "idempotency_key": "malformed-preview-token"},
            status=400,
        )

    async def test_draft_save_does_not_change_public_list_or_etag(self):
        _, c = await self.tree()
        p = await self.publish(await self.page(c["id"]))
        before = await self.anon.get("/api/wiki/pages")
        await self.save(p, title="内部修改", body="内部草稿")
        after = await self.anon.get("/api/wiki/pages")
        self.assertEqual(await before.get_json(), await after.get_json())
        self.assertEqual(before.headers["ETag"], after.headers["ETag"])
        data = await self.call("/wiki/pages/dsu", client=self.anon)
        self.assertNotIn("parent_revision_id", data)
        self.assertNotIn("hidden", data)

    async def test_blank_upload_and_role_revocation_of_private_wiki_assets(self):
        _, child = await self.tree()
        page = await self.page(child["id"], title="", body="")
        image = await self.upload(page["id"])
        self.assertEqual((await self.anon.get(image["url"])).status_code, 404)
        db = await connect_db(self.db_path)
        await db.execute("UPDATE web_accounts SET role='member' WHERE qq_id='12345678'")
        await db.commit()
        await db.close()
        self.assertEqual((await self.client.get(image["url"])).status_code, 404)
        await self.upload(page["id"], status=403)
        await self.call(
            "/forum/drafts",
            {"title": "禁止引用内部 Wiki 资源", "body": "![图](" + image["url"] + ")"},
            status=400,
        )
        draft = await self.call(
            "/forum/drafts", {"title": "", "body": "", "category_id": None}, status=201
        )
        owned = await self.upload(draft["id"], "forum_draft")
        self.assertEqual((await self.client.get(owned["url"])).status_code, 200)
        self.assertEqual((await self.anon.get(owned["url"])).status_code, 404)


    async def test_forum_mixed_asset_transaction_export_and_publication(self):
        draft = await self.call("/forum/drafts", {"title": "混合图片兼容测试", "body": ""}, status=201)
        shared = await self.upload(draft["id"], "forum_draft")
        image = io.BytesIO()
        Image.new("RGB", (16, 12), "blue").save(image, format="PNG")
        response = await self.client.post(
            "/api/forum/images", headers=self.headers,
            files={"image": FileStorage(io.BytesIO(image.getvalue()), filename="forum.png", content_type="image/png")},
        )
        self.assertEqual(response.status_code, 201)
        forum = await response.get_json()
        categories = await self.call("/forum/categories")
        content = {
            "title": "混合图片兼容测试", "category_id": categories[0]["id"],
            "cover_image_id": forum["id"],
            "body": f"![共享图]({shared['url']})\n\n![论坛图]({forum['url']})",
        }
        await self.call(f"/forum/drafts/{draft['id']}", content, method="PUT")
        # A failure in the second asset system must roll back body, cover and both reference sets.
        await self.call(f"/forum/drafts/{draft['id']}", {
            **content, "cover_image_id": None,
            "body": "![失效共享图](/api/markdown/assets/" + "f" * 32 + ")",
        }, method="PUT", status=400)
        saved = await self.call(f"/forum/drafts/{draft['id']}")
        self.assertEqual(saved["body"], content["body"])
        self.assertEqual(saved["cover_image_id"], forum["id"])
        # Downloaded/re-imported absolute URLs keep a body reference even without a cover.
        content["body"] = content["body"].replace(forum["url"], "https://wiki.example.test" + forum["url"])
        content["cover_image_id"] = None
        await self.call(f"/forum/drafts/{draft['id']}", content, method="PUT")
        db = await connect_db(self.db_path)
        try:
            row = await (await db.execute("SELECT COUNT(*) FROM forum_image_links WHERE draft_id=? AND image_id=?", (draft["id"], forum["id"]))).fetchone()
            self.assertEqual(row[0], 1)
        finally:
            await db.close()
        source = await self.client.get(f"/api/forum/drafts/{draft['id']}/markdown")
        self.assertEqual(source.status_code, 200)
        exported = (await source.get_data()).decode("utf-8")
        for asset in [shared, forum]:
            self.assertIn("https://wiki.example.test" + asset["url"], exported)
            self.assertEqual((await self.anon.get(asset["url"])).status_code, 404)
        post = await self.call(f"/forum/drafts/{draft['id']}/submit", {}, status=201)
        for asset in [shared, forum]:
            self.assertEqual((await self.anon.get(asset["url"])).status_code, 404)
        db = await connect_db(self.db_path)
        try:
            await db.execute("UPDATE forum_posts SET status='published' WHERE id=?", (post["id"],))
            await db.commit()
        finally:
            await db.close()
        for asset in [shared, forum]:
            self.assertEqual((await self.anon.get(asset["url"])).status_code, 200)
