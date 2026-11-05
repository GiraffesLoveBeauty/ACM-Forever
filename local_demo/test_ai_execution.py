"""Temporary SQLite, synthetic tasks, MockTransport only. No real network or credentials."""
import asyncio
from contextlib import closing
from copy import deepcopy
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from uuid import uuid4
from unittest.mock import patch

import httpx
from server import ReadOnlyLabels, initialize_database, isolate_environment, create_local_app, ADMIN_PASSWORD, DEMO_PASSWORD
from ai_execution import WebAIService, ExecutionConflict, problem_guard
from annotation_api.config import Config
from annotation_api.client import APIClient, CallError
from problem_processing.repository import Repository
from problem_processing.executor import MockAnnotationClient
from problem_processing.translation import MockTranslationClient
from problem_processing.execution_state import Ledger


class Fixture:
    @classmethod
    def setUpClass(cls):
        cls.base=tempfile.TemporaryDirectory(prefix='web-ai-fixture-')
        cls.seed=Path(cls.base.name)
        Repository(cls.seed/'labels').import_records([{
            'platform':'atcoder','problem_key':'atcoder:abc999:abc999_a','contest_id':'abc999','problem_id':'abc999_a',
            'source_links':['https://atcoder.jp/contests/abc999/tasks/abc999_a'],
            'original_title':'Synthetic test problem','original_statement':
                'Problem Statement\nFind the value N.\n\nConstraints\n\n- N is positive.\n\nInput\n\n```\nN\n```\n\nOutput\n\nPrint the integer N.'}])
        asyncio.run(initialize_database(cls.seed/'fixture.sqlite3',ReadOnlyLabels(cls.seed/'labels')))

    @classmethod
    def tearDownClass(cls):cls.base.cleanup()

    def fixture(self):
        self.temp=tempfile.TemporaryDirectory(prefix='web-ai-offline-');self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name)
        shutil.copytree(self.seed/'labels',root/'labels')
        shutil.copyfile(self.seed/'fixture.sqlite3',root/'fixture.sqlite3')
        self.database=root/'fixture.sqlite3';self.labels=ReadOnlyLabels(root/'labels')
        self.cfg=Config(provider='compatible',model='offline-model',api_key='synthetic-not-a-credential',
            base_url='https://offline.invalid/v1',max_retries=0,timeout=90,max_output_tokens=4000,request_interval=0)
        self.launched=[]
        self.service=WebAIService(self.labels,self.database,config_loader=lambda:self.cfg,launcher=self.launched.append)
        self.problem=self.service.source('atcoder','abc999_a')
        self.network=patch('httpx.HTTPTransport.handle_request',side_effect=AssertionError('REAL NETWORK FORBIDDEN'))
        self.network.start();self.addCleanup(self.network.stop)

    def update(self,sql,args=()):
        with closing(sqlite3.connect(self.database)) as db:
            db.execute(sql,args);db.commit()

    def queue(self,task='annotation'):
        proposal=self.service.proposal(self.problem,task)
        return self.service.submit(self.problem,'atcoder','abc999_a',task,proposal['revision'],'1')

    def crawler_only(self):
        # A newly collected problem has no label catalog entry or prior AI result.
        with closing(sqlite3.connect(self.database)) as db:
            db.row_factory=sqlite3.Row
            row=dict(db.execute('SELECT * FROM crawler_problems LIMIT 1').fetchone())
            for field,value in list(row.items()):
                if isinstance(value,str):row[field]=value.replace('abc999_a','abc999_b')
            columns=','.join('"'+k+'"' for k in row)
            db.execute('INSERT INTO crawler_problems ('+columns+') VALUES ('+','.join('?' for _ in row)+')',list(row.values()))
            db.commit()
        self.problem=self.service.source('atcoder','abc999_b')
        self.assertNotIn(self.problem['problem_key'],self.labels.repo.snapshot()[0])
        return self.problem

    def client(self,task='annotation',failure=None,rewrite=None):
        self.requests=[]
        def handler(request):
            self.requests.append(request)
            if failure=='timeout':raise httpx.ReadTimeout('synthetic timeout',request=request)
            if failure=='connect':raise httpx.ConnectError('synthetic TLS/connect failure',request=request)
            if failure=='auth':return httpx.Response(401,json={'error':{'message':'synthetic auth failure'}})
            body=json.loads(request.content)
            fake=(MockAnnotationClient() if task=='annotation' else MockTranslationClient()).call(body['messages'])
            if rewrite is not None:fake.content=rewrite(fake.content)
            return httpx.Response(200,json={'id':'offline','object':'chat.completion','created':0,'model':'offline-response',
                'choices':[{'index':0,'finish_reason':'stop','message':{'role':'assistant','content':fake.content}}],
                'usage':{'prompt_tokens':20,'completion_tokens':10,'total_tokens':30}})
        client=APIClient(self.cfg,http_client=httpx.Client(transport=httpx.MockTransport(handler)))
        self.addCleanup(client.close);return client


