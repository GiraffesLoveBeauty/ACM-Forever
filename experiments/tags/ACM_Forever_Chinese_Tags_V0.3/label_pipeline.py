#!/usr/bin/env python3
"""ACM-Forever V0.3 offline tag prep / merge / evaluation (Python standard library only).

This is an isolated experiment; it never edits the project's business DB.
"""
import argparse
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
TAXONOMY = json.loads((BASE / 'tag_taxonomy_v0.3.json').read_text(encoding='utf-8'))
MAPPING = json.loads((BASE / 'cf_mapping_v0.3.json').read_text(encoding='utf-8'))
TAG_BY_ID = {t['id']: t for t in TAXONOMY['tags']}
assert len(TAG_BY_ID) == len(TAXONOMY['tags'])


def unique(values):
    return list(dict.fromkeys(values))


def problem_key(p):
    platform = p.get('platform')
    contest = str(p.get('contest_id') or '')
    pid = str(p.get('problem_id') or '')
    if not platform or not pid:
        raise ValueError('Missing platform or problem_id')
    if platform == 'codeforces' and contest and pid.startswith(contest):
        pid = pid[len(contest):]  # normalize sample ID 2275H vs crawler ID H
    return f'{platform}:{contest}:{pid}'


def read_records(path):
    text = Path(path).read_text(encoding='utf-8-sig')
    if str(path).endswith('.jsonl'):
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    data = json.loads(text)
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get('problems'), list):
        return data['problems']
    raise ValueError('Input must be a JSON array, JSON with problems[], or JSONL')


def save_jsonl(records, path):
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open('w', encoding='utf-8') as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')


def prepare(p):
    source = p.get('platform')
    if source not in ('codeforces', 'atcoder'):
        raise ValueError(f'Unsupported platform: {source!r}; Niuke pending its schema')
    raw = p.get('tags') or []
    if isinstance(raw, dict):
        raw = raw.get('values') or []
    if not isinstance(raw, list) or not all(isinstance(s, str) for s in raw):
        raise ValueError('tags must be a list[str] or {values:list[str]}')

    exact = MAPPING['exact']; clue = MAPPING['clue']; prop = MAPPING['property']
    confirmed = unique([exact[t]['tag_id'] for t in raw if t in exact]) if source == 'codeforces' else []
    provisional = unique([clue[t]['provisional_tag_id'] for t in raw if t in clue]) if source == 'codeforces' else []
    hints = [t for t in raw if t in clue] if source == 'codeforces' else []
    properties = [t for t in raw if t in prop] if source == 'codeforces' else []
    unknown = [t for t in raw if t not in exact and t not in clue and t not in prop]
    key = problem_key(p)
    return {
        'problem_key': key, 'platform': source, 'contest_id': p.get('contest_id'),
        'problem_id': p.get('problem_id'), 'title': p.get('title') or p.get('problem_name'),
        'source_url': p.get('url') or p.get('problem_url'), 'content_hash': p.get('content_hash'),
        'raw_tags': raw, 'cf_exact_tag_ids': confirmed,
        'specific_tag_ids': confirmed, 'provisional_tag_ids': provisional,
        'specific_tag_names_zh': [TAG_BY_ID[t]['name_zh'] for t in confirmed],
        'provisional_tag_names_zh': [TAG_BY_ID[t]['name_zh'] for t in provisional],
        'cf_unresolved_hints': hints, 'problem_properties': properties,
        'unmapped_raw_tags': unknown, 'ai_specific_tag_ids': [],
        'review_status': 'needs_ai' if source == 'atcoder' or hints or not confirmed or unknown else 'rule_only',
        'needs_ai': bool(source == 'atcoder' or hints or not confirmed or unknown),
        'taxonomy_version': TAXONOMY['version'], 'ai_annotation': None,
    }


def validate_id_list(value, required_kind, field):
    if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
        raise ValueError(f'{field} must be list[str]')
    for value_id in value:
        if value_id not in TAG_BY_ID or TAG_BY_ID[value_id]['tag_kind'] != required_kind:
            raise ValueError(f'{field}: unsupported {required_kind} tag ID {value_id!r}')
    return unique(value)


