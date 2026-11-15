"""Offline Luogu public catalog contracts, failure safety and local API integration."""

import asyncio
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import aiohttp

from feat.api.acm_api.database import connect_db
from feat.api.acm_api.luogu_client import LuoguUnavailable, luogu_get, page_context
from feat.api.acm_api.luogu_problem import (classifications, load_taxonomy, metadata,
    normalize_taxonomy, parse_problem, problem_id, render_markdown, save_taxonomy)
from feat.api.acm_api.luogu_sync import LuoguSync
from feat.api.acm_api.problem_bank import save_problem
from feat.api.acm_api.problem_sync import ProblemSync, sync_options
from feat.api.acm_api.web_account_service import hash_password
from feat.api.app import create_app
from feat.api.service_runtime import WebTaskManager

CONFIG = {"_version": "test-config", "ProblemDifficulty": [
    {"id": 0, "type": "Nil", "name": "暂无评定", "color": "grey-3"},
    {"id": 1, "type": "Pupil", "name": "入门", "color": "pink-3"},
    {"id": 8, "type": "Noi", "name": "NOI/NOI+/CTS", "color": "lapis-4"}]}
TAGS = {"_version": "test-tags", "tags": [
    {"id": -2, "name": "语言入门", "type": 2, "parent": None},
    {"id": 1, "name": "模拟", "type": 2, "parent": 110}],
    "types": [{"id": 2, "name": "算法", "type": "Algorithm", "color": "lapis-3", "order": 1}]}
TAXONOMY = normalize_taxonomy(CONFIG, TAGS)


def page(template, data):
    return ('<html><script type="application/json" data-any="x" id="lentille-context">'
            + json.dumps({"template": template, "status": 200, "data": data}, ensure_ascii=False)
            + '</script></html>').encode()


def problem(pid="P1001", difficulty=1, tags=None, description="计算 $a+b$。"):
    return {"pid": pid, "type": "P", "name": "A+B " + pid, "difficulty": difficulty,
            "tags": [-2, 1] if tags is None else tags, "totalSubmit": 10, "totalAccepted": 8,
            "fullScore": 100, "content": {"description": description, "formatI": "输入两个整数。",
            "formatO": "输出和。", "locale": "zh-CN"}, "samples": [["20 30\n", "50\n"]],
            "limits": {"time": [1000], "memory": [524288]}}


def body(pid="P1001", **kwargs):
    return page("problem.show", {"problem": problem(pid, **kwargs)})


def listing(items, total=None, size=2):
    return page("problem.list", {"problems": {"result": items, "count": len(items) if total is None else total, "perPage": size}})


