"""Offline HTTP error classification for the administrator's AtCoder collector."""

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import aiohttp

from feat.api.acm_api.problem_sync import ATCODER_CATALOG_URL, ProblemSync


SOURCE = "https://atcoder.jp/contests/asprocon6/tasks/asprocon6_a?lang=en"


class AtCoderDownloadTests(unittest.IsolatedAsyncioTestCase):
    async def request(self, status, url=SOURCE):
        response = Mock(status=status)
        response.read = AsyncMock(return_value=b"statement")
        if status >= 400:
            response.raise_for_status.side_effect = aiohttp.ClientResponseError(
                SimpleNamespace(real_url=url), (), status=status, message="HTTP error",
            )
        context = AsyncMock()
        context.__aenter__.return_value = response
        session = Mock()
        session.get.return_value = context
        sync = ProblemSync("unused.db")
        with patch("feat.api.acm_api.problem_sync.asyncio.sleep", new_callable=AsyncMock):
            try:
                result = await sync.download(session, url)
                return result, response
            except Exception:
                response.read.assert_not_awaited()
                raise

    async def test_public_statement_response_is_unchanged(self):
        result, response = await self.request(200)
        self.assertEqual(result, b"statement")
        response.raise_for_status.assert_called_once()
        response.read.assert_awaited_once()

    async def test_atcoder_404_explains_unavailable_original_and_keeps_url(self):
        with self.assertRaises(ValueError) as raised:
            await self.request(404)
        self.assertIn("HTTP 404", str(raised.exception))
        self.assertIn("题目可能未公开或已移除", str(raised.exception))
        self.assertIn(SOURCE, str(raised.exception))

    async def test_access_denied_is_not_mislabeled_as_a_missing_problem(self):
        with self.assertRaises(aiohttp.ClientResponseError) as raised:
            await self.request(403)
        self.assertEqual(raised.exception.status, 403)

    async def test_catalog_404_keeps_its_original_http_error(self):
        with self.assertRaises(aiohttp.ClientResponseError) as raised:
            await self.request(404, ATCODER_CATALOG_URL)
        self.assertEqual(raised.exception.status, 404)


if __name__ == "__main__":
    unittest.main()
