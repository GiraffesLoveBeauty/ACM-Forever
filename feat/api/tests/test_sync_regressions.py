from pathlib import Path
import asyncio
import os
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from feat.api.acm_api.auth_service import hash_password
from feat.api.acm_api.backend_api import _active_sync_tasks, _parse_sync_incremental
from feat.api.acm_api.crawler import Crawler
from feat.api.acm_api.database import connect_db
from feat.api.app import create_app
from feat.api.service_runtime import WebTaskManager


class SyncAdmissionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db_path = Path(self.temp.name) / "sync.db"
        db = await connect_db(self.db_path)
        try:
            await db.execute("INSERT INTO users(qq_id,name,cf_handle) VALUES('10000001','测试成员','handle')")
            await db.commit()
        finally:
            await db.close()

    async def test_duplicate_member_submission_is_rejected_even_when_submissions_race(self):
        async def run(*args, **kwargs):
            await asyncio.Future()

        manager = WebTaskManager(SimpleNamespace(db_path=self.db_path, sync_account=run))
        try:
            results = await asyncio.gather(
                manager.submit_account_sync("10000001", ["codeforces"]),
                manager.submit_account_sync("10000001", ["codeforces"]),
            )
            self.assertEqual(sum(result is not None for result in results), 1)
            self.assertEqual(len(manager.tasks), 1)
        finally:
            await manager.close()

    async def test_non_luogu_full_sync_uses_selected_platform_state_for_ordering(self):
        db = await connect_db(self.db_path)
        try:
            await db.executemany(
                "INSERT INTO users(qq_id,name,cf_handle) VALUES(?,?,?)",
                [("10000002", "已尝试", "handle-2"), ("10000003", "未尝试", "handle-3")],
            )
            await db.execute(
                "INSERT INTO user_platform_sync_state(user_qq_id,platform,last_attempt_at,last_status) VALUES('10000002','codeforces',100,'success')"
            )
            await db.commit()
        finally:
            await db.close()

        async def run(task, days=0, *, incremental=False):
            task["status"] = "completed"

        manager = WebTaskManager(SimpleNamespace(db_path=self.db_path, sync_all_accounts=run))
        try:
            result = await manager.submit_all_accounts_sync(platforms=["codeforces"])
            snapshots = manager.tasks[result["id"]]["_account_snapshots"]
            ordered = [row["qq_id"] for row in snapshots if row["qq_id"] in {"10000002", "10000003"}]
            self.assertEqual(ordered, ["10000003", "10000002"])
        finally:
            await manager.close()


class SyncPayloadTests(unittest.TestCase):
    def test_global_task_only_marks_selected_platforms_running(self):
        active = _active_sync_tasks([
            {"kind": "全员平台同步", "qq_id": "*", "platform": "codeforces", "status": "running"},
        ])
        self.assertIn(("*", "codeforces"), active)
        self.assertNotIn(("*", "luogu"), active)

    def test_incremental_payload_requires_a_boolean_or_binary_integer(self):
        self.assertTrue(_parse_sync_incremental(None))
        self.assertTrue(_parse_sync_incremental(True))
        self.assertFalse(_parse_sync_incremental(0))
        with self.assertRaises(ValueError):
            _parse_sync_incremental("yes")


class AdminSyncApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db_path = Path(self.temp.name) / "api.db"
        self.env = patch.dict(
            os.environ,
            {
                "ACM_DATABASE_PATH": str(self.db_path),
                "ACM_WEBUI_SECRET_KEY": "sync-regression-secret",
                "ACM_BOT_API_TOKEN": "sync-regression-token",
            },
        )
        self.env.start()
        self.addCleanup(self.env.stop)
        self.app = create_app()

    async def _login(self, client):
        db = await connect_db(self.db_path)
        try:
            now = int(time.time())
            await db.execute(
                "INSERT INTO users(qq_id,name,cf_handle,luogu_id) VALUES('12345678','同步测试成员','handle','12345')"
            )
            await db.execute(
                "INSERT INTO web_accounts(qq_id,password_hash,role,must_change_password,is_active,credential_version,created_at,updated_at) "
                "VALUES('12345678',?,'admin',0,1,1,?,?)",
                (hash_password("Sync-Test-Password-123!"), now, now),
            )
            await db.execute(
                "INSERT INTO user_platform_sync_state(user_qq_id,platform,last_status,last_attempt_at) "
                "VALUES('12345678','codeforces','success',100)"
            )
            await db.commit()
        finally:
            await db.close()
        response = await client.post(
            "/api/auth/login",
            json={"qq_id": "12345678", "password": "Sync-Test-Password-123!"},
        )
        self.assertEqual(response.status_code, 200)
        return {"X-CSRF-Token": (await response.get_json())["csrf_token"]}

    async def test_member_status_api_filters_and_reports_only_selected_platform_as_running(self):
        async with self.app.test_app():
            client = self.app.test_client()
            headers = await self._login(client)
            self.app.config["PLUGIN_CONFIG"]["_task_provider"] = lambda: [
                {"kind": "全员平台同步", "qq_id": "*", "platform": "codeforces", "status": "running"}
            ]
            response = await client.get(
                "/api/admin/sync/members?platform=cf&status=running",
                headers=headers,
            )
            self.assertEqual(response.status_code, 200)
            payload = await response.get_json()
            self.assertEqual(payload["total"], 1)
            member = payload["items"][0]
            self.assertEqual(member["platforms"]["codeforces"]["status"], "running")
            self.assertEqual(member["platforms"]["luogu"]["status"], "never")

    async def test_sync_submit_api_passes_platform_and_incremental_contract(self):
        async with self.app.test_app():
            client = self.app.test_client()
            headers = await self._login(client)
            member_calls = []
            all_calls = []

            async def submit_member(*args, **kwargs):
                member_calls.append((args, kwargs))
                return {"id": "member-sync"}

            async def submit_all(*args, **kwargs):
                all_calls.append((args, kwargs))
                return {"id": "all-sync"}

            self.app.config["PLUGIN_CONFIG"].update(
                _account_sync_submitter=submit_member,
                _all_account_sync_submitter=submit_all,
            )
            response = await client.post(
                "/api/admin/sync/members/12345678",
                headers=headers,
                json={"platforms": ["cf"], "incremental": False},
            )
            self.assertEqual(response.status_code, 202)
            self.assertEqual(member_calls, [(
                ("12345678", ["codeforces"]),
                {"days": 0, "incremental": False},
            )])
            response = await client.post("/api/admin/sync/all", headers=headers, json={"platforms": ["luogu"]})
            self.assertEqual(response.status_code, 202)
            self.assertEqual(all_calls, [((), {"days": 0, "platforms": ["luogu"], "incremental": True})])

            response = await client.post("/api/admin/sync/all", headers=headers, json=[])
            self.assertEqual(response.status_code, 400)
            payload = await response.get_json()
            self.assertEqual(payload["code"], "invalid_request")
            self.assertEqual(len(all_calls), 1)


class RecentLuoguAcTests(unittest.IsolatedAsyncioTestCase):
    async def test_recent_ac_ignores_non_p_problem_ids(self):
        records = [
            {"submitTime": 300, "problem": {"pid": "P1001", "title": "P"}},
            {"submitTime": 299, "problem": {"pid": "B1001", "title": "Mirror"}},
            {"submitTime": 298, "problem": {"pid": "CF1A", "title": "Other OJ"}},
            {"submitTime": 297, "problem": {"pid": "P1002", "title": "P2"}},
        ]
        payload = {"currentData": {"records": {"result": records}}}
        with patch("feat.api.acm_api.crawler._fetch_luogu_json", new=AsyncMock(return_value=payload)):
            result = await Crawler._fetch_recent_luogu_ac(
                None,
                {"luogu_id": "12345"},
                0,
                10,
                {"luogu_cookie": "cookie", "luogu_csrf_token": "csrf"},
            )
        self.assertEqual([item["problem_id"] for item in result], ["P1001", "P1002"])


if __name__ == "__main__":
    unittest.main()