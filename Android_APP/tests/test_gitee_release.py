"""Gitee mirror transaction tests use only in-memory fixtures and never upload."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import gitee_release as mirror
import test_module_release as module_test


class FakeGitee:
    def __init__(self):
        self.current = None
        self.assets = {}
        self.operations = []
        self.corrupt = None
        self.latest = None
        self.private = False
        self.forbid_tag = False

    def api(self, method, suffix, data=None, missing=False, multipart=None):
        if method == 'GET' and suffix == '':
            return dict(private=self.private, full_name=mirror.GITEE_REPOSITORY)
        if method == 'GET' and suffix == '/releases/latest': return self.latest
        if method == 'POST' and suffix == '/releases':
            self.operations.append('create-prerelease')
            assert data['prerelease'] is True
            self.current = dict(data, id=123)
            return self.current
        if method == 'POST' and suffix.endswith('/attach_files'):
            self.operations.append('upload:' + multipart.name)
            self.assets[multipart.name] = multipart.read_bytes()
            return dict(name=multipart.name, id=len(self.assets))
        if method == 'PATCH':
            required = ('tag_name', 'name', 'body')
            if any(not isinstance((data or {}).get(k), str) or not data[k] for k in required):
                raise ValueError('Missing required Gitee PATCH fields')
            if any(data[k] != self.current[k] for k in required):
                raise ValueError('Publishing must preserve release identity and notes')
            self.operations.append('publish')
            self.current.update(data)
            return self.current
        raise AssertionError((method, suffix))

    def ensure_tag(self, tag, commit):
        if self.forbid_tag: raise ValueError('tag conflict')
        self.operations.append('verify-tag')

    def release(self, tag): return self.current
    def files(self, rid): return [dict(name=n, id=i+1) for i,n in enumerate(self.assets)]
    def formal_releases(self): return [] if self.latest is None else [self.latest]
    def readback(self, tag, name, size, expected_hash):
        self.operations.append('read:' + name)
        data = self.assets[name] + (b'corrupt' if name == self.corrupt else b'')
        if len(data) != size or hashlib.sha256(data).hexdigest() != expected_hash:
            raise ValueError('readback mismatch')


class GiteeReleaseTest(unittest.TestCase):
    def setUp(self):
        self.fixture = module_test.ModuleReleaseTest('test_complete_release_reads_back_all_eight_assets')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.directory = self.fixture.folder
        self.client = FakeGitee()
        self.tag = self.fixture.tag
        self.commit = 'a'*40

    def publish(self):
        return mirror.publish(self.client, self.directory, self.tag, self.commit)

    def test_all_eight_assets_verified_before_publication(self):
        self.assertIn('Verified all eight', self.publish())
        self.assertFalse(self.client.current['prerelease'])
        self.assertEqual(8, len(self.client.assets))
        self.assertEqual('publish', self.client.operations[-1])
        self.assertEqual(8, len([op for op in self.client.operations if op.startswith('read:')]))

    def test_patch_requires_fields_and_keeps_existing_title_and_notes(self):
        self.client.corrupt = 'update.json'
        with self.assertRaises(ValueError): self.publish()
        self.client.current.update(name='Existing custom title', body='Custom notes\n\nSource commit: `' + self.commit + '`')
        self.client.corrupt = None
        self.publish()
        self.assertEqual('Existing custom title', self.client.current['name'])
        self.assertTrue(self.client.current['body'].startswith('Custom notes'))
        self.assertFalse(self.client.current['prerelease'])

    def test_json_urls_change_but_signed_payload_bytes_and_hashes_do_not(self):
        for row in self.fixture.catalog["modules"]:
            row["revision"] = ("n1-" if row["kind"] == "native" else "a1-") + "a"*64
        self.fixture.save()
        self.publish()
        manifest = json.loads(self.client.assets['update.json'])
        catalog = json.loads(self.client.assets['modules.json'])
        self.assertTrue(manifest['apkUrl'].startswith(mirror.ORIGIN))
        self.assertTrue(manifest['modulesUrl'].startswith(mirror.ORIGIN))
        for field in ('sha256', 'sizeBytes', 'versionCode', 'channel', 'signingCertificateSha256'):
            self.assertEqual(self.fixture.manifest[field], manifest[field])
        for name,data in self.client.assets.items():
            if name not in ('update.json', 'modules.json'): self.assertEqual((self.directory/name).read_bytes(),data)
        for before,after in zip(self.fixture.catalog['modules'],catalog['modules']):
            self.assertTrue(after['url'].startswith(mirror.ORIGIN))
            self.assertEqual({k:v for k,v in before.items() if k!='url'},{k:v for k,v in after.items() if k!='url'})

    def test_corrupt_readback_keeps_prerelease_and_resume_uploads_only_missing(self):
        self.client.corrupt = 'module-cat-art.acmpack'
        with self.assertRaises(ValueError): self.publish()
        self.assertTrue(self.client.current['prerelease'])
        self.assertNotIn('publish', self.client.operations)
        previous = set(self.client.assets)
        self.client.corrupt = None
        self.client.operations.clear()
        self.publish()
        self.assertFalse(self.client.current['prerelease'])
        for name in previous: self.assertNotIn('upload:'+name,self.client.operations)

    def test_complete_published_release_is_immutable_and_identical_rerun_noop(self):
        self.publish()
        self.client.operations.clear()
        self.publish()
        self.assertFalse(any(op.startswith('upload:') or op=='publish' for op in self.client.operations))
        self.client.assets['module-admin.apk'] = b'bad'
        with self.assertRaises(ValueError): self.publish()

    def test_missing_published_asset_is_not_replaced(self):
        self.publish()
        del self.client.assets['modules.json']
        self.client.operations.clear()
        with self.assertRaises(ValueError): self.publish()
        self.assertNotIn('upload:modules.json',self.client.operations)

    def test_private_repository_and_changed_tag_block_before_upload(self):
        self.client.private=True
        with self.assertRaises(ValueError): self.publish()
        self.assertEqual([],self.client.operations)
        self.client.private=False;self.client.forbid_tag=True
        with self.assertRaises(ValueError): self.publish()
        self.assertEqual({},self.client.assets)

    def test_newer_or_unknown_gitee_release_prevents_rollback(self):
        for tag in ('v0.2.99','other'):
            self.client.latest=dict(tag_name=tag)
            with self.assertRaises(ValueError): self.publish()
            self.assertEqual({},self.client.assets)

    def test_wrong_manifest_corrupt_bytes_or_incomplete_modules_fail_before_network(self):
        self.fixture.manifest['apkUrl']='https://other.invalid/file.apk';self.fixture.save()
        with self.assertRaises(ValueError): self.publish()
        self.assertEqual([],self.client.operations)
        self.fixture.manifest['apkUrl']='https://github.com/'+mirror.GITHUB_REPOSITORY+'/releases/download/'+self.tag+'/'+self.fixture.name
        self.fixture.catalog['modules'].pop();self.fixture.save()
        with self.assertRaises(ValueError): self.publish()
        self.assertEqual([],self.client.operations)

    def test_unexpected_duplicate_or_modified_metadata_fail_closed(self):
        self.publish()
        self.client.assets['unexpected.apk']=b'x'
        with self.assertRaises(ValueError): self.publish()
        del self.client.assets['unexpected.apk']
        self.client.current['body']='different commit'
        with self.assertRaises(ValueError): self.publish()

    def test_untrusted_redirects_and_missing_credentials_are_rejected(self):
        for url in ('http://gitee.com/a','https://user:secret@gitee.com/a','https://gitee.com.evil.invalid/a','https://evil.invalid/a','https://foruda.gitee.com:8443/a','https://gitee.com/a#x'):
            with self.assertRaises(ValueError):mirror.check_public_url(url)
        for url in ('https://gitee.com/a','https://foruda.gitee.com/attach_file/a?token=ephemeral&ts=1','https://files.gitee.com/a'):
            mirror.check_public_url(url)
        with self.assertRaises(ValueError):mirror.Gitee('')

    def test_action_guard_refuses_local_publication(self):
        with patch.dict('os.environ',{},clear=True),patch('sys.argv',['gitee_release.py','--tag',self.tag,'--directory',str(self.directory),'--source-commit',self.commit]),patch.object(mirror,'publish') as publish:
            with self.assertRaises(SystemExit):mirror.main()
            publish.assert_not_called()


if __name__ == '__main__': unittest.main()
