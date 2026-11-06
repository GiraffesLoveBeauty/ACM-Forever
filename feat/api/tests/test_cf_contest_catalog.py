"""Paired CF divisions keep their own complete, locally readable contest catalogs."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import test_api_contract as contract
from feat.api.acm_api.cf_client import CFUnavailable
from feat.api.acm_api.cf_contest_catalog import complete_cf_catalog, save_cf_contest_catalog
from feat.api.acm_api.contest_metadata import save_contests
from feat.api.acm_api.database import connect_db
from feat.api.acm_api.problem_bank import save_metadata_batch, save_problem
from feat.api.acm_api.problem_sync import ProblemSync, cf_catalog_metadata, cf_metadata, sync_options


DIV1_NAMES = [
    ("A", "Hot Potatoes at the Fairy Warehouse"),
    ("B", "A Ribbon for Tomorrow"),
    ("C", "Even If the World Turns"),
    ("D", "How Long Until Nothing Remains?"),
    ("E1", "What Will Remain at the End? (Easy Version)"),
    ("E2", "What Will Remain at the End? (Hard Version)"),
    ("F", "Who Will Witness the End?"),
]
DIV2_NAMES = [
    ("A", "Three Numbers on the Blackboard"),
    ("B", "Domino Tiles"),
    *[(index, name) for index, (_, name) in zip("CDEF", DIV1_NAMES[:4])],
]


def raw_problems(contest):
    names = DIV1_NAMES if str(contest) == "2255" else DIV2_NAMES
    return [{"contestId": int(contest), "index": index, "name": name,
             "type": "PROGRAMMING", "rating": 1200, "tags": ["math"]}
            for index, name in names]


def bulk_catalog():
    # The archive lists a shared task only once: Div.2 retains just A and B.
    return cf_catalog_metadata(raw_problems("2255") + raw_problems("2256")[:2])


async def seed_pair(db):
    await save_contests(db, [
        {"platform": "codeforces", "contest_id": "2255",
         "contest_name": "Codeforces Round 1116 (Div. 1)", "start_time": 1_780_000_000},
        {"platform": "codeforces", "contest_id": "2256",
         "contest_name": "Codeforces Round 1116 (Div. 2)", "start_time": 1_780_000_000},
    ])
    await save_metadata_batch(db, bulk_catalog())


async def standings(session, method, params):
    if method != "contest.standings" or set(params) != {"contestId"}:
        raise AssertionError(f"Unexpected CF request: {method} {params}")
    contest = str(params["contestId"])
    return {"contest": {"id": int(contest), "phase": "FINISHED"},
            "problems": raw_problems(contest), "rows": []}


class CfContestCatalogTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.db_path = Path(directory.name) / "catalog.db"
        self.db = await connect_db(self.db_path)
        self.addAsyncCleanup(self.db.close)
        self.now = 1_800_000_000
        self.enterContext(patch("feat.api.acm_api.cf_contest_catalog.time.time", side_effect=lambda: self.now))
        await seed_pair(self.db)

    async def cache_rows(self):
        async with self.db.execute(
            "SELECT contest_id,problem_ids,updated_at FROM crawler_contest_catalogs "
            "WHERE platform='codeforces' ORDER BY contest_id"
        ) as cursor:
            return [dict(row) for row in await cursor.fetchall()]

    async def complete(self, network=None):
        network = network or AsyncMock(side_effect=standings)
        with patch("feat.api.acm_api.cf_contest_catalog.cf_request", network):
            result = await complete_cf_catalog(self.db, object(), bulk_catalog(), cf_metadata)
        return result, network

    async def test_paired_divisions_get_separate_official_indices_and_reuse_complete_cache(self):
        (items, errors), network = await self.complete()
        self.assertEqual(errors, [])
        self.assertEqual(network.await_count, 2)
        by_contest = {}
        for item in items:
            by_contest.setdefault(item["contest_id"], []).append(item)
        self.assertEqual({cid: len(rows) for cid, rows in by_contest.items()}, {"2255": 7, "2256": 6})
        shared = next(item for item in items if item["problem_id"] == "cf_2256C")
        self.assertEqual((shared["contest_id"], shared["problem_index"], shared["problem_name"]),
                         ("2256", "C", DIV1_NAMES[0][1]))
        self.assertEqual(shared["problem_url"], "https://codeforces.com/contest/2256/problem/C")
        cache = await self.cache_rows()
        self.assertEqual([len(json.loads(row["problem_ids"])) for row in cache], [7, 6])

        (again, errors), network = await self.complete(AsyncMock(side_effect=AssertionError("cache miss")))
        self.assertEqual(errors, [])
        self.assertEqual({item["problem_id"] for item in again}, {item["problem_id"] for item in items})
        network.assert_not_awaited()
        async with self.db.execute("SELECT COUNT(*) FROM crawler_problems") as cursor:
            self.assertEqual((await cursor.fetchone())[0], 13)

    async def test_metadata_completion_preserves_previously_saved_statement_and_samples(self):
        item = next(item for item in bulk_catalog() if item["problem_id"] == "cf_2256A")
        content = {"statement_html": "<p>Saved body</p>", "statement_text": "Saved body",
                   "statement_language": "en", "requested_language": "en",
                   "samples": [{"index": 1, "input": "1\n", "output": "2\n"}],
                   "source_url": item["problem_url"], "sha256": "saved"}
        await save_problem(self.db, item, content)
        await self.complete()
        async with self.db.execute(
            "SELECT statement_html,samples,last_fetch_status,statement_sha256 "
            "FROM crawler_problems WHERE problem_id='cf_2256A'"
        ) as cursor:
            row = await cursor.fetchone()
        self.assertEqual((row["statement_html"], row["last_fetch_status"], row["statement_sha256"]),
                         ("<p>Saved body</p>", "ok", "saved"))
        self.assertEqual(json.loads(row["samples"]), content["samples"])

    async def test_same_round_name_with_different_start_time_is_not_guessed_as_a_pair(self):
        await self.db.execute("UPDATE crawler_contests SET start_time=start_time+60 WHERE contest_id='2256'")
        await self.db.commit()
        (items, errors), network = await self.complete()
        self.assertEqual(errors, [])
        self.assertEqual(len(items), 9)
        network.assert_not_awaited()

    async def test_same_start_time_with_different_round_name_is_not_guessed_as_a_pair(self):
        await self.db.execute(
            "UPDATE crawler_contests SET contest_name='Codeforces Round 1117 (Div. 2)' WHERE contest_id='2256'"
        )
        await self.db.commit()
        (items, errors), network = await self.complete()
        self.assertEqual(errors, [])
        self.assertEqual(len(items), 9)
        network.assert_not_awaited()

    async def test_division_suffix_inside_parentheses_still_completes_both_lists(self):
        await self.db.executemany(
            "UPDATE crawler_contests SET contest_name=? WHERE contest_id=?",
            [(f"Codeforces Round 1127 (Div. {division}, Based on Mexican Olympiad in Informatics 2026)", cid)
             for division, cid in ((1, "2255"), (2, "2256"))],
        )
        await self.db.commit()
        (items, errors), network = await self.complete()
        self.assertEqual((len(items), errors, network.await_count), (13, [], 2))

    async def test_combined_division_label_is_not_matched_to_a_separate_division(self):
        await self.db.execute(
            "UPDATE crawler_contests SET contest_name='Codeforces Round 1116 (Div. 1 + Div. 2)' "
            "WHERE contest_id='2255'"
        )
        await self.db.commit()
        (items, errors), network = await self.complete()
        self.assertEqual((len(items), errors), (9, []))
        network.assert_not_awaited()

    async def test_failure_does_not_cache_incomplete_contest_and_next_run_can_retry(self):
        async def partial(session, method, params):
            if str(params["contestId"]) == "2256":
                raise CFUnavailable("temporary outage")
            return await standings(session, method, params)

        (items, errors), _ = await self.complete(AsyncMock(side_effect=partial))
        self.assertEqual(len(items), 9)
        self.assertEqual([error["contest_id"] for error in errors], ["2256"])
        self.assertIn("temporary outage", errors[0]["error"])
        self.assertEqual([row["contest_id"] for row in await self.cache_rows()], ["2255"])

        (items, errors), network = await self.complete()
        self.assertEqual(errors, [])
        self.assertEqual(len(items), 13)
        self.assertEqual(network.await_count, 1)
        self.assertEqual(str(network.await_args.args[2]["contestId"]), "2256")

    async def test_expired_successful_catalog_remains_available_during_upstream_failure(self):
        (items, errors), _ = await self.complete()
        self.assertEqual(errors, [])
        previous_cache = await self.cache_rows()
        self.now += 8 * 24 * 60 * 60
        (fallback, errors), network = await self.complete(AsyncMock(side_effect=CFUnavailable("offline")))
        self.assertEqual(network.await_count, 2)
        self.assertEqual({item["problem_id"] for item in fallback}, {item["problem_id"] for item in items})
        self.assertEqual({error["contest_id"] for error in errors}, {"2255", "2256"})
        self.assertEqual(await self.cache_rows(), previous_cache)

    async def test_expired_shared_problem_metadata_is_replaced_by_new_official_response(self):
        await self.complete()
        self.now += 8 * 24 * 60 * 60

        async def corrected(session, method, params):
            payload = await standings(session, method, params)
            if str(params["contestId"]) == "2256":
                payload["problems"][2]["name"] = "Corrected official title"
            return payload

        (items, errors), _ = await self.complete(AsyncMock(side_effect=corrected))
        self.assertEqual(errors, [])
        item = next(item for item in items if item["problem_id"] == "cf_2256C")
        self.assertEqual(item["problem_name"], "Corrected official title")
        async with self.db.execute(
            "SELECT problem_name FROM crawler_problems WHERE problem_id='cf_2256C'"
        ) as cursor:
            self.assertEqual((await cursor.fetchone())[0], "Corrected official title")

    async def test_single_contest_complete_list_is_also_reused_by_platform_completion(self):
        await save_cf_contest_catalog(self.db, "2256", cf_metadata(raw_problems("2256"), "2256"))
        (items, errors), network = await self.complete()
        self.assertEqual(errors, [])
        self.assertEqual(len(items), 13)
        self.assertEqual(network.await_count, 1)
        self.assertEqual(str(network.await_args.args[2]["contestId"]), "2255")

    async def test_single_contest_limit_and_statement_failure_keep_complete_metadata(self):
        payload = await standings(object(), "contest.standings", {"contestId": 2256})
        payload["contest"].update(name="Codeforces Round 1116 (Div. 2)", startTimeSeconds=1_780_000_000)
        collector = ProblemSync(self.db_path)
        task = {}
        with patch("feat.api.acm_api.problem_sync.cf_request", return_value=payload) as network, \
                patch.object(collector, "download", return_value=b"<html>Missing statement</html>") as download:
            await collector.run(sync_options({"platform": "codeforces", "contest_id": 2256, "limit": 1}), task)
        self.assertEqual(task["status"], "failed")
        result = task["result"]
        self.assertEqual((result["discovered_count"], result["selected_count"], result["remaining_count"]), (6, 1, 5))
        self.assertEqual((result["success_count"], result["failure_count"]), (0, 1))
        self.assertEqual(result["failures"][0]["problem_id"], "cf_2256A")
        self.assertEqual(download.await_count, 1)
        self.assertEqual(network.await_args.args[1:], ("contest.standings", {"contestId": 2256}))
        async with self.db.execute(
            "SELECT problem_id,last_fetch_status FROM crawler_problems WHERE contest_id='2256' ORDER BY problem_index"
        ) as cursor:
            rows = await cursor.fetchall()
        self.assertEqual([row["problem_id"] for row in rows], [f"cf_2256{index}" for index in "ABCDEF"])
        self.assertEqual([row["last_fetch_status"] for row in rows], ["failed", *(["never"] * 5)])
        cache = await self.cache_rows()
        self.assertEqual([(row["contest_id"], len(json.loads(row["problem_ids"]))) for row in cache], [("2256", 6)])

    async def test_platform_collection_publishes_completed_division_lists_before_statements(self):
        payload = {"problems": raw_problems("2255") + raw_problems("2256")[:2]}
        collector = ProblemSync(self.db_path)
        task = {}
        body = b'<div class="problem-statement"><p>Solve it.</p><div class="sample-test"></div></div>'
        with patch("feat.api.acm_api.problem_sync.cf_request", return_value=payload) as archive, \
                patch("feat.api.acm_api.problem_sync.refresh_contests", return_value=0), \
                patch("feat.api.acm_api.cf_contest_catalog.cf_request", side_effect=standings) as complete, \
                patch.object(collector, "download", return_value=body) as download:
            await collector.run(sync_options({"platform": "codeforces", "scope": "platform", "batch_size": 5}), task)
        self.assertEqual(task["status"], "completed", task["result"])
        result = task["result"]
        self.assertEqual((result["discovered_count"], result["metadata_count"], result["selected_count"]), (13, 13, 13))
        self.assertEqual((result["success_count"], result["failure_count"]), (13, 0))
        self.assertEqual(result["contest_catalog_failure_count"], 0)
        self.assertEqual(archive.await_args.args[1:], ("problemset.problems",))
        self.assertEqual(complete.await_count, 2)
        self.assertEqual(download.await_count, 13)
        async with self.db.execute(
            "SELECT contest_id,COUNT(*) FROM crawler_problems WHERE last_fetch_status='ok' GROUP BY contest_id"
        ) as cursor:
            self.assertEqual(dict(await cursor.fetchall()), {"2255": 7, "2256": 6})


class CfContestCatalogApiTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = contract.ApiContractTests.asyncSetUp
    asyncTearDown = contract.ApiContractTests.asyncTearDown
    account_login = contract.ApiContractTests.account_login

    async def test_each_division_tracker_cell_opens_its_own_local_catalog_detail(self):
        async with self.app.test_app():
            client = self.app.test_client()
            await self.account_login(client, role="member")
            db = await connect_db(self.db_path)
            try:
                await seed_pair(db)
                with patch("feat.api.acm_api.cf_contest_catalog.cf_request", side_effect=standings):
                    _, errors = await complete_cf_catalog(db, object(), bulk_catalog(), cf_metadata)
                self.assertEqual(errors, [])
                await db.execute(
                    "INSERT INTO submissions(user_qq_id,platform,problem_id,problem_name,submit_time) "
                    "VALUES('12345678','codeforces','cf_2256C','Saved AC title',10)"
                )
                await db.commit()
            finally:
                await db.close()
            with patch("feat.api.acm_api.backend_api.cf_request", new_callable=AsyncMock) as network:
                response = await client.get("/api/me/problems/tracker?platform=codeforces")
                self.assertEqual(response.status_code, 200)
                data = await response.get_json()
                contests = {row["contest_id"]: row for row in data["items"]}
                self.assertEqual({cid: row["total_count"] for cid, row in contests.items()}, {"2255": 7, "2256": 6})
                self.assertEqual([p["problem_index"] for p in contests["2256"]["problems"]], list("ABCDEF"))
                self.assertEqual(contests["2256"]["solved_count"], 1)
                for contest in contests.values():
                    for cell in contest["problems"]:
                        detail_response = await client.get(f"/api/me/problems/codeforces/{cell['problem_id']}")
                        self.assertEqual(detail_response.status_code, 200)
                        detail = await detail_response.get_json()
                        self.assertEqual(detail["contest_id"], contest["contest_id"])
                        self.assertEqual(detail["problem_id"], cell["problem_id"])
                        self.assertEqual(detail["problem_name"], cell["problem_name"])
                network.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
