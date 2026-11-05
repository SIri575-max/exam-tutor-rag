import copy
import unittest
from audit_external_rankings import compare


class RankingAuditTests(unittest.TestCase):
    def fixture(self):
        return {'cases':[{'case_id':'660b-c1-q001','query':'冻结题干','chapter':1,'source_pages':[6],
            'arms':{arm:{'hits':[{'id':'a'},{'id':'b'}],'route':'same'}
                    for arm in ['bm25','vector','hybrid','adaptive_rag']}}]}

    def test_reordering_is_not_pool_change_or_error_label(self):
        old=self.fixture();new=copy.deepcopy(old)
        new['cases'][0]['arms']['adaptive_rag']['hits'].reverse()
        value=compare(old,new,set());s=value['summary']['adaptive_rag']
        self.assertEqual((s['top1_changed'],s['order_changed'],s['pool_changed']),(1,1,0))
        self.assertNotIn('accuracy',value);self.assertFalse(value['cases'][0]['development'])
        self.assertEqual(value['summary']['bm25']['order_changed'],0)

    def test_frozen_query_mismatch_is_rejected(self):
        old=self.fixture();new=copy.deepcopy(old);new['cases'][0]['query']='更正后题干'
        with self.assertRaises(ValueError):compare(old,new,set())


if __name__=='__main__':unittest.main()
