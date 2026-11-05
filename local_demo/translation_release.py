"""Auditable local acceptance of saved AI responses; never imports/calls a network client."""
from collections import Counter
from copy import deepcopy
import json
import re

from annotation_api.adapter import digest
from annotation_api.storage import atomic_json, now
from problem_processing.execution_state import Ledger
from problem_processing.planning import historical_problem, task_policies, semantic_inputs
from problem_processing.repository import Repository
from problem_processing.translation import (TRANSLATION_VERSION, TOKEN, language_plan,
                                             prepare_request, validate_translation)
from tag_management.storage import Journal


def build_release(root, key, edits):
    repo = Repository(root)
    problems, _ = repo.snapshot()
    p = historical_problem(problems[key])
    ledger = Ledger(repo.root)
    rows = [r for r in ledger.records() if r['problem_key'] == key and r['task_type'] == 'translation']
    if len(rows) != 1:
        raise ValueError('Translation response identity is ambiguous')
    task = rows[0]
    if task['identity']['mode'] != 'live' or task['identity']['input_semantic_hash'] != digest(semantic_inputs(p)[1]):
        raise ValueError('Saved response does not match current source semantics')
    if task['state'] not in {'completed', 'blocked'} or not task.get('response_sha256'):
        raise ValueError('Unknown delivery cannot be accepted or retried automatically')
    response = ledger.artifact('responses', task['attempt_id'], task['response_sha256'])['response']
    if response.get('refused') or response.get('finish_reason') != 'stop':
        raise ValueError('Incomplete response cannot be accepted')
    content = json.loads(response['content'])
    prepared = prepare_request(p, language_plan(p))
    corrected = deepcopy(content)
    mapping = edits.get('token_mapping', {})
    if task['identity']['policy']['revision'] != TRANSLATION_VERSION and not mapping:
        raise ValueError('Old placeholder policy needs an explicit audited mapping')
    if mapping:
        for segment in corrected['segments']:
            segment['text'] = TOKEN.sub(lambda m: mapping[m[0]], segment['text'])
    changes = []
    for segment in corrected['segments']:
        updated = edits.get('segments', {}).get(str(segment['id']))
        if updated is not None:
            changes.append({'segment_id':segment['id'], 'before':segment['text'], 'after':updated})
            segment['text'] = updated
    # Old protection froze prose lines containing LaTeX. Translate only the explicitly listed
    # prose blocks while retaining their mathematical commands, numeric values and inline code.
    prose = []
    reviewed_prepared = deepcopy(prepared)
    for token, translated in edits.get('protected_prose', {}).items():
        source = prepared['protected'][token]
        stripped = re.sub(r'\\[A-Za-z]+', '', source)
        if not re.search(r'\b[A-Za-z]{3,}\b', stripped) or source.startswith(('```','`','http')):
            raise ValueError('Only documented frozen English prose may be corrected')
        commands = lambda text: Counter(re.findall(r'\\[A-Za-z]+', text))
        numbers = lambda text: Counter(re.findall(r'\d+', text))
        inline_code = lambda text: re.findall(r'`[^`\n]*`', text)
        def symbols(text):
            text = re.sub(r"\b[A-Za-z]{2,}['’]s\b", '', text)
            text = re.sub(r'\\[A-Za-z]+', '', text)
            return Counter(s for s in re.findall(r"(?<![A-Za-z])[A-Za-z](?:'(?![A-Za-z]))?(?![A-Za-z])", text)
                           if s not in {'a', 'A', 'I'})
        if commands(source) != commands(translated) or numbers(source) != numbers(translated) or inline_code(source) != inline_code(translated):
            raise ValueError('Prose correction changed protected mathematics, numbers or code')
        if symbols(source) != symbols(translated):
            raise ValueError('Prose correction changed mathematical variable identities')
        reviewed_prepared['protected'][token] = translated
        prose.append({'token':token,'source':source,'translation':translated,
                      'checks':{'tex_commands_equal':True,'numbers_equal':True,'inline_code_equal':True}})
    title, statement = validate_translation(json.dumps(corrected, ensure_ascii=False), reviewed_prepared)
    # Code blocks, including sample input/output bytes, are copied exactly from the source.
    code = re.compile(r'(?m)^ {0,3}(`{3,}|~{3,})[^\n]*\n[\s\S]*?^ {0,3}\1[ \t]*\r?(?:\n|$)')
    blocks = lambda text: [m[0] for m in code.finditer(text)]
    if blocks(language_plan(p)['source_text']) != blocks(statement):
        raise ValueError('Sample/code block bytes changed')
    audit = {'version':1,'problem_key':key,'source_task_id':task['task_id'],
             'source_attempt_id':task['attempt_id'],'source_response_sha256':task['response_sha256'],
             'source_task_state':task['state'],'source_content_hash':p['content_hash'],
             'source_verified_hash':p['verified_content_hash'],'validation_version':TRANSLATION_VERSION,
             'token_mapping':mapping,'segment_corrections':changes,'protected_prose_corrections':prose,
             'reason':edits.get('reason','Saved AI response checked for local website acceptance'),
             'checks':{'strict_structure_validator_passed':True,'sample_blocks_byte_identical':True},
             'fully_human_verified':False,'reviewer':'codex_offline','new_api_calls':0}
    corrected_output = bool(mapping or changes or prose)
    origin = 'ai_offline_corrected' if corrected_output else 'ai'
    fingerprint = digest({'audit':audit,'title_zh':title,'statement_zh':statement})
    row = {'problem_key':key,'original_title':p['original_title'],'original_statement':p['original_statement'],
           'source_links':p['source_links'],'source_language':language_plan(p)['source_language'],'target_language':'zh-CN',
           'title_zh':title,'statement_zh':statement,'source_content_hash':p['content_hash'],
           'source_verified_hash':p['verified_content_hash'],'translation_status':'auto',
           'translation_origin':origin,'translation_review_status':'pending_user_acceptance',
           'fully_human_verified':False,'translation_model':response['model'],'model':response['model'],
           'translation_version':TRANSLATION_VERSION,'processing_policy':task_policies()['translation'],
           'request_fingerprint':fingerprint,'source_execution_task_id':task['task_id'],
           'activation_audit_id':fingerprint,'usage':response.get('usage'),
           'elapsed_seconds':response.get('elapsed_seconds'),'request_id':response.get('request_id'),
           'execution_request_settings':task['identity']['request_settings'],
           'updated_at':now(),'prediction_origin':'ai','error':None}
    audit.update(audit_id=fingerprint,accepted_result_sha256=digest(row),decision='accept_for_local_website',created_at=now())
    existing = repo.root/'translations/history'/(fingerprint+'.json')
    evidence = repo.root/'translations/activations'/(fingerprint+'.json')
    if existing.exists() or evidence.exists():
        if not existing.exists() or not evidence.exists():
            raise ValueError('Incomplete existing activation requires inspection')
        previous = json.loads(existing.read_text(encoding='utf-8'))
        proof = json.loads(evidence.read_text(encoding='utf-8'))
        row['updated_at'] = previous['updated_at']
        audit.update(created_at=proof['created_at'],accepted_result_sha256=digest(row))
        if row != previous or audit != proof:
            raise ValueError('Existing activation is inconsistent')
    return row, audit


