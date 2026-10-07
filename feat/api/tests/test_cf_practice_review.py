"""Regressions reproduced by the CF practice review (2026-10-07)."""
import asyncio
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import aiosqlite

from feat.api.acm_api import crawler
from feat.api.acm_api.auth_service import hash_password
from feat.api.acm_api.bot_api import _codeforces_api_call
from feat.api.acm_api.cf_client import CFUnavailable, cf_request
from feat.api.acm_api.cf_practice_jobs import PracticeJobs
from feat.api.acm_api.crawler import Crawler
from feat.api.acm_api.database import connect_db, validate_submission_data
from feat.api.app import create_app
from feat.api.service_runtime import SyncEngine
from feat.api.tests.test_cf_practice import DatabaseCase


class ReviewHistoryTests(DatabaseCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        await self.member(ready=False)
        self.engine = SyncEngine(self.path, {})
        self.engine.db = self.db

    def submission(self, sid, verdict="OK", age=100):
        return {"id": sid, "verdict": verdict, "creationTimeSeconds": self.now - age,
                "problem": {"contestId": 1843, "index": "A", "name": "Fixture A", "tags": []}}

    async def sync(self, rows):
        task = {}
        with patch("feat.api.acm_api.cf_history.cf_request", AsyncMock(return_value=rows)):
            await self.engine.sync_account("10000001", ["codeforces"], task, days=0)
        self.assertEqual(task["status"], "completed")

    async def test_repair_then_rejudge_removes_normalized_ac_and_recent_counts(self):
        await self.sync([self.submission(1)])
        await validate_submission_data(self.db, repair=True)
        await self.sync([self.submission(1, "WRONG_ANSWER")])
        result, _ = await self.check(candidates=["1843A"], mode="ac_only")
        self.assertEqual((result["rows"][0]["decision"], result["rows"][0]["ac_count"]), ("eligible", 0))
        self.assertEqual((await self.query.overview(self.db, {"scope": self.scope}))["total"], 0)
        self.assertEqual((await (await self.db.execute("SELECT COUNT(*) FROM submissions")).fetchone())[0], 0)

    async def test_repair_keeps_one_ac_key_and_rejudge_falls_back_to_older_ok(self):
        await self.sync([self.submission(1, age=100), self.submission(2, age=10)])
        await validate_submission_data(self.db, repair=True)
        await self.sync([self.submission(2, age=10)])
        rows = await (await self.db.execute("SELECT problem_id FROM submissions")).fetchall()
        self.assertEqual([row[0] for row in rows], ["1843A"])
        await self.sync([self.submission(2, "WRONG_ANSWER", age=10)])
        row = await (await self.db.execute("SELECT problem_id,submit_time FROM submissions")).fetchone()
        self.assertEqual(tuple(row), ("1843A", self.now - 100))
        result, _ = await self.check(candidates=["1843A"], mode="ac_only")
        self.assertEqual(result["rows"][0]["decision"], "excluded_ac")

    async def test_group_refresh_uses_cursor_and_partial_failure_keeps_old_progress(self):
        jobs = PracticeJobs(self.path, self.engine, self.query)
        history = [self.submission(i, age=30 * 86400 + i) for i in range(1000)]
        calls = []
        fail_second = False
        async def response(session, method, params, config):
            calls.append(params["from"])
            if fail_second and params["from"] == 101:
                raise CFUnavailable("page two failed")
            return history[params["from"] - 1:params["from"] - 1 + 100]
        try:
            with patch("feat.api.acm_api.cf_history.cf_request", response), patch.object(jobs, "refresh_metadata", AsyncMock(return_value=[])):
                first = await jobs.submit("sync", await self.payload())
                await asyncio.gather(*list(jobs.tasks))
                self.assertEqual((await jobs.get(first))["status"], "completed")
                self.assertEqual(calls, list(range(1, 1002, 100)))
                calls.clear()
                history.insert(0, self.submission(1001, age=60))
                second = await jobs.submit("sync", await self.payload())
                await asyncio.gather(*list(jobs.tasks))
                self.assertEqual((await jobs.get(second))["status"], "completed")
                self.assertEqual(calls, [1])
                before = await (await self.db.execute("SELECT cursor_timestamp,full_history_at,coverage_through_at FROM user_platform_sync_state WHERE platform='codeforces'")).fetchone()
                calls.clear()
                history[:0] = [self.submission(2000 + i, age=30) for i in range(200)]
                fail_second = True
                third = await jobs.submit("sync", await self.payload())
                await asyncio.gather(*list(jobs.tasks))
                self.assertEqual((await jobs.get(third))["status"], "failed")
                self.assertEqual(calls, [1, 101])
                after = await (await self.db.execute("SELECT cursor_timestamp,full_history_at,coverage_through_at FROM user_platform_sync_state WHERE platform='codeforces'")).fetchone()
                self.assertEqual(tuple(after), tuple(before))
        finally:
            await jobs.close()


class ReviewMetadataTests(DatabaseCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        await self.member()
        self.engine = AsyncMock()
        self.engine._http_session = None
        self.engine._crawler_config = lambda: {}
        self.jobs = PracticeJobs(self.path, self.engine, self.query)
        self.catalog = {"problems": [{"contestId": 1843, "index": index, "name": index, "tags": []} for index in ["A", "B"]]}

    async def asyncTearDown(self):
        await self.jobs.close()
        await super().asyncTearDown()

    async def test_concurrent_candidates_reuse_catalog_and_skip_redundant_contest(self):
        entered, release = asyncio.Event(), asyncio.Event()
        calls = []
        async def response(session, method, params=None, config=None):
            calls.append(method)
            self.assertEqual(method, "problemset.problems")
            entered.set()
            await release.wait()
            return self.catalog
        with patch("feat.api.acm_api.cf_practice_jobs.cf_request", response):
            first = await self.jobs.submit("check", await self.payload(candidates=["1843A"]))
            await entered.wait()
            second = await self.jobs.submit("check", await self.payload(candidates=["1843B"]))
            release.set()
            await asyncio.gather(*list(self.jobs.tasks))
        self.assertEqual(calls, ["problemset.problems"])
        for job_id in (first, second):
            job = await self.jobs.get(job_id)
            self.assertEqual(job["status"], "completed")
            self.assertTrue(job["result"]["rows"][0]["eligible"])

    async def test_catalog_ttl_survives_restart_and_unknown_uses_contest_only(self):
        request = AsyncMock(return_value=self.catalog)
        with patch("feat.api.acm_api.cf_practice_jobs.cf_request", request):
            await self.jobs.refresh_metadata({"catalog": True, "contests": []})
            restarted = PracticeJobs(self.path, self.engine, self.query)
            await restarted.start()
            await restarted.refresh_metadata({"catalog": True, "contests": []})
        self.assertEqual(request.await_count, 1)
        missing = {"catalog": True, "contests": [9999], "problems": ["9999A"]}
        request = AsyncMock(side_effect=CFUnavailable("unknown contest"))
        with patch("feat.api.acm_api.cf_practice_jobs.cf_request", request):
            self.assertTrue(await self.jobs.refresh_metadata(missing))
            self.assertTrue(await self.jobs.refresh_metadata(missing))
        self.assertEqual([call.args[1] for call in request.await_args_list], ["contest.standings"] * 2)
        await self.db.execute("UPDATE settings SET value=? WHERE key='cf_problem_catalog_verified_at'", (str(self.now - self.query.problem_ttl - 1),))
        await self.db.commit()
        request = AsyncMock(return_value=self.catalog)
        with patch("feat.api.acm_api.cf_practice_jobs.cf_request", request):
            await self.jobs.refresh_metadata({"catalog": True, "contests": []})
        self.assertEqual(request.await_count, 1)

    async def test_bad_catalog_does_not_stamp_success_or_write_partial_problems(self):
        bad = {"problems": [self.catalog["problems"][0], {"contestId": 1843, "index": "B", "tags": {}}]}
        with patch("feat.api.acm_api.cf_practice_jobs.cf_request", AsyncMock(return_value=bad)):
            self.assertTrue(await self.jobs.refresh_metadata({"catalog": True}))
        self.assertIsNone(await (await self.db.execute("SELECT value FROM settings WHERE key='cf_problem_catalog_verified_at'")).fetchone())
        self.assertEqual((await (await self.db.execute("SELECT COUNT(*) FROM cf_problem_cache")).fetchone())[0], 0)


class ReviewApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "api.db"
        self.env = patch.dict(os.environ, {"ACM_DATABASE_PATH": str(self.path), "ACM_WEBUI_SECRET_KEY": "review-test-secret", "ACM_BOT_API_TOKEN": "review-concurrency-fixture-token"})
        self.env.start()
        self.app = create_app()

    async def asyncTearDown(self):
        self.env.stop()
        self.directory.cleanup()

    async def login(self, client):
        db = await connect_db(self.path)
        try:
            now = int(time.time())
            await db.execute("INSERT INTO users(qq_id,name,status,cf_handle) VALUES('10000001','测试成员','现役','alpha')")
            await db.execute("INSERT INTO web_accounts(qq_id,password_hash,role,must_change_password,is_active,credential_version,created_at,updated_at) VALUES('10000001',?,'root',0,1,1,?,?)", (hash_password("review-password-123"), now, now))
            await db.execute("INSERT INTO cf_problem_cache VALUES(1843,'A','Fixture A',800,'[]',?)", (now,))
            await db.execute("INSERT INTO submissions(user_qq_id,platform,problem_id,submit_time) VALUES('10000001','codeforces','cf_1843A',?)", (now,))
            await db.commit()
        finally:
            await db.close()
        response = await client.post("/api/auth/login", json={"qq_id": "10000001", "password": "review-password-123"})
        return {"X-CSRF-Token": (await response.get_json())["csrf_token"]}

    async def concurrent_rebind(self, bot_route, *, cancel_page=False):
        paused, resume = asyncio.Event(), asyncio.Event()
        bot_write_attempted, rebind_write_attempted = asyncio.Event(), asyncio.Event()
        writer = None
        original_store = crawler._store_cf_attempts
        original_execute = aiosqlite.Connection.execute
        now = int(time.time())
        old_ac = {"id": 7654321, "verdict": "OK", "creationTimeSeconds": now - 120,
                  "problem": {"contestId": 1843, "index": "A", "name": "Old handle only", "tags": []}}

        async def response(session, method, params=None, config=None):
            self.assertEqual(method, "user.status")
            return [old_ac] if params["handle"] == "alpha" else []

        async def pause_after_binding_check(db, qq_id, page, *, commit=True):
            nonlocal writer
            if str(qq_id) == "10000001" and page:
                writer = db
                paused.set()
                await resume.wait()
            return await original_store(db, qq_id, page, commit=commit)

        def observe_rebind(db, sql, *args, **kwargs):
            if sql.startswith("UPDATE users SET name=?, real_name=?, cf_handle=?"):
                rebind_write_attempted.set()
            return original_execute(db, sql, *args, **kwargs)

        async with self.app.test_app():
            client = self.app.test_client()
            headers = await self.login(client)
            db = await connect_db(self.path)
            try:
                await db.execute("DELETE FROM submissions WHERE user_qq_id='10000001'")
                await db.execute("INSERT INTO users(qq_id,name,status,cf_handle) VALUES('10000002','Bot fixture','别组','bot_fixture')")
                await db.execute("INSERT INTO random_challenges(qq_id,platform,problem_id,problem_url,challenge_rating,time_limit_minutes,zone,created_at,expires_at) VALUES('10000002','codeforces','cf_1843D','https://codeforces.com/contest/1843/problem/D',1000,60,'foundation',?,?)", (now - 60, now + 3600))
                await db.commit()
            finally:
                await db.close()
            scope = {"statuses": ["现役"]}
            overview = await (await client.post("/api/admin/cf/overview", json={"scope": scope}, headers=headers)).get_json()
            engine, jobs = self.app.sync_engine, self.app.config["CF_PRACTICE_JOBS"]
            original_state = engine._get_platform_sync_state

            async def observe_bot_write(qq_id, *args, **kwargs):
                if str(qq_id) == "10000002":
                    bot_write_attempted.set()
                return await original_state(qq_id, *args, **kwargs)

            requests = []
            with patch("feat.api.acm_api.cf_history.cf_request", response), patch("feat.api.acm_api.cf_practice_jobs.cf_request", AsyncMock(return_value={"problems": [old_ac["problem"]]})), patch("feat.api.acm_api.crawler._store_cf_attempts", pause_after_binding_check), patch.object(engine, "_get_platform_sync_state", observe_bot_write), patch.object(aiosqlite.Connection, "execute", observe_rebind):
                try:
                    queued = await client.post("/api/admin/cf/sync", json={"scope": scope, "expected_scope_fingerprint": overview["scope"]["fingerprint"]}, headers=headers)
                    self.assertEqual(queued.status_code, 202)
                    job_id = (await queued.get_json())["job_id"]
                    await asyncio.wait_for(paused.wait(), 3)
                    self.assertTrue(writer.in_transaction)
                    bot_request = asyncio.create_task(client.post(bot_route, json={}, headers={"Authorization": "Bearer review-concurrency-fixture-token"}))
                    requests.append(bot_request)
                    await asyncio.wait_for(bot_write_attempted.wait(), 3)
                    rebind_request = asyncio.create_task(client.put("/api/user", json={"qq_id": "10000001", "name": "Rebound fixture", "status": "现役", "cf_handle": "new_empty_fixture"}, headers=headers))
                    requests.append(rebind_request)
                    await asyncio.wait_for(rebind_write_attempted.wait(), 3)
                    # Both production routes have reached their write boundaries.
                    # Their commits must neither end the page nor admit a rebind within it.
                    self.assertIsNot(writer, engine.db)
                    self.assertTrue(writer.in_transaction)
                    self.assertFalse(bot_request.done())
                    self.assertFalse(rebind_request.done())
                    if cancel_page:
                        active = list(jobs.tasks)
                        for task in active:
                            task.cancel()
                        await asyncio.gather(*active, return_exceptions=True)
                    else:
                        resume.set()
                    bot_response, rebind_response = await asyncio.wait_for(asyncio.gather(*requests), 10)
                    self.assertEqual(bot_response.status_code, 409)
                    self.assertEqual(rebind_response.status_code, 202)
                    task_id = (await rebind_response.get_json())["task_id"]
                    await asyncio.wait_for(asyncio.gather(*list(jobs.tasks)), 10)
                    await asyncio.wait_for(self.app.task_manager.tasks[task_id]["_task"], 10)
                    self.assertEqual(self.app.task_manager.tasks[task_id]["status"], "completed")
                    latest = await (await client.post("/api/admin/cf/overview", json={"scope": scope}, headers=headers)).get_json()
                    self.assertEqual(latest["scope"]["ready_member_count"], 1)
                    checked = await client.post("/api/admin/cf/check", json={"scope": scope, "expected_scope_fingerprint": latest["scope"]["fingerprint"], "candidates": ["1843A"], "mode": "ac_only"}, headers=headers)
                    self.assertEqual(checked.status_code, 200)
                    row = (await checked.get_json())["rows"][0]
                    self.assertEqual((row["decision"], row["ac_count"], row["attempt_count"]), ("eligible", 0, 0))
                    db = await connect_db(self.path)
                    try:
                        for table, owner in [("submissions", "user_qq_id"), ("submission_attempts", "owner_qq_id")]:
                            count = (await (await db.execute(f"SELECT COUNT(*) FROM {table} WHERE {owner}='10000001'")).fetchone())[0]
                            self.assertEqual(count, 0)
                        if cancel_page:
                            status = (await (await db.execute("SELECT status FROM cf_practice_jobs WHERE id=?", (job_id,))).fetchone())[0]
                            self.assertEqual(status, "interrupted")
                    finally:
                        await db.close()
                finally:
                    resume.set()
                    await asyncio.gather(*requests, *list(jobs.tasks), return_exceptions=True)

    async def test_group_page_bot_challenge_and_rebind_preserve_account_isolation(self):
        await self.concurrent_rebind("/internal/v1/users/10000002/random-challenges/done")

    async def test_group_page_bot_training_and_rebind_preserve_account_isolation(self):
        await self.concurrent_rebind("/internal/v1/users/10000002/training/foundation/complete")

    async def test_cancelled_page_releases_writer_and_rebind_remains_clean(self):
        await self.concurrent_rebind("/internal/v1/users/10000002/random-challenges/done", cancel_page=True)

    async def test_malformed_url_is_an_invalid_row_and_enum_types_return_json_400(self):
        async with self.app.test_app():
            client = self.app.test_client()
            headers = await self.login(client)
            scope = {"statuses": ["现役"]}
            overview = await (await client.post("/api/admin/cf/overview", headers=headers, json={"scope": scope})).get_json()
            base = {"scope": scope, "expected_scope_fingerprint": overview["scope"]["fingerprint"], "candidates": ["1843A"]}
            malformed = "https://[codeforces.com/contest/1843/problem/B"
            response = await client.post("/api/admin/cf/check", headers=headers, json={**base, "candidates": ["1843A", malformed]})
            self.assertEqual(response.status_code, 200)
            self.assertEqual([row["decision"] for row in (await response.get_json())["rows"]], ["excluded_ac", "invalid"])
            for route, field, extra in [("check", "mode", {}), ("overview", "view", {}), ("problem-members", "period", {"problem_id": "1843A"})]:
                for value in ([], {}, None, True, 1):
                    with self.subTest(route=route, value=value):
                        response = await client.post("/api/admin/cf/" + route, headers=headers, json={**base, **extra, field: value})
                        self.assertEqual(response.status_code, 400)
                        self.assertEqual((await response.get_json())["code"], "invalid_request")

    async def test_legacy_cf_routes_and_new_requests_share_actual_pacing(self):
        starts = []
        class Response:
            def __init__(self, method):
                self.method = method
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                return False
            def raise_for_status(self):
                pass
            async def json(self):
                await asyncio.sleep(.01)
                return {"status": "OK", "result": [{"handle": "alpha"}] if self.method == "user.info" else []}
        class Session:
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                return False
            def get(self, url, **kwargs):
                starts.append(time.monotonic())
                return Response(url.rsplit("/", 1)[-1])
        async with self.app.test_app():
            client = self.app.test_client()
            await self.login(client)
            session = Session()
            original = self.app.sync_engine._http_session
            self.app.sync_engine._http_session = session
            try:
                with patch("feat.api.acm_api.backend_api.aiohttp.ClientSession", return_value=session):
                    async with self.app.app_context():
                        results = await asyncio.gather(
                            cf_request(session, "user.status", {"handle": "alpha"}),
                            _codeforces_api_call("user.status", {"handle": "alpha"}),
                            Crawler._validate_cf_account(session, "alpha", {}),
                            Crawler._fetch_recent_cf_ac(session, {"cf_handle": "alpha"}, 0, 10, {}),
                            client.get("/api/member/10000001"),
                        )
                self.assertEqual(results[2], (True, "alpha"))
                self.assertEqual(results[-1].status_code, 200)
                self.assertEqual(len(starts), 6)
                self.assertTrue(all(b - a >= 2.08 for a, b in zip(starts, starts[1:])))
            finally:
                self.app.sync_engine._http_session = original


if __name__ == "__main__":
    unittest.main()
