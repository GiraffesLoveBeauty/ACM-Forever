"""Production SDK/permit path, in-memory HTTP transport, all sockets forbidden."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx
from annotation_api.client import APIClient
from annotation_api.dispatch import request_settings
from problem_processing.adapter import normalize
from problem_processing.execution_state import Ledger
from problem_processing.executor import bind_plan, execute_batch, mock_config
from problem_processing.planning import Planner
from problem_processing.translation import MockTranslationClient


class MemoryTransport(httpx.BaseTransport):
    def __init__(self, failure=None):
        self.calls=0
        self.failure=failure
    def handle_request(self,request):
        self.calls+=1
        if self.failure:raise self.failure('synthetic failure; never record raw diagnostic credentials',request=request)
        body=json.loads(request.content)
        result=MockTranslationClient().call(body['messages'])
        return httpx.Response(200,json={'id':'synthetic','object':'chat.completion','created':0,'model':'memory-response',
            'choices':[{'index':0,'finish_reason':'stop','message':{'role':'assistant','content':result.content}}],
            'usage':{'prompt_tokens':20,'completion_tokens':10,'total_tokens':30}})


class TransportDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        guard=patch('socket.socket.connect',side_effect=AssertionError('NO NETWORK'))
        guard.start();self.addCleanup(guard.stop)
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'labels';self.cfg=mock_config()
        self.problem=normalize({'platform':'atcoder','problem_key':'atcoder:offline:offline_transport',
            'title':'Synthetic transport task','statement_markdown':'Read the diagram.\n\n![figure](https://img.atcoder.jp/offline/a.png)\n\nPrint $N$.\n\n'+'``` \n1 2\n```'})

    def run_task(self,transport,client_class=APIClient,hook=None):
        http=httpx.Client(transport=transport,trust_env=False,event_hooks={'request':[hook] if hook else []})
        client=client_class(self.cfg,http_client=http);self.addCleanup(client.close)
        plan=bind_plan(Planner(self.root).plan([self.problem]),'translation',request_settings(self.cfg))
        result=execute_batch([self.problem],'translation',root=self.root,config=self.cfg,client=client,
            execute=True,plan=plan,limit=1)
        return result,Ledger(self.root).records()[0]

    def test_complete_sdk_path_fills_text_and_retains_images(self):
        transport=MemoryTransport();result,row=self.run_task(transport)
        self.assertEqual(result['completed'],1,result)
        saved=result['results'][0]['result']
        self.assertIn('![figure](https://img.atcoder.jp/offline/a.png)',saved['statement_zh'])
        self.assertIn('$N$',saved['statement_zh'])
        self.assertEqual(saved['translation_validation_mode'],'layout_by_id')
        self.assertEqual(row['state'],'completed');self.assertEqual(transport.calls,1)

    def test_connect_failure_is_proven_not_dispatched(self):
        transport=MemoryTransport(httpx.ConnectError);result,row=self.run_task(transport)
        self.assertEqual(result['real_api_calls'],0)
        self.assertEqual(row['state'],'failed_before_dispatch')
        self.assertEqual(row['error'],'connection_failed')
        self.assertEqual(transport.calls,1)
        self.assertFalse(row.get('response_sha256'))

    def test_connect_timeout_is_not_a_response_timeout(self):
        result,row=self.run_task(MemoryTransport(httpx.ConnectTimeout))
        self.assertEqual(result['real_api_calls'],0)
        self.assertEqual(row['state'],'failed_before_dispatch')
        self.assertEqual(row['error'],'connection_failed')

    def test_read_timeout_stays_uncertain_and_does_not_resend(self):
        transport=MemoryTransport(httpx.ReadTimeout);first,row=self.run_task(transport)
        self.assertEqual(row['state'],'uncertain');self.assertEqual(first['real_api_calls'],1)
        second,_=self.run_task(transport)
        self.assertEqual(second['real_api_calls'],0);self.assertEqual(transport.calls,1)

    def test_write_failure_stays_uncertain(self):
        result,row=self.run_task(MemoryTransport(httpx.WriteError))
        self.assertEqual(row['state'],'uncertain');self.assertEqual(result['real_api_calls'],1)

    def test_source_hook_failure_never_reaches_transport(self):
        class BoundClient(APIClient):
            def _check_dispatch(self,request):raise ValueError('synthetic source changed')
        transport=MemoryTransport();result,row=self.run_task(transport,BoundClient)
        self.assertEqual(transport.calls,0);self.assertEqual(result['real_api_calls'],0)
        self.assertEqual(row['state'],'failed_before_dispatch')
        self.assertEqual(row['error'],'dispatch_validation_failed')

    def test_sdk_request_hook_failure_does_not_claim_a_paid_request(self):
        def stop(request):raise RuntimeError('synthetic pre-transport failure')
        transport=MemoryTransport();result,row=self.run_task(transport,hook=stop)
        self.assertEqual(transport.calls,0);self.assertEqual(result['real_api_calls'],0)
        self.assertEqual(row['state'],'failed_before_dispatch')
        self.assertEqual(row['error'],'local_request_failed')

    def test_client_permit_failure_before_sdk_is_not_unknown_delivery(self):
        transport=MemoryTransport()
        with patch('annotation_api.dispatch.Permit.call',side_effect=ValueError('synthetic changed state')):
            result,row=self.run_task(transport)
        self.assertEqual(transport.calls,0);self.assertEqual(result['real_api_calls'],0)
        self.assertEqual(row['state'],'failed_before_dispatch')
        self.assertEqual(row['error'],'dispatch_validation_failed')

    def test_explicit_second_attempt_after_connect_failure_is_safe(self):
        first_transport=MemoryTransport(httpx.ConnectError);first,_=self.run_task(first_transport)
        self.assertEqual(first_transport.calls,1)  # no automatic retry
        second_transport=MemoryTransport();second,row=self.run_task(second_transport)
        self.assertEqual(second['completed'],1,second);self.assertEqual(second_transport.calls,1)
        self.assertEqual(len(row['attempts']),2)

    def test_error_receipt_contains_no_raw_transport_message(self):
        _,row=self.run_task(MemoryTransport(httpx.ConnectError))
        self.assertNotIn('diagnostic credentials',json.dumps(row))
        self.assertNotIn(self.cfg.api_key,json.dumps(row))
