"""Shareable integration fixtures. No downloaded statements or saved paid responses.

Task records imitate legacy acceptance evidence entirely offline. The model name
is explicitly synthetic; live identity here exercises receipt validation only.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'experiments/tags/ACM_Forever_Chinese_Tags_V0.3'))

from annotation_api.adapter import adapt
from annotation_api.config import Config
from label_pipeline import TAXONOMY
from problem_processing.adapter import normalize
from problem_processing.repository import Repository
from problem_processing.planning import historical_problem, task_policies
from problem_processing.executor import task_identity
from problem_processing.execution_state import Ledger
from problem_processing.translation import MockTranslationClient, prepare_request, language_plan
from translation_release import build_release, publish_release


def build_fixture(root):
    root = Path(root)
    records = []
    # Familiar IDs are identifiers only. All names, statements and outputs below
    # are invented test data, not the corresponding OJ problems.
    ids = [('abc464', 'abc464_c'), ('abc469', 'abc469_a')]
    ids += [('offline', f'offline_{i}') for i in range(8)]
    for contest, pid in ids:
        records.append(normalize({
            'platform': 'atcoder', 'problem_key': f'atcoder:{contest}:{pid}',
            'contest_id': contest, 'problem_id': pid,
            'original_title': 'Synthetic integration fixture ' + pid,
            'original_statement': 'Problem Statement\n\nFind the value of the integer.\n\n'
                'Constraints\n\n- The integer is positive.\n\nInput\n\n```\n1\n```\n\n'
                'Output\n\nPrint the integer.\n\n```\n1\n```',
            'source_links': [f'https://atcoder.jp/contests/{contest}/tasks/{pid}']}))
    annotations = [{
        'problem_key': p['problem_key'], 'platform': 'atcoder', 'title': p['original_title'],
        'content_hash': p['content_hash'], 'taxonomy_version': TAXONOMY['version'],
        'raw_tags': [], 'specific_tag_ids': ['difference_array'] if p['problem_id']=='abc464_c' else ['enumeration'],
        'provisional_tag_ids': [], 'api_call_status': 'success', 'human_review_status': 'pending_review',
        'model': 'synthetic-offline-fixture', 'processing_policy': task_policies()['annotation'],
        'annotation_input_hash': adapt(p)['annotation_input_hash']
    } for p in records]
    repo = Repository(root)
    repo.import_records(records, annotations)
    cfg = Config(provider='compatible', model='synthetic-offline-fixture',
                 base_url='https://example.invalid/v1', api_key='synthetic-not-a-credential')
    ledger = Ledger(root)
    for row in repo.snapshot()[0].values():
        p = historical_problem(row)
        prepared = prepare_request(p, language_plan(p))
        response = MockTranslationClient().call(prepared['messages']).as_dict()
        response['model'] = 'synthetic-offline-fixture'
        task = ledger.claim(task_identity(p, 'translation', cfg), p)
        ledger.transition(task, 'dispatched')
        response_hash = ledger.save_artifact('responses', task['attempt_id'], {'response': response})
        ledger.transition(task, 'blocked', response_sha256=response_hash, error='synthetic_saved_response')
        publish_release(root, *build_release(root, p['problem_key'], {}))
    return root
