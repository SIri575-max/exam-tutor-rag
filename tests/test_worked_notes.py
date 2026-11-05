"""Authored explanations must not silently become source OCR or model evidence."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import worked_notes as notes
from worked_note_checks import checks
from sync_sources import fingerprint
from rag_generation import evidence_for


class WorkedNoteTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name)
        self.data={'lecture_source_sha256':'lecture','book_source_sha256':'book','collection_sha256':'collection',
                   'content_code_sha256':fingerprint(Path(notes.__file__).with_name('worked_note_content.py')),
                   'items':[{'record_id':'q1','title':'样板','book_label':'题目','lecture_page':1,
                             'teacher_review_status':'pending','generation_evidence_allowed':False,
                             'book_stem_sha256':notes.text_sha('原题')}]}
        self.patches=[patch.object(notes,'BASE',self.base),patch.object(notes,'source_for',return_value={'sha256':'lecture'}),
                      patch.object(notes,'status',return_value={'ready':True,'source_sha256':'book','collection_sha256':'collection'}),
                      patch.object(notes,'record',return_value={'question_text':'原题'})]
        for p in self.patches:p.start()
        self.save(self.data)

    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()

    def save(self,data):
        path=self.base/'notes.json';path.write_text(json.dumps(data),encoding='utf-8')
        (self.base/'manifest.json').write_text(json.dumps({'notes_sha256':fingerprint(path)}),encoding='utf-8')

    def test_pending_status_is_explicit_in_catalog(self):
        result=notes.catalog(['q1'])
        self.assertFalse(result['teacher_approved']);self.assertFalse(result['generated_live'])
        self.assertEqual(result['items'][0]['teacher_review_status'],'pending')

    def test_unavailable_problem_does_not_receive_some_other_answer(self):
        self.assertFalse(notes.catalog(['q2'])['items'])
        with self.assertRaises(ValueError):notes.get('q2')

    def test_changed_book_or_lecture_version_rejected(self):
        for field in ['lecture_source_sha256','book_source_sha256','collection_sha256','content_code_sha256']:
            changed=copy.deepcopy(self.data);changed[field]='other';self.save(changed)
            with self.subTest(field=field),self.assertRaises(ValueError):notes.load()

    def test_changed_stem_rejected_even_with_same_collection_metadata(self):
        with patch.object(notes,'record',return_value={'question_text':'条件改变后的题干'}),self.assertRaises(ValueError):notes.load()

    def test_modified_note_payload_rejected(self):
        (self.base/'notes.json').write_text('{}',encoding='utf-8')
        with self.assertRaises(ValueError):notes.load()

    def test_editing_state_cannot_silently_promote_notes_to_generation_evidence(self):
        for change in [{'generation_evidence_allowed':True},{'teacher_review_status':'approved'}]:
            data=copy.deepcopy(self.data);data['items'][0].update(change);self.save(data)
            with self.subTest(change=change),self.assertRaises(ValueError):notes.load()

    def test_bulk_limit_is_checked_before_loading_data(self):
        with patch.object(notes,'load') as loader,self.assertRaises(ValueError):notes.catalog([str(i) for i in range(21)])
        loader.assert_not_called()

    def test_model_evidence_builder_ignores_authored_notes(self):
        self.assertEqual(evidence_for({'study':{'worked_notes':self.data['items']},'worked_notes':self.data['items'],'hits':[]}),[])

    def test_missing_note_archive_is_an_empty_optional_feature(self):
        with patch.object(notes,'BASE',self.base/'not-built'):self.assertFalse(notes.catalog()['items'])


class WorkedMathChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.results=checks()

    def test_exact_weights_and_polynomial_moments(self):
        self.assertTrue(self.results['linear_weights']['passed'])
        self.assertTrue(self.results['uniform_order_statistics']['passed'])
        self.assertAlmostEqual(self.results['uniform_order_statistics']['variance_coefficients'][1]/self.results['uniform_order_statistics']['variance_coefficients'][0],9,places=9)

    def test_likelihood_prior_product_matches_normalized_beta(self):
        result=self.results['negative_binomial_beta']
        self.assertTrue(result['passed']);self.assertEqual(result['posterior_shapes'],[8,8])

    def test_interval_simulation_checks_translation_and_sign(self):
        result=self.results['shifted_exponential_interval']
        self.assertTrue(result['passed'])
        self.assertEqual([r['theta'] for r in result['results']],[-2.,0.,4.])


if __name__=='__main__':unittest.main()
