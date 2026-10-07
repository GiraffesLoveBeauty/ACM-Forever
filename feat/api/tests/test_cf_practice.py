"""CF practice contracts with temporary databases and deterministic OJ responses."""
import asyncio
import json
import os
import sqlite3
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import AsyncMock, patch

import aiohttp

from feat.api.acm_api.auth_service import hash_password
from feat.api.acm_api.cf_client import CFUnavailable, binding_key
from feat.api.acm_api.cf_client import cf_request
from feat.api.acm_api.cf_practice import (
    PracticeError, PracticeQuery, candidate_input, normalize_problem, options, resolve_scope,
)
from feat.api.acm_api.cf_practice_jobs import PracticeJobs
from feat.api.acm_api.database import connect_db
from feat.api.app import create_app
from feat.api.service_runtime import SyncEngine


class DatabaseCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "cf.db"
        self.db = await connect_db(self.path)
        self.now = int(time.time())
        self.query = PracticeQuery()
        self.scope = {"statuses": ["现役"], "exclude_qq_ids": []}

    async def asyncTearDown(self):
        await self.db.close()
        self.directory.cleanup()

    async def member(self, qq="10000001", handle="alpha", status="现役", ready=True):
        await self.db.execute("INSERT INTO users(qq_id,name,status,cf_handle) VALUES(?,?,?,?)", (qq, "成员" + qq[-2:], status, handle))
        if ready and handle:
            await self.db.execute("INSERT OR REPLACE INTO user_platform_sync_state(user_qq_id,platform,binding_key,full_history_at,coverage_through_at,last_success_at,last_status) VALUES(?,'codeforces',?,?,?,?, 'success')", (qq, handle.casefold() + ":0", self.now - 100, self.now - 60, self.now - 30))
        await self.db.commit()

    async def problem(self, pid="1843A", rating=800, age=0):
        item = normalize_problem(pid)
        await self.db.execute("INSERT OR REPLACE INTO cf_problem_cache VALUES(?,?,?,?,?,?)", (item["contest_id"], item["index"], "题目 " + pid, rating, '["math"]', self.now - age))
        await self.db.commit()

    async def attempt(self, qq, sid, pid, verdict="OK", age=100):
        item = normalize_problem(pid)
        await self.db.execute("INSERT INTO submission_attempts(owner_qq_id,platform,external_submission_id,problem_id,contest_id,verdict,submitted_at,created_at) VALUES(?,'codeforces',?,?,?,?,?,?)", (qq, f"{qq}:{sid}", "cf_" + pid, str(item["contest_id"]), verdict, self.now - age, self.now))
        await self.db.commit()

    async def legacy_ac(self, qq, pid, age):
        await self.db.execute("INSERT INTO submissions(user_qq_id,platform,problem_id,submit_time) VALUES(?,'codeforces',?,?)", (qq, "cf_" + pid, self.now - age))
        await self.db.commit()

    async def payload(self, **extra):
        public, _ = await resolve_scope(self.db, {"scope": self.scope}, 86400)
        await self.db.commit()
        return {"scope": self.scope, "expected_scope_fingerprint": public["fingerprint"], **extra}

    async def check(self, **extra):
        return await self.query.check(self.db, await self.payload(**extra))


