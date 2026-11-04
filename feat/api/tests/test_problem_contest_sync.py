"""Problem collection refreshes optional contest dates without jeopardizing statements."""

import unittest
from unittest.mock import ANY, patch

import test_problem_sync as contract
from feat.api.acm_api.contest_metadata import refresh_contests


class ProblemContestSyncTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = contract.ProblemSyncTests.asyncSetUp
    asyncTearDown = contract.ProblemSyncTests.asyncTearDown
    login = contract.ProblemSyncTests.login
    query = contract.ProblemSyncTests.query
    write = contract.ProblemSyncTests.write
    submit = contract.ProblemSyncTests.submit
    submit_platform = contract.ProblemSyncTests.submit_platform

    async def test_single_cf_collection_saves_contest_from_existing_standings_response(self):
        metadata = {"contest": {"id": 1843, "name": "CF Named Round", "startTimeSeconds": 1700000000},
                    "problems": [{"contestId": 1843, "index": "A", "name": "First"}]}
        async with self.app.test_app():
            client = self.app.test_client()
            headers = await self.login(client)
            with patch("feat.api.acm_api.problem_sync.cf_request", return_value=metadata) as fetch, \
                    patch.object(self.app.task_manager.problem_sync, "download", return_value=contract.CF_BODY):
                task = await self.submit(client, headers, platform="codeforces", contest_id=1843)
            self.assertEqual(task["status"], "completed")
            self.assertEqual(fetch.await_count, 1)
            fetch.assert_awaited_once_with(ANY, "contest.standings", {"contestId": 1843})
            rows = await self.query("SELECT platform,contest_id,contest_name,start_time FROM crawler_contests")
            self.assertEqual(rows, [{"platform": "codeforces", "contest_id": "1843", "contest_name": "CF Named Round", "start_time": 1700000000}])

    async def test_atcoder_collection_fetches_bulk_dates_once_and_reuses_persisted_fresh_cache(self):
        feed = [{"id": "abc370", "title": "ABC 370", "start_epoch_second": 1700000000}]
        async with self.app.test_app():
            client = self.app.test_client()
            headers = await self.login(client)
            with patch("feat.api.acm_api.problem_sync.refresh_contests", side_effect=refresh_contests), \
                    patch("feat.api.acm_api.contest_metadata.fetch_contests", return_value=feed) as fetch:
                with patch.object(self.app.task_manager.problem_sync, "download", side_effect=[contract.LISTING, contract.BODY, contract.BODY]):
                    first = await self.submit(client, headers)
                with patch.object(self.app.task_manager.problem_sync, "download", return_value=contract.LISTING):
                    second = await self.submit(client, headers)
                self.assertEqual(fetch.await_count, 1)
            self.assertEqual(first["status"], "completed")
            self.assertEqual(second["result"]["skipped_count"], 2)
            self.assertEqual((await self.query("SELECT start_time FROM crawler_contests WHERE contest_id='abc370'"))[0]["start_time"], 1700000000)

    async def test_auxiliary_metadata_failure_keeps_old_date_and_successful_problem_collection(self):
        await self.write("INSERT INTO crawler_contests(platform,contest_id,contest_name,start_time,updated_at) VALUES('atcoder','abc370','Saved name',100,0)")
        async with self.app.test_app():
            client = self.app.test_client()
            headers = await self.login(client)
            with patch("feat.api.acm_api.problem_sync.refresh_contests", side_effect=refresh_contests), \
                    patch("feat.api.acm_api.contest_metadata.fetch_contests", side_effect=ValueError("Unavailable contest catalog")), \
                    patch.object(self.app.task_manager.problem_sync, "download", side_effect=[contract.LISTING, contract.BODY, contract.BODY]):
                task = await self.submit(client, headers)
            self.assertEqual(task["status"], "completed")
            self.assertEqual((task["result"]["success_count"], task["result"]["failure_count"]), (2, 0))
            self.assertEqual(task["result"]["contest_metadata_error"], "Unavailable contest catalog")
            self.assertEqual((await self.query("SELECT contest_name,start_time FROM crawler_contests WHERE contest_id='abc370'")), [{"contest_name": "Saved name", "start_time": 100}])

    async def test_full_cf_collection_fetches_contest_list_without_changing_problem_catalog(self):
        problems = {"problems": [{"contestId": 100, "index": "A", "name": "Example"}]}
        contests = [{"id": 100, "name": "Full CF catalog", "startTimeSeconds": 200}]
        async with self.app.test_app():
            client = self.app.test_client()
            headers = await self.login(client)
            with patch("feat.api.acm_api.problem_sync.refresh_contests", side_effect=refresh_contests), \
                    patch("feat.api.acm_api.problem_sync.cf_request", return_value=problems), \
                    patch("feat.api.acm_api.contest_metadata.cf_request", return_value=contests) as fetch, \
                    patch.object(self.app.task_manager.problem_sync, "download", return_value=contract.CF_BODY):
                task = await self.submit_platform(client, headers, platform="codeforces")
            self.assertEqual(task["status"], "completed")
            fetch.assert_awaited_once_with(ANY, "contest.list", {"gym": "false"})
            self.assertEqual((await self.query("SELECT start_time FROM crawler_contests"))[0]["start_time"], 200)


if __name__ == "__main__":
    unittest.main()
