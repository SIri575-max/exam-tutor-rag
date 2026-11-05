import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import generation_records as records
import rag_generation
from release_v1 import generation_summary


class GenerationRecordsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.out=Path(self.temp.name)/'runs'
        self.patcher=patch.object(records,'OUT',self.out);self.patcher.start();self.addCleanup(self.patcher.stop)

    def test_saved_answer_replays_original_evidence_and_keeps_review_pending(self):
        data={'teaching':{'used':True,'status':'generated_pending_review','text':'依据[E1]','usage':{'total_tokens':10}},
              'evidence':[{'id':'E1','text':'原文','pages':[3]}],'retrieval_trace':[{'step':'source'}]}
        identifier=records.save('新题目','hint',data,1.2345)
        loaded=records.get(identifier)
        self.assertEqual(loaded['evidence'],data['evidence'])
        self.assertEqual(loaded['human_review']['status'],'pending')
        self.assertEqual(records.recent()[0]['id'],identifier)
        self.assertEqual(loaded['elapsed_seconds'],1.234)

    def test_invalid_record_path_is_never_read(self):
        for identifier in ['../other','a'*33,None,'A'*32]:
            with self.subTest(identifier=identifier),self.assertRaises(ValueError):records.get(identifier)
        with self.assertRaises(ValueError):records.get('a'*32)

    def test_failed_or_clarification_runs_are_distinct_from_generated_answers(self):
        records.save('缺条件输入','hint',{'teaching':{'used':False,'status':'needs_problem_context','live_call_verified':False},'evidence':[]},0.1)
        self.assertEqual(records.recent()[0]['status'],'needs_problem_context')
        self.assertFalse(records.recent()[0]['live_call_verified'])

    def test_log_write_failure_does_not_lose_actual_answer(self):
        retrieval={'status':'candidate_matches','route':'single_retrieval','clarifications':[],'hits':[]}
        generated={'used':True,'text':'真实输出[E1]','status':'generated_pending_review'}
        with patch('full_book_tutor.retrieve',return_value=retrieval),patch('rag_generation.evidence_for',return_value=[{'id':'E1'}]),patch('rag_generation.generate',return_value=generated),patch.object(records,'save',side_effect=OSError('private location')):
            result=rag_generation.explain('统计学题干')
        self.assertFalse(result['record_saved']);self.assertEqual(result['teaching'],generated)
        self.assertNotIn('private location',json.dumps(result))

    def test_clarification_is_saved_without_model_request(self):
        retrieval={'status':'needs_problem_context','route':'clarify_conditions','clarifications':['总体？'],'message':'补充条件'}
        with patch('full_book_tutor.retrieve',return_value=retrieval),patch('rag_generation.generate') as model:
            result=rag_generation.explain('有一组样本，求参数估计')
        model.assert_not_called();self.assertTrue(result['record_saved'])
        self.assertEqual(records.get(result['run_id'])['route'],'clarify_conditions')

    def test_summary_counts_failed_calls_and_missing_usage_without_fake_accuracy(self):
        failed={'status':'ready','generation':{'used':False,'status':'citation_validation_failed'},'elapsed_seconds':2}
        good={'status':'ready','generation':{'used':True,'usage':{'total_tokens':7}},'elapsed_seconds':1}
        guard={'status':'clarify_before_generation'}
        report={'cases':[{'arms':{'no_retrieval':good,'fixed_rag':failed,'adaptive_rag':good}},
                         {'arms':{k:guard for k in ['no_retrieval','fixed_rag','adaptive_rag']}}]}
        summary=generation_summary(report)
        self.assertEqual(summary['request_attempts'],3);self.assertEqual(summary['total_tokens'],14)
        self.assertEqual(summary['token_usage_missing_requests'],1)
        self.assertEqual(summary['arms']['fixed_rag']['citation_rejected'],1)
        self.assertEqual(summary['clarified_cases'],1);self.assertIsNone(summary['mathematical_accuracy'])


if __name__=='__main__':unittest.main()
