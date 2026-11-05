"""Lecture provenance and unresolved continuation pages must survive previewing."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import lecture_library as library
import lecture_pipeline as pipeline
from sync_sources import fingerprint


class LectureLibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.base=Path(self.temp.name)/'chapter6'
        (self.base/'pages').mkdir(parents=True)
        (self.base/'pages/p1.png').write_bytes(b'original-image-fixture')
        self.image_sha=fingerprint(self.base/'pages/p1.png')
        self.data={'source_sha256':'lecture-source','source_name':'lecture.pdf',
                   'source_total_pages':77,'pages':[{'pdf_page':1,'image':'pages/p1.png','image_sha256':self.image_sha},
                                                  {'pdf_page':40,'image':'pages/p1.png','image_sha256':self.image_sha}]}
        self.links={'lecture_source_sha256':'lecture-source','book_source_sha256':'book-source','collection_sha256':'collection',
                    'items':[{'id':'visual-q','lecture_pdf_page':1,'lecture_image_sha256':self.image_sha,'book_record_id':'book-q',
                              'user_review_status':'pending','answer_correctness_approved':False,'generation_evidence_allowed':False}]}
        self.write('manifest.json',self.data)
        self.write('alignment-candidates.json',self.links)
        self.patches=[patch.object(library,'BASE',Path(self.temp.name)),
                      patch.object(library,'source_for',return_value={'sha256':'lecture-source'}),
                      patch.object(library,'status',return_value={'source_sha256':'book-source','collection_sha256':'collection'}),
                      patch.object(library,'valid_cache',return_value=True)]
        for p in self.patches:p.start()

    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()

    def write(self,name,data):
        (self.base/name).write_text(json.dumps(data),encoding='utf-8')

    def test_lecture_page_is_not_textbook_page(self):
        with patch.object(library,'record',return_value={'id':'book-q','pages':[293]}),patch.object(library,'present',side_effect=lambda v:v):
            result=library.get_page('6',1)
        self.assertEqual(result['lecture_pdf_page'],1)
        self.assertEqual(result['book_records'][0]['pages'],[293])
        self.assertFalse(result['links'][0]['generation_evidence_allowed'])

    def test_continuation_is_not_assigned_to_previous_question(self):
        result=library.get_page('6',40)
        self.assertEqual(result['links'],[])
        self.assertEqual(result['book_records'],[])

    def test_unprepared_page_is_rejected(self):
        with self.assertRaises(ValueError):library.get_page('6',2)

    def test_changed_lecture_source_is_rejected(self):
        with patch.object(library,'source_for',return_value={'sha256':'new-source'}),self.assertRaises(ValueError):
            library.overview()

    def test_changed_book_or_collection_is_rejected(self):
        for field in ['book_source_sha256','collection_sha256','lecture_source_sha256']:
            altered=copy.deepcopy(self.links);altered[field]='changed';self.write('alignment-candidates.json',altered)
            with self.subTest(field=field),self.assertRaises(ValueError):library.alignment()

    def test_changed_image_rejected_for_preview_and_serving(self):
        (self.base/'pages/p1.png').write_bytes(b'replaced')
        for call in [lambda:library.get_page('6',1),lambda:library.image_bytes('6',1)]:
            with self.assertRaises(ValueError):call()

    def test_changed_ocr_source_cannot_enter_preview(self):
        (self.base/'normalized-blocks.jsonl').write_text(json.dumps({'pdf_page':40,'source_sha256':'other'})+'\n',encoding='utf-8')
        with self.assertRaises(ValueError):library.get_page('6',40)

    def test_request_limit_is_checked_before_loading_sources(self):
        with patch.object(library,'alignment') as lookup,self.assertRaises(ValueError):
            library.links_for([str(i) for i in range(21)])
        lookup.assert_not_called()

    def test_invalid_chapter_cannot_resolve_a_path(self):
        for chapter in ['../6','9','0','6/../../']:
            with self.subTest(chapter=chapter),self.assertRaises(ValueError):pipeline.source_for(chapter)


if __name__=='__main__':unittest.main()
