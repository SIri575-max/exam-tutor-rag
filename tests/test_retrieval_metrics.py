import unittest
from retrieval_metrics import evaluate


class RetrievalMetricsTests(unittest.TestCase):
    def test_multi_relevant_example(self):
        r=evaluate(['x','a','b'],{'a':3,'b':2,'c':2,'x':0},3,positive_set_complete=True)
        self.assertAlmostEqual(r['precision_at_k'],2/3)
        self.assertAlmostEqual(r['recall_at_k'],2/3)
        self.assertEqual(r['reciprocal_rank_at_k'],.5)

    def test_unknown_is_not_a_negative_or_an_exhaustive_label(self):
        r=evaluate(['unknown','a','z'],{'a':3,'z':0},3)
        self.assertIsNone(r['precision_at_k']);self.assertIsNone(r['recall_at_k'])
        self.assertIsNone(r['reciprocal_rank_at_k']);self.assertEqual(r['hit_at_k'],1)
        self.assertEqual(r['annotated_positive_coverage_at_k'],1)

    def test_empty_and_insufficient_results_use_fixed_k(self):
        r=evaluate(['a'],{'a':3,'b':2},3,positive_set_complete=True)
        self.assertAlmostEqual(r['precision_at_k'],1/3)
        self.assertEqual(r['recall_at_k'],.5)
        self.assertEqual(evaluate([],{'a':3},3,positive_set_complete=True)['reciprocal_rank_at_k'],0)

    def test_null_cannot_be_overridden_by_completeness_flag(self):
        r=evaluate(['unknown','a'],{'unknown':None,'a':3},2,positive_set_complete=True)
        self.assertIsNone(r['reciprocal_rank_at_k']);self.assertIsNone(r['precision_at_k'])
        self.assertIsNone(evaluate(['a'],{'a':3,'unreviewed':None},1,positive_set_complete=True)['recall_at_k'])

    def test_corpus_unlisted_negative_requires_explicit_completeness(self):
        self.assertIsNone(evaluate(['x','a'],{'a':3},2)['reciprocal_rank_at_k'])
        self.assertEqual(evaluate(['x','a'],{'a':3},2,positive_set_complete=True)['reciprocal_rank_at_k'],.5)

    def test_duplicate_children_are_not_multiple_retrieval_results(self):
        with self.assertRaises(ValueError):evaluate(['a','a'],{'a':3},2)


if __name__=='__main__':unittest.main()
