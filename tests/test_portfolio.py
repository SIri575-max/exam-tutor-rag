import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import portfolio
import release_v1


class PortfolioBoundaryTests(unittest.TestCase):
    def test_report_cannot_escape_private_evaluation_directory(self):
        with patch('portfolio.manifest',return_value={'comparison_report':'../../credentials.json'}):
            with self.assertRaisesRegex(ValueError,'无效评测来源'):portfolio.comparison()

    def test_prepared_report_cannot_be_promoted_to_live_release(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);folder=root/'data/private/generation-evaluation/test';folder.mkdir(parents=True)
            path=folder/'comparison.json';path.write_text(json.dumps({'mode':'prepared_only'}),encoding='utf-8')
            with patch.object(release_v1,'ROOT',root),patch('release_v1.index_status') as index:
                with self.assertRaisesRegex(ValueError,'准备稿'):release_v1.build(path)
                index.assert_not_called()

    def test_building_page_never_claims_v1_complete_without_release_artifact(self):
        with tempfile.TemporaryDirectory() as td,patch.object(portfolio,'RELEASE',Path(td)/'not-yet.json'),patch('portfolio.index_status',return_value={'ready':True,'records':1009}),patch('portfolio.model_status',return_value={'enabled':True,'configured':True,'model':'fixture'}),patch('portfolio.generation_records.recent',return_value=[]):
            data=portfolio.snapshot()
        self.assertEqual(data['release']['status'],'building')
        self.assertIsNone(data['release']['evaluation'])
        self.assertNotIn('api_key',json.dumps(data).lower())


if __name__=='__main__':unittest.main()