def publish_release(root, row, audit):
    repo = Repository(root)
    if (not re.fullmatch(r'[0-9a-f]{64}',row['request_fingerprint']) or
            digest(row) != audit['accepted_result_sha256'] or audit['decision'] != 'accept_for_local_website' or
            audit['problem_key'] != row['problem_key']):
        raise ValueError('Invalid activation evidence')
    with repo.lock.locked():
        problems, _ = repo.snapshot()
        p = problems[row['problem_key']]
        if (p['verified_content_hash'] != row['source_verified_hash'] or p['content_hash'] != row['source_content_hash']
                or p['original_statement'] != row['original_statement'] or p['original_title'] != row['original_title']):
            raise ValueError('Source changed during acceptance')
        with Journal(repo.root / 'translations/writer.jsonl').locked():
            fp = row['request_fingerprint']
            for path, value in ((repo.root/'translations/history'/(fp+'.json'),row),
                                (repo.root/'translations/activations'/(fp+'.json'),audit)):
                if path.exists():
                    previous = json.loads(path.read_text(encoding='utf-8'))
                    if previous != value: raise ValueError('Immutable release already exists')
                else: atomic_json(path, value)
            pointer = repo.root / 'translations/current.json'
            index = json.loads(pointer.read_text(encoding='utf-8')) if pointer.exists() else {}
            index[row['problem_key']] = fp
            atomic_json(pointer, index)
