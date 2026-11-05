import json
import unittest
from pathlib import Path
from unittest.mock import patch
from learning_engine import retrieve,guidance,dice_calculation
from course_data import load,document_text,PRIVATE
from tutor_provider import answer


class LearningContractTests(unittest.TestCase):
    def test_changed_dice_parameters_are_recalculated(self):
        result=dice_calculation('掷三颗骰子，最大点数恰好等于4')
        self.assertEqual(result['exact'],'37/216')
        self.assertEqual(dice_calculation('掷两颗骰子，最大点数恰好等于4')['exact'],'7/36')
        self.assertIsNone(dice_calculation('掷三颗有偏骰子，最大点数等于4'))
        self.assertIsNone(dice_calculation('掷三颗骰子，最大点数等于4，它们不独立'))

    def test_hints_do_not_expose_numeric_solution(self):
        result=retrieve('掷三颗骰子，最大点数恰好等于4',mode='bm25')
        hint=guidance(result,'hint')
        self.assertNotIn('37/216',hint['text']);self.assertIsNone(hint['calculation'])
        self.assertTrue(all('answer' not in q for q in result['matches']+result['related']))

    def test_outside_scope_and_missing_conditions(self):
        self.assertEqual(retrieve('习题2.1第3题求解','bm25')['status'],'out_of_scope')
        self.assertEqual(retrieve('求这道题概率','bm25')['status'],'clarification_needed')
        r=retrieve('袋中原来一球，不知道黑白，加白球后抽到白球，求原球颜色概率','bm25')
        self.assertEqual(r['route'],'clarify_with_evidence')

    def test_answer_text_never_enters_question_index(self):
        q=dict(load()['exercises'][0],answer={'text':'PRIVATE_ANSWER_SENTINEL'})
        self.assertNotIn('PRIVATE_ANSWER_SENTINEL',document_text(q))

    def test_semantic_round_consumes_prerequisite_evidence(self):
        r=retrieve('如何用贝叶斯公式反推原因，为什么需要全概率？','adaptive')
        self.assertTrue(r['semantic']['used'])
        self.assertEqual(r['route'],'bounded_multi_retrieval')
        second=next(x for x in r['trace'] if x['step']=='second_retrieval')
        self.assertEqual(second['round'],2)
        self.assertTrue(second['added_evidence_ids'])
        self.assertTrue(set(second['added_evidence_ids'])<={c['id'] for c in r['concepts']})

    def test_candidate_boundaries_and_math_fix_are_separate(self):
        report=json.loads((PRIVATE/'chapter1/segmentation-report.json').read_text(encoding='utf-8'))
        self.assertEqual(report['unique_exercise_ids'],122);self.assertFalse(report['searchable'])
        candidates=[json.loads(x) for x in (PRIVATE/'chapter1/exercise-candidates.jsonl').read_text(encoding='utf-8').splitlines()]
        die=next(q for q in candidates if q['id']=='mao3-1.2-12')
        self.assertEqual(die['pages'],[49,50])
        self.assertTrue(all(max(q['pages'])<469 for q in candidates))
        curated={q['id']:q for q in load()['exercises']}
        self.assertIn('(补A)B',curated['mao3-1.1-5']['text'])
        self.assertIn('补(AB)',curated['mao3-1.1-5']['text'])
        self.assertNotIn('frac',curated['mao3-1.1-9']['text'])


class ProviderGroundingTests(unittest.TestCase):
    def setUp(self):
        self.config={'TUTOR_ENABLE_LLM':'1','TUTOR_BASE_URL':'http://127.0.0.1:9999/v1','TUTOR_MODEL':'fixture-model','TUTOR_API_KEY':'fixture-not-a-real-key'}
        self.result={'status':'evidence_found','question':'条件概率如何定义','concepts':load()['concepts'][7:8],
                     'matches':[],'citations':[{'id':'P59'},{'id':'P60'}]}
    def test_unknown_citation_is_discarded(self):
        fake=lambda *args:{'choices':[{'message':{'content':'胡乱引用[P9999]'}}]}
        with patch('tutor_provider.configuration',return_value=self.config):r=answer(self.result,'hint',request=fake)
        self.assertFalse(r['used']);self.assertEqual(r['status'],'citation_validation_failed')
    def test_valid_source_id_contract(self):
        def fake(url,payload,key):
            self.assertNotIn('answer',payload['messages'][1]['content'])
            return {'choices':[{'message':{'content':'先明确条件事件及其正概率要求。[P59]'}}],'usage':{'total_tokens':10}}
        with patch('tutor_provider.configuration',return_value=self.config):r=answer(self.result,'hint',request=fake)
        self.assertTrue(r['used']);self.assertEqual(r['citation_ids'],['P59'])


if __name__=='__main__':unittest.main()
