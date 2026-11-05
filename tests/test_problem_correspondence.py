import unittest
from unittest.mock import patch
import problem_correspondence as mapping
from full_book_tutor import retrieve


def record(identifier,text,kind='exercise'):
    return {'id':identifier,'question_text':text,'kind':kind,'chapter':'6','section':'6.1',
            'label':identifier,'pages':[290],'stem_boundary':'numbered'}


class CorrespondenceTests(unittest.TestCase):
    def test_learning_goals_and_order_statistics_have_source_anchors(self):
        topics=mapping.input_topics('X_1,X_2,X_3~U(0,a)，比较最大值和最小值估计量的无偏性与方差')
        ids={t['subsection'] for t in topics}
        self.assertTrue({'6.1.1','6.1.2','5.3.5','2.5.2'}<=ids)
        self.assertTrue(all(t['pdf_page']>0 and t['basis'] and t['self_check'] for t in topics))

    def test_same_distribution_different_goal_is_explained(self):
        value=mapping.relation('X~U(0,a)，求置信区间',record('q','Y~U(0,b)，求最大似然估计'))
        self.assertEqual(value['level'],'different_goal');self.assertTrue(value['goal_mismatch'])
        self.assertTrue(value['differences']);self.assertFalse(value['equivalence_verified'])

    def test_material_condition_conflict_is_not_claimed_same_method(self):
        value=mapping.relation('X~U(0,a)，求无偏估计',record('q','Y~U(b,2b)，求无偏估计'))
        self.assertEqual(value['level'],'condition_difference');self.assertTrue(value['condition_conflict'])

    def test_empty_formula_candidates_do_not_erase_semantic_candidates(self):
        rows=[record('a','条件概率应用'),record('b','随机事件应用')]
        self.assertEqual([r['id'] for r in mapping.rank('P(A|B)=1',rows,[])],['a','b'])

    def test_formula_rank_cannot_wholly_replace_strong_semantic_result(self):
        a=record('a','X~U(0,a)，求无偏估计');b=record('b','Y~U(b,2b)，求无偏估计')
        out=mapping.rank('Z~U(0,k)，求无偏估计',[a,b],[b,a])
        self.assertEqual(out[0]['id'],'a');self.assertEqual({r['id'] for r in out},{'a','b'})

    def test_distribution_table_is_not_beta_prior_without_prior_words(self):
        p=mapping.formula.profile('常用分布：负二项分布，Beta(a,b)，求特征函数')
        self.assertNotIn('prior_beta',p['operations'])

    def test_practice_prefers_task_matching_example_over_model_only_example(self):
        a=record('a','X~U(0,a)，求最大似然估计','example')
        b=record('b','Y~U(0,b)，求无偏估计','example')
        rows=mapping.practice_order('Z~U(0,k)，求无偏估计',[a,b])
        self.assertEqual(rows[0]['id'],'b')

    def test_navigation_preserves_source_number_and_avoids_student_diagnosis(self):
        a=record('a','X~U(0,a)，求无偏估计');groups={'exercise':[a],'example':[]}
        nav=mapping.navigation('习题6.1第1题',[a],groups,{},True)
        self.assertEqual(a['correspondence']['level'],'source_number')
        self.assertIn('无法判断',nav['self_check_notice']);self.assertTrue(nav['graph']['edges'])

    def test_formula_route_still_supplies_both_types(self):
        a=record('a','X~U(0,a)，求无偏估计');b=record('b','Y~U(0,b)，求无偏估计','example')
        def search(query,mode,kind,*args):return {'hits':[b] if kind=='example' else [a],'filtered_records':2}
        with patch('full_book_tutor.vectors.search',side_effect=search),patch('full_book_tutor.vectors.snapshot',return_value=(None,{'a':a,'b':b})),patch('full_book_tutor.study_context',return_value={}):
            value=retrieve('Z~U(0,k)，求无偏估计')
        self.assertEqual(value['route'],'formula_assisted_fusion')
        self.assertTrue(value['practice_groups']['example']);self.assertTrue(value['practice_groups']['exercise'])
        self.assertFalse(value['llm_used'])


if __name__=='__main__':unittest.main()