class ServiceTests(Fixture,unittest.TestCase):
    def setUp(self):self.fixture()

    def test_preview_does_not_queue_or_call(self):
        for task in ('annotation','translation'):
            proposal=self.service.proposal(self.problem,task)
            self.assertTrue(proposal['can_execute'])
            self.assertEqual(proposal['maximum_requests'],1)
        self.assertEqual(self.launched,[])
        self.assertFalse((self.service.store/'jobs').exists())

    def test_connection_failure_reports_unsent_and_allows_only_explicit_new_attempt(self):
        job=self.queue('translation')
        first=self.service.run(job['job_id'],client=self.client('translation',failure='connect'))
        self.assertEqual(first['status'],'failed_before_dispatch',first)
        self.assertEqual(first['real_api_calls'],0)
        self.assertEqual(first['error'],'connection_failed')
        self.assertIn('生成请求正文未发出',first['message'])
        self.assertEqual(len(self.requests),1)  # one simulated connection, no retry
        proposal=self.service.proposal(self.problem,'translation')
        self.assertTrue(proposal['can_execute'])
        second=self.service.submit(self.problem,'atcoder','abc999_a','translation',proposal['revision'],'1')
        self.assertNotEqual(second['job_id'],job['job_id'])
        result=self.service.run(second['job_id'],client=self.client('translation'))
        self.assertEqual(result['status'],'completed',result)
        self.assertEqual(self.service.read(job['job_id'])['status'],'failed_before_dispatch')

    def test_parsing_failure_keeps_returned_usage_and_model(self):
        job=self.queue('translation')
        def missing_id(content):
            value=json.loads(content);value['segments'].pop();return json.dumps(value)
        result=self.service.run(job['job_id'],client=self.client('translation',rewrite=missing_id))
        self.assertEqual(result['status'],'blocked',result)
        self.assertEqual(result['usage']['total_tokens'],30)
        self.assertEqual(result['model'],'offline-response')
        self.assertIn('文字 ID',result['message'])
        self.assertFalse(self.service.proposal(self.problem,'translation')['can_execute'])

    def test_old_uncertain_receipt_is_projected_without_rewriting_history(self):
        row={'status':'uncertain','error':'unknown_delivery',
             'message':'任务已停止。请先核对保存记录，不要重复发起付费请求。'}
        original=deepcopy(row);view=self.service.public(row)
        self.assertIn('是否到达中转站及是否计费尚无法确认',view['message'])
        self.assertEqual(row,original)

    def test_worker_created_client_runs_real_sdk_guards_with_memory_transport(self):
        self.crawler_only()
        self.update("UPDATE crawler_problems SET statement_html=? WHERE problem_id='abc999_b'",
            ('<div id="task-statement"><p>Read the given diagram and print the answer.</p><img src="https://img.atcoder.jp/offline/a.png"></div>',))
        p=self.service.source('atcoder','abc999_b')
        proposal=self.service.proposal(p,'translation')
        job=self.service.submit(p,'atcoder','abc999_b','translation',proposal['revision'],'1')
        calls=[]
        class Memory(httpx.BaseTransport):
            def handle_request(_,request):
                calls.append(request)
                body=json.loads(request.content)
                fake=MockTranslationClient().call(body['messages'])
                return httpx.Response(200,json={'id':'offline','object':'chat.completion','created':0,'model':'memory-test',
                    'choices':[{'index':0,'finish_reason':'stop','message':{'role':'assistant','content':fake.content}}],
                    'usage':{'prompt_tokens':20,'completion_tokens':10,'total_tokens':30}})
        class GuardedMemoryClient(APIClient):
            def __init__(_,cfg):super().__init__(cfg,http_client=httpx.Client(transport=Memory(),trust_env=False))
        with patch('annotation_api.client.APIClient',GuardedMemoryClient):
            result=self.service.run(job['job_id'])
        self.assertEqual(result['status'],'completed',result)
        self.assertEqual(len(calls),1)
        self.assertIn('![图片](https://img.atcoder.jp/offline/a.png)',self.labels.find('atcoder','abc999_b')['translated_statement'])

    def test_same_revision_double_submit_launches_once(self):
        first=self.queue();second=self.queue()
        self.assertEqual(first['job_id'],second['job_id']);self.assertEqual(len(self.launched),1)

    def test_only_one_task_runs_at_a_time(self):
        self.queue()
        with self.assertRaises(ExecutionConflict):self.queue('translation')
        self.assertEqual(len(self.launched),1)

    def test_stale_statement_rejected_before_queue(self):
        old=self.service.proposal(self.problem,'annotation')
        self.update("UPDATE crawler_problems SET statement_text=statement_text||'\nChanged.'")
        current=self.service.source('atcoder','abc999_a')
        with self.assertRaises(ExecutionConflict):self.service.submit(current,'atcoder','abc999_a','annotation',old['revision'],'1')
        self.assertEqual(self.launched,[])

    def test_mock_annotation_uses_real_guarded_execution_and_persists(self):
        job=self.queue();client=self.client()
        result=self.service.run(job['job_id'],client=client)
        self.assertEqual(result['status'],'completed',result)
        self.assertEqual(len(self.requests),1);self.assertEqual(result['real_api_calls'],0)
        self.assertEqual(result['usage']['total_tokens'],30)
        self.assertEqual(Ledger(self.labels.root).records()[0]['state'],'completed')
        self.assertEqual(self.service.proposal(self.problem,'annotation')['status'],'reuse_existing')
        self.service.run(job['job_id'],client=client);self.assertEqual(len(self.requests),1)

    def test_worker_default_client_runs_through_http_dispatch_guard_with_mock_transport(self):
        reference=self.client()
        handler=reference.sdk._client._transport.handle_request
        def factory(**kwargs):return httpx.Client(transport=httpx.MockTransport(handler),**kwargs)
        job=self.queue()
        with patch('annotation_api.client.openai.DefaultHttpxClient',side_effect=factory):
            result=self.service.run(job['job_id'])
        self.assertEqual(result['status'],'completed',result)
        self.assertEqual(len(self.requests),1)
        self.assertEqual(str(self.requests[0].url),'https://offline.invalid/v1/chat/completions')

    def test_manual_correction_blocks_new_annotation(self):
        from tag_editor import LocalTagEditor
        job=self.queue();self.service.run(job['job_id'],client=self.client())
        editor=LocalTagEditor(self.labels);detail=editor.detail(self.problem['problem_key'])
        editor.change(self.problem['problem_key'],{'operation':'save','tag_ids':['enumeration','prefix_sum'],
            'revision':detail['revision'],'request_id':uuid4().hex,'reason':'模拟管理员修正'},'test-admin')
        proposal=self.service.proposal(self.problem,'annotation')
        self.assertTrue(proposal['manual_protected']);self.assertFalse(proposal['can_execute'])
        self.assertEqual(len(Ledger(self.labels.root).records()),1)

    def test_mock_translation_saved_separately_from_original(self):
        before=self.labels.repo.snapshot()[0][self.problem['problem_key']]['original_statement']
        job=self.queue('translation');result=self.service.run(job['job_id'],client=self.client('translation'))
        self.assertEqual(result['status'],'completed',result)
        self.assertEqual(self.labels.repo.snapshot()[0][self.problem['problem_key']]['original_statement'],before)
        self.assertTrue(self.labels.find('atcoder','abc999_a')['translation_active'])
        self.assertEqual(self.service.proposal(self.problem,'translation')['status'],'reuse_existing')

    def test_crawler_only_translation_without_prior_annotation(self):
        p=self.crawler_only()
        before=self.labels.repo.snapshot()[0]['atcoder:abc999:abc999_a']
        proposal=self.service.proposal(p,'translation')
        self.assertTrue(proposal['can_execute'],proposal)
        self.assertNotIn(p['problem_key'],self.labels.repo.snapshot()[0], 'GET preflight must remain read-only')
        job=self.service.submit(p,'atcoder','abc999_b','translation',proposal['revision'],'1')
        result=self.service.run(job['job_id'],client=self.client('translation'))
        self.assertEqual(result['status'],'completed',result)
        self.assertEqual(len(self.requests),1)
        self.assertEqual(result['real_api_calls'],0)
        self.assertEqual(self.labels.repo.snapshot()[0]['atcoder:abc999:abc999_a'],before)
        self.assertEqual(self.labels.repo.snapshot()[0][p['problem_key']]['original_statement'],p['original_statement'])
        self.assertTrue(self.labels.find('atcoder','abc999_b')['translation_active'])
        self.assertEqual(self.service.proposal(p,'translation')['status'],'reuse_existing')
        self.service.run(job['job_id'],client=self.client('translation'))
        self.assertEqual(self.requests,[])

    def test_web_translation_bypasses_strict_content_validator(self):
        self.crawler_only()
        self.update("UPDATE crawler_problems SET statement_text=?,statement_html='' WHERE problem_id='abc999_b'",
            ('Problem Statement\n\nRead $N$ and $M$ in that order.\n\nInput\n\n```\n1 2\n```\n\nOutput\n\nPrint the answer.',))
        p=self.service.source('atcoder','abc999_b')
        proposal=self.service.proposal(p,'translation')
        job=self.service.submit(p,'atcoder','abc999_b','translation',proposal['revision'],'1')
        def reorder(content):
            value=json.loads(content)
            value['segments'][0]['text']='Returned English 999'
            value['segments'].reverse()
            return json.dumps(value,ensure_ascii=False)
        with patch('problem_processing.translation.validate_translation',side_effect=AssertionError('STRICT GATE DISABLED')):
            result=self.service.run(job['job_id'],client=self.client('translation',rewrite=reorder))
        self.assertEqual(result['status'],'completed',result)
        self.assertEqual(len(self.requests),1)
        self.assertEqual(result['real_api_calls'],0)
        view=self.labels.find('atcoder','abc999_b')
        self.assertTrue(view['translation_active'])
        self.assertEqual(view['translation_validation_mode'],'layout_by_id')
        self.assertFalse(view['fully_human_verified'])
        self.assertIn('Returned English 999',view['translated_statement'])
        self.assertLess(view['translated_statement'].index('$N$'),view['translated_statement'].index('$M$'))
        self.assertEqual(self.service.proposal(p,'translation')['status'],'reuse_existing')

    def test_crawler_only_changed_before_worker_sends_nothing(self):
        p=self.crawler_only();proposal=self.service.proposal(p,'translation')
        job=self.service.submit(p,'atcoder','abc999_b','translation',proposal['revision'],'1')
        self.update("UPDATE crawler_problems SET statement_text=statement_text||' Changed.' WHERE problem_id='abc999_b'")
        result=self.service.run(job['job_id'],client=self.client('translation'))
        self.assertEqual(result['status'],'blocked')
        self.assertEqual(self.requests,[])
        self.assertNotIn(p['problem_key'],self.labels.repo.snapshot()[0])

    def test_crawler_image_translates_text_and_keeps_annotation_pending(self):
        self.crawler_only()
        self.update("UPDATE crawler_problems SET statement_html=? WHERE problem_id='abc999_b'",
            ('<div id="task-statement"><p>Find the value N in this figure.</p><img src="https://img.atcoder.jp/example.png"></div>',))
        p=self.service.source('atcoder','abc999_b')
        self.assertEqual(p['processing_status'],'html_pending')
        self.assertIn('image_requires_review',p['processing_issues'])
        proposal=self.service.proposal(p,'translation')
        self.assertTrue(proposal['can_execute'],proposal)
        self.assertFalse(self.service.proposal(p,'annotation')['can_execute'])
        job=self.service.submit(p,'atcoder','abc999_b','translation',proposal['revision'],'1')
        result=self.service.run(job['job_id'],client=self.client('translation'))
        self.assertEqual(result['status'],'completed',result)
        self.assertEqual(len(self.requests),1)
        self.assertIn('![图片](https://img.atcoder.jp/example.png)',self.labels.find('atcoder','abc999_b')['translated_statement'])

    def test_restart_preserves_crawler_samples_after_task_registers_input(self):
        self.crawler_only()
        self.update("UPDATE crawler_problems SET samples=?,sample_count=1 WHERE problem_id='abc999_b'",
            (json.dumps([{'index':1,'input':'1\n','output':'1\n'}]),))
        p=self.service.source('atcoder','abc999_b')
        self.labels.repo.import_records([p])
        with closing(sqlite3.connect(self.database)) as db:
            before=db.execute('SELECT * FROM crawler_problems ORDER BY platform,problem_id').fetchall()
        asyncio.run(initialize_database(self.database,self.labels))
        with closing(sqlite3.connect(self.database)) as db:
            after=db.execute('SELECT * FROM crawler_problems ORDER BY platform,problem_id').fetchall()
        self.assertEqual(after,before)

    def test_timeout_persists_uncertain_and_does_not_retry(self):
        job=self.queue();result=self.service.run(job['job_id'],client=self.client(failure='timeout'))
        self.assertEqual(result['status'],'uncertain');self.assertEqual(len(self.requests),1)
        self.assertFalse(self.service.proposal(self.problem,'annotation')['can_execute'])
        self.service.run(job['job_id'],client=self.client());self.assertEqual(len(self.requests),0)

    def test_api_error_not_retried_and_no_secrets_in_public_record(self):
        job=self.queue();result=self.service.run(job['job_id'],client=self.client(failure='auth'))
        self.assertEqual(result['status'],'blocked');self.assertEqual(len(self.requests),1)
        self.assertNotIn(self.cfg.api_key,json.dumps(self.service.read(job['job_id'])))

    def test_role_revoked_after_queue_prevents_dispatch(self):
        job=self.queue();self.update("UPDATE web_accounts SET role='member' WHERE qq_id='1'")
        result=self.service.run(job['job_id'],client=self.client())
        self.assertEqual(result['status'],'blocked');self.assertEqual(self.requests,[])

    def test_source_changed_after_queue_prevents_dispatch(self):
        job=self.queue();self.update("UPDATE crawler_problems SET statement_text=statement_text||'\nChanged.'")
        result=self.service.run(job['job_id'],client=self.client())
        self.assertEqual(result['status'],'blocked');self.assertEqual(self.requests,[])

    def test_manual_operations_share_execution_lock(self):
        from tag_editor import LocalTagEditor,EditConflict
        with problem_guard(self.labels,self.problem['problem_key']):
            with self.assertRaises(EditConflict):LocalTagEditor(self.labels).change(self.problem['problem_key'],{},'test')

    def test_restart_does_not_relaunch_queued_job(self):
        job=self.queue()
        service=WebAIService(self.labels,self.database,config_loader=lambda:self.cfg,launcher=self.launched.append)
        self.assertEqual(service.latest('atcoder','abc999_a')['annotation']['job_id'],job['job_id'])
        proposal=service.proposal(self.problem,'annotation')
        service.submit(self.problem,'atcoder','abc999_a','annotation',proposal['revision'],'1')
        self.assertEqual(len(self.launched),1)

    def test_launch_failure_is_persisted_before_dispatch(self):
        self.service.launcher=lambda _:(_ for _ in ()).throw(OSError('synthetic'))
        job=self.queue();self.assertEqual(job['status'],'failed_before_dispatch')
        self.assertEqual(Ledger(self.labels.root).records(),[])

    def test_bad_job_path_rejected(self):
        with self.assertRaises(ValueError):self.service.read('../anything')

    def test_ten_synthetic_results_reuse_across_source_export_hash_formats(self):
        # Read existing results only; no import, publication, job submission or network.
        from synthetic_fixtures import build_fixture
        root=Path(self.temp.name)/'ten-fixtures'
        labels=ReadOnlyLabels(build_fixture(root/'labels'));launched=[]
        database=root/'fixture.sqlite3'
        asyncio.run(initialize_database(database,labels))
        service=WebAIService(labels,database,
            config_loader=lambda:self.cfg,launcher=launched.append)
        # Failed first attempts may register additional source-only catalog rows.
        # They are not successful legacy results and must not be asserted reusable.
        original=[row for row in labels.views() if row['annotation_status']=='success']
        self.assertGreaterEqual(len(original),10)
        for row in original:
            p=service.source(row['platform'],row['problem_id'])
            for task in ('annotation','translation'):
                proposal=service.proposal(p,task)
                self.assertEqual(proposal['status'],'reuse_existing',(p['problem_key'],task))
                self.assertFalse(proposal['can_execute'])
        self.assertEqual(launched,[])


