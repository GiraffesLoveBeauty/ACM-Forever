"""AtCoder history paging must preserve same-second submissions and retry progress."""
import unittest
import urllib.parse
from unittest.mock import AsyncMock, patch

import aiosqlite

from feat.api.acm_api.binding_guard import BindingGuard
from feat.api.acm_api.crawler import Crawler


def submission(timestamp, problem_id="abc001_a", result="AC"):
    return {"epoch_second": timestamp, "problem_id": problem_id,
            "contest_id": "abc001", "result": result}


class Response:
    def __init__(self, payload, before_json=None):
        self.payload = payload
        self.before_json = before_json

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def raise_for_status(self):
        if isinstance(self.payload, Exception):
            raise self.payload

    async def json(self):
        if self.before_json:
            await self.before_json()
        return self.payload


class Session:
    def __init__(self, pages, before_page=None):
        self.pages = list(pages)
        self.before_page = before_page or {}
        self.cursors = []

    def get(self, url, **kwargs):
        page_index = len(self.cursors)
        self.cursors.append(int(urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["from_second"][0]))
        if not self.pages:
            raise AssertionError("Unexpected extra AtCoder request")
        return Response(self.pages.pop(0), self.before_page.get(page_index))


class AtCoderPaginationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await self.db.executescript(
            "CREATE TABLE users(qq_id TEXT PRIMARY KEY,atcoder_handle TEXT,"
            "atcoder_binding_version INTEGER,account_state TEXT,account_epoch INTEGER);"
            "INSERT INTO users VALUES('12345678','Example',0,'active',1);"
            "CREATE TABLE submissions(user_qq_id TEXT,platform TEXT,problem_id TEXT,"
            "problem_name TEXT,problem_rating TEXT,problem_url TEXT,submit_time INTEGER,"
            "UNIQUE(user_qq_id,platform,problem_id));"
        )
        async with self.db.execute("SELECT * FROM users") as cursor:
            self.user = await cursor.fetchone()
        self.guarded_db = BindingGuard(self.db, self.user, "atcoder")
        self.titles = patch.object(Crawler, "_get_atcoder_titles", new=AsyncMock(return_value={"abc001_a": "Welcome"}))
        self.ratings = patch.object(Crawler, "_get_atcoder_difficulties", new=AsyncMock(return_value={"abc001_a": "100"}))
        self.sleep = patch("feat.api.acm_api.crawler.asyncio.sleep", new=AsyncMock())
        self.titles.start()
        self.ratings.start()
        self.sleep.start()

    async def asyncTearDown(self):
        self.sleep.stop()
        self.ratings.stop()
        self.titles.stop()
        await self.db.close()

    async def stored_ids(self):
        async with self.db.execute("SELECT problem_id FROM submissions ORDER BY problem_id") as cursor:
            return [row[0] for row in await cursor.fetchall()]

    async def fetch(self, session):
        return await Crawler.fetch_atcoder_submissions(session, self.user, 0, self.guarded_db, {})

    def full_page(self):
        # WA records count toward the API's 500-record limit too.
        return [submission(i, result="WA") for i in range(1, 500)] + [submission(500)]

    async def test_full_page_overlaps_last_second_and_retries_idempotently(self):
        pages = [self.full_page(), [submission(500), submission(500, "abc001_b"), submission(501, "abc001_c")]]
        session = Session(pages)
        self.assertEqual(await self.fetch(session), 3)
        self.assertEqual(session.cursors, [0, 500])
        self.assertEqual(await self.stored_ids(), ["abc001_a", "abc001_b", "abc001_c"])
        async with self.db.execute("SELECT problem_name,problem_rating FROM submissions WHERE problem_id='abc001_a'") as cursor:
            self.assertEqual(tuple(await cursor.fetchone()), ("Welcome", "100"))
        self.assertEqual(await self.fetch(Session(pages)), 0)
        self.assertEqual(len(await self.stored_ids()), 3)

    async def test_later_page_failure_preserves_committed_progress_and_can_retry(self):
        session = Session([self.full_page(), RuntimeError("temporary outage")])
        self.assertEqual(await self.fetch(session), -1)
        self.assertEqual(await self.stored_ids(), ["abc001_a"])
        retry = Session([self.full_page(), [submission(500), submission(501, "abc001_b")]])
        self.assertEqual(await self.fetch(retry), 1)
        self.assertEqual(await self.stored_ids(), ["abc001_a", "abc001_b"])

    async def test_saturated_timestamp_fails_without_skipping_or_looping(self):
        page = [submission(100, result="WA") for _ in range(499)] + [submission(100)]
        session = Session([page, page])
        self.assertEqual(await self.fetch(session), -1)
        self.assertEqual(session.cursors, [0, 100])
        self.assertEqual(await self.stored_ids(), ["abc001_a"])

    async def test_invalid_page_entry_fails_instead_of_advancing_past_it(self):
        for payload in ([submission(1), {"result": "WA"}],
                        [submission(1), submission(2, problem_id="")],
                        {"error": "unavailable"}):
            with self.subTest(payload=payload):
                self.assertEqual(await self.fetch(Session([payload])), -1)
                self.assertEqual(await self.stored_ids(), [])

    async def test_binding_generation_is_checked_after_each_network_page(self):
        async def change_binding():
            # A completed page must not hold a write transaction during network IO.
            self.assertFalse(self.db.in_transaction)
            await self.db.execute("UPDATE users SET atcoder_handle='Other',atcoder_binding_version=1")
            await self.db.commit()

        session = Session([self.full_page(), [submission(500), submission(501, "abc001_b")]], {1: change_binding})
        self.assertEqual(await self.fetch(session), -1)
        self.assertEqual(await self.stored_ids(), ["abc001_a"])


if __name__ == "__main__":
    unittest.main()
