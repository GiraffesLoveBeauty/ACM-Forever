"""Lifecycle foundation regressions; all users and databases are synthetic.

The intake switch remains off by default; full closure contracts are covered in
test_account_closure after the policy confirmation.
"""
import asyncio
import os
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from contextlib import closing
from unittest.mock import AsyncMock, patch

import aiosqlite
import test_api_contract as contract
from feat.api.acm_api import backend_api, binding_service, cf_history
from feat.api.acm_api.auth_service import hash_password, password_hash_usable, verify_password
from feat.api.acm_api.account_lifecycle_service import (
    AccountLifecycleError, bootstrap_root, require_active_user, snapshot_epoch,
)
from feat.api.acm_api.binding_guard import BindingChanged, BindingGuard
from feat.api.acm_api.database import connect_db
from feat.api.app import create_app
from feat.api.service_runtime import SyncEngine

PASSWORD = "Test-Password-123!"


class LifecycleMigrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "lifecycle.db"
        self.db = await connect_db(self.path)

    async def asyncTearDown(self):
        await self.db.close()
        self.directory.cleanup()

    async def test_legacy_database_migration_preserves_identity_and_member_status(self):
        legacy = Path(self.directory.name) / "legacy.db"
        with closing(sqlite3.connect(legacy)) as connection, connection:
            connection.execute("CREATE TABLE users(qq_id TEXT PRIMARY KEY,name TEXT NOT NULL,cf_handle TEXT,luogu_id TEXT,nowcoder_id TEXT,atcoder_handle TEXT,status TEXT,school TEXT,last_sync_timestamp INTEGER DEFAULT 0)")
            connection.execute("INSERT INTO users VALUES('12345678','Legacy','Handle',NULL,NULL,NULL,'closed','School',123)")
        db = await connect_db(legacy)
        try:
            async with db.execute("SELECT * FROM users") as cursor:
                user = await cursor.fetchone()
            self.assertEqual((user['name'], user['cf_handle'], user['status'], user['school'], user['last_sync_timestamp']), ('Legacy', 'Handle', 'closed', 'School', 123))
            self.assertEqual((user['account_state'], user['account_epoch'], user['closed_at']), ('active', 1, None))
        finally:
            await db.close()

    async def tombstone(self):
        await self.db.execute("INSERT INTO users(qq_id,name) VALUES('12345678','Fixture')")
        await self.db.execute("UPDATE users SET account_state='closed',account_epoch=2,closed_at=123 WHERE qq_id='12345678'")
        await self.db.commit()

    async def test_repeated_migration_does_not_reactivate_tombstone(self):
        await self.tombstone()
        second = await connect_db(self.path)
        try:
            async with second.execute("SELECT account_state,account_epoch,closed_at FROM users") as cursor:
                self.assertEqual(tuple(await cursor.fetchone()), ('closed', 2, 123))
        finally:
            await second.close()

    async def test_closed_tombstone_cannot_be_reopened_deleted_replaced_or_upserted(self):
        await self.tombstone()
        await self.db.execute("PRAGMA recursive_triggers=OFF")
        for sql in (
            "UPDATE users SET account_state='active' WHERE qq_id='12345678'",
            "DELETE FROM users WHERE qq_id='12345678'",
            "INSERT OR REPLACE INTO users(qq_id,name) VALUES('12345678','Replacement')",
            "INSERT INTO users(qq_id,name) VALUES('12345678','Upsert') ON CONFLICT(qq_id) DO UPDATE SET name=excluded.name",
        ):
            with self.subTest(sql=sql):
                with self.assertRaises(aiosqlite.IntegrityError):
                    await self.db.execute(sql)
                await self.db.rollback()
        async with self.db.execute("SELECT account_state,name FROM users") as cursor:
            self.assertEqual(tuple(await cursor.fetchone()), ('closed', 'Fixture'))

    async def test_lifecycle_state_and_epoch_are_constrained(self):
        await self.db.execute("INSERT INTO users(qq_id,name) VALUES('12345678','Fixture')")
        await self.db.commit()
        for clause in ("account_state='disabled'", "account_epoch=0", "account_epoch=1.5", "account_state='closed'"):
            with self.subTest(clause=clause):
                with self.assertRaises(aiosqlite.IntegrityError):
                    await self.db.execute("UPDATE users SET " + clause)
                await self.db.rollback()
        await self.db.execute("UPDATE users SET account_epoch=3")
        await self.db.commit()
        with self.assertRaises(aiosqlite.IntegrityError):
            await self.db.execute("UPDATE users SET account_epoch=2")
        await self.db.rollback()

    async def test_active_upsert_and_member_status_remain_independent(self):
        await self.db.execute("INSERT INTO users(qq_id,name,status) VALUES('12345678','Old','毕业')")
        await self.db.execute("INSERT INTO users(qq_id,name,status) VALUES('12345678','New','现役') ON CONFLICT(qq_id) DO UPDATE SET name=excluded.name,status=excluded.status")
        user = await require_active_user(self.db, '12345678')
        self.assertEqual((user['account_state'], user['account_epoch']), ('active', 1))
        with self.assertRaises(AccountLifecycleError) as error:
            await require_active_user(self.db, '12345678', expected_epoch=2)
        self.assertEqual(error.exception.code, 'ACCOUNT_CHANGED')

    async def test_missing_epoch_snapshot_is_rejected(self):
        for user in ({'qq_id': '12345678'}, {'qq_id': '12345678', 'account_epoch': 1}, {'qq_id': '12345678', 'account_state': 'active', 'account_epoch': None}):
            with self.subTest(user=user):
                with self.assertRaises(AccountLifecycleError):
                    snapshot_epoch(user)

    async def test_two_bootstrap_processes_cannot_both_create_first_root(self):
        other = await aiosqlite.connect(self.path)
        other.row_factory = aiosqlite.Row
        await other.execute("PRAGMA busy_timeout=5000")
        encoded = hash_password(PASSWORD)
        try:
            results = await asyncio.gather(
                bootstrap_root(self.db, '12345678', encoded, 123),
                bootstrap_root(other, '87654321', encoded, 123),
            )
            self.assertEqual(sorted(results), [False, True])
            async with self.db.execute("SELECT COUNT(*) FROM web_accounts") as cursor:
                self.assertEqual((await cursor.fetchone())[0], 1)
        finally:
            await other.close()

    async def test_revoked_password_marker_is_always_unusable(self):
        for encoded in ('!closed', '', 'pbkdf2_sha256$600000$salt$bad', 'pbkdf2_sha256$1$salt$' + 'a' * 64):
            with self.subTest(encoded=encoded):
                self.assertFalse(password_hash_usable(encoded))
                self.assertFalse(verify_password(PASSWORD, encoded))


class LifecycleApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await contract.ApiContractTests.asyncSetUp(self)
        backend_api._LOGIN_ATTEMPTS.clear()

    asyncTearDown = contract.ApiContractTests.asyncTearDown
    account_login = contract.ApiContractTests.account_login

    async def sql(self, sql, values=()):
        db = await aiosqlite.connect(self.db_path)
        try:
            async with db.execute(sql, values) as cursor:
                rows = await cursor.fetchall()
            await db.commit()
            return rows
        finally:
            await db.close()

    async def fixture_user(self, qq_id, *, role=None):
        await self.sql("INSERT INTO users(qq_id,name,status) VALUES(?,?,'现役')", (qq_id, 'User-' + qq_id))
        if role:
            now = int(time.time())
            await self.sql("INSERT INTO web_accounts(qq_id,password_hash,role,must_change_password,is_active,credential_version,created_at,updated_at) VALUES(?,?,?,0,1,1,?,?)", (qq_id, hash_password(PASSWORD), role, now, now))

    async def closed_fixture(self, qq_id='12345678'):
        # Metadata-only fixture deliberately leaves the old hash and binding intact,
        # proving checks do not depend on credential or binding cleanup succeeding.
        await self.sql("UPDATE users SET account_state='closed',account_epoch=account_epoch+1,closed_at=? WHERE qq_id=?", (int(time.time()), qq_id))

    async def test_closed_account_rejects_password_login_and_old_session(self):
        async with self.app.test_app():
            client = self.app.test_client()
            headers = await self.account_login(client, role='member')
            await self.closed_fixture()
            self.assertFalse((await (await client.get('/api/auth/me')).get_json())['authenticated'])
            self.assertEqual((await client.put('/api/me/profile', json={'name': 'Late'}, headers=headers)).status_code, 401)
            self.assertEqual((await client.post('/api/auth/login', json={'qq_id': '12345678', 'password': PASSWORD})).status_code, 401)
            self.assertEqual((await self.sql("SELECT name FROM users"))[0][0], '测试账号')

    async def test_epoch_change_revokes_active_cookie(self):
        async with self.app.test_app():
            client = self.app.test_client()
            await self.account_login(client, role='member')
            await self.sql('UPDATE users SET account_epoch=account_epoch+1')
            self.assertEqual((await client.get('/api/me/profile')).status_code, 401)

    async def test_closed_target_rejects_all_web_account_writers(self):
        async with self.app.test_app():
            client = self.app.test_client()
            headers = await self.account_login(client)
            await self.fixture_user('87654321', role='member')
            await self.closed_fixture('87654321')
            operations = (
                ('PATCH', '/api/admin/web-accounts/87654321', {'is_active': True}),
                ('PATCH', '/api/admin/web-accounts/87654321', {'role': 'root'}),
                ('POST', '/api/admin/web-accounts/87654321/reset-password', {'initial_password': PASSWORD}),
                ('POST', '/api/admin/web-accounts/87654321/reset-temporary-password', {}),
                ('POST', '/api/register', {'qq_id': '87654321', 'name': 'Reopen'}),
                ('PUT', '/api/user', {'qq_id': '87654321', 'name': 'Reopen'}),
            )
            for method, url, data in operations:
                with self.subTest(url=url, data=data):
                    response = await client.open(url, method=method, json=data, headers=headers)
                    self.assertEqual(response.status_code, 409, await response.get_json())
                    self.assertEqual((await response.get_json())['code'], 'ACCOUNT_CLOSED')
            self.assertEqual((await self.sql("SELECT role,credential_version FROM web_accounts WHERE qq_id='87654321'"))[0], ('member', 1))

    async def test_batch_never_issues_password_for_closed_user(self):
        async with self.app.test_app():
            client = self.app.test_client()
            headers = await self.account_login(client)
            await self.fixture_user('87654321')
            await self.closed_fixture('87654321')
            response = await client.post('/api/admin/web-accounts/batch', json={'qq_ids': ['87654321']}, headers=headers)
            data = await response.get_json()
            self.assertEqual(data, {'created': [], 'skipped': [{'qq_id': '87654321', 'reason': 'account_closed'}]})
            self.assertFalse(await self.sql("SELECT 1 FROM web_accounts WHERE qq_id='87654321'"))

    async def test_closed_accounts_are_omitted_from_discovery_and_rankings(self):
        async with self.app.test_app():
            client = self.app.test_client()
            await self.account_login(client)
            await self.fixture_user('87654321')
            await self.closed_fixture('87654321')
            for path, key in (('/api/admin/members', 'items'), ('/api/admin/web-account-candidates?include_issued=true', 'items'), ('/api/community/leaderboard', 'rows')):
                response = await client.get(path)
                self.assertEqual(response.status_code, 200, await response.get_json())
                self.assertNotIn('87654321', str((await response.get_json())[key]))
            self.assertEqual((await client.get('/api/member/87654321')).status_code, 409)

    async def test_bot_cannot_rebuild_mutate_read_or_delete_tombstone(self):
        async with self.app.test_app():
            await self.fixture_user('87654321')
            await self.closed_fixture('87654321')
            client = self.app.test_client()
            headers = {'Authorization': 'Bearer test-only-bot-token'}
            for method, suffix, body in (
                ('GET', '', None), ('GET', '/summary', None), ('PUT', '', {'name': 'Reopen'}),
                ('PATCH', '/profile', {'name': 'Changed'}), ('DELETE', '', None),
                ('PUT', '/notification-preferences', {'enabled': True}),
                ('POST', '/bindings/cf/confirm', {}),
            ):
                with self.subTest(method=method, suffix=suffix):
                    response = await client.open('/internal/v1/users/87654321' + suffix, method=method, json=body, headers=headers)
                    self.assertEqual(response.status_code, 409, await response.get_json())
                    self.assertEqual((await response.get_json())['code'], 'ACCOUNT_CLOSED')
            self.assertEqual((await self.sql('SELECT account_state FROM users'))[0][0], 'closed')

    async def test_bot_cannot_use_member_delete_to_remove_web_account(self):
        async with self.app.test_app():
            await self.fixture_user('87654321', role='root')
            client = self.app.test_client()
            response = await client.delete('/internal/v1/users/87654321', headers={'Authorization': 'Bearer test-only-bot-token'})
            self.assertEqual(response.status_code, 409)
            self.assertEqual((await response.get_json())['code'], 'WEB_ACCOUNT_PROTECTED')
            self.assertTrue(await self.sql('SELECT 1 FROM web_accounts'))

    async def test_batch_bot_submission_write_rechecks_all_members(self):
        async with self.app.test_app():
            await self.fixture_user('12345678')
            await self.fixture_user('87654321')
            await self.closed_fixture('87654321')
            response = await self.app.test_client().post('/internal/v1/submissions/batch', headers={'Authorization': 'Bearer test-only-bot-token'}, json={'items': [
                {'qq_id': q, 'platform': 'codeforces', 'problem_id': '1A', 'submit_time': 123} for q in ('12345678', '87654321')
            ]})
            self.assertEqual(response.status_code, 409, await response.get_json())
            self.assertFalse(await self.sql('SELECT 1 FROM submissions'))

    async def test_last_root_is_protected_even_with_legacy_login_configured(self):
        async with self.app.test_app():
            client = self.app.test_client()
            headers = await self.account_login(client)
            self.app.config['PLUGIN_CONFIG'].update(webui_legacy_admin_login=True, webui_admin_username='legacy', webui_admin_password=PASSWORD)
            for data in ({'role': 'member'}, {'is_active': False}):
                response = await client.patch('/api/admin/web-accounts/12345678', json=data, headers=headers)
                self.assertEqual(response.status_code, 409)
                self.assertEqual((await response.get_json())['code'], 'LAST_ROOT_PROTECTED')

    async def test_expired_revoked_disabled_or_closed_root_is_not_a_successor(self):
        async with self.app.test_app():
            client = self.app.test_client()
            headers = await self.account_login(client)
            await self.fixture_user('87654321', role='root')
            changes = (
                "must_change_password=1,temporary_password_expires_at=1",
                "password_hash='!closed'",
                "is_active=0",
            )
            for clause in changes:
                await self.sql("UPDATE web_accounts SET must_change_password=0,temporary_password_expires_at=NULL,is_active=1,password_hash=? WHERE qq_id='87654321'", (hash_password(PASSWORD),))
                await self.sql("UPDATE web_accounts SET " + clause + " WHERE qq_id='87654321'")
                response = await client.patch('/api/admin/web-accounts/12345678', json={'role': 'member'}, headers=headers)
                self.assertEqual(response.status_code, 409)
            await self.sql("UPDATE web_accounts SET is_active=1,password_hash=? WHERE qq_id='87654321'", (hash_password(PASSWORD),))
            await self.closed_fixture('87654321')
            response = await client.patch('/api/admin/web-accounts/12345678', json={'role': 'member'}, headers=headers)
            self.assertEqual(response.status_code, 409)

    async def concurrent_roots(self, *, cross):
        async with self.app.test_app():
            first, second = self.app.test_client(), self.app.test_client()
            h1 = await self.account_login(first)
            await self.fixture_user('87654321', role='root')
            login = await second.post('/api/auth/login', json={'qq_id': '87654321', 'password': PASSWORD})
            h2 = {'X-CSRF-Token': (await login.get_json())['csrf_token']}
            original = backend_api._session_identity
            arrived, ready = 0, asyncio.Event()
            async def capture_before_writes():
                nonlocal arrived
                identity = await original()
                arrived += 1
                if arrived == 2:
                    ready.set()
                await ready.wait()
                return identity
            with patch.object(backend_api, '_session_identity', capture_before_writes):
                responses = await asyncio.wait_for(asyncio.gather(
                    first.patch('/api/admin/web-accounts/' + ('87654321' if cross else '12345678'), json={'role': 'member'}, headers=h1),
                    second.patch('/api/admin/web-accounts/' + ('12345678' if cross else '87654321'), json={'role': 'member'}, headers=h2),
                ), 10)
            codes = sorted(response.status_code for response in responses)
            self.assertEqual(codes, [200, 401 if cross else 409])
            self.assertEqual((await self.sql("SELECT COUNT(*) FROM web_accounts WHERE role='root' AND is_active=1"))[0][0], 1)

    async def test_two_roots_cannot_concurrently_demote_themselves(self):
        await self.concurrent_roots(cross=False)

    async def test_stale_root_actor_cannot_demote_the_remaining_root(self):
        await self.concurrent_roots(cross=True)

    async def test_forum_final_write_rejects_actor_closed_after_authentication(self):
        from feat.api.acm_api import forum_api as forum_module
        async with self.app.test_app():
            client = self.app.test_client()
            headers = await self.account_login(client, role='member')
            original = forum_module.get_db
            async def close_before_write():
                await self.closed_fixture()
                return await original()
            with patch.object(forum_module, 'get_db', close_before_write):
                response = await client.post('/api/forum/drafts', json={'title': 'A draft', 'body': 'Draft content'}, headers=headers)
            self.assertEqual(response.status_code, 409, await response.get_json())
            self.assertFalse(await self.sql('SELECT 1 FROM forum_drafts'))

    async def test_post_edit_request_cannot_create_draft_after_actor_closes(self):
        from feat.api.acm_api import forum_api as forum_module
        async with self.app.test_app():
            client = self.app.test_client()
            headers = await self.account_login(client, role='member')
            response = await client.post('/api/forum/posts', headers=headers, json={'title': 'Original post', 'body': 'Original content', 'category_id': 1})
            post_id = (await response.get_json())['id']
            original = forum_module.get_db
            async def close_before_write():
                await self.closed_fixture()
                return await original()
            with patch.object(forum_module, 'get_db', close_before_write):
                response = await client.post(f'/api/forum/mine/posts/{post_id}/edit', headers=headers, json={})
            self.assertEqual(response.status_code, 409, await response.get_json())
            self.assertFalse(await self.sql('SELECT 1 FROM forum_drafts'))

    async def test_post_resubmission_cannot_write_history_after_actor_closes(self):
        from feat.api.acm_api import forum_api as forum_module
        async with self.app.test_app():
            client = self.app.test_client()
            headers = await self.account_login(client, role='member')
            response = await client.post('/api/forum/posts', headers=headers, json={'title': 'Original post', 'body': 'Original content', 'category_id': 1})
            post_id = (await response.get_json())['id']
            response = await client.post(f'/api/forum/mine/posts/{post_id}/edit', headers=headers, json={})
            draft_id = (await response.get_json())['id']
            draft = await (await client.get(f'/api/forum/drafts/{draft_id}')).get_json()
            original = forum_module.get_db
            async def close_before_write():
                await self.closed_fixture()
                return await original()
            with patch.object(forum_module, 'get_db', close_before_write):
                response = await client.post(f'/api/forum/drafts/{draft_id}/submit', headers=headers, json={'edit_version': draft['edit_version']})
            self.assertEqual(response.status_code, 409, await response.get_json())
            self.assertFalse(await self.sql('SELECT 1 FROM forum_post_history'))
            self.assertEqual((await self.sql('SELECT content_version FROM forum_posts'))[0][0], 1)

    async def test_binding_response_cannot_recreate_state_after_closure(self):
        async with self.app.test_app():
            client = self.app.test_client()
            headers = await self.account_login(client, role='member')
            async def upstream(*args):
                await self.closed_fixture()
                return 'NewHandle'
            with patch.object(binding_service, 'validate_account', upstream):
                response = await client.post('/api/me/bindings/cf/verification', json={'account': 'NewHandle'}, headers=headers)
            self.assertEqual(response.status_code, 409, await response.get_json())
            self.assertFalse(await self.sql('SELECT 1 FROM account_bind_verifications WHERE validated_at>0'))

    async def test_bootstrap_does_not_recreate_root_for_closed_identity_without_web_row(self):
        db = await connect_db(self.db_path)
        await db.close()
        await self.fixture_user('87654321')
        await self.closed_fixture('87654321')
        with patch.dict(os.environ, {'ACM_BOOTSTRAP_ROOT_QQ_ID': '87654321', 'ACM_BOOTSTRAP_ROOT_PASSWORD': PASSWORD}):
            app = create_app()
            async with app.test_app():
                self.assertFalse(await self.sql('SELECT 1 FROM web_accounts'))
                self.assertEqual((await self.sql('SELECT account_state FROM users'))[0][0], 'closed')

    async def test_guard_fences_closed_crawler_and_late_cursor_writes(self):
        async with self.app.test_app():
            await self.fixture_user('12345678')
            await self.sql("UPDATE users SET atcoder_handle='Original' WHERE qq_id='12345678'")
            engine = SyncEngine(self.db_path, {})
            await engine.start()
            try:
                async with engine.db.execute('SELECT * FROM users') as cursor:
                    old = await cursor.fetchone()
                await engine._get_platform_sync_state('12345678', 'atcoder', user=old)
                await self.closed_fixture()
                db = await aiosqlite.connect(self.db_path)
                db.row_factory = aiosqlite.Row
                try:
                    with self.assertRaises(BindingChanged):
                        await BindingGuard(db, old, 'atcoder').executemany('INSERT INTO submissions(user_qq_id,platform,problem_id,submit_time) VALUES(?,?,?,?)', [('12345678', 'atcoder', 'stale', 123)])
                finally:
                    await db.close()
                self.assertFalse(await engine._mark_platform_sync('12345678', 'atcoder', 'success', 456, success=True))
                self.assertFalse(await engine._mark_user_synced(old, 456))
                self.assertFalse(await self.sql('SELECT 1 FROM submissions'))
                self.assertEqual((await self.sql('SELECT last_sync_timestamp FROM users'))[0][0], 0)
            finally:
                await engine.close()

    async def test_sync_rejects_snapshots_without_epoch_and_skips_closed_scans(self):
        async with self.app.test_app():
            await self.fixture_user('12345678')
            await self.sql("UPDATE users SET atcoder_handle='Original' WHERE qq_id='12345678'")
            engine = SyncEngine(self.db_path, {})
            await engine.start()
            try:
                with patch.object(engine, '_fetch_platform_with_limit', AsyncMock()) as fetch:
                    result = await engine.sync_single_platform_for_days('12345678', 'atcoder', 0, expected_binding={'account': 'Original', 'version': 1})
                    self.assertEqual(result, -4)
                    fetch.assert_not_awaited()
                await self.closed_fixture()
                with patch.object(engine, '_sync_user_with_limit', AsyncMock()) as sync:
                    await engine.sync_all_users_data()
                    sync.assert_not_awaited()
            finally:
                await engine.close()

    async def test_cf_page_arriving_after_closure_is_not_written(self):
        async with self.app.test_app():
            await self.fixture_user('12345678')
            await self.sql("UPDATE users SET cf_handle='Original' WHERE qq_id='12345678'")
            db = await aiosqlite.connect(self.db_path)
            db.row_factory = aiosqlite.Row
            try:
                async with db.execute('SELECT * FROM users') as cursor:
                    old = await cursor.fetchone()
                async def upstream(*args):
                    await self.closed_fixture()
                    return [{'id': 1, 'creationTimeSeconds': 123, 'verdict': 'OK', 'problem': {'contestId': 1, 'index': 'A', 'name': 'Fixture'}}]
                with patch.object(cf_history, 'cf_request', upstream):
                    self.assertEqual(await cf_history._fetch_history(None, old, 0, db, {}), -1)
                self.assertFalse(await self.sql('SELECT 1 FROM submissions'))
                self.assertFalse(await self.sql('SELECT 1 FROM submission_attempts'))
                self.assertFalse(await self.sql('SELECT 1 FROM user_platform_sync_state'))
            finally:
                await db.close()

    async def test_closure_intake_is_disabled_by_default(self):
        async with self.app.test_app():
            client = self.app.test_client()
            await self.account_login(client, role='member')
            for method, url in (('GET', '/api/me/account-closure/preview'), ('POST', '/api/me/account-closure'), ('GET', '/api/account-closures/fixture')):
                self.assertIn((await client.open(url, method=method)).status_code, (404, 405))


if __name__ == '__main__':
    unittest.main()
