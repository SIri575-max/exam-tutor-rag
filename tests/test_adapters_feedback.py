import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from course_data import PRIVATE,load
import feedback


class ExportAndFeedbackTests(unittest.TestCase):
    def test_export_references_real_chunks_and_known_entities(self):
        kg=json.loads((PRIVATE/'adapters/lightrag-custom-kg.json').read_text(encoding='utf-8'))
        entities={x['entity_name'] for x in kg['entities']};sources={x['source_id'] for x in kg['chunks']}
        self.assertTrue(all(e['source_id'] in sources for e in kg['entities']))
        self.assertTrue(all(r['src_id'] in entities and r['tgt_id'] in entities and r['source_id'] in sources for r in kg['relationships']))
        pairs=[(x['source_id'],x['source_chunk_index']) for x in kg['chunks']]
        self.assertEqual(len(pairs),len(set(pairs)))
    def test_feedback_is_an_issue_not_corpus_approval(self):
        before=(PRIVATE/'course.json').read_bytes()
        with tempfile.TemporaryDirectory() as td,patch.object(feedback,'PRIVATE',Path(td)):
            result=feedback.save({'record_id':'mao3-1.2-12','category':'wrong_formula','message':'自动化测试，验证反馈不会修改题库','automated_test':True})
            row=json.loads((Path(td)/'feedback.jsonl').read_text(encoding='utf-8'))
            self.assertFalse(row['teacher_approval']);self.assertFalse(row['changes_corpus'])
            self.assertEqual(row['origin'],'automated_test')
        self.assertEqual((PRIVATE/'course.json').read_bytes(),before)
