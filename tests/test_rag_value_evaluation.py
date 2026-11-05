import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import evaluate_rag_value as value


class RagValueEvaluationTests(unittest.TestCase):
    def test_source_title_normalization_keeps_examples_and_exercises_distinct(self):
        self.assertEqual(value.canonical('习题6.1 第6题'),'mao3-6.1-6')
        self.assertEqual(value.canonical('例 6.3.5'),'example-6.3.5')
        self.assertIsNone(value.canonical('相关的最大似然题'))

    def test_page_correctness_and_citation_link_are_scored_separately(self):
        case={'expected_record':'mao3-6.1-6'}
        source={'title':'习题6.1第6题','pdf_pages':[294],'evidence_ids':['E1']}
        resolve=lambda identifier:{'id':identifier,'pages':[294]}
        # A valid source ID alone cannot support a claim about a different source.
        evidence=[{'id':'E1','record_id':'other'}]
        score=value.score(case,{'sources':[source]},evidence,resolve)
        self.assertTrue(score['source_location_pass']);self.assertFalse(score['evidence_link_pass'])
        source['pdf_pages']=[999]
        score=value.score(case,{'sources':[source]},[{'id':'E1','record_id':'mao3-6.1-6'}],resolve)
        self.assertFalse(score['source_location_pass']);self.assertEqual(score['unverifiable_or_wrong_source_claims'],1)
        self.assertIsNone(score['mathematical_correctness'])

    def test_empty_source_is_abstention_not_a_wrong_source(self):
        score=value.score({'expected_record':'q'},{'sources':[]},[],lambda _:self.fail('unexpected lookup'))
        self.assertFalse(score['source_location_pass']);self.assertEqual(score['unverifiable_or_wrong_source_claims'],0)
        self.assertTrue(score['no_source_claim'])

    def test_general_math_control_does_not_require_citations(self):
        score=value.score({'expected_numeric_answer':4},{'sources':[],'numeric_answer':4},[])
        self.assertTrue(score['numeric_control_pass']);self.assertIsNone(score['source_location_pass'])
        score=value.score({'expected_numeric_answer':1},{'sources':[],'numeric_answer':True},[])
        self.assertFalse(score['numeric_control_pass'])

    def test_response_parser_does_not_repair_invented_or_invalid_fields(self):
        valid={'answer':'说明','sources':[]}
        self.assertEqual(value.parse_answer('```json\n'+json.dumps(valid)+'\n```'),valid)
        for raw in ['not json',json.dumps({'answer':'说明','sources':[{'title':'习题6.1第6题','pdf_pages':[True],'evidence_ids':[]}]}),json.dumps({'answer':'说明'})]:
            with self.subTest(raw=raw),self.assertRaises(ValueError):value.parse_answer(raw)

    def test_partial_summary_keeps_missing_or_failed_runs_in_denominator(self):
        row={'id':'S1','expected_record':'q','arms':{'fixed_rag':{'attempted':True,'status':'request_or_parse_failed','elapsed_seconds':2}}}
        summary=value.summarize({'cases':[row]})
        self.assertEqual(summary['no_retrieval']['source_tasks'],1)
        self.assertEqual(summary['fixed_rag']['source_location_pass'],0)
        self.assertEqual(summary['fixed_rag']['failed'],1)

    def test_prepared_three_arms_share_prompt_and_never_receive_gold_labels(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);dataset=root/'cases.json';dataset.write_text(json.dumps({'cases':[{'id':'a','question':'统计学新题','expected_record':'private-gold'}]}),encoding='utf-8')
            arms={name:{'status':'ready','evidence':[]} for name in value.ARMS}
            config={'TUTOR_ENABLE_LLM':'1','TUTOR_MODEL':'fixture','TUTOR_API_KEY':'fixture-key','TUTOR_BASE_URL':'https://example.test/v1'}
            with patch.object(value,'ROOT',root),patch('evaluate_rag_value.prepare',return_value=arms),patch('evaluate_rag_value.configuration',return_value=config),patch('evaluate_rag_value.index_status',return_value={'collection_sha256':'sha'}),patch('evaluate_rag_value.transport') as model:
                report,_=value.run(dataset,False)
            model.assert_not_called()
            payloads=[e['request_payload'] for e in report['cases'][0]['arms'].values()]
            self.assertEqual(len(payloads),3);self.assertTrue(all(p==payloads[0] for p in payloads))
            self.assertNotIn('private-gold',json.dumps(payloads))


if __name__=='__main__':unittest.main()
