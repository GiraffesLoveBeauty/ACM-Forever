"""Orphan recovery uses OS locks and saved evidence, never a network request."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

from server import create_local_app, isolate_environment, ADMIN_PASSWORD
from ai_execution import ExecutionConflict
from annotation_api.storage import atomic_json
from problem_processing.execution_state import Ledger
from problem_processing.executor import task_identity
from tag_management.storage import Journal
from test_ai_execution import Fixture


class OrphanRecoveryTests(Fixture, unittest.TestCase):
    def setUp(self):self.fixture()

    def receipt(self, job, **fields):
        row=self.service._read(job['job_id'])
        row.update(fields)
        atomic_json(self.service.job_path(job['job_id']),row)
        return row

    def stale(self, job, status='queued'):
        timestamp=(datetime.now(timezone.utc)-timedelta(minutes=2)).isoformat()
        return self.receipt(job,status=status,created_at=timestamp,updated_at=timestamp)

    def claim(self, job, state='claimed', bind=True):
        ledger=Ledger(self.labels.root)
        row=ledger.claim(task_identity(self.problem,job['task_type'],self.cfg),self.problem)
        if state=='dispatched':ledger.transition(row,state)
        if bind:self.receipt(job,execution_task_id=row['task_id'],execution_attempt_id=row['attempt_id'])
        return ledger,row

    def assert_other_question_can_queue(self):
        p=self.crawler_only()
        proposal=self.service.proposal(p,'translation')
        result=self.service.submit(p,'atcoder','abc999_b','translation',proposal['revision'],'1')
        self.assertEqual(result['status'],'queued',result)

    def test_abandoned_queue_is_terminal_and_unblocks_other_questions(self):
        job=self.queue();self.stale(job)
        self.service.recover_jobs()
        saved=self.service.read(job['job_id'])
        self.assertEqual(saved['status'],'blocked')
        self.assertEqual(saved['recovery']['previous_status'],'queued')
        self.assertEqual(saved['recovery']['ledger'],[])
        self.assertEqual(Ledger(self.labels.root).records(),[])
        self.assert_other_question_can_queue()

    def test_duplicate_submission_recovers_then_returns_original_terminal_receipt(self):
        job=self.queue();self.stale(job)
        result=self.queue()
        self.assertEqual(result['job_id'],job['job_id'])
        self.assertEqual(result['status'],'blocked')
        self.assertEqual(len(self.launched),1)

    def test_submit_recovers_orphans_before_global_busy_check(self):
        self.stale(self.queue())
        self.assert_other_question_can_queue()

    def test_latest_and_status_reads_recover_without_relaunch(self):
        job=self.queue();self.stale(job,'running')
        self.assertEqual(self.service.latest('atcoder','abc999_a')['annotation']['status'],'blocked')
        snapshot=self.service.job_path(job['job_id']).read_bytes()
        self.service.read(job['job_id']);self.service.recover_jobs()
        self.assertEqual(self.service.job_path(job['job_id']).read_bytes(),snapshot)
        self.assertEqual(len(self.launched),1)

    def test_recent_queue_retains_bounded_startup_window(self):
        job=self.queue();self.service.recover_jobs()
        self.assertEqual(self.service.read(job['job_id'])['status'],'queued')
        with self.assertRaises(ExecutionConflict):self.queue('translation')
        self.stale(job)
        self.service.recover_jobs()
        self.assertEqual(self.service.read(job['job_id'])['status'],'blocked')

    def test_running_without_ledger_is_recovered_immediately(self):
        job=self.queue();self.receipt(job,status='running')
        self.assertEqual(self.service.read(job['job_id'])['status'],'blocked')

    def test_live_worker_lock_wins_over_old_timestamps(self):
        job=self.queue();self.stale(job,'running')
        with self.service.worker_guard(job['job_id']):
            self.service.recover_jobs()
            self.assertEqual(self.service.read(job['job_id'])['status'],'running')
            with self.assertRaises(ExecutionConflict):self.queue('translation')
        self.assertEqual(self.service.read(job['job_id'])['status'],'blocked')

    def test_executor_lock_prevents_false_orphan_recovery(self):
        job=self.queue();self.stale(job,'running');ledger,row=self.claim(job,'dispatched')
        with ledger.locked(self.problem['problem_key'],'annotation'):
            self.service.recover_jobs()
            self.assertEqual(self.service._read(job['job_id'])['status'],'running')
            self.assertEqual(ledger.load(row['task_id'])['state'],'dispatched')
        self.service.recover_jobs()
        self.assertEqual(ledger.load(row['task_id'])['state'],'uncertain')

    def test_launch_writer_lock_prevents_recovery_during_handoff(self):
        job=self.queue();self.stale(job)
        with Journal(self.service.store/'writer.jsonl').locked():
            self.service.recover_jobs()
            self.assertEqual(self.service._read(job['job_id'])['status'],'queued')

    def test_claimed_task_becomes_audited_blocked_without_dispatch(self):
        job=self.queue();self.stale(job,'running');ledger,row=self.claim(job)
        self.service.recover_jobs()
        record=ledger.load(row['task_id'])
        self.assertEqual(record['state'],'blocked')
        self.assertEqual([e['state'] for e in record['attempts'][-1]['events']],['claimed','blocked'])
        self.assertFalse(self.service.proposal(self.problem,'annotation')['can_execute'])
        self.assert_other_question_can_queue()

    def test_dispatched_task_becomes_uncertain_and_never_retries(self):
        job=self.queue();self.stale(job,'running');ledger,row=self.claim(job,'dispatched')
        self.service.recover_jobs()
        self.assertEqual(ledger.load(row['task_id'])['state'],'uncertain')
        receipt=self.service.read(job['job_id'])
        self.assertEqual(receipt['status'],'uncertain')
        self.assertIsNone(receipt['real_api_calls'])
        self.assertIn('是否计费尚无法确认',receipt['message'])
        result=self.service.run(job['job_id'],client=self.client())
        self.assertEqual(result['status'],'uncertain');self.assertEqual(self.requests,[])
        self.assertFalse(self.service.proposal(self.problem,'annotation')['can_execute'])
        self.assert_other_question_can_queue()

    def test_saved_response_is_preserved_for_review_without_republication(self):
        job=self.queue();self.stale(job,'running');ledger,row=self.claim(job,'dispatched')
        envelope={'task_id':row['task_id'],'attempt_id':row['attempt_id'],
                  'response':{'content':'saved candidate','usage':{'total_tokens':23},'model':'offline-response'}}
        # Simulate exit after the response file is saved but before its hash is recorded.
        ledger.save_artifact('responses',row['attempt_id'],envelope)
        original=ledger.path('responses',row['attempt_id']).read_bytes()
        self.service.recover_jobs()
        result=self.service.read(job['job_id'])
        self.assertEqual(result['status'],'blocked')
        self.assertEqual(result['error'],'saved_response_requires_review')
        self.assertEqual(result['usage'],{'total_tokens':23})
        self.assertEqual(ledger.load(row['task_id'])['state'],'blocked')
        self.assertEqual(ledger.path('responses',row['attempt_id']).read_bytes(),original)
        self.assertFalse(ledger.path('results',row['task_id']).exists())
        self.assert_other_question_can_queue()

    def test_corrupt_response_retains_evidence_and_marks_delivery_uncertain(self):
        job=self.queue();self.stale(job,'running');ledger,row=self.claim(job,'dispatched')
        path=ledger.path('responses',row['attempt_id']);path.parent.mkdir(parents=True)
        path.write_bytes(b'{damaged response')
        self.service.recover_jobs()
        self.assertEqual(self.service.read(job['job_id'])['status'],'uncertain')
        self.assertEqual(ledger.load(row['task_id'])['state'],'uncertain')
        self.assertEqual(path.read_bytes(),b'{damaged response')
        self.assert_other_question_can_queue()

    def test_future_queue_timestamp_cannot_hold_global_slot_forever(self):
        job=self.queue()
        self.receipt(job,created_at=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat())
        self.assertEqual(self.service.read(job['job_id'])['status'],'blocked')

    def test_completed_ledger_repairs_lost_success_receipt_and_usage(self):
        job=self.queue();completed=self.service.run(job['job_id'],client=self.client())
        self.assertEqual(completed['status'],'completed')
        self.receipt(job,status='running',usage=None)
        result=self.service.read(job['job_id'])
        self.assertEqual(result['status'],'completed')
        self.assertEqual(result['usage'],completed['usage'])
        self.assertEqual(result['recovery']['ledger'][0]['state'],'completed')
        self.assertEqual(len(self.requests),1)

    def test_legacy_receipt_matches_only_attempts_after_queue_creation(self):
        job=self.queue();self.stale(job,'running');ledger,row=self.claim(job,'dispatched',bind=False)
        self.service.recover_jobs()
        self.assertEqual(ledger.load(row['task_id'])['state'],'uncertain')
        self.assertEqual(self.service.read(job['job_id'])['status'],'uncertain')

    def test_old_unrelated_attempt_is_not_reported_as_this_workers_success(self):
        job=self.queue();self.service.run(job['job_id'],client=self.client())
        completed=self.service._read(job['job_id'])
        from annotation_api.adapter import digest
        other=dict(completed,job_id=digest('synthetic-later-receipt'),status='running',
                   created_at=datetime.now(timezone.utc).isoformat())
        other.pop('execution_task_id');other.pop('execution_attempt_id')
        atomic_json(self.service.job_path(other['job_id']),other)
        result=self.service.read(other['job_id'])
        self.assertEqual(result['status'],'blocked')
        self.assertEqual(result['recovery']['ledger'],[])

    def test_missing_bound_ledger_blocks_only_receipt_without_fabricating_success(self):
        job=self.queue();self.stale(job,'running')
        self.receipt(job,execution_task_id='a'*64,execution_attempt_id='b'*64)
        result=self.service.read(job['job_id'])
        self.assertEqual(result['status'],'blocked')
        self.assertEqual(result['error'],'worker_recovery_requires_review')
        self.assertIsNone(result['real_api_calls'])
        self.assert_other_question_can_queue()

    def test_late_worker_cannot_send_after_queue_is_recovered(self):
        job=self.queue();self.stale(job)
        self.service.recover_jobs()
        result=self.service.run(job['job_id'],client=self.client())
        self.assertEqual(result['status'],'blocked');self.assertEqual(self.requests,[])

    def test_real_process_lock_release_after_termination_enables_recovery(self):
        job=self.queue();self.stale(job,'running');ledger,row=self.claim(job,'dispatched')
        ready=Path(self.temp.name)/'worker-ready'
        module=Path(__file__).resolve().parents[1]/'experiments/tags/ACM_Forever_Chinese_Tags_V0.3'
        code=('import sys; from pathlib import Path; sys.path.insert(0,sys.argv[1]); '
              'from tag_management.storage import Journal; '
              'guard=Journal(sys.argv[2]).locked(); guard.__enter__(); '
              'Path(sys.argv[3]).write_text("ready"); sys.stdin.read()')
        process=subprocess.Popen([sys.executable,'-B','-c',code,str(module),
            str(self.service.store/'worker-locks'/(job['job_id']+'.jsonl')),str(ready)],
            stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        def close():
            if process.poll() is None:process.terminate()
            process.wait(timeout=10)
            process.stdin.close();process.stderr.close()
        self.addCleanup(close)
        deadline=time.monotonic()+10
        while not ready.exists() and process.poll() is None and time.monotonic()<deadline:time.sleep(.02)
        self.assertTrue(ready.exists(),'isolated lock worker did not start')
        self.service.recover_jobs()
        self.assertEqual(self.service._read(job['job_id'])['status'],'running')
        process.terminate();process.wait(timeout=10)
        self.service.recover_jobs()
        self.assertEqual(self.service.read(job['job_id'])['status'],'uncertain')
        self.assertEqual(ledger.load(row['task_id'])['state'],'uncertain')
        self.assert_other_question_can_queue()

    def test_service_registration_recovers_old_receipts_on_startup(self):
        job=self.queue();self.stale(job)
        with patch.dict('os.environ'):
            isolate_environment(self.database)
            create_local_app(self.labels)
        self.assertEqual(self.service._read(job['job_id'])['status'],'blocked')


class OrphanStatusRouteTests(Fixture,unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.fixture()
        env=patch.dict('os.environ');env.start();self.addCleanup(env.stop)
        isolate_environment(self.database)
        self.app=create_local_app(self.labels)
        self.service=self.app.extensions['local_ai_execution']
        self.service.config_loader=lambda:self.cfg;self.service.launcher=self.launched.append
        self.browser=self.app.test_client()

    async def test_status_poll_recovers_orphan_with_audit_and_no_api(self):
        job=self.queue()
        row=self.service._read(job['job_id']);row['status']='running'
        atomic_json(self.service.job_path(job['job_id']),row)
        response=await self.browser.post('/api/auth/login',json={'qq_id':'1','password':ADMIN_PASSWORD})
        self.assertEqual(response.status_code,200)
        response=await self.browser.get('/api/admin/problem-processing/jobs/'+job['job_id'])
        self.assertEqual(response.status_code,200)
        result=await response.get_json()
        self.assertEqual(result['status'],'blocked');self.assertIn('recovery',result)
        self.assertNotIn(self.cfg.api_key,json.dumps(result))
        self.assertEqual(len(self.launched),1)


if __name__=='__main__':unittest.main()
