import itertools
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from retrieval import corpus,retrieve


class RetrievalTests(unittest.TestCase):
    def test_dice_anchor(self):
        r=retrieve('掷三颗骰子，最大点数恰好等于5的概率')
        self.assertEqual(r['matches'][0]['id'],'ch1-s15-q12')
        self.assertIn('complement',{x['id'] for x in r['concepts']})
    def test_probability_inequality(self):
        r=retrieve('对三个事件A B C证明交集概率不等式')
        self.assertEqual(r['matches'][0]['id'],'ch1-s06-q19')
    def test_grass_anchor(self):
        self.assertEqual(retrieve('六根草头尾随机配对连成一个环的概率')['matches'][0]['id'],'ch1-s07-q16')
    def test_out_of_scope(self):
        r=retrieve('如何证明最大似然估计的一致性？')
        self.assertEqual(r['status'],'insufficient_evidence');self.assertFalse(r['matches'])
    def test_excluded_fragment_not_retrieved(self):
        self.assertNotIn('ch1-s12-fragment',{e['id'] for e in retrieve('事件的概率计算')['matches']})
    def test_baseline_no_expansion(self):
        r=retrieve('掷三颗骰子最大点数恰好等于5','baseline')
        self.assertEqual(r['route'],'single_retrieval');self.assertEqual(r['related'],[])
    def test_iterative_consumes_background(self):
        r=retrieve('掷三颗骰子最大点数恰好等于5的概率')
        self.assertEqual(r['route'],'iterative_graph')
        step=next(x for x in r['trace'] if x['step']=='bounded_second_retrieval')
        self.assertTrue(step['added_background_exercises'])
        self.assertTrue(set(step['added_background_exercises'])<={x['id'] for x in r['related']})
    def test_graph_references_exist(self):
        d=corpus();nodes={x['id'] for x in d['graph']['nodes']}
        for e in d['graph']['edges']:self.assertTrue(e['from'] in nodes and e['to'] in nodes)
    def test_candidate_status_not_verified(self):
        self.assertTrue(all(e['review_status']=='candidate_pending_user_review' for e in corpus()['graph']['edges']))
    def test_source_image_hashes(self):
        import hashlib
        from retrieval import ROOT
        for e in corpus()['exercises']:
            path=ROOT/'data/private/evidence'/e['image']
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),e['image_sha256'])
    def test_dice_correction_enumeration(self):
        outcomes=list(itertools.product(range(1,7),repeat=3))
        self.assertEqual(len(outcomes),216)
        self.assertEqual(sum(max(x)==5 for x in outcomes),61)
        self.assertEqual(sum(max(x)<=5 for x in outcomes),125)
        self.assertNotEqual(61/216,25/72)
    def test_parameters_do_not_trigger_stored_answer(self):
        r=retrieve('掷四颗骰子，最大点数等于5的概率')
        self.assertEqual(r['generation_status'],'not_connected')
        self.assertNotIn('answer',r)


if __name__=='__main__':unittest.main()
