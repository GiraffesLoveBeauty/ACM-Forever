"""A public Release can never contain the privileged distribution."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from test_tag_release import FakeGitHub
from test_release_credits import apk_fixture

spec = importlib.util.spec_from_file_location("private_tag_release", Path(__file__).resolve().parents[1] / "tools/tag_release.py")
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class PrivateGitHub(FakeGitHub):
    def create_private(self, tag, commit, notes):
        self.operations.append("create-private")
        self.releases[tag] = {"tag_name": tag, "draft": True, "assets": []}


class PrivateReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.github = PrivateGitHub()
        self.name = "acmforever-1.0.0-preview.1.apk"
        payload = apk_fixture()
        self.manifest = dict(packageName=release.PACKAGE, versionName="1.0.0", versionCode=44,
            releaseVersionCode=45, previewRevision=1, previewTag="v1.0.0-preview.1",
            minSdk=26, schemaVersion=2, distribution="preview", sizeBytes=len(payload), notes="Test preview notes",
            sha256=hashlib.sha256(payload).hexdigest(), signingCertificateSha256="1" * 64,
            apkPath="/api/admin/android/releases/v1.0.0-preview.1/apk")
        old={**self.manifest,"versionName":"0.2.30","distribution":"release"}
        self.github.latest_tag="v0.2.30"
        self.github.releases["v0.2.30"]={"tag_name":"v0.2.30","draft":False,"assets":[{"name":"update.json"}]}
        self.github.files[("v0.2.30","update.json")]=json.dumps(old).encode()
        (self.directory / self.name).write_bytes(payload)
        (self.directory / (self.name + ".sha256")).write_text(self.manifest["sha256"] + "  " + self.name)
        tag=self.manifest['previewTag']
        self.manifest['modulesPath']=f'/api/admin/android/releases/{tag}/modules'
        rows=[]
        from create_module_assets import filename
        for module in ('official-themes','advanced','admin','cat-art'):
            data=(module+' synthetic').encode()
            (self.directory/filename(module)).write_bytes(data)
            native=module in ('advanced','admin')
            rows.append(dict(id=module,kind='native' if native else 'assets',sizeBytes=len(data),
                sha256=hashlib.sha256(data).hexdigest(),revision=('n1-' if native else 'a1-')+'f'*64,
                url=f'https://github.com/{self.github.repository}/releases/download/{tag}/{filename(module)}'))
        self.catalog=dict(schemaVersion=1,versionCode=44,versionName='1.0.0',previewTag=tag,modules=rows)
        (self.directory/'modules.json').write_text(json.dumps(self.catalog))
        self.save()

    def save(self):
        (self.directory / "update.json").write_text(json.dumps(self.manifest), encoding="utf-8")

    def stage(self):
        return release.stage_preview(self.github, "v1.0.0-preview.1", self.directory, "a" * 40)

    def test_complete_readback_without_publish_or_latest_change(self):
        self.assertIn("NOT published", self.stage())
        self.assertTrue(self.github.releases["v1.0.0-preview.1"]["draft"])
        self.assertNotIn("publish", self.github.operations)
        self.assertEqual("v0.2.30",self.github.latest_tag)
        self.assertEqual(9, len([o for o in self.github.operations if o.startswith("download:")]))
        self.assertEqual(8,len(self.github.releases['v1.0.0-preview.1']['assets']))

    def test_rerun_is_immutable_and_missing_module_never_uploads(self):
        self.stage()
        self.github.operations.clear()
        self.assertIn('NOT published',self.stage())
        self.assertNotIn('upload',self.github.operations)
        (self.directory/'module-admin.apk').unlink()
        self.github.operations.clear()
        with self.assertRaises((ValueError,FileNotFoundError)): self.stage()
        self.assertNotIn('upload',self.github.operations)

    def test_refuses_publication_through_formal_path(self):
        with self.assertRaises(ValueError): release.publish(self.github, "v1.0.0", self.directory, "a" * 40)
        self.assertFalse(self.github.operations)

    def test_refuses_wrong_package_or_exposed_asset_url(self):
        for key, value in (("packageName", release.PACKAGE+".admin"), ("distribution", "release"),
                           ("apkUrl", "https://github.com/public.apk"), ("apkPath", "/api/me/avatar")):
            old = copy.deepcopy(self.manifest)
            self.manifest[key] = value
            self.save()
            with self.subTest(key=key), self.assertRaises(ValueError): self.stage()
            self.manifest = old
        self.assertFalse(self.github.operations)

    def test_corrupt_readback_and_public_draft_are_rejected(self):
        self.github.corrupt = self.name
        with self.assertRaises(ValueError): self.stage()
        self.assertTrue(self.github.releases["v1.0.0-preview.1"]["draft"])
        self.github.releases["v1.0.0-preview.1"]["draft"] = False
        self.github.operations.clear()
        with self.assertRaises(ValueError): self.stage()
        self.assertNotIn("upload",self.github.operations)

    def test_preview_must_reuse_live_stable_code_and_signature(self):
        for key,value in (("versionCode",36),("signingCertificateSha256","2"*64),("releaseVersionCode",37)):
            old=copy.deepcopy(self.manifest);self.manifest[key]=value;self.save()
            with self.subTest(key=key),self.assertRaises(ValueError):self.stage()
            self.manifest=old

    def test_modern_formal_publication_has_only_formal_eight_assets(self):
        name='acmforever-1.0.0.apk'
        (self.directory/self.name).rename(self.directory/name)
        (self.directory/(self.name+'.sha256')).unlink()
        (self.directory/(name+'.sha256')).write_text(self.manifest['sha256']+'  '+name)
        self.manifest.update(distribution='release',versionCode=45,
            apkUrl=f'https://github.com/{self.github.repository}/releases/download/v1.0.0/{name}',
            modulesUrl=f'https://github.com/{self.github.repository}/releases/download/v1.0.0/modules.json')
        for key in ('previewRevision','previewTag','releaseVersionCode','apkPath','modulesPath'):self.manifest.pop(key,None)
        self.catalog.pop('previewTag');self.catalog['versionCode']=45
        for row in self.catalog['modules']:row['url']=row['url'].replace('/v1.0.0-preview.1/','/v1.0.0/')
        (self.directory/'modules.json').write_text(json.dumps(self.catalog));self.save()
        self.assertIn('Published',release.publish(self.github,'v1.0.0',self.directory,'a'*40))
        self.assertFalse(self.github.releases['v1.0.0']['draft'])
        self.assertEqual(8,len(self.github.releases['v1.0.0']['assets']))
        self.assertTrue(all('preview' not in a['name'] for a in self.github.releases['v1.0.0']['assets']))
