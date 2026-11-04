"""Isolated local editing contracts. Temporary journals/SQLite, no live network or AI."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from server import (ReadOnlyLabels, LABELS, ADMIN_QQ, ADMIN_PASSWORD, DEMO_QQ, DEMO_PASSWORD,
                    create_local_app, initialize_database, isolate_environment)
from tag_editor import LocalTagEditor, EditConflict
from label_pipeline import TAG_BY_ID
from test_integration import hashes
from synthetic_fixtures import build_fixture


class EditorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='local-tag-editor-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        build_fixture(self.root / 'labels')
        self.labels = ReadOnlyLabels(self.root / 'labels', self.root / 'manual/overrides.jsonl')
        self.editor = LocalTagEditor(self.labels)
        self.before = hashes(self.labels.root)
        self.key = self.labels.views()[0]['problem_key']
        self.initial = self.editor.detail(self.key)
        self.ids = [t['id'] for t in self.initial['effective_tags']]
        self.extra = next(t for t in TAG_BY_ID if t not in self.ids)
        self.addCleanup(lambda: self.assertEqual(self.before, hashes(self.labels.root)))

    def payload(self, tags=None, operation='save', **changes):
        return {'operation': operation, 'tag_ids': self.ids + [self.extra] if tags is None else tags,
                'revision': self.editor.detail(self.key)['revision'], 'reason': '离线验收模拟修正',
                'request_id': uuid4().hex, **changes}

    def change(self, tags=None, operation='save'):
        return self.editor.change(self.key, self.payload(tags, operation), 'forum_admin:fixture')

    def test_batch_add_remove_one_atomic_history_event(self):
        self.change([self.extra])
        view = self.editor.detail(self.key)
        self.assertEqual([t['id'] for t in view['effective_tags']], [self.extra])
        self.assertEqual(len(view['history']), 1)
        self.assertEqual(view['review_status'], 'corrected')
        self.assertFalse(view['fully_human_verified'])

    def test_empty_tags_allowed(self):
        self.change([])
        self.assertEqual(self.editor.detail(self.key)['effective_tags'], [])

    def test_duplicate_request_is_not_recorded_twice(self):
        payload = self.payload()
        first = self.editor.change(self.key, payload, 'forum_admin:fixture')
        again = self.editor.change(self.key, payload, 'forum_admin:fixture')
        self.assertTrue(again['replayed'])
        self.assertEqual(first['event_id'], again['event_id'])
        self.assertEqual(len(self.editor.detail(self.key)['history']), 1)

    def test_request_id_cannot_be_reused_with_different_content(self):
        payload = self.payload()
        self.editor.change(self.key, payload, 'forum_admin:fixture')
        with self.assertRaises(EditConflict):
            self.editor.change(self.key, {**payload, 'reason': '不同的原因'}, 'forum_admin:fixture')

    def test_stale_version_rejected(self):
        stale = self.payload()
        self.change([self.extra])
        with self.assertRaises(EditConflict):
            self.editor.change(self.key, stale, 'forum_admin:second')

    def test_invalid_and_duplicate_tags_rejected(self):
        for tags in [['not_a_tag'], [self.extra, self.extra], ['<script>alert(1)</script>']]:
            with self.subTest(tags=tags), self.assertRaises(ValueError): self.change(tags)

    def test_chinese_tag_names_accepted(self):
        self.change([TAG_BY_ID[self.extra]['name_zh']])
        self.assertEqual(self.editor.detail(self.key)['effective_tags'][0]['id'], self.extra)

    def test_reason_required(self):
        with self.assertRaises(ValueError):
            self.editor.change(self.key, self.payload(reason=''), 'fixture')

    def test_undo_preserves_history(self):
        self.change([self.extra]); self.change([], 'undo')
        view = self.editor.detail(self.key)
        self.assertEqual([t['id'] for t in view['effective_tags']], self.ids)
        self.assertEqual(len(view['history']), 2)

    def test_reset_preserves_history(self):
        self.change([self.extra]); self.change([], 'reset')
        view = self.editor.detail(self.key)
        self.assertEqual([t['id'] for t in view['effective_tags']], self.ids)
        self.assertEqual(len(view['history']), 2)

    def test_verify_is_explicit_and_changes_invalidate_it(self):
        self.change([], 'verify')
        self.assertTrue(self.editor.detail(self.key)['fully_human_verified'])
        self.change([self.extra])
        self.assertFalse(self.editor.detail(self.key)['fully_human_verified'])

    def test_restart_reloads_overlay(self):
        self.change([self.extra])
        again = ReadOnlyLabels(self.labels.root, self.labels.override_file)
        self.assertEqual(LocalTagEditor(again).detail(self.key)['effective_tags'][0]['id'], self.extra)

    def test_unrelated_problems_are_unchanged(self):
        before = {p['problem_key']: p for p in self.labels.views() if p['problem_key'] != self.key}
        self.change([self.extra])
        self.assertEqual(before, {p['problem_key']: p for p in self.labels.views() if p['problem_key'] != self.key})

    def test_effective_query_reflects_edits_but_auto_tags_do_not_change(self):
        self.change([self.extra])
        row = next(p for p in self.labels.views() if p['problem_key'] == self.key)
        self.assertEqual([t['id'] for t in row['auto_tags']], self.ids)
        self.assertEqual([t['id'] for t in row['effective_tags']], [self.extra])

    def test_deleted_manual_addition_leaves_tombstone(self):
        self.change(self.ids + [self.extra]); self.change(self.ids)
        view = self.editor.detail(self.key)
        self.assertIn(self.extra, view['manual_overrides']['removed_tag_ids'])
        self.assertNotIn(self.extra, view['manual_overrides']['added_tag_ids'])

    def test_same_effective_set_is_a_noop(self):
        result = self.change(self.ids)
        self.assertFalse(result['changed'])
        self.assertFalse(self.labels.override_file.exists())

    def test_audit_contains_actor_reason_and_no_raw_request(self):
        self.change([self.extra])
        event = self.editor.detail(self.key)['history'][0]
        self.assertEqual(event['actor'], 'forum_admin:fixture')
        self.assertEqual(event['reason'], '离线验收模拟修正')
        self.assertNotIn('automatic_snapshot', event)


class TagAPITests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='local-tag-api-')
        self.root = Path(self.temp.name)
        build_fixture(self.root / 'labels')
        self.labels = ReadOnlyLabels(self.root / 'labels', self.root / 'manual/overrides.jsonl')
        self.env = patch.dict('os.environ'); self.env.start()
        isolate_environment(self.root / 'local.sqlite3')
        await initialize_database(self.root / 'local.sqlite3', self.labels)
        self.app = create_local_app(self.labels); self.client = self.app.test_client()
        self.row = self.labels.views()[0]
        self.path = '/api/secondary/tag-management/' + self.row['platform'] + '/' + self.row['problem_id']
        self.before = hashes(self.labels.root)

    async def asyncTearDown(self):
        self.assertEqual(self.before, hashes(self.labels.root))
        self.env.stop(); self.temp.cleanup()

    async def login(self, admin=True):
        r = await self.client.post('/api/auth/login', json={
            'qq_id': ADMIN_QQ if admin else DEMO_QQ, 'password': ADMIN_PASSWORD if admin else DEMO_PASSWORD})
        self.assertEqual(r.status_code, 200)
        self.csrf = (await r.get_json())['csrf_token']

    async def body(self):
        data = await (await self.client.get(self.path)).get_json()
        return {'operation': 'save', 'tag_ids': [], 'reason': '离线接口测试',
                'revision': data['revision'], 'request_id': uuid4().hex}

    async def test_anonymous_cannot_read_or_edit(self):
        self.assertEqual((await self.client.get(self.path)).status_code, 401)
        self.assertEqual((await self.client.post(self.path, json={})).status_code, 401)

    async def test_member_cannot_manage(self):
        await self.login(False)
        self.assertEqual((await self.client.get('/api/secondary/tag-management')).status_code, 403)
        self.assertEqual((await self.client.post(self.path, json={}, headers={'X-CSRF-Token': self.csrf})).status_code, 403)

    async def test_csrf_required(self):
        await self.login()
        self.assertEqual((await self.client.post(self.path, json=await self.body())).status_code, 403)

    async def test_cross_origin_and_cross_site_rejected(self):
        await self.login()
        for headers in [{'Origin': 'https://example.org'}, {'Sec-Fetch-Site': 'cross-site'}]:
            r = await self.client.post(self.path, json=await self.body(), headers={'X-CSRF-Token': self.csrf, **headers})
            self.assertEqual(r.status_code, 403)

    async def test_atomic_save_reflects_in_member_projection(self):
        await self.login()
        r = await self.client.post(self.path, json=await self.body(), headers={'X-CSRF-Token': self.csrf})
        self.assertEqual(r.status_code, 200)
        self.assertEqual((await r.get_json())['detail']['effective_tags'], [])
        member_path = '/api/secondary/problems/' + self.row['platform'] + '/' + self.row['problem_id']
        view = await (await self.client.get(member_path)).get_json()
        self.assertEqual(view['effective_tags'], [])
        self.assertEqual(view['manual_history_count'], 1)

    async def test_catalog_only_uses_v03_tags(self):
        await self.login()
        data = await (await self.client.get('/api/secondary/tag-management')).get_json()
        self.assertEqual(len(data['items']), 10)
        self.assertEqual(len(data['taxonomy']), 115)
        self.assertEqual(data['real_api_calls'], 0)

    async def test_export_retains_complete_journal(self):
        await self.login()
        await self.client.post(self.path, json=await self.body(), headers={'X-CSRF-Token': self.csrf})
        response = await self.client.get('/api/secondary/tag-management/export')
        self.assertEqual(response.status_code, 200)
        event = json.loads(await response.get_data(as_text=True))
        self.assertEqual(event['problem_key'], self.row['problem_key'])
        self.assertEqual(event['actor'], 'forum_admin:' + ADMIN_QQ)
        self.assertIn('automatic_snapshot', event)
        self.assertIn('attachment;', response.headers['Content-Disposition'])
        self.assertNotIn('original_statement', event['automatic_snapshot'])

    async def test_optimistic_conflict_is_409(self):
        await self.login(); body = await self.body()
        self.assertEqual((await self.client.post(self.path, json=body, headers={'X-CSRF-Token': self.csrf})).status_code, 200)
        body['request_id'] = uuid4().hex; body['reason'] = '另一个管理员'
        self.assertEqual((await self.client.post(self.path, json=body, headers={'X-CSRF-Token': self.csrf})).status_code, 409)

    async def test_other_write_and_ai_routes_still_blocked(self):
        await self.login()
        for path in ['/api/problems/sync', '/internal/v1/execute', '/api/me/problems/atcoder/a/state']:
            self.assertEqual((await self.client.post(path, json={}, headers={'X-CSRF-Token': self.csrf})).status_code, 403)

    async def test_unknown_problem_is_404(self):
        await self.login()
        self.assertEqual((await self.client.get('/api/secondary/tag-management/atcoder/missing')).status_code, 404)


if __name__ == '__main__':
    unittest.main()
