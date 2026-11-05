import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from http.server import ThreadingHTTPServer
import threading
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import external_review as review


class ExternalReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name);self.patch=patch.object(review,'BASE',self.base);self.patch.start();self.addCleanup(self.patch.stop)
        self.addCleanup(review._load.cache_clear)
        self.identifier='660b-c1-q001'
        self.case={'case_id':self.identifier,'query':'若P(A|B)=1，判断命题。','chapter':1,'source_pages':[6],
                   'arms':{name:{'route':'secret-route','hits':[{'id':'r1','label':'题一','question_text':'题干一','pages':[32]},
                                                              {'id':'r2','label':'题二','question_text':'题干二','pages':[33]}]}
                           for name in ['bm25','vector','hybrid','adaptive_rag']}}
        self.report={'cases':[self.case],'frozen_cases':[{'case_id':self.identifier}],
                     'answer_page_text':'sealed-answer-must-not-leak','expected_record':'hidden-gold'}
        self.path=self.base/'retrieval-runs/fixture/report.json';self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps(self.report),encoding='utf-8')
        self.pointer=review.activate(self.path)
        self.body={'case_id':self.identifier,'report_sha256':self.pointer['report_sha256'],'base_revision':0,
                   'status':'draft','grades':{'r1':None,'r2':0},'reviewer':'','family_id':'','ocr_checked':False,
                   'overlap_stratum':'','notes':'先核对公式'}

    def test_blind_case_hides_routes_gold_and_answers(self):
        value=review.get_case(self.identifier);raw=json.dumps(value)
        self.assertNotIn('secret-route',raw);self.assertNotIn('hidden-gold',raw)
        self.assertNotIn('sealed-answer',raw);self.assertNotIn('arms',value)
        self.assertEqual([r['id'] for r in value['candidates']],['r1','r2'])
        self.assertEqual(value['state']['revision'],0)

    def test_draft_does_not_approve_or_change_frozen_report(self):
        digest=hashlib.sha256(self.path.read_bytes()).hexdigest()
        result=review.save(self.body)
        self.assertEqual(result['revision'],1)
        self.assertEqual(review.overview()['approved'],0)
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(),digest)
        exported=review.export();self.assertEqual(exported['cases'][0]['status'],'draft')
        self.assertIsNone(exported['cases'][0]['grades']['r1'])

    def test_explicit_approval_requires_complete_human_fields(self):
        self.body['status']='approved'
        with self.assertRaises(ValueError):review.save(self.body)
        self.body.update(reviewer='单元测试审核人',family_id='f1',ocr_checked=True,
                         overlap_stratum='related_concept_new_problem',grades={'r1':2,'r2':0})
        review.save(self.body)
        self.assertEqual(review.overview()['approved'],1)
        self.assertEqual(review.export()['cases'][0]['split'],'development')

    def test_stale_revision_is_rejected_without_overwrite(self):
        review.save(self.body)
        with self.assertRaises(review.ConflictError):review.save(self.body)
        self.assertEqual(len(review.get_case(self.identifier)['state']['history']),1)

    def test_foreign_snapshot_and_candidate_are_rejected(self):
        for field,value in [('report_sha256','another'),('case_id','../../private')]:
            body={**self.body,field:value}
            with self.assertRaises(ValueError):review.save(body)
        with self.assertRaises(ValueError):review.save({**self.body,'grades':{'foreign':3}})

    def test_boolean_grade_and_ocr_string_cannot_be_imported(self):
        for body in [{**self.body,'grades':{'r1':True}}, {**self.body,'ocr_checked':'true'}]:
            with self.assertRaises(ValueError):review.save(body)

    def test_unresolved_stratum_cannot_be_approved(self):
        self.body.update(status='approved',reviewer='测试',family_id='f',ocr_checked=True,
                         overlap_stratum='unresolved',grades={'r1':3,'r2':0})
        with self.assertRaises(ValueError):review.save(self.body)

    def test_changed_report_is_not_silently_reused(self):
        review.get_case(self.identifier)
        self.path.write_text(json.dumps({**self.report,'changed':True}),encoding='utf-8')
        with self.assertRaises(ValueError):review.get_case(self.identifier)

    def test_source_image_endpoint_never_serves_answers_or_arbitrary_paths(self):
        (self.base/'pages').mkdir();(self.base/'pages/pdf-006.png').write_bytes(b'question-image')
        self.assertEqual(review.image_bytes(6),b'question-image')
        for value in [88,146,0,'6','../secret',True]:
            with self.assertRaises(ValueError):review.image_bytes(value)

    def test_source_hints_do_not_depend_on_ranks_or_assign_labels(self):
        path=self.base/'dataset/math-syntax-audit.json';path.parent.mkdir()
        path.write_text(json.dumps({'failures':[{'case_id':self.identifier}]}),encoding='utf-8')
        self.case['source_pages']=[6,7]
        hints=review.source_checks({self.identifier:self.case})[self.identifier]
        self.assertEqual(hints,['公式语法待核对','跨页条件待核对'])
        overview=review.overview()
        self.assertEqual(overview['cases'][0]['search_text'],self.case['query'])
        self.assertEqual(overview['cases'][0]['source_checks'],['公式语法待核对'])
        self.assertEqual(overview['approved'],0)
        self.assertEqual(review.get_case(self.identifier)['state']['revision'],0)

    def start_server(self):
        from app import Handler
        class QuietHandler(Handler):
            def log_message(self,*args):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),QuietHandler)
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        return 'http://127.0.0.1:'+str(server.server_address[1])

    def test_http_read_contract_and_sealed_answer_boundary(self):
        base=self.start_server()
        with urlopen(base+'/api/external-review/case?id='+self.identifier) as response:
            data=json.load(response)
        self.assertEqual(data['case_id'],self.identifier)
        self.assertNotIn('arms',data)
        with self.assertRaises(HTTPError) as error:urlopen(base+'/api/external-review/image?n=88')
        self.assertEqual(error.exception.code,400)

    def test_http_origin_and_conflict_guard(self):
        base=self.start_server();raw=json.dumps(self.body).encode()
        bad=Request(base+'/api/external-review',data=raw,headers={'Content-Type':'application/json','Origin':'https://unrelated.invalid'})
        with self.assertRaises(HTTPError) as error:urlopen(bad)
        self.assertEqual(error.exception.code,403)
        request=Request(base+'/api/external-review',data=raw,headers={'Content-Type':'application/json','Origin':base})
        with urlopen(request) as response:self.assertTrue(json.load(response)['saved'])
        with self.assertRaises(HTTPError) as error:urlopen(request)
        self.assertEqual(error.exception.code,409)


if __name__=='__main__':unittest.main()
