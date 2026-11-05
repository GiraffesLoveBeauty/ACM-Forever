"""Pausing Luogu must preserve history and leave other platforms usable."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from feat.api.acm_api.crawler import Crawler
from feat.api.acm_api.database import connect_db
from feat.api.acm_api.sync_policy import SYNC_PAUSED, submission_sync_paused
from feat.api.app import create_app
from feat.api.service_runtime import SyncEngine, WebTaskManager


class LuoguPolicyTests(unittest.IsolatedAsyncioTestCase):
    def test_pause_is_default_and_requires_explicit_configuration(self):
        for config in ({}, {"luogu_cookie": "cookie", "luogu_csrf_token": "csrf"},
                       {"luogu_user_sync_enabled": False}, {"luogu_user_sync_enabled": "false"}):
            with self.subTest(config=config):
                self.assertTrue(submission_sync_paused("luogu", config))
        self.assertFalse(submission_sync_paused("luogu", {"luogu_user_sync_enabled": True}))
        for platform in ("codeforces", "atcoder", "nowcoder", "cjlu"):
            self.assertFalse(submission_sync_paused(platform, {}))
        for value, enabled in (("false", False), ("true", True)):
            with patch.dict(os.environ, {"ACM_LUOGU_USER_SYNC_ENABLED": value}):
                self.assertEqual(create_app().sync_engine.crawler_config["luogu_user_sync_enabled"], enabled)

    async def test_both_crawler_entry_points_skip_http_and_database_access(self):
        for fetch in (Crawler.fetch_luogu_submission, Crawler.fetch_luogu_submissions):
            for config in ({}, {"luogu_cookie": "cookie", "luogu_csrf_token": "csrf"}):
                with self.subTest(fetch=fetch.__name__, configured=bool(config)):
                    session, db = AsyncMock(), AsyncMock()
                    result = await fetch(session, None, 0, db, config)
                    self.assertEqual(result, SYNC_PAUSED)
                    self.assertEqual(session.mock_calls, [])
                    self.assertEqual(db.mock_calls, [])

    async def test_crawlers_can_be_resumed_explicitly(self):
        config = {"luogu_user_sync_enabled": True, "luogu_cookie": "cookie", "luogu_csrf_token": "csrf"}
        for fetch in (Crawler.fetch_luogu_submission, Crawler.fetch_luogu_submissions):
            with self.subTest(fetch=fetch.__name__):
                with patch("feat.api.acm_api.crawler._fetch_luogu_json", new=AsyncMock(return_value={})) as http:
                    with patch.object(Crawler, "_get_existing_problem_ids", new=AsyncMock(return_value=set())):
                        result = await fetch(AsyncMock(), {"qq_id": "12345678", "luogu_id": "1234"}, 0, AsyncMock(), config)
                self.assertEqual(result, 0)
                http.assert_awaited_once()


class LuoguPauseIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "sync.db"
        db = await connect_db(self.path)
        try:
            await db.execute("INSERT INTO users(qq_id,name,luogu_id,atcoder_handle,last_sync_timestamp) VALUES('12345678','Mixed','1234','Example',123)")
            await db.execute("INSERT INTO users(qq_id,name,luogu_id,last_sync_timestamp) VALUES('87654321','Luogu only','5678',456)")
            await db.execute("INSERT INTO submissions(user_qq_id,platform,problem_id,submit_time) VALUES('12345678','luogu','P1000',100)")
            await db.execute("INSERT INTO user_platform_sync_state(user_qq_id,platform,cursor_timestamp,last_attempt_at,last_success_at,last_status,consecutive_failures) VALUES('12345678','luogu',101,102,100,'failed',2)")
            await db.commit()
        finally:
            await db.close()
        self.engine = SyncEngine(self.path, {})
        await self.engine.start()
        self.luogu_patch = patch.object(Crawler, "fetch_luogu_submission", new=AsyncMock(side_effect=AssertionError("Luogu must not run")))
        self.atcoder_patch = patch.object(Crawler, "fetch_atcoder_submissions", new=AsyncMock(return_value=2))
        self.luogu = self.luogu_patch.start()
        self.atcoder = self.atcoder_patch.start()
        self.before = await self.snapshot()

    async def asyncTearDown(self):
        self.atcoder_patch.stop()
        self.luogu_patch.stop()
        await self.engine.close()
        self.temp.cleanup()

    async def sql(self, query):
        async with self.engine.db.execute(query) as cursor:
            return [tuple(row) for row in await cursor.fetchall()]

    async def snapshot(self):
        return (
            await self.sql("SELECT * FROM user_platform_sync_state WHERE platform='luogu' ORDER BY user_qq_id"),
            await self.sql("SELECT * FROM submissions WHERE platform='luogu' ORDER BY user_qq_id,problem_id"),
            await self.sql("SELECT qq_id,last_sync_timestamp FROM users ORDER BY qq_id"),
        )

    async def assert_preserved(self):
        self.luogu.assert_not_awaited()
        self.assertEqual(await self.snapshot(), self.before)

    async def test_periodic_sync_continues_other_platform_and_preserves_luogu_state(self):
        self.assertTrue(await self.engine.sync_single_user("12345678"))
        self.atcoder.assert_awaited_once()
        await self.assert_preserved()
        self.assertEqual(await self.sql("SELECT last_status FROM user_platform_sync_state WHERE platform='atcoder'"), [("success",)])

    async def test_periodic_all_users_does_not_start_luogu_crawls(self):
        await self.engine.sync_all_users_data()
        self.atcoder.assert_awaited_once()
        await self.assert_preserved()

    async def test_manual_full_and_bounded_platform_sync_report_pause_without_state_writes(self):
        for days in (0, 7):
            self.assertEqual(await self.engine.sync_single_platform_for_days("12345678", "luogu", days), SYNC_PAUSED)
        await self.assert_preserved()
        self.atcoder.assert_not_awaited()

    async def test_manual_user_sync_reports_pause_and_keeps_other_results(self):
        for days in (0, 7):
            result = await self.engine.sync_single_user_for_days("12345678", days)
            self.assertEqual(result, {"luogu": SYNC_PAUSED, "atcoder": 2})
        self.assertEqual(self.atcoder.await_count, 2)
        await self.assert_preserved()

    async def test_pause_keeps_user_and_binding_generation_checks(self):
        self.assertEqual(await self.engine.sync_single_platform_for_days("00000000", "luogu", 0), -1)
        result = await self.engine.sync_single_platform_for_days(
            "12345678", "luogu", 0,
            expected_binding={"account": "stale", "version": 0, "account_epoch": 1},
        )
        self.assertEqual(result, -4)
        await self.assert_preserved()

    async def test_explicit_resume_uses_the_existing_cursor_and_fetcher(self):
        self.engine.crawler_config["luogu_user_sync_enabled"] = True
        with patch.object(Crawler, "fetch_luogu_submission", new=AsyncMock(return_value=0)) as fetch:
            self.assertEqual(await self.engine.sync_single_platform_for_days("12345678", "luogu", 0), 0)
        fetch.assert_awaited_once()
        state = await self.sql("SELECT cursor_timestamp,last_status,consecutive_failures FROM user_platform_sync_state WHERE platform='luogu'")
        self.assertGreater(state[0][0], 101)
        self.assertEqual(state[0][1:], ("success", 0))

    async def test_api_task_is_completed_with_an_explicit_paused_result(self):
        manager = WebTaskManager(self.engine)
        with self.assertLogs("acm.events", level="INFO") as captured:
            submitted = await manager.submit_account_sync("12345678", ["luogu", "atcoder"])
            task = manager.tasks[submitted["id"]]
            await task["_task"]
        self.assertEqual(task["status"], "completed")
        self.assertEqual(task["result"], {"luogu": SYNC_PAUSED, "atcoder": 2})
        self.assertEqual(captured.records[-1].acm_event["level"], "info")
        await self.assert_preserved()

    async def test_luogu_only_api_task_is_paused_instead_of_failed(self):
        manager = WebTaskManager(self.engine)
        submitted = await manager.submit_account_sync("87654321", ["luogu"])
        task = manager.tasks[submitted["id"]]
        await task["_task"]
        self.assertEqual(task["status"], "completed")
        self.assertEqual(task["result"], {"luogu": SYNC_PAUSED})
        await self.assert_preserved()

    async def test_all_accounts_task_preserves_pause_and_other_platform_results(self):
        manager = WebTaskManager(self.engine)
        submitted = await manager.submit_all_accounts_sync(days=7)
        task = manager.tasks[submitted["id"]]
        await task["_task"]
        self.assertEqual(task["status"], "completed")
        self.assertEqual(task["result"], {"12345678": {"luogu": SYNC_PAUSED, "atcoder": 2}, "87654321": {"luogu": SYNC_PAUSED}})
        await self.assert_preserved()

    async def test_other_platform_failure_is_still_a_failure(self):
        self.atcoder.return_value = -1
        manager = WebTaskManager(self.engine)
        submitted = await manager.submit_account_sync("12345678", ["luogu", "atcoder"])
        task = manager.tasks[submitted["id"]]
        await task["_task"]
        self.assertEqual(task["status"], "failed")
        self.assertEqual(task["result"], {"luogu": SYNC_PAUSED, "atcoder": -1})
        await self.assert_preserved()

    async def test_bind_and_manual_job_messages_explain_pause(self):
        event = AsyncMock()
        await self.engine._run_bind_platform_sync_job(event, "12345678", "luogu")
        self.assertIn("已暂停", event.reply.call_args.kwargs["text"])
        task = {"status": "queued"}
        await self.engine._run_sync_platform_job(event, "12345678", "luogu", 7, task)
        self.assertEqual((task["status"], task["result"]), ("completed", SYNC_PAUSED))
        self.assertIn("已暂停", event.reply.call_args.kwargs["text"])
        await self.engine._run_bind_sync_job(event, "12345678")
        self.assertIn("已暂停", event.reply.call_args.kwargs["text"])
        await self.assert_preserved()
