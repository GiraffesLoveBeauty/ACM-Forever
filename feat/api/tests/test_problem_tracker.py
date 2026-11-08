"""Contest tracker uses the current account's local submission evidence only."""

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import test_api_contract as contract
from feat.api.acm_api.database import connect_db
from feat.api.acm_api.problem_bank import save_metadata_batch
from test_problem_sync import CF_PDF

with patch.object(sys, "path", [str(Path(__file__).resolve().parents[3] / "tools/crawlers"), *sys.path]):
    from codeforces_sample import make_sample
    from problem_store import ProblemStore


class ProblemTrackerTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = contract.ApiContractTests.asyncSetUp
    asyncTearDown = contract.ApiContractTests.asyncTearDown
    account_login = contract.ApiContractTests.account_login

    async def execute(self, sql, rows):
        db = await connect_db(self.db_path)
        try:
            await db.executemany(sql, rows)
            await db.commit()
        finally:
            await db.close()

    async def catalog(self, items):
        db = await connect_db(self.db_path)
        try:
            await save_metadata_batch(db, items)
        finally:
            await db.close()

    def offline_problem(self, contest=100, index="A", pdf=False):
        items = make_sample([{"contestId": contest, "index": index, "type": "PROGRAMMING",
                              "name": "Offline saved problem", "rating": 1600, "tags": ["math"]}], 1)
        store = ProblemStore(self.db_path)
        content = {"statement_html": None if pdf else "<p>Offline saved statement</p>",
                   "statement_text": None if pdf else "Offline saved statement",
                   "statement_pdf": CF_PDF if pdf else None,
                   "statement_language": "en", "requested_language": "en",
                   "samples": [] if pdf else [{"index": 1, "input": "1\n", "output": "2\n"}],
                   "source_url": items[0]["problem_url"], "sha256": "offline-fixture"}
        try:
            store.import_metadata(items)
            store.save_content("codeforces", items[0]["problem_id"], content)
        finally:
            store.close()
        return items[0], content

    @staticmethod
    def problem(contest, index, platform="codeforces", **kwargs):
        if platform == "codeforces":
            pid = f"cf_{contest}{index}"
            url = f"https://codeforces.com/contest/{contest}/problem/{index}"
        else:
            pid = f"{contest}_{index.lower()}"
            url = f"https://atcoder.jp/contests/{contest}/tasks/{pid}"
        return {"platform": platform, "problem_id": pid, "contest_id": contest,
                "problem_index": index, "problem_name": f"Problem {index}",
                "problem_url": url, "problem_rating": 1200, "tags": ["math"], **kwargs}

    async def test_progress_deduplicates_ac_and_uses_only_current_account(self):
        async with self.app.test_app():
            client = self.app.test_client()
            await self.account_login(client, role="member")
            await self.catalog([self.problem("100", index) for index in ("D2", "A", "C", "B", "D1")])
            await self.execute(
                "INSERT INTO submissions(user_qq_id,platform,problem_id,problem_name,submit_time) "
                "VALUES(?,'codeforces',?,'old title',?)",
                [("12345678", "100A", 10), ("87654321", "cf_100C", 50)],
            )
            await self.execute(
                "INSERT INTO submission_attempts(owner_qq_id,platform,problem_id,contest_id,verdict,submitted_at,created_at,source_code) "
                "VALUES(?,'codeforces',?,'100',?,?,1,'secret source')",
                [("12345678", "cf_100A", "WRONG_ANSWER", 30),
                 ("12345678", "cf_100B", "WRONG_ANSWER", 20),
                 ("12345678", "100D1", "OK", 15),
                 ("12345678", "cf_100D1", "WRONG_ANSWER", 40),
                 ("87654321", "cf_100C", "OK", 60)],
            )
            await self.execute("INSERT INTO user_problem_state(owner_qq_id,platform,problem_id,is_favorite,updated_at) VALUES(?,'codeforces',?,1,1)",
                               [("12345678", "100A"), ("87654321", "cf_100C")])
            with patch("feat.api.acm_api.backend_api.cf_request", new_callable=AsyncMock) as network:
                response = await client.get("/api/me/problems/tracker?owner_qq_id=87654321&qq_id=87654321")
                network.assert_not_awaited()
            self.assertEqual(response.status_code, 200)
            data = await response.get_json()
            self.assertEqual((data["total"], data["page"], data["page_size"]), (1, 1, 20))
            contest = data["items"][0]
            self.assertEqual((contest["total_count"], contest["solved_count"], contest["attempted_count"]), (5, 2, 1))
            self.assertEqual(contest["contest_name"], "Codeforces #100")
            self.assertEqual([p["problem_index"] for p in contest["problems"]], ["A", "B", "C", "D1", "D2"])
            a, b, c, d1, d2 = contest["problems"]
            self.assertEqual([p["status"] for p in (a, b, c, d1, d2)], ["solved", "attempted", "unseen", "solved", "unseen"])
            self.assertEqual((a["ac_at"], a["last_submit_at"], a["is_favorite"]), (10, 30, True))
            self.assertEqual((d1["ac_at"], d1["last_submit_at"]), (15, 40))
            self.assertEqual(a["problem_name"], "Problem A")
            self.assertFalse(c["is_favorite"])
            self.assertNotIn("secret source", str(data))
            self.assertNotIn("owner_qq_id", str(data))

    async def test_progress_exposes_catalog_ratings_and_whole_algorithm_labels_without_extra_fetch(self):
        async with self.app.test_app():
            client = self.app.test_client()
            await self.account_login(client)
            await self.catalog([
                self.problem("100", "A", tags=["digit dp", "math"], problem_rating=1800),
                self.problem("100", "B", tags=[], problem_rating=None),
            ])
            with patch("feat.api.acm_api.backend_api.cf_request", new_callable=AsyncMock) as network:
                data = await (await client.get("/api/me/problems/tracker?platform=codeforces&problem_tag=digit%20dp")).get_json()
                network.assert_not_awaited()
            a, b = data["items"][0]["problems"]
            self.assertEqual((a["problem_rating"], a["tags"]), (1800, ["digit dp", "math"]))
            self.assertEqual((b["problem_rating"], b["tags"]), (None, []))
            self.assertEqual(data["items"][0]["total_count"], 2)

    async def test_search_scope_and_favorites_filter_contests_without_removing_other_problems(self):
        async with self.app.test_app():
            client = self.app.test_client()
            await self.account_login(client)
            await self.catalog([self.problem(contest, index, contest_name="Named Round" if contest == "100" else "Older Round")
                                for contest in ("20", "100") for index in ("A", "B")])
            await self.execute("INSERT INTO submissions(user_qq_id,platform,problem_id,submit_time) VALUES('12345678','codeforces','cf_100A',10)", [()])
            await self.execute("INSERT INTO user_problem_state(owner_qq_id,platform,problem_id,is_favorite,updated_at) VALUES('12345678','codeforces','cf_100A',1,1)", [()])
            for query in ("tag=cf_100A", "tag=named%20round", "scope=solved", "state=favorite", "scope=solved&state=favorite&tag=100A"):
                with self.subTest(query=query):
                    response = await client.get("/api/me/problems/tracker?" + query)
                    self.assertEqual(response.status_code, 200)
                    data = await response.get_json()
                    self.assertEqual(data["total"], 1)
                    self.assertEqual(data["items"][0]["contest_id"], "100")
                    self.assertEqual([p["problem_index"] for p in data["items"][0]["problems"]], ["A", "B"])
            data = await (await client.get("/api/me/problems/tracker?page_size=1&page=2")).get_json()
            self.assertEqual((data["total"], data["page"], data["page_size"]), (2, 2, 1))
            self.assertEqual(data["items"][0]["contest_id"], "20")
            self.assertEqual(len(data["items"][0]["problems"]), 2)
            self.assertEqual((await (await client.get("/api/me/problems/tracker?page=3&page_size=1")).get_json())["items"], [])

    async def test_identifiers_use_stored_contests_and_include_own_missing_catalog_records(self):
        async with self.app.test_app():
            client = self.app.test_client()
            await self.account_login(client)
            await self.catalog([
                self.problem("921", "01"),
                self.problem("abc100", "A", "atcoder"),
                self.problem("abc99", "B", "atcoder"),
                self.problem("ahc023", "B", "atcoder", problem_id="asprocon10_b",
                             problem_url="https://atcoder.jp/contests/ahc023/tasks/asprocon10_b"),
            ])
            await self.execute("INSERT INTO submissions(user_qq_id,platform,problem_id,problem_name,problem_rating,submit_time) VALUES('12345678',?,?,?,?,10)",
                               [("codeforces", "92101", "numeric index", "2000"),
                                ("codeforces", "cf_999A", "Own missing problem", "1300"),
                                ("atcoder", "abc100_a", "known", None)])
            await self.execute("INSERT INTO submission_attempts(owner_qq_id,platform,problem_id,contest_id,verdict,submitted_at,created_at) VALUES('12345678',?,?,?,?,10,1)",
                               [("atcoder", "asprocon10_b", "ahc023", "AC"),
                                ("codeforces", "cf_999B", "999", "WRONG_ANSWER"),
                                ("codeforces", "malformed", None, "OK")])
            await self.execute("INSERT INTO user_problem_state(owner_qq_id,platform,problem_id,is_favorite,updated_at) VALUES('12345678','codeforces','92101',1,1)", [()])
            data = await (await client.get("/api/me/problems/tracker?platform=codeforces")).get_json()
            self.assertEqual([row["contest_id"] for row in data["items"]], ["999", "921"])
            self.assertEqual([p["status"] for p in data["items"][0]["problems"]], ["solved", "attempted"])
            numeric = data["items"][1]["problems"][0]
            self.assertEqual((numeric["problem_id"], numeric["problem_index"], numeric["status"], numeric["is_favorite"]), ("cf_92101", "01", "solved", True))
            data = await (await client.get("/api/me/problems/tracker?platform=atcoder")).get_json()
            contests = {row["contest_id"]: row for row in data["items"]}
            self.assertEqual(contests["ahc023"]["problems"][0]["status"], "solved")
            self.assertNotIn("asprocon10", contests)
            self.assertEqual([row["contest_id"] for row in data["items"] if row["contest_id"].startswith("abc")], ["abc100", "abc99"])

    async def test_authentication_password_guard_and_all_member_roles(self):
        async with self.app.test_app():
            client = self.app.test_client()
            self.assertEqual((await client.get("/api/me/problems/tracker")).status_code, 401)
            await self.account_login(client, role="member", change=1)
            self.assertEqual((await client.get("/api/me/problems/tracker")).status_code, 428)
            for role in ("member", "admin", "root"):
                await self.execute("UPDATE web_accounts SET role=?,must_change_password=0,credential_version=credential_version+1 WHERE qq_id='12345678'", [(role,)])
                login = await client.post("/api/auth/login", json={"qq_id": "12345678", "password": "Test-Password-123!"})
                self.assertEqual(login.status_code, 200)
                response = await client.get("/api/me/problems/tracker")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(await response.get_json(), {"items": [], "total": 0, "page": 1, "page_size": 20})

    async def test_invalid_filters_and_pagination_return_400(self):
        async with self.app.test_app():
            client = self.app.test_client()
            await self.account_login(client)
            for query in ("platform=luogu", "platform=CODEFORCES", "scope=any", "state=inbox", "page=0", "page=-1", "page=1.2", "page=x", "page_size=0", "page_size=51", "page_size=x", "tag=" + "x" * 101):
                with self.subTest(query=query):
                    self.assertEqual((await client.get("/api/me/problems/tracker?" + query)).status_code, 400)

    async def test_attempt_only_tracker_cells_open_pending_details_for_each_role(self):
        async with self.app.test_app():
            client = self.app.test_client()
            self.assertEqual((await client.get("/api/me/problems/codeforces/cf_999B")).status_code, 401)
            await self.account_login(client, role="member")
            await self.execute(
                "INSERT INTO submission_attempts(owner_qq_id,platform,problem_id,contest_id,verdict,submitted_at,created_at,source_code) "
                "VALUES(?,'codeforces',?,'999','WRONG_ANSWER',10,1,'private attempted source')",
                [("12345678", "cf_999B"), ("87654321", "cf_999C")],
            )
            with patch("feat.api.acm_api.backend_api.cf_request", new_callable=AsyncMock) as network, \
                    patch.object(self.app.task_manager.problem_sync, "download", new_callable=AsyncMock) as download:
                for role in ("member", "admin", "root"):
                    await self.execute(
                        "UPDATE web_accounts SET role=?,credential_version=credential_version+1 WHERE qq_id='12345678'",
                        [(role,)],
                    )
                    login = await client.post("/api/auth/login", json={"qq_id": "12345678", "password": "Test-Password-123!"})
                    self.assertEqual(login.status_code, 200)
                    data = await (await client.get("/api/me/problems/tracker?platform=codeforces&tag=999B")).get_json()
                    cell = data["items"][0]["problems"][0]
                    self.assertEqual((cell["problem_id"], cell["status"]), ("cf_999B", "attempted"))
                    prefixes = ["/api/me/problems"] + (["/api/problems"] if role != "member" else [])
                    for prefix in prefixes:
                        with self.subTest(role=role, prefix=prefix):
                            response = await client.get(f"{prefix}/{cell['platform']}/{cell['problem_id']}")
                            self.assertEqual(response.status_code, 200)
                            detail = await response.get_json()
                            self.assertFalse(detail["content_available"])
                            self.assertEqual(detail["samples"], [])
                            self.assertIsNone(detail["statement_format"])
                            self.assertEqual(detail["last_fetch_status"], "never")
                            self.assertEqual(detail["problem_url"], "https://codeforces.com/contest/999/problem/B")
                            self.assertEqual(detail["contest_id"], "999")
                            self.assertNotIn("private attempted source", str(detail))
                            for key in ("source_code", "owner_qq_id", "verdict", "submitted_at", "external_submission_id"):
                                self.assertNotIn(key, detail)
                            other = await client.get(f"{prefix}/codeforces/cf_999C?qq_id=87654321&owner_qq_id=87654321")
                            self.assertEqual(other.status_code, 404)
                network.assert_not_awaited()
                download.assert_not_awaited()
                self.assertEqual(self.app.task_manager.tasks, {})
            db = await connect_db(self.db_path)
            try:
                for table in ("crawler_problems", "recommendations", "submissions"):
                    self.assertEqual((await (await db.execute(f"SELECT COUNT(*) FROM {table}")).fetchone())[0], 0)
            finally:
                await db.close()

    async def test_attempt_detail_resolves_aliases_and_preserves_catalog_priority(self):
        async with self.app.test_app():
            client = self.app.test_client()
            await self.account_login(client, role="member")
            await self.execute(
                "INSERT INTO submission_attempts(owner_qq_id,platform,problem_id,contest_id,verdict,submitted_at,created_at) "
                "VALUES('12345678',?,?,?,'WRONG_ANSWER',10,1)",
                [("codeforces", "1000d1", "1000"),
                 ("codeforces", "92101", "921"),
                 ("atcoder", "asprocon10_b", "ahc023"),
                 ("codeforces", "malformed", None)],
            )
            cases = [
                ("codeforces", "cf_1000D1", "1000", "https://codeforces.com/contest/1000/problem/D1"),
                ("codeforces", "1000D1", "1000", "https://codeforces.com/contest/1000/problem/D1"),
                ("codeforces", "cf_92101", "921", "https://codeforces.com/contest/921/problem/01"),
                ("atcoder", "asprocon10_b", "ahc023", "https://atcoder.jp/contests/ahc023/tasks/asprocon10_b"),
            ]
            for platform, pid, contest, url in cases:
                with self.subTest(platform=platform, problem_id=pid):
                    response = await client.get(f"/api/me/problems/{platform}/{pid}")
                    self.assertEqual(response.status_code, 200)
                    detail = await response.get_json()
                    self.assertEqual(detail["contest_id"], contest)
                    self.assertEqual(detail["problem_url"], url)
                    self.assertFalse(detail["content_available"])
            for pid in ("malformed", "cf_2000A"):
                self.assertEqual((await client.get(f"/api/me/problems/codeforces/{pid}")).status_code, 404)

            metadata = self.problem("1000", "D1", problem_name="Catalog title", problem_rating=1800,
                                    problem_url="https://codeforces.com/problemset/problem/1000/D1")
            await self.catalog([metadata])
            for keep_crawler in (True, False):
                with self.subTest(keep_crawler=keep_crawler):
                    if not keep_crawler:
                        await self.execute("DELETE FROM crawler_problems WHERE platform='codeforces' AND problem_id='cf_1000D1'", [()])
                    detail = await (await client.get("/api/me/problems/codeforces/cf_1000D1")).get_json()
                    self.assertEqual(detail["problem_name"], metadata["problem_name"])
                    self.assertEqual(int(detail["problem_rating"]), metadata["problem_rating"])
                    self.assertEqual(detail["problem_url"], metadata["problem_url"])
                    self.assertEqual(detail["tags"], ["math"])

    async def test_offline_bare_catalog_tracker_links_open_saved_html_and_pdf_for_all_roles(self):
        async with self.app.test_app():
            client = self.app.test_client()
            await self.account_login(client, role="member")
            fixtures = [self.offline_problem(), self.offline_problem(497, "D", pdf=True)]
            db = await connect_db(self.db_path)
            try:
                for table in ("submission_attempts", "submissions", "recommendations"):
                    self.assertEqual((await (await db.execute(f"SELECT COUNT(*) FROM {table}")).fetchone())[0], 0)
            finally:
                await db.close()
            with patch("feat.api.acm_api.backend_api.cf_request", new_callable=AsyncMock) as network, \
                    patch.object(self.app.task_manager.problem_sync, "download", new_callable=AsyncMock) as download:
                for role in ("member", "admin", "root"):
                    await self.execute("UPDATE web_accounts SET role=?,credential_version=credential_version+1 WHERE qq_id='12345678'", [(role,)])
                    login = await client.post("/api/auth/login", json={"qq_id": "12345678", "password": "Test-Password-123!"})
                    self.assertEqual(login.status_code, 200)
                    for metadata, content in fixtures:
                        pid = metadata["problem_id"]
                        self.assertFalse(pid.startswith("cf_"), "real offline collector emits bare identifiers")
                        tracker = await (await client.get("/api/me/problems/tracker?platform=codeforces&tag=" + pid)).get_json()
                        cell = tracker["items"][0]["problems"][0]
                        self.assertEqual((cell["problem_id"], cell["status"]), ("cf_" + pid, "unseen"))
                        for prefix in ["/api/me/problems"] + (["/api/problems"] if role != "member" else []):
                            with self.subTest(role=role, prefix=prefix, problem=pid):
                                path = f"{prefix}/codeforces/{cell['problem_id']}"
                                response = await client.get(path)
                                self.assertEqual(response.status_code, 200)
                                detail = await response.get_json()
                                self.assertEqual(detail["problem_id"], pid)
                                self.assertTrue(detail["content_available"])
                                self.assertEqual(detail["problem_name"], metadata["problem_name"])
                                self.assertEqual(detail["problem_url"], metadata["problem_url"])
                                self.assertEqual(detail["statement_html"], content["statement_html"])
                                self.assertEqual(detail["samples"], content["samples"])
                                self.assertEqual(detail["statement_format"], "pdf" if content["statement_pdf"] else "html")
                                if content["statement_pdf"]:
                                    for detail_id in (cell["problem_id"], detail["problem_id"]):
                                        pdf_path = f"{prefix}/codeforces/{detail_id}/statement.pdf"
                                        full = await client.get(pdf_path)
                                        self.assertEqual(full.status_code, 200)
                                        self.assertEqual(await full.get_data(), CF_PDF)
                                        part = await client.get(pdf_path, headers={"Range": "bytes=0-7"})
                                        self.assertEqual(part.status_code, 206)
                                        self.assertEqual(await part.get_data(), CF_PDF[:8])
                network.assert_not_awaited()
                download.assert_not_awaited()
                self.assertEqual(self.app.task_manager.tasks, {})

    async def test_saved_alias_beats_pending_exact_catalog_and_equal_content_prefers_exact_id(self):
        async with self.app.test_app():
            client = self.app.test_client()
            await self.account_login(client, role="member")
            metadata, content = self.offline_problem()
            await self.catalog([self.problem("100", "A", problem_name="New pending catalog")])
            response = await client.get("/api/me/problems/codeforces/cf_100A")
            self.assertEqual(response.status_code, 200)
            detail = await response.get_json()
            self.assertTrue(detail["content_available"])
            self.assertEqual(detail["problem_id"], "100A")
            self.assertEqual(detail["statement_html"], content["statement_html"])
            tracker = await (await client.get("/api/me/problems/tracker?platform=codeforces")).get_json()
            self.assertEqual(tracker["items"][0]["total_count"], 1)
            self.assertEqual(len(tracker["items"][0]["problems"]), 1)
            await self.execute("UPDATE crawler_problems SET statement_html='<p>Exact saved statement</p>',statement_text='Exact saved statement',last_fetch_status='ok' WHERE problem_id='cf_100A'", [()])
            exact = await (await client.get("/api/me/problems/codeforces/cf_100A")).get_json()
            self.assertEqual(exact["problem_id"], "cf_100A")
            self.assertEqual(exact["statement_html"], "<p>Exact saved statement</p>")
            bare = await (await client.get("/api/me/problems/codeforces/100A")).get_json()
            self.assertEqual(bare["problem_id"], "100A")
            self.assertEqual(bare["statement_html"], content["statement_html"])

            self.offline_problem(497, "D", pdf=True)
            await self.catalog([self.problem("497", "D")])
            pdf_detail = await (await client.get("/api/me/problems/codeforces/cf_497D")).get_json()
            self.assertEqual((pdf_detail["problem_id"], pdf_detail["statement_format"]), ("497D", "pdf"))
            self.assertEqual(await (await client.get("/api/me/problems/codeforces/cf_497D/statement.pdf")).get_data(), CF_PDF)

    async def test_bare_recommendation_and_ac_metadata_resolve_without_attempts(self):
        async with self.app.test_app():
            client = self.app.test_client()
            await self.account_login(client, role="member")
            await self.execute("INSERT INTO recommendations(platform,problem_id,problem_name,problem_url,tags) VALUES('codeforces',?,?,?,'math')",
                               [("200A", "Bare recommendation", "https://codeforces.com/contest/200/problem/A")])
            await self.execute("INSERT INTO submissions(user_qq_id,platform,problem_id,problem_name,problem_url,submit_time) VALUES('12345678','codeforces',?,?,?,10)",
                               [("201B", "Bare AC", "https://codeforces.com/contest/201/problem/B"),
                                ("cf_200A", "Exact AC duplicate", "https://codeforces.com/problemset/problem/200/A")])
            for pid, title, url in [("200A", "Bare recommendation", "https://codeforces.com/contest/200/problem/A"),
                                    ("201B", "Bare AC", "https://codeforces.com/contest/201/problem/B")]:
                response = await client.get("/api/me/problems/codeforces/cf_" + pid)
                self.assertEqual(response.status_code, 200)
                detail = await response.get_json()
                self.assertEqual((detail["problem_id"], detail["problem_name"], detail["problem_url"]), (pid, title, url))
                self.assertFalse(detail["content_available"])

    async def test_catalog_aliases_support_cf_case_and_numeric_indices_but_keep_atcoder_exact(self):
        async with self.app.test_app():
            client = self.app.test_client()
            await self.account_login(client, role="member")
            self.offline_problem(921, "01")
            self.offline_problem(1000, "D1")
            for requested, stored in [("cf_92101", "92101"), ("92101", "92101"),
                                      ("CF_1000d1", "1000D1"), ("1000d1", "1000D1")]:
                response = await client.get("/api/me/problems/codeforces/" + requested)
                self.assertEqual(response.status_code, 200)
                detail = await response.get_json()
                self.assertEqual(detail["problem_id"], stored)
                self.assertTrue(detail["content_available"])
            await self.catalog([self.problem("Case", "a", "atcoder", problem_id="Case_a", problem_name="Case sensitive")])
            self.assertEqual((await client.get("/api/me/problems/atcoder/Case_a")).status_code, 200)
            for requested in ("case_a", "cf_Case_a"):
                self.assertEqual((await client.get("/api/me/problems/atcoder/" + requested)).status_code, 404)


if __name__ == "__main__":
    unittest.main()
