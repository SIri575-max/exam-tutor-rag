import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from exercise_collection import example_stem, searchable_text
import exercise_vectors as index


class QuestionVectorTests(unittest.TestCase):
    def test_explicit_solution_not_in_stem(self):
        item={'text':'例6.3.1 如何求解此问题？\n设总体满足某条件。\n解：秘密解答123','block_ids':['a']}
        text, boundary=example_stem(item,{'a':{'text':'例6.3.1 如何求解此问题？'}})
        self.assertIn('如何求解',text)
        self.assertNotIn('秘密',text)
        self.assertIn('explicit',boundary)

    def test_unmarked_example_uses_opening_and_warns(self):
        item={'text':'例1.1.1 条件\n后面是没有明确标记的讲解','block_ids':['a']}
        text,boundary=example_stem(item,{'a':{'text':'例1.1.1 条件'}})
        self.assertEqual(text,'例1.1.1 条件')
        self.assertEqual(boundary,'opening_only_boundary_unresolved')

    def test_table_cells_and_math_survive_search_normalization(self):
        self.assertIn(r'\theta',searchable_text(r'<table><tr><td>条件</td><td><eq>\theta</eq></td></tr></table>'))
        self.assertNotIn('<td>',searchable_text('<td>2</td>'))

    def test_long_problem_is_fully_covered_without_truncation(self):
        text='条件甲乙丙丁'*200+'尾部重要条件'
        record={'search_text':text,'section_title':'小节','label':'题号','id':'q'}
        parts=index.chunks(record,len)
        self.assertGreater(len(parts),1)
        covered=set()
        for c in parts:
            covered.update(range(c['start'],c['end']))
            self.assertLessEqual(c['token_count'],index.MAX_TOKENS)
            self.assertTrue(c['text'].endswith(text[c['start']:c['end']]))
        self.assertEqual(covered,set(range(len(text))))
        self.assertIn('尾部重要条件',parts[-1]['text'])

    def test_rrf_votes_are_per_record_not_per_chunk(self):
        rows=[('a1','a','',b''),('a2','a','',b''),('b1','b','',b'')]
        rank=index.fuse([.8,.7,.9],[4.,3.,5.],[0,1,2],rows,limit=3)
        self.assertEqual([x['id'] for x in rank],['b','a'])
        self.assertEqual(rank[0]['rrf'],round(2/61,8))
        self.assertEqual(index.fuse(None,[0.,0.,0.],[0,1,2],rows,'bm25'),[])

    def test_scope_filters_before_ranking_and_solutions_not_returned(self):
        def record(i,kind,ch):
            return {'id':i,'kind':kind,'chapter':ch,'section':ch+'.1','label':i,'pages':[23],
                    'question_text':'问题条件','full_text':'秘密讲解','block_ids':[],'search_text':'问题条件'}
        records={'a':record('a','exercise','1'),'b':record('b','example','2')}
        rows=[('a1','a','问题条件',b''),('b1','b','问题条件',b'')]
        bags=[{'问题':1},{'问题':1}]
        snap=({'collection_sha256':'x'},records,rows,np.zeros((2,512)),bags,[1,1],{'问题':2})
        with patch.object(index,'status',return_value={'ready':True}),patch.object(index,'snapshot',return_value=snap),patch.object(index,'query_lexical',return_value=(1.,1.)):
            result=index.search('问题条件',mode='bm25',kind='example',chapter='2')
        self.assertEqual([x['id'] for x in result['hits']],['b'])
        self.assertNotIn('full_text',result['hits'][0])
        self.assertFalse(result['reference_answers_searched'])

    def test_stale_archive_is_not_silently_searched(self):
        with tempfile.TemporaryDirectory() as directory:
            db=Path(directory)/'index';db.touch()
            with patch.object(index,'DB',db),patch.object(index,'snapshot',return_value=({'input_sha256':{'a':'old'}},)),patch.object(index,'input_signature',return_value={'a':'new'}):
                self.assertFalse(index.status()['ready'])

    def test_invalid_query_or_mode_is_rejected(self):
        for query in (None,'','好'):
            with self.assertRaises(ValueError):index.search(query)
        with self.assertRaises(ValueError):index.search('合法问题',mode='unknown')


if __name__=='__main__':unittest.main()
