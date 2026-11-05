"""Back up the actual website overlay using synthetic problems and isolated files only."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

from server import ReadOnlyLabels
from tag_editor import LocalTagEditor
import backup_labels
from annotation_api.adapter import digest
from annotation_api.storage import atomic_json
from label_pipeline import TAXONOMY
from problem_processing import backup
from problem_processing.adapter import normalize
from problem_processing.repository import Repository


class WebsiteManualBackupTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='web-manual-backup-')
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.root = self.base/'labels'
        self.repo = Repository(self.root)
        self.key = 'atcoder:offline:offline_a'
        self.problem = normalize({'problem_key': self.key, 'platform': 'atcoder',
            'contest_id': 'offline', 'problem_id': 'offline_a', 'title': 'Synthetic backup example',
            'statement_markdown': 'Synthetic only. Print the sum of two positive integers.'})
        self.auto = {'problem_key': self.key, 'platform': 'atcoder',
            'content_hash': self.problem['content_hash'], 'taxonomy_version': TAXONOMY['version'],
            'specific_tag_ids': ['enumeration', 'simulation'], 'provisional_tag_ids': [],
            'api_call_status': 'success', 'model': 'offline-fixture'}
        self.repo.import_records([self.problem], [self.auto])
        self.labels = ReadOnlyLabels(self.root)
        self.editor = LocalTagEditor(self.labels)
        self.destination = self.base/'backups'
        network = patch('socket.socket.connect', side_effect=AssertionError('NO NETWORK'))
        network.start()
        self.addCleanup(network.stop)

    def change(self, tags=(), operation='save'):
        return self.editor.change(self.key, {'operation': operation, 'tag_ids': list(tags),
            'reason': '离线备份回归测试', 'revision': self.editor.detail(self.key)['revision'],
            'request_id': uuid4().hex}, 'forum_admin:synthetic')

    def create(self, **kwargs):
        return Path(backup.create_backup(self.root, self.destination, **kwargs)['backup'])

    def restore(self, folder, **kwargs):
        result = backup.restore_backup(folder, self.base/'restored', active_root=self.root, **kwargs)
        return result, ReadOnlyLabels(result['restored_data_root'])

    def test_default_website_history_and_effective_view_round_trip(self):
        self.change(['prefix_sum'])
        expected = self.labels.views()
        history = self.labels.override_file.read_bytes()
        original = backup.inventory(self.root)
        folder = self.create()
        report = backup.verify_backup(folder)
        self.assertTrue(report['web_manual_verified'])
        self.assertEqual(report['web_manual']['source'], 'local_tag_management')
        self.assertEqual(report['web_manual']['manual_events'], 1)
        views = self.labels.manager().get_effective_tags_many([self.key])
        self.assertEqual(report['web_manual']['effective_view_sha256'], digest(views))
        result, restored = self.restore(folder)
        self.assertEqual(Path(result['restored_override_file']), restored.override_file)
        self.assertEqual(restored.override_file.read_bytes(), history)
        self.assertEqual(restored.views(), expected)
        self.assertEqual(LocalTagEditor(restored).detail(self.key), self.editor.detail(self.key))
        self.assertEqual(backup.inventory(self.root), original)
        self.assertEqual(self.labels.override_file.read_bytes(), history)
        self.assertEqual(result['api_calls'], 0)

    def test_deleted_automatic_tags_stay_deleted(self):
        self.change([])
        _, restored = self.restore(self.create())
        self.assertEqual(restored.views()[0]['effective_tags'], [])
        self.assertEqual(restored.views()[0]['manual_removed_ids'], ['enumeration', 'simulation'])
        self.assertEqual(len(restored.views()[0]['auto_tags']), 2)

    def test_undo_and_verification_history_are_preserved(self):
        self.change(['prefix_sum'])
        self.change(operation='undo')
        self.change(operation='verify')
        _, restored = self.restore(self.create())
        self.assertEqual(restored.views(), self.labels.views())
        self.assertEqual(restored.views()[0]['manual_history_count'], 3)
        self.assertTrue(restored.views()[0]['fully_human_verified'])
        self.assertEqual(LocalTagEditor(restored).detail(self.key)['history'], self.editor.detail(self.key)['history'])

    def test_both_internal_and_website_histories_are_retained_separately(self):
        self.repo.manager().change(self.key, 'remove', ['enumeration'])
        self.change(['prefix_sum'])
        internal = (self.root/'manual/overrides.jsonl').read_bytes()
        external = self.labels.override_file.read_bytes()
        result, restored = self.restore(self.create())
        self.assertEqual((Path(result['restored_data_root'])/'manual/overrides.jsonl').read_bytes(), internal)
        self.assertEqual(restored.override_file.read_bytes(), external)
        self.assertEqual(restored.views(), self.labels.views())
        self.assertNotEqual(restored.repo.manager().get_effective_tags(self.key)['effective_tags'], restored.views()[0]['effective_tags'])

    def test_existing_empty_website_file_overrides_internal_history(self):
        self.repo.manager().change(self.key, 'remove', ['enumeration'])
        self.labels.override_file.parent.mkdir(parents=True)
        self.labels.override_file.write_bytes(b'')
        result, restored = self.restore(self.create())
        self.assertEqual(result['web_manual']['source'], 'local_tag_management')
        self.assertEqual(restored.override_file.read_bytes(), b'')
        self.assertEqual(restored.views(), self.labels.views())
        self.assertEqual(len(restored.views()[0]['effective_tags']), 2)

    def test_absent_website_file_keeps_internal_fallback(self):
        self.repo.manager().change(self.key, 'remove', ['enumeration'])
        result, restored = self.restore(self.create())
        self.assertIsNone(result['restored_override_file'])
        self.assertEqual(result['web_manual']['source'], 'label_manual')
        self.assertEqual(restored.views(), self.labels.views())

    def test_custom_history_path_and_cli_round_trip(self):
        custom = self.base/'custom-admin/history.jsonl'
        self.labels = ReadOnlyLabels(self.root, custom)
        self.editor = LocalTagEditor(self.labels)
        self.change(['prefix_sum'])
        with redirect_stdout(io.StringIO()) as output:
            code = backup_labels.main(['create', '--data-root', str(self.root), '--backup-root', str(self.destination),
                                       '--override-file', str(custom), '--no-annotation-requests'])
        self.assertEqual(code, 0)
        folder = Path(json.loads(output.getvalue())['backup'])
        _, restored = self.restore(folder)
        self.assertEqual(restored.override_file.read_bytes(), custom.read_bytes())
        self.assertEqual(restored.views(), self.labels.views())

    def test_explicit_missing_history_fails_instead_of_silently_omitting_it(self):
        with self.assertRaisesRegex(ValueError, '不存在'):
            self.create(override_file=self.base/'missing.jsonl')
        self.assertFalse(self.destination.exists())

    def test_missing_or_corrupt_archived_website_history_blocks_restore(self):
        self.change([])
        folder = self.create()
        path = folder/backup.WEB_OVERRIDES
        original = path.read_bytes()
        for content in (None, b'{}'):
            if content is None:
                path.unlink()
            else:
                path.write_bytes(content)
            with self.assertRaises(ValueError):
                self.restore(folder)
            self.assertFalse((self.base/'restored').exists())
        path.write_bytes(original)

    def test_rehashed_history_with_different_effective_view_is_rejected(self):
        self.change([])
        folder = self.create()
        path = folder/backup.WEB_OVERRIDES
        event = backup.rows(path.read_bytes())[0]
        event['after']['removed_tag_ids'] = []
        path.write_text(json.dumps(event, ensure_ascii=False)+'\n', encoding='utf-8')
        manifest = backup.parse((folder/'manifest.json').read_bytes())
        for entry in manifest['files']:
            if entry['path'] == backup.WEB_OVERRIDES:
                manifest['total_bytes'] += path.stat().st_size - entry['bytes']
                entry.update(bytes=path.stat().st_size, sha256=backup.sha256(path.read_bytes()))
        atomic_json(folder/'manifest.json', manifest)
        with self.assertRaisesRegex(ValueError, '网页人工历史或有效标签摘要'):
            self.restore(folder)
        self.assertFalse((self.base/'restored').exists())

    def test_incompatible_event_chain_and_unknown_problem_are_rejected(self):
        self.change([])
        original = self.labels.override_file.read_bytes()
        for change in ('chain', 'identity'):
            event = backup.rows(original)[0]
            if change == 'chain':
                event['previous_event_id'] = 'missing-event'
            else:
                event['problem_key'] = event['automatic_snapshot']['problem_key'] = 'atcoder:other:other_a'
            self.labels.override_file.write_text(json.dumps(event, ensure_ascii=False)+'\n', encoding='utf-8')
            with self.assertRaises(ValueError):
                self.create()
        self.assertFalse(self.destination.exists())

    def test_sensitive_external_history_is_rejected_without_disclosure(self):
        self.change([])
        event = backup.rows(self.labels.override_file.read_bytes())[0]
        event['details']['authorization'] = 'synthetic-private-value'
        self.labels.override_file.write_text(json.dumps(event, ensure_ascii=False)+'\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '敏感') as raised:
            self.create()
        self.assertNotIn('synthetic-private-value', str(raised.exception))
        self.assertFalse(self.destination.exists())

    def test_concurrent_external_history_change_prevents_success(self):
        self.change([])
        inventory = backup.inventory
        reads = 0
        def changing(path):
            nonlocal reads
            if Path(path) == self.root:
                reads += 1
                if reads == 2:
                    history = self.labels.override_file
                    history.write_bytes(history.read_bytes()+b'\n')
            return inventory(path)
        with patch.object(backup, 'inventory', changing), self.assertRaisesRegex(ValueError, '数据变化'):
            self.create()
        self.assertFalse(self.destination.exists())

    def test_external_reparse_point_is_rejected(self):
        self.change([])
        lstat = Path.lstat
        def reparse(path, *args, **kwargs):
            if path == self.labels.override_file:
                return SimpleNamespace(st_mode=stat.S_IFREG, st_file_attributes=1024)
            return lstat(path, *args, **kwargs)
        with patch.object(Path, 'lstat', reparse), self.assertRaisesRegex(ValueError, '重解析点'):
            self.create()

    def test_active_custom_history_is_protected_from_restore(self):
        self.change([])
        folder = self.create()
        with self.assertRaisesRegex(ValueError, '活动网页人工历史'):
            backup.restore_backup(folder, self.labels.override_file.parent/'new-restore', active_root=self.root,
                                  active_override_file=self.labels.override_file)

    def test_legacy_backup_explicitly_reports_web_history_unknown(self):
        folder = self.create()
        manifest = backup.parse((folder/'manifest.json').read_bytes())
        manifest['backup_version'] = 1
        del manifest['web_manual']
        atomic_json(folder/'manifest.json', manifest)
        report = backup.verify_backup(folder)
        self.assertTrue(report['verified'])
        self.assertFalse(report['web_manual_verified'])
        self.assertTrue(report['warnings'])
        result, _ = self.restore(folder)
        self.assertFalse(result['web_manual_verified'])
        self.assertTrue(result['warnings'])

    def test_historical_generation_keeps_external_tombstones(self):
        generation = self.repo.current().name
        self.change([])
        changed = normalize({'problem_key': self.key, 'platform': 'atcoder',
            'contest_id': 'offline', 'problem_id': 'offline_a', 'title': self.problem['original_title'],
            'statement_markdown': 'Changed synthetic problem content.'})
        annotation = dict(self.auto, content_hash=changed['content_hash'])
        self.repo.import_records([changed], [annotation])
        self.assertEqual(self.labels.views()[0]['review_status'], 'needs_review')
        _, restored = self.restore(self.create(), generation=generation)
        self.assertEqual(restored.views()[0]['effective_tags'], [])
        self.assertEqual(restored.views()[0]['manual_history_count'], 1)
        self.assertEqual(restored.views()[0]['review_status'], 'corrected')


if __name__ == '__main__':
    unittest.main()
