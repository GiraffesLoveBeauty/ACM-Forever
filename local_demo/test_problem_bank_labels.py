"""Effective-label search, pagination, privacy and live correction contracts; no external requests."""
from copy import deepcopy
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from server import (LABELS, ReadOnlyLabels, DEMO_QQ, DEMO_PASSWORD, create_local_app,
                    initialize_database, isolate_environment)
from problem_bank_labels import parse_options, project_rows, filter_bank
from tag_editor import LocalTagEditor
from test_integration import hashes
from synthetic_fixtures import build_fixture


class BankFilterTests(unittest.TestCase):
    def setUp(self):
        self.raw = [dict(platform='atcoder',problem_id='demo_a',problem_name='Alpha',tags='old',is_favorite=0),
                    dict(platform='atcoder',problem_id='demo_b',problem_name='Beta',tags='raw',is_favorite=1)]
        self.views = [{'platform':'atcoder','problem_id':'demo_a','problem_key':'atcoder:demo:demo_a',
            'effective_tags':[{'id':'difference_array','name_zh':'差分','source':'ai'}],
            'review_status':'auto','fully_human_verified':False,'manual_history_count':0},
            {'platform':'atcoder','problem_id':'demo_b','problem_key':'atcoder:demo:demo_b',
            'effective_tags':[{'id':'difference_array','name_zh':'差分','source':'manual_add'},
                              {'id':'enumeration','name_zh':'枚举','source':'ai'}],
            'review_status':'corrected','fully_human_verified':False,'manual_history_count':1}]

    def result(self, **args):
        return filter_bank(project_rows(self.raw, self.views), parse_options(args))

    def test_search_matches_chinese_effective_label(self):
        self.assertEqual(self.result(tag='差分')['total'],2)

    def test_search_matches_english_label_id(self):
        self.assertEqual(self.result(tag='difference_array')['total'],2)

    def test_all_and_any_tag_combinations(self):
        self.assertEqual(self.result(labels='difference_array,enumeration')['total'],1)
        self.assertEqual(self.result(labels='difference_array,enumeration',match='any')['total'],2)

    def test_filter_before_pagination(self):
        result=self.result(labels='enumeration',page_size='1')
        self.assertEqual(result['total'],1)
        self.assertEqual(result['items'][0]['problem_id'],'demo_b')

    def test_out_of_range_page_preserves_total(self):
        result=self.result(page='3',page_size='1')
        self.assertEqual(result['items'],[]);self.assertEqual(result['total'],2)

    def test_unknown_tag_and_bad_paging_rejected(self):
        for args in [{'labels':'unknown'}, {'page':'x'}, {'page_size':'1000'}, {'platform':'unsafe'}, {'match':'unsafe'}]:
            with self.subTest(args=args),self.assertRaises(ValueError):parse_options(args)

    def test_removed_raw_label_does_not_leak_into_search(self):
        self.assertEqual(self.result(tag='old')['total'],0)

    def test_explicit_empty_effective_set_never_falls_back_to_old_auto(self):
        self.views[0]['effective_tags']=[]
        result=self.result(tag='Alpha')['items'][0]
        self.assertEqual(result['tags'],[])
        self.assertEqual(result['effective_tags'],[])

    def test_metadata_only_records_remain_visible_without_fake_algorithm_tags(self):
        self.views=[]
        result=self.result(tag='raw')
        self.assertEqual(result['total'],1)
        self.assertFalse(result['items'][0]['has_secondary'])
        self.assertEqual(result['items'][0]['effective_tags'],[])

    def test_facets_count_effective_tags(self):
        facets={t['id']:t['count'] for t in self.result()['tag_facets']}
        self.assertEqual(facets['difference_array'],2)
        self.assertEqual(facets['enumeration'],1)

    def test_does_not_mutate_source_records(self):
        original=deepcopy(self.raw);views=deepcopy(self.views)
        self.result(labels='difference_array')
        self.assertEqual(original,self.raw);self.assertEqual(views,self.views)

    def test_platform_and_favorite_filters_combine(self):
        self.assertEqual(self.result(state='favorite',labels='difference_array')['total'],1)
        self.assertEqual(self.result(platform='codeforces')['total'],0)


