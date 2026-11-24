"""Offline transport failures, secret redaction and ambiguous upload recovery."""
import contextlib
import io
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from gitee_transport import Budget, CurlTransport, Reply, TransferError
import gitee_release as mirror
import gitee_mirror as recovery
import test_gitee_release as fixtures


class Clock:
    def __init__(self):self.now=0
    def sleep(self,seconds):self.now+=seconds
    def budget(self,seconds=900):return Budget(seconds,lambda:self.now,self.sleep)


class TransportTest(unittest.TestCase):
    def fake_runner(self,code=0,status=201,body=b'{"id":1}',sent=12,request_id='request-1'):
        def run(args,**kwargs):
            self.argv=args;self.stdin=kwargs['input'];self.process_timeout=kwargs['timeout']
            values={}
            for line in self.stdin.decode().splitlines():
                key,sep,value=line.partition(' = ')
                if sep and value.startswith('"'):values[key]=json.loads(value)
            Path(values['output']).write_bytes(body)
            Path(values['dump-header']).write_text('HTTP/1.1 '+str(status)+' Test\r\nX-Request-Id: '+request_id+'\r\n')
            return subprocess.CompletedProcess(args,code,('status='+str(status)+'\nsent='+str(sent)+'\ntotal=1.2\n').encode(),b'sensitive stderr must not be emitted')
        return run

    def test_upload_credentials_are_only_in_stdin_and_logs_are_allowlisted(self):
        secret='fake-release-token-DO-NOT-LOG'
        clock=Clock();out=io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            artifact=Path(directory)/'module-cat-art.acmpack';artifact.write_bytes(b'fixture')
            with contextlib.redirect_stdout(out):
                result=CurlTransport(clock.budget(),self.fake_runner(body=secret.encode(),request_id=secret)).request(
                    'POST',mirror.API+'/releases/1/attach_files',upload=artifact,token=secret,timeout=180)
        self.assertEqual(201,result.status)
        self.assertNotIn(secret,' '.join(self.argv));self.assertIn(secret,self.stdin.decode())
        self.assertNotIn(secret,out.getvalue());self.assertNotIn('sensitive stderr',out.getvalue())
        self.assertIn('module-cat-art.acmpack',out.getvalue())
        self.assertLessEqual(self.process_timeout,182)
        self.assertNotIn('location =',self.stdin.decode())

    def test_dns_is_retryable_but_sent_upload_timeout_is_ambiguous(self):
        for code,sent,safe in ((6,0,True),(28,1024,False),(60,0,True)):
            with contextlib.redirect_stdout(io.StringIO()),self.assertRaises(TransferError) as failure:
                CurlTransport(Clock().budget(),self.fake_runner(code=code,status=0,sent=sent)).request('GET',mirror.API)
            self.assertEqual(safe,failure.exception.safe_to_retry)
            if code==60:self.assertFalse(failure.exception.retryable)

    def test_budget_is_real_and_cannot_be_extended_by_retry_after(self):
        clock=Clock();budget=clock.budget(10);clock.sleep(7)
        self.assertEqual(3,budget.remaining(180))
        with self.assertRaises(TransferError):budget.pause(4)

    def test_curl_launch_error_is_sanitized(self):
        with patch('gitee_transport.subprocess.run',side_effect=OSError('fake secret')):
            # Explicit injection also makes the subprocess exception path deterministic.
            client=CurlTransport(Clock().budget(),runner=lambda *a,**k:(_ for _ in ()).throw(OSError('fake secret')))
            with contextlib.redirect_stdout(io.StringIO()),self.assertRaises(TransferError) as failure:client.request('GET',mirror.API)
        self.assertNotIn('fake secret',str(failure.exception))

    def test_public_redirect_cannot_send_request_to_unknown_host(self):
        class FakeTransport:
            budget=Clock().budget()
            def request(self,*args,**kwargs):return Reply(302,{'location':'https://unknown.invalid/file'},b'',0,'')
        with self.assertRaises(ValueError):mirror.Gitee('fixture',FakeTransport()).readback('v1.0.2','update.json',100,'a'*64)

    def test_official_list_filters_prereleases_instead_of_trusting_latest(self):
        class FakeTransport:
            budget=Clock().budget()
            def request(self,*args,**kwargs):return Reply(200,{},json.dumps([{'tag_name':'v9.0.0','prerelease':True},{'tag_name':'v1.0.2','prerelease':False}]).encode(),0,'')
        client=mirror.Gitee('fixture',FakeTransport())
        self.assertEqual(['v1.0.2'],[r['tag_name'] for r in client.formal_releases()])
        mirror.ensure_not_newer(client,'v1.0.2')
        with self.assertRaises(ValueError):mirror.ensure_not_newer(client,'v1.0.1')

    def test_delayed_public_download_recovers_within_readback_budget(self):
        class FakeTransport:
            def __init__(self):self.budget=Clock().budget();self.calls=0
            def request(self,*args,**kwargs):
                self.calls+=1
                return Reply(404 if self.calls==1 else 200,{},b'',1,hashlib.sha256(b'x').hexdigest())
        transport=FakeTransport()
        mirror.Gitee('fixture',transport).readback('v1.0.2','update.json',1,hashlib.sha256(b'x').hexdigest())
        self.assertEqual(2,transport.calls)

    def test_api_retry_after_is_bounded_and_authentication_is_not_retried(self):
        class FakeTransport:
            def __init__(self,status):self.budget=Clock().budget(10);self.status=status;self.calls=0
            def request(self,*args,**kwargs):self.calls+=1;return Reply(self.status,{'retry-after':'3600'},b'{}',2,'')
        for status in (401,429):
            transport=FakeTransport(status)
            with self.assertRaises(TransferError):mirror.Gitee('fixture',transport).api('GET','')
            self.assertEqual(1,transport.calls)


