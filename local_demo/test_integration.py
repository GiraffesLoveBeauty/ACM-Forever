"""Read-only local integration contracts; no real network or API requests."""
import hashlib
import json
import os
import shutil
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from synthetic_fixtures import build_fixture

from server import (ReadOnlyLabels, LABELS, DEMO_QQ, DEMO_PASSWORD, isolate_environment,
                    initialize_database, create_local_app, loopback_only)


def hashes(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


class SnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='synthetic-snapshot-')
        cls.fixture_root = build_fixture(Path(cls.temp.name)/'labels')

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_synthetic_ten_labels_and_identity(self):
        rows = ReadOnlyLabels(self.fixture_root).views()
        self.assertEqual(len(rows), 10)
        self.assertTrue(all(r['problem_key'] == f"atcoder:{r['problem_key'].split(':')[1]}:{r['problem_id']}" for r in rows))
        self.assertTrue(all(r['annotation_status'] == 'success' for r in rows))

    def test_query_does_not_modify_snapshot(self):
        before = hashes(self.fixture_root)
        ReadOnlyLabels(self.fixture_root).views()
        self.assertEqual(hashes(self.fixture_root), before)

    def test_auto_not_human_verified(self):
        rows = ReadOnlyLabels(self.fixture_root).views()
        self.assertTrue(all(r['review_status'] == 'auto' and not r['fully_human_verified'] for r in rows))
        self.assertTrue(all(t['source'] == 'ai' for r in rows for t in r['effective_tags']))

    def test_blocked_translation_not_activated(self):
        # A blocked response alone remains unusable: only an explicit activation enables it.
        with tempfile.TemporaryDirectory(prefix='blocked-response-') as temp:
            root=Path(temp)/'labels';shutil.copytree(self.fixture_root,root)
            pointer=root/'translations/current.json'
            index=json.loads(pointer.read_text(encoding='utf-8')) if pointer.exists() else {}
            index.pop('atcoder:abc469:abc469_a',None)
            pointer.write_text(json.dumps(index),encoding='utf-8')
            row = ReadOnlyLabels(root).find('atcoder', 'abc469_a')
        self.assertEqual(row['translation_status'], 'needs_review')
        self.assertIn('blocked', row['translation_task_states'])
        self.assertIsNone(row['translated_statement'])
        self.assertFalse(row['translation_active'])

    def test_active_translations_have_saved_response_and_activation_evidence(self):
        from annotation_api.adapter import digest
        from problem_processing.execution_state import Ledger
        index=json.loads((self.fixture_root/'translations/current.json').read_text(encoding='utf-8'))
        for view in ReadOnlyLabels(self.fixture_root).views():
            self.assertTrue(view['translation_active'])
            fp=index[view['problem_key']]
            row=json.loads((self.fixture_root/'translations/history'/(fp+'.json')).read_text(encoding='utf-8'))
            audit=json.loads((self.fixture_root/'translations/activations'/(fp+'.json')).read_text(encoding='utf-8'))
            self.assertEqual(digest(row),audit['accepted_result_sha256'])
            ledger=Ledger(self.fixture_root);task=ledger.load(audit['source_task_id'])
            envelope=ledger.artifact('responses',task['attempt_id'],audit['source_response_sha256'])
            self.assertFalse(envelope['response']['model'].startswith('mock'))
            self.assertFalse(row['fully_human_verified'])

    def test_public_projection_excludes_secrets_requests_and_statement(self):
        for row in ReadOnlyLabels(self.fixture_root).views():
            self.assertFalse({'api_key','headers','authorization','input_problem','original_statement','response'} & row.keys())

    def test_unknown_id_never_matches_by_title(self):
        self.assertIsNone(ReadOnlyLabels(self.fixture_root).find('atcoder', 'Train Car'))

    def test_network_boundary(self):
        with self.assertRaises(PermissionError): loopback_only('socket.connect', (None, ('8.8.8.8', 443)))
        with self.assertRaises(PermissionError): loopback_only('socket.getaddrinfo', ('example.com', 443))
        loopback_only('socket.connect', (None, ('127.0.0.1', 18088)))

    def test_inherited_config_scrubbed(self):
        with patch.dict(os.environ, {'OPENAI_API_KEY':'synthetic-only', 'ACM_DATABASE_PATH':'wrong', 'TAG_DATA_ROOT':'wrong'}):
            isolate_environment(Path('local-only.sqlite'))
            self.assertNotIn('OPENAI_API_KEY', os.environ)
            self.assertEqual(os.environ['ACM_DATABASE_PATH'], 'local-only.sqlite')
            self.assertEqual(os.environ['TAG_DATA_ROOT'], str(LABELS))


class APITests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='local-forum-integration-')
        self.env = patch.dict(os.environ)
        self.env.start()
        self.database = Path(self.temp.name) / 'fixture.sqlite3'
        isolate_environment(self.database)
        self.fixture_root = build_fixture(Path(self.temp.name)/'labels')
        self.labels = ReadOnlyLabels(self.fixture_root)
        self.before = hashes(self.fixture_root)
        await initialize_database(self.database, self.labels)
        self.app = create_local_app(self.labels)
        self.client = self.app.test_client()

    async def asyncTearDown(self):
        self.assertEqual(self.before, hashes(self.fixture_root))
        self.env.stop()
        self.temp.cleanup()

    async def login(self):
        response = await self.client.post('/api/auth/login', json={'qq_id':DEMO_QQ,'password':DEMO_PASSWORD})
        self.assertEqual(response.status_code, 200)

    async def test_auth_required(self):
        self.assertEqual((await self.client.get('/api/secondary/problems')).status_code, 401)

    async def test_list_ten_after_login(self):
        await self.login()
        response = await self.client.get('/api/secondary/problems')
        data = await response.get_json()
        self.assertEqual(data['count'], 10)
        self.assertEqual(data['real_api_calls'], 0)
        self.assertEqual(data['active_translations'], 10)

    async def test_synthetic_detail_and_labels_join(self):
        await self.login()
        for row in self.labels.views():
            path = f"atcoder/{row['problem_id']}"
            detail = await (await self.client.get('/api/me/problems/' + path)).get_json()
            view = await (await self.client.get('/api/secondary/problems/' + path)).get_json()
            self.assertEqual(detail['problem_name'], row['title'])
            self.assertEqual(view['problem_key'], row['problem_key'])
            self.assertTrue(detail['content_available'])

    async def test_no_write_or_sync_entry(self):
        await self.login()
        for path in ['/api/problems/sync', '/api/secondary/problems', '/internal/v1/execute', '/api/me/problems/atcoder/abc469_a/state']:
            self.assertEqual((await self.client.post(path, json={})).status_code, 403)

    async def test_unknown_detail(self):
        await self.login()
        self.assertEqual((await self.client.get('/api/secondary/problems/atcoder/no_such_task')).status_code, 404)

    async def test_page_served_and_security_headers(self):
        await self.login()
        response = await self.client.get('/processing-demo.html')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['X-Local-Demo'], 'isolated-read-only')
        csp=response.headers['Content-Security-Policy']
        self.assertIn("connect-src 'self'",csp)
        self.assertIn("script-src 'self'",csp)
        self.assertIn('https://img.atcoder.jp',csp)
        self.assertNotIn('img-src https:;',csp)

    async def test_remote_host_rejected(self):
        self.assertEqual((await self.client.get('/health', headers={'Host':'external.example'})).status_code, 403)

    async def test_no_background_jobs(self):
        async with self.app.test_app():
            self.app.sync_engine.start.assert_awaited_once()
            self.assertTrue(self.database.exists())


if __name__ == '__main__':
    unittest.main()
