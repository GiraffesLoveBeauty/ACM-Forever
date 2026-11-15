"""Exercise mirror recovery using published bytes, including two real signed ZIP builds."""
import copy
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import test_gitee_release as fixtures
import create_module_assets as modules
import gitee_release as mirror


class GiteeRecoveryTest(unittest.TestCase):
    def setUp(self):
        self.case = fixtures.GiteeReleaseTest('test_all_eight_assets_verified_before_publication')
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.fixture = self.case.fixture
        self.github = self.fixture.github
        self.destination = self.fixture.folder / 'restored'

    def restore(self, **changes):
        args = dict(github=self.github, directory=self.destination, tag=self.fixture.tag,
                    source_commit=self.case.commit, version=self.fixture.version, code=self.fixture.code,
                    channel='debug', certificate='a'*64)
        args.update(changes)
        return mirror.restore_github(**args)

    def test_unpublished_or_draft_release_uses_normal_build(self):
        self.assertFalse(self.restore())
        self.github.create(self.fixture.tag, 'Draft', self.fixture.folder/'update.json')
        self.assertFalse(self.restore())
        self.assertFalse(self.destination.exists())

    def test_restores_all_original_bytes_without_upload_or_republish(self):
        self.fixture.publish()
        before = [x for x in self.github.operations if not x.startswith('download:')]
        self.assertTrue(self.restore())
        self.assertEqual(8, len(list(self.destination.iterdir())))
        for p in self.destination.iterdir():
            self.assertEqual(self.github.files[(self.fixture.tag, p.name)], p.read_bytes())
        self.assertEqual(before, [x for x in self.github.operations if not x.startswith('download:')])

    def test_wrong_source_tag_channel_certificate_or_version_rejected(self):
        self.fixture.publish()
        current = self.github.release(self.fixture.tag)
        for fields in (dict(body='Source commit: `'+'b'*40+'`'), dict(prerelease=True), dict(tag_name='v0.2.24')):
            saved = copy.deepcopy(current)
            current.update(fields)
            with self.assertRaises(ValueError): self.restore()
            current.clear(); current.update(saved)
            self.assertFalse(self.destination.exists())
        with patch.object(self.github, 'tag_commit', return_value='b'*40):
            with self.assertRaises(ValueError): self.restore()
        for args in (dict(channel='release'), dict(certificate='b'*64), dict(code=self.fixture.code+1), dict(version='0.2.99')):
            with self.assertRaises(ValueError): self.restore(**args)
            self.assertFalse(self.destination.exists())
        self.github.private = True
        with self.assertRaises(ValueError): self.restore()

    def test_missing_extra_or_duplicate_asset_rejected(self):
        self.fixture.publish()
        current = self.github.release(self.fixture.tag)
        original = copy.deepcopy(current['assets'])
        for rows in (original[:-1], original+[dict(name='other.apk')], original+[original[0]]):
            current['assets'] = rows
            with self.assertRaises(ValueError): self.restore()
            self.assertFalse(self.destination.exists())

    def test_corrupt_download_is_not_accepted_or_written_to_output(self):
        self.fixture.publish()
        for name in ('update.json', self.fixture.name, self.fixture.name+'.sha256', 'modules.json', 'module-cat-art.acmpack'):
            self.github.corrupt = name
            with self.assertRaises((ValueError, OSError)): self.restore()
            self.assertFalse(self.destination.exists())

    def test_preexisting_rebuilt_files_are_preserved_and_rejected(self):
        self.fixture.publish()
        self.destination.mkdir()
        rebuilt = self.destination/'rebuilt.apk'
        rebuilt.write_bytes(b'leave intact')
        with self.assertRaises(ValueError): self.restore()
        self.assertEqual(b'leave intact', rebuilt.read_bytes())

    def test_cli_outputs_reuse_only_after_validated_restore_and_never_calls_gitee(self):
        gradle, history, output = [self.fixture.folder/n for n in ('build.gradle','history.json','github-output')]
        gradle.write_text("versionName '"+self.fixture.version+"'\nversionCode "+str(self.fixture.code))
        history.write_text(json.dumps(dict(schemaVersion=1,currentVersionCode=self.fixture.code,
                                         entries=[dict(versionName=self.fixture.version)])))
        argv = ['gitee_release.py','--restore-github','--tag',self.fixture.tag,'--directory',str(self.destination),
                '--source-commit',self.case.commit,'--channel','debug','--certificate','a'*64,
                '--gradle',str(gradle),'--history',str(history)]
        env = dict(GITHUB_ACTIONS='true',GITHUB_EVENT_NAME='push',GITHUB_REF='refs/tags/'+self.fixture.tag,
                   GITHUB_SHA=self.case.commit,GITHUB_REPOSITORY=mirror.GITHUB_REPOSITORY,GITHUB_OUTPUT=str(output))
        with patch.dict(os.environ,env,clear=True),patch('sys.argv',argv),patch.object(mirror,'GitHub',return_value=self.github), \
                patch.object(mirror,'Gitee') as gitee, contextlib.redirect_stdout(io.StringIO()):
            mirror.main()
            self.assertEqual('reused=false\n',output.read_text())
            self.fixture.publish()
            output.unlink()
            self.github.corrupt = 'module-cat-art.acmpack'
            with self.assertRaises(ValueError): mirror.main()
            self.assertFalse(output.exists())  # A corrupt public release never falls through to rebuilding.
            self.github.corrupt = None
            mirror.main()
            self.assertEqual('reused=true\n',output.read_text())
            gitee.assert_not_called()
            output.unlink()
            os.environ['GITHUB_REF'] = 'refs/heads/main'
            with contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit): mirror.main()
            self.assertFalse(output.exists())

    @unittest.skipUnless(shutil.which('keytool') and shutil.which('jarsigner'), 'JDK tools required for real signed packages')
    def test_two_real_signed_packages_recover_from_original_published_artifacts(self):
        key = self.fixture.folder/'fixture.jks'
        def run(*args):
            subprocess.run(args, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        run(shutil.which('keytool'), '-genkeypair', '-keystore', str(key), '-storepass', 'fixture-only',
            '-keypass', 'fixture-only', '-alias', 'fixture', '-keyalg', 'RSA', '-keysize', '2048',
            '-validity', '1', '-dname', 'CN=Offline test fixture')
        source = self.fixture.folder/'resources'
        (source/'payload').mkdir(parents=True)
        (source/'payload/art.txt').write_bytes(b'same source art for both actual builds')
        artifact = self.fixture.folder/'module-cat-art.acmpack'
        row = next(r for r in self.fixture.catalog['modules'] if r['id']=='cat-art')
        def package(day):
            # Distinct actual ZIP timestamps, no wall-clock sleep or random payload change.
            with patch('zipfile.time.localtime', return_value=(2026,1,day,0,0,0,0,1,-1)):
                modules.package_resources(source, artifact, 'cat-art', self.fixture.code)
            run(shutil.which('jarsigner'), '-keystore', str(key), '-storepass', 'fixture-only',
                '-keypass', 'fixture-only', '-digestalg', 'SHA-256', '-sigalg', 'SHA256withRSA', str(artifact), 'fixture')
            row.update(sizeBytes=artifact.stat().st_size, sha256=hashlib.sha256(artifact.read_bytes()).hexdigest())
            self.fixture.save()
            return artifact.read_bytes()
        first = package(1)
        self.fixture.publish()
        self.case.client.corrupt = artifact.name
        with self.assertRaises(ValueError): self.case.publish()
        self.assertTrue(self.case.client.current['prerelease'])
        previous = set(self.case.client.assets)
        second = package(2)
        self.assertNotEqual(first, second)
        with self.assertRaises(ValueError): self.fixture.publish()  # Immutable originals stay protected.
        self.assertTrue(self.restore())
        self.assertEqual(first, (self.destination/artifact.name).read_bytes())
        self.case.client.corrupt = None
        self.case.client.operations.clear()
        mirror.publish(self.case.client, self.destination, self.fixture.tag, self.case.commit)
        self.assertFalse(self.case.client.current['prerelease'])
        self.assertEqual(first, self.case.client.assets[artifact.name])
        for name in previous:
            self.assertNotIn('upload:'+name, self.case.client.operations)


if __name__ == '__main__': unittest.main()
