import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from http.server import ThreadingHTTPServer
import threading
from urllib.request import urlopen
import matching_evaluation as evaluation


class MatchingEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.base=self.root/'private';self.base.mkdir()
        for name,value in [('ROOT',self.root),('BASE',self.base)]:
            p=patch.object(evaluation,name,value);p.start();self.addCleanup(p.stop)
        (self.root/'source.py').write_bytes(b'original')
        self.result={'cases':24,'implementation_sha256':{'source.py':hashlib.sha256(b'original').hexdigest()},
                     'review_template':'human-review-template.json','remaining_boundary':'development only'}
        (self.base/'human-review-template.json').write_text(json.dumps({'cases':[{'grade':None}]}),encoding='utf-8')
        self.pin()

    def pin(self):
        raw=json.dumps(self.result).encode();(self.base/'comparison.json').write_bytes(raw)
        (self.base/'latest.json').write_text(json.dumps({'report':'comparison.json','sha256':hashlib.sha256(raw).hexdigest()}),encoding='utf-8')

    def test_pinned_snapshot_and_ungraded_export(self):
        self.assertTrue(evaluation.snapshot()['code_current'])
        self.assertIsNone(evaluation.review_template()['cases'][0]['grade'])

    def test_new_code_is_shown_as_stale_not_fresh_measurement(self):
        (self.root/'source.py').write_bytes(b'changed')
        self.assertFalse(evaluation.snapshot()['code_current'])

    def test_changed_measurement_is_rejected(self):
        (self.base/'comparison.json').write_text('{}',encoding='utf-8')
        with self.assertRaises(ValueError):evaluation.snapshot()

    def test_review_path_cannot_escape_private_experiment(self):
        self.result['review_template']='../secret.json';self.pin()
        with self.assertRaises(ValueError):evaluation.review_template()

    def test_live_http_contract_and_export(self):
        from app import Handler
        class Quiet(Handler):
            def log_message(self,*args):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Quiet)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        address='http://127.0.0.1:'+str(server.server_address[1])
        with urlopen(address+'/api/matching-evaluation') as response:self.assertEqual(json.load(response)['cases'],24)
        with urlopen(address+'/api/matching-evaluation/review') as response:
            self.assertIn('attachment',response.headers['Content-Disposition']);self.assertIsNone(json.load(response)['cases'][0]['grade'])

    def test_workspace_assets_are_served_using_actual_files(self):
        from app import Handler
        class Quiet(Handler):
            def log_message(self,*args):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Quiet)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        address='http://127.0.0.1:'+str(server.server_address[1])
        with urlopen(address+'/workspace-ui.js') as response:
            self.assertIn('javascript',response.headers['Content-Type']);self.assertIn(b'Presentation-only state',response.read())
        with urlopen(address+'/workspace-theme.css') as response:
            self.assertIn('text/css',response.headers['Content-Type']);self.assertIn(b'workspace-sidebar',response.read())


if __name__=='__main__':unittest.main()
