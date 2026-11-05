"""Boundary, provenance, and safe search checks for the full-book archive."""
import copy
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import book_library
from book_structure import structure, location
from normalize_pilot_blocks import convert
from organize_full_book import section_heading, subsection_heading, exercise_heading, numbered_parts, formula_segments
from process_full_book import valid_cache
from sync_sources import fingerprint


class BookArchiveTests(unittest.TestCase):
    def test_every_source_page_has_exactly_one_region(self):
        data = structure()
        for page in range(1, 491):
            self.assertEqual(sum(r['pdf_first'] <= page <= r['pdf_last'] for r in data['regions']), 1)
        self.assertEqual(len(data['sections']), 43)
        self.assertEqual(location(77)[1]['id'], '2')
        self.assertEqual(location(488)[0]['id'], 'references')

    def test_heading_does_not_confuse_subsections_or_decimal_formulas(self):
        self.assertEqual(section_heading('§ 7.6 非参数检验', 'paragraph_title'), '7.6')
        self.assertIsNone(section_heading('7.6.1 游程检验', 'paragraph_title'))
        self.assertEqual(subsection_heading('7.6.1 游程检验', 'paragraph_title'), '7.6.1')
        self.assertIsNone(subsection_heading('定理7.6.1 设……', 'text'))
        self.assertIsNone(section_heading('7.6 是一个常数', 'text'))
        self.assertEqual(exercise_heading('习 题 2.7'), '2.7')
        self.assertIsNone(exercise_heading('见习题2.7第3题'))

    def test_answers_can_change_sections_within_one_source_page(self):
        self.assertEqual(exercise_heading('习题1.5'), '1.5')
        self.assertEqual(exercise_heading('习题2.1'), '2.1')
        self.assertEqual(numbered_parts('1. 略.  2. P=0.5  3. 见证明'),
                         [(1, '1. 略.'), (2, '2. P=0.5'), (3, '3. 见证明')])
        self.assertEqual(numbered_parts('概率0.15与数值2.33'), [])
        self.assertEqual(numbered_parts('18—23. 略.'), [(n, '18—23. 略.') for n in range(18,24)])
        self.assertEqual(numbered_parts('13.4. 14. 2/3'), [(13,'13.4.'),(14,'14. 2/3')])

    def test_single_image_index_is_mapped_to_original_pdf(self):
        raw = {'schema': 'docvortex.middle', 'schema_version': '2.0',
               'pages': [{'page_idx': 0, 'blocks': [{'type': 'text', 'content': [{'type': 'text', 'content': 'sample'}], 'bbox': [.1, .2, .3, .4]}]}]}
        original = copy.deepcopy(raw)
        source = {'source_id': 's', 'source_sha256': 'sha'}
        row = {'pdf_page': 245, 'purpose': 'full_book', 'image': 'pages/pdf-245.png'}
        block = convert(raw, source, row, 'out')[0]
        self.assertEqual(block['page_idx'], 244)
        self.assertEqual(block['raw_block'], original['pages'][0]['blocks'][0])
        self.assertEqual(raw, original)
        self.assertFalse(block['searchable'])

    def test_cache_rejects_changed_image_and_output(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); (base / 'mineru-basic').mkdir()
            path = base / 'mineru-basic/pdf-001.json'
            path.write_text(json.dumps({'schema': 'docvortex.middle', 'schema_version': '2.0', 'pages': [{'page_idx': 0, 'blocks': []}]}))
            row = {'pdf_page': 1, 'image_sha256': 'imageA'}
            cache = {path.name: {'package_pin': '4.0.12', 'input_image_sha256': 'imageA', 'output_sha256': fingerprint(path)}}
            self.assertTrue(valid_cache(base, row, cache))
            self.assertFalse(valid_cache(base, {**row, 'image_sha256': 'imageB'}, cache))
            path.write_text('{}')
            self.assertFalse(valid_cache(base, row, cache))

    def test_formula_scope_preserved(self):
        formula = r'P(\overline{A\cup B})=1-P(A\cup B)'
        result = list(formula_segments({'type': 'text', 'content': [{'type': 'equation_inline', 'content': formula}]}))
        self.assertEqual(result[0][2], formula)

    def test_literal_search_and_answers_hidden_until_explicit_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            with sqlite3.connect(base / 'catalog.sqlite3') as db:
                db.execute('CREATE TABLE pages(pdf_page,region,chapter,status,text)')
                db.executemany('INSERT INTO pages VALUES(?,?,?,?,?)',
                               [(23, 'body', '1', 'complete_unreviewed', '条件概率100%'),
                                (469, 'answers', None, 'complete_unreviewed', '条件概率答案'),
                                (24, 'body', '1', 'complete_unreviewed', "literal ' OR 1=1")])
            db.close()
            with patch.object(book_library, 'BASE', base):
                self.assertEqual(len(book_library.search('条件概率')['hits']), 1)
                self.assertEqual(book_library.search('条件概率', 'answers')['hits'][0]['pdf_page'], 469)
                self.assertEqual(len(book_library.search('%')['hits']), 1)
                self.assertEqual(book_library.search("' OR 1=1")['hits'][0]['pdf_page'], 24)
                with self.assertRaises(ValueError):
                    book_library.get_page(491)


if __name__ == '__main__':
    unittest.main()