class PracticeQueryTests(DatabaseCase):
    async def test_old_database_migration_preserves_evidence_without_claiming_full_history(self):
        legacy_path = Path(self.directory.name) / "legacy.db"
        with closing(sqlite3.connect(legacy_path)) as old:
            old.execute("CREATE TABLE users(qq_id TEXT PRIMARY KEY,name TEXT NOT NULL,cf_handle TEXT,luogu_id TEXT,nowcoder_id TEXT,atcoder_handle TEXT,status TEXT,school TEXT,last_sync_timestamp INTEGER DEFAULT 0)")
            old.execute("CREATE TABLE user_platform_sync_state(user_qq_id TEXT NOT NULL,platform TEXT NOT NULL,cursor_timestamp INTEGER NOT NULL DEFAULT 0,last_attempt_at INTEGER NOT NULL DEFAULT 0,last_success_at INTEGER NOT NULL DEFAULT 0,last_status TEXT NOT NULL DEFAULT 'never',last_error_code TEXT,last_error_message TEXT,consecutive_failures INTEGER NOT NULL DEFAULT 0,next_retry_at INTEGER NOT NULL DEFAULT 0,updated_at INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(user_qq_id,platform))")
            old.execute("CREATE TABLE submissions(id INTEGER PRIMARY KEY AUTOINCREMENT,user_qq_id TEXT NOT NULL,platform TEXT NOT NULL,problem_id TEXT NOT NULL,problem_name TEXT,problem_rating TEXT,problem_url TEXT,tags TEXT NOT NULL DEFAULT '',submit_time INTEGER NOT NULL,UNIQUE(user_qq_id,platform,problem_id))")
            old.execute("INSERT INTO users(qq_id,name,cf_handle,status,last_sync_timestamp) VALUES('10000001','老成员','alpha','现役',?)", (self.now,))
            old.execute("INSERT INTO user_platform_sync_state(user_qq_id,platform,cursor_timestamp,last_success_at,last_status) VALUES('10000001','codeforces',?,?,'success')", (self.now, self.now))
            old.execute("INSERT INTO submissions(user_qq_id,platform,problem_id,submit_time) VALUES('10000001','codeforces','cf_1843A',?)", (self.now - 86400,))
            old.commit()
        for _ in range(2):
            upgraded = await connect_db(legacy_path)
            try:
                public, _ = await resolve_scope(upgraded, {"scope": self.scope}, 86400)
                self.assertEqual(public["members"][0]["reason"], "history_incomplete")
                user = await (await upgraded.execute("SELECT * FROM users")).fetchone()
                self.assertEqual(binding_key(user), "alpha:0")
                state = await (await upgraded.execute("SELECT * FROM user_platform_sync_state WHERE platform='codeforces'")).fetchone()
                self.assertEqual((state["cursor_timestamp"], state["full_history_at"]), (self.now, 0))
                result, _ = await self.query.check(upgraded, {"scope": self.scope, "expected_scope_fingerprint": public["fingerprint"], "candidates": ["1843A"]})
                self.assertEqual((result["rows"][0]["decision"], result["rows"][0]["attempt_count"]), ("excluded_ac", 1))
            finally:
                await upgraded.close()

    def test_normalization_deduplication_and_limits(self):
        _, _, rows = candidate_input({"candidates": ["cf_1843a", "1843 A", "https://codeforces.com/problemset/problem/1843/A?locale=en", "https://codeforces.com/gym/104123/problem/A1", "bad", "https://evil.example/1843A"]})
        self.assertEqual([r["display_id"] for r in rows[:2]], ["1843A", "104123A1"])
        self.assertEqual(len(rows[0]["inputs"]), 3)
        self.assertEqual(sum("invalid_reason" in r for r in rows), 2)
        for payload in ({"candidates": [], "contest_id": 1}, {"candidates": ["1A"] * 101}, {"candidates": [f"{n}A" for n in range(1, 22)]}, {"contest_id": True}, {"candidates": ["1A"], "mode": "unsafe"}):
            with self.subTest(payload=payload), self.assertRaises(PracticeError):
                candidate_input(payload)

    async def test_statuses_exclusions_unbound_and_common_minimum_coverage(self):
        await self.member()
        await self.member("10000002", "beta")
        await self.member("10000003", None)
        await self.member("10000004", "other", status="退役")
        choices = await options(self.db)
        self.assertEqual({row["value"]: row["member_count"] for row in choices["statuses"]}, {"现役": 3, "退役": 1})
        public, _ = await resolve_scope(self.db, {"scope": self.scope}, 86400)
        self.assertEqual((public["member_count"], public["ready_member_count"], public["unknown_member_count"]), (3, 2, 1))
        self.assertIsNone(public["coverage_as_of"])
        self.scope["exclude_qq_ids"] = ["10000003"]
        await self.db.execute("UPDATE user_platform_sync_state SET coverage_through_at=? WHERE user_qq_id='10000002'", (self.now - 600,))
        public, _ = await resolve_scope(self.db, {"scope": self.scope}, 86400)
        self.assertEqual(public["member_count"], 2)
        self.assertIn(time.strftime("%H:%M:%S", time.gmtime(self.now - 600 + 8 * 3600)), public["coverage_as_of"])

    async def test_binding_generation_blocks_aba_and_clears_only_cf_history(self):
        await self.member()
        await self.attempt("10000001", 1, "1843A")
        await self.legacy_ac("10000001", "1843A", 100)
        await self.db.execute("INSERT INTO submissions(user_qq_id,platform,problem_id,submit_time) VALUES('10000001','atcoder','abc1_a',?)", (self.now,))
        data = await self.payload(candidates=["1843A"])
        await self.db.execute("UPDATE users SET cf_handle='ALPHA' WHERE qq_id='10000001'")
        await self.db.commit()
        await self.query.check(self.db, data)  # case-only changes keep the same binding
        await self.db.execute("UPDATE users SET cf_handle='second' WHERE qq_id='10000001'")
        await self.db.execute("UPDATE users SET cf_handle='alpha' WHERE qq_id='10000001'")
        await self.db.commit()
        with self.assertRaises(PracticeError) as error:
            await self.query.check(self.db, data)
        self.assertEqual((error.exception.status, error.exception.code), (409, "scope_changed"))
        self.assertEqual((await (await self.db.execute("SELECT cf_binding_version FROM users")).fetchone())[0], 2)
        self.assertEqual((await (await self.db.execute("SELECT COUNT(*) FROM submission_attempts")).fetchone())[0], 0)
        self.assertEqual((await (await self.db.execute("SELECT platform FROM submissions")).fetchone())[0], "atcoder")

    async def test_member_identity_and_exclusion_changes_invalidate_fingerprint(self):
        await self.member()
        data = await self.payload(candidates=["1843A"])
        await self.member("10000002", "beta")
        with self.assertRaises(PracticeError) as error:
            await self.query.check(self.db, data)
        self.assertEqual(error.exception.code, "scope_changed")
        data = await self.payload(candidates=["1843A"])
        data["scope"] = {"statuses": ["现役"], "exclude_qq_ids": ["10000002"]}
        with self.assertRaises(PracticeError):
            await self.query.check(self.db, data)
        await self.db.execute("UPDATE users SET status='退役' WHERE qq_id='10000001'")
        await self.db.commit()
        with self.assertRaises(PracticeError):
            await self.query.check(self.db, data)

    async def test_recent_repeated_ac_counts_and_history_are_separate(self):
        await self.member()
        await self.member("10000002", "beta")
        await self.problem(rating=None)
        await self.attempt("10000001", 1, "1843A", age=200)
        await self.attempt("10000001", 2, "1843A", age=100)
        await self.legacy_ac("10000002", "1843A", 40 * 86400)
        overview = await self.query.overview(self.db, {"scope": self.scope, "days": 7})
        row = overview["rows"][0]
        self.assertEqual((row["recent_ac_count"], row["history_ac_count"], row["rating"]), (1, 2, None))
        evidence = await self.query.problem_members(self.db, {"scope": self.scope, "problem_id": "1843A", "period": "recent"})
        self.assertEqual(evidence["total"], 1)
        self.assertTrue(evidence["rows"][0]["ac_submission_url"].endswith("/2"))
        history = await self.query.problem_members(self.db, {"scope": self.scope, "problem_id": "1843A", "period": "history", "days": 1})
        self.assertEqual(history["total"], 2)
        result, _ = await self.check(candidates=["1843A"], days=1, rating_min=5000, search="no match")
        self.assertEqual((result["rows"][0]["ac_count"], result["rows"][0]["attempt_count"]), (2, 2))
        self.assertEqual((await self.query.overview(self.db, {"scope": self.scope, "rating_min": 800}))["total"], 0)

    async def test_wa_modes_and_legacy_ac_member_counts(self):
        await self.member()
        for pid in ["1843A", "1843B", "1843C"]:
            await self.problem(pid)
        await self.legacy_ac("10000001", "1843A", 40 * 86400)
        await self.attempt("10000001", 1, "1843B", "WRONG_ANSWER")
        await self.attempt("10000001", 2, "1843B", "WRONG_ANSWER")
        strict, pending = await self.check(candidates=["1843A", "1843B", "1843C", "bad"])
        self.assertIsNone(pending)
        self.assertEqual([r["decision"] for r in strict["rows"]], ["excluded_ac", "excluded_attempted", "eligible", "invalid"])
        self.assertEqual([r["attempt_count"] for r in strict["rows"]], [1, 1, 0, 0])
        ac_only, _ = await self.check(candidates=["1843B"], mode="ac_only")
        self.assertTrue(ac_only["rows"][0]["eligible"])

    async def test_missing_participants_do_not_override_positive_evidence(self):
        await self.member()
        await self.member("10000002", None)
        await self.attempt("10000001", 1, "1843A")
        await self.attempt("10000001", 2, "1843B", "WRONG_ANSWER")
        await self.problem("1843C")
        result, _ = await self.check(candidates=["1843A", "1843B", "1843C"])
        self.assertEqual([r["decision"] for r in result["rows"]], ["excluded_ac", "excluded_attempted", "unknown"])

    async def test_readiness_failed_interrupted_running_stale_incomplete_binding(self):
        await self.member()
        await self.problem()
        for sql, params, reason in [
            ("last_status=?", ("failed",), "sync_failed"),
            ("last_status=?", ("interrupted",), "sync_interrupted"),
            ("last_status=?", ("running",), "sync_in_progress"),
            ("coverage_through_at=?", (self.now - 90000,), "stale"),
            ("full_history_at=?", (0,), "history_incomplete"),
            ("binding_key=?", ("old:0",), "binding_changed"),
        ]:
            with self.subTest(reason=reason):
                await self.db.execute("UPDATE user_platform_sync_state SET last_status='success',full_history_at=?,coverage_through_at=?,binding_key='alpha:0'", (self.now, self.now))
                await self.db.execute("UPDATE user_platform_sync_state SET " + sql, params)
                await self.db.commit()
                result, _ = await self.check(candidates=["1843A"])
                self.assertEqual(result["rows"][0]["decision"], "unknown")
                self.assertEqual(result["scope"]["members"][0]["reason"], reason)

    async def test_empty_scope_and_authoritative_absence(self):
        await self.member()
        await self.problem()
        self.scope["exclude_qq_ids"] = ["10000001"]
        result, pending = await self.check(candidates=["1843A", "9999A"])
        self.assertEqual(result["status"], "empty_scope")
        self.assertTrue(all(r["decision"] == "unknown" for r in result["rows"]))
        self.assertIsNone(pending)
        self.scope["exclude_qq_ids"] = []
        await self.db.execute("INSERT INTO cf_contest_cache VALUES(1843,'[\"A\",\"B\"]',?)", (self.now,))
        await self.problem("1843B")
        await self.db.commit()
        result, _ = await self.check(candidates=["1843Z"])
        self.assertEqual(result["rows"][0]["decision"], "invalid")
        contest, pending = await self.check(contest_id=1843)
        self.assertEqual([r["display_id"] for r in contest["rows"]], ["1843A", "1843B"])
        self.assertIsNone(pending)

    async def test_pagination_filters_and_timezone_validation(self):
        await self.member()
        for i in range(1, 24):
            await self.problem(f"{i}A", 800 if i % 2 else 1600)
            await self.attempt("10000001", i, f"{i}A", age=i * 10)
        data = await self.query.overview(self.db, {"scope": self.scope, "page": 2, "page_size": 20})
        self.assertEqual((data["total"], len(data["rows"])), (23, 3))
        filtered = await self.query.overview(self.db, {"scope": self.scope, "rating_min": 1500, "tag": "math", "view": "members"})
        self.assertEqual(filtered["rows"][0]["recent_ac_count"], 11)
        for parameters in ({"date_from": "2026-10-01", "date_to": "2026-10-02"}, {"page_size": 101}, {"rating_min": 1800, "rating_max": 800}):
            with self.subTest(parameters=parameters), self.assertRaises(PracticeError):
                await self.query.overview(self.db, {"scope": self.scope, **parameters})


