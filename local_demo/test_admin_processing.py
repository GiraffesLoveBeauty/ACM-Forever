"""Admin crawler integration uses temporary SQLite/journals and never an AI client."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from server import (LABELS, ReadOnlyLabels, create_local_app, initialize_database,
                    isolate_environment, ADMIN_QQ, ADMIN_PASSWORD, DEMO_QQ, DEMO_PASSWORD)
from test_integration import hashes
from synthetic_fixtures import build_fixture
from feat.api.acm_api.database import connect_db


class AdminProcessingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='admin-processing-')
        self.root = Path(self.temp.name)
        build_fixture(self.root / 'labels')
        self.labels = ReadOnlyLabels(self.root / 'labels', self.root / 'manual/overrides.jsonl')
        self.before = hashes(self.labels.root)
        self.env = patch.dict('os.environ'); self.env.start()
        self.database = self.root / 'local.sqlite3'
        isolate_environment(self.database)
        await initialize_database(self.database, self.labels)
        self.client = create_local_app(self.labels).test_client()
        self.path = '/api/admin/problem-processing/atcoder/abc464_c'

    async def asyncTearDown(self):
        self.assertEqual(self.before, hashes(self.labels.root))
        self.env.stop(); self.temp.cleanup()

    async def login(self, admin=True):
        res = await self.client.post('/api/auth/login', json={
            'qq_id': ADMIN_QQ if admin else DEMO_QQ,
            'password': ADMIN_PASSWORD if admin else DEMO_PASSWORD})
        self.assertEqual(res.status_code, 200)
        self.csrf = (await res.get_json())['csrf_token']

    async def update(self, sql, args=()):
        db = await connect_db(self.database)
        try:
            await db.execute(sql, args); await db.commit()
        finally:
            await db.close()

    async def detail(self):
        response = await self.client.get(self.path)
        self.assertEqual(response.status_code, 200)
        return await response.get_json()

    async def test_anonymous_and_member_cannot_read_admin_processing(self):
        self.assertEqual((await self.client.get(self.path)).status_code, 401)
        await self.login(False)
        self.assertEqual((await self.client.get(self.path)).status_code, 403)

    async def test_crawler_list_uses_effective_labels(self):
        await self.login()
        data = await (await self.client.get('/api/admin/database/problems?labels=difference_array')).get_json()
        self.assertTrue(any(r['problem_id'] == 'abc464_c' for r in data['items']))
        self.assertEqual(data['data_source'], 'crawler_problems')
        self.assertEqual(len(data['tag_facets']), 115)

    async def test_known_problem_identity_content_and_separate_hashes(self):
        await self.login(); data = await self.detail()
        self.assertEqual(data['problem_key'], 'atcoder:abc464:abc464_c')
        self.assertEqual(data['processing_status'], 'ready')
        self.assertTrue(data['edit_available'], data.get('edit_block_reason'))
        for field in ('normalized_content_hash', 'annotation_input_hash', 'translation_input_hash'):
            self.assertEqual(len(data[field]), 64)
        self.assertNotEqual(data['annotation_input_hash'], data['translation_input_hash'])

    async def test_ai_preflight_never_executes_or_imports_client(self):
        await self.login()
        with patch('annotation_api.client.APIClient.call', side_effect=AssertionError('NO API')):
            data = await self.detail()
        self.assertTrue(data['execution_enabled'])
        self.assertEqual(data['real_api_calls'], 0)
        self.assertIn('annotation', data['plan'])
        self.assertIn('translation', data['plan'])
        self.assertFalse(self.labels.override_file.exists())

    async def test_unknown_crawler_problem_is_not_hidden(self):
        await self.login()
        await self.update("UPDATE crawler_problems SET problem_id='abc464_z',metadata_json='{}',"
                          "problem_url='https://atcoder.jp/contests/abc464/tasks/abc464_z',"
                          "statement_source_url='https://atcoder.jp/contests/abc464/tasks/abc464_z' WHERE problem_id='abc464_c'")
        self.path = self.path.replace('abc464_c', 'abc464_z')
        data = await self.detail()
        self.assertEqual(data['problem_key'], 'atcoder:abc464:abc464_z')
        self.assertFalse(data['edit_available'])
        self.assertIsNone(data['existing'])
        self.assertIn('尚未纳入', data['edit_block_reason'])

    async def test_pdf_only_crawler_is_pending(self):
        await self.login()
        await self.update("UPDATE crawler_problems SET statement_text=NULL,statement_html=NULL,statement_pdf=? WHERE problem_id='abc464_c'", (b'%PDF-synthetic',))
        data = await self.detail()
        self.assertEqual(data['processing_status'], 'pdf_pending')
        # Historical response review can additionally block a newly PDF-only source.
        self.assertIn(data['plan']['translation']['status'], {'pending','needs_review'})
        self.assertFalse(data['plan']['translation']['needs_ai'])
        self.assertEqual(data['statement_preview'], '')
        self.assertFalse(data['edit_available'])

    async def test_changed_content_requires_review_before_editing(self):
        await self.login()
        await self.update("UPDATE crawler_problems SET statement_text=statement_text||'\nChanged constraints.' WHERE problem_id='abc464_c'")
        data = await self.detail()
        self.assertFalse(data['edit_available'])
        self.assertIn('版本不一致', data['edit_block_reason'])
        self.assertEqual(data['plan']['annotation']['status'], 'needs_review')

    async def test_missing_crawler_returns_404(self):
        await self.login()
        self.assertEqual((await self.client.get(self.path + '_missing')).status_code, 404)

    async def test_bad_identity_returns_invalid_not_a_guess(self):
        await self.login()
        await self.update("UPDATE crawler_problems SET contest_id='abc999' WHERE problem_id='abc464_c'")
        data = await self.detail()
        self.assertEqual(data['processing_status'], 'invalid')
        self.assertFalse(data['edit_available'])

    async def test_manual_changes_immediately_affect_crawler_filters(self):
        await self.login()
        path = '/api/secondary/tag-management/atcoder/abc464_c'
        original = await (await self.client.get(path)).get_json()
        result = await self.client.post(path, headers={'X-CSRF-Token': self.csrf}, json={
            'operation': 'save', 'tag_ids': ['enumeration'], 'revision': original['revision'],
            'reason': '临时后台验收', 'request_id': uuid4().hex})
        self.assertEqual(result.status_code, 200)
        found = await (await self.client.get('/api/admin/database/problems?labels=enumeration&q=abc464_c')).get_json()
        self.assertEqual(found['total'], 1)
        absent = await (await self.client.get('/api/admin/database/problems?labels=difference_array&q=abc464_c')).get_json()
        self.assertEqual(absent['total'], 0)
        data = await self.detail()
        self.assertTrue(data['plan']['manual_overlay_present'])
        self.assertEqual(data['existing']['effective_tags'][0]['source'], 'manual_add')

    async def test_execution_post_is_disabled_even_for_admin(self):
        await self.login()
        self.assertEqual((await self.client.post(self.path, json={'execute': True}, headers={'X-CSRF-Token': self.csrf})).status_code, 403)

    async def test_bad_label_and_status_rejected(self):
        await self.login()
        for query in ('labels=not_a_tag', 'status=wrong'):
            self.assertEqual((await self.client.get('/api/admin/database/problems?' + query)).status_code, 400)

    async def test_custom_hashed_debug_password_survives_restart(self):
        from feat.api.acm_api.auth_service import hash_password
        password = 'synthetic-new-local-password'
        encoded = hash_password(password)
        await initialize_database(self.database, self.labels, admin_password_hash=encoded)
        await initialize_database(self.database, self.labels, admin_password_hash=encoded)
        response = await self.client.post('/api/auth/login', json={'qq_id': '1', 'password': password})
        self.assertEqual(response.status_code, 200)
        data = await response.get_json()
        self.assertEqual(data['qq_id'], '1')
        self.assertEqual(data['role'], 'admin')
        self.assertEqual((await self.client.get(self.path)).status_code, 200)

    async def test_short_debug_identity_does_not_allow_other_short_accounts(self):
        from feat.api.acm_api import backend_api
        app = create_local_app(self.labels)
        async with app.app_context():
            self.assertTrue(backend_api._valid_qq('1'))
            self.assertFalse(backend_api._valid_qq('2'))
            app.config['LOCAL_TAG_MANAGEMENT'] = False
            self.assertFalse(backend_api._valid_qq('1'))

    async def test_source_change_after_open_blocks_save_on_server(self):
        await self.login()
        path = '/api/secondary/tag-management/atcoder/abc464_c'
        original = await (await self.client.get(path)).get_json()
        await self.update("UPDATE crawler_problems SET statement_text=statement_text||'\nChanged bound.' WHERE problem_id='abc464_c'")
        result = await self.client.post(path, headers={'X-CSRF-Token': self.csrf}, json={
            'operation': 'save', 'tag_ids': [], 'revision': original['revision'],
            'reason': '过期正文应拒绝保存', 'request_id': uuid4().hex})
        self.assertEqual(result.status_code, 409)
        self.assertFalse(self.labels.override_file.exists())
