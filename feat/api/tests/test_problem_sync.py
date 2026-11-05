"""Server initialization and administrator problem collection contracts."""

import asyncio
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import AsyncExitStack, closing
from pathlib import Path
from unittest.mock import patch

from feat.api.acm_api.auth_service import hash_password
from feat.api.acm_api.contest_metadata import save_contests
from feat.api.acm_api.database import connect_db
from feat.api.acm_api.problem_bank import save_metadata_batch, save_problem
from feat.api.acm_api.problem_content import parse_atcoder, parse_atcoder_tasks, parse_codeforces
from feat.api.acm_api.problem_sync import ATCODER_CATALOG_URL, atcoder_catalog_metadata, cf_catalog_metadata, sync_options
from feat.api.app import create_app


LISTING = b'''<table><tbody>
<tr><td><a href="/contests/abc370/tasks/abc370_a">A</a></td>
<td><a href="/contests/abc370/tasks/abc370_a">Raise Both Hands</a></td></tr>
<tr><td><a href="/contests/abc370/tasks/abc370_b">B</a></td>
<td><a href="/contests/abc370/tasks/abc370_b">Binary Alchemy</a></td></tr>
</tbody></table>'''
BODY = b'''<div id="task-statement"><span class="lang-en">
<h3>Problem Statement</h3><p>Solve the problem.</p>
<h3>Sample Input 1</h3><pre>1 0\n</pre>
<h3>Sample Output 1</h3><pre>Yes\n</pre></span></div>'''
CF_BODY = b'''<div class="problem-statement"><div class="header"><div class="title">A. Example</div></div>
<p>Solve $$$x &lt; y$$$.</p><div class="sample-test">
<div class="input"><div class="title">Input</div><pre>
<div class="test-example-line"> 1 2</div><div class="test-example-line">3 4 </div></pre></div>
<div class="output"><div class="title">Output</div><pre>5<br>6<br></pre></div>
</div></div>'''

CF_NO_SAMPLES = b'''<div class="problem-statement"><p>Print the name of the language.</p>
<div class="input-specification"><p>This test is empty.</p></div><div class="sample-test"></div></div>'''
CF_UNRECOGNIZED_SAMPLES = CF_NO_SAMPLES.replace(
    b'<div class="sample-test"></div>',
    b'<div class="sample-test"><div class="unknown"><pre>1\n2\n</pre></div></div>',
)


def sample_pdf():
    """A self-contained one-page PDF fixture, with no network or PDF package dependency."""
    stream = b'BT /F1 12 Tf 72 720 Td (Synthetic statement and sample: OK) Tj ET'
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>', b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
               b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>',
               b'<< /Length ' + str(len(stream)).encode() + b' >>\nstream\n' + stream + b'\nendstream',
               b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
    raw, offsets = b'%PDF-1.4\n', [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(raw))
        raw += str(index).encode() + b' 0 obj\n' + obj + b'\nendobj\n'
    start = len(raw)
    raw += b'xref\n0 6\n0000000000 65535 f \n'
    raw += b''.join(f'{offset:010d} 00000 n \n'.encode() for offset in offsets[1:])
    return raw + f'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n'.encode()


CF_PDF = sample_pdf()

CATALOG = [{"id": "abc370_a", "contest_id": "abc370", "problem_index": "A", "name": "First"},
           {"id": "abc371_a", "contest_id": "abc371", "problem_index": "A", "name": "Second"},
           {"id": "abc372_a", "contest_id": "abc372", "problem_index": "A", "name": "Third"}]