class PayloadTests(unittest.TestCase):
    def test_context_attribute_order_and_profile_reuse(self):
        self.assertEqual(page_context(page("user.show", {"user": {"uid": 1}}))["data"]["user"]["uid"], 1)
        with self.assertRaises(ValueError):
            page_context(page("user.show", {}), template="problem.show")
        with self.assertRaises(ValueError):
            page_context(b'<script id="lentille-context" type="application/json">{broken}</script>')
        with self.assertRaises(ValueError):
            page_context(b'<html>login</html>')

    def test_problem_ids_and_scopes(self):
        self.assertEqual(problem_id(" p1001 "), "P1001")
        for value in ("CF1A", "AT_abc_a", "B1001", "P0", "P01", "P1/other", "https://luogu.com.cn/problem/P1", True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                problem_id(value)
        value = sync_options({"platform": "luogu", "problem_ids": ["p1001", "P1001"]})
        self.assertEqual(value["problem_ids"], ["P1001"])
        self.assertEqual(value["language"], "zh-CN")
        for data in ({"scope": []}, {"scope": "contest"}, {"scope": "problems"}, {"contest_id": "abc370"},
                     {"scope": "catalog", "problem_ids": []}, {"scope": "catalog", "limit": 5},
                     {"limit": 0}, {"limit": True}, {"batch_size": False}, {"language": "en"}, {"refresh": "true"}):
            with self.subTest(data=data), self.assertRaises(ValueError):
                sync_options({"platform": "luogu", **data})

    def test_native_zero_eight_negative_and_unknown_ids_are_preserved(self):
        for level in (0, 8, 99):
            item = metadata(problem(difficulty=level, tags=[-2, 99999]), TAXONOMY)
            self.assertIsNone(item["problem_rating"])
            difficulty, tags = classifications(item["luogu"], TAXONOMY)
            self.assertEqual(difficulty["id"], level)
            self.assertEqual(tags[0]["category"]["color"], "lapis-3")
            self.assertEqual(tags[1]["id"], 99999)
            self.assertIsNone(tags[1]["name"])
        self.assertEqual(classifications({"difficulty": 8}, TAXONOMY)[0]["name"], "NOI/NOI+/CTS")

    def test_taxonomy_malformed_or_duplicate_entries_are_rejected(self):
        for config, tags in (({}, TAGS), (CONFIG, {}), (CONFIG, {**TAGS, "tags": TAGS["tags"] * 2}),
                             (CONFIG, {**TAGS, "tags": [{"id": True, "name": "x", "type": 2}]})):
            with self.assertRaises(ValueError):
                normalize_taxonomy(config, tags)

    def test_markdown_preserves_math_code_table_and_resolves_images_safely(self):
        source = '# 标题\n\n$a<b$\n\n$$\na<b\n$$\n\n' + '~~~cpp\nint main() {}\n~~~\n\n|a|b|\n|-|-|\n|1|2|\n\n![img](/image/a.png)\n\n<script>alert(1)</script>\n\n[x](javascript:alert%281%29)\n\n![bad](data:text/html,bad)'
        rendered = render_markdown(source)
        self.assertIn('class="math"', rendered)
        self.assertIn('a&lt;b', rendered)
        self.assertIn('<table>', rendered)
        self.assertIn('language-cpp', rendered)
        self.assertIn('https://www.luogu.com.cn/image/a.png', rendered)
        self.assertNotIn('<script>', rendered)
        self.assertNotIn('javascript:', rendered)
        self.assertNotIn('src="data:', rendered)

    def test_statement_samples_and_limits_are_exact(self):
        item, content = parse_problem(body(), "P1001", TAXONOMY)
        self.assertEqual(content["samples"], [{"index": 1, "input": "20 30\n", "output": "50\n"}])
        self.assertEqual(item["luogu"]["limits"]["memory"], [524288])
        self.assertIn('$a+b$', item["luogu"]["markdown"])
        self.assertEqual(content["requested_language"], "zh-CN")
        no_samples = problem()
        no_samples["samples"] = []
        self.assertEqual(parse_problem(page("problem.show", {"problem": no_samples}), "P1001", TAXONOMY)[1]["samples"], [])

    def test_absent_difficulty_and_limits_are_unknown_instead_of_unrated(self):
        value = problem()
        value.pop("difficulty")
        value.pop("limits")
        item, _ = parse_problem(page("problem.show", {"problem": value}), "P1001", TAXONOMY)
        level, _ = classifications(item["luogu"], TAXONOMY)
        self.assertIsNone(level["id"])
        self.assertIsNone(level["name"])
        self.assertIsNone(item["luogu"]["limits"])
        value["limits"] = {"time": [], "memory": None}
        item, _ = parse_problem(page("problem.show", {"problem": value}), "P1001", TAXONOMY)
        self.assertEqual(item["luogu"]["limits"], value["limits"])

    def test_incomplete_payloads_never_replace_saved_content(self):
        for field, value in (("samples", None), ("samples", [["input"]]), ("samples", [[None, "x"]]),
                             ("content", {}), ("limits", {"time": "1000", "memory": [1]}),
                             ("difficulty", True), ("tags", ["1"]), ("pid", "P1002")):
            value_problem = problem()
            value_problem[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                parse_problem(page("problem.show", {"problem": value_problem}), "P1001", TAXONOMY)


class _Content:
    def __init__(self, raw):
        self.raw = raw

    async def iter_chunked(self, size):
        for offset in range(0, len(self.raw), size):
            yield self.raw[offset:offset + size]


class _Response:
    def __init__(self, raw=b'ok', status=200, headers=None):
        self.status, self.headers = status, headers or {}
        self.content = _Content(raw)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def raise_for_status(self):
        if self.status >= 400:
            raise aiohttp.ClientResponseError(SimpleNamespace(real_url="https://www.luogu.com.cn/"), (), status=self.status)


class RequestTests(unittest.IsolatedAsyncioTestCase):
    async def test_403_stops_requests_and_applies_shared_cooldown(self):
        session = SimpleNamespace(get=unittest.mock.Mock(return_value=_Response(status=403)))
        for _ in range(2):
            with self.assertRaises(LuoguUnavailable) as caught:
                await luogu_get(session, "https://www.luogu.com.cn/problem/P1001")
            self.assertGreaterEqual(caught.exception.retry_after, 299)
        self.assertEqual(session.get.call_count, 1)
        self.assertFalse(session.get.call_args.kwargs["allow_redirects"])

    async def test_429_honors_longer_retry_after(self):
        session = SimpleNamespace(get=lambda *a, **k: _Response(status=429, headers={"Retry-After": "900"}))
        with self.assertRaises(LuoguUnavailable) as caught:
            await luogu_get(session, "https://www.luogu.com.cn/_lfe/tags")
        self.assertEqual(caught.exception.retry_after, 900)

    async def test_redirect_is_not_followed(self):
        session = SimpleNamespace(get=lambda *a, **k: _Response(status=302))
        with self.assertRaises(LuoguUnavailable) as caught:
            await luogu_get(session, "https://www.luogu.com.cn/problem/P1001")
        self.assertEqual(caught.exception.status, 302)

    async def test_requests_are_paced_and_response_size_is_bounded(self):
        session = SimpleNamespace(get=unittest.mock.Mock(return_value=_Response()))
        with patch("feat.api.acm_api.luogu_client.asyncio.sleep", new_callable=AsyncMock) as wait:
            await luogu_get(session, "https://www.luogu.com.cn/_lfe/tags")
            await luogu_get(session, "https://www.luogu.com.cn/_lfe/config")
            self.assertGreater(wait.await_args_list[-1].args[0], 1.8)
        with patch("feat.api.acm_api.luogu_client.MAX_RESPONSE_BYTES", 1), patch("feat.api.acm_api.luogu_client.asyncio.sleep", new_callable=AsyncMock):
            with self.assertRaises(ValueError):
                await luogu_get(session, "https://www.luogu.com.cn/_lfe/config")
        for url in ("http://www.luogu.com.cn/problem/P1", "https://evil.com/problem/P1", "https://www.luogu.com.cn@evil.com/"):
            with self.assertRaises(ValueError):
                await luogu_get(session, url)


class StorageTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "test.db"
        self.db = await connect_db(self.path)
        self.addAsyncCleanup(self.db.close)
        await save_taxonomy(self.db, TAXONOMY)

    async def rows(self):
        async with self.db.execute("SELECT * FROM crawler_problems ORDER BY problem_id") as cursor:
            return [dict(row) for row in await cursor.fetchall()]

    async def run_sync(self, data, download=None, config=None):
        options = sync_options({"platform": "luogu", **data})
        task = {}
        if download is None:
            async def download(http, path):
                return body(path.rsplit('/', 1)[-1])
        with patch.object(LuoguSync, "download", side_effect=download):
            await ProblemSync(self.path, config).run(options, task)
        return task

    async def test_collect_explicit_skip_and_refresh(self):
        data = {"problem_ids": ["P1001", "P1002"]}
        task = await self.run_sync(data)
        self.assertEqual(task["status"], "completed")
        self.assertEqual(task["result"]["success_count"], 2)
        skipped = await self.run_sync(data, AsyncMock(side_effect=AssertionError("must skip saved statements")))
        self.assertEqual(skipped["result"]["skipped_count"], 2)
        refreshed = await self.run_sync({**data, "refresh": True})
        self.assertEqual(refreshed["result"]["success_count"], 2)
        self.assertEqual(len(await self.rows()), 2)

    async def test_failed_refresh_retains_statement_and_samples(self):
        await self.run_sync({"problem_ids": ["P1001"]})
        before = (await self.rows())[0]
        broken = problem()
        broken.pop("samples")
        task = await self.run_sync({"problem_ids": ["P1001"], "refresh": True}, AsyncMock(return_value=page("problem.show", {"problem": broken})))
        after = (await self.rows())[0]
        self.assertEqual(task["status"], "partial")
        self.assertEqual(after["statement_html"], before["statement_html"])
        self.assertEqual(after["samples"], before["samples"])
        self.assertEqual(after["last_fetch_status"], "failed")

    async def test_catalog_paginates_and_retains_markdown_while_clearing_labels(self):
        await self.run_sync({"problem_ids": ["P1001"]})
        first = [problem("P1001", difficulty=0, tags=[]), problem("P1002")]
        second = [problem("P1003", difficulty=8)]
        calls = []
        async def download(http, path):
            calls.append(path)
            return listing(first if path.endswith('1') else second, total=3)
        task = await self.run_sync({"scope": "catalog", "batch_size": 1}, download)
        self.assertEqual(task["status"], "completed")
        self.assertEqual(task["result"]["metadata_count"], 3)
        self.assertEqual(len(calls), 2)
        first_saved = (await self.rows())[0]
        self.assertTrue(first_saved["statement_html"])
        self.assertIn("markdown", json.loads(first_saved["metadata_json"])["luogu"])
        self.assertEqual(first_saved["tags"], "[]")
        async with self.db.execute("SELECT tags,problem_rating FROM recommendations WHERE platform='luogu' AND problem_id='P1001'") as cursor:
            self.assertEqual(tuple(await cursor.fetchone()), ("", None))

    async def test_repeated_page_is_partial_without_losing_committed_metadata(self):
        task = await self.run_sync({"scope": "catalog"}, AsyncMock(return_value=listing([problem("P1001"), problem("P1002")], total=4)))
        self.assertEqual(task["status"], "partial")
        self.assertFalse(task["result"]["catalog_complete"])
        self.assertEqual(len(await self.rows()), 2)

    async def test_catalog_batch_failure_reports_committed_partial_rows(self):
        await self.db.execute("CREATE TRIGGER fail_second BEFORE INSERT ON recommendations WHEN NEW.problem_id='P1002' BEGIN SELECT RAISE(ABORT,'test failure'); END")
        await self.db.commit()
        task = await self.run_sync({"scope": "catalog", "batch_size": 1}, AsyncMock(return_value=listing([problem("P1001"), problem("P1002")])))
        self.assertEqual(task["status"], "partial")
        self.assertEqual(task["result"]["metadata_count"], 1)
        self.assertEqual([row["problem_id"] for row in await self.rows()], ["P1001"])

    async def test_page_limit_is_an_explicit_incomplete_result(self):
        task = await self.run_sync({"scope": "catalog"}, AsyncMock(return_value=listing([problem("P1001"), problem("P1002")], total=4)), {"luogu_catalog_max_pages": 1})
        self.assertEqual(task["status"], "partial")
        self.assertIn("页数上限", task["result"]["error"])

    async def test_platform_statement_cap_and_resume(self):
        async def download(http, path):
            return listing([problem("P1001"), problem("P1002")]) if '/list?' in path else body(path.rsplit('/', 1)[-1])
        task = await self.run_sync({"scope": "platform", "limit": 1}, download)
        self.assertEqual(task["result"]["success_count"], 1)
        self.assertEqual(task["result"]["remaining_count"], 1)
        task = await self.run_sync({"scope": "platform", "limit": 1}, download)
        self.assertEqual(task["result"]["skipped_count"], 1)
        self.assertEqual(task["result"]["remaining_count"], 0)
        self.assertTrue(all(row["last_fetch_status"] == "ok" for row in await self.rows()))

    async def test_individual_404_and_timeout_do_not_discard_other_problems(self):
        async def download(http, path):
            if path.endswith('1003'):
                raise LuoguUnavailable("not found", status=404)
            if path.endswith('1002'):
                raise asyncio.TimeoutError("timeout")
            return body("P1001")
        task = await self.run_sync({"problem_ids": ["P1001", "P1002", "P1003"]}, download)
        self.assertEqual(task["status"], "partial")
        self.assertEqual(task["result"]["failure_count"], 2)
        self.assertEqual(task["result"]["success_count"], 1)

    async def test_retry_advances_past_previously_failed_rows(self):
        ids = ["P1001", "P1002", "P1003", "P1004", "P1005"]
        async def download(http, path):
            pid = path.rsplit('/', 1)[-1]
            if pid in {"P1003", "P1004", "P1005"}:
                raise LuoguUnavailable("not found", status=404)
            return body(pid)
        first = await self.run_sync({"problem_ids": ids}, download)
        self.assertEqual(first["result"]["failure_count"], 3)
        self.assertEqual(first["result"]["success_count"], 0)
        resumed = await self.run_sync({"problem_ids": ids}, download)
        self.assertEqual(resumed["result"]["success_count"], 2)
        self.assertEqual(sum(row["last_fetch_status"] == "ok" for row in await self.rows()), 2)

    async def test_access_restriction_stops_entire_task(self):
        download = AsyncMock(side_effect=LuoguUnavailable("restricted", status=429, retry_after=60))
        task = await self.run_sync({"problem_ids": ["P1001", "P1002"]}, download)
        self.assertEqual(download.await_count, 1)
        self.assertTrue(task["result"]["access_limited"])
        self.assertEqual(task["result"]["retry_after"], 60)
        self.assertEqual((await self.rows())[-1]["last_fetch_status"], "failed")

    async def test_cancel_and_resume_keeps_committed_rows(self):
        started = asyncio.Event()
        async def download(http, path):
            if path.endswith('1001'):
                started.set()
                await asyncio.Event().wait()
            return body("P1002")
        options = sync_options({"platform": "luogu", "problem_ids": ["P1001", "P1002"]})
        task = {}
        with patch.object(LuoguSync, "download", side_effect=download):
            running = asyncio.create_task(ProblemSync(self.path).run(options, task))
            await asyncio.wait_for(started.wait(), 5)
            running.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await running
        self.assertEqual(task["status"], "cancelled")
        resumed = await self.run_sync({"problem_ids": ["P1001", "P1002"]})
        self.assertEqual(resumed["result"]["skipped_count"], 1)
        self.assertEqual(resumed["result"]["success_count"], 1)

    async def test_statement_and_catalog_write_roll_back_together(self):
        await self.run_sync({"problem_ids": ["P1001"]})
        before = (await self.rows())[0]
        await self.db.execute("CREATE TRIGGER fail_luogu BEFORE UPDATE ON recommendations BEGIN SELECT RAISE(ABORT,'test failure'); END")
        await self.db.commit()
        item, content = parse_problem(body(description="New statement"), "P1001", TAXONOMY)
        with self.assertRaises(Exception):
            await save_problem(self.db, item, content)
        self.assertEqual((await self.rows())[0], before)

    async def test_cold_taxonomy_then_local_cache_and_stale_fallback(self):
        await self.db.execute("DELETE FROM crawler_platform_taxonomies")
        await self.db.commit()
        async def download(http, path):
            if path == '/_lfe/config': return json.dumps(CONFIG).encode()
            if path == '/_lfe/tags': return json.dumps(TAGS).encode()
            return body()
        task = await self.run_sync({"problem_ids": ["P1001"]}, download)
        self.assertEqual(task["status"], "completed")
        self.assertFalse((await load_taxonomy(self.db))["stale"])
        await self.db.execute("UPDATE crawler_platform_taxonomies SET updated_at=0")
        await self.db.commit()
        task = await self.run_sync({"problem_ids": ["P1001"]}, AsyncMock(side_effect=asyncio.TimeoutError()))
        self.assertEqual(task["status"], "completed")
        self.assertIn("taxonomy_warning", task["result"])


class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "api.db"
        self.env = self.enterContext(patch.dict(os.environ, {"ACM_DATABASE_PATH": str(self.path), "ACM_WEBUI_SECRET_KEY": "test-only-secret"}))
        self.app = create_app()
        self.addAsyncCleanup(self.app.task_manager.close)
        db = await connect_db(self.path)
        try:
            now = int(time.time())
            password = hash_password("Test-Password-123!")
            for qq, role in (("12345678", "member"), ("87654321", "admin")):
                await db.execute("INSERT INTO users(qq_id,name) VALUES(?,?)", (qq, role))
                await db.execute("INSERT INTO web_accounts(qq_id,password_hash,role,must_change_password,is_active,credential_version,created_at,updated_at) VALUES(?,?,?,0,1,1,?,?)", (qq, password, role, now, now))
            await db.commit()
            await save_taxonomy(db, TAXONOMY)
            for pid, level, tags in (("P1001", 0, [-2]), ("P1002", 8, [1])):
                item, content = parse_problem(body(pid, difficulty=level, tags=tags), pid, TAXONOMY)
                await save_problem(db, item, content)
        finally:
            await db.close()

    async def login(self, client, qq="12345678"):
        response = await client.post("/api/auth/login", json={"qq_id": qq, "password": "Test-Password-123!"})
        self.assertEqual(response.status_code, 200)
        return {"X-CSRF-Token": (await response.get_json())["csrf_token"]}

    async def test_member_reads_native_labels_markdown_and_empty_taxonomy_without_network(self):
        client = self.app.test_client()
        await self.login(client)
        with patch.object(LuoguSync, "download", side_effect=AssertionError("read API must stay local")):
            response = await client.get("/api/me/problems?platform=luogu&native_difficulty=0&native_tag=-2&page_size=1")
            self.assertEqual(response.status_code, 200)
            result = await response.get_json()
            self.assertEqual(result["total"], 1)
            self.assertEqual(result["items"][0]["native_difficulty"]["name"], "暂无评定")
            self.assertIsNone(result["items"][0]["problem_rating"])
            detail = await (await client.get("/api/me/problems/luogu/p1001")).get_json()
            self.assertTrue(detail["content_available"])
            self.assertIn("$a+b$", detail["statement_markdown"])
            self.assertEqual(detail["native_limits"]["time"], [1000])
            self.assertNotIn("metadata_json", detail)
            statement_page = await client.get("/problem.html?platform=luogu&problem_id=P1001")
            self.assertEqual(statement_page.status_code, 200)
            self.assertIn("https://cdn.luogu.com.cn", statement_page.headers["Content-Security-Policy"])
            self.assertNotIn("https://cdn.luogu.com.cn", (await client.get("/home.html")).headers["Content-Security-Policy"])
            taxonomy = await (await client.get("/api/me/problems/taxonomy?platform=luogu")).get_json()
            self.assertEqual(taxonomy["difficulties"][-1]["id"], 8)
            solved = await (await client.get("/api/me/problems?platform=luogu&scope=solved")).get_json()
            self.assertEqual(solved["total"], 0)
        db = await connect_db(self.path)
        try:
            await db.execute("DELETE FROM crawler_platform_taxonomies")
            await db.commit()
        finally:
            await db.close()
        taxonomy = await (await client.get("/api/me/problems/taxonomy")).get_json()
        self.assertEqual(taxonomy["tags"], [])
        self.assertTrue(taxonomy["stale"])

    async def test_permissions_and_native_filter_validation(self):
        anonymous = self.app.test_client()
        self.assertEqual((await anonymous.get("/api/me/problems/taxonomy")).status_code, 401)
        member = self.app.test_client()
        headers = await self.login(member)
        self.assertEqual((await member.get("/api/problems/taxonomy")).status_code, 403)
        self.assertEqual((await member.post("/api/admin/problems/sync", json={"platform": "luogu", "problem_ids": ["P1001"]}, headers=headers)).status_code, 403)
        for args in ("native_difficulty=1", "platform=codeforces&native_tag=1", "platform=luogu&native_difficulty=-1", "platform=luogu&native_tag=bad"):
            self.assertEqual((await member.get("/api/me/problems?" + args)).status_code, 400)

    async def test_admin_can_filter_and_submit_existing_task_interface_with_csrf(self):
        client = self.app.test_client()
        headers = await self.login(client, "87654321")
        result = await (await client.get("/api/problems?platform=luogu&native_difficulty=8&native_tag=1")).get_json()
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0]["native_difficulty"]["color"], "lapis-4")
        payload = {"platform": "luogu", "problem_ids": ["P1001"], "refresh": True}
        self.assertEqual((await client.post("/api/admin/problems/sync", json=payload)).status_code, 403)
        with patch.object(LuoguSync, "download", new=AsyncMock(return_value=body())):
            response = await client.post("/api/admin/problems/sync", json=payload, headers=headers)
            self.assertEqual(response.status_code, 202)
            task_id = (await response.get_json())["task"]["id"]
            await self.app.task_manager.tasks[task_id]["_task"]
            self.assertEqual(self.app.task_manager.tasks[task_id]["status"], "completed")

    async def test_daily_luogu_is_opt_in_and_uses_existing_persistent_claims(self):
        engine = SimpleNamespace(db_path=self.path, crawler_config={"luogu_daily_problem_sync_enabled": True, "luogu_daily_statement_limit": 500})
        manager = WebTaskManager(engine)
        self.addAsyncCleanup(manager.close)
        calls = []
        async def run(options, task):
            calls.append(options)
            task["status"] = "completed"
        manager.problem_sync.run = run
        await manager._run_daily_problem_sync()
        await manager._run_daily_problem_sync()
        self.assertEqual([row["platform"] for row in calls], ["atcoder", "codeforces", "luogu"])
        self.assertTrue(calls[-1]["scheduled"])
        self.assertEqual(calls[-1]["limit"], 500)
