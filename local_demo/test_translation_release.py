"""Offline saved-response release contracts. Only synthetic problems and temporary data."""
from copy import deepcopy
import json
import re
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from server import ROOT
from annotation_api.config import Config
from annotation_api.adapter import digest
from annotation_api.storage import atomic_json
from problem_processing.executor import task_identity
from problem_processing.repository import Repository
from problem_processing.planning import historical_problem
from problem_processing.translation import MockTranslationClient, language_plan, prepare_request, current_translation
from problem_processing.execution_state import Ledger
from problem_processing import backup
from translation_release import build_release, publish_release


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='offline-release-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)/'labels'
        self.repo = Repository(self.root)
        self.key = 'atcoder:abc999:abc999_a'
        self.repo.import_records([{'problem_key':self.key,'platform':'atcoder',
            'contest_id':'abc999','problem_id':'abc999_a','original_title':'Synthetic test only',
            'original_statement':'Problem Statement\nFind the integer N.\n\nThe bound N is at most 2 \\times 10^5.\n\nConstraints\n\n- N is positive.\n\nInput\n\n```\nN\n```\n\nOutput\n\nPrint the answer.'}])
        ps,_ = self.repo.snapshot()
        self.problem = historical_problem(ps[self.key])
        prepared = prepare_request(self.problem,language_plan(self.problem))
        response = MockTranslationClient().call(prepared['messages']).as_dict()
        response['model'] = 'offline-fixture'
        cfg = Config(provider='compatible',model='offline-fixture',base_url='https://example.invalid/v1',api_key='synthetic-not-a-credential')
        self.ledger = Ledger(self.root)
        self.task = self.ledger.claim(task_identity(self.problem,'translation',cfg),self.problem)
        self.ledger.transition(self.task,'dispatched')
        response_hash = self.ledger.save_artifact('responses', self.task['attempt_id'], {
            'version': 1, 'task_id': self.task['task_id'],
            'attempt_id': self.task['attempt_id'], 'response': response})
        self.ledger.transition(self.task,'blocked',response_sha256=response_hash,error='test_structure_failure')
        token=next(k for k,v in prepared['protected'].items() if v.startswith('The bound'))
        self.edits={'protected_prose':{token:'N 的上界为 2 \\times 10^5。'}}

    def test_complete_saved_response_can_be_released_without_network(self):
        with patch('socket.socket.connect',side_effect=AssertionError('NO NETWORK')):
            row,audit=build_release(self.root,self.key,self.edits)
            publish_release(self.root,row,audit)
        self.assertEqual(current_translation(self.root,self.problem),row)
        self.assertEqual(row['original_statement'],self.problem['original_statement'])
        self.assertIn('N 的上界',row['statement_zh'])
        self.assertEqual(row['translation_origin'],'ai_offline_corrected')
        self.assertFalse(row['fully_human_verified'])
        self.assertEqual(audit['new_api_calls'],0)

    def test_publish_is_idempotent_and_history_immutable(self):
        first=build_release(self.root,self.key,self.edits)
        publish_release(self.root,*first)
        second=build_release(self.root,self.key,self.edits)
        self.assertEqual(first,second)
        publish_release(self.root,*second)
        self.assertEqual(len(list((self.root/'translations/history').glob('*.json'))),1)

    def release_backup(self):
        row, audit = build_release(self.root, self.key, self.edits)
        publish_release(self.root, row, audit)
        report = backup.create_backup(self.root, Path(self.temp.name)/'backups')
        return row, audit, Path(report['backup'])

    def test_published_translation_backup_and_isolated_restore_preserve_activation(self):
        with patch('socket.socket.connect', side_effect=AssertionError('NO NETWORK')):
            row, audit = build_release(self.root, self.key, self.edits)
            publish_release(self.root, row, audit)
            before = backup.inventory(self.root)
            report = backup.create_backup(self.root, Path(self.temp.name)/'backups')
            folder = Path(report['backup'])
            rel = 'translations/activations/' + row['request_fingerprint'] + '.json'
            self.assertIn('payload/' + rel, [f['path'] for f in report['files']])
            self.assertTrue(backup.verify_backup(folder)['verified'])
            restored = backup.restore_backup(folder, Path(self.temp.name)/'restored', active_root=self.root)
            restored_root = Path(restored['restored_data_root'])
            self.assertEqual((self.root/rel).read_bytes(), (restored_root/rel).read_bytes())
            self.assertEqual(json.loads((restored_root/rel).read_bytes()), audit)
            self.assertEqual(current_translation(restored_root, self.problem), row)
            self.assertEqual(backup.inventory(self.root), before)
            self.assertEqual(report['api_calls'], 0)
            self.assertEqual(restored['api_calls'], 0)

    def test_corrupt_activation_blocks_restore_before_target_creation(self):
        row, _, folder = self.release_backup()
        path = folder/'payload/translations/activations'/(row['request_fingerprint']+'.json')
        path.write_bytes(b'{}')
        target = Path(self.temp.name)/'restored'
        with self.assertRaisesRegex(ValueError, 'SHA-256'):
            backup.restore_backup(folder, target, active_root=self.root)
        self.assertFalse(target.exists())

    def test_missing_activation_blocks_restore_before_target_creation(self):
        row, _, folder = self.release_backup()
        (folder/'payload/translations/activations'/(row['request_fingerprint']+'.json')).unlink()
        target = Path(self.temp.name)/'restored'
        with self.assertRaises(ValueError):
            backup.restore_backup(folder, target, active_root=self.root)
        self.assertFalse(target.exists())

    def test_published_translation_missing_audit_is_not_backed_up(self):
        row, audit = build_release(self.root, self.key, self.edits)
        publish_release(self.root, row, audit)
        (self.root/'translations/activations'/(row['request_fingerprint']+'.json')).unlink()
        with self.assertRaisesRegex(ValueError, '缺少对应发布审计'):
            backup.create_backup(self.root, Path(self.temp.name)/'backups')

    def test_mismatched_activation_result_digest_is_not_backed_up(self):
        row, audit = build_release(self.root, self.key, self.edits)
        publish_release(self.root, row, audit)
        audit['accepted_result_sha256'] = '0'*64
        atomic_json(self.root/'translations/activations'/(row['request_fingerprint']+'.json'), audit)
        with self.assertRaisesRegex(ValueError, '发布审计与历史结果不对应'):
            backup.create_backup(self.root, Path(self.temp.name)/'backups')

    def test_activation_allowlist_rejects_other_paths(self):
        fp = 'a'*64
        self.assertTrue(backup.allowed_data_path('translations/activations/'+fp+'.json'))
        self.assertTrue(backup.allowed_data_directory('translations/activations'))
        for path in ('translations/activations/.env', 'translations/activations/other.json',
                     'translations/activations/../'+fp+'.json',
                     'translations/activations/nested/'+fp+'.json'):
            self.assertFalse(backup.allowed_data_path(path))
        self.assertFalse(backup.allowed_data_directory('translations/activations/nested'))

    def test_activation_sensitive_fields_still_block_backup(self):
        row, audit = build_release(self.root, self.key, self.edits)
        publish_release(self.root, row, audit)
        audit['authorization'] = 'synthetic-sensitive-value'
        atomic_json(self.root/'translations/activations'/(row['request_fingerprint']+'.json'), audit)
        with self.assertRaisesRegex(ValueError, '敏感') as raised:
            backup.create_backup(self.root, Path(self.temp.name)/'backups')
        self.assertNotIn('synthetic-sensitive-value', str(raised.exception))

    def test_original_response_and_blocked_task_remain_unchanged(self):
        paths=list((self.root/'execution').rglob('*.json'))
        before={p:p.read_bytes() for p in paths}
        publish_release(self.root,*build_release(self.root,self.key,self.edits))
        self.assertEqual(before,{p:p.read_bytes() for p in paths})

    def test_uncertain_delivery_cannot_be_released(self):
        self.task['state']='uncertain';self.task['attempts'][-1]['events'][-1]['state']='uncertain'
        self.ledger.save(self.task)
        with self.assertRaises(ValueError):build_release(self.root,self.key,self.edits)

    def test_tampered_response_rejected(self):
        path=self.ledger.path('responses',self.task['attempt_id'])
        value=json.loads(path.read_text());value['response']['content']='{}';atomic_json(path,value)
        with self.assertRaises(ValueError):build_release(self.root,self.key,self.edits)

    def test_number_change_rejected(self):
        edits=deepcopy(self.edits)
        key=next(iter(edits['protected_prose']));edits['protected_prose'][key]=edits['protected_prose'][key].replace('2','3')
        with self.assertRaises(ValueError):build_release(self.root,self.key,edits)

    def test_variable_change_rejected(self):
        edits=deepcopy(self.edits)
        key=next(iter(edits['protected_prose']));edits['protected_prose'][key]=edits['protected_prose'][key].replace('N','M')
        with self.assertRaises(ValueError):build_release(self.root,self.key,edits)

    def test_unbound_output_rejected_before_write(self):
        row,audit=build_release(self.root,self.key,self.edits)
        row['statement_zh']+='changed'
        with self.assertRaises(ValueError):publish_release(self.root,row,audit)
        self.assertFalse((self.root/'translations/current.json').exists())

    def test_missing_placeholder_rejected(self):
        edits=deepcopy(self.edits)
        edits['segments']={'0':'题目描述\n整数。'}
        with self.assertRaises(ValueError):build_release(self.root,self.key,edits)

    def test_source_changed_after_validation_rejected(self):
        row,audit=build_release(self.root,self.key,self.edits)
        row['source_verified_hash']='0'*64;audit['accepted_result_sha256']=digest(row)
        with self.assertRaises(ValueError):publish_release(self.root,row,audit)


class FormulaOrderReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='formula-order-release-')
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'labels'
        repo=Repository(self.root)
        self.key='atcoder:abc998:abc998_a'
        repo.import_records([{'problem_key':self.key,'platform':'atcoder','contest_id':'abc998',
            'problem_id':'abc998_a','original_title':'Synthetic formula order',
            'original_statement':'Problem Statement\n\nConstruct a sequence $a$ of length $2^M$.\n\n'
                'Constraints\n\n- $M$ is positive.\n\nInput\n\n```\nM\n```\n\nOutput\n\nPrint the sequence.'}])
        p=historical_problem(repo.snapshot()[0][self.key])
        prepared=prepare_request(p,language_plan(p))
        source=next(s for s in prepared['segments'] if 'Construct a sequence' in s['text'])
        tokens=re.findall(r'__ACM_KEEP_\d+__',source['text'])
        self.assertEqual(len(tokens),2)
        response=MockTranslationClient().call(prepared['messages']).as_dict()
        response['model']='offline-fixture'
        content=json.loads(response['content'])
        next(s for s in content['segments'] if s['id']==source['id'])['text']=f'构造长度为 {tokens[1]} 的序列 {tokens[0]}。'
        response['content']=json.dumps(content,ensure_ascii=False)
        cfg=Config(provider='compatible',model='offline-fixture',base_url='https://example.invalid/v1',api_key='synthetic-not-a-credential')
        ledger=Ledger(self.root)
        task=ledger.claim(task_identity(p,'translation',cfg),p)
        ledger.transition(task,'dispatched')
        response_hash=ledger.save_artifact('responses',task['attempt_id'],{
            'task_id':task['task_id'],'attempt_id':task['attempt_id'],'response':response})
        ledger.transition(task,'blocked',response_sha256=response_hash,error='test_formula_order')
        self.edits={'segments':{str(source['id']):f'构造序列 {tokens[0]}，其长度为 {tokens[1]}。'},
            'reason':'离线调整中文语序，保留全部原始公式及响应。'}

    def test_reordered_fixed_formulas_are_not_silently_accepted(self):
        with self.assertRaisesRegex(ValueError,'顺序'):
            build_release(self.root,self.key,{})
        self.assertFalse((self.root/'translations/current.json').exists())

    def test_explicit_offline_correction_keeps_paid_response_and_audit(self):
        before={p:p.read_bytes() for p in (self.root/'execution').rglob('*.json')}
        with patch('socket.socket.connect',side_effect=AssertionError('NO NETWORK')):
            row,audit=build_release(self.root,self.key,self.edits)
            publish_release(self.root,row,audit)
        self.assertEqual(before,{p:p.read_bytes() for p in before})
        self.assertEqual(audit['new_api_calls'],0)
        self.assertEqual(len(audit['segment_corrections']),1)
        self.assertEqual(row['translation_origin'],'ai_offline_corrected')
        self.assertFalse(row['fully_human_verified'])
        self.assertIn('构造序列 $a$，其长度为 $2^M$。',row['statement_zh'])


if __name__=='__main__':unittest.main()