class RouteTests(Fixture,unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.fixture();self.env=patch.dict('os.environ');self.env.start();self.addCleanup(self.env.stop)
        isolate_environment(self.database)
        self.app=create_local_app(self.labels);self.client=self.app.test_client()
        service=self.app.extensions['local_ai_execution']
        service.config_loader=lambda:self.cfg;service.launcher=self.launched.append
        self.service=service
        self.path='/api/admin/problem-processing/atcoder/abc999_a'

    async def login(self,role='admin'):
        if role=='root':self.update("UPDATE web_accounts SET role='root' WHERE qq_id='1'")
        result=await self.client.post('/api/auth/login',json={'qq_id':'10000001' if role=='member' else '1',
            'password':DEMO_PASSWORD if role=='member' else ADMIN_PASSWORD})
        self.assertEqual(result.status_code,200)
        self.csrf=(await result.get_json())['csrf_token']

    def payload(self):
        return {'task_type':'annotation','revision':self.service.proposal(self.problem,'annotation')['revision'],'confirm':True}

    async def test_anonymous_and_member_denied_both_execution_and_receipts(self):
        self.assertEqual((await self.client.post(self.path+'/execute',json={})).status_code,401)
        await self.login('member')
        self.assertEqual((await self.client.post(self.path+'/execute',json=self.payload(),headers={'X-CSRF-Token':self.csrf})).status_code,403)
        self.assertEqual((await self.client.get('/api/admin/problem-processing/jobs/'+'0'*64)).status_code,403)
        self.assertEqual(self.launched,[])

    async def test_admin_and_root_can_queue_with_csrf_and_confirmation(self):
        for role in ('admin','root'):
            await self.login(role)
            result=await self.client.post(self.path+'/execute',json=self.payload(),headers={'X-CSRF-Token':self.csrf})
            self.assertEqual(result.status_code,202)
        self.assertEqual(len(self.launched),1)

    async def test_csrf_and_cross_origin_denied(self):
        await self.login()
        self.assertEqual((await self.client.post(self.path+'/execute',json=self.payload())).status_code,403)
        self.assertEqual((await self.client.post(self.path+'/execute',json=self.payload(),headers={
            'X-CSRF-Token':self.csrf,'Origin':'https://evil.invalid'})).status_code,403)
        self.assertEqual(self.launched,[])

    async def test_no_model_endpoint_limit_or_force_override_accepted(self):
        await self.login()
        for extra in ({'model':'changed'},{'base_url':'https://evil.invalid'},{'limit':100},{'force':True},{'confirm':False}):
            response=await self.client.post(self.path+'/execute',json=self.payload()|extra,headers={'X-CSRF-Token':self.csrf})
            self.assertEqual(response.status_code,400)
        self.assertEqual(self.launched,[])

    async def test_receipt_and_reload_expose_same_durable_job(self):
        await self.login()
        response=await self.client.post(self.path+'/execute',json=self.payload(),headers={'X-CSRF-Token':self.csrf})
        job=await response.get_json()
        receipt=await(await self.client.get('/api/admin/problem-processing/jobs/'+job['job_id'])).get_json()
        self.assertEqual(receipt['job_id'],job['job_id'])
        detail=await(await self.client.get(self.path)).get_json()
        self.assertEqual(detail['jobs']['annotation']['job_id'],job['job_id'])
        self.assertNotIn('api_key',json.dumps(detail));self.assertNotIn(self.cfg.api_key,json.dumps(receipt))

    async def test_crawler_only_admin_preflight_and_translation_complete_with_mock(self):
        self.crawler_only();await self.login()
        path='/api/admin/problem-processing/atcoder/abc999_b'
        detail=await(await self.client.get(path)).get_json()
        self.assertIsNone(detail['existing'])
        self.assertTrue(detail['execution']['translation']['can_execute'],detail)
        self.assertIn('翻译无需先标注',detail['edit_block_reason'])
        response=await self.client.post(path+'/execute',json={'task_type':'translation',
            'revision':detail['execution']['translation']['revision'],'confirm':True},headers={'X-CSRF-Token':self.csrf})
        self.assertEqual(response.status_code,202)
        job=await response.get_json()
        result=self.service.run(job['job_id'],client=Fixture.client(self,'translation'))
        self.assertEqual(result['status'],'completed',result)
        after=await(await self.client.get(path)).get_json()
        self.assertTrue(after['existing']['translation_active'])
        self.assertEqual(after['execution']['translation']['status'],'reuse_existing')
        self.assertEqual(len(self.requests),1)

    async def test_image_unknown_delivery_reason_is_not_replaced_by_image_block(self):
        self.crawler_only()
        self.update("UPDATE crawler_problems SET statement_html=? WHERE problem_id='abc999_b'",
            ('<div id="task-statement"><p>Read this figure and print the correct answer.</p><img src="https://img.atcoder.jp/offline/a.png"></div>',))
        p=self.service.source('atcoder','abc999_b')
        proposal=self.service.proposal(p,'translation')
        job=self.service.submit(p,'atcoder','abc999_b','translation',proposal['revision'],'1')
        self.service.run(job['job_id'],client=Fixture.client(self,'translation',failure='timeout'))
        await self.login()
        detail=await(await self.client.get('/api/admin/problem-processing/atcoder/abc999_b')).get_json()
        self.assertIn('是否到达中转站及是否计费尚无法确认',detail['execution']['translation']['reason'])
        self.assertNotIn('需先复核；并非 API 配置',detail['execution']['translation']['reason'])
        self.assertIn('默认保留原图',detail['image_handling_notice'])
        self.assertFalse(detail['execution']['translation']['can_execute'])
        self.assertEqual(len(self.requests),1)

    async def test_direct_old_execution_route_remains_blocked(self):
        await self.login()
        self.assertEqual((await self.client.post(self.path,json={'execute':True},headers={'X-CSRF-Token':self.csrf})).status_code,403)
        self.assertEqual((await self.client.post('/api/problems/sync',json={},headers={'X-CSRF-Token':self.csrf})).status_code,403)


if __name__=='__main__':unittest.main()
