#!/usr/bin/env python3
"""Stratified, deterministic exploration/holdout split from original crawler exports."""
import argparse
import json
import random
from collections import Counter
from pathlib import Path
from label_pipeline import prepare,save_jsonl

SEED=20261009

def take(pool, n, rng):
    return rng.sample(pool, min(n,len(pool)))

def plain(p):
    statement=p.get('statement') or {}
    editorial=p.get('editorial') or {}
    tags=p.get('tags') or {}
    raw=tags.get('values',[]) if isinstance(tags,dict) else tags
    return {
      'problem_key':prepare(p)['problem_key'],'platform':p['platform'],
      'title':p.get('title'), 'url':p.get('url'),
      'raw_tags':raw or [],
      'statement_markdown':statement.get('markdown'),
      'statement_status':statement.get('status'),
      'editorial_status':editorial.get('status'),
      'verified_editorial_markdown':editorial.get('markdown') if p['platform']=='codeforces' and editorial.get('status')=='ok' else None,
      'difficulty':p.get('difficulty'),
      'contest_score':p.get('contest_score'),
      'content_hash':p.get('content_hash'),
    }

def choose_cf(problems,rng):
    groups={'broad_and_exact':[],'broad_only':[],'exact_only':[],'no_labels':[]}
    for p in problems:
      b=prepare(p)
      if b['provisional_tag_ids'] and b['specific_tag_ids']: typ='broad_and_exact'
      elif b['provisional_tag_ids']: typ='broad_only'
      elif b['specific_tag_ids']: typ='exact_only'
      else: typ='no_labels'
      groups[typ].append(p)
    picks=[]
    for typ,n in [('broad_and_exact',5),('broad_only',3),('exact_only',2)]:
      chosen=take(groups[typ],n,rng)
      picks += chosen
    remain=[p for p in problems if p not in picks]
    if len(picks)<10:picks += take(remain,10-len(picks),rng)
    left=[p for p in problems if p not in picks]
    holdout=take(left,30,rng)
    return picks,holdout,dict((k,len(v)) for k,v in groups.items())

def choose_atcoder(problems,rng):
    groups={'abc':[],'arc':[],'other':[]}
    for p in problems:
      x=p['contest_id'][:3]
      groups[x if x in groups else 'other'].append(p)
    # diverse ABC/ARC + other contest families; points are not difficulty ratings
    explore=[]
    for typ,n in [('abc',6),('arc',3),('other',1)]:explore+=take(groups[typ],n,rng)
    left=[p for p in problems if p not in explore]
    holdout=[]
    for typ,n in [('abc',18),('arc',9),('other',3)]:
      holdout+=take([p for p in left if p['contest_id'].startswith(typ) if typ!='other'] if typ!='other'
                      else [p for p in left if p['contest_id'][:3] not in ('abc','arc')],n,rng)
    return explore,holdout,dict((k,len(v)) for k,v in groups.items())

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--cf',required=True);p.add_argument('--atcoder',required=True);p.add_argument('--output-dir',default='data')
    a=p.parse_args()
    dest=Path(a.output_dir);dest.mkdir(parents=True,exist_ok=True)
    rng=random.Random(SEED)
    problem_sets={}
    for key,f in [('codeforces',a.cf),('atcoder',a.atcoder)]:
      data=json.loads(Path(f).read_text(encoding='utf-8-sig'))
      problem_sets[key]=data['problems'] if isinstance(data,dict) else data
    cf_exp,cf_hold,cf_stats=choose_cf(problem_sets['codeforces'],rng)
    atc_exp,atc_hold,atc_stats=choose_atcoder(problem_sets['atcoder'],rng)
    keys=[]
    for source,data in problem_sets.items():
      all_baseline=[prepare(x) for x in data]
      save_jsonl(all_baseline,dest/f'{source}_baseline_all.jsonl')
      keys += [x['problem_key'] for x in all_baseline]
    if len(keys)!=len(set(keys)):raise ValueError('duplicate keys in input')
    exploration=cf_exp+atc_exp
    holdout=cf_hold+atc_hold
    save_jsonl([plain(p) for p in exploration],dest/'exploration_inputs_20.jsonl')
    save_jsonl([plain(p) for p in holdout],dest/'holdout_inputs_60.jsonl')
    save_jsonl([prepare(p) for p in exploration],dest/'exploration_rule_baseline_20.jsonl')
    save_jsonl([prepare(p) for p in holdout],dest/'holdout_rule_baseline_60.jsonl')
    for name,problems in [('exploration',exploration),('holdout',holdout)]:
      save_jsonl([{'problem_key':prepare(p)['problem_key'],'reviewed':False,
                   'accepted_specific_tag_ids':[],'accepted_provisional_tag_ids':[],
                   'reviewer':'','evidence_kind':'','evidence_note':'','taxonomy_version':'0.3-draft'}
                  for p in problems],dest/f'gold_template_{name}.jsonl')
    manifest={'seed':SEED,'source_count':{x:len(y) for x,y in problem_sets.items()},
      'exploration_count':{'codeforces':len(cf_exp),'atcoder':len(atc_exp)},
      'holdout_count':{'codeforces':len(cf_hold),'atcoder':len(atc_hold)},
      'exploration_keys':[prepare(p)['problem_key'] for p in exploration],
      'holdout_keys':[prepare(p)['problem_key'] for p in holdout],
      'cf_group_counts':cf_stats,'atcoder_contest_groups':atc_stats,
      'warning':'保留测试集不用于修改词表和提示词；初期探索集用于调整方案。'}
    (dest/'selection_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    assert not set(manifest['exploration_keys'])&set(manifest['holdout_keys'])
    print('Selected exploration:',len(exploration),'holdout:',len(holdout),'overlap:0')
    print('CF groups',cf_stats,'AtCoder groups',atc_stats)

if __name__=='__main__':main()
