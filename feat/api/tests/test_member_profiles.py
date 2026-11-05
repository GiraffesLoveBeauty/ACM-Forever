"""Real Cookie/SQLite contracts for the member profile editor (synthetic data only)."""
import asyncio
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from feat.api.app import create_app
from feat.api.acm_api.auth_service import hash_password
from feat.api.acm_api.database import connect_db
from feat.api.acm_api import member_profile_service as profiles

PASSWORD = "Profile-fixture-only!2026"
ENCODED = hash_password(PASSWORD)


class MemberProfileTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "profiles.db"
        self.env = patch.dict(os.environ, {"ACM_DATABASE_PATH": str(self.path), "ACM_WEBUI_SECRET_KEY": "synthetic-profile-secret", "ACM_BOOTSTRAP_ROOT_QQ": "", "ACM_BOOTSTRAP_ROOT_PASSWORD": "", "ACM_WEBUI_ADMIN_USERNAME": "legacy-fixture", "ACM_WEBUI_ADMIN_PASSWORD": PASSWORD, "ACM_WEBUI_LEGACY_ADMIN_LOGIN": "true"})
        self.env.start()
        self.app = create_app()
        db = await connect_db(self.path)
        now = int(time.time())
        for qq, role in [("10000001", "admin"), ("10000002", "root"), ("10000003", "member")]:
            await db.execute("INSERT INTO users(qq_id,name) VALUES(?,?)", (qq, "合成" + role))
            await db.execute("INSERT INTO web_accounts(qq_id,password_hash,role,must_change_password,is_active,created_at,updated_at) VALUES(?,?,?,0,1,?,?)", (qq, ENCODED, role, now, now))
        for i in range(25):
            await db.execute("INSERT INTO users(qq_id,name,real_name,school,status,cf_handle,atcoder_handle,luogu_id,nowcoder_id,cjlu_username) VALUES(?,?,?,?,?,?,?,?,?,?)", (str(20000000 + i), f"成员{i:02}", "合成姓名" if i == 0 else None, " 学校甲 " if i % 2 == 0 else "学校乙", "现役" if i % 3 else "集训", f"CF_{i}", f"AC_{i}", str(60000 + i), str(70000 + i), f"campus_{i}"))
        await db.commit()
        await db.close()
        self.client, self.headers = await self.login("10000001")

    async def asyncTearDown(self):
        self.env.stop()
        self.temp.cleanup()

    async def login(self, qq=None):
        client = self.app.test_client()
        response = await client.post("/api/auth/login", json={"qq_id": qq, "password": PASSWORD} if qq else {"username": "legacy-fixture", "password": PASSWORD})
        self.assertEqual(response.status_code, 200, await response.get_json())
        return client, {"X-CSRF-Token": (await response.get_json())["csrf_token"]}

    async def snapshot(self, qq="20000000"):
        response = await self.client.get("/api/admin/members/" + qq)
        self.assertEqual(response.status_code, 200, await response.get_json())
        return await response.get_json()

    async def save(self, changes, before=None, qq="20000000", client=None, headers=None):
        before = before or await self.snapshot(qq)
        return await (client or self.client).patch("/api/admin/members/" + qq, headers=self.headers if headers is None else headers, json={"expected_account_epoch": before["account_epoch"], "profile_revision": before["profile_revision"], **changes})

    async def test_complete_fields_real_name_and_all_platforms(self):
        data = await (await self.client.get("/api/admin/members", query_string={"search":"合成姓名"})).get_json()
        self.assertEqual(data["total"], 1)
        user = data["items"][0]
        self.assertEqual(user, await self.snapshot())
        self.assertEqual([user[key] for key in ("real_name", "cf_handle", "atcoder_handle", "luogu_id", "nowcoder_id")], ["合成姓名", "CF_0", "AC_0", "60000", "70000"])
        self.assertIsNone(user["role"])
        self.assertEqual((await self.snapshot("20000001"))["real_name"], "")

    async def test_combined_filters_options_and_page_clamping(self):
        data = await (await self.client.get("/api/admin/members", query_string={"school":"学校甲","status":"集训","search":"成员","page":999,"page_size":2})).get_json()
        self.assertEqual((data["total"], data["page"], len(data["items"])), (5, 3, 1))
        options = await (await self.client.get("/api/admin/members/options?search=NO_MATCH")).get_json()
        self.assertEqual(options["schools"], ["学校乙", "学校甲"])
        self.assertEqual(set(options["statuses"]), {"现役", "集训"})
        self.assertRegex(options["draft_scope"], r"^[a-f0-9]{64}$")

    async def test_scope_is_unique_stable_and_legacy_has_real_scope(self):
        first = await (await self.client.get("/api/admin/members/options")).get_json()
        same = await (await self.client.get("/api/admin/members/options")).get_json()
        other, _ = await self.login("10000002")
        legacy, _ = await self.login()
        scopes = [first["draft_scope"], (await (await other.get("/api/admin/members/options")).get_json())["draft_scope"], (await (await legacy.get("/api/admin/members/options")).get_json())["draft_scope"]]
        self.assertEqual(first, same)
        self.assertEqual(len(set(scopes)), 3)
        self.assertTrue(all("100000" not in scope and PASSWORD not in scope for scope in scopes))

    async def test_only_explicit_fields_change_hidden_binding_and_evidence_survive(self):
        before = await self.snapshot()
        db = await connect_db(self.path)
        await db.execute("INSERT INTO submissions(user_qq_id,platform,problem_id,submit_time) VALUES('20000000','cjlu','A',123)")
        await db.commit(); await db.close()
        response = await self.save({"real_name": None, "school": "新学校"}, before)
        self.assertEqual(response.status_code, 200, await response.get_json())
        after = (await response.get_json())["member"]
        for field in ("name", "status", "cjlu_username", *profiles.VERSION_FIELDS, "cf_handle", "luogu_id", "atcoder_handle", "nowcoder_id"):
            self.assertEqual(after[field], before[field], field)
        db = await connect_db(self.path)
        self.assertEqual((await profiles.row(db, "SELECT COUNT(*) n FROM submissions"))["n"], 1)
        await db.close()
        self.assertEqual(after["real_name"], "")

    async def test_unknown_immutable_and_hidden_fields_rejected(self):
        before = await self.snapshot()
        for field in ("qq_id", "role", "password", "is_active", "account_state", "account_epoch", "cjlu_username"):
            response = await self.save({field: "forged", "name": "不能写入"}, before)
            self.assertEqual(response.status_code, 400, (field, await response.get_json()))
        self.assertEqual((await self.snapshot())["name"], before["name"])

    async def test_explicit_validation_types_lengths_and_empty_nickname(self):
        for changes, field in [({"name": " "}, "name"), ({"school": True}, "school"), ({"real_name": 32}, "real_name"), ({"status": "x" * 65}, "status"), ({"school": "x" * 129}, "school")]:
            response = await self.save(changes)
            self.assertEqual(response.status_code, 400)
            self.assertIn(field, (await response.get_json())["field_errors"])
        response = await self.client.patch("/api/admin/members/20000000", headers=self.headers, json=[])
        self.assertEqual(response.status_code, 400)

    async def test_revision_conflict_with_old_detail_writer_and_no_partial_write(self):
        before = await self.snapshot()
        changed = await self.client.put("/api/user/real-name", headers=self.headers, json={"qq_id": "20000000", "real_name": "另一管理员"})
        self.assertEqual(changed.status_code, 200)
        response = await self.save({"school": "不能覆盖"}, before)
        self.assertEqual(response.status_code, 409)
        data = await response.get_json()
        self.assertEqual(data["code"], "profile_conflict")
        self.assertEqual(data["current"]["real_name"], "另一管理员")
        self.assertEqual(data["current"]["school"], before["school"])

    async def test_fingerprint_includes_hidden_campus_and_binding_versions_not_stats(self):
        before = await self.snapshot()
        db = await connect_db(self.path)
        await db.execute("UPDATE users SET last_sync_timestamp=123 WHERE qq_id='20000000'")
        await db.commit()
        self.assertEqual((await self.snapshot())["profile_revision"], before["profile_revision"])
        await db.execute("UPDATE users SET cjlu_username='new_campus' WHERE qq_id='20000000'")
        await db.commit(); await db.close()
        self.assertEqual((await self.save({"school": "新"}, before)).status_code, 409)

    async def test_binding_format_confirmation_and_duplicate_are_atomic(self):
        before = await self.snapshot()
        for changes, code, status in [({"cf_handle": "https://bad/"}, "invalid_account", 400), ({"cf_handle": "Fresh"}, "confirmation_required", 400), ({"cf_handle": "CF_1", "confirm_bindings": True, "expected_bindings": {"cf_handle": "CF_0"}, "binding_versions": before["binding_versions"]}, "duplicate_binding", 409)]:
            response = await self.save({"school": "不能部分写入", **changes}, before)
            self.assertEqual(response.status_code, status, await response.get_json())
            self.assertEqual((await response.get_json())["code"], code)
            self.assertEqual(await self.snapshot(), before)

    async def test_binding_cleanup_versions_unbind_and_scheduler_failure(self):
        before = await self.snapshot()
        db = await connect_db(self.path)
        for platform in ("codeforces", "atcoder", "cjlu"):
            await db.execute("INSERT INTO submissions(user_qq_id,platform,problem_id,submit_time) VALUES('20000000',?,'A',123)", (platform,))
        await db.commit(); await db.close()
        async def broken(*_args):
            raise RuntimeError("Synthetic scheduler unavailable")
        self.app.config["PLUGIN_CONFIG"]["_account_sync_submitter"] = broken
        response = await self.save({"cf_handle": "Fresh_Profile", "atcoder_handle": None, "confirm_bindings": True, "expected_bindings": {"cf_handle": "CF_0", "atcoder_handle": "AC_0"}, "binding_versions": before["binding_versions"]}, before)
        self.assertEqual(response.status_code, 200, await response.get_json())
        result = await response.get_json()
        self.assertTrue(result["success"] and result["warnings"])
        self.assertEqual(result["member"]["cf_binding_version"], before["cf_binding_version"] + 1)
        self.assertEqual(result["member"]["cjlu_binding_version"], before["cjlu_binding_version"])
        db = await connect_db(self.path)
        records = await profiles.row(db, "SELECT COUNT(*) n FROM submissions WHERE platform='cjlu'")
        self.assertEqual(records["n"], 1)
        self.assertEqual((await profiles.row(db, "SELECT COUNT(*) n FROM submissions WHERE platform<>'cjlu'"))["n"], 0)
        await db.close()

    async def test_successful_sync_is_202_and_returns_transaction_snapshot(self):
        before = await self.snapshot()
        self.app.config["PLUGIN_CONFIG"]["_account_sync_submitter"] = lambda *args: {"id": "synthetic-task"}
        response = await self.save({"cf_handle": "New_Profile", "confirm_bindings": True, "expected_bindings": {"cf_handle": "CF_0"}, "binding_versions": before["binding_versions"]}, before)
        self.assertEqual(response.status_code, 202)
        self.assertEqual((await response.get_json())["member"], await self.snapshot())

    async def test_changed_generation_or_closed_target_never_accepts_old_draft(self):
        before = await self.snapshot()
        db = await connect_db(self.path)
        await db.execute("UPDATE users SET account_epoch=account_epoch+1 WHERE qq_id='20000000'")
        await db.commit(); await db.close()
        response = await self.save({"name": "旧草稿"}, before)
        self.assertEqual((await response.get_json())["code"], "ACCOUNT_CHANGED")
        db = await connect_db(self.path)
        await db.execute("UPDATE users SET account_state='closed',account_epoch=account_epoch+1 WHERE qq_id='20000000'")
        await db.commit(); await db.close()
        self.assertEqual((await (await self.save({"name": "旧草稿"}, before)).get_json())["code"], "ACCOUNT_CLOSED")
        result = await (await self.client.get("/api/admin/members?search=20000000")).get_json()
        self.assertEqual(result["total"], 0)

    async def test_permission_csrf_and_private_cache(self):
        member, headers = await self.login("10000003")
        self.assertEqual((await member.get("/api/admin/members/options")).status_code, 403)
        self.assertEqual((await self.save({"name": "X"}, headers={})).status_code, 403)
        response = await self.client.get("/api/admin/members/20000000")
        self.assertIn("no-store", response.headers["Cache-Control"])

    async def test_final_transaction_rechecks_concurrent_role_revocation(self):
        before = await self.snapshot()
        db = await connect_db(self.path)
        await db.execute("BEGIN IMMEDIATE")
        await db.execute("UPDATE web_accounts SET role='member' WHERE qq_id='10000001'")
        task = asyncio.create_task(self.save({"school": "不能写入"}, before))
        try:
            await asyncio.sleep(0.1)
            await db.commit()
            response = await task
            self.assertEqual(response.status_code, 403, await response.get_json())
            self.assertEqual((await profiles.snapshot(db, "20000000"))["school"], before["school"])
        finally:
            await db.close()
