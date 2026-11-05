import asyncio
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from feat.api.acm_api.problem_sync import sync_options
from feat.api.service_runtime import PROBLEM_SYNC_TIMEZONE, WebTaskManager


class DailyProblemSyncTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.db_path = Path(directory.name) / "daily.db"
        with closing(sqlite3.connect(self.db_path)) as db, db:
            db.execute("CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT NOT NULL)")
        clock = self.enterContext(patch("feat.api.service_runtime.datetime"))
        clock.now.return_value = datetime(2026, 11, 5, 4, 0, tzinfo=PROBLEM_SYNC_TIMEZONE)
        self.clock = clock
        self.manager = self.make_manager()

    def make_manager(self):
        manager = WebTaskManager(SimpleNamespace(db_path=self.db_path))
        self.addAsyncCleanup(manager.close)
        return manager

    async def test_waits_for_manual_work_and_remembers_daily_runs_across_restart(self):
        manual_gate = asyncio.Event()
        completed = []

        async def run(options, task):
            task["status"] = "running"
            if not options.get("scheduled"):
                await manual_gate.wait()
            else:
                completed.append(options["platform"])
            task["status"] = "completed"

        self.manager.problem_sync.run = run
        options = sync_options({"platform": "atcoder", "scope": "platform"})
        task_id = self.manager.submit_problem_sync(options)["id"]
        self.assertFalse(await self.manager._run_daily_problem_sync())
        manual_gate.set()
        await self.manager.tasks[task_id]["_task"]

        self.assertTrue(await self.manager._run_daily_problem_sync())
        restarted = self.make_manager()
        restarted.problem_sync.run = run
        self.assertTrue(await restarted._run_daily_problem_sync())
        self.assertEqual(completed, ["atcoder", "codeforces"])
        self.assertEqual(restarted.snapshots(), [])

        self.clock.now.return_value = datetime(2026, 11, 6, 4, 0, tzinfo=PROBLEM_SYNC_TIMEZONE)
        self.assertTrue(await self.manager._run_daily_problem_sync())
        self.assertEqual(completed, ["atcoder", "codeforces", "atcoder", "codeforces"])
        self.assertEqual(len(self.manager.snapshots()), 3)

    async def test_service_shutdown_cancels_active_daily_collection(self):
        started = asyncio.Event()

        async def run(options, task):
            task["status"] = "running"
            started.set()
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                task["status"] = "cancelled"
                raise

        self.manager.problem_sync.run = run
        self.manager.start_daily_problem_sync()
        await asyncio.wait_for(started.wait(), timeout=5)
        await self.manager.close()
        self.assertEqual(
            [(item["platform"], item["status"]) for item in self.manager.snapshots()],
            [("atcoder", "cancelled")],
        )
