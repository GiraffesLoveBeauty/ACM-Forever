"""Transactional projection, indexed read plans and stable pagination contracts."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from feat.api.acm_api.database import connect_db
from feat.api.acm_api.problem_listing import indexed_query, listing_page, listing_tags, listing_version


class ProblemListingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "listing.db"
        self.db = await connect_db(self.path)

    async def asyncTearDown(self):
        await self.db.close()
        self.temp.cleanup()

    async def recommend(self, pid, tags="math", rating=1200):
        await self.db.execute("INSERT INTO recommendations(platform,problem_id,problem_name,problem_rating,problem_url,tags) "
                              "VALUES('codeforces',?,?,?,'https://example.test/problem',?) "
                              "ON CONFLICT(platform,problem_id) DO UPDATE SET tags=excluded.tags",
                              (pid, pid, rating, tags))

    async def page(self, **args):
        return await listing_page(self.db, "member", {"platform": "codeforces", "page_size": "2", **args})

    async def test_commit_updates_aliases_tags_and_favorites_and_rollback_is_atomic(self):
        await self.recommend("cf_100A")
        await self.db.execute("INSERT INTO submissions(user_qq_id,platform,problem_id,tags,submit_time) VALUES('member','codeforces','100a','private',10)")
        await self.db.execute("INSERT INTO user_problem_state VALUES('member','codeforces','CF_100-A',1,'inbox','',1)")
        await self.db.commit()
        result = await self.page(scope="solved", state="favorite", problem_tag="MATH")
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0]["ac_at"], 10)
        self.assertEqual(result["items"][0]["is_favorite"], 1)
        self.assertEqual(await listing_tags(self.db, "member", "codeforces"), ["math"])
        with patch("feat.api.acm_api.problem_listing._refresh_catalog", side_effect=RuntimeError("index failure")):
            await self.recommend("cf_101A", "new-tag")
            with self.assertRaisesRegex(RuntimeError, "index failure"):
                await self.db.commit()
        self.assertEqual((await self.page())["total"], 1)
        async with self.db.execute("SELECT COUNT(*) FROM recommendations WHERE problem_id='cf_101A'") as cursor:
            self.assertEqual((await cursor.fetchone())[0], 0)
        await self.db.execute("DELETE FROM submissions WHERE user_qq_id='member'")
        await self.db.commit()
        self.assertEqual((await self.page(scope="solved"))["total"], 0)
        self.assertEqual((await self.page(state="favorite"))["total"], 1)

    async def test_tag_dictionary_removes_unused_tags_and_private_fallback_is_isolated(self):
        await self.recommend("cf_100A", "Math")
        await self.recommend("cf_101A", "math")
        await self.db.executemany("INSERT INTO submissions(user_qq_id,platform,problem_id,tags,submit_time) VALUES(?,'codeforces',?,?,1)",
                                  [("member", "cf_102A", "mine"), ("other", "cf_103A", "secret")])
        await self.db.commit()
        self.assertEqual(await listing_tags(self.db, "member", "codeforces"), ["Math", "mine"])
        await self.db.execute("DELETE FROM recommendations WHERE problem_id='cf_100A'")
        await self.db.commit()
        self.assertEqual(await listing_tags(self.db, "member", "codeforces"), ["math", "mine"])
        await self.db.execute("DELETE FROM recommendations")
        await self.db.commit()
        self.assertEqual(await listing_tags(self.db, "member", "codeforces"), ["mine"])
        self.assertEqual((await self.page(problem_tag="secret"))["total"], 0)
        self.assertEqual((await self.page(problem_tag="mine"))["total"], 1)

    async def test_known_times_precede_unknown_and_corrections_do_not_change_identity(self):
        for contest, created in (("100", "2026-01-01T00:00:00Z"), ("101", "2026-02-01T00:00:00Z"), ("102", "2026-03-01T00:00:00Z")):
            await self.db.execute("INSERT INTO crawler_problems(platform,problem_id,contest_id,problem_name,problem_url,metadata_json,created_at,updated_at) "
                                  "VALUES('codeforces',?,?,?,'https://example.test','{}',?,?)", ("cf_" + contest + "A", contest, contest, created, created))
        await self.db.execute("INSERT INTO crawler_contests VALUES('codeforces','100','old',100,1)")
        await self.db.commit()
        first = await self.page(page_size="10")
        self.assertEqual([p["problem_id"] for p in first["items"]], ["cf_100A", "cf_102A", "cf_101A"])
        unknown = await self.page(time_basis="unknown", page_size="10")
        self.assertEqual(unknown["total"], 2)
        await self.db.execute("INSERT INTO crawler_contests VALUES('codeforces','101','newly dated',200,1)")
        await self.db.commit()
        second = await self.page(page_size="10")
        self.assertEqual([p["problem_id"] for p in second["items"]], ["cf_101A", "cf_100A", "cf_102A"])
        self.assertEqual(first["items"][2]["first_seen_at"], second["items"][0]["first_seen_at"])

    async def test_cursor_matches_page_numbers_and_survives_new_top_insertion(self):
        for pid in ("100A", "101A", "102A", "103A", "104A"):
            await self.recommend("cf_" + pid)
        await self.db.commit()
        first = await self.page()
        offset = await self.page(page="2")
        second = await self.page(page="2", cursor=first["next_cursor"])
        self.assertEqual(second["items"], offset["items"])
        await self.recommend("cf_99A")
        await self.db.execute("INSERT INTO crawler_problems(platform,problem_id,contest_id,problem_name,problem_url,metadata_json,created_at,updated_at) VALUES('codeforces','cf_99A','99','new top','https://example.test','{}','2026-01-01','2026-01-01')")
        await self.db.execute("INSERT INTO crawler_contests VALUES('codeforces','99','new top',100,1)")
        await self.db.commit()
        stable = await self.page(page="2", cursor=first["next_cursor"])
        self.assertEqual(stable["items"], second["items"])
        with self.assertRaises(ValueError):
            await self.page(page="2", problem_tag="dp", cursor=first["next_cursor"])
        for malformed in ("!", "W10", "bnVsbA"):
            with self.assertRaises(ValueError):
                await self.page(page="2", cursor=malformed)

    async def test_solved_cursor_applies_filters_before_paging_and_uses_member_index(self):
        for i in range(1, 9):
            await self.recommend(f"cf_{i}A", "math" if i % 2 else "dp")
            await self.db.execute("INSERT INTO submissions(user_qq_id,platform,problem_id,submit_time) VALUES('member','codeforces',?,?)", (f"{i}a", i))
        await self.db.commit()
        args = {"platform": "codeforces", "scope": "solved", "problem_tag": "math", "page_size": "2"}
        first = await listing_page(self.db, "member", args)
        second = await listing_page(self.db, "member", {**args, "page": "2", "cursor": first["next_cursor"]})
        self.assertEqual(first["total"], 4)
        self.assertEqual([p["ac_at"] for p in first["items"] + second["items"]], [7, 5, 3, 1])
        query, params = await indexed_query(self.db, "member", {"platform": "codeforces", "scope": "solved"})
        async with self.db.execute("EXPLAIN QUERY PLAN " + query + " ORDER BY m.ac_order,m.platform,m.id_key LIMIT 20", params) as cursor:
            plan = "\n".join(row[3] for row in await cursor.fetchall())
        self.assertIn("idx_member_platform_ac_page", plan)
        self.assertNotIn("USE TEMP B-TREE", plan)
        async with self.db.execute("EXPLAIN QUERY PLAN SELECT COUNT(*) FROM (" + query + ")", params) as cursor:
            count_plan = [row[3] for row in await cursor.fetchall()]
        self.assertIn("SEARCH m", count_plan[0])
        self.assertIn("owner=?", count_plan[0])

    async def test_read_paths_do_not_touch_source_tables_and_default_order_uses_index(self):
        await self.recommend("cf_100A")
        await self.db.commit()
        trace = []
        await self.db.set_trace_callback(trace.append)
        await self.page()
        await listing_tags(self.db, "member", "codeforces")
        statements = "\n".join(trace).lower()
        for table in ("submissions", "recommendations", "crawler_problems", "crawler_contests"):
            self.assertNotIn(table, statements)
        query, params = await indexed_query(self.db, "member", {"platform": "codeforces"})
        async with self.db.execute("EXPLAIN QUERY PLAN " + query + " ORDER BY p.sort_unknown,p.sort_order,p.platform,p.id_key LIMIT 20", params) as cursor:
            plan = "\n".join(row[3] for row in await cursor.fetchall())
        self.assertIn("idx_listing_platform_newest", plan)
        self.assertNotIn("USE TEMP B-TREE", plan)

    async def test_external_writes_queue_without_custom_functions_and_restart_recovers(self):
        with sqlite3.connect(self.path) as external:
            external.execute("INSERT INTO recommendations(platform,problem_id,problem_name,problem_url,tags) VALUES('codeforces','cf_100A','original','https://example.test','math')")
        external.close()
        # Startup, not a read request, recovers a legacy writer's durable queue.
        await self.db.close()
        self.db = await connect_db(self.path)
        self.assertEqual((await self.page())["total"], 1)
        version = await listing_version(self.db, "member")
        await self.db.close()
        self.db = await connect_db(self.path)
        self.assertEqual(await listing_version(self.db, "member"), version)
        async with self.db.execute("SELECT COUNT(*) FROM problem_listing_dirty") as cursor:
            self.assertEqual((await cursor.fetchone())[0], 0)

    async def test_other_members_private_updates_do_not_invalidate_own_tag_version(self):
        await self.recommend("cf_100A", "")
        await self.db.execute("INSERT INTO submissions(user_qq_id,platform,problem_id,tags,submit_time) VALUES('other','codeforces','100A','private',1)")
        await self.db.commit()
        before = await listing_version(self.db, "member")
        await self.db.execute("UPDATE submissions SET tags='updated-private' WHERE user_qq_id='other'")
        await self.db.commit()
        self.assertEqual(await listing_version(self.db, "member"), before)
        self.assertEqual(await listing_tags(self.db, "member", "codeforces"), [])

    async def test_pre_index_database_is_backfilled_once_without_rewriting_sources(self):
        await self.db.close()
        external = sqlite3.connect(self.path)
        try:
            for (name,) in external.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'listing_%'").fetchall():
                external.execute('DROP TRIGGER "' + name + '"')
            for table in ("problem_listing", "problem_listing_tags", "problem_listing_tag_options", "problem_listing_native_tags", "member_problem_index", "member_problem_tags", "problem_listing_dirty", "member_problem_dirty"):
                external.execute("DROP TABLE " + table)
            external.execute("DELETE FROM settings WHERE key LIKE 'problem_listing_%'")
            external.execute("INSERT INTO recommendations(platform,problem_id,problem_name,problem_url,tags) VALUES('codeforces','cf_100A','legacy name','https://example.test','math')")
            external.execute("INSERT INTO submissions(user_qq_id,platform,problem_id,submit_time) VALUES('member','codeforces','100a',123)")
            external.commit()
        finally:
            external.close()
        self.db = await connect_db(self.path)
        result = await self.page(scope="solved")
        self.assertEqual(result["items"][0]["problem_name"], "legacy name")
        self.assertEqual(result["items"][0]["ac_at"], 123)
        async with self.db.execute("SELECT problem_id FROM submissions") as cursor:
            self.assertEqual((await cursor.fetchone())[0], "100a")
        version = await listing_version(self.db, "member")
        await self.db.close()
        self.db = await connect_db(self.path)
        self.assertEqual(await listing_version(self.db, "member"), version)

    async def test_binding_cleanup_keeps_favorites_and_removes_last_personal_revision(self):
        from feat.api.acm_api.binding_service import apply_binding
        await self.db.execute("INSERT INTO users(qq_id,name,cf_handle) VALUES('member','Synthetic member','old_handle')")
        await self.recommend("cf_100A", "")
        await self.db.execute("INSERT INTO submissions(user_qq_id,platform,problem_id,tags,submit_time) VALUES('member','codeforces','100A','old-private',1)")
        await self.db.execute("INSERT INTO user_problem_state VALUES('member','codeforces','cf_100A',1,'inbox','',1)")
        await self.db.commit()
        before = await listing_version(self.db, "member")
        await self.db.execute("UPDATE submissions SET tags=tags,submit_time=submit_time WHERE user_qq_id='member'")
        await self.db.commit()
        self.assertEqual(await listing_version(self.db, "member"), before)
        await apply_binding(self.db, "member", "codeforces", "new_handle")
        await self.db.commit()
        self.assertEqual((await self.page(scope="solved"))["total"], 0)
        self.assertEqual((await self.page(state="favorite"))["total"], 1)
        self.assertEqual(await listing_tags(self.db, "member", "codeforces"), [])
        await self.db.execute("DELETE FROM user_problem_state WHERE owner_qq_id='member'")
        await self.db.commit()
        async with self.db.execute("SELECT value FROM settings WHERE key='problem_listing_member:member'") as cursor:
            self.assertIsNone(await cursor.fetchone())
        for table in ("member_problem_index", "member_problem_tags", "member_problem_dirty"):
            async with self.db.execute("SELECT COUNT(*) FROM " + table + " WHERE owner='member'") as cursor:
                self.assertEqual((await cursor.fetchone())[0], 0, table)
        await self.db.execute("INSERT INTO submissions(user_qq_id,platform,problem_id,tags,submit_time) VALUES('member','codeforces','100A','new-private',2)")
        await self.db.commit()
        self.assertNotEqual(await listing_version(self.db, "member"), before)
        self.assertEqual(await listing_tags(self.db, "member", "codeforces"), ["new-private"])

    async def test_sqlite_commit_failure_rolls_back_sources_and_projection(self):
        await self.db.execute("CREATE TABLE listing_test_parent(id INTEGER PRIMARY KEY)")
        await self.db.execute("CREATE TABLE listing_test_child(parent INTEGER REFERENCES listing_test_parent(id) DEFERRABLE INITIALLY DEFERRED)")
        await self.recommend("cf_100A")
        await self.db.execute("INSERT INTO listing_test_child VALUES(1)")
        with self.assertRaises(sqlite3.IntegrityError):
            await self.db.commit()
        for table in ("recommendations", "problem_listing", "problem_listing_dirty"):
            async with self.db.execute("SELECT COUNT(*) FROM " + table) as cursor:
                self.assertEqual((await cursor.fetchone())[0], 0, table)
