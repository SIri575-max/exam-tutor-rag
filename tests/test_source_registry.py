import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import sync_sources


class RegistryTests(unittest.TestCase):
    def test_added_unchanged_and_content_change(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);source=root/'sources';source.mkdir()
            file=source/'chapter.pdf';file.write_bytes(b'fixture-original-not-a-real-pdf')
            (source/'notes.docx').write_bytes(b'fixture-unsupported-format')
            config={'primary_source_directory':str(source),'generated_output_directory':'private/registry',
                    'recursive':True,'include_extensions':['.pdf'],'source_role':'lecture_exercise_explanations'}
            (root/'source_config.json').write_text(json.dumps(config),encoding='utf-8')
            with patch.object(sync_sources,'ROOT',root),patch.object(sync_sources,'inspect_pdf',return_value={'pages':2}),contextlib.redirect_stdout(io.StringIO()):
                first=sync_sources.sync();self.assertEqual(first['delta']['added'],['chapter.pdf'])
                self.assertEqual(first['files'][0]['role'],'unclassified_pending_review')
                self.assertEqual(first['unsupported_files_pending_adapter'],['notes.docx'])
                second=sync_sources.sync();self.assertEqual(second['delta']['unchanged'],['chapter.pdf'])
                self.assertEqual(file.read_bytes(),b'fixture-original-not-a-real-pdf')
                self.assertFalse(second['files'][0]['searchable'])
                old_hash=second['files'][0]['sha256'];file.write_bytes(b'changed-fixture')
                third=sync_sources.sync();self.assertEqual(third['delta']['content_changed'],['chapter.pdf'])
                self.assertEqual(third['files'][0]['previous_sha256'],old_hash)
                self.assertTrue(list((root/'private/registry').glob('manifest-history-*.json')))
    def test_textbook_config_keeps_lecture_registry_separate(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);source=root/'books';source.mkdir()
            (source/'book.pdf').write_bytes(b'fixture-book')
            lecture=root/'private/lectures';lecture.mkdir(parents=True)
            (lecture/'manifest.json').write_text('{"existing":"lecture"}',encoding='utf-8')
            config={'primary_source_directory':str(source),'generated_output_directory':'private/books',
                    'recursive':True,'include_extensions':['.pdf'],'source_role':'textbook',
                    'file_roles':{'book.pdf':'textbook'},'file_editions':{'book.pdf':'third'}}
            (root/'textbook_source_config.json').write_text(json.dumps(config),encoding='utf-8')
            with patch.object(sync_sources,'ROOT',root),patch.object(sync_sources,'inspect_pdf',return_value={'pages':490}),contextlib.redirect_stdout(io.StringIO()):
                result=sync_sources.sync('textbook_source_config.json')
            self.assertEqual(result['files'][0]['role'],'textbook')
            self.assertEqual(result['files'][0]['edition'],'third')
            self.assertFalse(result['files'][0]['searchable'])
            self.assertEqual(json.loads((lecture/'manifest.json').read_text())['existing'],'lecture')

    def test_output_cannot_escape_project(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);source=root/'sources';source.mkdir()
            config={'primary_source_directory':str(source),'generated_output_directory':'../escape','recursive':True,'include_extensions':['.pdf'],'source_role':'lecture'}
            (root/'source_config.json').write_text(json.dumps(config),encoding='utf-8')
            with patch.object(sync_sources,'ROOT',root),self.assertRaises(ValueError):sync_sources.sync()


if __name__=='__main__':unittest.main()
