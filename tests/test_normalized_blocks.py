import unittest
from normalize_pilot_blocks import convert


class SourceIdentityTests(unittest.TestCase):
    def test_image_index_zero_maps_back_to_real_book_page(self):
        data={'schema':'docvortex.middle','schema_version':'2.0','pages':[{'page_idx':0,'blocks':[{'index':1,'type':'text','content':[{'type':'equation_inline','content':r'P(A|B)'}]}]}]}
        source={'source_id':'src','source_sha256':'hash'}
        row={'pdf_page':469,'purpose':'reference_answer','printed_page_verified':'447','image':'pages/pdf-469.png'}
        result=convert(data,source,row,'output-hash')[0]
        self.assertEqual(result['pdf_page'],469)
        self.assertEqual(result['page_idx'],468)
        self.assertEqual(result['channel'],'reference_answer')
        self.assertEqual(result['segments'][0]['content'],r'P(A|B)')
        self.assertFalse(result['searchable'])
        self.assertNotEqual(result['id'],convert(data,source,row,'different-output-hash')[0]['id'])


if __name__=='__main__':unittest.main()
