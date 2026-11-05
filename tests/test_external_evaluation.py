import copy
import unittest
from build_external_evaluation import (QUESTION, extract_questions, query_text, audit,
                                       overlap_candidates, chapter_at)
from external_question_bank import page_blocks
from evaluate_external_answers import answer_matches, make_payload
from evaluate_external_retrieval import payload, summarize


def page(n, texts):
    return {'pdf_page': n, 'source_sha256': 'hash',
            'blocks': [{'type': kind, 'text': text, 'bbox': [0, 0, 1, 1]} for kind, text in texts]}


class ExternalEvaluationTests(unittest.TestCase):
    def test_two_questions_in_single_ocr_block(self):
        rows = extract_questions([page(6, [('text', '7. (2星) 求概率。 8. （3 星）求期望。')])])
        self.assertEqual([r['number'] for r in rows], [7, 8])
        self.assertNotIn('8.', rows[0]['text'])

    def test_cross_page_and_options_preserved(self):
        rows = extract_questions([page(6, [('text', '1.(2 星)条件A。')]),
                                  page(7, [('text', 'B.第二个选项'), ('text', '2.(1星)下题。')])])
        self.assertEqual(rows[0]['pages'], [6, 7])
        self.assertIn('第二个选项', rows[0]['text'])

    def test_answer_pages_never_enter_stems(self):
        rows = extract_questions([page(87, [('text', '30.(2星)回归题')]),
                                  page(88, [('text', '1.秘密答案')])])
        self.assertEqual(len(rows), 1)
        self.assertNotIn('秘密答案', rows[0]['text'])
        self.assertEqual(rows[0]['boundary_status'], 'candidate_complete')

    def test_missing_page_marks_boundary(self):
        rows = extract_questions([page(6, [('text', '1.(2星)开始')]),
                                  page(8, [('text', '2.(2星)新题')])])
        self.assertEqual(rows[0]['boundary_status'], 'missing_page_or_next_boundary')

    def test_chapter_number_reset(self):
        rows = extract_questions([page(15, [('text', '99.(2星)旧章')]),
                                  page(16, [('text', '1.(2星)新章')])])
        self.assertEqual([r['chapter'] for r in rows], [1, 2])
        self.assertNotEqual(rows[0]['id'], rows[1]['id'])

    def test_topic_removed_from_question(self):
        rows = extract_questions([page(6, [('text', '1.(2星)前题'),
                                          ('paragraph_title', '知识点二：条件概率'),
                                          ('text', '2.(2星)后题')])])
        self.assertNotIn('知识点', rows[0]['text'])
        self.assertIn('条件概率', rows[1]['topic_hint'])

    def test_query_omits_school_and_answer_fields(self):
        item = {'text': '7.(2星)求概率[2014 厦大]', 'answer': '秘密'}
        self.assertEqual(query_text(item), '求概率')

    def test_subquestion_not_top_level(self):
        self.assertIsNone(QUESTION.search('(1)先证明；(2)构造区间'))

    def test_ocr_punctuation_variants(self):
        for text in ['55，（2星）题干', '69。(3星）题干', '32.·(5星)题干']:
            self.assertIsNotNone(QUESTION.match(text))

    def test_source_review_override_never_changes_ocr(self):
        import hashlib
        text='25. 没有星级的题干'
        source=page(18,[('text',text),('text','26.(2星)下一题')])
        overrides={(18,0):{'block_text_sha256':hashlib.sha256(text.encode()).hexdigest(),
                           'starts':[{'start':0,'number':25,'stars':None}], 'review':{'by':'assistant'}}}
        result=extract_questions([source],overrides)
        self.assertEqual(result[0]['text'],text)
        self.assertEqual(result[0]['difficulty_stars'],None)
        self.assertEqual(query_text(result[0]),'没有星级的题干')
        overrides[(18,0)]['block_text_sha256']='stale'
        with self.assertRaises(ValueError):extract_questions([source],overrides)

    def test_figures_preserved_for_review_without_invented_text(self):
        source=page(6,[('text','1.(2星)见图'),('image',''),('text','2.(2星)无图')])
        rows=extract_questions([source])
        self.assertTrue(rows[0]['requires_figure_review'])
        self.assertFalse(rows[1]['requires_figure_review'])
        self.assertEqual(rows[0]['visual_assets'][0]['pdf_page'],6)

    def test_difficulty_annotation_keeps_top_level_number(self):
        for text in ['1.（需要额外补充概念，4星）题干', '4.（1星，证明必要性5星）题干']:
            self.assertIsNotNone(QUESTION.match(text))

    def test_no_metrics_without_labels(self):
        result = audit([], [])
        self.assertIsNone(result['mathematical_accuracy'])
        self.assertIsNone(result['retrieval_recall'])

    def test_duplicate_flag_does_not_confirm_split(self):
        item = {'text': '1.(2星)均匀总体未知上界最大似然估计是多少'}
        records = {'r': {'question_text': '均匀总体未知上界最大似然估计是多少', 'label': '某题', 'pages': [1]}}
        overlap_candidates([item], records)
        self.assertEqual(item['overlap_status'], 'possible_near_duplicate_pending_review')
        self.assertIsNone(item['family_id'])
        self.assertEqual(item['relevance_labels'], [])

    def test_schema_and_formula_are_preserved(self):
        parsed = {'schema': 'docvortex.middle', 'schema_version': '2.0', 'pages': [{'blocks': [
            {'type': 'text', 'bbox': [0,0,1,1], 'content': [{'type': 'text', 'content': '密度'},
             {'type': 'equation_inline', 'content': r'\theta x'}]}]}]}
        self.assertIn(r'$\theta x$', page_blocks(parsed)[0]['text'])
        with self.assertRaises(ValueError): page_blocks({})

    def test_generation_payload_excludes_gold_and_provenance(self):
        body = make_payload('题干', [], 'qwen-plus')
        import json
        text = json.dumps(body, ensure_ascii=False)
        for key in ['expected_answer', 'label_derivation', 'source_question', 'teacher_review']:
            self.assertNotIn(key, text)

    def test_objective_score_tolerates_rounding_not_type_coercion(self):
        self.assertTrue(answer_matches(1/3, .333333))
        self.assertFalse(answer_matches(1/3, '1/3'))
        self.assertFalse(answer_matches(1, True))
        self.assertTrue(answer_matches('B', ' b '))

    def test_retrieval_payload_uses_only_stem_and_provenance(self):
        row = {'id':'x','text':'1.(2星)完整题干','text_sha256':'h','pages':[6],
               'chapter':1,'boundary_status':'candidate_complete','review_status':'pending',
               'answer':'sealed','relevance_labels':[{'id':'gold'}]}
        result=payload(row)
        self.assertNotIn('answer',result)
        self.assertNotIn('relevance_labels',result)
        self.assertNotIn('gold',result['query'])

    def test_candidates_do_not_become_recall(self):
        summary=summarize([{'arms':{'bm25':{'status':'completed','hits':[{'id':'r'}],'elapsed_seconds':.1}}}])
        self.assertEqual(summary['bm25']['with_candidates'],1)
        self.assertIsNone(summary['bm25']['recall_at_5'])


if __name__ == '__main__': unittest.main()