class BankAPITests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='effective-bank-')
        self.root=Path(self.temp.name)
        build_fixture(self.root/'labels')
        self.labels=ReadOnlyLabels(self.root/'labels',self.root/'manual/overrides.jsonl')
        self.before=hashes(self.labels.root)
        self.env=patch.dict('os.environ');self.env.start()
        self.database=self.root/'forum.sqlite3'
        isolate_environment(self.database)
        await initialize_database(self.database,self.labels)
        self.client=create_local_app(self.labels).test_client()
        self.key='atcoder:abc464:abc464_c'

    async def asyncTearDown(self):
        self.assertEqual(self.before,hashes(self.labels.root))
        self.env.stop();self.temp.cleanup()

    async def login(self):
        response=await self.client.post('/api/auth/login',json={'qq_id':DEMO_QQ,'password':DEMO_PASSWORD})
        self.assertEqual(response.status_code,200)

    async def query(self,args=''):
        response=await self.client.get('/api/me/problems?'+args)
        self.assertEqual(response.status_code,200)
        return await response.get_json()

    async def test_member_can_read_ten_and_facets(self):
        await self.login();data=await self.query()
        self.assertEqual(data['total'],10)
        self.assertEqual(len(data['tag_facets']),115)
        self.assertEqual(data['label_filter_source'],'effective_tags')

    async def test_anonymous_denied(self):
        self.assertEqual((await self.client.get('/api/me/problems')).status_code,401)

    async def test_real_saved_difference_label_is_searchable(self):
        await self.login();data=await self.query('labels=difference_array')
        self.assertTrue(any(p['problem_id']=='abc464_c' for p in data['items']))

    async def test_manual_save_changes_search_immediately(self):
        await self.login()
        editor=LocalTagEditor(self.labels);view=editor.detail(self.key)
        editor.change(self.key,{'operation':'save','tag_ids':['enumeration'],'reason':'离线测试替换',
            'revision':view['revision'],'request_id':uuid4().hex},'test_admin')
        self.assertEqual((await self.query('tag=abc464_c&labels=difference_array'))['total'],0)
        data=await self.query('tag=abc464_c&labels=enumeration')
        self.assertEqual(data['total'],1)
        self.assertEqual(data['items'][0]['effective_tags'][0]['source'],'manual_add')

    async def test_reset_restores_search_results(self):
        await self.login();editor=LocalTagEditor(self.labels)
        for operation,tags in [('save',[]),('reset',[])]:
            editor.change(self.key,{'operation':operation,'tag_ids':tags,'reason':'离线恢复测试',
                'revision':editor.detail(self.key)['revision'],'request_id':uuid4().hex},'test_admin')
        self.assertEqual((await self.query('tag=abc464_c&labels=difference_array'))['total'],1)

    async def test_pagination_counts_after_tag_filter(self):
        await self.login();data=await self.query('labels=difference_array&page_size=1')
        self.assertEqual(data['returned'],1)
        self.assertTrue(all(any(t['id']=='difference_array' for t in p['effective_tags']) for p in data['items']))

    async def test_invalid_filter_is_400(self):
        await self.login()
        self.assertEqual((await self.client.get('/api/me/problems?labels=illegal')).status_code,400)

    async def test_owner_parameters_never_expose_other_favorites_or_solved_rows(self):
        from feat.api.acm_api.database import connect_db
        db=await connect_db(self.database)
        try:
            await db.execute("INSERT INTO user_problem_state(owner_qq_id,platform,problem_id,is_favorite,updated_at) VALUES('99999999','atcoder','abc464_c',1,1)")
            await db.execute("INSERT INTO submissions(user_qq_id,platform,problem_id,submit_time) VALUES('99999999','atcoder','abc464_c',1)")
            await db.commit()
        finally:await db.close()
        await self.login()
        self.assertEqual((await self.query('state=favorite&owner_qq_id=99999999'))['total'],0)
        self.assertEqual((await self.query('scope=solved&qq_id=99999999'))['total'],0)


if __name__=='__main__':unittest.main()
