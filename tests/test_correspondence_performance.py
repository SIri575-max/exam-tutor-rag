import unittest
from unittest.mock import patch
import numpy as np
import exercise_vectors as vectors
import problem_correspondence as mapping
import math_fingerprint


class PerformanceIsolationTests(unittest.TestCase):
    def tearDown(self):
        vectors.query_dense.cache_clear();vectors.query_lexical.cache_clear()

    def test_lexical_cache_is_invalidated_by_index_stamp(self):
        fake=(None,None,None,None,[{}],[0],{})
        with patch.object(vectors,'_snapshot',return_value=fake),patch.object(vectors,'lexical',return_value=[1.]) as calculate:
            self.assertEqual(vectors.query_lexical('query','index',1),(1.,))
            vectors.query_lexical('query','index',1);vectors.query_lexical('query','index',2)
        self.assertEqual(calculate.call_count,2)

    def test_dense_cache_tracks_model_and_index_and_is_readonly(self):
        fake=(None,None,None,np.array([[1.,0.]],dtype=np.float32))
        class Encoder:
            calls=0
            def query_embed(self,parts):self.calls+=1;return [[1.,0.] for _ in parts]
        encoder=Encoder()
        with patch.object(vectors,'_snapshot',return_value=fake),patch.object(vectors,'encoder',return_value=encoder),patch.object(vectors,'tokenizer_counter',return_value=(len,None)):
            first=vectors.query_dense('query','index',1,'model-a')
            vectors.query_dense('query','index',1,'model-a')
            vectors.query_dense('query','index',2,'model-a')
            vectors.query_dense('query','index',2,'model-b')
        self.assertEqual(encoder.calls,3)
        with self.assertRaises(ValueError):first[0][0]=42

    def test_topic_cache_cannot_be_modified_by_response_enrichment(self):
        a=mapping.mentions('无偏估计与置信区间');self.assertTrue(a)
        a[0]['label']='changed'
        self.assertNotEqual(mapping.mentions('无偏估计与置信区间')[0]['label'],'changed')

    def test_typed_keyword_candidate_survives_semantic_candidate_union(self):
        rows=[{'id':'a','question_text':'条件概率的应用'},{'id':'b','question_text':'条件概率的应用'}]
        result=mapping.rank('如何应用条件概率',[rows[0]],lexical_hits=[rows[1]])
        self.assertEqual([r['id'] for r in result],['b','a'])

    def test_math_features_preserve_numbers_and_do_not_certify_equivalence(self):
        a=math_fingerprint.signature(r'P(\frac{(X_1+X_2)^2}{(X_1-X_2)^2+(X_1+X_2)^2}>k)=0.05')[0]
        b=math_fingerprint.signature('P((X1+X2)^2/((X1-X2)^2+(X1+X2)^2)>k)=0.05')[0]
        self.assertEqual(a,b)
        self.assertNotEqual(a,math_fingerprint.signature('P((X1+X2)^2/((X1-X2)^2+(X1+X2)^2)>k)=0.10')[0])
        r={'q':{'id':'q','kind':'exercise','question_text':'X~N(0,1),P((X1+X2)^2/((X1-X2)^2+(X1+X2)^2)>k)=0.05'}}
        hits=math_fingerprint.candidates('X~N(0,1),P((X1+X2)^2/((X1-X2)^2+(X1+X2)^2)>k)=0.05',r)
        self.assertFalse(hits[0]['math_fingerprint_match']['equivalence_verified'])

    def test_math_candidates_keep_kind_and_scope(self):
        text='P((X1+X2)^2/((X1-X2)^2+(X1+X2)^2)>k)=0.05'
        r={i:{'id':i,'kind':k,'chapter':ch,'section':ch+'.1','question_text':text}
           for i,k,ch in [('a','exercise','5'),('b','example','5'),('c','exercise','6')]}
        self.assertEqual([h['id'] for h in math_fingerprint.candidates(text,r,'exercise','5')],['a'])


if __name__=='__main__':unittest.main()
