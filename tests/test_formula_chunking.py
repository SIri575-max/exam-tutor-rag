import unittest
from formula_chunking import intervals, protected_spans
from exercise_vectors import chunks
from retrieval_policy import RetrievalBudget


class FormulaBoundaryTests(unittest.TestCase):
    def check_coverage(self, text, rows, prefix='', budget=480):
        covered=set()
        for a,b,flags in rows:
            self.assertLess(a,b)
            self.assertLessEqual(len(prefix+text[a:b]),budget)
            covered.update(range(a,b))
        self.assertEqual(covered,set(range(len(text))))

    def test_latex_and_numeric_units_are_not_cut_when_they_fit(self):
        text='题干条件。'*50+r'\frac{\sum_{i=1}^{10}X_i}{100.05}'+ '继续求期望。'*65
        rows=list(intervals(text,'',len))
        self.check_coverage(text,rows)
        spans=protected_spans(text)
        for start,end,flags in rows:
            self.assertFalse(any(a<start<b or a<end<b for a,b in spans))
            self.assertFalse(flags)

    def test_long_environment_can_exceed_soft_chars_but_not_tokens(self):
        text=r'\begin{aligned}'+ 'x+'*170+r'y\end{aligned}'
        rows=list(intervals(text,'',len))
        self.assertEqual([(a,b) for a,b,_ in rows],[(0,len(text))])
        self.assertIn('atomic_unit_exceeds_character_target',rows[0][2])
        self.check_coverage(text,rows)

    def test_oversized_formula_keeps_all_content_and_flags_forced_splits(self):
        text=r'\begin{aligned}'+ 'x+'*600+r'y\end{aligned}'
        rows=list(intervals(text,'前缀',len))
        self.check_coverage(text,rows,'前缀')
        self.assertTrue(any('protected_unit_split_for_token_budget' in flags for _,_,flags in rows))

    def test_unclosed_ocr_markup_is_covered_without_infinite_loop(self):
        text='题目'+r'\frac{'+ 'x'*900
        rows=list(intervals(text,'',len))
        self.check_coverage(text,rows)
        self.assertLess(len(rows),10)

    def test_short_question_is_one_piece_and_not_padded(self):
        record={'id':'q','section_title':'假设检验','label':'第1题','search_text':r'检验 H_0:\mu=100 与 H_1:\mu>100。'}
        parts=chunks(record,len)
        self.assertEqual(len(parts),1)
        self.assertTrue(parts[0]['text'].endswith(record['search_text']))

    def test_sentence_in_short_question_does_not_create_tiny_tail(self):
        text='题目条件'*42+'。接着问其概率。'
        rows=list(intervals(text,'',len))
        self.assertEqual(len(rows),1)

    def test_short_tail_merges_without_splitting_a_number(self):
        text='条件'*158+'H_1:mu>100.'
        rows=list(intervals(text,'',len))
        self.assertEqual(len(rows),1)
        self.assertIn('short_tail_merged_exceeds_character_target',rows[0][2])

    def test_overlap_before_long_atomic_unit_does_not_emit_redundant_fragments(self):
        text='较短题干如下：'+r'\begin{aligned}'+ 'x+'*165+r'y\end{aligned}'+'。'
        rows=list(intervals(text,'',len))
        self.check_coverage(text,rows)
        self.assertEqual(len(rows),1)

    def test_explicit_math_delimiters_and_escaped_dollar(self):
        text=r'费用\$5，设 $X\sim N(0,1)$，又有 \[Y={X+1}\]。'
        spans=protected_spans(text)
        self.assertIn((text.index('$X'),text.index('$，')+1),spans)
        self.assertIn((text.index(r'\['),text.index(r'\]')+2),spans)

    def test_budget_configuration_rejects_unbounded_or_ambiguous_values(self):
        for kwargs in [{'recall_k':0},{'recall_k':21},{'recall_k':True},{'practice_k':6}]:
            with self.assertRaises(ValueError):RetrievalBudget(**kwargs)


if __name__=='__main__':unittest.main()
