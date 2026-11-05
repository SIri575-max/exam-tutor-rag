"""Numbers repeat by section; continuations and OCR windows are only proposals."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lecture_alignment import opening_number, segment_blocks, rank_candidates, choose_proposal
from process_full_book import parse_batch
from sync_sources import fingerprint


def block(page,index,text,kind='text',box=None):
    return {'id':f'p{page}b{index}','pdf_page':page,'block_index':index,'text':text,'type':kind,
            'bbox_normalized':box or [.15,.10,.85,.13]}


class LectureAlignmentTests(unittest.TestCase):
    def test_main_number_is_separate_from_subquestions_and_math(self):
        self.assertEqual(opening_number(block(1,0,'２．设总体服从正态分布，试求均值的估计。')),2)
        for text in ['(1) 证明此统计量无偏','1.23 为样本方差','x_1 = 1. 设总体的参数','每日更新通知']:
            with self.subTest(text=text):self.assertIsNone(opening_number(block(1,0,text)))
        self.assertIsNone(opening_number(block(1,0,'2. 设总体服从正态分布','footer')))

    def test_two_questions_on_one_page_have_distinct_boundaries(self):
        rows=[block(3,0,'3. 设参数的估计量满足无偏性。'),block(3,1,'解答内容'),
              block(3,2,'4. 设总体服从正态分布。'),block(3,3,'另一个解答')]
        segments,unassigned=segment_blocks(rows,[3])
        self.assertEqual([s['printed_number_candidate'] for s in segments],[3,4])
        self.assertEqual(segments[0]['block_ids'],['p3b0','p3b1'])
        self.assertEqual(segments[1]['block_ids'],['p3b2','p3b3'])
        self.assertFalse(unassigned)
        self.assertEqual(segments[0]['shared_question_pages'],[3])

    def test_handwritten_step_near_left_edge_is_not_a_new_question(self):
        self.assertIsNone(opening_number(block(3,2,'3. 如果是无偏估计，则推导产生矛盾',box=[.04,.17,.82,.40])))

    def test_numeric_observations_can_start_a_real_question(self):
        self.assertEqual(opening_number(block(64,0,'3.0.50,1.25,0.80,2.00是取自总体X的样本')),3)

    def test_two_printed_openings_merged_by_ocr_keep_parent_provenance(self):
        rows=[block(37,0,'9. 设总体服从泊松分布，求信息量。 10. 设样本来自伽马分布，求有效估计。')]
        segments,_=segment_blocks(rows,[37])
        self.assertEqual([s['printed_number_candidate'] for s in segments],[9,10])
        self.assertEqual(segments[1]['block_ids'],['p37b0'])
        span=segments[1]['query_source_spans'][0]
        self.assertEqual(rows[0]['text'][span['text_start']:span['text_end']].strip(),segments[1]['query_text'])

    def test_visual_text_span_excludes_merged_handwriting_from_match_query(self):
        text='印刷题干与公式。手写解答不能当作题干'
        anchor={'id':'visual1','lecture_pdf_page':1,'book_record_id':'mao3-6.1-1','stem_candidate_block_ids':['p1b0'],
                'stem_candidate_text_spans':[{'block_id':'p1b0','text_start':0,'text_end':8}]}
        segments,_=segment_blocks([block(1,0,text)],[1],[anchor])
        self.assertEqual(segments[0]['query_text'],text[:8])

    def test_gap_in_ocr_cannot_be_bridged_by_nearest_question(self):
        rows=[block(1,0,'1. 设总体服从正态分布。'),block(3,0,'无题号续写')]
        segments,unassigned=segment_blocks(rows,[1,3])
        self.assertEqual(segments[0]['pages'],[1])
        self.assertEqual(unassigned,['p3b0'])

    def test_adjacent_continuation_is_flagged_and_not_approved(self):
        segments,_=segment_blocks([block(1,0,'1. 设总体服从正态分布。'),block(2,0,'继续推导')],[1,2])
        self.assertEqual(segments[0]['continuation_pages'],[2])
        self.assertEqual(segments[0]['review_status'],'pending')
        self.assertFalse(segments[0]['answer_correctness_approved'])
        self.assertFalse(segments[0]['generation_evidence_allowed'])

    def test_visual_anchor_can_preserve_an_ocr_damaged_question_opening(self):
        anchor={'id':'visual1','lecture_pdf_page':1,'book_record_id':'mao3-6.1-1','stem_candidate_block_ids':['p1b0']}
        segments,_=segment_blocks([block(1,0,'\\sigma^{2} 样本记号被红笔遮挡')],[1],[anchor])
        self.assertEqual(segments[0]['printed_number_candidate'],1)
        self.assertEqual(segments[0]['visual_anchor_id'],'visual1')

    def test_obscured_question_number_image_belongs_to_next_visual_anchor(self):
        anchor={'id':'visual2','lecture_pdf_page':2,'book_record_id':'mao3-6.3-7','stem_candidate_block_ids':['p2b1']}
        rows=[block(1,0,'6. 设总体服从正态分布。'),block(2,0,'',kind='image'),block(2,1,'设总体服从均匀分布。')]
        segments,_=segment_blocks(rows,[1,2],[anchor])
        self.assertEqual(segments[0]['pages'],[1])
        self.assertIn('p2b0',segments[1]['block_ids'])
        self.assertFalse(segments[1]['shared_question_pages'])

    def test_same_number_does_not_prove_same_section(self):
        seg={'query_text':'2. 这是一段与原题没有任何相同条件的无关内容','printed_number_candidate':2}
        books=[{'id':'mao3-6.1-2','label':'6.1-2','pages':[1],'question_text':'设指数分布样本，均值的无偏估计'},
               {'id':'mao3-6.2-2','label':'6.2-2','pages':[2],'question_text':'求正态总体的矩估计'}]
        candidates=rank_candidates(seg,books)
        self.assertEqual(len(candidates),2)
        self.assertIsNone(choose_proposal(seg,candidates))

    def test_near_tie_remains_unresolved(self):
        seg={'query_text':'设总体服从正态分布，试求其参数的最大似然估计。'}
        self.assertIsNone(choose_proposal(seg,[{'score':.8,'number_agrees':True},{'score':.75}]))

    def test_large_handwritten_block_is_not_added_to_query_window(self):
        rows=[block(1,0,'1. 设总体服从正态分布，试求参数。'),
              block(1,1,'长篇手写推导',box=[0,.2,1,.5]),block(1,2,'另一个解答')]
        segments,_=segment_blocks(rows,[1])
        self.assertEqual(segments[0]['query_block_ids'],['p1b0'])
        self.assertIn('p1b1',segments[0]['block_ids'])

    def test_parser_explicit_workspace_does_not_write_textbook_output(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder);(base/'logs').mkdir();(base/'pages').mkdir();(base/'mineru-basic').mkdir()
            image=base/'pages/p1.png';image.write_bytes(b'fixture')
            row={'pdf_page':1,'image':'pages/p1.png','image_sha256':fingerprint(image)}
            with patch('process_full_book.subprocess.run') as run:
                run.return_value.returncode=0;result=parse_batch([row],1,base)
            command=run.call_args.args[0]
            self.assertIn(str(image),command)
            self.assertEqual(command[command.index('-o')+1],str(base/'mineru-basic'))
            self.assertEqual(result['pages'],[1])
            self.assertTrue((base/result['log']).exists())


if __name__=='__main__':unittest.main()
