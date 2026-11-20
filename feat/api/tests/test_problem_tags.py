"""Member catalog tag facets and exact filters share pagination and ownership rules."""

import unittest
from urllib.parse import urlencode
from unittest.mock import patch

import test_api_contract as contract
from feat.api.acm_api import backend_api
from feat.api.acm_api.database import connect_db, isolated_connection
from feat.api.acm_api.problem_bank import save_metadata_batch
from feat.api.acm_api.problem_tags import has_problem_tag, problem_tags


class ProblemTagParsingTests(unittest.TestCase):
    def test_full_tag_matching_decodes_both_storage_formats(self):
        self.assertEqual(problem_tags(' math, greedy;dp|graphs， Math '),
                         ["math", "greedy", "dp", "graphs"])
        self.assertEqual(problem_tags('["Math", "dp", "math", null, {}]'), ["Math", "dp"])
        self.assertEqual(has_problem_tag('["Math", "dp"]', " math "), 1)
        self.assertEqual(has_problem_tag("mathematics,notmath", "math"), 0)
        self.assertEqual(has_problem_tag("100% math,under_score", "%"), 0)
        self.assertEqual(has_problem_tag("100% math,under_score", "100% math"), 1)
        self.assertEqual(has_problem_tag("under_score", "under_score"), 1)