class PracticeHistoryTests(DatabaseCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        await self.member(ready=False)
        self.engine = SyncEngine(self.path, {})
        self.engine.db = self.db

    def submission(self, sid, verdict="OK", age=100, pid="1843A"):
        item = normalize_problem(pid)
        return {"id": sid, "verdict": verdict, "creationTimeSeconds": self.now - age, "problem": {"contestId": item["contest_id"], "index": item["index"], "name": pid, "tags": []}}

    async def state_row(self):
        return dict(await (await self.db.execute("SELECT * FROM user_platform_sync_state WHERE user_qq_id='10000001' AND platform='codeforces'")).fetchone())

    async def sync(self, request):
        task = {}
        with patch("feat.api.acm_api.cf_history.cf_request", request):
            await self.engine.sync_account("10000001", ["codeforces"], task)
        return task

    async def test_full_and_incremental_paging_cover_more_than_100_submissions(self):
        history = [self.submission(i, age=i) for i in range(250, 0, -1)]
        history.sort(key=lambda s: s["creationTimeSeconds"], reverse=True)
        async def pages(session, method, params, config):
            return history[params["from"] - 1:params["from"] - 1 + 100]
        request = AsyncMock(side_effect=pages)
        self.assertEqual((await self.sync(request))["status"], "completed")
        self.assertEqual(request.await_count, 3)
        state = await self.state_row()
        self.assertTrue(state["full_history_at"])
        self.assertEqual(state["cursor_timestamp"], state["coverage_through_at"])
        old_full = state["full_history_at"]
        history = [self.submission(i, age=i) for i in range(500, 250, -1)] + history
        history.sort(key=lambda s: s["creationTimeSeconds"], reverse=True)
        request.reset_mock()
        task = {}
        with patch("feat.api.acm_api.cf_history.cf_request", request):
            self.assertTrue(await self.engine.sync_single_user("10000001"))
        self.assertEqual(request.await_count, 6)  # includes the terminal empty page
        self.assertEqual((await (await self.db.execute("SELECT COUNT(*) FROM submission_attempts")).fetchone())[0], 500)
        self.assertEqual((await self.state_row())["full_history_at"], old_full)

    async def test_second_page_failure_keeps_partial_evidence_without_complete_marker(self):
        request = AsyncMock(side_effect=[[self.submission(i) for i in range(100)], CFUnavailable("429")])
        self.assertEqual((await self.sync(request))["status"], "failed")
        state = await self.state_row()
        self.assertEqual((state["full_history_at"], state["coverage_through_at"], state["cursor_timestamp"]), (0, 0, 0))
        self.assertEqual((await (await self.db.execute("SELECT COUNT(*) FROM submission_attempts")).fetchone())[0], 100)
        result, _ = await self.check(candidates=["1843A", "1843B"])
        self.assertEqual([r["decision"] for r in result["rows"]], ["excluded_ac", "unknown"])

    async def test_incremental_failure_does_not_advance_old_cursor(self):
        await self.sync(AsyncMock(return_value=[]))
        await self.db.execute("UPDATE user_platform_sync_state SET cursor_timestamp=?,coverage_through_at=?,full_history_at=?", (self.now - 3600,) * 3)
        await self.db.commit()
        request = AsyncMock(side_effect=[[self.submission(i) for i in range(100)], CFUnavailable("timeout")])
        with patch("feat.api.acm_api.cf_history.cf_request", request):
            self.assertFalse(await self.engine.sync_single_user("10000001"))
        state = await self.state_row()
        self.assertEqual((state["cursor_timestamp"], state["full_history_at"], state["coverage_through_at"]), (self.now - 3600,) * 3)

    async def test_verdict_updates_and_rejudged_ac_recent_time(self):
        await self.sync(AsyncMock(return_value=[self.submission(1, "TESTING")]))
        await self.sync(AsyncMock(return_value=[self.submission(1, "OK")]))
        self.assertEqual((await (await self.db.execute("SELECT verdict FROM submission_attempts")).fetchone())[0], "OK")
        await self.sync(AsyncMock(return_value=[self.submission(2, "OK", age=10)]))
        await self.sync(AsyncMock(return_value=[self.submission(2, "WRONG_ANSWER", age=10)]))
        self.assertEqual((await (await self.db.execute("SELECT submit_time FROM submissions")).fetchone())[0], self.now - 100)
        await self.sync(AsyncMock(return_value=[self.submission(1, "WRONG_ANSWER")]))
        self.assertEqual((await (await self.db.execute("SELECT COUNT(*) FROM submissions")).fetchone())[0], 0)
        result, _ = await self.check(candidates=["1843A"], mode="ac_only")
        self.assertEqual(result["rows"][0]["decision"], "eligible")

    async def test_rebind_during_paging_rejects_stale_account_writes(self):
        count = 0
        async def rebind(session, method, params, config):
            nonlocal count
            count += 1
            if count == 1:
                return [self.submission(i) for i in range(100)]
            other = await connect_db(self.path)
            try:
                await other.execute("UPDATE users SET cf_handle='second' WHERE qq_id='10000001'")
                await other.execute("UPDATE users SET cf_handle='alpha' WHERE qq_id='10000001'")
                await other.commit()
            finally:
                await other.close()
            return [self.submission(101)]
        self.assertEqual((await self.sync(AsyncMock(side_effect=rebind)))["status"], "failed")
        self.assertEqual((await (await self.db.execute("SELECT COUNT(*) FROM submission_attempts")).fetchone())[0], 0)
        public, _ = await resolve_scope(self.db, {"scope": self.scope}, 86400)
        self.assertEqual(public["ready_member_count"], 0)

    async def test_cancel_and_malformed_page_never_mark_history_complete(self):
        for response in ([{"id": 1}], asyncio.CancelledError()):
            request = AsyncMock(side_effect=response if isinstance(response, BaseException) else None, return_value=response)
            if isinstance(response, BaseException):
                with self.assertRaises(asyncio.CancelledError):
                    await self.sync(request)
            else:
                self.assertEqual((await self.sync(request))["status"], "failed")
            self.assertEqual((await self.state_row())["full_history_at"], 0)


class PracticeJobTests(DatabaseCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        await self.member()
        self.engine = AsyncMock()
        self.engine._http_session = None
        self.engine._crawler_config = lambda: {}
        self.jobs = PracticeJobs(self.path, self.engine, self.query)

    async def asyncTearDown(self):
        await self.jobs.close()
        await super().asyncTearDown()

    async def wait_jobs(self):
        await asyncio.gather(*list(self.jobs.tasks))

    async def test_partial_member_results_and_unexpected_error_are_terminal(self):
        await self.member("10000002", None)
        async def succeed(qq, platforms, task, days, *, incremental=False):
            self.assertTrue(incremental)
            task["status"] = "completed"
        self.engine.sync_account.side_effect = succeed
        with patch.object(self.jobs, "refresh_metadata", AsyncMock(return_value=[])):
            job_id = await self.jobs.submit("sync", await self.payload())
            await self.wait_jobs()
        job = await self.jobs.get(job_id)
        self.assertEqual((job["status"], job["completed_member_count"], job["failed_member_count"]), ("partial", 1, 1))
        self.engine.sync_account.side_effect = RuntimeError("unexpected")
        job_id = await self.jobs.submit("sync", await self.payload())
        await self.wait_jobs()
        job = await self.jobs.get(job_id)
        self.assertEqual(job["status"], "failed")
        self.assertTrue(all(m["status"] == "failed" for m in job["members"]))

    async def test_restart_marks_persisted_jobs_and_members_interrupted(self):
        data = await self.payload()
        await self.db.execute("INSERT INTO cf_practice_jobs(id,kind,status,payload,scope_fingerprint,created_at) VALUES('restart','sync','running',?,?,?)", (json.dumps(data), data["expected_scope_fingerprint"], self.now))
        await self.db.execute("INSERT INTO cf_practice_job_members(job_id,qq_id,status) VALUES('restart','10000001','queued')")
        await self.db.execute("UPDATE user_platform_sync_state SET last_status='running'")
        await self.db.commit()
        await self.jobs.start()
        job = await self.jobs.get("restart")
        self.assertEqual(job["status"], "interrupted")
        self.assertEqual(job["members"][0]["status"], "interrupted")
        result, _ = await self.check(candidates=["1843A"])
        self.assertFalse(result["rows"][0]["eligible"])

    async def test_cf_failure_and_nonfinal_contest_cannot_prove_absence(self):
        pending = {"catalog": True, "contests": [1843]}
        with patch("feat.api.acm_api.cf_practice_jobs.cf_request", AsyncMock(side_effect=CFUnavailable("429"))):
            warnings = await self.jobs.refresh_metadata(pending)
        self.assertEqual(len(warnings), 2)
        result, _ = await self.check(candidates=["1843A"])
        self.assertEqual(result["rows"][0]["decision"], "unknown")
        contest = {"contest": {"phase": "BEFORE"}, "problems": [{"contestId": 1843, "index": "A", "name": "A", "tags": []}]}
        with patch("feat.api.acm_api.cf_practice_jobs.cf_request", AsyncMock(return_value=contest)):
            self.assertTrue(await self.jobs.refresh_metadata({"contests": [1843]}))
        result, _ = await self.check(candidates=["1843Z"])
        self.assertEqual(result["rows"][0]["decision"], "unknown")
        contest["contest"]["phase"] = "FINISHED"
        with patch("feat.api.acm_api.cf_practice_jobs.cf_request", AsyncMock(return_value=contest)):
            self.assertEqual(await self.jobs.refresh_metadata({"contests": [1843]}), [])
        result, _ = await self.check(candidates=["1843Z"])
        self.assertEqual(result["rows"][0]["decision"], "invalid")

    async def test_malformed_metadata_is_not_cached_as_complete(self):
        malformed = {"contest": {"phase": "FINISHED"}, "problems": [{"contestId": 1843, "index": "A", "tags": "broken"}]}
        with patch("feat.api.acm_api.cf_practice_jobs.cf_request", AsyncMock(return_value=malformed)):
            self.assertTrue(await self.jobs.refresh_metadata({"contests": [1843]}))
        self.assertEqual((await (await self.db.execute("SELECT COUNT(*) FROM cf_contest_cache")).fetchone())[0], 0)

    async def test_job_results_revalidate_scope_and_freshness_at_collection(self):
        await self.problem()
        data = await self.payload(candidates=["1843A"])
        job_id = await self.jobs.submit("check", data)
        await self.wait_jobs()
        self.assertTrue((await self.jobs.get(job_id))["result"]["rows"][0]["eligible"])
        await self.db.execute("UPDATE user_platform_sync_state SET coverage_through_at=?", (self.now - 90000,))
        await self.db.commit()
        self.assertFalse((await self.jobs.get(job_id))["result"]["rows"][0]["eligible"])
        await self.db.execute("UPDATE users SET cf_handle='second' WHERE qq_id='10000001'")
        await self.db.commit()
        with self.assertRaises(PracticeError) as error:
            await self.jobs.get(job_id)
        self.assertEqual(error.exception.code, "scope_changed")

    async def test_duplicate_pending_jobs_coalesce_and_cancel_is_persisted(self):
        entered = asyncio.Event()
        async def blocked(*args, **kwargs):
            entered.set()
            await asyncio.Event().wait()
        self.engine.sync_account.side_effect = blocked
        data = await self.payload()
        first = await self.jobs.submit("sync", data)
        await entered.wait()
        second = await self.jobs.submit("sync", data)
        self.assertEqual(first, second)
        await self.jobs.close()
        job = await self.jobs.get(first)
        self.assertEqual((job["status"], job["members"][0]["status"]), ("interrupted", "interrupted"))


class PracticeApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "api.db"
        self.env = patch.dict(os.environ, {"ACM_DATABASE_PATH": str(self.path), "ACM_WEBUI_SECRET_KEY": "cf-test-only-secret"})
        self.env.start()
        self.app = create_app()

    async def asyncTearDown(self):
        self.env.stop()
        self.directory.cleanup()

    async def account(self, role):
        db = await connect_db(self.path)
        try:
            now = int(time.time())
            await db.execute("INSERT INTO users(qq_id,name,status,cf_handle) VALUES('10000001','测试成员','现役','alpha')")
            await db.execute("INSERT INTO web_accounts(qq_id,password_hash,role,must_change_password,is_active,credential_version,created_at,updated_at) VALUES('10000001',?,?,0,1,1,?,?)", (hash_password("cf-test-password-123"), role, now, now))
            await db.commit()
        finally:
            await db.close()

    async def login(self, client):
        result = await client.post("/api/auth/login", json={"qq_id": "10000001", "password": "cf-test-password-123"})
        return {"X-CSRF-Token": (await result.get_json())["csrf_token"]}

    async def test_anonymous_member_csrf_and_admin_page_whitelist(self):
        async with self.app.test_app():
            client = self.app.test_client()
            self.assertEqual((await client.get("/api/admin/cf/options")).status_code, 401)
            self.assertEqual((await client.get("/cf-practice.html")).status_code, 302)
            await self.account("member")
            headers = await self.login(client)
            self.assertEqual((await client.get("/api/admin/cf/options")).status_code, 403)
            self.assertEqual((await client.post("/api/admin/cf/check", headers=headers, json={})).status_code, 403)
            self.assertEqual((await client.get("/cf-practice.html")).status_code, 403)
            db = await connect_db(self.path)
            await db.execute("UPDATE web_accounts SET role='admin'")
            await db.commit()
            await db.close()
            headers = await self.login(client)
            self.assertEqual((await client.get("/cf-practice.html")).status_code, 200)
            for route in ("overview", "problem-members", "check", "sync"):
                self.assertEqual((await client.post("/api/admin/cf/" + route, json={})).status_code, 403)
            response = await client.post("/api/admin/cf/overview", headers=headers, json={"scope": {"statuses": ["现役"]}})
            self.assertEqual(response.status_code, 200)
            data = await response.get_json()
            body = {"scope": {"statuses": ["现役"]}, "expected_scope_fingerprint": data["scope"]["fingerprint"], "candidates": ["bad"]}
            self.assertEqual((await client.post("/api/admin/cf/check", headers=headers, json=body)).status_code, 200)
            body["expected_scope_fingerprint"] = "obsolete"
            changed = await client.post("/api/admin/cf/check", headers=headers, json=body)
            self.assertEqual((changed.status_code, (await changed.get_json())["code"]), (409, "scope_changed"))

    async def test_check_returns_202_and_task_delivers_verified_result(self):
        async with self.app.test_app():
            await self.account("root")
            client = self.app.test_client()
            headers = await self.login(client)
            overview = await (await client.post("/api/admin/cf/overview", headers=headers, json={"scope": {"statuses": ["现役"]}})).get_json()
            catalog = {"problems": [{"contestId": 1843, "index": "A", "name": "A", "tags": []}]}
            contest = {"contest": {"phase": "FINISHED"}, **catalog}
            with patch("feat.api.acm_api.cf_practice_jobs.cf_request", AsyncMock(side_effect=[catalog, contest])):
                response = await client.post("/api/admin/cf/check", headers=headers, json={"scope": {"statuses": ["现役"]}, "expected_scope_fingerprint": overview["scope"]["fingerprint"], "candidates": ["1843A", "1843Z"]})
                self.assertEqual(response.status_code, 202)
                job_id = (await response.get_json())["job_id"]
                await asyncio.gather(*list(self.app.config["CF_PRACTICE_JOBS"].tasks))
                job = await (await client.get("/api/admin/cf/jobs/" + job_id)).get_json()
            self.assertEqual(job["status"], "completed")
            self.assertEqual([r["decision"] for r in job["result"]["rows"]], ["unknown", "invalid"])

    def test_invalid_ttl_configuration_is_rejected_at_startup(self):
        for value in ("0", "721", "invalid"):
            with patch.dict(os.environ, {"ACM_CF_DATA_TTL_HOURS": value}), self.assertRaises(ValueError):
                create_app()


class CFRequestTests(unittest.IsolatedAsyncioTestCase):
    class Response:
        def __init__(self, value, error=None):
            self.value, self.error = value, error

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def raise_for_status(self):
            if self.error:
                raise self.error

        async def json(self):
            return self.value

    class Session:
        def __init__(self, responses):
            self.responses, self.requests = iter(responses), []

        def get(self, url, **kwargs):
            self.requests.append((url, kwargs))
            return next(self.responses)

    async def test_failed_and_malformed_cf_responses_retry_then_remain_unavailable(self):
        for value in ({"status": "FAILED", "comment": "429 temporary failure"}, [], {"status": "OK"}):
            with self.subTest(value=value):
                session = self.Session([self.Response(value)] * 3)
                with patch("feat.api.acm_api.cf_client.asyncio.sleep", AsyncMock()), self.assertRaises(CFUnavailable):
                    await cf_request(session, "contest.standings", {"contestId": 1843})
                self.assertEqual(len(session.requests), 3)

    async def test_network_errors_do_not_expose_signed_url_and_retry_can_succeed(self):
        secret_url = "https://codeforces.com/api/m?apiKey=private-key&apiSig=private-signature"
        bad = self.Response(None, aiohttp.ClientError(secret_url))
        session = self.Session([bad] * 3)
        with patch("feat.api.acm_api.cf_client.asyncio.sleep", AsyncMock()), self.assertRaises(CFUnavailable) as error:
            await cf_request(session, "user.status")
        self.assertNotIn("private", str(error.exception))
        session = self.Session([bad, self.Response({"status": "OK", "result": []})])
        with patch("feat.api.acm_api.cf_client.asyncio.sleep", AsyncMock()):
            self.assertEqual(await cf_request(session, "user.status"), [])
        self.assertEqual(len(session.requests), 2)


if __name__ == "__main__":
    unittest.main()
