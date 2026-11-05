import unittest
from unittest.mock import patch
from full_book_tutor import retrieve
from problem_conditions import missing_estimation_context
import source_properties


class ProblemConditionTests(unittest.TestCase):
    def test_generic_estimation_asks_without_retrieving(self):
        for query in ['有一组样本，求参数估计。','根据样本求参数估计','求未知参数的估计']:
            with patch('full_book_tutor.vectors.search') as search:
                result=retrieve(query,chapter='6')
                search.assert_not_called()
                self.assertEqual(result['status'],'needs_problem_context')
                self.assertEqual(len(result['clarifications']),3)

    def test_conceptual_browsing_and_specific_models_remain_available(self):
        for query in ['最大似然估计的不变性如何用于参数函数的估计','想找参数估计的例题',
                      '样本来自U(0,θ)，求θ的最大似然估计','解释矩估计和最大似然估计的区别']:
            self.assertFalse(missing_estimation_context(query))

    def test_property_request_is_narrow(self):
        self.assertTrue(source_properties.requested('MLE的不变性'))
        self.assertFalse(source_properties.requested('最大似然估计'))
        self.assertFalse(source_properties.requested('方差的平移不变性'))

    def test_original_property_paragraph_has_page_and_provenance(self):
        from exercise_vectors import snapshot
        items=source_properties.lookup('最大似然估计的不变性',snapshot()[1])
        self.assertTrue(items)
        item=next(e for e in items if e['record_id']=='example-6.3.5')
        self.assertEqual(item['pages'],[302]);self.assertIn('最大似然估计的不变性',item['text'])
        self.assertEqual(len(item['text_sha256']),64)

    def test_property_lookup_preserves_question_filters(self):
        result=retrieve('最大似然估计的不变性如何用于参数函数的估计',kind='exercise')
        self.assertTrue(all(r['kind']=='exercise' for r in result['hits']))
        self.assertTrue(result['study']['property_evidence'])
        self.assertFalse(any(t['step']=='type_balancing_retrieval' for t in result['trace']))


if __name__=='__main__':unittest.main()
