"""Difficulty provenance must describe the exact rating shown by each problem view."""

import json
import unittest
from unittest.mock import AsyncMock, patch

import test_api_contract as contract
from feat.api.acm_api.database import connect_db
from feat.api.acm_api.problem_bank import save_metadata_batch


FIELDS = ("difficulty_source", "difficulty_raw", "difficulty_is_experimental")


def problem(index="A", rating=1450, **extra):
    pid = "abc200_" + index.lower()
    return {
        "platform": "atcoder", "problem_id": pid, "contest_id": "abc200",
        "problem_index": index, "problem_name": "Synthetic " + index,
        "problem_url": f"https://atcoder.jp/contests/abc200/tasks/{pid}",
        "problem_rating": rating, "tags": ["dp"], **extra,
    }


class DifficultyMetadataTests(unittest.TestCase):
    def test_extraction_keeps_only_public_difficulty_provenance(self):
        from feat.api.acm_api.atcoder_difficulty import difficulty_metadata

        raw = json.dumps({
            "difficulty_source": "atcoder_problems", "difficulty_raw": -250,
            "difficulty_is_experimental": True, "problem_name": "private metadata",
            "private_payload": "do-not-publish", "statement_html": "not-an-api-field",
        })
        self.assertEqual(difficulty_metadata(raw), {
            "difficulty_source": "atcoder_problems", "difficulty_raw": -250,
            "difficulty_is_experimental": True,
        })

    def test_malformed_or_non_object_metadata_does_not_fabricate_provenance(self):
        from feat.api.acm_api.atcoder_difficulty import difficulty_metadata

        for raw in (None, "", "{broken", "[]", "null", "false", '"a string"'):
            with self.subTest(raw=raw):
                parsed = difficulty_metadata(raw)
                self.assertIsNone(parsed.get("difficulty_source"))
                self.assertFalse(set(parsed) - set(FIELDS))


