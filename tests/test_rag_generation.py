import unittest
from unittest.mock import patch
from rag_generation import generate, payload, evidence_for

CONFIG={'TUTOR_ENABLE_LLM':'1','TUTOR_BASE_URL':'https://model.example/v1','TUTOR_MODEL':'test-model','TUTOR_API_KEY':'test-key-not-real'}
EVIDENCE=[{'id':'E1','title':'教材段落','text':'条件完整的原文','pages':[302]}]


class RagGenerationTests(unittest.TestCase):
    def setUp(self):
        self.config=patch('rag_generation.configuration',return_value=dict(CONFIG));self.config.start()
        self.state=patch('rag_generation.status',return_value={'enabled':True,'configured':True});self.state.start()

    def tearDown(self):self.config.stop();self.state.stop()

    def test_disabled_provider_does_not_send_evidence(self):
        with patch('rag_generation.status',return_value={'enabled':False,'configured':False}):
            result=generate('题目',EVIDENCE,request=lambda *a:self.fail('network called'))
        self.assertFalse(result['used']);self.assertEqual(result['status'],'not_configured')

    def test_known_citation_accepted_but_test_is_not_live_verification(self):
        result=generate('题目',EVIDENCE,request=lambda *a:{'choices':[{'message':{'content':'依据教材[E1]解释。'}}]})
        self.assertTrue(result['used']);self.assertEqual(result['citation_ids'],['E1']);self.assertFalse(result['live_call_verified'])

    def test_unknown_or_absent_citation_is_rejected(self):
        for text in ['没有引用的答案','虚构来源[E9]']:
            result=generate('题目',EVIDENCE,request=lambda *a:{'choices':[{'message':{'content':text}}]})
            self.assertFalse(result['used']);self.assertEqual(result['status'],'citation_validation_failed')

    def test_no_retrieval_arm_must_be_explicit(self):
        fake=lambda *a:{'choices':[{'message':{'content':'直接回答，说明假设。'}}]}
        self.assertEqual(generate('题目',[],request=fake)['status'],'insufficient_evidence')
        self.assertTrue(generate('题目',[],request=fake,allow_no_evidence=True)['used'])

    def test_non_local_http_or_embedded_credentials_rejected(self):
        for url in ['http://remote.example/v1','https://u:pass@model.example/v1','https://model.example/v1?key=hidden']:
            with patch('rag_generation.configuration',return_value={**CONFIG,'TUTOR_BASE_URL':url}):
                result=generate('题目',EVIDENCE,request=lambda *a:self.fail('network called'))
                self.assertEqual(result['status'],'invalid_provider_url')

    def test_payload_controls_match_across_arms_and_has_no_key(self):
        a=payload('同一道题',[],'solution','fixed-model');b=payload('同一道题',EVIDENCE,'solution','fixed-model')
        for key in ['model','temperature','max_tokens','stream']:self.assertEqual(a[key],b[key])
        self.assertNotIn('test-key',str(b))

    def test_source_units_are_not_truncated_mid_formula(self):
        source='公式开始 '+r'\frac{1}{\theta}'+' 原文尾部'*300
        result=evidence_for({'study':{'readings':[{'title':'定义','text':source,'pages':[1]}]},'hits':[]})
        self.assertEqual(result[0]['text'],source)
        oversized='x'*19000
        self.assertFalse(evidence_for({'study':{'readings':[{'title':'过长','text':oversized,'pages':[1]}]},'hits':[]}))


if __name__=='__main__':unittest.main()
