"""Periodic member sync uses captured identities and durable interval admission."""

import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from feat.api.acm_api.database import connect_db
from feat.api.acm_api.sync_policy import SYNC_PAUSED
from feat.api.service_runtime import SyncEngine, WebTaskManager


class PeriodicMemberSyncTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.db_path = Path(directory.name) / "members.db"
        db = await connect_db(self.db_path)
        try:
            await db.executemany(
                "INSERT INTO users(qq_id,name,cf_handle,atcoder_handle) VALUES(?,?,?,?)",
                [("11111111", "CF member", "Alpha", None),
                 ("22222222", "AtCoder member", None, "Beta"),
                 ("33333333", "Unbound member", None, None),
                 ("44444444", "Closed member", "Former", None)],
            )
            await db.execute(
                "UPDATE users SET account_state='closed',account_epoch=2,closed_at=1 "
                "WHERE qq_id='44444444'"
            )
            await db.commit()
            async with db.execute("SELECT * FROM users ORDER BY qq_id") as cursor:
                self.members = [dict(row) for row in await cursor.fetchall()]
        finally:
            await db.close()
        self.now = 1_800_000_000
        self.enterContext(patch("feat.api.service_runtime.time.time", side_effect=lambda: self.now))
        self.calls = []
        self.manager = self.make_manager()

    def make_manager(self):
        async def run(task, days=0, *, incremental=False):
            self.calls.append((task, days, incremental))
            task["status"] = "completed"

        manager = WebTaskManager(SimpleNamespace(db_path=self.db_path, sync_all_accounts=run))
        self.addAsyncCleanup(manager.close)
        return manager

    async def test_busy_defers_then_interval_and_restart_prevent_duplicate_runs(self):
        self.manager.tasks["manual"] = {
            "id": "manual", "kind": "题目采集", "platform": "codeforces", "status": "running",
        }
        params = {"incremental": True, "scheduled": True, "interval_seconds": 3600}
        self.assertIsNone(await self.manager.submit_all_accounts_sync(**params))
        db = await connect_db(self.db_path)
        try:
            async with db.execute("SELECT value FROM settings WHERE key='member_sync_last_started_at'") as cursor:
                self.assertIsNone(await cursor.fetchone())
        finally:
            await db.close()

        self.manager.tasks["manual"]["status"] = "completed"
        responses = await asyncio.gather(
            self.manager.submit_all_accounts_sync(**params),
            self.manager.submit_all_accounts_sync(**params),
        )
        accepted = [result for result in responses if result is not None]
        self.assertEqual(len(accepted), 1)
        await self.manager.tasks[accepted[0]["id"]]["_task"]
        task, days, incremental = self.calls[0]
        self.assertEqual((days, incremental, task["kind"]), (0, True, "全员定时同步"))
        self.assertEqual(
            [(member["qq_id"], member["account_epoch"]) for member in task["_account_snapshots"]],
            [("11111111", 1), ("22222222", 1)],
        )

        restarted = self.make_manager()
        self.assertIsNone(await restarted.submit_all_accounts_sync(**params))
        self.now += 3600
        result = await restarted.submit_all_accounts_sync(**params)
        self.assertIsNotNone(result)
        await restarted.tasks[result["id"]]["_task"]
        self.assertEqual(len(self.calls), 2)

    async def test_shutdown_cancels_scheduler_and_active_member_sync(self):
        started = asyncio.Event()

        async def run(task, days=0, *, incremental=False):
            task["status"] = "running"
            started.set()
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                task["status"] = "cancelled"
                raise

        self.manager.sync_engine.sync_all_accounts = run
        self.manager.start_member_sync(interval_seconds=3600)
        await asyncio.wait_for(started.wait(), timeout=5)
        await self.manager.close()
        tasks = list(self.manager.tasks.values())
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["status"], "cancelled")
        self.assertTrue(tasks[0]["_task"].done())

    async def test_incremental_cycle_continues_after_platform_failure_with_snapshot_guards(self):
        engine = SyncEngine(self.db_path, {})
        calls = []

        async def sync(qq_id, platform, days, *, incremental=False, expected_binding=None):
            calls.append((qq_id, platform, days, incremental, expected_binding))
            if platform == "codeforces":
                raise RuntimeError("Synthetic CF outage")
            return 2

        engine.sync_single_platform_for_days = sync
        task = {"_account_snapshots": self.members[:2]}
        await engine.sync_all_accounts(task, incremental=True)
        self.assertEqual([(row[0], row[1], row[2], row[3]) for row in calls],
                         [("11111111", "codeforces", 0, True), ("22222222", "atcoder", 0, True)])
        self.assertEqual(calls[0][4]["account"], "Alpha")
        self.assertEqual(calls[0][4]["account_epoch"], 1)
        self.assertEqual(task["result"], {"11111111": {"codeforces": -3}, "22222222": {"atcoder": 2}})
        self.assertEqual(task["progress"], {"done": 2, "total": 2})
        self.assertEqual(task["status"], "partial")

    async def test_paused_platform_is_reported_without_failing_the_cycle(self):
        engine = SyncEngine(self.db_path, {})
        member = {**self.members[0], "cf_handle": None, "luogu_id": "Paused"}

        async def sync(qq_id, platform, days, *, incremental=False, expected_binding=None):
            self.assertEqual(platform, "luogu")
            return SYNC_PAUSED

        engine.sync_single_platform_for_days = sync
        task = {"_account_snapshots": [member]}
        await engine.sync_all_accounts(task, incremental=True)
        self.assertEqual(task["status"], "completed")
        self.assertEqual(task["result"], {"11111111": {"luogu": SYNC_PAUSED}})

    async def test_atcoder_initial_sync_backfills_then_uses_successful_cursor(self):
        db = await connect_db(self.db_path)
        try:
            await db.execute(
                "INSERT INTO user_platform_sync_state"
                "(user_qq_id,platform,cursor_timestamp,last_success_at,full_history_at,last_status) "
                "VALUES('22222222','atcoder',?,?,0,'backfill') "
                "ON CONFLICT(user_qq_id,platform) DO UPDATE SET "
                "cursor_timestamp=excluded.cursor_timestamp,last_success_at=excluded.last_success_at,"
                "full_history_at=0,last_status='backfill'",
                (self.now - 1000, self.now - 1000),
            )
            await db.commit()
        finally:
            await db.close()

        engine = SyncEngine(self.db_path, {})
        await engine.start()
        self.addAsyncCleanup(engine.close)
        fetch = AsyncMock(return_value=0)
        with patch.object(engine, "_fetch_platform_with_limit", fetch):
            self.assertEqual(
                await engine.sync_single_platform_for_days("22222222", "atcoder", 0, incremental=True),
                0,
            )
            self.assertEqual(fetch.call_args.args[-1], 0)
            async with engine.db.execute(
                "SELECT full_history_at,last_status FROM user_platform_sync_state "
                "WHERE user_qq_id='22222222' AND platform='atcoder'"
            ) as cursor:
                state = await cursor.fetchone()
            self.assertGreater(state["full_history_at"], 0)
            self.assertEqual(state["last_status"], "success")
            first_success = self.now
            self.now += 3600
            self.assertEqual(
                await engine.sync_single_platform_for_days("22222222", "atcoder", 0, incremental=True),
                0,
            )
            self.assertEqual(fetch.call_args.args[-1], first_success - 7 * 86400)
            self.assertEqual(await engine.sync_single_platform_for_days("22222222", "atcoder", 0), 0)
            self.assertEqual(fetch.call_args.args[-1], 0)
