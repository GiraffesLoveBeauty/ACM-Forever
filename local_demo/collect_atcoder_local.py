"""Collect a bounded number of public ABC tasks into the isolated local forum only.

No AI calls, credentials, background collection or automatic request retries.
"""
import asyncio
import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import re
import sqlite3
import sys
from urllib.parse import urlsplit

import aiohttp
import aiosqlite

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from feat.api.acm_api.problem_content import parse_atcoder
from feat.api.acm_api.problem_bank import save_problem
from feat.api.acm_api.problem_sync import ATCODER_CATALOG_URL, atcoder_catalog_metadata


def hashes(root):
    return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


async def main(count=3, *, translation_ready=False):
    if type(count) is not int or not 1 <= count <= 3:
        raise ValueError('Only one to three new local problems may be collected.')
    database=ROOT/'local_demo/runtime/forum-demo.sqlite3'
    if not database.is_file(): raise ValueError('Existing isolated forum database is required.')
    with closing(sqlite3.connect(database.as_uri()+'?mode=ro',uri=True)) as db:
        before={tuple(row[:2]):hashlib.sha256(repr(tuple(row)).encode()).hexdigest()
                for row in db.execute('SELECT * FROM crawler_problems ORDER BY platform,problem_id')}
    labels_before=hashes(ROOT/'data/labels')
    output=ROOT/'local_demo/runtime'/('crawler-'+str(count)+'-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    output.mkdir(exist_ok=False)
    report={'created_at':datetime.now(timezone.utc).isoformat(),'database':str(database),
        'selection_scope':'Public ABC 100–400, tasks A–F, excluding existing local records',
        'before_count':len(before),'requested_count':count,'translation_ready_required':translation_ready,
        'saved':[], 'skipped':[], 'errors':[], 'ai_calls':0}
    async def download(http,url):
        parsed=urlsplit(url)
        if parsed.scheme!='https' or parsed.hostname not in {'atcoder.jp','kenkoooo.com'} or parsed.username or parsed.password:
            raise ValueError('Unexpected crawler destination')
        async with http.get(url,allow_redirects=False) as response:
            if response.status!=200: raise ValueError(f'Public source returned HTTP {response.status}')
            return await response.read()
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30),trust_env=False,
            headers={'User-Agent':'ACM-Forever-DataCollector/0.1'}) as http:
            raw_catalog=await download(http,ATCODER_CATALOG_URL)
            catalog=atcoder_catalog_metadata(json.loads(raw_catalog))
            candidates=[p for p in catalog if re.fullmatch(r'abc\d{3}_[a-f]',p['problem_id']) and re.fullmatch(r'abc\d{3}',p['contest_id'])
                and 100<=int(p['contest_id'][3:])<=400 and ('atcoder',p['problem_id']) not in before]
            selected=random.SystemRandom().sample(candidates,min(count*5 if translation_ready else count,len(candidates)))
            staged=[]
            for p in selected:
                await asyncio.sleep(1.5)
                source=p['problem_url']+'?lang=en'
                raw=await download(http,source)
                content=parse_atcoder(raw,source,'en')
                if not content['statement_text'].strip() or not content['samples']:
                    raise ValueError(p['problem_id']+': complete statement and samples required')
                content.update(source_url=source,requested_language='en',sha256=hashlib.sha256(raw).hexdigest())
                if translation_ready:
                    sys.path.insert(0,str(ROOT/'experiments/tags/ACM_Forever_Chinese_Tags_V0.3'))
                    from problem_processing.adapter import normalize
                    normalized=normalize({**p,**content,'statement_source_url':source,
                        'statement_sha256':content['sha256'],'last_fetch_status':'ok'})
                    if normalized['processing_status']!='ready':
                        report['skipped'].append({'problem_id':p['problem_id'],
                            'status':normalized['processing_status'],'issues':normalized['processing_issues']})
                        print('Skipped '+p['problem_id']+': input is not translation-ready',flush=True)
                        continue
                (output/(p['problem_id']+'.html')).write_bytes(raw)
                staged.append((p,content))
                print(f"Fetched {p['problem_id']}: {len(content['samples'])} samples, {len(content['statement_text'])} characters",flush=True)
                if len(staged)==count:break
            if len(staged)!=count:raise ValueError('Not enough complete translation-ready tasks; no database writes performed')
            report['selected']=[p for p,_ in staged]
            (output/'selection.json').write_text(json.dumps(report['selected'],ensure_ascii=False,indent=2),encoding='utf-8')
        # Stage/validate every selected problem before any write. Keep an online SQLite backup.
        with closing(sqlite3.connect(database)) as source, closing(sqlite3.connect(output/'forum-before.sqlite3')) as target:
            source.backup(target)
        async with aiosqlite.connect(database,timeout=10) as db:
            db.row_factory=aiosqlite.Row
            await db.execute('PRAGMA busy_timeout=10000')
            await db.execute('PRAGMA foreign_keys=ON')
            for p,content in staged:
                async with db.execute('SELECT 1 FROM crawler_problems WHERE platform=? AND problem_id=?',('atcoder',p['problem_id'])) as cursor:
                    if await cursor.fetchone(): raise ValueError('Problem appeared during collection; refusing to overwrite')
                await save_problem(db,p,content)
                report['saved'].append({'problem_id':p['problem_id'],'title':p['problem_name'],
                    'url':p['problem_url'],'language':content['statement_language'],
                    'sample_count':len(content['samples']),'sha256':content['sha256']})
        with closing(sqlite3.connect(database.as_uri()+'?mode=ro',uri=True)) as db:
            after={tuple(row[:2]):hashlib.sha256(repr(tuple(row)).encode()).hexdigest()
                for row in db.execute('SELECT * FROM crawler_problems ORDER BY platform,problem_id')}
        report.update(after_count=len(after),existing_rows_unchanged=all(after.get(k)==v for k,v in before.items()),
            label_data_unchanged=labels_before==hashes(ROOT/'data/labels'),
            new_count=len(after.keys()-before.keys()),backup_file='forum-before.sqlite3')
        if len(report['saved'])!=count or report['new_count']!=count or not report['existing_rows_unchanged'] or not report['label_data_unchanged']:
            raise ValueError('Post-collection audit failed; inspect the report, do not rerun blindly')
        report['status']='completed'
    except Exception as error:
        report['status']='failed';report['errors'].append(f'{type(error).__name__}: {error}')
        raise
    finally:
        (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print('Report: '+str(output/'report.json'),flush=True)
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--count',type=int,default=3)
    parser.add_argument('--translation-ready',action='store_true')
    args=parser.parse_args()
    asyncio.run(main(args.count,translation_ready=args.translation_ready))
