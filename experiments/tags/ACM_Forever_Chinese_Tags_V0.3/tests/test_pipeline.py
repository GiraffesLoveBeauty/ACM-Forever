import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from label_pipeline import prepare,merge_one,merge_all,evaluate,problem_key,TAG_BY_ID

class TagPipelineTests(unittest.TestCase):
    def cf(self, raw):
        return prepare({'platform':'codeforces','contest_id':2275,'problem_id':'2275G',
                        'tags': {'values': raw}})

    def test_cf_exact_and_temporary_fallback(self):
        p=self.cf(['dsu','data structures','dp'])
        self.assertEqual(p['specific_tag_ids'],['dsu'])
        self.assertEqual(p['provisional_tag_ids'],['pending_data_structures','pending_dp'])
        self.assertEqual(p['problem_key'],'codeforces:2275:G')

    def test_atcoder_does_not_invent_fallback(self):
        p=prepare({'platform':'atcoder','contest_id':'abc478','problem_id':'abc478_c', 'tags': {'values':[]}})
        self.assertEqual(p['specific_tag_ids'],[])
        self.assertEqual(p['provisional_tag_ids'],[])
        self.assertEqual(p['review_status'],'needs_ai')

    def test_special_properties_are_not_algorithm_tags(self):
        p=self.cf(['interactive','*special','binary search'])
        self.assertEqual(p['problem_properties'],['interactive','*special'])
        self.assertEqual(p['specific_tag_ids'],['binary_search'])

    def test_ai_resolve_one_parent_keep_other_parent(self):
        p=self.cf(['dp','data structures'])
        pred={'problem_key':p['problem_key'], 'resolved_cf_hints': {'data structures':['segment_tree']},
              'reason':'题解存在区间加与区间最值维护'}
        result=merge_one(p,pred)
        self.assertEqual(result['provisional_tag_ids'],['pending_dp'])
        self.assertEqual(result['specific_tag_ids'],['segment_tree'])
        self.assertEqual(result['review_status'],'ai_suggested_pending_human_review')

    def test_ai_unresolved_keeps_parent(self):
        p=self.cf(['data structures'])
        result=merge_one(p,{'problem_key':p['problem_key'], 'specific_tag_ids':[], 'reason':'证据不足'})
        self.assertEqual(result['provisional_tag_ids'],['pending_data_structures'])

    def test_atcoder_ai_only_broad_category(self):
        p=prepare({'platform':'atcoder','contest_id':'abc478','problem_id':'abc478_b','tags':[]})
        result=merge_one(p,{'problem_key':p['problem_key'], 'provisional_tag_ids':['pending_dp'],
                            'reason':'状态转移可能涉及DP，但缺乏可验证解法'})
        self.assertEqual(result['specific_tag_ids'],[])
        self.assertEqual(result['provisional_tag_names_zh'],['动态规划·待细化'])

    def test_invalid_ai_specific_tag_rejected(self):
        p=self.cf(['dp'])
        with self.assertRaises(ValueError):
            merge_one(p,{'problem_key':p['problem_key'], 'specific_tag_ids':['invented_algorithm'], 'reason':'猜的'})

    def test_empty_resolution_rejected(self):
        p=self.cf(['dp'])
        with self.assertRaises(ValueError):
            merge_one(p,{'problem_key':p['problem_key'], 'resolved_cf_hints':{'dp':[]},'reason':'unknown'})

    def test_cf_exact_is_immutable_in_merge(self):
        p=self.cf(['greedy','data structures'])
        result=merge_one(p,{'problem_key':p['problem_key'], 'specific_tag_ids':['priority_queue'],
                            'resolved_cf_hints':{'data structures':['priority_queue']},'reason':'题解利用堆'})
        self.assertEqual(result['specific_tag_ids'],['greedy','priority_queue'])
        self.assertFalse(result['provisional_tag_ids'])

    def test_unsupported_prediction_problem_rejected(self):
        p=self.cf(['dp'])
        with self.assertRaises(ValueError):
            merge_all([p],[{'problem_key':'wrong'}])

    def test_evaluation_skips_unreviewed(self):
        p=self.cf(['dsu','dp'])
        gold=[{'problem_key':p['problem_key'],'reviewed':True,'accepted_specific_tag_ids':['dsu']},
              {'problem_key':'other','reviewed':False,'accepted_specific_tag_ids':[]}]
        result=evaluate([p],gold)
        self.assertEqual(result['micro_f1'],1.0)
        self.assertEqual(result['provisional_rate'],1.0)

    def test_stale_content_rejected(self):
        p=self.cf(['dp'])
        p['content_hash']='abc123'
        with self.assertRaises(ValueError):
            merge_one(p,{'problem_key':p['problem_key'],'content_hash':'old', 'reason':'pending'})

    def test_human_confirmation_preserved(self):
        p=self.cf(['dp'])
        p['review_status']='human_confirmed'
        with self.assertRaises(ValueError):
            merge_one(p,{'problem_key':p['problem_key'], 'reason':'pending'})

    def test_tag_kinds_have_distinct_namespaces(self):
        self.assertEqual(sum(x['tag_kind']=='specific' for x in TAG_BY_ID.values()),100)
        self.assertEqual(sum(x['tag_kind']=='provisional' for x in TAG_BY_ID.values()),15)

if __name__=='__main__': unittest.main()
