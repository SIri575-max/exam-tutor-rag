import hashlib
import unittest
from unittest.mock import patch
from exercise_collection import reviewed_stem, example_references
from full_book_tutor import retrieve, explicit_id
from question_knowledge import mentions,canonical_units


class FullBookStudyTests(unittest.TestCase):
    def test_explicit_book_numbers_are_lookup_keys(self):
        self.assertEqual(explicit_id('请解释例 6.3.5'),'example-6.3.5')
        self.assertEqual(explicit_id('习题1.2第12题'),'mao3-1.2-12')
        self.assertIsNone(explicit_id('总体均值为6.3，求估计'))

    def test_ordinary_chat_asks_for_problem_instead_of_searching(self):
        with patch('full_book_tutor.vectors.search') as search:
            r=retrieve('今天晚饭吃什么比较好')
        search.assert_not_called()
        self.assertEqual(r['status'],'needs_problem_context')
        self.assertFalse(r['hits'])

    def test_second_round_retrieval_supplies_missing_example_type(self):
        q={'id':'q','kind':'exercise','stem_boundary':'numbered','question_text':'条件概率'}
        e={'id':'e','kind':'example','stem_boundary':'explicit','question_text':'条件概率'}
        def search(query,mode,kind,*args):return {'hits':[e] if kind=='example' else [q],'filtered_records':2}
        with patch('full_book_tutor.vectors.search',side_effect=search),patch('full_book_tutor.study_context',return_value={}):
            r=retrieve('条件概率的实际应用题')
        self.assertEqual(r['practice_groups']['example'][0]['id'],'e')
        self.assertEqual(r['route'],'bounded_type_balancing')
        self.assertTrue(any('e' in t.get('consumed_ids',[]) for t in r['trace']))

    def test_number_lookup_can_avoid_embedding_and_checks_filters(self):
        item={'id':'example-6.3.5','kind':'example','chapter':'6','section':'6.3',
              'question_text':'均匀总体的最大似然估计','stem_boundary':'source','review_flags':[]}
        with patch('full_book_tutor.vectors.record',return_value=item),patch('full_book_tutor.vectors.search') as search,patch('full_book_tutor.study_context',return_value={}):
            r=retrieve('例6.3.5',adaptive=False)
            search.assert_not_called()
            self.assertEqual(r['route'],'source_number_lookup')
            with self.assertRaises(ValueError):retrieve('例6.3.5',kind='exercise')

    def test_only_literal_topic_mentions_are_claimed(self):
        result=mentions('如何使用全概率公式和贝叶斯公式？')
        ids={x['id'] for x in result}
        self.assertIn('topic:1.4.3',ids)
        self.assertIn('topic:1.4.4',ids)
        self.assertNotIn('topic:6.3.1',ids)
        self.assertTrue(all(x['matched_alias'].lower() in x['quote'].lower() for x in result))

    def test_references_do_not_create_self_edges(self):
        refs=example_references({'id':'example-8.1.2','text':'例8.1.2 采用例8.1.1的数据，继续进行计算。'})
        self.assertEqual([r['id'] for r in refs],['example-8.1.1'])
        self.assertEqual(refs[0]['kind'],'data_or_continuation_reference')

    def test_source_span_and_image_hashes_are_enforced(self):
        text='题目条件。后面为解答';sha=lambda s:hashlib.sha256(s.encode()).hexdigest()
        item={'id':'q','text':text};blocks={'b':{'text':text}}
        manifest={'source_sha256':'source','pages':[{'pdf_page':1,'image_sha256':'image'}]}
        a={'source_sha256':'source','source_unit_text_sha256':sha(text),'page_image_sha256':{'1':'image'},
           'spans':[{'block_id':'b','start':0,'end':5,'text_sha256':sha(text)}]}
        self.assertEqual(reviewed_stem(item,blocks,a,manifest),'题目条件。')
        blocks['b']['text']='changed'
        with self.assertRaises(ValueError):reviewed_stem(item,blocks,a,manifest)

    def test_reference_paragraph_does_not_replace_the_original_theorem(self):
        reference={'id':'theorem-1.1.1','text':'定理1.1.1表明这一性质成立','pages':[24],'block_ids':['b']}
        theorem={'id':'theorem-1.1.1','text':'定理1.1.1 设随机变量满足条件','pages':[23],'block_ids':['a']}
        result=canonical_units([reference,theorem])
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]['text'],theorem['text'])
        self.assertEqual(result[0]['source_commentary'][0]['pages'],[24])


if __name__=='__main__':unittest.main()