class MemberProblemTagTests(unittest.IsolatedAsyncioTestCase):
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

    async def recommendations(self):
        await self.execute(
            "INSERT INTO recommendations(platform,problem_id,problem_name,problem_rating,problem_url,tags) "
            "VALUES(?,?,?,?,?,?)",
            [("codeforces", "cf_100A", "Math named title", "700", "https://example.org/A", "mathematics"),
             ("codeforces", "cf_100B", "First", "800", "https://example.org/B", "math,greedy"),
             ("codeforces", "cf_100C", "Second", "900", "https://example.org/C", '["Math","dp"]'),
             ("codeforces", "cf_100D", "Literal wildcard", "1000", "https://example.org/D", "100% math,under_score"),
             ("codeforces", "cf_100E", "Not a full tag", "1100", "https://example.org/E", "notmath"),
             ("atcoder", "abc100_a", "Other platform", None, "https://example.org/at", "atcoder-only,math")],
        )

    async def test_tag_options_are_platform_wide_deduplicated_and_account_safe(self):
        async with self.app.test_app():
            client = self.app.test_client()
            self.assertEqual((await client.get("/api/me/problems/tags")).status_code, 401)
            await self.account_login(client, role="member")
            await self.recommendations()
            await self.execute(
                "INSERT INTO submissions(user_qq_id,platform,problem_id,tags,submit_time) VALUES(?,'codeforces',?,?,1)",
                [("12345678", "cf_200A", "own-only"), ("87654321", "cf_300A", "other-only")],
            )
            response = await client.get("/api/me/problems/tags?platform=codeforces&page=99&page_size=1&owner_qq_id=87654321")
            self.assertEqual(response.status_code, 200)
            tags = (await response.get_json())["tags"]
            self.assertEqual([tag.casefold() for tag in tags],
                             ["100% math", "dp", "greedy", "math", "mathematics", "notmath", "own-only", "under_score"])
            self.assertNotIn("atcoder-only", tags)
            self.assertNotIn("other-only", tags)
            self.assertEqual((await (await client.get("/api/me/problems/tags?platform=atcoder")).get_json())["tags"],
                             ["atcoder-only", "math"])
            self.assertEqual((await client.get("/api/me/problems/tags?platform=invalid")).status_code, 400)
            await self.execute("UPDATE web_accounts SET must_change_password=1 WHERE qq_id='12345678'", [()])
            self.assertEqual((await client.get("/api/me/problems/tags")).status_code, 428)

    async def test_tag_options_and_version_share_a_snapshot_during_sync(self):
        async with self.app.test_app():
            client = self.app.test_client()
            await self.account_login(client, role="member")
            await self.execute(
                "INSERT INTO recommendations(platform,problem_id,problem_name,problem_url,tags) "
                "VALUES('codeforces','cf_100A','Synthetic','https://example.test','old-tag')", [()],
            )
            await self.execute(
                "INSERT INTO submissions(user_qq_id,platform,problem_id,tags,submit_time) "
                "VALUES('12345678','codeforces','100-A','old-tag',1)", [()],
            )
            original_version = backend_api.listing_version
            for source in ("public", "private"):
                with self.subTest(source=source):
                    if source == "private":
                        await self.execute("UPDATE recommendations SET tags=''", [()])
                    before = await (await client.get("/api/me/problems/tags?platform=codeforces")).get_json()
                    self.assertEqual(before["tags"], ["old-tag"])

                    async def sync_between_tags_and_version(read_db, owner):
                        async with isolated_connection(read_db) as writer:
                            if source == "public":
                                await writer.execute("UPDATE recommendations SET tags='new-tag'")
                            else:
                                await writer.execute("UPDATE submissions SET tags='new-tag'")
                            await writer.commit()
                        return await original_version(read_db, owner)

                    with patch.object(backend_api, "listing_version", sync_between_tags_and_version):
                        response = await client.get("/api/me/problems/tags?platform=codeforces")
                    self.assertEqual(response.status_code, 200)
                    during = await response.get_json()
                    self.assertEqual(during, before)
                    after = await (await client.get("/api/me/problems/tags?platform=codeforces")).get_json()
                    listing = await (await client.get("/api/me/problems?platform=codeforces")).get_json()
                    self.assertEqual(after["tags"], ["new-tag"])
                    self.assertNotEqual(after["tags_version"], before["tags_version"])
                    self.assertEqual(after["tags_version"], listing["tags_version"])

    async def test_list_exact_tags_filter_before_count_and_paging_and_combine_with_own_state(self):
        async with self.app.test_app():
            client = self.app.test_client()
            await self.account_login(client, role="member")
            await self.recommendations()
            await self.execute(
                "INSERT INTO submissions(user_qq_id,platform,problem_id,submit_time) VALUES(?,'codeforces',?,1)",
                [("12345678", "cf_100B"), ("12345678", "cf_100C"), ("87654321", "cf_100A")],
            )
            await self.execute(
                "INSERT INTO user_problem_state(owner_qq_id,platform,problem_id,is_favorite,updated_at) "
                "VALUES(?,'codeforces',?,1,1)", [("12345678", "cf_100C"), ("87654321", "cf_100B")],
            )
            base = "/api/me/problems?platform=codeforces&problem_tag=mAtH"
            data = await (await client.get(base + "&page_size=1&page=2")).get_json()
            self.assertEqual((data["total"], len(data["items"]), data["items"][0]["problem_id"]),
                             (2, 1, "cf_100C"))
            self.assertEqual((await (await client.get(base + "&page_size=1&page=3")).get_json())["items"], [])
            data = await (await client.get(base + "&scope=solved&state=favorite&owner_qq_id=87654321")).get_json()
            self.assertEqual((data["total"], data["items"][0]["problem_id"]), (1, "cf_100C"))
            self.assertEqual((await (await client.get(base + "&tag=First")).get_json())["items"][0]["problem_id"],
                             "cf_100B")
            for selected, expected in (("%", []), ("100% math", ["cf_100D"]), ("under_score", ["cf_100D"])):
                data = await (await client.get("/api/me/problems?" + urlencode({"platform": "codeforces", "problem_tag": selected}))).get_json()
                self.assertEqual([row["problem_id"] for row in data["items"]], expected)
            self.assertEqual((await client.get(base + "x" * 101)).status_code, 400)

    async def test_tracker_matches_full_tag_on_same_problem_and_preserves_complete_contests(self):
        async with self.app.test_app():
            client = self.app.test_client()
            await self.account_login(client, role="member")
            db = await connect_db(self.db_path)
            try:
                await save_metadata_batch(db, [
                    {"platform": "codeforces", "problem_id": f"cf_{contest}{index}", "contest_id": contest,
                     "problem_index": index, "problem_name": f"Problem {index}",
                     "problem_url": f"https://codeforces.com/contest/{contest}/problem/{index}", "tags": tags}
                    for contest, index, tags in (("100", "A", ["math"]), ("100", "B", ["greedy"]),
                                                 ("200", "A", ["mathematics"]))])
            finally:
                await db.close()
            await self.execute(
                "INSERT INTO user_problem_state(owner_qq_id,platform,problem_id,is_favorite,updated_at) "
                "VALUES('12345678','codeforces','cf_100B',1,1)", [()],
            )
            base = "/api/me/problems/tracker?platform=codeforces&problem_tag=MATH"
            data = await (await client.get(base)).get_json()
            self.assertEqual(data["total"], 1)
            self.assertEqual([p["problem_index"] for p in data["items"][0]["problems"]], ["A", "B"])
            self.assertEqual((await (await client.get(base + "&tag=Problem%20B")).get_json())["total"], 0)
            self.assertEqual((await (await client.get(base + "&state=favorite")).get_json())["total"], 0)
            await self.execute(
                "INSERT INTO user_problem_state(owner_qq_id,platform,problem_id,is_favorite,updated_at) "
                "VALUES('12345678','codeforces','cf_100A',1,1)", [()],
            )
            self.assertEqual((await (await client.get(base + "&state=favorite")).get_json())["total"], 1)
            self.assertEqual((await client.get(base + "x" * 101)).status_code, 400)

    async def test_codeforces_tag_intersection_filters_each_problem_and_preserves_complete_contests(self):
        async with self.app.test_app():
            client = self.app.test_client()
            await self.account_login(client, role="member")
            db = await connect_db(self.db_path)
            try:
                await save_metadata_batch(db, [
                    {"platform": "codeforces", "problem_id": f"cf_{contest}{index}", "contest_id": contest,
                     "problem_index": index, "problem_name": f"Problem {index}",
                     "problem_url": f"https://codeforces.com/contest/{contest}/problem/{index}", "tags": tags}
                    for contest, index, tags in (
                        ("100", "A", ["math"]), ("100", "B", ["dp"]),
                        ("200", "A", ["math", "dp"]), ("200", "B", []),
                        ("300", "A", []), ("400", "A", ["math"]), ("500", "A", []),
                    )
                ])
            finally:
                await db.close()
            await self.execute(
                "INSERT INTO submissions(user_qq_id,platform,problem_id,tags,submit_time) VALUES(?,'codeforces',?,?,1)",
                [("12345678", "300-A", '["math","DP"]'), ("12345678", "cf_400A", "dp"),
                 ("87654321", "cf_500A", "math,dp")],
            )
            await self.execute(
                "INSERT INTO user_problem_state(owner_qq_id,platform,problem_id,is_favorite,updated_at) "
                "VALUES(?,'codeforces',?,1,1)", [("12345678", "300-A"), ("87654321", "cf_200A")],
            )
            params = {"platform": "codeforces", "problem_tags": " mAtH ,dp,MATH ", "problem_tag": "unused"}
            listing = "/api/me/problems?" + urlencode(params)
            tracker = "/api/me/problems/tracker?" + urlencode(params)
            page = await (await client.get(listing + "&page_size=1")).get_json()
            self.assertEqual(page["total"], 2)
            next_page = await (await client.get(listing + "&" + urlencode({
                "page_size": 1, "page": 2, "cursor": page["next_cursor"],
            }))).get_json()
            self.assertEqual({row["problem_id"] for row in page["items"] + next_page["items"]},
                             {"cf_200A", "cf_300A"})
            data = await (await client.get(tracker)).get_json()
            self.assertEqual({row["contest_id"]: [p["problem_index"] for p in row["problems"]]
                              for row in data["items"]}, {"200": ["A", "B"], "300": ["A"]})
            both = "&scope=solved&state=favorite&owner_qq_id=87654321"
            self.assertEqual([row["problem_id"] for row in (await (await client.get(listing + both)).get_json())["items"]],
                             ["cf_300A"])
            self.assertEqual([row["contest_id"] for row in (await (await client.get(tracker + both)).get_json())["items"]],
                             ["300"])
            for url in (listing, tracker):
                self.assertEqual((await (await client.get(url + "&tag=Problem+B")).get_json())["total"], 0)

    async def test_codeforces_multi_tag_query_validates_limits_format_and_platform(self):
        async with self.app.test_app():
            client = self.app.test_client()
            await self.account_login(client, role="member")
            invalid_queries = (
                {"platform": "atcoder", "problem_tags": "dp"},
                {"problem_tags": "dp"},
                {"platform": "codeforces", "problem_tags": "dp,,math"},
                {"platform": "codeforces", "problem_tags": "dp," + "x" * 101},
                {"platform": "codeforces", "problem_tags": ",".join(f"tag-{i}" for i in range(21))},
            )
            for route in ("/api/me/problems?", "/api/me/problems/tracker?"):
                for query in invalid_queries:
                    with self.subTest(route=route, query=query):
                        self.assertEqual((await client.get(route + urlencode(query))).status_code, 400)
                self.assertEqual((await client.get(route + "platform=codeforces&problem_tags=" + "dp," * 25 + "DP")).status_code, 200)

    async def test_codeforces_keyword_search_matches_displayed_and_source_tags(self):
        async with self.app.test_app():
            client = self.app.test_client()
            await self.account_login(client, role="member")
            db = await connect_db(self.db_path)
            try:
                await save_metadata_batch(db, [
                    {"platform": "codeforces", "problem_id": f"cf_{contest}{index}", "contest_id": contest,
                     "problem_index": index, "problem_name": f"Problem {index}",
                     "problem_url": f"https://codeforces.com/contest/{contest}/problem/{index}", "tags": tags}
                    for contest, index, tags in (
                        ("100", "A", ["Math"]), ("100", "B", ["greedy"]),
                        ("200", "A", ["combinatorics"]), ("300", "A", []),
                        ("400", "A", ["greedy"]), ("500", "A", []),
                    )
                ] + [{
                    "platform": "atcoder", "problem_id": "abc100_a", "contest_id": "abc100",
                    "problem_index": "A", "problem_name": "AtCoder problem",
                    "problem_url": "https://atcoder.jp/contests/abc100/tasks/abc100_a", "tags": ["math"],
                }])
            finally:
                await db.close()
            await self.execute(
                "INSERT INTO submissions(user_qq_id,platform,problem_id,tags,submit_time) "
                "VALUES(?,'codeforces',?,'math',1)",
                [("12345678", "300-A"), ("12345678", "cf_400A"), ("87654321", "cf_500A")],
            )

            for keyword, platform, problems, contests in (
                ("math", "codeforces", {"cf_100A", "cf_300A"}, {"100", "300"}),
                ("数学", "codeforces", {"cf_100A", "cf_200A", "cf_300A"}, {"100", "200", "300"}),
                ("数学", "", {"cf_100A", "cf_200A", "cf_300A"}, {"100", "200", "300"}),
                ("数学", "atcoder", set(), set()),
                ("math", "atcoder", {"abc100_a"}, {"abc100"}),
            ):
                with self.subTest(keyword=keyword, platform=platform):
                    query = "?" + urlencode({"platform": platform, "tag": keyword})
                    listing_response = await client.get("/api/me/problems" + query)
                    self.assertEqual(listing_response.status_code, 200)
                    listing = await listing_response.get_json()
                    self.assertEqual(listing["total"], len(problems))
                    self.assertEqual({row["problem_id"] for row in listing["items"]}, problems)

                    tracker_response = await client.get("/api/me/problems/tracker" + query)
                    self.assertEqual(tracker_response.status_code, 200)
                    tracker = await tracker_response.get_json()
                    self.assertEqual(tracker["total"], len(contests))
                    self.assertEqual({row["contest_id"] for row in tracker["items"]}, contests)
                    for row in tracker["items"]:
                        if row["contest_id"] == "100":
                            self.assertEqual([problem["problem_index"] for problem in row["problems"]], ["A", "B"])

    async def test_options_list_and_tracker_share_effective_tags_for_empty_and_stale_sources(self):
        async with self.app.test_app():
            client = self.app.test_client()
            await self.account_login(client, role="member")
            db = await connect_db(self.db_path)
            try:
                await save_metadata_batch(db, [
                    {"platform": "codeforces", "problem_id": f"cf_{contest}A", "contest_id": contest,
                     "problem_index": "A", "problem_name": f"Problem {contest}",
                     "problem_url": f"https://codeforces.com/contest/{contest}/problem/A", "tags": tags}
                    for contest, tags in (("500", []), ("501", ["math"]), ("502", []), ("503", []))])
                # Exercise distinct first-seen seconds, which can change the listing order.
                await db.executemany(
                    "UPDATE crawler_problems SET created_at=? WHERE platform='codeforces' AND problem_id=?",
                    [("2020-01-01 00:00:00", "cf_500A"), ("2020-01-01 00:00:01", "cf_501A")],
                )
                await db.executemany("UPDATE recommendations SET tags=? WHERE problem_id=?",
                                     [("", "cf_500A"), ("stale", "cf_501A"),
                                      ("greedy", "cf_502A"), ("", "cf_503A")])
                await db.executemany(
                    "INSERT INTO submissions(user_qq_id,platform,problem_id,tags,submit_time) "
                    "VALUES(?,'codeforces',?,?,1)",
                    [("12345678", "cf_500A", "math"), ("12345678", "cf_501A", "dp"),
                     ("12345678", "cf_502A", "math"), ("87654321", "cf_503A", "other-only")])
                await db.commit()
            finally:
                await db.close()
            tags = (await (await client.get("/api/me/problems/tags?platform=codeforces")).get_json())["tags"]
            self.assertEqual(tags, ["greedy", "math"])
            for selected, expected in (("math", ["cf_500A", "cf_501A"]), ("greedy", ["cf_502A"]),
                                       ("stale", []), ("dp", []), ("other-only", [])):
                query = "?platform=codeforces&" + urlencode({"problem_tag": selected})
                listing = await (await client.get("/api/me/problems" + query)).get_json()
                self.assertCountEqual([item["problem_id"] for item in listing["items"]], expected)
                for item in listing["items"]:
                    self.assertIn(selected, problem_tags(item["tags"]))
                tracker = await (await client.get("/api/me/problems/tracker" + query)).get_json()
                self.assertCountEqual([p["problem_id"] for contest in tracker["items"]
                                       for p in contest["problems"]], expected)

    async def test_codeforces_aliases_share_tags_and_member_state_across_views(self):
        async with self.app.test_app():
            client = self.app.test_client()
            headers = await self.account_login(client, role="member")
            db = await connect_db(self.db_path)
            try:
                await save_metadata_batch(db, [
                    {"platform": "codeforces", "problem_id": problem_id, "contest_id": contest,
                     "problem_index": "A", "problem_name": f"Problem {contest}",
                     "problem_url": f"https://codeforces.com/contest/{contest}/problem/A", "tags": tags}
                    for problem_id, contest, tags in (("100A", "100", ["greedy"]), ("cf_200A", "200", []))])
                await db.execute(
                    "INSERT INTO recommendations(platform,problem_id,problem_name,problem_url,tags) "
                    "VALUES('codeforces','cf_100A','Old problem','https://codeforces.com/contest/100/problem/A','math')"
                )
                await db.executemany(
                    "INSERT INTO submissions(user_qq_id,platform,problem_id,tags,submit_time) "
                    "VALUES('12345678','codeforces',?,?,?)",
                    [("CF_100a", "math", 10), ("200a", "dp", 20)],
                )
                await db.execute(
                    "INSERT INTO user_problem_state(owner_qq_id,platform,problem_id,is_favorite,updated_at) "
                    "VALUES('12345678','codeforces','100a',1,1)"
                )
                await db.commit()
            finally:
                await db.close()

            base = "/api/me/problems"
            platform = "?platform=codeforces"
            tags = await (await client.get(base + "/tags" + platform)).get_json()
            self.assertEqual(tags["tags"], ["dp", "greedy"])
            listing = await (await client.get(base + platform)).get_json()
            self.assertEqual(listing["total"], 2)
            for selected, expected_contests in (("math", []), ("greedy", ["100"]), ("dp", ["200"])):
                with self.subTest(selected=selected):
                    query = platform + "&problem_tag=" + selected
                    listing = await (await client.get(base + query)).get_json()
                    self.assertEqual(listing["total"], len(expected_contests))
                    self.assertEqual([problem_tags(item["tags"]) for item in listing["items"]],
                                     [[selected]] if expected_contests else [])
                    tracker = await (await client.get(base + "/tracker" + query)).get_json()
                    self.assertEqual([contest["contest_id"] for contest in tracker["items"]], expected_contests)

            query = platform + "&problem_tag=greedy&scope=solved&state=favorite"
            listing = await (await client.get(base + query)).get_json()
            self.assertEqual(listing["total"], 1)
            self.assertEqual(listing["items"][0]["ac_at"], 10)
            self.assertTrue(listing["items"][0]["is_favorite"])
            tracker = await (await client.get(base + "/tracker" + query)).get_json()
            self.assertEqual([contest["contest_id"] for contest in tracker["items"]], ["100"])

            response = await client.put(base + "/codeforces/cf_100A/state",
                                        json={"is_favorite": False}, headers=headers)
            self.assertEqual(response.status_code, 200)
            for endpoint in (base, base + "/tracker"):
                data = await (await client.get(endpoint + query)).get_json()
                self.assertEqual(data["total"], 0)

    async def test_legacy_hyphenated_codeforces_ids_share_one_problem(self):
        async with self.app.test_app():
            client = self.app.test_client()
            headers = await self.account_login(client, role="member")
            statement = "<p>Collected 1706A statement</p>"
            db = await connect_db(self.db_path)
            try:
                await save_metadata_batch(db, [{
                    "platform": "codeforces", "problem_id": "cf_1706A",
                    "contest_id": "1706", "problem_index": "A",
                    "problem_name": "Another String Minimization Problem",
                    "problem_url": "https://codeforces.com/contest/1706/problem/A",
                    "tags": ["greedy"],
                }])
                await db.execute(
                    "UPDATE crawler_problems SET statement_html=?,last_fetch_status='ok' "
                    "WHERE platform='codeforces' AND problem_id='cf_1706A'", (statement,),
                )
                await db.executemany(
                    "INSERT INTO recommendations(platform,problem_id,problem_name,problem_url,tags) "
                    "VALUES('codeforces',?,?,?,?)",
                    [("1706-A", "Another String Minimization Problem",
                      "https://codeforces.com/problemset/problem/1706/A", "math"),
                     ("2097-A", "Sports Betting", "", "dp")],
                )
                await db.execute(
                    "INSERT INTO submissions(user_qq_id,platform,problem_id,tags,submit_time) "
                    "VALUES('12345678','codeforces','1706-a','implementation',10)"
                )
                await db.execute(
                    "INSERT INTO user_problem_state(owner_qq_id,platform,problem_id,is_favorite,updated_at) "
                    "VALUES('12345678','codeforces','1706-A',1,1)"
                )
                await db.commit()
            finally:
                await db.close()

            base = "/api/me/problems"
            platform = "?platform=codeforces"
            listing = await (await client.get(base + platform)).get_json()
            self.assertEqual(listing["total"], 2)
            tags = await (await client.get(base + "/tags" + platform)).get_json()
            self.assertEqual(tags["tags"], ["dp", "greedy"])

            filters = platform + "&problem_tag=greedy&scope=solved&state=favorite"
            listing = await (await client.get(base + filters + "&tag=cf_1706-A")).get_json()
            self.assertEqual(listing["total"], 1)
            self.assertEqual(listing["items"][0]["ac_at"], 10)
            tracker = await (await client.get(base + "/tracker" + filters + "&tag=1706-A")).get_json()
            self.assertEqual([p["problem_id"] for c in tracker["items"] for p in c["problems"]],
                             ["cf_1706A"])
            legacy_only = await (await client.get(base + "/tracker" + platform + "&tag=2097-A")).get_json()
            self.assertEqual([p["problem_id"] for c in legacy_only["items"] for p in c["problems"]],
                             ["cf_2097A"])

            response = await client.get(base + "/codeforces/1706-A")
            self.assertEqual(response.status_code, 200)
            self.assertEqual((await response.get_json())["statement_html"], statement)
            response = await client.put(base + "/codeforces/cf_1706A/state",
                                        json={"is_favorite": False}, headers=headers)
            self.assertEqual(response.status_code, 200)
            for endpoint in (base, base + "/tracker"):
                self.assertEqual((await (await client.get(endpoint + filters)).get_json())["total"], 0)


if __name__ == "__main__":
    unittest.main()
