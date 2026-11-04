"""Member activity pages and data stay independent from administrator tools."""

import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit
from unittest.mock import AsyncMock

import aiosqlite

import test_api_contract as contract


class MemberActivityAccessTests(unittest.IsolatedAsyncioTestCase):
    asyncTearDown = contract.ApiContractTests.asyncTearDown
    account_login = contract.ApiContractTests.account_login

    async def asyncSetUp(self):
        await contract.ApiContractTests.asyncSetUp(self)
        dist = Path(self.temp_dir.name) / "dist"
        dist.mkdir()
        (dist / "index.html").write_text('<div id="app">Application</div>', encoding="utf-8")
        self.app.config["WEBUI_DIST_DIR"] = dist

    async def sql(self, query, args=()):
        db = await aiosqlite.connect(self.db_path)
        try:
            cursor = await db.execute(query, args)
            rows = await cursor.fetchall()
            await db.commit()
            return rows
        finally:
            await db.close()

    async def role_login(self, client, role):
        await self.sql(
            "UPDATE web_accounts SET role=?,credential_version=credential_version+1 WHERE qq_id='12345678'",
            (role,),
        )
        response = await client.post("/api/auth/login", json={
            "qq_id": "12345678", "password": "Test-Password-123!",
        })
        self.assertEqual(response.status_code, 200)
        return {"X-CSRF-Token": (await response.get_json())["csrf_token"]}

    async def test_member_activity_pages_do_not_redirect_any_role_into_admin(self):
        async with self.app.test_app():
            client = self.app.test_client()
            await self.account_login(client, role="member")
            for role in ("member", "admin", "root"):
                await self.role_login(client, role)
                for target in (
                    "/challenge.html?platform=atcoder&tag=dp&qq_id=99999999",
                    "/contest-review.html?contest_id=1843&owner_qq_id=99999999",
                ):
                    with self.subTest(role=role, target=target):
                        response = await client.get(target)
                        self.assertEqual(response.status_code, 200)
                        self.assertNotIn("Location", response.headers)
                        self.assertIn('id="app"', await response.get_data(as_text=True))

    async def test_activity_login_and_first_password_change_keep_the_requested_page(self):
        targets = (
            "/challenge.html?platform=atcoder&tag=dp",
            "/contest-review.html?contest_id=1843",
        )
        async with self.app.test_app():
            client = self.app.test_client()
            for target in targets:
                response = await client.get(target)
                location = urlsplit(response.headers["Location"])
                self.assertEqual(location.path, "/login.html")
                self.assertEqual(parse_qs(location.query)["next"], [target])
            await self.account_login(client, role="root", change=1)
            for target in targets:
                response = await client.get(target)
                location = urlsplit(response.headers["Location"])
                self.assertEqual(location.path, "/change-password.html")
                self.assertEqual(parse_qs(location.query)["next"], [target])
                # Browser fragments are carried through an encoded login destination.
                with_anchor = target + "#history"
                response = await client.get("/login.html?" + urlencode({"next": with_anchor}))
                location = urlsplit(response.headers["Location"])
                self.assertEqual(location.path, "/change-password.html")
                self.assertEqual(parse_qs(location.query)["next"], [with_anchor])

    async def test_member_cannot_open_admin_pages_or_call_management_endpoints(self):
        async with self.app.test_app():
            client = self.app.test_client()
            headers = await self.account_login(client, role="member")
            for target in ("/admin.html", "/admin.html?section=training", "/admin.html?section=contests"):
                response = await client.get(target)
                self.assertEqual(response.status_code, 403, target)
            for target in (
                "/api/admin/members",
                "/api/challenge/list?qq_id=99999999",
                "/api/contest/reviews?owner_qq_id=99999999&contest_id=1843",
            ):
                self.assertEqual((await client.get(target)).status_code, 403, target)
            self.assertEqual((await client.post("/api/challenge/start", headers=headers, json={
                "owner_qq_id": "99999999", "platform": "atcoder",
            })).status_code, 403)
            self.assertEqual((await client.put("/api/contest/reviews", headers=headers, json={
                "owner_qq_id": "99999999", "contest_id": "1843", "problem_id": "A", "status": "reviewed",
            })).status_code, 403)

    async def test_training_history_and_generation_use_session_owner_for_every_role(self):
        async with self.app.test_app():
            client = self.app.test_client()
            await self.account_login(client, role="member")
            for owner, problem in (("12345678", "Own"), ("99999999", "Other")):
                await self.sql(
                    "INSERT INTO random_challenges(qq_id,platform,problem_id,problem_url,challenge_rating,"
                    "time_limit_minutes,created_at,expires_at) VALUES(?,'atcoder',?,'https://atcoder.jp',800,60,1,2)",
                    (owner, problem),
                )
            provider = AsyncMock(return_value={"success": True, "problem_id": "Recommended"})
            self.app.config["PLUGIN_CONFIG"]["_challenge_provider"] = provider
            for role in ("member", "admin", "root"):
                with self.subTest(role=role):
                    headers = await self.role_login(client, role)
                    response = await client.get("/api/me/training/challenges?qq_id=99999999&owner_qq_id=99999999")
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual([row["problem_id"] for row in await response.get_json()], ["Own"])
                    provider.reset_mock()
                    response = await client.post("/api/me/challenge/start?qq_id=99999999", headers=headers, json={
                        "platform": "atcoder", "difficulty": 800, "tag": "dp",
                        "qq_id": "99999999", "owner_qq_id": "99999999",
                    })
                    self.assertEqual(response.status_code, 200)
                    provider.assert_awaited_once_with("atcoder", "dp", 800, owner_qq_id="12345678")

    async def test_contest_queries_and_partial_updates_cannot_target_another_member(self):
        async with self.app.test_app():
            client = self.app.test_client()
            await self.account_login(client, role="member")
            for owner, verdict, status in (
                ("12345678", "WRONG_ANSWER", "unsolved"), ("99999999", "OK", "solved"),
            ):
                await self.sql(
                    "INSERT INTO contest_problem_reviews(owner_qq_id,contest_id,problem_id,verdict,rating,note_md,status,updated_at) "
                    "VALUES(?,'1843','cf_1843A',?,800,'archived private note',?,1)",
                    (owner, verdict, status),
                )
            for role in ("member", "admin", "root"):
                with self.subTest(role=role):
                    headers = await self.role_login(client, role)
                    response = await client.get("/api/me/contest/reviews?contest_id=1843&owner_qq_id=99999999&qq_id=99999999")
                    self.assertEqual(response.status_code, 200)
                    rows = await response.get_json()
                    self.assertEqual(len(rows), 1)
                    self.assertEqual(rows[0]["owner_qq_id"], "12345678")
                    self.assertEqual(rows[0]["verdict"], "WRONG_ANSWER")
                    self.assertNotIn("note_md", rows[0])
                    response = await client.put("/api/me/contest/reviews", headers=headers, json={
                        "owner_qq_id": "99999999", "qq_id": "99999999",
                        "contest_id": "1843", "problem_id": "cf_1843A", "status": "reviewed",
                    })
                    self.assertEqual(response.status_code, 200)
            rows = await self.sql("SELECT owner_qq_id,verdict,rating,note_md,status FROM contest_problem_reviews ORDER BY owner_qq_id")
            self.assertEqual(rows, [
                ("12345678", "WRONG_ANSWER", 800, "archived private note", "reviewed"),
                ("99999999", "OK", 800, "archived private note", "solved"),
            ])

    async def test_activity_apis_enforce_login_first_password_change_and_csrf(self):
        async with self.app.test_app():
            client = self.app.test_client()
            provider = AsyncMock(return_value={"success": True})
            self.app.config["PLUGIN_CONFIG"]["_challenge_provider"] = provider
            calls = (
                ("GET", "/api/me/training/challenges", None),
                ("GET", "/api/me/contest/reviews?contest_id=1843", None),
                ("POST", "/api/me/challenge/start", {"platform": "atcoder"}),
                ("PUT", "/api/me/contest/reviews", {"contest_id": "1843", "problem_id": "A", "status": "reviewed"}),
            )
            for method, target, body in calls:
                self.assertEqual((await client.open(target, method=method, json=body)).status_code, 401)
            headers = await self.account_login(client, role="member", change=1)
            for method, target, body in calls:
                self.assertEqual((await client.open(target, method=method, json=body, headers=headers)).status_code, 428)
            await self.sql("UPDATE web_accounts SET must_change_password=0 WHERE qq_id='12345678'")
            for method, target, body in calls:
                if method != "GET":
                    self.assertEqual((await client.open(target, method=method, json=body)).status_code, 403)
            provider.assert_not_awaited()
            self.assertEqual(await self.sql("SELECT * FROM contest_problem_reviews"), [])
