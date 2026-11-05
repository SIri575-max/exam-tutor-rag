"""A review must be explicit, version-bound, append-only and never auto-approved."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import validation_review as review


class ValidationReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name)
        self.batch={'batch_id':'b1','collection_sha256':'c1','source_sha256':'s1',
                    'items':[{'id':'q1','record_text_sha256':'t1'}]}
        review.write(self.folder/'batch.json',self.batch)
        self.patcher=patch.object(review,'status',return_value={'ready':True,'collection_sha256':'c1'})
        self.patcher.start()
        self.body={'batch_id':'b1','collection_sha256':'c1','record_id':'q1',
                   'verdicts':{'stem':'pass','topic':'unsure','practice':'pass'},'notes':''}

    def tearDown(self):
        self.patcher.stop();self.temp.cleanup()

    def test_initial_review_is_pending(self):
        self.assertEqual(review.current(self.folder)['reviewed_count'],0)
        self.assertFalse(review.current(self.folder)['automatic_approval_or_training'])

    def test_partial_or_empty_verdict_cannot_become_approval(self):
        for verdicts in [{},{'stem':'pass'},{'stem':'','topic':'pass','practice':'pass'}]:
            with self.subTest(verdicts=verdicts),self.assertRaises(ValueError):
                review.save({**self.body,'verdicts':verdicts},self.folder)
        self.assertFalse(list((self.folder/'decisions').glob('*.json')))

    def test_modification_requires_specific_notes(self):
        body={**self.body,'verdicts':{'stem':'needs_changes','topic':'unsure','practice':'unsure'}}
        with self.assertRaises(ValueError):review.save(body,self.folder)
        saved=review.save({**body,'notes':'题干缺少参数范围'},self.folder)
        self.assertEqual(saved['review']['notes'],'题干缺少参数范围')

    def test_stale_batch_or_collection_rejected(self):
        for change in [{'batch_id':'old'},{'collection_sha256':'old'},{'record_id':'elsewhere'}]:
            with self.subTest(change=change),self.assertRaises(ValueError):review.save({**self.body,**change},self.folder)
        with patch.object(review,'status',return_value={'ready':True,'collection_sha256':'changed'}),self.assertRaises(ValueError):
            review.save(self.body,self.folder)

    def test_saved_revisions_are_append_only_and_bound_to_source(self):
        first=review.save(self.body,self.folder)['review']
        second=review.save({**self.body,'notes':'再次核对后保留疑问'},self.folder)['review']
        self.assertEqual(len(list((self.folder/'decisions').glob('*.json'))),2)
        current=review.current(self.folder)
        self.assertEqual(current['latest_reviews']['q1']['id'],second['id'])
        self.assertEqual(first['record_text_sha256'],'t1')
        self.assertFalse(second['teacher_approval_claimed'])
        self.assertFalse(second['automatic_approval_or_training'])
        self.assertEqual(json.loads((self.folder/'batch.json').read_text(encoding='utf-8')),self.batch)


if __name__=='__main__':unittest.main()
