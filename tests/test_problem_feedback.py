import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import json
import problem_feedback as feedback


class FeedbackTests(unittest.TestCase):
    def test_feedback_is_source_versioned_and_stays_pending(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(feedback,'status',return_value={'ready':True,'source_sha256':'src','collection_sha256':'collection'}),patch.object(feedback,'snapshot',return_value=(None,{'q':{'label':'题号','pages':[23]}})):
            r=feedback.save({'record_id':'q','category':'stem_missing','message':'缺少一个条件'},Path(directory))
            item=json.loads((Path(directory)/(r['id']+'.json')).read_text(encoding='utf-8'))
            self.assertEqual(item['collection_sha256'],'collection')
            self.assertEqual(item['status'],'pending_review')
            self.assertFalse(item['automatic_training_or_approval'])

    def test_unknown_record_cannot_choose_an_output_path(self):
        with patch.object(feedback,'status',return_value={'ready':True}),patch.object(feedback,'snapshot',return_value=(None,{})):
            with self.assertRaises(ValueError):feedback.save({'record_id':'../../bad','category':'other','message':'问题说明'})


if __name__=='__main__':unittest.main()