class UploadRecoveryTest(unittest.TestCase):
    def setUp(self):
        self.case=fixtures.GiteeReleaseTest('test_all_eight_assets_verified_before_publication');self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.client=self.case.client;self.client.budget=Clock().budget()
        self.path=self.case.directory/'module-cat-art.acmpack'

    def test_lost_upload_response_reconciles_without_duplicate_post(self):
        original=self.client.api;calls=[]
        def api(method,suffix,data=None,missing=False,multipart=None):
            if multipart:
                calls.append(multipart.name);original(method,suffix,multipart=multipart)
                raise TransferError('timeout',retryable=True)
            return original(method,suffix,data,missing,multipart)
        self.client.api=api
        with contextlib.redirect_stdout(io.StringIO()):mirror.upload_missing(self.client,123,self.case.tag,self.path)
        self.assertEqual([self.path.name],calls)

    def test_unknown_upload_is_not_blindly_retried(self):
        with patch.object(self.client,'api',side_effect=TransferError('timeout',retryable=True)) as upload:
            with contextlib.redirect_stdout(io.StringIO()),self.assertRaisesRegex(TransferError,'upload_result_unknown'):
                mirror.upload_missing(self.client,123,self.case.tag,self.path)
            self.assertEqual(1,upload.call_count)

    def test_definitely_unsent_failure_can_retry_only_three_times(self):
        with patch.object(self.client,'api',side_effect=TransferError('dns',retryable=True,safe_to_retry=True)) as upload:
            with contextlib.redirect_stdout(io.StringIO()),self.assertRaises(TransferError):mirror.upload_missing(self.client,123,self.case.tag,self.path)
            self.assertEqual(3,upload.call_count)

    def test_permanent_http_error_is_not_retried(self):
        for status in (401,403,413):
            with patch.object(self.client,'api',side_effect=TransferError('http',status=status)) as upload:
                with contextlib.redirect_stdout(io.StringIO()),self.assertRaises(TransferError):mirror.upload_missing(self.client,123,self.case.tag,self.path)
                self.assertEqual(1,upload.call_count)

    def test_accepted_but_corrupt_upload_fails_integrity_check(self):
        def api(*args,**kwargs):
            self.client.assets[self.path.name]=b'wrong'
            raise TransferError('timeout',retryable=True)
        self.client.api=api
        with contextlib.redirect_stdout(io.StringIO()),self.assertRaises(ValueError):mirror.upload_missing(self.client,123,self.case.tag,self.path)

    def test_wrong_upload_response_does_not_trigger_another_post(self):
        with patch.object(self.client,'api',return_value={'name':'other.apk','id':1}) as upload:
            with contextlib.redirect_stdout(io.StringIO()),self.assertRaises(ValueError):mirror.upload_missing(self.client,123,self.case.tag,self.path)
            self.assertEqual(1,upload.call_count)

    def test_newer_formal_release_appearing_during_upload_blocks_publication(self):
        with patch.object(self.client,'formal_releases',side_effect=[[],[{'tag_name':'v9.0.0'}]]):
            with contextlib.redirect_stdout(io.StringIO()),self.assertRaises(ValueError):self.case.publish()
        self.assertTrue(self.client.current['prerelease'])
        self.assertNotIn('publish',self.client.operations)

    def test_duplicate_appearing_after_last_upload_blocks_publication(self):
        original=self.client.files
        def files(rid):
            rows=original(rid)
            return rows+[dict(rows[0])] if len(rows)==8 else rows
        with patch.object(self.client,'files',side_effect=files):
            with contextlib.redirect_stdout(io.StringIO()),self.assertRaises(ValueError):self.case.publish()
        self.assertTrue(self.client.current['prerelease'])


class RecoveryContextTest(unittest.TestCase):
    def test_only_reviewed_main_dispatch_or_matching_tag_is_accepted(self):
        base=dict(GITHUB_ACTIONS='true',GITHUB_REPOSITORY=mirror.GITHUB_REPOSITORY)
        for event,ref in (('workflow_dispatch','refs/heads/main'),('push','refs/tags/v1.0.2')):
            recovery.validate_context('v1.0.2',dict(base,GITHUB_EVENT_NAME=event,GITHUB_REF=ref))
        for event,ref in (('workflow_dispatch','refs/heads/feature'),('pull_request','refs/heads/main'),('push','refs/tags/v1.0.3')):
            with self.assertRaises(ValueError):recovery.validate_context('v1.0.2',dict(base,GITHUB_EVENT_NAME=event,GITHUB_REF=ref))
        with self.assertRaises(ValueError):recovery.validate_context('v1.0.2-preview.1',base)

    def test_recovery_reads_target_tag_source_even_when_main_has_next_version(self):
        tag='v1.0.2';commit='b'*40;history={'schemaVersion':1,'currentVersionCode':47,'entries':[{'versionName':'1.0.2'}]}
        class Github:
            def tag_commit(self,selected):self.selected=selected;return commit
        calls=[]
        def source(sha,path):
            calls.append((sha,path))
            return "versionName '1.0.2'\nversionCode 47" if path==recovery.GRADLE else json.dumps(history)
        with patch.object(recovery,'restore_github',return_value=True) as restore,patch.object(recovery,'bundled_history'),patch.object(recovery,'validate_release_credits'),patch.object(recovery,'bundled_credits'):
            result=recovery.prepare(Github(),tag,Path('unused'),source,lambda *a,**k:subprocess.CompletedProcess(a,0))
        self.assertEqual(commit,result);self.assertTrue(all(sha==commit for sha,path in calls))
        self.assertEqual(('1.0.2',47,'release'),restore.call_args.args[4:7])


if __name__=='__main__':unittest.main()
