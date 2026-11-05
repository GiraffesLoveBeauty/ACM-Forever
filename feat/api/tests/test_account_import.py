"""Synthetic regression coverage for Excel account imports; never reads production data."""
import asyncio
import io
import json
import os
import secrets
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import aiosqlite
from openpyxl import load_workbook
from openpyxl.packaging.custom import StringProperty
from werkzeug.datastructures import FileStorage

from feat.api.app import create_app
from feat.api.acm_api import account_import_service as imports
from feat.api.acm_api import binding_service
from feat.api.acm_api.account_import_excel import ExcelError, parse_workbook, report_bytes, template_bytes
from feat.api.acm_api.auth_service import hash_password, validate_password, verify_password
from feat.api.acm_api.database import connect_db

PASSWORD = "Synthetic-import!2026"
ENCODED = hash_password(PASSWORD)
PREFIX = "/api/admin/account-imports"


def workbook(rows):
    book = load_workbook(io.BytesIO(template_bytes()))
    for number, values in enumerate(rows, 2):
        for column, value in enumerate(values, 1):
            book["导入数据"].cell(number, column, value)
    output = io.BytesIO()
    book.save(output)
    return output.getvalue()


def rewrite(content, transform):
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(content)) as source, zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as target:
        for name in source.namelist():
            target.writestr(name, transform(name, source.read(name)))
    return output.getvalue()


class WorkbookTests(unittest.TestCase):
    def test_template_text_identifiers_and_real_excel_rows(self):
        data = parse_workbook(workbook([["10000084", "合成成员", "", "现役", "", "Demo84", "12345", "12345", "Demo84", "demo84"], [], [10000085]]))
        self.assertEqual([r["excel_row_number"] for r in data], [2, 4])
        self.assertEqual(data[1]["payload"]["qq_id"], "10000085")
        self.assertTrue(data[1]["warnings"])

    def test_numeric_precision_types_and_scientific_notation(self):
        data = parse_workbook(workbook([["10000084", "", "", "", "", 123], [True], ["1e8"], ["10000085", "", "", "", "", "", 10**16]]))
        self.assertFalse(data[0]["errors"])
        self.assertIn("已跳过绑定", " ".join(data[0]["warnings"]))
        self.assertTrue(data[1]["errors"])
        self.assertEqual(data[2]["payload"]["qq_id"], "1e8")  # QQ validation is shared by the service.
        self.assertFalse(data[3]["errors"])
        self.assertEqual(data[3]["payload"]["luogu_id"], "")
        self.assertIn("已跳过绑定", " ".join(data[3]["warnings"]))

    def test_office_metadata_and_empty_directories_are_accepted(self):
        book = load_workbook(io.BytesIO(workbook([["10000084"]])))
        book.custom_doc_props.append(StringProperty(name="KSOProductBuildVer", value="Synthetic-only"))
        output = io.BytesIO(); book.save(output)
        with zipfile.ZipFile(output, "a") as archive:
            for name in ("_rels/", "docProps/", "xl/", "xl/_rels/", "xl/theme/", "xl/worksheets/"):
                archive.writestr(name, b"")
        parsed = parse_workbook(output.getvalue())
        self.assertEqual(parsed[0]["payload"]["qq_id"], "10000084")
        self.assertFalse(parsed[0]["errors"])

    def test_metadata_compatibility_does_not_allow_unsafe_entries(self):
        for name, content in [("_rels/", b"not empty"), ("xl/unexpected/", b""), ("docProps/custom.xml", b'<!DOCTYPE x [<!ENTITY e "unsafe">]><x>&e;</x>'), ("docProps/custom.xml", b'<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/custom-properties"><property><blob/></property></Properties>')]:
            with self.subTest(name=name, content=content):
                output = io.BytesIO(workbook([["10000084"]]))
                with zipfile.ZipFile(output, "a") as archive:
                    archive.writestr(name, content)
                with self.assertRaises(ExcelError):
                    parse_workbook(output.getvalue())
        book = load_workbook(io.BytesIO(workbook([["10000084"]])))
        book.custom_doc_props.append(StringProperty(name="KSOProductBuildVer", value="Synthetic-only"))
        output = io.BytesIO(); book.save(output)
        for target in (b'TargetMode="External" Target="https://invalid.example/"', b'Target="../docProps/custom.xml"', b'Target="xl/workbook.xml"'):
            unsafe = rewrite(output.getvalue(), lambda name, raw: raw.replace(b'Target="docProps/custom.xml"', target) if name == '_rels/.rels' else raw)
            with self.assertRaises(ExcelError):
                parse_workbook(unsafe)

    def test_formula_and_external_relationship_rejected(self):
        for content in [workbook([["10000084", "=1+1"]]), rewrite(workbook([["10000084"]]), lambda name, raw: raw.replace(b'Target="styles.xml"', b'TargetMode="External" Target="https://invalid.example/"') if name == 'xl/_rels/workbook.xml.rels' else raw)]:
            with self.assertRaises(ExcelError):
                parse_workbook(content)

    def test_headers_hidden_rows_and_template_version_rejected(self):
        for edit in [lambda b: setattr(b["导入数据"]["A1"], "value", "角色"), lambda b: setattr(b["导入数据"].row_dimensions[2], "hidden", True), lambda b: setattr(b["_meta"]["B1"], "value", "other")]:
            book = load_workbook(io.BytesIO(workbook([["10000084"]])))
            edit(book)
            data = io.BytesIO(); book.save(data)
            with self.assertRaises(ExcelError):
                parse_workbook(data.getvalue())

    def test_false_dimension_cannot_hide_more_than_200_rows(self):
        data = workbook([[str(10000084+i)] for i in range(201)])
        data = rewrite(data, lambda name, raw: __import__('re').sub(rb'<dimension[^>]*/>', b'<dimension ref="A1:A2"/>', raw) if name == 'xl/worksheets/sheet1.xml' else raw)
        with self.assertRaises(ExcelError) as caught:
            parse_workbook(data)
        self.assertEqual(caught.exception.code, "row_limit")

    def test_dtd_path_duplicate_and_actual_zip_inflation(self):
        raw = workbook([["10000084"]])
        bad = rewrite(raw, lambda name, data: b'<!DOCTYPE x [<!ENTITY x "evil">]>' + data if name == 'xl/workbook.xml' else data)
        with self.assertRaises(ExcelError): parse_workbook(bad)
        for name, content in [("../escape.xml", b"x"), ("xl/vbaProject.bin", b"macro"), ("xl/sharedStrings.xml", b"x" * (8*1024*1024+1))]:
            output = io.BytesIO(raw)
            with zipfile.ZipFile(output, "a", zipfile.ZIP_DEFLATED) as archive: archive.writestr(name, content)
            with self.assertRaises(ExcelError): parse_workbook(output.getvalue())

    def test_report_forces_text_and_has_no_link_relationships(self):
        rows = [{"excel_row_number":2,"qq_id":"10000084","name":'=HYPERLINK("https://invalid.example")',"action":"create","status":"created","errors":["+SUM(1,1)"],"warnings":["@evil"],"ignored_fields":["-1+1"]}]
        data = report_bytes(rows)
        book = load_workbook(io.BytesIO(data), data_only=False)
        self.assertTrue(all(cell.data_type != 'f' and not cell.hyperlink for row in book.active for cell in row))
        self.assertEqual(book.active['C2'].value, rows[0]['name'])
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            self.assertFalse(any('externalLink' in name or 'hyperlink' in archive.read(name).decode('utf-8', errors='ignore') for name in archive.namelist()))


class AccountImportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'imports.db'
        self.env = patch.dict(os.environ, {"ACM_DATABASE_PATH":str(self.path),"ACM_WEBUI_SECRET_KEY":"synthetic-import-tests", "ACM_ACCOUNT_IMPORT_ENABLED":"true", "ACM_BOOTSTRAP_ROOT_QQ_ID":"", "ACM_BOOTSTRAP_ROOT_PASSWORD":""})
        self.env.start()
        self.app = create_app()
        db = await connect_db(self.path)
        now = int(time.time())
        for qq, role in [('10000001','admin'),('10000002','admin'),('10000003','root'),('10000004','member')]:
            await db.execute("INSERT INTO users(qq_id,name) VALUES(?,?)", (qq, '合成'+role))
            await db.execute("INSERT INTO web_accounts(qq_id,password_hash,role,must_change_password,created_at,updated_at) VALUES(?,?,?,0,?,?)", (qq,ENCODED,role,now,now))
        await db.commit(); await db.close()
        self.client, self.headers = await self.login('10000001')

    async def asyncTearDown(self):
        executor = self.app.extensions.get('account_password_executor')
        if executor: executor.close()
        self.env.stop(); self.temp.cleanup()

    async def db(self):
        db = await aiosqlite.connect(self.path)
        db.row_factory = aiosqlite.Row
        await db.execute('PRAGMA foreign_keys=ON')
        return db

    async def login(self, qq, password=PASSWORD):
        client = self.app.test_client()
        response = await client.post('/api/auth/login', json={'qq_id':qq,'password':password})
        self.assertEqual(response.status_code,200)
        return client, {'X-CSRF-Token':(await response.get_json())['csrf_token']}

    async def preview(self, rows, client=None, headers=None):
        response = await (client or self.client).post(PREFIX+'/preview', headers=self.headers if headers is None else headers, files={'file':FileStorage(io.BytesIO(workbook(rows)),filename='synthetic.xlsx')})
        self.assertEqual(response.status_code,201,await response.get_data(as_text=True))
        batch = await response.get_json()
        response = await (client or self.client).get(PREFIX+'/'+batch['id']+'/rows')
        return batch, (await response.get_json())['items']

    def intent(self, rows, **extra):
        return {'preview_version':1,'selected_row_ids':[r['row_id'] for r in rows if r['can_submit']],'acknowledge_admin_binding':True,'idempotency_key':secrets.token_hex(16),**extra}

    async def execute(self,batch,rows,body=None,client=None,headers=None):
        response = await (client or self.client).post(PREFIX+'/'+batch['id']+'/commit',json=body or self.intent(rows),headers=headers or self.headers)
        self.assertEqual(response.status_code,200,await response.get_data(as_text=True))
        return await response.get_json()

    async def test_preview_is_metadata_only_and_new_account_login_change_password(self):
        batch, rows = await self.preview([['10000084','','合成姓名','现役','合成学校','Demo84','12345','12345','Demo84','demo84']])
        db = await self.db()
        self.assertIsNone(await imports.row(db,"SELECT * FROM users WHERE qq_id='10000084'"))
        await db.close()
        self.assertEqual(rows[0]['name'],'10000084')
        result = await self.execute(batch,rows)
        self.assertEqual(result['summary']['created'],1)
        self.assertEqual(result['credentials'][0]['real_name'], '合成姓名')
        self.assertEqual(result['credentials'][0]['username'], '10000084')
        password = result['credentials'][0]['temporary_password']
        self.assertIsNone(validate_password(password))
        db = await self.db()
        self.assertEqual((await imports.row(db,"SELECT COUNT(*) n FROM binding_provenance WHERE qq_id='10000084'"))['n'],5)
        account = await imports.row(db,"SELECT * FROM web_accounts WHERE qq_id='10000084'")
        self.assertTrue(verify_password(password,account['password_hash']))
        await db.close()
        client, headers = await self.login('10000084',password)
        me = await (await client.get('/api/auth/me')).get_json()
        self.assertTrue(me['must_change_password'])
        response = await client.post('/api/auth/change-password',json={'old_password':password,'new_password':'Changed-Synthetic!2026'},headers=headers)
        self.assertEqual(response.status_code,200)
        # Neither reports nor persistence contain the random plaintext.
        response = await self.client.get(PREFIX+'/'+batch['id']+'/report')
        self.assertEqual(response.status_code,200)
        self.assertIn('no-store',response.headers['Cache-Control'])
        self.assertNotIn(password.encode(),await response.get_data())
        self.assertNotIn(password.encode(),self.path.read_bytes())

    async def test_existing_member_only_receives_account_preserving_all_evidence(self):
        db = await self.db()
        await db.execute("INSERT INTO users(qq_id,name,real_name,school,cf_handle) VALUES('10000084','原昵称','原姓名','原学校','Original84')")
        await db.execute("INSERT INTO submissions(user_qq_id,platform,problem_id,submit_time) VALUES('10000084','codeforces','cf_1A',100)")
        await db.commit(); before = dict(await imports.row(db,"SELECT * FROM users WHERE qq_id='10000084'")); await db.close()
        batch, rows = await self.preview([['10000084','新昵称','新姓名','其他','新学校','Other84']])
        self.assertIn('昵称',rows[0]['ignored_fields'])
        self.assertEqual(rows[0]['action'],'create_web_account_only')
        result = await self.execute(batch,rows)
        self.assertEqual(result['credentials'][0]['real_name'], '原姓名')
        self.assertEqual(result['credentials'][0]['username'], '10000084')
        db = await self.db()
        self.assertEqual(dict(await imports.row(db,"SELECT * FROM users WHERE qq_id='10000084'")),before)
        self.assertEqual((await imports.row(db,"SELECT COUNT(*) n FROM submissions WHERE user_qq_id='10000084'"))['n'],1)
        await db.close()

    async def test_duplicates_existing_inactive_and_occupied_bindings(self):
        db = await self.db()
        await db.execute("UPDATE users SET cf_handle='Occupied' WHERE qq_id='10000004'")
        await db.execute("UPDATE web_accounts SET is_active=0 WHERE qq_id='10000004'")
        await db.commit(); await db.close()
        _, rows = await self.preview([['10000084'],['10000084'],['10000001'],['10000004'],['10000085','','','','','occupied'],['10000086','','','','','Duplicate'],['10000087','','','','','duplicate']])
        self.assertEqual([r['status'] for r in rows],['invalid','invalid','skipped','blocked','ready','ready','ready'])
        for value in rows[4:]:
            self.assertEqual(value['bindings'], {})
            self.assertTrue(any('已跳过绑定' in w for w in value['warnings']))

    async def test_bad_optional_oj_fields_do_not_block_qq_only_accounts(self):
        batch, rows = await self.preview([
            ['10000084', '合成昵称', '合成姓名', '', '', 'Has\u2006Space', 'not_uid', 'not_uid', True, 123],
            ['10000085', '', '', '', '', 'Valid85', 12345, 10**16, 'bad handle', 'valid85'],
            ['10000086'],
        ])
        self.assertTrue(all(r['can_submit'] and not r['errors'] for r in rows))
        self.assertEqual(rows[0]['bindings'], {})
        self.assertEqual(len([w for w in rows[0]['warnings'] if '已跳过绑定' in w]), 5)
        self.assertEqual(rows[1]['bindings'], {'cf_handle':'Valid85', 'luogu_id':'12345', 'cjlu_username':'valid85'})
        result = await self.execute(batch, rows)
        self.assertEqual(result['summary']['created'], 3)
        self.assertEqual(len(result['credentials']), 3)
        self.assertEqual(result['credentials'][1]['real_name'], '')
        db = await self.db()
        user = await imports.row(db, "SELECT * FROM users WHERE qq_id='10000084'")
        self.assertTrue(all(not user[field] for field in ('cf_handle','luogu_id','nowcoder_id','atcoder_handle','cjlu_username')))
        self.assertEqual((await imports.row(db, "SELECT COUNT(*) n FROM binding_provenance WHERE qq_id='10000085'"))['n'], 3)
        await db.close()
        report = await self.client.get(PREFIX+'/'+batch['id']+'/report')
        book = load_workbook(io.BytesIO(await report.get_data()), data_only=False)
        self.assertIn('已跳过绑定', str(book.active['G2'].value))

    async def test_occupied_and_duplicate_oj_fields_are_ignored_not_accounts(self):
        db = await self.db()
        await db.execute("UPDATE users SET cf_handle='Occupied' WHERE qq_id='10000004'")
        await db.commit(); await db.close()
        batch, rows = await self.preview([['10000084','','','','','occupied'], ['10000085','','','','','Duplicate'], ['10000086','','','','','duplicate']])
        result = await self.execute(batch, rows)
        self.assertEqual(result['summary']['created'], 3)
        db = await self.db()
        self.assertEqual((await imports.row(db,"SELECT COUNT(*) n FROM users WHERE qq_id IN ('10000084','10000085','10000086') AND cf_handle IS NOT NULL"))['n'], 0)
        self.assertEqual((await imports.row(db,"SELECT cf_handle FROM users WHERE qq_id='10000004'"))['cf_handle'], 'Occupied')
        await db.close()

    async def test_invalid_qq_and_orphan_evidence_do_not_create(self):
        batch, rows = await self.preview([['1e8'],['0000'],['10000084']])
        self.assertEqual([r['status'] for r in rows],['invalid','invalid','ready'])
        db = await self.db()
        await db.execute("INSERT INTO submissions(user_qq_id,platform,problem_id,submit_time) VALUES('10000084','codeforces','cf_1A',1)")
        await db.commit(); await db.close()
        result = await self.execute(batch,rows)
        self.assertEqual(result['summary']['conflict'],1)
        db = await self.db(); self.assertIsNone(await imports.row(db,"SELECT * FROM users WHERE qq_id='10000084'")); await db.close()

    async def test_retry_has_no_credentials_and_changed_key_payload_is_rejected(self):
        batch,rows = await self.preview([['10000084']]); body = self.intent(rows)
        result = await self.execute(batch,rows,body)
        replay = await self.execute(batch,rows,body)
        self.assertEqual(replay['credentials'],[])
        self.assertEqual(replay['summary']['created'],1)
        self.assertFalse(replay['credentials_replayed'])
        response = await self.client.post(PREFIX+'/'+batch['id']+'/commit',json={**body,'acknowledge_admin_binding':False},headers=self.headers)
        self.assertEqual(response.status_code,409)
        data = await (await self.client.get(PREFIX+'/'+batch['id'])).get_json()
        self.assertNotIn('credentials',data)
        again, rows2 = await self.preview([['10000084']])
        self.assertFalse(rows2[0]['can_submit'])

    async def test_multi_chunk_freezes_selection_and_explicit_continuation(self):
        batch,rows = await self.preview([[str(10000084+i)] for i in range(12)])
        result = await self.execute(batch,rows)
        self.assertEqual((result['summary']['created'],result['summary']['remaining']),(10,2))
        self.assertEqual(result['status'],'paused')
        body = {'preview_version':1,'selection_digest':result['selection_digest'],'continuation_token':result['next_chunk_token'],'idempotency_key':secrets.token_hex(16)}
        final = await self.execute(batch,rows,body)
        self.assertEqual(final['summary']['created'],12)
        self.assertEqual(len(final['credentials']),2)

    async def test_concurrent_oj_occupation_skips_only_binding_not_qq_account(self):
        a,ra = await self.preview([['10000084','','','','','Race84']])
        b,rb = await self.preview([['10000085','','','','','race84']])
        results = await asyncio.gather(self.execute(a,ra),self.execute(b,rb))
        self.assertEqual(sum(r['summary']['created'] for r in results),2)
        self.assertEqual(sum(r['summary']['conflict'] for r in results),0)
        db = await self.db()
        self.assertEqual((await imports.row(db,"SELECT COUNT(*) n FROM users WHERE LOWER(cf_handle)='race84'"))['n'],1)
        self.assertEqual((await imports.row(db,"SELECT COUNT(*) n FROM binding_provenance WHERE qq_id IN ('10000084','10000085')"))['n'],1)
        await db.close()
        all_rows = []
        for value in (a, b):
            all_rows += (await (await self.client.get(PREFIX+'/'+value['id']+'/rows')).get_json())['items']
        self.assertEqual(sum(any('预检后被占用' in w for w in r['warnings']) for r in all_rows),1)

    async def test_concurrent_batches_still_cannot_duplicate_qq(self):
        a, ra = await self.preview([['10000084']])
        b, rb = await self.preview([['10000084']])
        results = await asyncio.gather(self.execute(a,ra),self.execute(b,rb))
        self.assertEqual(sum(r['summary']['created'] for r in results),1)
        self.assertEqual(sum(r['summary']['conflict'] for r in results),1)

    async def test_preview_snapshot_changes_are_conflicts_and_row_failure_is_atomic(self):
        batch,rows = await self.preview([['10000084'],['10000085']])
        db = await self.db(); await db.execute("INSERT INTO users(qq_id,name) VALUES('10000084','并发建档')")
        await db.execute("CREATE TRIGGER reject_test BEFORE INSERT ON web_accounts WHEN NEW.qq_id='10000085' BEGIN SELECT RAISE(ABORT,'synthetic failure'); END")
        await db.commit(); await db.close()
        result = await self.execute(batch,rows)
        self.assertEqual(result['summary']['created'],0)
        self.assertEqual(result['summary']['conflict'],2)
        db = await self.db(); self.assertIsNone(await imports.row(db,"SELECT * FROM users WHERE qq_id='10000085'")); await db.close()

    async def test_access_csrf_owner_and_root_read_only(self):
        anonymous = self.app.test_client()
        self.assertEqual((await anonymous.get(PREFIX+'/capabilities')).status_code,401)
        member,_ = await self.login('10000004')
        self.assertEqual((await member.get(PREFIX+'/capabilities')).status_code,403)
        response = await self.client.post(PREFIX+'/preview')
        self.assertEqual(response.status_code,403)
        batch,rows = await self.preview([['10000084']])
        other,headers = await self.login('10000002')
        self.assertEqual((await other.get(PREFIX+'/'+batch['id'])).status_code,404)
        response = await other.post(PREFIX+'/'+batch['id']+'/commit',json=self.intent(rows),headers=headers)
        self.assertEqual(response.status_code,404)
        root,root_headers = await self.login('10000003')
        self.assertTrue((await (await root.get(PREFIX+'/'+batch['id'])).get_json())['read_only'])
        self.assertEqual((await root.post(PREFIX+'/'+batch['id']+'/commit',json=self.intent(rows),headers=root_headers)).status_code,404)

    async def test_extra_fields_acknowledgement_and_foreign_row_are_rejected(self):
        batch,rows = await self.preview([['10000084','','','','','Demo84']])
        for extra in [{'role':'root'},{'acknowledge_admin_binding':False},{'selected_row_ids':['unknown-row']}]:
            response = await self.client.post(PREFIX+'/'+batch['id']+'/commit',json=self.intent(rows,**extra),headers=self.headers)
            self.assertEqual(response.status_code,400)
        response = await self.client.post(PREFIX+'/preview',headers=self.headers,form={'role':'root'},files={'file':FileStorage(io.BytesIO(workbook([['10000084']])),filename='x.xlsx')})
        self.assertEqual(response.status_code,400)

    async def test_expiry_cleanup_and_cancel_preserve_created_accounts(self):
        batch,rows = await self.preview([[str(10000084+i)] for i in range(11)])
        await self.execute(batch,rows)
        response = await self.client.post(PREFIX+'/'+batch['id']+'/cancel',json={},headers=self.headers)
        self.assertEqual(response.status_code,200)
        db = await self.db()
        self.assertEqual((await imports.row(db,"SELECT COUNT(*) n FROM web_accounts WHERE qq_id>='10000084'"))['n'],10)
        await imports.cleanup(db,int(time.time())+2*86400)
        stored = await imports.row(db,"SELECT payload_json FROM account_import_rows WHERE batch_id=?",(batch['id'],))
        self.assertEqual(stored['payload_json'],'{}')
        self.assertEqual((await imports.row(db,"SELECT COUNT(*) n FROM binding_provenance"))['n'],0)
        await db.close()
        self.assertEqual((await self.client.get(PREFIX+'/'+batch['id']+'/report')).status_code,410)

    async def test_expired_lease_is_fenced_and_can_resume_without_replaying(self):
        batch,rows = await self.preview([['10000084']])
        identity={'qq_id':'10000001','credential_version':1}
        db = await self.db()
        chunk,original = await imports.acquire_chunk(db,identity,batch['id'],self.intent(rows))
        self.assertTrue(original)
        await db.execute("UPDATE account_import_chunks SET lease_until=1 WHERE id=?",(chunk['id'],));await db.commit()
        resumed = await imports.summary(db,identity,batch['id'])
        self.assertEqual(resumed['status'],'paused')
        current,_ = await imports.get_batch(db,identity,batch['id'])
        await db.execute('BEGIN IMMEDIATE')
        with self.assertRaises(imports.ImportError): await imports._lease_valid(db,current,chunk,identity,int(time.time()))
        await db.rollback();await db.close()
        body={'preview_version':1,'selection_digest':resumed['selection_digest'],'continuation_token':resumed['next_chunk_token'],'idempotency_key':secrets.token_hex(16)}
        final=await self.execute(batch,rows,body)
        self.assertEqual(final['summary']['created'],1)

    async def test_actor_demotion_stops_later_rows_and_withholds_secrets(self):
        batch,rows=await self.preview([['10000084'],['10000085']])
        real=imports.prepare_password; calls=0
        async def demote(password):
            nonlocal calls
            calls+=1
            if calls==2:
                db=await self.db();await db.execute("UPDATE web_accounts SET role='member' WHERE qq_id='10000001'");await db.commit();await db.close()
            return await real(password)
        with patch.object(imports,'prepare_password',demote):
            response=await self.client.post(PREFIX+'/'+batch['id']+'/commit',json=self.intent(rows),headers=self.headers)
        self.assertEqual(response.status_code,403)
        self.assertNotIn('temporary_password',await response.get_data(as_text=True))
        db=await self.db()
        self.assertEqual((await imports.row(db,"SELECT COUNT(*) n FROM web_accounts WHERE qq_id>='10000084'"))['n'],1)
        await db.close()

    async def test_lifecycle_closed_block_and_redaction_hook(self):
        # Low-level hook coverage; real closure and new-generation routes are tested below.
        db=await self.db()
        async with db.execute("PRAGMA table_info(users)") as cursor:
            columns = {item["name"] for item in await cursor.fetchall()}
        if "account_state" not in columns:
            await db.execute("ALTER TABLE users ADD COLUMN account_state TEXT NOT NULL DEFAULT 'active'")
        if "account_epoch" not in columns:
            await db.execute("ALTER TABLE users ADD COLUMN account_epoch INTEGER NOT NULL DEFAULT 1")
        await imports.initialize_imports(db)
        await db.execute("INSERT INTO users(qq_id,name,account_state) VALUES('10000084','已注销','closed')")
        await db.commit();await db.close()
        batch,rows=await self.preview([['10000084'],['10000085','','','','','Demo85']])
        self.assertEqual(rows[0]['action'],'blocked_closed')
        await self.execute(batch,rows)
        db=await self.db();await db.execute("UPDATE users SET account_state='closed',account_epoch=2 WHERE qq_id='10000085'");await db.commit()
        stored=await imports.row(db,"SELECT * FROM account_import_rows WHERE batch_id=? AND excel_row_number=3",(batch['id'],))
        self.assertEqual(stored['qq_id'],'');self.assertEqual(stored['payload_json'],'{}')
        self.assertEqual((await imports.row(db,"SELECT COUNT(*) n FROM binding_provenance WHERE qq_id='10000085'"))['n'],0)
        await db.close()

    async def imported_member_login(self, nickname=''):
        batch, rows = await self.preview([['10000084', nickname, '', '', '', 'Demo84']])
        created = await self.execute(batch, rows)
        temporary = created['credentials'][0]['temporary_password']
        client, headers = await self.login('10000084', temporary)
        response = await client.post('/api/auth/change-password', headers=headers,
                                     json={'old_password': temporary, 'new_password': PASSWORD})
        self.assertEqual(response.status_code, 200, await response.get_json())
        return await self.login('10000084')

    async def close_import_member(self, client, headers):
        self.app.config['ACCOUNT_CLOSURE_ENABLED'] = True
        response = await client.get('/api/me/account-closure/preview')
        self.assertEqual(response.status_code, 200, await response.get_json())
        preview = await response.get_json()
        response = await client.post('/api/me/account-closure', headers={
            **headers, 'Idempotency-Key': preview['request_id'],
            'X-Closure-Receipt': preview['receipt_token'],
        }, json={'current_password': PASSWORD, 'confirm_text': '注销账号',
                 'policy_version': preview['policy_version'],
                 'expected_account_epoch': preview['account_epoch']})
        self.assertEqual(response.status_code, 200, await response.get_json())
        self.assertEqual((await response.get_json())['status'], 'closed')
        return preview

    async def test_real_closure_redacts_import_and_explicit_new_account_stays_separate(self):
        member, headers = await self.imported_member_login()
        old_session, _ = await self.login('10000084')
        receipt = await self.close_import_member(member, headers)
        batch, rows = await self.preview([['10000084', '不得从 Excel 重开']])
        self.assertEqual(rows[0]['action'], 'blocked_closed')
        self.assertFalse(rows[0]['can_submit'])
        created = await self.client.post('/api/admin/web-accounts', headers=self.headers,
                                         json={'qq_id': '10000084', 'name': '新代际昵称',
                                               'initial_password': PASSWORD})
        self.assertEqual(created.status_code, 201, await created.get_json())
        self.assertTrue((await created.get_json())['new_generation'])
        fresh, fresh_headers = await self.login('10000084')
        changed = await fresh.post('/api/auth/change-password', headers=fresh_headers,
                                   json={'old_password': PASSWORD, 'new_password': 'Fresh-Import!2026'})
        self.assertEqual(changed.status_code, 200, await changed.get_json())
        fresh, _ = await self.login('10000084', 'Fresh-Import!2026')
        profile = await (await fresh.get('/api/me/profile')).get_json()
        self.assertEqual((await (await fresh.get('/api/auth/me')).get_json())['account_epoch'], 3)
        self.assertEqual(profile['user']['name'], '新代际昵称')
        self.assertFalse(profile['user']['cf_handle'])
        self.assertEqual(profile['recent_ac'], [])
        self.assertTrue(all(item['provenance'] is None for item in profile['bindings']))
        self.assertEqual((await old_session.get('/api/me/profile')).status_code, 401)
        replay = await fresh.get('/api/account-closures/' + receipt['request_id'],
                                 headers={'X-Closure-Receipt': receipt['receipt_token']})
        self.assertEqual(replay.status_code, 200)
        self.assertEqual((await fresh.get('/api/me/profile')).status_code, 200)
        _, rows = await self.preview([['10000084', '不得覆盖新代际']])
        self.assertEqual(rows[0]['action'], 'skipped_existing')
        db = await self.db()
        try:
            async with db.execute("SELECT qq_id,payload_json FROM account_import_rows WHERE status='created'") as cursor:
                self.assertEqual([tuple(item) for item in await cursor.fetchall()], [('', '{}')])
        finally:
            await db.close()

    async def test_closed_import_operator_and_new_generation_cannot_reclaim_old_batch(self):
        batch, rows = await self.preview([['10000084', '旧操作者的待导入资料']])
        root, root_headers = await self.login('10000003')
        demoted = await root.patch('/api/admin/web-accounts/10000001', headers=root_headers,
                                   json={'role': 'member'})
        self.assertEqual(demoted.status_code, 200, await demoted.get_json())
        member, member_headers = await self.login('10000001')
        await self.close_import_member(member, member_headers)
        created = await root.post('/api/admin/web-accounts', headers=root_headers,
                                  json={'qq_id': '10000001', 'name': '新管理员',
                                        'role': 'admin', 'initial_password': PASSWORD})
        self.assertEqual(created.status_code, 201, await created.get_json())
        fresh, fresh_headers = await self.login('10000001')
        changed = await fresh.post('/api/auth/change-password', headers=fresh_headers,
                                   json={'old_password': PASSWORD, 'new_password': 'Fresh-Admin!2026'})
        self.assertEqual(changed.status_code, 200, await changed.get_json())
        fresh, fresh_headers = await self.login('10000001', 'Fresh-Admin!2026')
        for client in (fresh, root):
            response = await client.get(PREFIX + '/' + batch['id'])
            self.assertEqual(response.status_code, 404, await response.get_json())
        response = await fresh.post(PREFIX + '/' + batch['id'] + '/commit',
                                    headers=fresh_headers, json=self.intent(rows))
        self.assertEqual(response.status_code, 404, await response.get_json())
        db = await self.db()
        try:
            stored = await imports.row(db, 'SELECT actor_qq_id,status,payload_purged FROM account_import_batches WHERE id=?', (batch['id'],))
            self.assertEqual(tuple(stored), ('', 'cancelled', 1))
            stored = await imports.row(db, 'SELECT qq_id,payload_json FROM account_import_rows WHERE batch_id=?', (batch['id'],))
            self.assertEqual(tuple(stored), ('', '{}'))
            self.assertIsNone(await imports.row(db, "SELECT * FROM users WHERE qq_id='10000084'"))
        finally:
            await db.close()

    async def binding_evidence(self):
        db = await self.db()
        try:
            evidence = {}
            for table, owner in [('users', 'qq_id'), ('submissions', 'user_qq_id'),
                                 ('submission_attempts', 'owner_qq_id'),
                                 ('user_platform_sync_state', 'user_qq_id'),
                                 ('random_challenges', 'qq_id')]:
                async with db.execute(f'SELECT * FROM {table} WHERE {owner}=?', ('10000084',)) as cursor:
                    evidence[table] = [dict(item) for item in await cursor.fetchall()]
            return evidence
        finally:
            await db.close()

    async def test_same_handle_verification_uses_real_routes_and_keeps_evidence(self):
        client, headers = await self.imported_member_login()
        self.app.config['PLUGIN_CONFIG']['_account_sync_submitter'] = lambda *args: {'id': 'synthetic-sync'}
        db = await self.db()
        try:
            await db.execute("INSERT INTO submissions(user_qq_id,platform,problem_id,submit_time) VALUES('10000084','codeforces','1A',100)")
            await db.execute("INSERT INTO submission_attempts(owner_qq_id,platform,external_submission_id,problem_id,verdict,submitted_at,created_at) VALUES('10000084','codeforces','synthetic-84','1A','OK',100,100)")
            await db.execute("INSERT INTO user_platform_sync_state(user_qq_id,platform,cursor_timestamp,last_success_at,last_status,full_history_at,coverage_through_at,updated_at) VALUES('10000084','codeforces',100,100,'success',100,100,100)")
            await db.execute("INSERT INTO random_challenges(qq_id,platform,problem_id,problem_url,challenge_rating,time_limit_minutes,created_at,expires_at) VALUES('10000084','codeforces','1A','https://codeforces.com/problemset/problem/1/A',1000,60,100,200)")
            await db.commit()
        finally:
            await db.close()
        before = await self.binding_evidence()
        # Case differences must still verify the currently bound identity without a rebind.
        with patch.object(binding_service, 'validate_account', AsyncMock(return_value='Demo84')) as validate:
            response = await client.post('/api/me/bindings/codeforces/verification', headers=headers,
                                         json={'account': 'demo84'})
        self.assertEqual(response.status_code, 200, await response.get_json())
        validate.assert_awaited_once_with('codeforces', 'demo84')
        pending = await response.get_json()
        body = {'verification_id': pending['verification_id'], 'password': PASSWORD,
                'confirmed': True, 'current_account': 'Demo84'}
        with patch.object(binding_service, 'verify_ownership', AsyncMock(return_value=False)):
            rejected = await client.post('/api/me/bindings/codeforces/confirm', headers=headers, json=body)
        self.assertEqual(rejected.status_code, 400)
        self.assertEqual((await rejected.get_json())['code'], 'ownership_unverified')
        self.assertEqual(await self.binding_evidence(), before)
        db = await self.db()
        try:
            source = await imports.row(db, "SELECT * FROM binding_provenance WHERE qq_id='10000084'")
            self.assertEqual(source['source'], 'admin_import')
            self.assertIsNone(source['owner_verified_at'])
            await db.execute("DELETE FROM binding_rate_limits WHERE qq_id='10000084' AND action='confirm'")
            await db.commit()
        finally:
            await db.close()
        with patch.object(binding_service, 'verify_ownership', AsyncMock(return_value=True)) as verify:
            confirmed = await client.post('/api/me/bindings/cf/confirm', headers=headers, json=body)
        self.assertEqual(confirmed.status_code, 202, await confirmed.get_json())
        verify.assert_awaited_once_with('codeforces', 'Demo84', pending['code'])
        self.assertEqual(await self.binding_evidence(), before)
        profile = await (await client.get('/api/me/profile')).get_json()
        cf = next(item for item in profile['bindings'] if item['platform'] == 'codeforces')
        self.assertEqual(cf['provenance']['source'], 'member_verified')
        self.assertTrue(cf['provenance']['owner_verified_at'])
        self.assertEqual(cf['provenance']['existence_status'], 'exists')
        db = await self.db()
        try:
            self.assertIsNone(await imports.row(db, "SELECT * FROM account_bind_verifications WHERE qq_id='10000084'"))
            await db.execute("DELETE FROM binding_rate_limits WHERE qq_id='10000084'")
            await db.commit()
        finally:
            await db.close()
        replay = await client.post('/api/me/bindings/cf/confirm', headers=headers, json=body)
        self.assertEqual((await replay.get_json())['code'], 'verification_expired')
        repeated = await client.post('/api/me/bindings/cf/verification', headers=headers, json={'account': 'Demo84'})
        self.assertEqual((await repeated.get_json())['code'], 'already_bound')
        for _ in range(2):
            db = await connect_db(self.path)
            await db.close()
        self.assertEqual((await self.binding_evidence())['users'], before['users'])

    async def test_same_handle_requires_current_unverified_import_provenance(self):
        client, headers = await self.imported_member_login()
        cases = [('member_verified', 1, 'demo84', 123), ('admin_import', 2, 'demo84', None),
                 ('admin_import', 1, 'another', None), ('admin_import', 1, 'demo84', 123),
                 ('legacy', 1, 'demo84', None), (None, 1, 'demo84', None)]
        for source, version, account, verified_at in cases:
            with self.subTest(source=source, version=version, account=account, verified_at=verified_at):
                db = await self.db()
                try:
                    if source is None:
                        await db.execute("DELETE FROM binding_provenance WHERE qq_id='10000084'")
                    else:
                        await db.execute("UPDATE binding_provenance SET source=?,binding_version=?,account_canonical=?,owner_verified_at=? WHERE qq_id='10000084'",
                                         (source, version, account, verified_at))
                    await db.execute("DELETE FROM binding_rate_limits WHERE qq_id='10000084'")
                    await db.commit()
                finally:
                    await db.close()
                with patch.object(binding_service, 'validate_account', AsyncMock()) as upstream:
                    response = await client.post('/api/me/bindings/cf/verification', headers=headers,
                                                 json={'account': 'Demo84'})
                self.assertEqual(response.status_code, 409, await response.get_json())
                self.assertEqual((await response.get_json())['code'], 'already_bound')
                upstream.assert_not_awaited()

    async def capabilities_after_restart(self):
        restarted = create_app()
        try:
            client = restarted.test_client()
            response = await client.post('/api/auth/login', json={'qq_id': '10000001', 'password': PASSWORD})
            self.assertEqual(response.status_code, 200)
            response = await client.get(PREFIX + '/capabilities')
            self.assertEqual(response.status_code, 200)
            return await response.get_json()
        finally:
            executor = restarted.extensions.get('account_password_executor')
            if executor:
                executor.close()

    async def test_import_is_enabled_by_default_without_environment_setting(self):
        with patch.dict(os.environ):
            os.environ.pop('ACM_ACCOUNT_IMPORT_ENABLED', None)
            self.assertTrue((await self.capabilities_after_restart())['enabled'])
        db = await self.db()
        self.assertIsNone(await imports.row(db, "SELECT value FROM settings WHERE key='account_import_enabled'"))
        await db.close()

    async def test_environment_remains_the_unsaved_default(self):
        for value in ('false', '0', 'off', 'no'):
            with self.subTest(value=value), patch.dict(os.environ, {'ACM_ACCOUNT_IMPORT_ENABLED': value}):
                self.assertFalse((await self.capabilities_after_restart())['enabled'])

    async def test_switch_is_global_persistent_and_can_be_reenabled(self):
        response = await self.client.patch(PREFIX + '/settings', json={'enabled': False}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(await response.get_json(), {'enabled': False})
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        other, _ = await self.login('10000002')
        self.assertFalse((await (await other.get(PREFIX + '/capabilities')).get_json())['enabled'])
        self.assertEqual((await other.get(PREFIX + '/template')).status_code, 503)
        self.assertFalse((await self.capabilities_after_restart())['enabled'])
        db = await self.db()
        self.assertEqual((await imports.row(db, "SELECT value FROM settings WHERE key='account_import_enabled'"))['value'], 'false')
        await db.close()
        root, headers = await self.login('10000003')
        response = await root.patch(PREFIX + '/settings', json={'enabled': True}, headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(await response.get_json(), {'enabled': True})
        self.assertTrue((await (await other.get(PREFIX + '/capabilities')).get_json())['enabled'])
        self.assertEqual((await other.get(PREFIX + '/template')).status_code, 200)
        with patch.dict(os.environ, {'ACM_ACCOUNT_IMPORT_ENABLED': 'false'}):
            self.assertTrue((await self.capabilities_after_restart())['enabled'])

    async def test_disabled_switch_blocks_writes_but_preserves_results_reports_and_cancel(self):
        batch, rows = await self.preview([['10000084']])
        response = await self.client.patch(PREFIX + '/settings', json={'enabled': False}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        for suffix in ('', '/rows', '/report'):
            response = await self.client.get(PREFIX + '/' + batch['id'] + suffix)
            self.assertEqual(response.status_code, 200)
        response = await self.client.post(PREFIX + '/preview', headers=self.headers)
        self.assertEqual(response.status_code, 503)
        self.assertEqual((await response.get_json())['code'], 'import_disabled')
        response = await self.client.post(PREFIX + '/' + batch['id'] + '/commit', json=self.intent(rows), headers=self.headers)
        self.assertEqual(response.status_code, 503)
        db = await self.db()
        self.assertIsNone(await imports.row(db, "SELECT * FROM web_accounts WHERE qq_id='10000084'"))
        await db.close()
        response = await self.client.post(PREFIX + '/' + batch['id'] + '/cancel', json={}, headers=self.headers)
        self.assertEqual(response.status_code, 200)

    async def test_switch_requires_named_admin_and_csrf(self):
        anonymous = self.app.test_client()
        response = await anonymous.patch(PREFIX + '/settings', json={'enabled': False})
        self.assertEqual(response.status_code, 401)
        member, headers = await self.login('10000004')
        response = await member.patch(PREFIX + '/settings', json={'enabled': False}, headers=headers)
        self.assertEqual(response.status_code, 403)
        for headers in ({}, {'X-CSRF-Token': 'wrong'}):
            response = await self.client.patch(PREFIX + '/settings', json={'enabled': False}, headers=headers)
            self.assertEqual(response.status_code, 403)
        self.app.config['PLUGIN_CONFIG'].update(webui_legacy_admin_login=True, webui_admin_username='synthetic-legacy', webui_admin_password_hash='', webui_admin_password=PASSWORD)
        legacy = self.app.test_client()
        response = await legacy.post('/api/auth/login', json={'username': 'synthetic-legacy', 'password': PASSWORD})
        self.assertEqual(response.status_code, 200)
        headers = {'X-CSRF-Token': (await response.get_json())['csrf_token']}
        response = await legacy.patch(PREFIX + '/settings', json={'enabled': False}, headers=headers)
        self.assertEqual(response.status_code, 403)
        self.assertEqual((await response.get_json())['code'], 'named_admin_required')
        self.assertTrue((await (await self.client.get(PREFIX + '/capabilities')).get_json())['enabled'])

    async def test_switch_rejects_non_boolean_or_extra_fields_without_saving(self):
        for value in ({}, {'enabled': 'false'}, {'enabled': 0}, {'enabled': None}, [], False, {'enabled': False, 'role': 'root'}):
            with self.subTest(value=value):
                response = await self.client.patch(PREFIX + '/settings', json=value, headers=self.headers)
                self.assertEqual(response.status_code, 400)
                self.assertEqual((await response.get_json())['code'], 'invalid_settings')
        response = await self.client.patch(PREFIX + '/settings', data='{"enabled":', headers={**self.headers, 'Content-Type': 'application/json'})
        self.assertEqual(response.status_code, 400)
        self.assertTrue((await (await self.client.get(PREFIX + '/capabilities')).get_json())['enabled'])

    async def test_closed_and_demoted_admins_cannot_change_switch(self):
        other, headers = await self.login('10000002')
        db = await self.db()
        await db.execute("UPDATE web_accounts SET role='member' WHERE qq_id='10000002'")
        await db.execute("UPDATE users SET account_state='closed', account_epoch=account_epoch+1, closed_at=? WHERE qq_id='10000001'", (int(time.time()),))
        await db.commit()
        await db.close()
        response = await other.patch(PREFIX + '/settings', json={'enabled': False}, headers=headers)
        self.assertEqual(response.status_code, 403)
        response = await self.client.patch(PREFIX + '/settings', json={'enabled': False}, headers=self.headers)
        self.assertEqual(response.status_code, 401)
        db = await self.db()
        self.assertIsNone(await imports.row(db, "SELECT value FROM settings WHERE key='account_import_enabled'"))
        await db.close()

    async def test_switch_rechecks_actor_under_write_lock(self):
        with patch.object(imports, 'actor_snapshot', side_effect=[{}, imports.ImportError('身份已变化', 'actor_changed', 403)]):
            response = await self.client.patch(PREFIX + '/settings', json={'enabled': False}, headers=self.headers)
        self.assertEqual(response.status_code, 403)
        db = await self.db()
        self.assertIsNone(await imports.row(db, "SELECT value FROM settings WHERE key='account_import_enabled'"))
        await db.close()

    async def test_feature_switch_keeps_existing_results_readable(self):
        batch,_=await self.preview([['10000084']])
        self.app.config['ACCOUNT_IMPORT_ENABLED']=False
        self.assertEqual((await self.client.get(PREFIX+'/'+batch['id'])).status_code,200)
        self.assertEqual((await self.client.get(PREFIX+'/template')).status_code,503)

    async def test_parse_process_finishes_and_deletes_raw_upload(self):
        await self.preview([['10000084']])
        self.assertEqual(list((self.path.parent/'private'/'account-imports').glob('*.xlsx')),[])
        async def timeout(awaitable, **kwargs):
            awaitable.close()
            raise asyncio.TimeoutError
        async with self.app.app_context():
            with patch.object(imports.asyncio,'wait_for',side_effect=timeout):
                with self.assertRaises(imports.ImportError) as caught: await imports.parse_upload(workbook([['10000085']]))
        self.assertEqual(caught.exception.code,'parse_timeout')
        self.assertEqual(list((self.path.parent/'private'/'account-imports').glob('*.xlsx')),[])

    async def test_preview_expiry_does_not_create_and_old_details_are_purged_on_read(self):
        batch,rows=await self.preview([['10000084','到期应清理的昵称']])
        db=await self.db();await db.execute('UPDATE account_import_batches SET preview_expires_at=1 WHERE id=?',(batch['id'],));await db.commit();await db.close()
        response=await self.client.post(PREFIX+'/'+batch['id']+'/commit',json=self.intent(rows),headers=self.headers)
        self.assertEqual(response.status_code,410)
        db=await self.db();await db.execute('UPDATE account_import_batches SET payload_purge_at=1 WHERE id=?',(batch['id'],));await db.commit();await db.close()
        result=await(await self.client.get(PREFIX+'/'+batch['id']+'/rows')).get_json()
        self.assertEqual(result['items'][0]['name'],'')
        self.assertTrue(result['payload_purged'])

    async def test_credential_change_keeps_result_read_only_but_stops_execution(self):
        batch,rows=await self.preview([['10000084']])
        db=await self.db();await db.execute("UPDATE web_accounts SET credential_version=2 WHERE qq_id='10000001'");await db.commit();await db.close()
        client,headers=await self.login('10000001')
        data=await(await client.get(PREFIX+'/'+batch['id'])).get_json()
        self.assertTrue(data['read_only'])
        response=await client.post(PREFIX+'/'+batch['id']+'/commit',json=self.intent(rows),headers=headers)
        self.assertEqual(response.status_code,403)

    async def test_shared_legacy_root_cannot_use_personal_imports(self):
        client=self.app.test_client()
        async with client.session_transaction() as session:
            session.update(webui_legacy=True,webui_authenticated=True)
        from feat.api.acm_api import backend_api
        with patch.object(backend_api,'_legacy_login_enabled',return_value=True),patch.object(backend_api,'_admin_configured',return_value=True):
            response=await client.get(PREFIX+'/capabilities')
        self.assertEqual(response.status_code,403)
        self.assertEqual((await response.get_json())['code'],'named_admin_required')

    async def test_same_running_request_returns_202_without_second_execution(self):
        batch,rows=await self.preview([['10000084']]);intent=self.intent(rows)
        db=await self.db()
        chunk,_=await imports.acquire_chunk(db,{'qq_id':'10000001','credential_version':1},batch['id'],intent)
        await db.close()
        response=await self.client.post(PREFIX+'/'+batch['id']+'/commit',json=intent,headers=self.headers)
        self.assertEqual(response.status_code,202)
        self.assertEqual((await response.get_json())['credentials'],[])
        changed={**intent,'idempotency_key':secrets.token_hex(16)}
        response=await self.client.post(PREFIX+'/'+batch['id']+'/commit',json=changed,headers=self.headers)
        self.assertEqual(response.status_code,409)

    async def test_import_nickname_survives_real_rebinding_unbinding_and_restarts(self):
        client, headers = await self.imported_member_login()
        self.app.config['PLUGIN_CONFIG']['_account_sync_submitter'] = lambda *args: {'id': 'synthetic-sync'}
        with patch.object(binding_service, 'validate_account', AsyncMock(return_value='Changed84')):
            response = await client.post('/api/me/bindings/cf/verification', headers=headers,
                                         json={'account': 'Changed84'})
        self.assertEqual(response.status_code, 200, await response.get_json())
        pending = await response.get_json()
        body = {'verification_id': pending['verification_id'], 'password': PASSWORD,
                'confirmed': True, 'current_account': 'Demo84'}
        with patch.object(binding_service, 'verify_ownership', AsyncMock(return_value=True)):
            response = await client.post('/api/me/bindings/cf/confirm', headers=headers, json=body)
        self.assertEqual(response.status_code, 202, await response.get_json())
        for operation in ('rebind', 'unbind'):
            if operation == 'unbind':
                response = await client.delete('/api/me/bindings/cf', headers=headers,
                                               json={'password': PASSWORD, 'confirmed': True,
                                                     'current_account': 'Changed84'})
                self.assertEqual(response.status_code, 200, await response.get_json())
            for _ in range(2):
                db = await connect_db(self.path)
                try:
                    user = await imports.row(db, "SELECT * FROM users WHERE qq_id='10000084'")
                    self.assertEqual(user['name'], '10000084')
                    self.assertEqual(user['cf_handle'], 'Changed84' if operation == 'rebind' else None)
                    source = await imports.row(db, "SELECT * FROM binding_provenance WHERE qq_id='10000084'")
                    if operation == 'rebind':
                        self.assertEqual(source['source'], 'member_verified')
                    else:
                        self.assertIsNone(source)
                finally:
                    await db.close()

    async def test_explicit_qq_nickname_and_admin_rebinding_survive_restarts(self):
        await self.imported_member_login(nickname='10000084')
        db = await self.db()
        try:
            await db.execute("UPDATE users SET cf_handle='Changed84' WHERE qq_id='10000084'")
            await db.commit()
            self.assertIsNone(await imports.row(db, "SELECT * FROM binding_provenance WHERE qq_id='10000084'"))
        finally:
            await db.close()
        for _ in range(2):
            db = await connect_db(self.path)
            try:
                self.assertEqual((await imports.row(db, "SELECT name FROM users WHERE qq_id='10000084'"))['name'], '10000084')
            finally:
                await db.close()

    async def test_real_timeout_terminates_parser_process(self):
        processes=[]
        real_spawn=asyncio.create_subprocess_exec;real_wait=asyncio.wait_for
        async def spawn(*args,**kwargs):
            process=await real_spawn(*args,**kwargs);processes.append(process);return process
        async def short_wait(awaitable,**kwargs):return await real_wait(awaitable,timeout=.001)
        async with self.app.app_context():
            with patch.object(imports.asyncio,'create_subprocess_exec',side_effect=spawn),patch.object(imports.asyncio,'wait_for',side_effect=short_wait):
                with self.assertRaises(imports.ImportError):await imports.parse_upload(workbook([['10000084']]))
        self.assertEqual(len(processes),1)
        self.assertIsNotNone(processes[0].returncode)


class NicknameMigrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_legacy_empty_names_are_backfilled_once_and_qq_names_are_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'legacy.db'
            async with aiosqlite.connect(path) as db:
                await db.execute('CREATE TABLE users(qq_id TEXT PRIMARY KEY, name TEXT, cf_handle TEXT, luogu_id TEXT, nowcoder_id TEXT, atcoder_handle TEXT, status TEXT, school TEXT, last_sync_timestamp INTEGER DEFAULT 0)')
                await db.executemany('INSERT INTO users(qq_id,name,cf_handle) VALUES(?,?,?)', [
                    ('10000081', '', 'Legacy81'), ('10000082', None, None),
                    ('10000083', '10000083', 'Chosen83'), ('10000084', 'Chosen nickname', 'Demo84'),
                ])
                await db.commit()
            db = await connect_db(path)
            try:
                async with db.execute('SELECT qq_id,name FROM users ORDER BY qq_id') as cursor:
                    self.assertEqual([tuple(row) for row in await cursor.fetchall()], [
                        ('10000081', 'Legacy81'), ('10000082', '10000082'),
                        ('10000083', '10000083'), ('10000084', 'Chosen nickname'),
                    ])
                await db.execute("UPDATE users SET name='' WHERE qq_id='10000081'")
                await db.execute("INSERT INTO users(qq_id,name,cf_handle) VALUES('10000085','10000085','New85')")
                await db.commit()
            finally:
                await db.close()
            for _ in range(2):
                db = await connect_db(path)
                try:
                    async with db.execute('SELECT qq_id,name FROM users ORDER BY qq_id') as cursor:
                        self.assertEqual([tuple(row) for row in await cursor.fetchall()], [
                            ('10000081', ''), ('10000082', '10000082'),
                            ('10000083', '10000083'), ('10000084', 'Chosen nickname'),
                            ('10000085', '10000085'),
                        ])
                finally:
                    await db.close()
