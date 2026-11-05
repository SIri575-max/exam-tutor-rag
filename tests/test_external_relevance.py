import unittest
from score_external_relevance import score_case, template


class RelevanceTests(unittest.TestCase):
    def setUp(self):
        self.case={'case_id':'q','arms':{'hybrid':{'hits':[{'id':'r1'},{'id':'r2'}]},'vector':{'hits':[{'id':'r2'}]}}}
        self.review={'status':'approved','reviewer':'教师A','ocr_checked':True,'family_id':'f1',
                     'overlap_stratum':'related_concept_new_problem','grades':{'r1':3,'r2':0}}

    def test_pending_is_not_failure_or_success(self):
        self.assertIsNone(score_case(self.case,{})['metrics'])

    def test_valid_explicit_labels(self):
        result=score_case(self.case,self.review)
        self.assertEqual(result['metrics']['hybrid']['pooled_recall_at_5'],1)
        self.assertEqual(result['metrics']['vector']['pooled_ndcg_at_5'],0)

    def test_partial_pool_cannot_be_approved(self):
        self.review['grades']={'r1':3}
        with self.assertRaises(ValueError):score_case(self.case,self.review)

    def test_null_or_boolean_grade_rejected(self):
        for grade in [None,True,4,-1,.5]:
            self.review['grades']['r1']=grade
            with self.assertRaises(ValueError):score_case(self.case,self.review)

    def test_empty_positive_pool_has_no_recall_denominator(self):
        self.review['grades']={'r1':0,'r2':0}
        self.assertIsNone(score_case(self.case,self.review)['metrics']['hybrid']['pooled_recall_at_5'])

    def test_foreign_candidate_does_not_change_metric_denominator(self):
        self.review['grades']['unretrieved-unknown']=3
        with self.assertRaises(ValueError):score_case(self.case,self.review)

    def test_truthy_ocr_string_and_unresolved_stratum_are_not_approval(self):
        self.review['ocr_checked']='yes'
        with self.assertRaises(ValueError):score_case(self.case,self.review)
        self.review['ocr_checked']=True;self.review['overlap_stratum']='unresolved'
        with self.assertRaises(ValueError):score_case(self.case,self.review)

    def test_template_is_unlabeled(self):
        result=template({'cases':[self.case]})
        self.assertEqual(result['cases'][0]['grades'],{'r1':None,'r2':None})


if __name__=='__main__':unittest.main()
