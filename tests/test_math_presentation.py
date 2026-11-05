"""Rendering metadata must preserve mathematical scope and original evidence."""
import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from math_presentation import spans, present
from exercise_vectors import record
from book_library import get_page


class MathPresentationTests(unittest.TestCase):
    def test_longest_source_formula_preserves_scope(self):
        text = r'求 \overline{AB} 与 A 的关系'
        found = spans(text, {r'\overline{AB}': False, 'A': False, 'AB': False})
        self.assertEqual(text[found[0]['start']:found[0]['end']], r'\overline{AB}')
        self.assertEqual(len(found), 2)

    def test_ascii_variable_does_not_split_words_or_numbers(self):
        self.assertEqual(spans('PDF 123 normal', {'P': False, '1': False, 'n': False}), [])

    def test_offsets_use_browser_utf16_units(self):
        self.assertEqual(spans('📖题 x_1', {'x_1': False}), [{'start': 4, 'end': 7, 'display': False}])

    def test_record_source_and_retrieval_text_unchanged(self):
        source = record('example-6.3.5'); original = copy.deepcopy(source)
        shown = present(source)
        self.assertEqual(source, original)
        self.assertEqual(shown['full_text'], source['full_text'])
        self.assertTrue(any(s['display'] for s in shown['_math']['full_text']))
        stem = shown['question_text']
        self.assertIn(r'U(0,\theta)', [stem[s['start']:s['end']] for s in shown['_math']['question_text']])

    def test_inherited_page_metadata_for_study_reading(self):
        text = r'样本 x_{1},x_{2},\cdots,x_{n} 来自 U(0,\theta)'
        page = record('example-6.3.5')['pages'][0]
        shown = present({'pages': [page], 'items': [{'text': text}]})
        self.assertGreaterEqual(len(shown['items'][0]['_math']['text']), 2)

    def test_page_math_metadata_keeps_segments(self):
        page = get_page(395); shown = present(page)
        self.assertEqual([b['segments'] for b in shown['blocks']], [b['segments'] for b in page['blocks']])
        self.assertTrue(any(b.get('_math') for b in shown['blocks']))

    def test_long_reading_keeps_final_formula_conditions(self):
        from question_knowledge import current, canonical_units
        from exercise_collection import rows
        from process_full_book import BASE
        units = canonical_units([u for u in rows(BASE / 'learning-units.jsonl') if u['kind'] != 'example'])
        readings = {r['id']: r for group in current()['readings'].values() for r in group}
        long_unit = max((u for u in units if u['id'] in readings), key=lambda u: len(u['text']))
        self.assertGreater(len(long_unit['text']), 650)
        self.assertEqual(readings[long_unit['id']]['text'], long_unit['text'])


if __name__ == '__main__':
    unittest.main()
