"""Server initialization and administrator problem collection contracts."""

import asyncio
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import AsyncExitStack
from pathlib import Path
from unittest.mock import patch

from feat.api.acm_api.auth_service import hash_password
from feat.api.acm_api.database import connect_db
from feat.api.acm_api.problem_content import parse_atcoder_tasks, parse_codeforces
from feat.api.app import create_app


LISTING = b'''<table><tbody>
<tr><td><a href="/contests/abc370/tasks/abc370_a">A</a></td>
<td><a href="/contests/abc370/tasks/abc370_a">Raise Both Hands</a></td></tr>
<tr><td><a href="/contests/abc370/tasks/abc370_b">B</a></td>
<td><a href="/contests/abc370/tasks/abc370_b">Binary Alchemy</a></td></tr>
</tbody></table>'''
BODY = b'''<div id="task-statement"><span class="lang-en">
<h3>Problem Statement</h3><p>Solve the problem.</p>
<h3>Sample Input 1</h3><pre>1 0\n</pre>
<h3>Sample Output 1</h3><pre>Yes\n</pre></span></div>'''
CF_BODY = b'''<div class="problem-statement"><div class="header"><div class="title">A. Example</div></div>
<p>Solve $$$x &lt; y$$$.</p><div class="sample-test">
<div class="input"><div class="title">Input</div><pre>
<div class="test-example-line"> 1 2</div><div class="test-example-line">3 4 </div></pre></div>
<div class="output"><div class="title">Output</div><pre>5<br>6<br></pre></div>
</div></div>'''


class TaskListTests(unittest.TestCase):
    def test_cf_samples_preserve_modern_line_divs_old_breaks_and_multiple_pairs(self):
        parsed = parse_codeforces(CF_BODY, "https://codeforces.com/contest/1843/problem/A")
        self.assertEqual(parsed["samples"], [{"index": 1, "input": " 1 2\n3 4 \n", "output": "5\n6\n"}])
        self.assertIn("$$$x &lt; y$$$", parsed["statement_html"])
        extra = b'<div class="input"><pre>7\n</pre></div><div class="output"><pre>8\n</pre></div>'
        head, tail = CF_BODY.rsplit(b"</div></div>", 1)
        raw = head + extra + b"</div></div>" + tail
        self.assertEqual(len(parse_codeforces(raw, "https://codeforces.com")["samples"]), 2)
        with self.assertRaises(ValueError):
            parse_codeforces(b"<h1>Access denied</h1>", "https://codeforces.com")
        with self.assertRaises(ValueError):
            parse_codeforces(b'<div class="problem-statement"><div class="sample-test"><div class="input"><pre>1</pre></div></div></div>', "https://codeforces.com")

    def test_list_resolves_names_and_ignores_external_or_other_contest_links(self):
        invalid_row = b'<tr><td><a href="https://other.example/contests/abc370/tasks/abc370_c">C</a></td></tr>'
        items = parse_atcoder_tasks(LISTING.replace(b"</tbody>", invalid_row + b"</tbody>"), "abc370")
        self.assertEqual([item["problem_id"] for item in items], ["abc370_a", "abc370_b"])
        self.assertEqual(items[0]["problem_name"], "Raise Both Hands")
        self.assertEqual(items[0]["problem_index"], "A")
        with self.assertRaises(ValueError):
            parse_atcoder_tasks(LISTING, "abc001")
        with self.assertRaises(ValueError):
            parse_atcoder_tasks(b"<h1>Login</h1>", "abc370")


class ProblemSyncTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        asyncio.get_running_loop().slow_callback_duration = 1
        self.directory = tempfile.TemporaryDirectory()
        self.db_path = Path(self.directory.name) / "server.db"
        self.env = patch.dict(os.environ, {
            "ACM_DATABASE_PATH": str(self.db_path), "ACM_WEBUI_SECRET_KEY": "test-only-secret",
        })
        self.env.start()
        self.app = create_app()
        db = await connect_db(self.db_path)
        try:
            now = int(time.time())
            await db.execute("INSERT INTO users(qq_id,name) VALUES('12345678','Administrator')")
            await db.execute(
                "INSERT INTO web_accounts(qq_id,password_hash,role,must_change_password,is_active,"
                "credential_version,created_at,updated_at) VALUES('12345678',?,'admin',0,1,1,?,?)",
                (hash_password("Test-Password-123!"), now, now),
            )
            await db.commit()
        finally:
            await db.close()

    async def asyncTearDown(self):
        await self.app.task_manager.close()
        self.env.stop()
        self.directory.cleanup()

    async def login(self, client):
        response = await client.post("/api/auth/login", json={"qq_id": "12345678", "password": "Test-Password-123!"})
        self.assertEqual(response.status_code, 200)
        return {"X-CSRF-Token": (await response.get_json())["csrf_token"]}

    async def query(self, sql, parameters=()):
        db = await connect_db(self.db_path)
        try:
            async with db.execute(sql, parameters) as cursor:
                return [dict(row) for row in await cursor.fetchall()]
        finally:
            await db.close()

    async def write(self, sql):
        db = await connect_db(self.db_path)
        try:
            await db.execute(sql)
            await db.commit()
        finally:
            await db.close()

    async def submit(self, client, headers, **options):
        response = await client.post("/api/admin/problems/sync", json={"contest_id": "abc370", **options}, headers=headers)
        self.assertEqual(response.status_code, 202, await response.get_json())
        task_id = (await response.get_json())["task"]["id"]
        await self.app.task_manager.tasks[task_id]["_task"]
        snapshots = await (await client.get("/api/tasks")).get_json()
        return next(task for task in snapshots if task["id"] == task_id)

    async def test_sync_requires_login_admin_csrf_and_password_change(self):
        async with self.app.test_app():
            client = self.app.test_client()
            payload = {"contest_id": "abc370"}
            self.assertEqual((await client.post("/api/admin/problems/sync", json=payload)).status_code, 401)
            headers = await self.login(client)
            self.assertEqual((await client.post("/api/admin/problems/sync", json=payload)).status_code, 403)
            await self.write("UPDATE web_accounts SET role='member' WHERE qq_id='12345678'")
            self.assertEqual((await client.post("/api/admin/problems/sync", json=payload, headers=headers)).status_code, 403)
            await self.write("UPDATE web_accounts SET role='root',must_change_password=1 WHERE qq_id='12345678'")
            self.assertEqual((await client.post("/api/admin/problems/sync", json=payload, headers=headers)).status_code, 428)
            self.assertEqual(self.app.task_manager.tasks, {})

    async def test_invalid_payloads_do_not_start_network_tasks(self):
        async with self.app.test_app():
            client = self.app.test_client()
            headers = await self.login(client)
            payloads = [None, [], {}, {"contest_id": "../other"},
                        {"contest_id": "abc370", "platform": "codeforces"},
                        {"contest_id": "abc370", "limit": True},
                        {"contest_id": "abc370", "limit": 101},
                        {"contest_id": "abc370", "language": []},
                        {"contest_id": "abc370", "refresh": "true"},
                        {"contest_id": "abc370", "problem_ids": "abc370_a"},
                        {"contest_id": "abc370", "problem_ids": ["https://other.example"]},
                        {"contest_id": "abc370", "items": []}]
            payloads += [{"platform": "codeforces", "contest_id": True},
                         {"platform": "codeforces", "contest_id": 100001},
                         {"platform": "codeforces", "contest_id": 1843, "problem_ids": ["1844A"]},
                         {"platform": "codeforces", "contest_id": 1843, "language": "ja"}]
            for payload in payloads:
                with self.subTest(payload=payload):
                    response = await client.post("/api/admin/problems/sync", json=payload, headers=headers)
                    self.assertEqual(response.status_code, 400)
                    self.assertEqual((await response.get_json())["code"], "invalid_request")
            self.assertEqual(self.app.task_manager.tasks, {})

    async def test_limited_sync_resumes_and_new_problems_are_visible_in_catalog(self):
        async def download(http, url):
            return LISTING if "/tasks?" in url else BODY
        async with AsyncExitStack() as stack:
            await stack.enter_async_context(self.app.test_app())
            fetch = stack.enter_context(patch.object(self.app.task_manager.problem_sync, "download", side_effect=download))
            client = self.app.test_client()
            headers = await self.login(client)
            for expected_skips in (0, 1):
                task = await self.submit(client, headers, limit=1)
                self.assertEqual(task["status"], "completed")
                self.assertEqual(task["result"]["success_count"], 1)
                self.assertEqual(task["result"]["skipped_count"], expected_skips)
            task = await self.submit(client, headers, limit=1)
            self.assertEqual(task["result"]["skipped_count"], 2)
            self.assertEqual(task["result"]["selected_count"], 0)
            self.assertEqual(fetch.await_count, 5)
            rows = await self.query("SELECT * FROM crawler_problems ORDER BY problem_id")
            self.assertEqual(len(rows), 2)
            self.assertEqual(json.loads(rows[0]["samples"]), [{"index": 1, "input": "1 0\n", "output": "Yes\n"}])
            self.assertIn("Sample Input 1", rows[0]["statement_html"])
            data = await (await client.get("/api/problems?platform=atcoder")).get_json()
            self.assertEqual(data["total"], 2)
            self.assertEqual({row["problem_name"] for row in data["items"]}, {"Raise Both Hands", "Binary Alchemy"})

    async def test_failed_refresh_preserves_previous_body_samples_and_catalog(self):
        async with self.app.test_app():
            client = self.app.test_client()
            headers = await self.login(client)
            with patch.object(self.app.task_manager.problem_sync, "download", side_effect=[LISTING, BODY]):
                await self.submit(client, headers, problem_ids=["abc370_a"])
            old = (await self.query("SELECT statement_html,samples,statement_sha256 FROM crawler_problems"))[0]
            for broken_page in (b"<h1>Sign in</h1>", b'<div id="task-statement"><p>Incomplete replacement</p></div>'):
                with patch.object(self.app.task_manager.problem_sync, "download", side_effect=[LISTING, broken_page]):
                    task = await self.submit(client, headers, problem_ids=["abc370_a"], refresh=True)
                self.assertEqual(task["status"], "failed")
                self.assertEqual(task["result"]["failure_count"], 1)
                self.assertEqual((await self.query("SELECT statement_html,samples,statement_sha256 FROM crawler_problems"))[0], old)
            self.assertEqual((await self.query("SELECT last_fetch_status FROM crawler_problems"))[0]["last_fetch_status"], "failed")
            self.assertEqual(len(await self.query("SELECT * FROM recommendations")), 1)

    async def test_cf_sync_normalizes_ids_and_updates_existing_catalog_without_duplicates(self):
        metadata = {"problems": [{"contestId": 1843, "index": "A", "name": "CF Example",
                                 "rating": 800, "tags": ["math"]}]}
        async with self.app.test_app():
            client = self.app.test_client()
            headers = await self.login(client)
            with patch("feat.api.acm_api.problem_sync.cf_request", return_value=metadata) as request_cf:
                with patch.object(self.app.task_manager.problem_sync, "download", return_value=CF_BODY) as fetch:
                    task = await self.submit(client, headers, platform="codeforces", contest_id=1843, problem_ids=["1843A", "cf_1843A"])
                    self.assertEqual(task["status"], "completed")
                    self.assertEqual(task["platform"], "codeforces")
                    self.assertEqual(task["result"]["success_count"], 1)
                    await self.submit(client, headers, platform="codeforces", contest_id="1843", problem_ids=["cf_1843A"])
                    self.assertEqual(fetch.await_count, 1)
                self.assertEqual(request_cf.await_args.args[1:], ("contest.standings", {"contestId": 1843}))
            rows = await self.query("SELECT * FROM crawler_problems")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["problem_id"], "cf_1843A")
            self.assertEqual(json.loads(rows[0]["samples"])[0]["input"], " 1 2\n3 4 \n")
            catalog = await (await client.get("/api/problems?platform=codeforces")).get_json()
            self.assertEqual(catalog["total"], 1)
            self.assertEqual(catalog["items"][0]["problem_rating"], "800")

    async def test_partial_failure_continues_and_unknown_ids_do_not_write(self):
        async with self.app.test_app():
            client = self.app.test_client()
            headers = await self.login(client)
            with patch.object(self.app.task_manager.problem_sync, "download", side_effect=[LISTING]):
                task = await self.submit(client, headers, problem_ids=["abc370_z"])
                self.assertEqual(task["status"], "failed")
                self.assertIn("不存在", task["result"]["error"])
            self.assertEqual(await self.query("SELECT * FROM crawler_problems"), [])
            with patch.object(self.app.task_manager.problem_sync, "download", side_effect=[LISTING, b"<h1>Sign in</h1>", BODY]):
                task = await self.submit(client, headers)
            self.assertEqual(task["status"], "partial")
            self.assertEqual((task["result"]["success_count"], task["result"]["failure_count"]), (1, 1))
            self.assertEqual((await self.query("SELECT problem_id FROM crawler_problems"))[0]["problem_id"], "abc370_b")

    async def test_same_task_merges_different_task_is_busy_and_cancel_stops_it(self):
        started = asyncio.Event()
        blocker = asyncio.Event()
        async def download(http, url):
            started.set()
            await blocker.wait()
            return LISTING
        async with AsyncExitStack() as stack:
            await stack.enter_async_context(self.app.test_app())
            stack.enter_context(patch.object(self.app.task_manager.problem_sync, "download", side_effect=download))
            client = self.app.test_client()
            headers = await self.login(client)
            payload = {"contest_id": "abc370"}
            response = await client.post("/api/admin/problems/sync", json=payload, headers=headers)
            task_id = (await response.get_json())["task"]["id"]
            await asyncio.wait_for(started.wait(), 5)
            repeated = await (await client.post("/api/admin/problems/sync", json=payload, headers=headers)).get_json()
            self.assertEqual(repeated["task"], {"id": task_id, "merged": True})
            busy = await client.post("/api/admin/problems/sync", json={"contest_id": "abc001"}, headers=headers)
            self.assertEqual(busy.status_code, 409)
            self.assertEqual((await busy.get_json())["code"], "problem_sync_busy")
            cancelled = await client.post(f"/api/tasks/{task_id}/cancel", json={}, headers=headers)
            self.assertEqual(cancelled.status_code, 200)
            with self.assertRaises(asyncio.CancelledError):
                await self.app.task_manager.tasks[task_id]["_task"]
            self.assertEqual(self.app.task_manager.tasks[task_id]["status"], "cancelled")
            self.assertEqual(await self.query("SELECT * FROM crawler_problems"), [])

    async def test_catalog_write_failure_rolls_back_problem_and_samples(self):
        await self.write("CREATE TRIGGER reject_problem BEFORE INSERT ON recommendations BEGIN SELECT RAISE(ABORT, 'write failed'); END")
        async with self.app.test_app():
            client = self.app.test_client()
            headers = await self.login(client)
            with patch.object(self.app.task_manager.problem_sync, "download", side_effect=[LISTING, BODY]):
                task = await self.submit(client, headers, problem_ids=["abc370_a"])
            self.assertEqual(task["status"], "failed")
            self.assertEqual(await self.query("SELECT * FROM crawler_problems"), [])
            self.assertEqual(await self.query("SELECT * FROM recommendations"), [])

    async def test_deployed_init_command_can_be_repeated_without_deleting_data(self):
        path = Path(self.directory.name) / "initialized.db"
        command = [sys.executable, "-X", "utf8", "-m", "api.init_db", "--database", str(path)]
        cwd = Path(__file__).resolve().parents[2]
        for iteration in range(2):
            result = await asyncio.to_thread(subprocess.run, command, cwd=cwd, capture_output=True, encoding="utf-8", timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            db = await connect_db(path)
            try:
                if not iteration:
                    await db.execute("INSERT INTO users(qq_id,name) VALUES('87654321','Preserved')")
                    await db.commit()
                async with db.execute("SELECT name FROM users WHERE qq_id='87654321'") as cursor:
                    self.assertEqual((await cursor.fetchone())[0], "Preserved")
                async with db.execute("SELECT COUNT(*) FROM crawler_problems") as cursor:
                    self.assertEqual((await cursor.fetchone())[0], 0)
            finally:
                await db.close()


if __name__ == "__main__":
    unittest.main()
