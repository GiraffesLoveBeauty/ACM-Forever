"""Public Luogu AC parsing, binding fences and idempotent persistence (synthetic data)."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from feat.api.acm_api import luogu_user_sync as sync
from feat.api.acm_api.binding_guard import BindingChanged
from feat.api.acm_api.binding_service import apply_binding
from feat.api.acm_api.crawler import Crawler
from feat.api.acm_api.database import connect_db
from feat.api.acm_api.luogu_client import LuoguUnavailable
from feat.api.acm_api.problem_bank import save_metadata_batch
from feat.api.acm_api.sync_policy import SYNC_LUOGU_ACCESS_RESTRICTED, SyncOutcome
from feat.api.service_runtime import SyncEngine, WebTaskManager


def page(passed=None, *, account=1234, **overrides):
    context = {"template": "user.practice", "status": 200,
               "data": {"user": {"uid": account}, "passed": passed if passed is not None else []}}
    context.update(overrides)
    return '<script type="application/json" id="lentille-context">' + json.dumps(context) + '</script>'


class PracticeParserTests(unittest.TestCase):
    def test_only_passed_list_is_imported_and_deduplicated(self):
        data = {"user": {"uid": 1234}, "passed": ["P1001", {"pid": "p1001"}, {"pid": "CF1A", "title": "Synthetic"}],
                "submitted": [{"pid": "P1002"}]}
        rows = sync.practice_snapshot(page(data=data), "1234")
        self.assertEqual([row["pid"] for row in rows], ["P1001"])

    def test_non_p_entries_are_skipped_before_optional_fields_are_validated(self):
        rows = sync.practice_snapshot(page([
            "P1001", "B1001", "T1", "U2", "SP3", "CF1A", "UVA100", "AT1202Contest_a",
            {"pid": "AT_abc100_a", "name": [], "difficulty": True}, "luogu_p1002",
        ]), "1234")
        self.assertEqual([row["pid"] for row in rows], ["P1001", "P1002"])
        self.assertEqual(sync.practice_snapshot(page(["CF1A", "UVA100"]), "1234"), [])
        for value in (None, True, "", "   ", "P0", "P01", "Pbroken", "luogu_P1/other"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                sync.practice_snapshot(page(["P1001", {"pid": value}]), "1234")

    def test_empty_is_valid_but_missing_passed_is_not(self):
        self.assertEqual(sync.practice_snapshot(page(), "1234"), [])
        for raw in (page(data={"user": {"uid": 1234}}), page(data={"user": {"uid": 1234}, "passed": {"result": [], "count": 10}})):
            with self.assertRaises(ValueError):
                sync.practice_snapshot(raw, "1234")

    def test_no_login_error_partial_or_wrong_owner_pages(self):
        for raw in ("<html>Login required</html>", page(account=5678), page(status=403),
                    page(data={"passed": []}), page(["P1001", {"pid": "P1/other"}])):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                sync.practice_snapshot(raw, "1234")

    def test_canonical_ids_reject_urls_and_sql_fragments(self):
        for value in ("P1001", "P123456789"):
            self.assertEqual(sync.canonical_pid(value), value)
        self.assertEqual(sync.canonical_pid("luogu_p1001"), "P1001")
        for value in (None, True, "B1001", "CF1A", "AT_abc100_a", "P1234567890", "0", "P0", "P01", "P1' OR 1=1", "https://www.luogu.com.cn/problem/P1", "P1/other"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                sync.canonical_pid(value)

    def test_uid_and_fields_are_bounded(self):
        for value in (True, "0", "01", "1/other", "https://luogu.com.cn/user/1"):
            with self.assertRaises(ValueError):
                sync.uid(value)
        for item in ({"pid": "P1", "name": []}, {"pid": "P1", "difficulty": True}, {"pid": "P1", "name": "a" * 1001}):
            with self.assertRaises(ValueError):
                sync.practice_snapshot(page([item]), "1234")


class PracticeStorageTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "test.db"
        self.db = await connect_db(self.path)
        self.addAsyncCleanup(self.db.close)
        await self.db.execute("INSERT INTO users(qq_id,name,luogu_id) VALUES('12345678','Synthetic','1234')")
        await self.db.commit()
        self.user = await self.one("SELECT * FROM users WHERE qq_id='12345678'")

    async def one(self, sql):
        async with self.db.execute(sql) as cursor:
            return await cursor.fetchone()

    async def rows(self):
        async with self.db.execute("SELECT * FROM submissions ORDER BY problem_id") as cursor:
            return [dict(row) for row in await cursor.fetchall()]

    async def run_snapshot(self, raw, *, start=0):
        with patch.object(sync, "luogu_get", new=AsyncMock(return_value=raw)) as http:
            result = await Crawler.fetch_luogu_submission(None, self.user, start, self.db, {})
        return result, http

    async def test_anonymous_snapshot_is_idempotent_and_not_filtered_by_time(self):
        raw = page([{"pid": "P1001", "name": "A"}, "P1002", "P1001", "CF1A"])
        count, http = await self.run_snapshot(raw, start=9999999999)
        self.assertEqual(count, 2)
        self.assertEqual((await self.run_snapshot(raw))[0], 0)
        records = await self.rows()
        self.assertEqual({row["submit_time"] for row in records}, {0})
        self.assertEqual({row["platform"] for row in records}, {"luogu"})
        self.assertTrue(all(row["problem_url"].startswith("https://www.luogu.com.cn/problem/") for row in records))
        self.assertEqual(http.call_args.args[1], "https://www.luogu.com.cn/user/1234/practice")
        self.assertNotIn("Cookie", http.call_args.kwargs["headers"])
        self.assertEqual((await self.one("SELECT COUNT(*) FROM submission_attempts"))[0], 0)

    async def test_mixed_snapshot_only_inserts_p_problems_with_one_request(self):
        count, http = await self.run_snapshot(page(["P1001", "CF1A", "B1001", "UVA100", "AT1202Contest_a"]))
        self.assertEqual(count, 1)
        self.assertEqual([row["problem_id"] for row in await self.rows()], ["P1001"])
        self.assertEqual(http.await_count, 1)

    async def test_non_p_only_snapshot_still_checks_binding_generation(self):
        await self.db.execute("UPDATE users SET luogu_binding_version=luogu_binding_version+1 WHERE qq_id='12345678'")
        await self.db.commit()
        with self.assertRaises(BindingChanged):
            await self.run_snapshot(page(["CF1A", "UVA100"]))
        self.assertEqual(await self.rows(), [])

    async def test_known_times_and_legacy_aliases_are_preserved(self):
        await self.db.execute("INSERT INTO submissions(user_qq_id,platform,problem_id,submit_time) VALUES('12345678','luogu','luogu_P1001',123)")
        await self.db.commit()
        self.assertEqual((await self.run_snapshot(page(["P1001", "P1002"])))[0], 1)
        records = await self.rows()
        self.assertEqual(len(records), 2)
        self.assertEqual(next(r for r in records if r["problem_id"] == "luogu_P1001")["submit_time"], 123)

    async def test_metadata_is_reused_without_crawling_every_problem(self):
        await save_metadata_batch(self.db, [{"platform": "luogu", "problem_id": "P1001", "contest_id": "",
                                             "problem_name": "Catalog name", "problem_url": "https://www.luogu.com.cn/problem/P1001",
                                             "tags": ["模拟"]}])
        count, http = await self.run_snapshot(page([{"pid": "P1001", "name": "Page name"}]))
        self.assertEqual(count, 1)
        self.assertEqual((await self.rows())[0]["problem_name"], "Catalog name")
        self.assertEqual((await self.rows())[0]["tags"], '["模拟"]')
        self.assertEqual(http.await_count, 1)

    async def test_failed_or_empty_snapshot_never_deletes_history(self):
        await self.run_snapshot(page(["P1001"]))
        for raw, expected in ((page(), 0), (page(account=4567), -1), ("<html>challenge</html>", -1), (page(["P1002", "Pbroken"]), -1)):
            self.assertEqual((await self.run_snapshot(raw))[0], expected)
            self.assertEqual([r["problem_id"] for r in await self.rows()], ["P1001"])

    async def test_http_restriction_stops_without_writes_or_retries(self):
        for status in (403, 429, 302):
            with patch.object(sync, "luogu_get", new=AsyncMock(side_effect=LuoguUnavailable("restricted", status=status))) as http:
                self.assertEqual(await Crawler.fetch_luogu_submission(None, self.user, 0, self.db, {}), -1)
            self.assertEqual(http.await_count, 1)
        self.assertEqual(await self.rows(), [])

    async def test_http_403_preserves_account_restriction_metadata(self):
        with patch.object(sync, "luogu_get", new=AsyncMock(side_effect=LuoguUnavailable("restricted", status=403))):
            result = await Crawler.fetch_luogu_submission(None, self.user, 0, self.db, {})
        self.assertIsInstance(result, SyncOutcome)
        self.assertEqual(result, -1)
        self.assertEqual(result.status, 403)
        self.assertEqual(result.error_code, "access_restricted")

    async def test_http_403_disables_only_that_member_and_later_skips_it(self):
        await self.db.execute("INSERT INTO users(qq_id,name,luogu_id) VALUES('87654321','Other','5678')")
        await self.db.commit()
        engine = SyncEngine(self.path, {})
        await engine.start()
        self.addAsyncCleanup(engine.close)

        calls = []

        async def fetch(*args):
            user = args[1]
            calls.append(user["qq_id"])
            if user["qq_id"] == "12345678":
                return SyncOutcome(-1, status=403, error_code="access_restricted")
            return 1

        with patch.object(Crawler, "fetch_luogu_submission", new=fetch):
            await engine.sync_all_users_data()
            self.assertEqual(set(calls), {"12345678", "87654321"})
            self.assertEqual(await engine.sync_single_platform_for_days("12345678", "luogu", 0), SYNC_LUOGU_ACCESS_RESTRICTED)

        restricted = await self.one("SELECT sync_enabled,last_status,last_error_code FROM user_platform_sync_state WHERE user_qq_id='12345678' AND platform='luogu'")
        healthy = await self.one("SELECT sync_enabled,last_status FROM user_platform_sync_state WHERE user_qq_id='87654321' AND platform='luogu'")
        self.assertEqual((restricted["sync_enabled"], restricted["last_status"], restricted["last_error_code"]), (0, "disabled", "access_restricted"))
        self.assertEqual((healthy["sync_enabled"], healthy["last_status"]), (1, "success"))
        self.assertEqual(calls.count("12345678"), 1)

    async def test_changed_binding_cannot_receive_stale_snapshot(self):
        async def download(*args, **kwargs):
            other = await connect_db(self.path)
            try:
                await other.execute("BEGIN IMMEDIATE")
                await apply_binding(other, "12345678", "luogu", "5678", actor="12345678")
                await other.commit()
            finally:
                await other.close()
            return page(["P1001"])
        with patch.object(sync, "luogu_get", side_effect=download), self.assertRaises(BindingChanged):
            await Crawler.fetch_luogu_submission(None, self.user, 0, self.db, {})
        self.assertEqual(await self.rows(), [])

    async def test_closed_account_cannot_receive_even_empty_snapshot(self):
        await self.db.execute("UPDATE users SET account_state='closed',account_epoch=account_epoch+1 WHERE qq_id='12345678'")
        await self.db.commit()
        with patch.object(sync, "luogu_get", new=AsyncMock(return_value=page())), self.assertRaises(BindingChanged):
            await Crawler.fetch_luogu_submission(None, self.user, 0, self.db, {})

    async def test_default_task_path_syncs_public_records_and_reports_added_count(self):
        engine = SyncEngine(self.path, {})
        await engine.start()
        self.addAsyncCleanup(engine.close)
        manager = WebTaskManager(engine)
        with patch.object(sync, "luogu_get", new=AsyncMock(return_value=page(["P1001"]))):
            submitted = await manager.submit_account_sync("12345678", ["luogu"])
            task = manager.tasks[submitted["id"]]
            await task["_task"]
        self.assertEqual(task["status"], "completed")
        self.assertEqual(task["result"], {"luogu": 1})
        state = await self.one("SELECT * FROM user_platform_sync_state WHERE platform='luogu'")
        self.assertEqual(state["last_status"], "success")
        self.assertGreater(state["full_history_at"], 0)
        self.assertEqual(state["coverage_through_at"], 0)

    async def test_failed_task_keeps_cursor_and_existing_records(self):
        await self.run_snapshot(page(["P1001"]))
        await self.db.execute("INSERT INTO user_platform_sync_state(user_qq_id,platform,cursor_timestamp) VALUES('12345678','luogu',123)")
        await self.db.commit()
        engine = SyncEngine(self.path, {})
        await engine.start()
        self.addAsyncCleanup(engine.close)
        with patch.object(sync, "luogu_get", new=AsyncMock(return_value="<html>login</html>")):
            self.assertEqual(await engine.sync_single_platform_for_days("12345678", "luogu", 0), -1)
        state = await self.one("SELECT * FROM user_platform_sync_state WHERE platform='luogu'")
        self.assertEqual(state["cursor_timestamp"], 123)
        self.assertEqual(state["last_status"], "failed")
        self.assertEqual([r["problem_id"] for r in await self.rows()], ["P1001"])
