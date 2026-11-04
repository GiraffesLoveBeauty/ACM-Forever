"""Contest chronology comes from the persisted public catalog, never inferred IDs."""

import contextlib
import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import test_api_contract as contract
from feat.api import sync_contests
from feat.api.acm_api.cf_client import CFUnavailable
from feat.api.acm_api.contest_metadata import contest_metadata, refresh_contests, save_contests
from feat.api.acm_api.database import connect_db
from feat.api.acm_api.problem_bank import save_metadata_batch


class ContestMetadataParsingTests(unittest.TestCase):
    def test_public_catalog_shapes_keep_names_and_unix_seconds(self):
        raw_cf = [{"id": 20, "name": " CF Round ", "startTimeSeconds": 1700000000}]
        expected = [{"platform": "codeforces", "contest_id": "20",
                     "contest_name": "CF Round", "start_time": 1700000000}]
        self.assertEqual(contest_metadata("codeforces", raw_cf), expected)
        self.assertEqual(contest_metadata("codeforces", {"status": "OK", "result": raw_cf}), expected)
        self.assertEqual(contest_metadata("atcoder", [
            {"id": "arc190", "title": " AtCoder Regular Contest 190 ", "start_epoch_second": 1700000100},
        ]), [{"platform": "atcoder", "contest_id": "arc190",
              "contest_name": "AtCoder Regular Contest 190", "start_time": 1700000100}])

    def test_missing_or_invalid_dates_stay_unknown_in_both_catalogs(self):
        for platform, name_key, time_key, cid in (
            ("codeforces", "name", "startTimeSeconds", 20),
            ("atcoder", "title", "start_epoch_second", "abc020"),
        ):
            for value in (None, True, False, "1700000000", 1700000000.5, 0, -1, 253402300800, {}, []):
                with self.subTest(platform=platform, value=value):
                    row = contest_metadata(platform, [{"id": cid, name_key: "Named contest", time_key: value}])[0]
                    self.assertIsNone(row["start_time"])
            with self.subTest(platform=platform, missing=True):
                row = contest_metadata(platform, [{"id": cid, name_key: "Named contest"}])[0]
                self.assertIsNone(row["start_time"])

    def test_invalid_catalogs_and_boolean_cf_ids_are_rejected(self):
        for platform, payload in (
            ("luogu", [{"id": "1", "title": "Unsupported"}]),
            ("codeforces", {"status": "FAILED", "result": [{"id": 20, "name": "Round"}]}),
            ("codeforces", [{"id": True, "name": "Not contest 1"}]),
            ("codeforces", []),
            ("atcoder", {"id": "abc020", "title": "Wrong container"}),
            ("atcoder", [{"id": "../abc020", "title": "Bad ID"}]),
            ("atcoder", [{"id": "abc020", "title": " "}]),
        ):
            with self.subTest(platform=platform, payload=payload), self.assertRaises(ValueError):
                contest_metadata(platform, payload)


class ContestMetadataStorageTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.db_path = Path(self.directory.name) / "catalog.db"

    async def test_fresh_cache_survives_reconnect_and_unknown_update_preserves_date(self):
        db = await connect_db(self.db_path)
        try:
            await save_contests(db, contest_metadata("codeforces", [
                {"id": 20, "name": "Original name", "startTimeSeconds": 200},
            ]))
            await save_contests(db, contest_metadata("codeforces", [{"id": 20, "name": "Updated name"}]))
        finally:
            await db.close()
        db = await connect_db(self.db_path)
        try:
            with patch("feat.api.acm_api.contest_metadata.fetch_contests", side_effect=AssertionError("cache miss")) as fetch:
                self.assertEqual(await refresh_contests(db, object(), "codeforces", ["20"]), 0)
                fetch.assert_not_awaited()
            async with db.execute("SELECT contest_name,start_time,updated_at FROM crawler_contests") as cursor:
                row = await cursor.fetchone()
            self.assertEqual((row["contest_name"], row["start_time"]), ("Updated name", 200))
            self.assertGreater(row["updated_at"], 0)
        finally:
            await db.close()

    async def test_adding_contest_schema_is_idempotent_and_preserves_collected_problem(self):
        db = await connect_db(self.db_path)
        try:
            await db.execute(
                "INSERT INTO crawler_problems(platform,problem_id,contest_id,problem_index,problem_name,"
                "problem_url,metadata_json,statement_html,statement_text,statement_pdf,samples,sample_count,"
                "last_fetch_status,created_at,updated_at) VALUES('codeforces','cf_20A','20','A','Saved problem',"
                "'https://codeforces.com/contest/20/problem/A','{}','<p>Saved body</p>','Saved body',?,"
                "'[{\"input\":\"1\",\"output\":\"2\"}]',1,'ok','old-created','old-updated')",
                (b"%PDF-saved-fixture",),
            )
            # Reproduce an existing problem bank from before the additive table.
            await db.execute("DROP TABLE crawler_contests")
            await db.commit()
            async with db.execute("SELECT * FROM crawler_problems") as cursor:
                original = dict(await cursor.fetchone())
        finally:
            await db.close()
        for _ in range(2):
            db = await connect_db(self.db_path)
            try:
                async with db.execute("SELECT * FROM crawler_problems") as cursor:
                    self.assertEqual(dict(await cursor.fetchone()), original)
                async with db.execute("SELECT COUNT(*) FROM crawler_contests") as cursor:
                    self.assertEqual((await cursor.fetchone())[0], 0)
                async with db.execute("PRAGMA table_info(crawler_contests)") as cursor:
                    self.assertEqual({row["name"] for row in await cursor.fetchall()},
                                     {"platform", "contest_id", "contest_name", "start_time", "updated_at"})
            finally:
                await db.close()


class ContestChronologyTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = contract.ApiContractTests.asyncSetUp
    asyncTearDown = contract.ApiContractTests.asyncTearDown
    account_login = contract.ApiContractTests.account_login

    async def seed(self, records):
        problems, contests = [], []
        for platform, cid, start in records:
            pid = f"cf_{cid}A" if platform == "codeforces" else f"{cid}_a"
            url = (f"https://codeforces.com/contest/{cid}/problem/A" if platform == "codeforces" else
                   f"https://atcoder.jp/contests/{cid}/tasks/{pid}")
            problems.append({"platform": platform, "problem_id": pid, "contest_id": cid,
                             "problem_index": "A", "problem_name": "Saved problem", "problem_url": url,
                             "contest_name": "Old per-problem name"})
            contests.append({"platform": platform, "contest_id": cid,
                             "contest_name": "Cached " + cid, "start_time": start})
        db = await connect_db(self.db_path)
        try:
            await save_metadata_batch(db, problems)
            await save_contests(db, contests)
            await db.execute("UPDATE crawler_contests SET updated_at=0")
            await db.commit()
        finally:
            await db.close()

    async def tracker(self, client, query=""):
        response = await client.get("/api/me/problems/tracker" + query)
        self.assertEqual(response.status_code, 200)
        return await response.get_json()

    async def test_cf_dates_override_id_order_and_get_reads_only_stale_local_cache(self):
        async with self.app.test_app():
            client = self.app.test_client()
            await self.account_login(client, role="member")
            await self.seed([("codeforces", "100", 100), ("codeforces", "20", 200)])
            with patch("feat.api.acm_api.contest_metadata.fetch_contests", side_effect=AssertionError("GET must not refresh")) as fetch, \
                    patch("aiohttp.ClientSession._request", side_effect=AssertionError("GET must stay offline")) as network:
                data = await self.tracker(client)
                self.assertEqual(data, await self.tracker(client))
                fetch.assert_not_awaited()
                network.assert_not_awaited()
            self.assertEqual([(row["contest_id"], row["start_time"]) for row in data["items"]],
                             [("20", 200), ("100", 100)])
            self.assertEqual(data["items"][0]["contest_name"], "Cached 20")
            db = await connect_db(self.db_path)
            try:
                async with db.execute("SELECT updated_at FROM crawler_contests") as cursor:
                    self.assertEqual([row[0] for row in await cursor.fetchall()], [0, 0])
            finally:
                await db.close()

    async def test_atcoder_abc_and_arc_interleave_by_start_time(self):
        async with self.app.test_app():
            client = self.app.test_client()
            await self.account_login(client)
            await self.seed([("atcoder", "abc400", 1700000000),
                             ("atcoder", "arc190", 1700000100),
                             ("atcoder", "abc370", 1700000200)])
            rows = (await self.tracker(client, "?platform=atcoder"))["items"]
            self.assertEqual([row["contest_id"] for row in rows], ["abc370", "arc190", "abc400"])
            self.assertEqual([row["start_time"] for row in rows], [1700000200, 1700000100, 1700000000])

    async def test_equal_dates_use_stable_platform_and_natural_id_order_with_unknown_last(self):
        records = [("atcoder", "abc20", 500), ("codeforces", "20", 500),
                   ("atcoder", "abc100", 500), ("codeforces", "100", 500),
                   ("atcoder", "arc1", 500), ("codeforces", "9999999", None),
                   ("atcoder", "arc999", None), ("codeforces", "1000", None)]
        async with self.app.test_app():
            client = self.app.test_client()
            await self.account_login(client)
            await self.seed(records)
            data = await self.tracker(client)
            self.assertEqual(data, await self.tracker(client))
            self.assertEqual([(row["platform"], row["contest_id"]) for row in data["items"]], [
                ("codeforces", "100"), ("codeforces", "20"),
                ("atcoder", "arc1"), ("atcoder", "abc100"), ("atcoder", "abc20"),
                ("codeforces", "9999999"), ("codeforces", "1000"), ("atcoder", "arc999"),
            ])
            self.assertEqual([row["start_time"] for row in data["items"]], [500] * 5 + [None] * 3)

    async def test_full_chronology_is_sorted_before_default_twenty_contest_pagination(self):
        async with self.app.test_app():
            client = self.app.test_client()
            await self.account_login(client)
            await self.seed([("codeforces", str(cid), 1000 - cid) for cid in range(25, 0, -1)] +
                            [("codeforces", "9999999", None)])
            first = await self.tracker(client)
            second = await self.tracker(client, "?page=2")
            self.assertEqual((first["total"], first["page"], first["page_size"]), (26, 1, 20))
            self.assertEqual((second["total"], second["page"], second["page_size"]), (26, 2, 20))
            self.assertEqual([row["contest_id"] for row in first["items"]], [str(cid) for cid in range(1, 21)])
            self.assertEqual([row["contest_id"] for row in second["items"]],
                             [str(cid) for cid in range(21, 26)] + ["9999999"])
            self.assertEqual((await self.tracker(client, "?page=3"))["items"], [])


class ContestMetadataCliTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.db_path = Path(self.directory.name) / "import.db"
        self.input_path = Path(self.directory.name) / "catalog.json"

    def run_cli(self, platform):
        environment = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        return subprocess.run(
            [sys.executable, "-m", "api.sync_contests", "--database", str(self.db_path),
             "--platform", platform, "--input", str(self.input_path)],
            cwd=Path(__file__).resolve().parents[2], env=environment,
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
        )

    def test_module_imports_real_cf_and_atcoder_json_without_touching_problem_bodies(self):
        feeds = (
            ("codeforces", {"status": "OK", "result": [
                {"id": 20, "name": "Codeforces Round", "startTimeSeconds": 1700000000},
            ]}),
            ("atcoder", [{"id": "abc370", "title": "AtCoder Beginner Contest 370",
                          "start_epoch_second": 1700000100, "duration_second": 6000, "rate_change": "~1999"}]),
        )
        for platform, payload in feeds:
            with self.subTest(platform=platform):
                self.input_path.write_text(json.dumps(payload), encoding="utf-8-sig")
                result = self.run_cli(platform)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout)["updated"], {platform: 1})
        with contextlib.closing(sqlite3.connect(self.db_path)) as db:
            self.assertEqual(db.execute(
                "SELECT platform,contest_id,contest_name,start_time FROM crawler_contests ORDER BY platform"
            ).fetchall(), [("atcoder", "abc370", "AtCoder Beginner Contest 370", 1700000100),
                          ("codeforces", "20", "Codeforces Round", 1700000000)])
            self.assertEqual(db.execute("SELECT COUNT(*) FROM crawler_problems").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM recommendations").fetchone()[0], 0)

    def test_cli_reports_invalid_json_catalog_and_platform_without_tracebacks(self):
        for raw, platform, code in (("{", "codeforces", 1),
                                    (json.dumps({"status": "FAILED", "result": []}), "codeforces", 1),
                                    ("[]", "atcoder", 1), ("[]", "luogu", 2), ("[]", "all", 2)):
            with self.subTest(raw=raw, platform=platform):
                self.input_path.write_text(raw, encoding="utf-8")
                result = self.run_cli(platform)
                self.assertEqual(result.returncode, code)
                self.assertTrue(result.stderr.strip())
                self.assertNotIn("Traceback", result.stderr)
                if code == 1:
                    self.assertIn("比赛元数据同步失败", result.stderr)

    def test_cli_reports_cf_unavailability_as_a_concise_failure(self):
        output = io.StringIO()
        with patch("feat.api.sync_contests.fetch_contests", side_effect=CFUnavailable("fixture unavailable")) as fetch, \
                contextlib.redirect_stderr(output):
            result = sync_contests.main(["--database", str(self.db_path), "--platform", "codeforces"])
        self.assertEqual(result, 1)
        fetch.assert_awaited_once()
        self.assertIn("比赛元数据同步失败", output.getvalue())
        self.assertIn("fixture unavailable", output.getvalue())
        self.assertNotIn("Traceback", output.getvalue())


if __name__ == "__main__":
    unittest.main()
