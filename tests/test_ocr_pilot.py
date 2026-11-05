import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import prepare_ocr_pilot as pilot
import prepare_chapter1
from sync_sources import fingerprint


class PilotTests(unittest.TestCase):
    def test_chapter_cache_rejects_different_book_version(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/'data/private/ocr-pilot').mkdir(parents=True)
            (root/'data/private/textbook_registry').mkdir()
            (root/'data/private/ocr-pilot/manifest.json').write_text(json.dumps({'source_sha256':'old-book'}))
            (root/'data/private/textbook_registry/manifest.json').write_text(json.dumps({'files':[{'sha256':'new-book'}]}))
            with patch.object(prepare_chapter1,'ROOT',root):
                with self.assertRaisesRegex(ValueError,'different textbook version'):prepare_chapter1.build()
    def fixture(self, root):
        source=root/'source.pdf';source.write_bytes(b'fixture-original-not-a-real-pdf')
        registry=root/'data/private/textbook_registry';registry.mkdir(parents=True)
        entry={'id':'fixture','path':str(source),'role':'textbook','sha256':fingerprint(source)}
        (registry/'manifest.json').write_text(json.dumps({'files':[entry]}),encoding='utf-8')
        return source

    def test_rerun_preserves_review_and_source(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);source=self.fixture(root)
            def render(command,**kwargs):Path(command[-1]+'.png').write_bytes(b'fixture-image')
            with patch.object(pilot,'ROOT',root),patch.object(pilot,'PAGES',[23]),patch.object(pilot.subprocess,'run',side_effect=render) as renderer:
                pilot.prepare();path=root/'data/private/ocr-pilot/manifest.json'
                data=json.loads(path.read_text());data['pages'][0]['printed_page_verified']='1'
                data['pages'][0]['page_mapping_status']='reviewed';path.write_text(json.dumps(data))
                sheet=root/'data/private/ocr-pilot/page-review.csv';sheet.write_text('retained human notes',encoding='utf-8')
                result=pilot.prepare()
                self.assertEqual(result['pages'][0]['page_mapping_status'],'reviewed')
                self.assertEqual(sheet.read_text(),'retained human notes')
                self.assertEqual(renderer.call_count,1)
                self.assertEqual(source.read_bytes(),b'fixture-original-not-a-real-pdf')

    def test_changed_source_rejected_before_render(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);source=self.fixture(root);source.write_bytes(b'changed')
            with patch.object(pilot,'ROOT',root),patch.object(pilot.subprocess,'run') as renderer:
                with self.assertRaisesRegex(ValueError,'Source changed'):pilot.prepare()
                renderer.assert_not_called()


if __name__=='__main__':unittest.main()
