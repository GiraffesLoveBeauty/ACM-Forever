"""Real session/role boundary tests. Upstream release bytes are synthetic fixtures."""
import hashlib
import io
import json
import copy
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch, AsyncMock

from feat.api.app import create_app
from feat.api.acm_api.auth_service import hash_password
from feat.api.acm_api.database import connect_db
from feat.api.acm_api.android_release_api import validate_manifest, validate_catalog, ReleaseUnavailable, NoPreview, DraftReleases, CERTIFICATE, MAX_APK, MODULES


def fixture():
    return dict(schemaVersion=2, distribution="preview", packageName="com.giraffeslovebeauty.acmforever",
        versionCode=37, versionName="1.0.0", minSdk=26, notes="Synthetic preview release", releaseVersionCode=38,
        previewRevision=1, previewTag="v1.0.0-preview.1",
        apkPath="/api/admin/android/releases/v1.0.0-preview.1/apk", sizeBytes=7,
        sha256=hashlib.sha256(b"fixture").hexdigest(), signingCertificateSha256=CERTIFICATE)


def modular_fixture():
    value = fixture()
    value.update(versionCode=44, releaseVersionCode=45, modulesPath='/api/admin/android/releases/v1.0.0-preview.1/modules')
    prefix = 'https://github.com/GiraffesLoveBeauty/ACM-Forever/releases/download/v1.0.0-preview.1/'
    rows = [dict(id=key, kind='native' if key in ('advanced', 'admin') else 'assets',
        url=prefix+name, sizeBytes=7, sha256=hashlib.sha256(b'fixture').hexdigest(),
        revision=('n1-' if key in ('advanced', 'admin') else 'a1-')+'f'*64) for key, name in MODULES.items()]
    catalog = dict(schemaVersion=1, versionCode=44, versionName='1.0.0', previewTag='v1.0.0-preview.1', modules=rows)
    assets = [dict(id=1,name='update.json',state='uploaded'),
        dict(id=2,name='acmforever-1.0.0-preview.1.apk',size=7,state='uploaded'),
        dict(id=3,name='acmforever-1.0.0-preview.1.apk.sha256',state='uploaded'),
        dict(id=4,name='modules.json',state='uploaded')]
    assets += [dict(id=5+i,name=name,state='uploaded',size=7) for i,name in enumerate(MODULES.values())]
    return value,catalog,dict(tag_name='v1.0.0-preview.1',draft=True,assets=assets)


class AndroidReleaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "test.db"
        self.env = patch.dict(os.environ, {"ACM_DATABASE_PATH": str(self.db_path),
            "ACM_WEBUI_SECRET_KEY": "test-release-session", "ACM_ANDROID_GITHUB_TOKEN": ""})
        self.env.start()
        self.app = create_app()

    async def asyncTearDown(self):
        self.env.stop()
        self.temp.cleanup()

    async def login(self, client, role, change=0):
        db = await connect_db(self.db_path)
        try:
            now = int(time.time())
            await db.execute("INSERT INTO users(qq_id,name,status) VALUES('12345678','测试','现役')")
            await db.execute("INSERT INTO web_accounts(qq_id,password_hash,role,must_change_password,is_active,credential_version,created_at,updated_at) VALUES('12345678',?,?,?,1,1,?,?)", (hash_password("Test-Password-123!"), role, change, now, now))
            await db.commit()
        finally:
            await db.close()
        response = await client.post("/api/auth/login", json={"qq_id": "12345678", "password": "Test-Password-123!"})
        self.assertEqual(200, response.status_code)

    async def test_anonymous_and_member_cannot_download(self):
        async with self.app.test_app():
            client = self.app.test_client()
            for path in ("latest", "v1.0.0-preview.1/apk"):
                response = await client.get("/api/admin/android/releases/" + path)
                self.assertEqual(401, response.status_code)
                self.assertIn("no-store", response.headers["Cache-Control"])
            await self.login(client, "member")
            for path in ("latest", "v1.0.0-preview.1/apk"):
                self.assertEqual(403, (await client.get("/api/admin/android/releases/" + path)).status_code)

    async def test_first_password_change_and_missing_configuration(self):
        async with self.app.test_app():
            client = self.app.test_client()
            await self.login(client, "admin", 1)
            self.assertEqual(428, (await client.get("/api/admin/android/releases/latest")).status_code)
            db = await connect_db(self.db_path)
            await db.execute("UPDATE web_accounts SET must_change_password=0")
            await db.commit()
            await db.close()
            response = await client.get("/api/admin/android/releases/latest")
            self.assertEqual(503, response.status_code)
            self.assertNotIn("token", await response.get_data(as_text=True))

    async def test_admin_metadata_and_apk_are_private_and_role_revalidated(self):
        async with self.app.test_app():
            client = self.app.test_client()
            await self.login(client, "root")
            service = self.app.extensions["android_private_releases"]
            with patch.object(service, "metadata", new=AsyncMock(return_value=fixture())):
                response = await client.get("/api/admin/android/releases/latest")
                self.assertEqual(fixture(), await response.get_json())
                self.assertIn("no-store", response.headers["Cache-Control"])
            with patch.object(service, "download", new=AsyncMock(return_value=(fixture(), io.BytesIO(b"fixture")))):
                response = await client.get("/api/admin/android/releases/v1.0.0-preview.1/apk")
                self.assertEqual(b"fixture", await response.get_data())
                self.assertIn("no-store", response.headers["Cache-Control"])
            async def demoted(code):
                db = await connect_db(self.db_path)
                await db.execute("UPDATE web_accounts SET role='member'")
                await db.commit()
                await db.close()
                return fixture(), io.BytesIO(b"fixture")
            with patch.object(service, "download", side_effect=demoted):
                self.assertEqual(403, (await client.get("/api/admin/android/releases/v1.0.0-preview.1/apk")).status_code)

    async def test_published_or_incomplete_draft_is_not_downloadable(self):
        service = DraftReleases()
        row = {"tag_name": "v1.0.0-preview.1", "draft": True, "assets": [
            {"id": 1, "name": "update.json", "state": "uploaded"},
            {"id": 2, "name": "acmforever-1.0.0-preview.1.apk", "state": "uploaded", "size": 7}]}
        import json
        async def fetch(session, path, limit):
            return json.dumps([row] if "?per_page=" in path else fixture()).encode()
        with patch.object(service, "fetch", side_effect=fetch):
            self.assertEqual((fixture(), 2, {}), await service.latest(None))
            row["draft"] = False
            with self.assertRaises(ReleaseUnavailable): await service.latest(None)
            row["draft"] = True
            row["assets"][1]["size"] = 6
            with self.assertRaises(ReleaseUnavailable): await service.latest(None)

    def test_metadata_strips_unknown_fields_and_rejects_unsafe_identity(self):
        self.assertEqual(fixture(), validate_manifest({**fixture(), "secret": "never forward"}))
        for key, value in (("packageName", "com.giraffeslovebeauty.acmforever.admin"), ("apkUrl", "https://example.com/a.apk"),
                           ("sizeBytes", MAX_APK + 1), ("versionCode", True), ("signingCertificateSha256", "0" * 64),
                           ("apkPath", "/api/me/avatar"), ("distribution", "release")):
            with self.subTest(key=key), self.assertRaises(ReleaseUnavailable): validate_manifest({**fixture(), key: value})

    async def test_upstream_redirect_drops_token_and_rejects_other_hosts(self):
        class Content:
            async def iter_chunked(self, size):
                yield b"fixture"
        class Reply:
            def __init__(self, status, location=""):
                self.status = status
                self.headers = {"Location": location}
                self.content_length = 7
                self.content = Content()
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
        class Session:
            def __init__(self, location): self.location, self.calls = location, []
            def get(self, url, **kwargs):
                self.calls.append((url, kwargs))
                return Reply(302, self.location) if len(self.calls) == 1 else Reply(200)
        service = DraftReleases()
        service.token = "synthetic-secret"
        session = Session("https://release-assets.githubusercontent.com/signed-asset")
        self.assertEqual(b"fixture", await service.fetch(session, "/releases/assets/1", 7))
        self.assertIn("Authorization", session.calls[0][1]["headers"])
        self.assertNotIn("Authorization", session.calls[1][1]["headers"])
        self.assertTrue(all(not call[1]["allow_redirects"] for call in session.calls))
        for location in ("https://evil.invalid/a", "http://objects.githubusercontent.com/a",
                         "https://user:pass@objects.githubusercontent.com/a", "https://objects.githubusercontent.com:8443/a"):
            with self.subTest(location=location), self.assertRaises(ReleaseUnavailable):
                await service.fetch(Session(location), "/releases/assets/1", 7)
        with self.assertRaises(ReleaseUnavailable):
            await service.fetch(Session("https://objects.githubusercontent.com/a"), "/releases/assets/1", 6)

    async def test_download_hash_mismatch_closes_private_tempfile(self):
        service = DraftReleases()
        service.token = "synthetic-secret"
        async def fetch(session, path, limit, target=None):
            target.write(b"corrupt")
        with patch.object(service, "latest", new=AsyncMock(return_value=(fixture(), 2, {}))), patch.object(service, "fetch", side_effect=fetch):
            with self.assertRaises(ReleaseUnavailable): await service.download("v1.0.0-preview.1")
            with self.assertRaises(ReleaseUnavailable): await service.download("v1.0.0-preview.2")

    async def test_published_formal_release_retires_preview(self):
        import json
        service=DraftReleases()
        rows=[{"tag_name":"v1.0.0-preview.1","draft":True,"assets":[{"id":1,"name":"update.json","state":"uploaded"},{"id":2,"name":"acmforever-1.0.0-preview.1.apk","state":"uploaded","size":7}]},
              {"tag_name":"v1.0.0","draft":False,"prerelease":False,"assets":[{"name":"update.json"}]}]
        async def fetch(session,path,limit):return json.dumps(rows if "?per_page=" in path else fixture()).encode()
        with patch.object(service,"fetch",side_effect=fetch):
            with self.assertRaises(ReleaseUnavailable):await service.latest(None)

    async def test_no_unreleased_preview_is_a_valid_empty_result(self):
        async with self.app.test_app():
            client=self.app.test_client();await self.login(client,"admin")
            with patch.object(self.app.extensions["android_private_releases"],"metadata",new=AsyncMock(side_effect=NoPreview())):
                response=await client.get("/api/admin/android/releases/latest")
                self.assertEqual(200,response.status_code)
                self.assertEqual(False,(await response.get_json())["available"])

    async def test_modular_preview_requires_eight_complete_pinned_attachments(self):
        value,catalog,row=modular_fixture()
        service=DraftReleases()
        async def fetch(session,path,limit):
            return json.dumps([row] if '?per_page=' in path else catalog if path.endswith('/4') else value).encode()
        with patch.object(service,'fetch',side_effect=fetch):
            result=await service.latest(None)
            self.assertEqual(catalog,result[0]['moduleCatalog'])
            self.assertEqual(set(MODULES.values()),set(result[2]))
            for bad in ('missing','wrong-size','public-url','duplicate'):
                original=copy.deepcopy(row),copy.deepcopy(catalog)
                if bad=='missing': row['assets'].pop()
                if bad=='wrong-size': row['assets'][-1]['size']=8
                if bad=='public-url': catalog['modules'][0]['url']='https://evil.invalid/file'
                if bad=='duplicate': catalog['modules'][1]=catalog['modules'][0]
                with self.subTest(bad=bad),self.assertRaises(NoPreview): await service.latest(None)
                row.clear();row.update(original[0]);catalog.clear();catalog.update(original[1])

    async def test_private_module_bytes_are_hashed_and_unknown_names_rejected(self):
        value,catalog,row=modular_fixture();value['moduleCatalog']=catalog
        service=DraftReleases();service.token='synthetic-only'
        async def fetch(session,path,limit,target=None): target.write(b'fixture')
        with patch.object(service,'latest',new=AsyncMock(return_value=(value,2,{'module-admin.apk':5}))),patch.object(service,'fetch',side_effect=fetch):
            metadata,file=await service.download_asset(value['previewTag'],'module-admin.apk')
            try:
                self.assertEqual(b'fixture',file.read())
                self.assertEqual('admin',metadata['id'])
            finally: file.close()
            with self.assertRaises(ReleaseUnavailable): await service.download_asset(value['previewTag'],'update.json')

    async def test_role_loss_during_metadata_does_not_release_private_catalog(self):
        async with self.app.test_app():
            client=self.app.test_client();await self.login(client,'admin')
            async def demoted():
                db=await connect_db(self.db_path)
                await db.execute("UPDATE web_accounts SET role='member'")
                await db.commit();await db.close()
                value,catalog,_=modular_fixture();value['moduleCatalog']=catalog
                return value
            with patch.object(self.app.extensions['android_private_releases'],'metadata',side_effect=demoted):
                self.assertEqual(403,(await client.get('/api/admin/android/releases/latest')).status_code)

    async def test_private_module_endpoints_are_denied_to_members(self):
        async with self.app.test_app():
            client=self.app.test_client();await self.login(client,'member')
            for path in ('modules','assets/module-admin.apk'):
                response=await client.get('/api/admin/android/releases/v1.0.0-preview.1/'+path)
                self.assertEqual(403,response.status_code)
                self.assertIn('no-store',response.headers['Cache-Control'])

    async def test_scan_limit_fails_closed_and_strict_catalog_types(self):
        service=DraftReleases()
        with patch.object(service,'fetch',new=AsyncMock(return_value=json.dumps([{}]*100).encode())):
            with self.assertRaises(ReleaseUnavailable): await service.latest(None)
        value,catalog,_=modular_fixture()
        for key,bad in [('schemaVersion',True),('versionCode',True),('modulesPath','/api/me/avatar'),('modulesUrl','https://example.invalid/modules.json')]:
            with self.subTest(key=key),self.assertRaises(ReleaseUnavailable):validate_manifest({**value,key:bad})
        with self.assertRaises(ReleaseUnavailable):validate_catalog({**catalog,'versionCode':True},value,service.repository)