def merge_one(base, pred):
    if pred['problem_key'] != base['problem_key']:
        raise ValueError('problem_key mismatch')
    if base.get('review_status') == 'human_confirmed':
        raise ValueError('Cannot overwrite human-confirmed labels with AI')
    if base.get('content_hash') and pred.get('content_hash') != base['content_hash']:
        raise ValueError('Missing or outdated content_hash in AI prediction')
    extra_specific = validate_id_list(pred.get('specific_tag_ids', []), 'specific', 'specific_tag_ids')
    extra_provisional = validate_id_list(pred.get('provisional_tag_ids', []), 'provisional', 'provisional_tag_ids')
    resolved = pred.get('resolved_cf_hints', {})
    if not isinstance(resolved, dict):
        raise ValueError('resolved_cf_hints must be a dictionary')
    if resolved and base['platform'] != 'codeforces':
        raise ValueError('Only Codeforces input may resolve original CF hints')
    allowed_hints = set(base.get('cf_unresolved_hints', []))
    resolved_ids = []
    for hint, values in resolved.items():
        if hint not in allowed_hints:
            raise ValueError(f'Cannot resolve missing CF hint {hint!r}')
        arr = validate_id_list(values, 'specific', f'resolved_cf_hints[{hint}]')
        if not arr:
            raise ValueError('An empty resolution cannot remove a provisional label')
        resolved_ids.extend(arr)
    if (extra_specific or extra_provisional or resolved_ids) and not str(pred.get('reason', '')).strip():
        raise ValueError('AI suggestions need a nonempty reason for human review')
    remaining = [t for t in base['provisional_tag_ids']
                 if t not in {MAPPING['clue'][hint]['provisional_tag_id'] for hint in resolved}]
    # The model must request the resolution explicitly; merely adding one specific tag
    # must not silently erase unrelated or possibly still relevant broad hints.
    specific = unique(base['cf_exact_tag_ids'] + extra_specific + resolved_ids)
    provisional = unique(remaining + extra_provisional)
    updated = dict(base)
    updated.update({
        'specific_tag_ids': specific,
        'provisional_tag_ids': provisional,
        'specific_tag_names_zh': [TAG_BY_ID[t]['name_zh'] for t in specific],
        'provisional_tag_names_zh': [TAG_BY_ID[t]['name_zh'] for t in provisional],
        'ai_specific_tag_ids': unique(extra_specific + resolved_ids),
        'cf_unresolved_hints': [h for h in base.get('cf_unresolved_hints', []) if h not in resolved],
        'ai_annotation': {k: pred.get(k) for k in ['model', 'reason', 'evidence_kind', 'resolved_cf_hints']},
        'review_status': 'ai_suggested_pending_human_review' if (extra_specific or extra_provisional or resolved_ids)
                         else 'ai_unresolved_pending_review',
        'needs_ai': False,
    })
    return updated


def merge_all(baselines, predictions):
    pred_by_id = {}
    for pred in predictions:
        key = pred['problem_key']
        if key in pred_by_id:
            raise ValueError(f'duplicate prediction for {key}')
        pred_by_id[key] = pred
    base_keys = {b['problem_key'] for b in baselines}
    unexpected = set(pred_by_id) - base_keys
    if unexpected:
        raise ValueError(f'prediction references unknown problem(s): {sorted(unexpected)[:3]}')
    return [merge_one(b, pred_by_id[b['problem_key']]) if b['problem_key'] in pred_by_id else b
            for b in baselines]


def evaluate(predictions, golds):
    by_key = {p['problem_key']: p for p in predictions}
    tp = fp = fn = 0
    n = specific_coverage = provisional_coverage = exact_matches = 0
    for gold in golds:
        if not gold.get('reviewed', False):
            continue
        key = gold['problem_key']
        if key not in by_key:
            raise ValueError(f'Gold problem missing from predictions: {key}')
        expected = set(validate_id_list(gold['accepted_specific_tag_ids'], 'specific', 'accepted_specific_tag_ids'))
        predicted = set(by_key[key]['specific_tag_ids'])
        tp += len(expected & predicted)
        fp += len(predicted - expected)
        fn += len(expected - predicted)
        n += 1
        specific_coverage += bool(predicted)
        provisional_coverage += bool(by_key[key]['provisional_tag_ids'])
        exact_matches += predicted == expected
    if not n:
        return {'reviewed_count':0,'message':'尚无人工确认样本；无法计算准确率'}
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if precision + recall else 0.0
    return {'reviewed_count':n,'true_positive':tp,'false_positive':fp,'false_negative':fn,
            'micro_precision':round(precision,4),'micro_recall':round(recall,4),
            'micro_f1':round(f1,4),'exact_match_rate':round(exact_matches/n,4),
            'specific_coverage':round(specific_coverage/n,4),
            'provisional_rate':round(provisional_coverage/n,4),
            'note':'仅评估人工确认的具体标签；临时标签单独统计，不当作正确细分算法。'}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='command', required=True)
    prep = sub.add_parser('prepare'); prep.add_argument('--input',required=True); prep.add_argument('--output',required=True)
    merge = sub.add_parser('merge'); merge.add_argument('--base',required=True); merge.add_argument('--ai',required=True); merge.add_argument('--output',required=True)
    ev = sub.add_parser('evaluate'); ev.add_argument('--predictions',required=True); ev.add_argument('--gold',required=True); ev.add_argument('--output',required=True)
    args = ap.parse_args()
    if args.command == 'prepare':
        result = [prepare(p) for p in read_records(args.input)]
        keys = [x['problem_key'] for x in result]
        if len(keys) != len(set(keys)): raise ValueError('Duplicate source problem ID')
        save_jsonl(result, args.output)
        print(f'Prepared {len(result)} problems; waiting AI: {sum(x["needs_ai"] for x in result)}')
    elif args.command == 'merge':
        result = merge_all(read_records(args.base), read_records(args.ai))
        save_jsonl(result, args.output)
        print(f'Merged {len(result)} problems, AI results: {len(read_records(args.ai))}')
    else:
        result = evaluate(read_records(args.predictions), read_records(args.gold))
        Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__ == '__main__': main()