class ProblemDifficultyApiTests(unittest.IsolatedAsyncioTestCase):
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

    async def get(self, client, path):
        response = await client.get(path)
        self.assertEqual(response.status_code, 200, path)
        return await response.get_json()

    def no_private_metadata(self, data):
        self.assertNotIn("metadata_json", str(data))
        self.assertNotIn("private_payload", str(data))
        self.assertNotIn("do-not-publish", str(data))

    async def test_attach_uses_exact_problem_and_displayed_rating_including_zero(self):
        from feat.api.acm_api.atcoder_difficulty import attach_difficulty_metadata

        async with self.app.test_app():
            await self.catalog([
                problem("A", 0, difficulty_source="atcoder_problems", difficulty_raw=-10000,
                        difficulty_is_experimental=False),
                problem("B", 1450, difficulty_source="atcoder_problems", difficulty_raw=1450),
                problem("C", 800),
                problem("D", 900),
            ])
            await self.execute("UPDATE crawler_problems SET metadata_json='{broken' WHERE problem_id=?",
                               [("abc200_d",)])
            rows = [
                {"platform": "atcoder", "problem_id": "abc200_a", "problem_rating": "0"},
                {"platform": "atcoder", "problem_id": "abc200_b", "problem_rating": 800},
                {"platform": "atcoder", "problem_id": "abc200_c", "problem_rating": 800},
                {"platform": "atcoder", "problem_id": "abc200_d", "problem_rating": 900},
                {"platform": "atcoder", "problem_id": "abc200_e", "problem_rating": 1450},
                {"platform": "codeforces", "problem_id": "abc200_b", "problem_rating": 1450},
                {"platform": "atcoder", "problem_id": "ABC200_A", "problem_rating": 0},
            ]
            db = await connect_db(self.db_path)
            try:
                await attach_difficulty_metadata(db, rows)
            finally:
                await db.close()
            self.assertEqual(rows[0].get("difficulty_source"), "atcoder_problems")
            self.assertEqual(rows[0].get("difficulty_raw"), -10000)
            self.assertIs(rows[0].get("difficulty_is_experimental"), False)
            for row in rows[1:]:
                self.assertIsNone(row.get("difficulty_source"), row)
            self.no_private_metadata(rows)

    async def test_member_admin_database_tracker_and_detail_share_confirmed_source(self):
        async with self.app.test_app():
            client = self.app.test_client()
            await self.account_login(client, role="admin")
            await self.catalog([problem(
                difficulty_source="atcoder_problems", difficulty_raw=1450,
                difficulty_is_experimental=True, private_payload="do-not-publish",
            )])
            paths = [
                "/api/me/problems?platform=atcoder", "/api/problems?platform=atcoder",
                "/api/admin/database/problems?platform=atcoder",
                "/api/me/problems/tracker?platform=atcoder",
                "/api/me/problems/atcoder/abc200_a", "/api/problems/atcoder/abc200_a",
            ]
            for path in paths:
                with self.subTest(path=path):
                    data = await self.get(client, path)
                    item = (data["items"][0]["problems"][0] if "/tracker?" in path else
                            data["items"][0] if "items" in data else data)
                    self.assertEqual(int(item["problem_rating"]), 1450)
                    self.assertEqual({key: item.get(key) for key in FIELDS}, {
                        "difficulty_source": "atcoder_problems", "difficulty_raw": 1450,
                        "difficulty_is_experimental": True,
                    })
                    self.no_private_metadata(data)

    async def test_legacy_or_mismatched_recommendation_rating_does_not_borrow_model_source(self):
        async with self.app.test_app():
            client = self.app.test_client()
            await self.account_login(client, role="admin")
            await self.catalog([
                problem("A", 1450, difficulty_source="atcoder_problems", difficulty_raw=1450),
                problem("B", 800),
            ])
            await self.execute("UPDATE recommendations SET problem_rating='400' WHERE problem_id=?",
                               [("abc200_a",)])
            for path in ("/api/me/problems?platform=atcoder", "/api/problems?platform=atcoder"):
                data = await self.get(client, path)
                items = {item["problem_id"]: item for item in data["items"]}
                self.assertEqual(int(items["abc200_a"]["problem_rating"]), 400)
                for item in items.values():
                    self.assertIsNone(item.get("difficulty_source"), (path, item))
            # The crawler detail still displays its own confirmed model rating.
            detail = await self.get(client, "/api/me/problems/atcoder/abc200_a")
            self.assertEqual(detail["difficulty_source"], "atcoder_problems")
            self.assertEqual(int(detail["problem_rating"]), 1450)

    async def test_bad_metadata_keeps_all_local_problem_views_usable_without_source(self):
        async with self.app.test_app():
            client = self.app.test_client()
            await self.account_login(client, role="admin")
            await self.catalog([problem()])
            for raw in ("{broken", "[]", "null"):
                await self.execute("UPDATE crawler_problems SET metadata_json=? WHERE problem_id='abc200_a'",
                                   [(raw,)])
                for path in (
                    "/api/me/problems?platform=atcoder", "/api/problems?platform=atcoder",
                    "/api/admin/database/problems?platform=atcoder",
                    "/api/me/problems/tracker?platform=atcoder", "/api/me/problems/atcoder/abc200_a",
                ):
                    with self.subTest(raw=raw, path=path):
                        data = await self.get(client, path)
                        item = (data["items"][0]["problems"][0] if "/tracker?" in path else
                                data["items"][0] if "items" in data else data)
                        self.assertEqual(int(item["problem_rating"]), 1450)
                        self.assertIsNone(item.get("difficulty_source"))
                        self.no_private_metadata(data)

    async def test_tracker_fallback_rating_cannot_inherit_null_catalog_model_source(self):
        async with self.app.test_app():
            client = self.app.test_client()
            await self.account_login(client, role="member")
            await self.catalog([problem(
                rating=None, difficulty_source="atcoder_problems", difficulty_raw=None,
                difficulty_is_experimental=False, difficulty_missing=True,
            )])
            await self.execute("UPDATE recommendations SET problem_rating='800' WHERE problem_id=?",
                               [("abc200_a",)])
            data = await self.get(client, "/api/me/problems/tracker?platform=atcoder")
            item = data["items"][0]["problems"][0]
            self.assertEqual(item["problem_rating"], 800)
            for field in FIELDS:
                self.assertIsNone(item.get(field), (field, item))

    async def test_profile_and_member_detail_recent_ac_keep_confirmed_model_source(self):
        async with self.app.test_app():
            client = self.app.test_client()
            await self.account_login(client, role="admin")
            await self.catalog([
                problem("A", 1450, difficulty_source="atcoder_problems", difficulty_raw=1450,
                        difficulty_is_experimental=True, private_payload="do-not-publish"),
                problem("B", 0, difficulty_source="atcoder_problems", difficulty_raw=-10000,
                        difficulty_is_experimental=False),
            ])
            await self.execute(
                "INSERT INTO submissions(user_qq_id,platform,problem_id,problem_name,problem_rating,submit_time) "
                "VALUES('12345678','atcoder',?,?,?,?)",
                [("abc200_a", "Model problem", 1450, 20), ("abc200_b", "Zero model", 0, 10)],
            )
            for path in ("/api/me/profile", "/api/member/12345678"):
                with self.subTest(path=path):
                    data = await self.get(client, path)
                    recent = {item["problem_id"]: item for item in data["recent_ac"]}
                    for pid, expected in (
                        ("abc200_a", {"difficulty_source": "atcoder_problems", "difficulty_raw": 1450,
                                      "difficulty_is_experimental": True}),
                        ("abc200_b", {"difficulty_source": "atcoder_problems", "difficulty_raw": -10000,
                                      "difficulty_is_experimental": False}),
                    ):
                        self.assertEqual({key: recent[pid].get(key) for key in FIELDS}, expected)
                    self.assertEqual(int(recent["abc200_a"]["problem_rating"]), 1450)
                    self.assertEqual(int(recent["abc200_b"]["problem_rating"]), 0)
                    if "atcoder" in data:
                        self.assertEqual(data["atcoder"], {"rating": None, "contests": []})
                    self.no_private_metadata(data)

    async def test_profile_recent_ac_does_not_borrow_unknown_or_mismatched_model_source(self):
        async with self.app.test_app():
            client = self.app.test_client()
            await self.account_login(client, role="admin")
            await self.catalog([
                problem("A", 1450, difficulty_source="atcoder_problems", difficulty_raw=1450),
                problem("B", 800),
                problem("C", 900),
            ])
            await self.execute("UPDATE crawler_problems SET metadata_json='{broken' WHERE problem_id=?",
                               [("abc200_c",)])
            await self.execute(
                "INSERT INTO submissions(user_qq_id,platform,problem_id,problem_rating,submit_time) "
                "VALUES('12345678',?,?,?,?)",
                [("atcoder", "abc200_a", 400, 50),
                 ("atcoder", "abc200_b", 800, 40),
                 ("atcoder", "abc200_c", 900, 30),
                 ("atcoder", "abc200_d", 1450, 20),
                 ("codeforces", "abc200_a", 1450, 10)],
            )
            for path in ("/api/me/profile", "/api/member/12345678"):
                with self.subTest(path=path):
                    data = await self.get(client, path)
                    for item in data["recent_ac"]:
                        self.assertTrue(all(item.get(key) is None for key in FIELDS), item)
                    item = next(row for row in data["recent_ac"] if row["platform"] == "atcoder"
                                and row["problem_id"] == "abc200_a")
                    self.assertEqual(int(item["problem_rating"]), 400)
                    self.no_private_metadata(data)

    async def test_profile_difficulty_metadata_does_not_expand_member_access(self):
        async with self.app.test_app():
            client = self.app.test_client()
            await self.account_login(client, role="member")
            await self.catalog([problem(difficulty_source="atcoder_problems", difficulty_raw=1450)])
            await self.execute("INSERT INTO users(qq_id,name,status) VALUES(?,'Other member','现役')",
                               [("87654321",)])
            await self.execute(
                "INSERT INTO submissions(user_qq_id,platform,problem_id,problem_rating,submit_time) "
                "VALUES(?,'atcoder',?,1450,10)",
                [("12345678", "abc200_a"), ("87654321", "abc200_b")],
            )
            data = await self.get(client, "/api/me/profile?qq_id=87654321&owner_qq_id=87654321")
            self.assertEqual([row["problem_id"] for row in data["recent_ac"]], ["abc200_a"])
            self.assertEqual(data["recent_ac"][0].get("difficulty_source"), "atcoder_problems")
            self.assertEqual((await client.get("/api/member/87654321")).status_code, 403)

    async def challenge_history(self, rows):
        await self.execute(
            "INSERT INTO random_challenges(qq_id,platform,problem_id,problem_name,problem_rating,"
            "problem_url,tags,challenge_rating,time_limit_minutes,status,created_at,expires_at) "
            "VALUES(?,?,?,'Synthetic challenge',?,?,'dp',1700,45,'active',100,200)",
            [(owner, platform, pid, rating,
              f"https://atcoder.jp/contests/abc200/tasks/{pid}")
             for owner, platform, pid, rating in rows],
        )

    async def test_generated_challenges_and_both_history_views_keep_confirmed_model_source(self):
        from feat.api.service_runtime import create_web_challenge

        async with self.app.test_app():
            client = self.app.test_client()
            headers = await self.account_login(client, role="admin")
            await self.catalog([problem(
                difficulty_source="atcoder_problems", difficulty_raw=1450,
                difficulty_is_experimental=True, private_payload="do-not-publish",
            )])
            generated = []

            async def provider(*args, **kwargs):
                row = await create_web_challenge(self.db_path, *args, **kwargs)
                self.assertTrue(row["success"])
                row["source"], row["weak_tag"] = "provider selection", "preserved tag"
                generated.append(dict(row))
                return row

            self.app.config["PLUGIN_CONFIG"]["_challenge_provider"] = provider
            with patch("feat.api.acm_api.backend_api.aiohttp.ClientSession",
                       side_effect=AssertionError("difficulty enrichment must stay local")):
                for path in ("/api/challenge/start", "/api/me/challenge/start"):
                    with self.subTest(path=path):
                        response = await client.post(path, headers=headers, json={
                            "platform": "atcoder", "difficulty": 1450, "owner_qq_id": "12345678",
                        })
                        self.assertEqual(response.status_code, 200, await response.get_json())
                        row = await response.get_json()
                        self.assertEqual({key: row.get(key) for key in FIELDS}, {
                            "difficulty_source": "atcoder_problems", "difficulty_raw": 1450,
                            "difficulty_is_experimental": True,
                        })
                        for key, value in generated[-1].items():
                            self.assertEqual(row[key], value, (path, key))
                        self.no_private_metadata(row)

                await self.challenge_history([("12345678", "atcoder", "abc200_a", 1450)])
                for path in ("/api/challenge/list?qq_id=12345678", "/api/me/training/challenges"):
                    with self.subTest(path=path):
                        rows = await self.get(client, path)
                        self.assertEqual(len(rows), 1)
                        self.assertEqual({key: rows[0].get(key) for key in FIELDS}, {
                            "difficulty_source": "atcoder_problems", "difficulty_raw": 1450,
                            "difficulty_is_experimental": True,
                        })
                        self.assertEqual(rows[0]["problem_rating"], 1450)
                        self.assertEqual(rows[0]["challenge_rating"], 1700)
                        self.assertEqual(rows[0]["status"], "active")
                        self.no_private_metadata(rows)

            db = await connect_db(self.db_path)
            try:
                async with db.execute("PRAGMA table_info(random_challenges)") as cursor:
                    self.assertFalse(set(FIELDS) & {row["name"] for row in await cursor.fetchall()})
                async with db.execute("SELECT challenge_rating FROM users WHERE qq_id='12345678'") as cursor:
                    self.assertEqual((await cursor.fetchone())["challenge_rating"], 1000)
                async with db.execute("SELECT problem_rating,challenge_rating,status FROM random_challenges") as cursor:
                    self.assertEqual([tuple(row) for row in await cursor.fetchall()], [(1450, 1700, "active")])
            finally:
                await db.close()

    async def test_challenge_history_unknown_or_mismatched_scores_never_borrow_model_source(self):
        async with self.app.test_app():
            client = self.app.test_client()
            await self.account_login(client, role="admin")
            await self.catalog([
                problem("A", 1450, difficulty_source="atcoder_problems", difficulty_raw=1450),
                problem("B", 800), problem("C", 900),
            ])
            await self.execute("UPDATE crawler_problems SET metadata_json='{broken' WHERE problem_id=?",
                               [("abc200_c",)])
            records = [("12345678", "atcoder", "abc200_a", 400),
                       ("12345678", "atcoder", "abc200_b", 800),
                       ("12345678", "atcoder", "abc200_c", 900),
                       ("12345678", "atcoder", "abc200_d", 1450),
                       ("12345678", "codeforces", "abc200_a", 1450)]
            await self.challenge_history(records)
            with patch("feat.api.acm_api.backend_api.aiohttp.ClientSession",
                       side_effect=AssertionError("history must not fetch remote model data")):
                for path in ("/api/challenge/list?qq_id=12345678", "/api/me/training/challenges"):
                    rows = await self.get(client, path)
                    self.assertEqual(len(rows), len(records))
                    self.assertEqual({(row["platform"], row["problem_id"], row["problem_rating"])
                                      for row in rows}, {(platform, pid, rating)
                                                       for _, platform, pid, rating in records})
                    for row in rows:
                        self.assertTrue(all(row.get(key) is None for key in FIELDS), row)
                        self.assertEqual(row["challenge_rating"], 1700)
                        self.assertEqual(row["status"], "active")
                    self.no_private_metadata(rows)

    async def test_generated_legacy_scores_and_incomplete_provider_results_keep_their_contract(self):
        async with self.app.test_app():
            client = self.app.test_client()
            headers = await self.account_login(client, role="admin")
            await self.catalog([problem(
                difficulty_source="atcoder_problems", difficulty_raw=1450,
                difficulty_is_experimental=False,
            )])
            legacy = {"success": True, "platform": "atcoder", "problem_id": "abc200_a",
                      "problem_rating": 400, "recommendation_reason": "preserved reason",
                      "source": "provider source", "weak_tag": "provider weak tag",
                      "difficulty_source": "atcoder_problems", "difficulty_raw": 1450,
                      "difficulty_is_experimental": False}
            failed = {"success": False, "message": "No matching local candidate"}
            incomplete = {"success": True, "platform": "atcoder", "problem_rating": 1450}
            with patch("feat.api.acm_api.backend_api.aiohttp.ClientSession",
                       side_effect=AssertionError("generation enrichment must stay local")):
                for path in ("/api/challenge/start", "/api/me/challenge/start"):
                    for payload, status in ((legacy, 200), (failed, 400), (incomplete, 200)):
                        with self.subTest(path=path, payload=payload):
                            provider = AsyncMock(return_value=dict(payload))
                            self.app.config["PLUGIN_CONFIG"]["_challenge_provider"] = provider
                            response = await client.post(path, headers=headers,
                                                         json={"platform": "atcoder", "difficulty": 400})
                            self.assertEqual(response.status_code, status)
                            row = await response.get_json()
                            self.assertTrue(all(row.get(key) is None for key in FIELDS), row)
                            for key, value in payload.items():
                                if key not in FIELDS:
                                    self.assertEqual(row[key], value, key)
                            self.assertEqual(row["source"], payload.get("source", "random"))
                            self.assertEqual(row["weak_tag"], payload.get("weak_tag", ""))
                            self.no_private_metadata(row)

    async def test_challenge_model_metadata_does_not_expand_member_scope_or_change_owner(self):
        async with self.app.test_app():
            client = self.app.test_client()
            headers = await self.account_login(client, role="member")
            await self.catalog([problem(difficulty_source="atcoder_problems", difficulty_raw=1450)])
            await self.execute("INSERT INTO users(qq_id,name,status) VALUES(?,'Other member','现役')",
                               [("87654321",)])
            await self.challenge_history([("12345678", "atcoder", "abc200_a", 1450),
                                          ("87654321", "atcoder", "abc200_b", 1450)])
            provider = AsyncMock(return_value={"success": True, "platform": "atcoder",
                                             "problem_id": "abc200_a", "problem_rating": 1450})
            self.app.config["PLUGIN_CONFIG"]["_challenge_provider"] = provider
            body = {"platform": "atcoder", "difficulty": 1450, "owner_qq_id": "87654321"}
            self.assertEqual((await client.post("/api/me/challenge/start", json=body)).status_code, 403)
            generated = await client.post("/api/me/challenge/start", headers=headers, json=body)
            self.assertEqual(generated.status_code, 200)
            self.assertEqual(provider.await_args.kwargs["owner_qq_id"], "12345678")
            self.assertEqual((await generated.get_json()).get("difficulty_source"), "atcoder_problems")
            rows = await self.get(client, "/api/me/training/challenges?qq_id=87654321&owner_qq_id=87654321")
            self.assertEqual([row["problem_id"] for row in rows], ["abc200_a"])
            self.assertEqual(rows[0].get("difficulty_source"), "atcoder_problems")
            self.assertEqual((await client.get("/api/challenge/list?qq_id=87654321")).status_code, 403)
            self.assertEqual((await client.post("/api/challenge/start", headers=headers, json=body)).status_code, 403)


if __name__ == "__main__":
    unittest.main()
