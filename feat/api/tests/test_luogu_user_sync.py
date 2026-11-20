"""Public Luogu AC parsing, binding fences and idempotent persistence (synthetic data)."""
import asyncio
import json
import tempfile
import unittest
from email.utils import formatdate
from itertools import count
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from urllib.parse import urlsplit

from multidict import CIMultiDict

from feat.api import service_runtime
from feat.api.acm_api import luogu_client, sync_service
from feat.api.acm_api import luogu_user_sync as sync
from feat.api.acm_api.binding_guard import BindingChanged
from feat.api.acm_api.binding_service import apply_binding
from feat.api.acm_api.crawler import Crawler
from feat.api.acm_api.database import connect_db
from feat.api.acm_api.luogu_client import LuoguUnavailable
from feat.api.acm_api.problem_bank import save_metadata_batch
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


class PracticeResponse:
    def __init__(self, status=200, *, body="", headers=None, cookies=None):
        self.status = status
        self.body = body
        self.headers = CIMultiDict(headers or {})
        self.cookies = cookies or {}
        self.content = self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass

    async def iter_chunked(self, _):
        yield self.body.encode("utf-8")


class AllMemberPracticeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "members.db"
        self.db = await connect_db(path)
        self.addAsyncCleanup(self.db.close)
        await self.add_members([("11111111", "Member A", "111"), ("22222222", "Member B", "222")])
        self.engine = SyncEngine(path, {})
        await self.engine.start()
        self.addAsyncCleanup(self.engine.close)
        self.manager = WebTaskManager(self.engine)
        self.addAsyncCleanup(self.manager.close)
        self.now = 1_800_000_000
        update_sequence = count()
        clock = SimpleNamespace(time=lambda: self.now, monotonic=lambda: self.now,
                                time_ns=lambda: self.now * 10**9 + next(update_sequence))
        for module in (luogu_client, sync_service, service_runtime):
            self.enterContext(patch.object(module, "time", clock))
        self.enterContext(patch.object(luogu_client.asyncio, "sleep", new=AsyncMock()))
        self.get = Mock()

    async def add_members(self, members):
        await self.db.executemany("INSERT INTO users(qq_id,name,luogu_id) VALUES(?,?,?)", members)
        await self.db.commit()

    async def execute_cycle(self, responses, **options):
        self.get.reset_mock()
        self.get.side_effect = responses
        with patch.object(self.engine, "_http_session", SimpleNamespace(get=self.get)):
            submitted = await self.manager.submit_all_accounts_sync(**options)
            task = self.manager.tasks[submitted["id"]]
            await task["_task"]
        return task

    def requested_paths(self):
        return [urlsplit(call.args[0]).path for call in self.get.call_args_list]

    async def state(self, qq_id):
        async with self.db.execute("SELECT * FROM user_platform_sync_state WHERE user_qq_id=? AND platform='luogu'",
                                   (qq_id,)) as cursor:
            return await cursor.fetchone()

    async def test_failed_practice_is_limited_to_one_member_and_preserves_ac(self):
        await self.db.execute("INSERT INTO submissions(user_qq_id,platform,problem_id,submit_time) VALUES('11111111','luogu','P1001',123)")
        await self.db.commit()
        task = await self.execute_cycle([
            PracticeResponse(302, headers={"Location": "/user/111/practice"}, cookies={"session": "synthetic"}),
            PracticeResponse(403),
            PracticeResponse(body=page(["P1002", "CF1A"], account=222)),
        ])
        self.assertEqual(self.requested_paths(), ["/user/111/practice", "/user/111/practice", "/user/222/practice"])
        self.assertEqual(task["status"], "partial")
        self.assertEqual(task["result"], {"11111111": {"luogu": -1}, "22222222": {"luogu": 1}})
        self.assertEqual(task["luogu_members"], {"11111111": {"name": "Member A", "uid": "111"},
                                                 "22222222": {"name": "Member B", "uid": "222"}})
        error = task["errors"]["11111111"]["luogu"]
        self.assertEqual((error["code"], error["http_status"], error["consecutive_failures"]), ("luogu_http_403", 403, 1))
        self.assertTrue(error["request_attempted"])
        self.assertFalse(error["deferred"])
        self.assertEqual(error["next_retry_at"], self.now + 60)
        self.assertFalse(luogu_client.recovery_pending())
        async with self.db.execute("SELECT user_qq_id,problem_id,submit_time FROM submissions ORDER BY user_qq_id") as cursor:
            self.assertEqual([tuple(row) for row in await cursor.fetchall()],
                             [("11111111", "P1001", 123), ("22222222", "P1002", 0)])

        self.now += 10
        task = await self.execute_cycle([PracticeResponse(body=page(["P1002"], account=222))])
        self.assertEqual(self.requested_paths(), ["/user/222/practice"])
        self.assertEqual(task["status"], "waiting")
        waiting = task["errors"]["11111111"]["luogu"]
        self.assertEqual(waiting["code"], "luogu_retry_wait")
        self.assertTrue(waiting["deferred"])
        self.assertFalse(waiting["request_attempted"])
        self.assertIsNone(waiting["http_status"])
        state = await self.state("11111111")
        self.assertEqual(state["last_error_code"], "luogu_http_403")
        self.assertEqual(state["last_attempt_at"], self.now - 10)
        self.assertEqual(waiting["consecutive_failures"], 1)
        self.assertEqual(waiting["next_retry_at"], state["next_retry_at"])
        self.assertEqual(waiting["next_retry_at"], error["next_retry_at"])

    async def test_shared_cooldown_defers_luogu_and_recovers_in_the_next_cycle(self):
        await self.add_members([("33333333", "Member C", "333"), ("44444444", "Member D", "444")])
        await self.db.execute("UPDATE users SET atcoder_handle='OtherPlatform' WHERE qq_id='22222222'")
        await self.db.execute("INSERT INTO user_platform_sync_state(user_qq_id,platform,next_retry_at) VALUES('22222222','luogu',?)",
                              (self.now + 300,))
        await self.db.commit()
        with patch.object(Crawler, "fetch_atcoder_submissions", new=AsyncMock(return_value=1)) as atcoder:
            task = await self.execute_cycle([PracticeResponse(429, headers={"Retry-After": "120"})])
            atcoder.assert_awaited_once()
        self.assertEqual(self.requested_paths(), ["/user/111/practice"])
        self.assertEqual(task["result"]["22222222"], {"luogu": -1, "atcoder": 1})
        errors = {qq: details["luogu"] for qq, details in task["errors"].items()}
        self.assertEqual(errors["11111111"]["http_status"], 429)
        self.assertTrue(errors["11111111"]["request_attempted"])
        self.assertFalse(errors["11111111"]["deferred"])
        for qq in ("22222222", "33333333", "44444444"):
            with self.subTest(qq=qq):
                error = errors[qq]
                self.assertTrue(error["deferred"])
                self.assertFalse(error["request_attempted"])
                self.assertIsNone(error["http_status"])
                self.assertEqual(error["cause_http_status"], 429)
                state = await self.state(qq)
                self.assertEqual((state["last_status"], state["last_attempt_at"], state["consecutive_failures"]),
                                 ("waiting", 0, 0))
                self.assertEqual(error["next_retry_at"], state["next_retry_at"])
        self.assertEqual(errors["22222222"]["next_retry_at"], self.now + 300)
        async with self.db.execute("SELECT value FROM settings WHERE key='luogu_request_gate'") as cursor:
            gate = json.loads((await cursor.fetchone())[0])
        self.assertEqual((gate["cause_http_status"], gate["failures"], gate["blocked_until"]), (429, 1, self.now + 120))

        self.now += 301
        luogu_client._GATES.pop(asyncio.get_running_loop())
        probes = []
        responses = iter([PracticeResponse(403), PracticeResponse(body=page(["P1003"], account=333)),
                          PracticeResponse(body=page(["P1004"], account=444)), PracticeResponse(body=page(account=111))])

        def respond(*args, **kwargs):
            probes.append(luogu_client.recovery_pending())
            return next(responses)

        with patch.object(Crawler, "fetch_atcoder_submissions", new=AsyncMock(return_value=0)):
            next_task = await self.execute_cycle(respond, scheduled=True, incremental=True)
        self.assertEqual(self.requested_paths(), ["/user/222/practice", "/user/333/practice", "/user/444/practice", "/user/111/practice"])
        self.assertEqual(probes, [True, True, False, False])
        self.assertEqual(next_task["result"]["33333333"]["luogu"], 1)
        self.assertEqual(next_task["result"]["44444444"]["luogu"], 1)
        self.assertEqual(next_task["errors"]["22222222"]["luogu"]["http_status"], 403)
        self.assertFalse(luogu_client.recovery_pending())

    async def test_retry_after_date_and_confirmed_challenge_trigger_cooldown(self):
        for status, headers in ((403, {"Retry-After": formatdate(self.now + 600, usegmt=True)}),
                                (200, {"cf-mitigated": "challenge"})):
            with self.subTest(status=status):
                await self.db.execute("DELETE FROM user_platform_sync_state WHERE platform='luogu'")
                await self.db.execute("DELETE FROM settings WHERE key='luogu_request_gate'")
                await self.db.commit()
                luogu_client._GATES.pop(asyncio.get_running_loop(), None)
                task = await self.execute_cycle([PracticeResponse(status, headers=headers)])
                self.assertEqual(self.requested_paths(), ["/user/111/practice"])
                error = task["errors"]["11111111"]["luogu"]
                self.assertTrue(error["request_attempted"])
                self.assertEqual(error["http_status"], status)
                if status == 403:
                    self.assertEqual(error["next_retry_at"], self.now + 600)
                waiting = task["errors"]["22222222"]["luogu"]
                self.assertTrue(waiting["deferred"])
                self.assertEqual(waiting["cause_http_status"], status)
                self.assertEqual(waiting["next_retry_at"], error["next_retry_at"])

    async def test_invalid_saved_uid_is_reported_without_counting_an_http_attempt(self):
        await self.db.execute("UPDATE users SET luogu_id='invalid' WHERE qq_id='11111111'")
        await self.db.commit()
        task = await self.execute_cycle([PracticeResponse(body=page(account=222))])
        self.assertEqual(self.requested_paths(), ["/user/222/practice"])
        error = task["errors"]["11111111"]["luogu"]
        self.assertEqual(error["code"], "luogu_invalid_uid")
        self.assertFalse(error["request_attempted"])
        self.assertFalse(error["deferred"])
        self.assertEqual(error["consecutive_failures"], 0)
        self.assertEqual(error["next_retry_at"], 0)
        state = await self.state("11111111")
        self.assertEqual((state["last_status"], state["last_attempt_at"]), ("failed", 0))
