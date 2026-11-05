import unittest
from unittest.mock import patch
from math_query_bridge import expand,profile,merge
from full_book_tutor import retrieve


class MathBridgeTests(unittest.TestCase):
    def test_expansion_uses_explicit_conditions(self):
        result=expand('正态样本的总体均值已知，离差平方和服从什么分布')
        self.assertIsNotNone(result)
        self.assertIn(r'\sum',result['query'])
        self.assertNotIn('卡方',result['query'])
        self.assertIsNone(expand('正态总体均值未知，求离差平方和分布'))

    def test_symbolic_candidate_requires_all_conditions(self):
        actual={'id':'a','question_text':r'正态分布N(\mu,\sigma^{2})，\mu 是已知常数，T=\sum_{i=1}^{n}(x_i-\mu)^{2}'}
        wrong={'id':'b','question_text':'正态总体均值未知，求离差平方和'}
        self.assertTrue(all(profile(actual['question_text']).values()))
        self.assertEqual(merge([wrong],[actual])[0]['id'],'a')

    def test_math_expansion_is_bounded_and_keeps_the_exact_condition_match(self):
        wrong={'id':'b','kind':'exercise','question_text':'正态总体均值未知，求离差平方和','stem_boundary':'source'}
        actual={'id':'a','kind':'example','question_text':r'正态分布，\mu 已知，T=\sum(x_i-\mu)^{2}','stem_boundary':'source'}
        with patch('full_book_tutor.vectors.search',side_effect=[{'hits':[wrong],'filtered_records':2},{'hits':[actual,wrong]}]) as search,patch('full_book_tutor.study_context',return_value={}):
            result=retrieve('正态总体均值已知，求离差平方和的分布')
        self.assertEqual(search.call_count,2)
        self.assertEqual(result['route'],'explicit_math_query_bridge')
        self.assertEqual(result['hits'][0]['id'],'a')


if __name__=='__main__':unittest.main()
