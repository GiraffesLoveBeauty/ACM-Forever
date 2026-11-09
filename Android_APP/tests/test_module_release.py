"""Offline optional-artifact publication tests; never create a remote release."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from create_module_assets import validate_catalog, filename
from test_tag_release import FakeGitHub, release


class ModuleReleaseTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.github = FakeGitHub()
        self.version, self.code, self.tag = '0.2.25', 39, 'v0.2.25'
        self.name = 'acmforever-0.2.25-debug.apk'
        prefix = f'https://github.com/{self.github.repository}/releases/download/{self.tag}/'
        apk = b'base fixture'
        self.manifest = dict(packageName=release.PACKAGE, versionCode=self.code, versionName=self.version,
                             minSdk=26, apkUrl=prefix+self.name, sha256=hashlib.sha256(apk).hexdigest(),
                             sizeBytes=len(apk), notes='optional modules', channel='debug',
                             signingCertificateSha256='a'*64, modulesUrl=prefix+'modules.json')
        (self.folder/self.name).write_bytes(apk)
        (self.folder/(self.name+'.sha256')).write_text(self.manifest['sha256']+'  '+self.name+'\n')
        rows = []
        for module in ('official-themes', 'advanced', 'admin', 'cat-art'):
            payload = (module+' fixture').encode()
            (self.folder/filename(module)).write_bytes(payload)
            rows.append(dict(id=module, kind='native' if module in ('advanced', 'admin') else 'assets',
                             url=prefix+filename(module), sizeBytes=len(payload), sha256=hashlib.sha256(payload).hexdigest()))
        self.catalog = dict(schemaVersion=1, versionCode=self.code, versionName=self.version, modules=rows)
        self.save()

    def save(self):
        (self.folder/'modules.json').write_text(json.dumps(self.catalog))
        (self.folder/'update.json').write_text(json.dumps(self.manifest))

    def publish(self):
        return release.publish(self.github, self.tag, self.folder, 'a'*40)

    def test_complete_release_reads_back_all_eight_assets(self):
        self.publish()
        self.assertFalse(self.github.release(self.tag)['draft'])
        self.assertEqual(len(self.github.release(self.tag)['assets']), 8)
        self.assertIn('download:module-admin.apk', self.github.operations)
        self.assertEqual(self.github.operations[-1], 'publish')

    def test_corrupt_module_readback_stays_draft(self):
        self.github.corrupt = 'module-cat-art.acmpack'
        with self.assertRaises(ValueError): self.publish()
        self.assertTrue(self.github.release(self.tag)['draft'])
        self.assertNotIn('publish', self.github.operations)

    def test_new_modular_release_cannot_omit_catalog(self):
        del self.manifest['modulesUrl']
        self.save()
        with self.assertRaises(ValueError): self.publish()
        self.assertEqual(self.github.operations, [])

    def test_missing_changed_and_wrong_version_block_before_upload(self):
        for change in ('bytes', 'version', 'url', 'duplicate', 'kind'):
            with self.subTest(change=change):
                original = copy.deepcopy(self.catalog)
                if change == 'bytes': self.catalog['modules'][0]['sha256'] = '0'*64
                if change == 'version': self.catalog['versionCode'] += 1
                if change == 'url': self.catalog['modules'][0]['url'] = 'https://elsewhere.invalid/a'
                if change == 'duplicate': self.catalog['modules'][1] = self.catalog['modules'][0]
                if change == 'kind': self.catalog['modules'][0]['kind'] = 'native'
                self.save()
                with self.assertRaises(ValueError): self.publish()
                self.assertEqual(self.github.operations, [])
                self.catalog = original

    def test_published_modules_are_immutable(self):
        self.publish()
        self.assertIn('Already published', self.publish())
        (self.folder/'module-admin.apk').write_bytes(b'changed')
        self.catalog['modules'][2].update(sizeBytes=7, sha256=hashlib.sha256(b'changed').hexdigest())
        self.save()
        with self.assertRaises(ValueError): self.publish()

    def test_catalog_strict_size_url_and_identity(self):
        validate_catalog(self.catalog, self.version, self.code, self.github.repository)
        for value in (0, -1, 16*1024*1024+1, 1.5, True, '100'):
            changed = copy.deepcopy(self.catalog)
            changed['modules'][0]['sizeBytes'] = value
            with self.assertRaises(ValueError): validate_catalog(changed, self.version, self.code, self.github.repository)


if __name__ == '__main__': unittest.main()