class TaskListTests(unittest.TestCase):
    def test_cf_empty_sample_container_is_valid_but_incomplete_pairs_remain_invalid(self):
        for empty in [b'', b' \n\t', b' \n<!-- No examples -->\n']:
            raw = CF_NO_SAMPLES.replace(b'class="sample-test">', b'class="sample-test">' + empty)
            with self.subTest(empty=empty):
                self.assertEqual(parse_codeforces(raw, 'https://codeforces.com/contest/171/problem/E')['samples'], [])
        empty_input = CF_BODY.replace(b'<div class="test-example-line"> 1 2</div><div class="test-example-line">3 4 </div>', b'')
        self.assertEqual(parse_codeforces(empty_input, 'https://codeforces.com')['samples'][0]['input'], '')
        for raw in [b'<div class="problem-statement"><div class="sample-test"><div class="output"><pre>x</pre></div></div></div>',
                    b'<div class="problem-statement"><div class="sample-test"><div class="input">missing pre</div></div></div>']:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                parse_codeforces(raw, 'https://codeforces.com')

    def test_cf_nonempty_unrecognized_sample_containers_are_rejected(self):
        for child in [b'1 2', b'<pre>1\n2\n</pre>', b'<div></div>', b'<img src="sample.png">',
                      b'<script>sample()</script>', b'<style>.sample {}</style>']:
            raw = CF_NO_SAMPLES.replace(b'class="sample-test">', b'class="sample-test">' + child)
            with self.subTest(child=child), self.assertRaisesRegex(ValueError, 'CF 样例区非空'):
                parse_codeforces(raw, 'https://codeforces.com')
        valid_then_broken = CF_BODY.rsplit(b'</div>', 1)[0] + b'<div class="sample-test"><pre>3</pre></div></div>'
        for raw in [CF_UNRECOGNIZED_SAMPLES, valid_then_broken]:
            with self.subTest(raw=raw), self.assertRaisesRegex(ValueError, 'CF 样例区非空'):
                parse_codeforces(raw, 'https://codeforces.com')

    def test_cf_pdf_is_preserved_as_bytes_and_truncated_documents_are_rejected(self):
        content = parse_codeforces(CF_PDF, 'https://codeforces.com/contest/497/problem/D')
        self.assertEqual(content['statement_pdf'], CF_PDF)
        self.assertIsNone(content['statement_html'])
        self.assertEqual(content['samples'], [])
        for raw in [CF_PDF[:-20], b'%PDF-invalid\n%%EOF', b'%PDF-1.4\n' + b'x' * (20 * 1024 * 1024) + b'%%EOF']:
            with self.subTest(length=len(raw)), self.assertRaises(ValueError):
                parse_codeforces(raw, 'https://codeforces.com')

    def test_historical_cf_numeric_indices_are_kept_in_the_catalog_and_explicit_requests(self):
        items = cf_catalog_metadata([{"contestId": 921, "index": index, "name": "Example"} for index in ("01", "14")])
        self.assertEqual([row["problem_id"] for row in items], ["cf_92101", "cf_92114"])
        self.assertEqual(items[0]["problem_url"], "https://codeforces.com/contest/921/problem/01")
        options = sync_options({"platform": "codeforces", "contest_id": 921, "problem_ids": ["92101", "cf_92114"]})
        self.assertEqual(options["problem_ids"], ["cf_92101", "cf_92114"])

    def test_cf_samples_preserve_modern_line_divs_old_breaks_and_multiple_pairs(self):
        parsed = parse_codeforces(CF_BODY, "https://codeforces.com/contest/1843/problem/A")
        self.assertEqual(parsed["samples"], [{"index": 1, "input": " 1 2\n3 4 \n", "output": "5\n6\n"}])
        self.assertIn("$$$x &lt; y$$$", parsed["statement_html"])
        extra = b'<div class="input"><pre>7\n</pre></div><div class="output"><pre>8\n</pre></div>'
        head, tail = CF_BODY.rsplit(b"</div></div>", 1)
        raw = head + extra + b"</div></div>" + tail
        self.assertEqual(len(parse_codeforces(raw, "https://codeforces.com")["samples"]), 2)
        with self.assertRaises(ValueError):
            parse_codeforces(b"<h1>Access denied</h1>", "https://codeforces.com")
        with self.assertRaises(ValueError):
            parse_codeforces(b'<div class="problem-statement"><div class="sample-test"><div class="input"><pre>1</pre></div></div></div>', "https://codeforces.com")

    def test_list_resolves_names_and_ignores_external_or_other_contest_links(self):
        invalid_row = b'<tr><td><a href="https://other.example/contests/abc370/tasks/abc370_c">C</a></td></tr>'
        items = parse_atcoder_tasks(LISTING.replace(b"</tbody>", invalid_row + b"</tbody>"), "abc370")
        self.assertEqual([item["problem_id"] for item in items], ["abc370_a", "abc370_b"])
        self.assertEqual(items[0]["problem_name"], "Raise Both Hands")
        self.assertEqual(items[0]["problem_index"], "A")
        with self.assertRaises(ValueError):
            parse_atcoder_tasks(LISTING, "abc001")
        with self.assertRaises(ValueError):
            parse_atcoder_tasks(b"<h1>Login</h1>", "abc370")


class ProblemSyncTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        asyncio.get_running_loop().slow_callback_duration = 1
        # Contest-date refresh is covered separately; existing fixtures only
        # model statement/catalog downloads and must never reach the network.
        self.contest_refresh = patch("feat.api.acm_api.problem_sync.refresh_contests", return_value=0)
        self.contest_refresh.start()
        self.addCleanup(self.contest_refresh.stop)
        self.directory = tempfile.TemporaryDirectory()
        self.db_path = Path(self.directory.name) / "server.db"
        self.env = patch.dict(os.environ, {
            "ACM_DATABASE_PATH": str(self.db_path), "ACM_WEBUI_SECRET_KEY": "test-only-secret",
        })
        self.env.start()
        self.app = create_app()
        db = await connect_db(self.db_path)
        try:
            now = int(time.time())
            await db.execute("INSERT INTO users(qq_id,name) VALUES('12345678','Administrator')")
            await db.execute(
                "INSERT INTO web_accounts(qq_id,password_hash,role,must_change_password,is_active,"
                "credential_version,created_at,updated_at) VALUES('12345678',?,'admin',0,1,1,?,?)",
                (hash_password("Test-Password-123!"), now, now),
            )
            await db.commit()
        finally:
            await db.close()

    async def asyncTearDown(self):
        await self.app.task_manager.close()
        self.env.stop()
        self.directory.cleanup()

    async def login(self, client):
        response = await client.post("/api/auth/login", json={"qq_id": "12345678", "password": "Test-Password-123!"})
        self.assertEqual(response.status_code, 200)
        return {"X-CSRF-Token": (await response.get_json())["csrf_token"]}

    async def query(self, sql, parameters=()):
        db = await connect_db(self.db_path)
        try:
            async with db.execute(sql, parameters) as cursor:
                return [dict(row) for row in await cursor.fetchall()]
        finally:
            await db.close()

    async def write(self, sql):
        db = await connect_db(self.db_path)
        try:
            await db.execute(sql)
            await db.commit()
        finally:
            await db.close()

    async def submit(self, client, headers, **options):
        response = await client.post("/api/admin/problems/sync", json={"contest_id": "abc370", **options}, headers=headers)
        self.assertEqual(response.status_code, 202, await response.get_json())
        task_id = (await response.get_json())["task"]["id"]
        await self.app.task_manager.tasks[task_id]["_task"]
        snapshots = await (await client.get("/api/tasks")).get_json()
        return next(task for task in snapshots if task["id"] == task_id)

    async def submit_platform(self, client, headers, **options):
        response = await client.post("/api/admin/problems/sync", json={"scope": "platform", **options}, headers=headers)
        self.assertEqual(response.status_code, 202, await response.get_json())
        task_id = (await response.get_json())["task"]["id"]
        await self.app.task_manager.tasks[task_id]["_task"]
        return next(task for task in self.app.task_manager.snapshots() if task["id"] == task_id)

    async def test_cf_no_samples_and_pdf_succeed_skip_on_resume_and_survive_failed_refresh(self):
        metadata = {'problems': [{'contestId': 171, 'index': 'E', 'name': 'No samples'},
                                 {'contestId': 497, 'index': 'D', 'name': 'PDF statement'}]}
        async def download(http, url):
            return CF_NO_SAMPLES if '/171/' in url else CF_PDF
        async with self.app.test_app():
            client = self.app.test_client()
            headers = await self.login(client)
            with patch('feat.api.acm_api.problem_sync.cf_request', return_value=metadata), patch.object(self.app.task_manager.problem_sync, 'download', side_effect=download) as fetch:
                task = await self.submit_platform(client, headers, platform='codeforces', batch_size=1)
                self.assertEqual(task['status'], 'completed')
                self.assertEqual(task['result']['success_count'], 2)
                self.assertEqual(task['result']['failure_count'], 0)
                resumed = await self.submit_platform(client, headers, platform='codeforces')
                self.assertEqual(resumed['result']['skipped_count'], 2)
                self.assertEqual(fetch.await_count, 2)
            status = await (await client.get('/api/admin/database')).get_json()
            self.assertEqual(status['platforms'][0]['collected'], 2)
            for pid, fmt in [('cf_171E', 'html'), ('cf_497D', 'pdf')]:
                detail = await (await client.get('/api/problems/codeforces/' + pid)).get_json()
                self.assertTrue(detail['content_available'])
                self.assertEqual(detail['statement_format'], fmt)
                self.assertEqual(detail['samples'], [])
            pdf_metadata = {'problems': [metadata['problems'][1]]}
            with patch('feat.api.acm_api.problem_sync.cf_request', return_value=pdf_metadata), patch.object(self.app.task_manager.problem_sync, 'download', return_value=CF_PDF[:-20]):
                failed = await self.submit(client, headers, platform='codeforces', contest_id=497, refresh=True)
            self.assertEqual(failed['status'], 'failed')
            detail = await (await client.get('/api/problems/codeforces/cf_497D')).get_json()
            self.assertTrue(detail['content_available'])
            self.assertEqual(detail['last_fetch_status'], 'failed')
            self.assertEqual(await (await client.get('/api/problems/codeforces/cf_497D/statement.pdf')).get_data(), CF_PDF)

    async def test_cf_unrecognized_samples_fail_preserve_old_content_and_retry_without_refresh(self):
        catalog = {'problems': [{'contestId': 171, 'index': 'E', 'name': 'Previously empty'},
                                {'contestId': 1843, 'index': 'A', 'name': 'First collection'}]}
        metadata = cf_catalog_metadata(catalog['problems'])[0]
        content = parse_codeforces(CF_NO_SAMPLES, metadata['problem_url'])
        db = await connect_db(self.db_path)
        try:
            await save_problem(db, metadata, {**content, 'requested_language': 'en',
                'source_url': metadata['problem_url'], 'sha256': 'previous-empty-samples'})
        finally:
            await db.close()
        async with self.app.test_app():
            client = self.app.test_client()
            headers = await self.login(client)
            with patch('feat.api.acm_api.problem_sync.cf_request', return_value=catalog):
                with patch.object(self.app.task_manager.problem_sync, 'download', return_value=CF_UNRECOGNIZED_SAMPLES) as fetch:
                    failed = await self.submit_platform(client, headers, platform='codeforces', refresh=True)
                    self.assertEqual(fetch.await_count, 2)
                self.assertEqual(failed['status'], 'failed')
                self.assertEqual(failed['result']['success_count'], 0)
                self.assertEqual(failed['result']['failure_count'], 2)
                rows = {row['problem_id']: row for row in await self.query('SELECT * FROM crawler_problems')}
                for row in rows.values():
                    self.assertEqual(row['last_fetch_status'], 'failed')
                    self.assertIn('CF 样例区非空', row['last_error'])
                    self.assertEqual(json.loads(row['samples']), [])
                    self.assertEqual(row['sample_count'], 0)
                self.assertEqual(rows['cf_171E']['statement_html'], content['statement_html'])
                self.assertEqual(rows['cf_171E']['statement_sha256'], 'previous-empty-samples')
                self.assertIsNone(rows['cf_1843A']['statement_html'])
                self.assertIsNone(rows['cf_1843A']['statement_sha256'])
                with patch.object(self.app.task_manager.problem_sync, 'download', return_value=CF_BODY) as fetch:
                    resumed = await self.submit_platform(client, headers, platform='codeforces')
                    self.assertEqual(fetch.await_count, 2)
            self.assertEqual(resumed['status'], 'completed')
            self.assertEqual(resumed['result']['success_count'], 2)
            self.assertEqual(resumed['result']['skipped_count'], 0)
            expected = parse_codeforces(CF_BODY, 'https://codeforces.com')['samples']
            for row in await self.query('SELECT last_fetch_status,samples,sample_count,last_error FROM crawler_problems'):
                self.assertEqual(row['last_fetch_status'], 'ok')
                self.assertEqual(json.loads(row['samples']), expected)
                self.assertEqual(row['sample_count'], 1)
                self.assertIsNone(row['last_error'])

    async def test_pdf_delivery_uses_saved_bytes_ranges_and_existing_role_and_password_guards(self):
        metadata = {'platform': 'codeforces', 'problem_id': 'cf_497D', 'contest_id': '497',
                    'problem_name': 'PDF', 'problem_url': 'https://codeforces.com/contest/497/problem/D'}
        db = await connect_db(self.db_path)
        try:
            await save_problem(db, metadata, {**parse_codeforces(CF_PDF, metadata['problem_url']),
                'requested_language': 'en', 'source_url': metadata['problem_url'], 'sha256': 'test-pdf'})
        finally:
            await db.close()
        async with self.app.test_app():
            client = self.app.test_client()
            path = '/api/problems/codeforces/cf_497D/statement.pdf'
            member_path = path.replace('/problems/', '/me/problems/')
            self.assertEqual((await client.get(path)).status_code, 401)
            self.assertEqual((await client.get(member_path)).status_code, 401)
            await self.login(client)
            with patch.object(self.app.task_manager.problem_sync, 'download') as fetch:
                response = await client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.mimetype, 'application/pdf')
                self.assertEqual(await response.get_data(), CF_PDF)
                self.assertEqual(response.headers['Cache-Control'], 'no-store')
                self.assertIn('inline;', response.headers['Content-Disposition'])
                self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')
                self.assertEqual(response.headers['X-Frame-Options'], 'DENY')
                self.assertIn("frame-ancestors 'none'", response.headers['Content-Security-Policy'])
                self.assertEqual((await client.get('/problem.html')).headers['X-Frame-Options'], 'DENY')
                self.assertIn("frame-ancestors 'none'", (await client.get('/problem.html')).headers['Content-Security-Policy'])
                partial = await client.get(path, headers={'Range': 'bytes=0-9'})
                self.assertEqual(partial.status_code, 206)
                self.assertEqual(partial.headers['X-Frame-Options'], 'DENY')
                self.assertEqual(await partial.get_data(), CF_PDF[:10])
                self.assertEqual((await client.get(path.replace('cf_497D', 'missing'))).status_code, 404)
                self.assertEqual((await client.get(path, headers={'Range': 'bytes=999999-'})).status_code, 416)
                await self.write("UPDATE web_accounts SET role='member'")
                self.assertEqual((await client.get(path)).status_code, 403)
                member_pdf = await client.get(member_path)
                self.assertEqual(await member_pdf.get_data(), CF_PDF)
                self.assertEqual(member_pdf.headers['X-Frame-Options'], 'DENY')
                await self.write('UPDATE web_accounts SET must_change_password=1')
                self.assertEqual((await client.get(member_path)).status_code, 428)
                fetch.assert_not_called()

    async def test_pdf_preview_assets_include_worker_modules_and_scoped_font_resources(self):
        dist = Path(self.directory.name) / 'web-dist'
        assets = dist / 'assets'
        (assets / 'pdfjs' / 'standard_fonts').mkdir(parents=True)
        (assets / 'pdfjs' / 'cmaps').mkdir()
        fixtures = {'pdf.worker-test.mjs': b'export const worker = true;',
                    'pdfjs/standard_fonts/font.pfb': b'font-bytes',
                    'pdfjs/standard_fonts/font.ttf': b'ttf-bytes',
                    'pdfjs/cmaps/test.bcmap': b'cmap-bytes'}
        for name, raw in fixtures.items():
            (assets / name).write_bytes(raw)
        (assets / 'unrelated.pfb').write_bytes(b'not-a-preview-asset')
        self.app.config['WEBUI_DIST_DIR'] = dist
        async with self.app.test_app():
            client = self.app.test_client()
            for name, raw in fixtures.items():
                response = await client.get('/assets/' + name)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(await response.get_data(), raw)
                if name.endswith('.mjs'):
                    self.assertEqual(response.mimetype, 'text/javascript')
            self.assertEqual((await client.get('/assets/unrelated.pfb')).status_code, 404)

    async def test_existing_database_gets_pdf_column_without_losing_html_or_samples(self):
        metadata = {'platform': 'atcoder', 'problem_id': 'abc370_a', 'contest_id': 'abc370',
                    'problem_name': 'Old body', 'problem_url': 'https://atcoder.jp/contests/abc370/tasks/abc370_a'}
        db = await connect_db(self.db_path)
        try:
            await save_problem(db, metadata, {**parse_atcoder(BODY, metadata['problem_url']),
                'requested_language': 'en', 'source_url': metadata['problem_url'], 'sha256': 'old-hash'})
        finally:
            await db.close()
        with closing(sqlite3.connect(self.db_path)) as legacy:
            with legacy:
                legacy.execute('ALTER TABLE crawler_problems DROP COLUMN statement_pdf')
        for _ in range(2):
            rows = await self.query('SELECT statement_pdf,statement_sha256,sample_count FROM crawler_problems')
            self.assertIsNone(rows[0]['statement_pdf'])
            self.assertEqual(rows[0]['statement_sha256'], 'old-hash')
            self.assertEqual(rows[0]['sample_count'], 1)

    async def test_sync_requires_login_admin_csrf_and_password_change(self):
        async with self.app.test_app():
            client = self.app.test_client()
            payload = {"contest_id": "abc370"}
            self.assertEqual((await client.post("/api/admin/problems/sync", json=payload)).status_code, 401)
            headers = await self.login(client)
            self.assertEqual((await client.post("/api/admin/problems/sync", json=payload)).status_code, 403)
            await self.write("UPDATE web_accounts SET role='member' WHERE qq_id='12345678'")
            self.assertEqual((await client.post("/api/admin/problems/sync", json=payload, headers=headers)).status_code, 403)
            await self.write("UPDATE web_accounts SET role='root',must_change_password=1 WHERE qq_id='12345678'")
            self.assertEqual((await client.post("/api/admin/problems/sync", json=payload, headers=headers)).status_code, 428)
            self.assertEqual(self.app.task_manager.tasks, {})

    async def test_local_detail_returns_saved_statement_and_samples_for_admin_and_member(self):
        metadata = {"platform": "codeforces", "problem_id": "cf_1843A", "contest_id": "1843",
                    "problem_name": "Example", "problem_url": "https://codeforces.com/contest/1843/problem/A",
                    "problem_rating": 800, "tags": ["math"]}
        content = parse_codeforces(CF_BODY, metadata["problem_url"])
        db = await connect_db(self.db_path)
        try:
            await save_problem(db, metadata, {**content, "requested_language": "en", "source_url": metadata["problem_url"], "sha256": "test-body"})
        finally:
            await db.close()
        async with self.app.test_app():
            client = self.app.test_client()
            path = "/api/problems/codeforces/cf_1843A"
            self.assertEqual((await client.get(path)).status_code, 401)
            self.assertEqual((await client.get(path.replace('/problems/', '/me/problems/'))).status_code, 401)
            self.assertEqual((await client.get('/problem.html?platform=codeforces&problem_id=cf_1843A')).status_code, 302)
            await self.login(client)
            response = await client.get(path)
            self.assertEqual(response.status_code, 200)
            detail = await response.get_json()
            self.assertTrue(detail["content_available"])
            self.assertEqual(detail["statement_html"], content["statement_html"])
            self.assertEqual(detail["samples"], content["samples"])
            self.assertEqual(detail["tags"], ["math"])
            self.assertEqual(detail["problem_url"], metadata["problem_url"])
            self.assertEqual(response.headers["Cache-Control"], "no-store")
            await self.write("UPDATE crawler_problems SET last_fetch_status='failed'")
            self.assertTrue((await (await client.get(path)).get_json())["content_available"])
            await self.write("UPDATE web_accounts SET role='member'")
            self.assertEqual((await client.get(path)).status_code, 403)
            member = await client.get(path.replace('/problems/', '/me/problems/'))
            self.assertEqual(member.status_code, 200)
            self.assertEqual((await member.get_json())["samples"], content["samples"])
            self.assertEqual((await member.get_json())["problem_url"], metadata["problem_url"])
            page = await client.get('/problem.html?platform=codeforces&problem_id=cf_1843A')
            self.assertEqual(page.status_code, 200)
            self.assertIn('https://img.atcoder.jp', page.headers['Content-Security-Policy'])
            self.assertNotIn('https://img.atcoder.jp', (await client.get('/home.html')).headers['Content-Security-Policy'])
            await self.write("UPDATE web_accounts SET must_change_password=1")
            self.assertEqual((await client.get(path.replace('/problems/', '/me/problems/'))).status_code, 428)

    async def test_local_detail_distinguishes_pending_catalog_and_missing_problem_without_fetching(self):
        metadata = {"platform": "atcoder", "problem_id": "abc370_a", "contest_id": "abc370",
                    "problem_name": "Pending", "problem_url": "https://atcoder.jp/contests/abc370/tasks/abc370_a"}
        db = await connect_db(self.db_path)
        try:
            await save_metadata_batch(db, [metadata])
        finally:
            await db.close()
        async with self.app.test_app():
            client = self.app.test_client()
            await self.login(client)
            with patch.object(self.app.task_manager.problem_sync, "download") as download:
                for crawler_row in (True, False):
                    if not crawler_row:
                        await self.write("DELETE FROM crawler_problems")
                    response = await client.get('/api/problems/atcoder/abc370_a')
                    self.assertEqual(response.status_code, 200)
                    detail = await response.get_json()
                    self.assertFalse(detail["content_available"])
                    self.assertEqual(detail["problem_name"], "Pending")
                    self.assertEqual(detail["samples"], [])
                    self.assertEqual(detail["last_fetch_status"], "never")
                    self.assertEqual(detail["problem_url"], metadata["problem_url"])
                self.assertEqual((await client.get('/api/problems/atcoder/missing')).status_code, 404)
                download.assert_not_called()
                self.assertEqual(self.app.task_manager.tasks, {})

    async def test_invalid_payloads_do_not_start_network_tasks(self):
        async with self.app.test_app():
            client = self.app.test_client()
            headers = await self.login(client)
            payloads = [None, [], {}, {"contest_id": "../other"},
                        {"contest_id": "abc370", "platform": "codeforces"},
                        {"contest_id": "abc370", "limit": True},
                        {"contest_id": "abc370", "limit": 101},
                        {"contest_id": "abc370", "language": []},
                        {"contest_id": "abc370", "refresh": "true"},
                        {"contest_id": "abc370", "problem_ids": "abc370_a"},
                        {"contest_id": "abc370", "problem_ids": ["https://other.example"]},
                        {"contest_id": "abc370", "items": []}]
            payloads += [{"platform": "codeforces", "contest_id": True},
                         {"platform": "codeforces", "contest_id": 100001},
                         {"platform": "codeforces", "contest_id": 1843, "problem_ids": ["1844A"]},
                         {"platform": "codeforces", "contest_id": 1843, "language": "ja"}]
            for payload in payloads:
                with self.subTest(payload=payload):
                    response = await client.post("/api/admin/problems/sync", json=payload, headers=headers)
                    self.assertEqual(response.status_code, 400)
                    self.assertEqual((await response.get_json())["code"], "invalid_request")
            self.assertEqual(self.app.task_manager.tasks, {})

    async def test_limited_sync_resumes_and_new_problems_are_visible_in_catalog(self):
        async def download(http, url):
            return LISTING if "/tasks?" in url else BODY
        async with AsyncExitStack() as stack:
            await stack.enter_async_context(self.app.test_app())
            fetch = stack.enter_context(patch.object(self.app.task_manager.problem_sync, "download", side_effect=download))
            client = self.app.test_client()
            headers = await self.login(client)
            for expected_skips in (0, 1):
                task = await self.submit(client, headers, limit=1)
                self.assertEqual(task["status"], "completed")
                self.assertEqual(task["result"]["success_count"], 1)
                self.assertEqual(task["result"]["skipped_count"], expected_skips)
            task = await self.submit(client, headers, limit=1)
            self.assertEqual(task["result"]["skipped_count"], 2)
            self.assertEqual(task["result"]["selected_count"], 0)
            self.assertEqual(fetch.await_count, 5)
            rows = await self.query("SELECT * FROM crawler_problems ORDER BY problem_id")
            self.assertEqual(len(rows), 2)
            self.assertEqual(json.loads(rows[0]["samples"]), [{"index": 1, "input": "1 0\n", "output": "Yes\n"}])
            self.assertIn("Sample Input 1", rows[0]["statement_html"])
            data = await (await client.get("/api/problems?platform=atcoder")).get_json()
            self.assertEqual(data["total"], 2)
            self.assertEqual({row["problem_name"] for row in data["items"]}, {"Raise Both Hands", "Binary Alchemy"})

    async def test_failed_refresh_preserves_previous_body_samples_and_catalog(self):
        async with self.app.test_app():
            client = self.app.test_client()
            headers = await self.login(client)
            with patch.object(self.app.task_manager.problem_sync, "download", side_effect=[LISTING, BODY]):
                await self.submit(client, headers, problem_ids=["abc370_a"])
            old = (await self.query("SELECT statement_html,samples,statement_sha256 FROM crawler_problems"))[0]
            for broken_page in (b"<h1>Sign in</h1>", b'<div id="task-statement"><p>Incomplete replacement</p></div>'):
                with patch.object(self.app.task_manager.problem_sync, "download", side_effect=[LISTING, broken_page]):
                    task = await self.submit(client, headers, problem_ids=["abc370_a"], refresh=True)
                self.assertEqual(task["status"], "failed")
                self.assertEqual(task["result"]["failure_count"], 1)
                self.assertEqual((await self.query("SELECT statement_html,samples,statement_sha256 FROM crawler_problems"))[0], old)
            self.assertEqual((await self.query("SELECT last_fetch_status FROM crawler_problems"))[0]["last_fetch_status"], "failed")
            self.assertEqual(len(await self.query("SELECT * FROM recommendations")), 1)

    async def test_cf_sync_normalizes_ids_and_updates_existing_catalog_without_duplicates(self):
        metadata = {"problems": [{"contestId": 1843, "index": "A", "name": "CF Example",
                                 "rating": 800, "tags": ["math"]}]}
        async with self.app.test_app():
            client = self.app.test_client()
            headers = await self.login(client)
            with patch("feat.api.acm_api.problem_sync.cf_request", return_value=metadata) as request_cf:
                with patch.object(self.app.task_manager.problem_sync, "download", return_value=CF_BODY) as fetch:
                    task = await self.submit(client, headers, platform="codeforces", contest_id=1843, problem_ids=["1843A", "cf_1843A"])
                    self.assertEqual(task["status"], "completed")
                    self.assertEqual(task["platform"], "codeforces")
                    self.assertEqual(task["result"]["success_count"], 1)
                    await self.submit(client, headers, platform="codeforces", contest_id="1843", problem_ids=["cf_1843A"])
                    self.assertEqual(fetch.await_count, 1)
                self.assertEqual(request_cf.await_args.args[1:], ("contest.standings", {"contestId": 1843}))
            rows = await self.query("SELECT * FROM crawler_problems")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["problem_id"], "cf_1843A")
            self.assertEqual(json.loads(rows[0]["samples"])[0]["input"], " 1 2\n3 4 \n")
            catalog = await (await client.get("/api/problems?platform=codeforces")).get_json()
            self.assertEqual(catalog["total"], 1)
            self.assertEqual(catalog["items"][0]["problem_rating"], "800")

    async def test_partial_failure_continues_and_unknown_ids_do_not_write(self):
        async with self.app.test_app():
            client = self.app.test_client()
            headers = await self.login(client)
            with patch.object(self.app.task_manager.problem_sync, "download", side_effect=[LISTING]):
                task = await self.submit(client, headers, problem_ids=["abc370_z"])
                self.assertEqual(task["status"], "failed")
                self.assertIn("不存在", task["result"]["error"])
            self.assertEqual(await self.query("SELECT * FROM crawler_problems"), [])
            with patch.object(self.app.task_manager.problem_sync, "download", side_effect=[LISTING, b"<h1>Sign in</h1>", BODY]):
                task = await self.submit(client, headers)
            self.assertEqual(task["status"], "partial")
            self.assertEqual((task["result"]["success_count"], task["result"]["failure_count"]), (1, 1))
            self.assertEqual((await self.query("SELECT problem_id FROM crawler_problems"))[0]["problem_id"], "abc370_b")

    async def test_same_task_merges_different_task_is_busy_and_cancel_stops_it(self):
        started = asyncio.Event()
        blocker = asyncio.Event()
        async def download(http, url):
            started.set()
            await blocker.wait()
            return LISTING
        async with AsyncExitStack() as stack:
            await stack.enter_async_context(self.app.test_app())
            stack.enter_context(patch.object(self.app.task_manager.problem_sync, "download", side_effect=download))
            client = self.app.test_client()
            headers = await self.login(client)
            payload = {"contest_id": "abc370"}
            response = await client.post("/api/admin/problems/sync", json=payload, headers=headers)
            task_id = (await response.get_json())["task"]["id"]
            await asyncio.wait_for(started.wait(), 5)
            repeated = await (await client.post("/api/admin/problems/sync", json=payload, headers=headers)).get_json()
            self.assertEqual(repeated["task"], {"id": task_id, "merged": True})
            busy = await client.post("/api/admin/problems/sync", json={"contest_id": "abc001"}, headers=headers)
            self.assertEqual(busy.status_code, 409)
            self.assertEqual((await busy.get_json())["code"], "problem_sync_busy")
            cancelled = await client.post(f"/api/tasks/{task_id}/cancel", json={}, headers=headers)
            self.assertEqual(cancelled.status_code, 200)
            with self.assertRaises(asyncio.CancelledError):
                await self.app.task_manager.tasks[task_id]["_task"]
            self.assertEqual(self.app.task_manager.tasks[task_id]["status"], "cancelled")
            self.assertEqual(await self.query("SELECT * FROM crawler_problems"), [])

    async def test_catalog_write_failure_rolls_back_problem_and_samples(self):
        await self.write("CREATE TRIGGER reject_problem BEFORE INSERT ON recommendations BEGIN SELECT RAISE(ABORT, 'write failed'); END")
        async with self.app.test_app():
            client = self.app.test_client()
            headers = await self.login(client)
            with patch.object(self.app.task_manager.problem_sync, "download", side_effect=[LISTING, BODY]):
                task = await self.submit(client, headers, problem_ids=["abc370_a"])
            self.assertEqual(task["status"], "failed")
            self.assertEqual(await self.query("SELECT * FROM crawler_problems"), [])
            self.assertEqual(await self.query("SELECT * FROM recommendations"), [])

    async def test_web_database_init_authorization_repair_and_data_preservation(self):
        async with self.app.test_app():
            client = self.app.test_client()
            self.assertEqual((await client.get("/api/admin/database")).status_code, 401)
            self.assertEqual((await client.post("/api/admin/database/init", json={})).status_code, 401)
            headers = await self.login(client)
            self.assertEqual((await client.post("/api/admin/database/init", json={})).status_code, 403)
            self.assertEqual((await client.post("/api/admin/database/init", json={"database": "other.db"}, headers=headers)).status_code, 400)
            await self.write("DROP TABLE crawler_problems")
            status = await (await client.get("/api/admin/database")).get_json()
            self.assertFalse(status["initialized"])
            self.assertIn("crawler_problems", status["missing_tables"])
            self.assertEqual((await client.post("/api/admin/database/init", json={}, headers=headers)).status_code, 200)
            with patch.object(self.app.task_manager.problem_sync, "download", side_effect=[LISTING, BODY]):
                await self.submit(client, headers, problem_ids=["abc370_a"])
            before = await self.query("SELECT statement_html,samples FROM crawler_problems")
            await self.write("UPDATE settings SET value='preserved' WHERE key='report_enabled'")
            for _ in range(2):
                result = await (await client.post("/api/admin/database/init", json={}, headers=headers)).get_json()
                self.assertTrue(result["initialized"])
                self.assertEqual(result["platforms"][0]["collected"], 1)
                self.assertEqual(await self.query("SELECT statement_html,samples FROM crawler_problems"), before)
            self.assertEqual((await self.query("SELECT value FROM settings WHERE key='report_enabled'"))[0]["value"], "preserved")
            await self.write("UPDATE web_accounts SET role='member' WHERE qq_id='12345678'")
            self.assertEqual((await client.get("/api/admin/database")).status_code, 403)
            self.assertEqual((await client.post("/api/admin/database/init", json={}, headers=headers)).status_code, 403)

    async def test_platform_scope_validation(self):
        async with self.app.test_app():
            client = self.app.test_client()
            headers = await self.login(client)
            invalid = [{"scope": "all"}, {"scope": []}, {"scope": "platform", "limit": 10},
                       {"scope": "platform", "contest_id": "abc370"}, {"scope": "platform", "problem_ids": []},
                       {"scope": "platform", "batch_size": True}, {"scope": "platform", "batch_size": 101},
                       {"scope": "platform", "batch_size": 0}, {"contest_id": "abc370", "batch_size": 10},
                       {"scope": "platform", "scheduled": True}]
            for payload in invalid:
                self.assertEqual((await client.post("/api/admin/problems/sync", json=payload, headers=headers)).status_code, 400)
            self.assertEqual(self.app.task_manager.tasks, {})

    async def test_atcoder_full_platform_batches_catalog_dedup_and_resume(self):
        async def download(http, url):
            return json.dumps(CATALOG + [CATALOG[0]]).encode() if url == ATCODER_CATALOG_URL else BODY
        async with self.app.test_app():
            client = self.app.test_client()
            headers = await self.login(client)
            with patch.object(self.app.task_manager.problem_sync, "download", side_effect=download) as fetch:
                task = await self.submit_platform(client, headers, batch_size=1)
                self.assertEqual(task["status"], "completed")
                self.assertEqual(task["result"]["metadata_count"], 3)
                self.assertEqual(task["result"]["success_count"], 3)
                self.assertEqual(task["result"]["completed_batches"], 3)
                self.assertEqual(task["progress"]["done"], 3)
                self.assertEqual(fetch.await_count, 4)
                task = await self.submit_platform(client, headers, batch_size=1)
                self.assertEqual(task["result"]["skipped_count"], 3)
                self.assertEqual(task["result"]["success_count"], 0)
            self.assertEqual(len(await self.query("SELECT * FROM recommendations")), 3)
            self.assertEqual({row["contest_id"] for row in await self.query("SELECT * FROM crawler_problems")}, {"abc370", "abc371", "abc372"})

    async def test_daily_platform_sync_refreshes_catalog_and_limits_newest_statements(self):
        older, saved = CATALOG[:2]
        newest = [
            {"id": f"abc372_{index}", "contest_id": "abc372", "name": f"Latest {index}"}
            for index in range(100)
        ]
        catalog = [older, *newest, {**saved, "name": "Renamed in catalog"}]
        previous = atcoder_catalog_metadata([saved])[0]
        source_url = previous["problem_url"] + "?lang=ja"
        content = parse_atcoder(BODY.replace(b"lang-en", b"lang-ja"), source_url, "ja")
        db = await connect_db(self.db_path)
        try:
            await save_problem(db, previous, {
                **content, "requested_language": "ja", "source_url": source_url, "sha256": "original-body",
            })
            await save_contests(db, [
                {"platform": "atcoder", "contest_id": item["contest_id"],
                 "contest_name": item["name"], "start_time": start}
                for start, item in enumerate(CATALOG, start=1)
            ])
        finally:
            await db.close()

        async def download(http, url):
            return json.dumps(catalog).encode() if url == ATCODER_CATALOG_URL else BODY

        sync = self.app.task_manager.problem_sync
        options = {**sync_options({"platform": "atcoder", "scope": "platform"}), "scheduled": True}
        task = {}
        with patch.object(sync, "download", side_effect=download) as fetch:
            await sync.run(options, task)
        self.assertEqual(task["status"], "completed", task["result"])
        self.assertEqual(task["result"]["metadata_count"], 102)
        self.assertEqual(task["result"]["skipped_count"], 1)
        self.assertEqual(task["result"]["success_count"], 100)
        self.assertEqual(task["result"]["remaining_count"], 1)
        urls = [call.args[1] for call in fetch.await_args_list]
        self.assertEqual(urls[0], ATCODER_CATALOG_URL)
        self.assertCountEqual(urls[1:], [
            f"https://atcoder.jp/contests/abc372/tasks/{item['id']}?lang=en"
            for item in newest
        ])
        self.assertEqual(len(await self.query("SELECT problem_id FROM recommendations")), 102)
        rows = await self.query(
            "SELECT problem_name,statement_html,requested_language,statement_sha256 FROM crawler_problems WHERE problem_id=?",
            (saved["id"],),
        )
        self.assertEqual(rows, [{
            "problem_name": "Renamed in catalog", "statement_html": content["statement_html"],
            "requested_language": "ja", "statement_sha256": "original-body",
        }])

    async def test_cf_full_platform_uses_problemset_and_excludes_gym(self):
        problems = [{"contestId": contest, "index": "A", "name": "Example", "rating": 800, "tags": ["math"]}
                    for contest in (1843, 1844, 1845, 100001)]
        async with self.app.test_app():
            client = self.app.test_client()
            headers = await self.login(client)
            with patch("feat.api.acm_api.problem_sync.cf_request", return_value={"problems": problems + [problems[0]]}) as request_cf:
                with patch.object(self.app.task_manager.problem_sync, "download", return_value=CF_BODY):
                    task = await self.submit_platform(client, headers, platform="codeforces", batch_size=1)
            self.assertEqual(request_cf.call_args.args[1:], ("problemset.problems",))
            self.assertEqual(task["result"]["success_count"], 3)
            self.assertEqual(task["result"]["completed_batches"], 3)
            rows = await self.query("SELECT * FROM crawler_problems")
            self.assertEqual({row["problem_id"] for row in rows}, {"cf_1843A", "cf_1844A", "cf_1845A"})
            self.assertTrue(all(row["sample_count"] == 1 and row["problem_rating"] == 800 for row in rows))

    async def test_full_platform_failure_is_persisted_and_retried_without_overwriting_successes(self):
        broken = True
        async def download(http, url):
            if url == ATCODER_CATALOG_URL:
                return json.dumps(CATALOG).encode()
            return b"<h1>Access denied</h1>" if broken and "abc371_a" in url else BODY
        async with self.app.test_app():
            client = self.app.test_client()
            headers = await self.login(client)
            with patch.object(self.app.task_manager.problem_sync, "download", side_effect=download):
                task = await self.submit_platform(client, headers, batch_size=2)
                self.assertEqual(task["status"], "partial")
                rows = await self.query("SELECT * FROM crawler_problems WHERE problem_id='abc371_a'")
                self.assertEqual(rows[0]["last_fetch_status"], "failed")
                self.assertIsNone(rows[0]["statement_html"])
                before = await self.query("SELECT samples,statement_sha256 FROM crawler_problems WHERE problem_id='abc370_a'")
                broken = False
                task = await self.submit_platform(client, headers, batch_size=2)
                self.assertEqual(task["result"]["success_count"], 1)
                self.assertEqual(task["result"]["skipped_count"], 2)
                self.assertEqual(await self.query("SELECT samples,statement_sha256 FROM crawler_problems WHERE problem_id='abc370_a'"), before)

    async def test_full_platform_cancel_preserves_committed_rows_and_can_resume(self):
        waiting = asyncio.Event()
        async def download(http, url):
            if url == ATCODER_CATALOG_URL:
                return json.dumps(CATALOG).encode()
            if "abc371_a" in url:
                waiting.set()
                await asyncio.Event().wait()
            return BODY
        async with self.app.test_app():
            client = self.app.test_client()
            headers = await self.login(client)
            with patch.object(self.app.task_manager.problem_sync, "download", side_effect=download):
                response = await client.post("/api/admin/problems/sync", json={"scope": "platform", "batch_size": 1}, headers=headers)
                task_id = (await response.get_json())["task"]["id"]
                await asyncio.wait_for(waiting.wait(), timeout=5)
                await client.post(f"/api/tasks/{task_id}/cancel", json={}, headers=headers)
                with self.assertRaises(asyncio.CancelledError):
                    await self.app.task_manager.tasks[task_id]["_task"]
            self.assertEqual(len(await self.query("SELECT * FROM crawler_problems WHERE last_fetch_status='ok'")), 1)
            async def resume(http, url):
                return json.dumps(CATALOG).encode() if url == ATCODER_CATALOG_URL else BODY
            with patch.object(self.app.task_manager.problem_sync, "download", side_effect=resume):
                task = await self.submit_platform(client, headers, batch_size=1)
            self.assertEqual(task["result"]["skipped_count"], 1)
            self.assertEqual(task["result"]["success_count"], 2)

    async def test_full_platform_error_list_is_bounded_but_all_failures_are_saved(self):
        catalog = [{"id": f"test_{index}", "contest_id": "test", "name": "Example"} for index in range(101)]
        async def download(http, url):
            return json.dumps(catalog).encode() if url == ATCODER_CATALOG_URL else b"<h1>Access denied</h1>"
        async with self.app.test_app():
            client = self.app.test_client()
            headers = await self.login(client)
            with patch.object(self.app.task_manager.problem_sync, "download", side_effect=download):
                task = await self.submit_platform(client, headers, batch_size=100)
            self.assertEqual(task["result"]["failure_count"], 101)
            self.assertEqual(len(task["result"]["failures"]), 100)
            self.assertTrue(task["result"]["failure_details_truncated"])
            self.assertEqual(task["result"]["completed_batches"], 2)
            self.assertEqual(len(await self.query("SELECT * FROM crawler_problems WHERE last_fetch_status='failed'")), 101)

    async def test_full_platform_catalog_batch_rolls_back_when_catalog_write_fails(self):
        await self.write("CREATE TRIGGER reject_metadata BEFORE INSERT ON recommendations WHEN NEW.problem_id='abc371_a' BEGIN SELECT RAISE(ABORT,'write failed'); END")
        async with self.app.test_app():
            client = self.app.test_client()
            headers = await self.login(client)
            with patch.object(self.app.task_manager.problem_sync, "download", return_value=json.dumps(CATALOG).encode()):
                task = await self.submit_platform(client, headers, batch_size=3)
            self.assertEqual(task["status"], "failed")
            self.assertEqual(await self.query("SELECT * FROM crawler_problems"), [])
            self.assertEqual(await self.query("SELECT * FROM recommendations"), [])

    async def test_deployed_init_command_can_be_repeated_without_deleting_data(self):
        path = Path(self.directory.name) / "initialized.db"
        command = [sys.executable, "-X", "utf8", "-m", "api.init_db", "--database", str(path)]
        cwd = Path(__file__).resolve().parents[2]
        for iteration in range(2):
            result = await asyncio.to_thread(subprocess.run, command, cwd=cwd, capture_output=True, encoding="utf-8", timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            db = await connect_db(path)
            try:
                if not iteration:
                    await db.execute("INSERT INTO users(qq_id,name) VALUES('87654321','Preserved')")
                    await db.commit()
                async with db.execute("SELECT name FROM users WHERE qq_id='87654321'") as cursor:
                    self.assertEqual((await cursor.fetchone())[0], "Preserved")
                async with db.execute("SELECT COUNT(*) FROM crawler_problems") as cursor:
                    self.assertEqual((await cursor.fetchone())[0], 0)
            finally:
                await db.close()


if __name__ == "__main__":
    unittest.main()
