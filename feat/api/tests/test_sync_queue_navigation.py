"""Legacy task links retain their destination without weakening admin page guards."""
import unittest
from urllib.parse import parse_qs, urlsplit

import test_api_contract as contract


class SyncQueueNavigationTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = contract.ApiContractTests.asyncSetUp
    asyncTearDown = contract.ApiContractTests.asyncTearDown
    account_login = contract.ApiContractTests.account_login
    links = ("/tasks.html?platform=luogu", "/admin.html?section=tasks&platform=luogu")

    def assert_queue(self, target):
        self.assertEqual(urlsplit(target).path, "/admin.html")
        self.assertEqual(parse_qs(urlsplit(target).query), {
            "section": ["sync-center"], "tab": ["queue"], "platform": ["luogu"],
        })

    async def test_admin_legacy_links_redirect_to_the_queue_with_parameters(self):
        async with self.app.test_app():
            client = self.app.test_client()
            await self.account_login(client, role="admin")
            for link in self.links:
                response = await client.get(link)
                self.assertEqual(response.status_code, 302)
                self.assert_queue(response.headers["Location"])
                destination = await client.get(response.headers["Location"])
                self.assertEqual(destination.status_code, 200)

    async def test_anonymous_legacy_links_keep_the_queue_as_the_login_destination(self):
        async with self.app.test_app():
            client = self.app.test_client()
            for link in self.links:
                response = await client.get(link)
                self.assertEqual(response.status_code, 302)
                target = urlsplit(response.headers["Location"])
                self.assertEqual(target.path, "/login.html")
                self.assert_queue(parse_qs(target.query)["next"][0])

    async def test_password_change_keeps_the_queue_as_the_return_destination(self):
        async with self.app.test_app():
            client = self.app.test_client()
            await self.account_login(client, role="admin", change=1)
            for link in self.links:
                response = await client.get(link)
                self.assertEqual(response.status_code, 302)
                target = urlsplit(response.headers["Location"])
                self.assertEqual(target.path, "/change-password.html")
                self.assert_queue(parse_qs(target.query)["next"][0])

    async def test_members_cannot_open_either_legacy_link_or_the_queue(self):
        async with self.app.test_app():
            client = self.app.test_client()
            await self.account_login(client, role="member")
            for link in (*self.links, "/admin.html?section=sync-center&tab=queue"):
                self.assertEqual((await client.get(link)).status_code, 403)
