"""Draft provenance, concurrent edits, and actual server-side retrieval association."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.request
import urllib.error

import photo_ocr
import photo_notebook as notes


class NotebookFixture(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name);self.folder=self.base/('a'*32);self.folder.mkdir()
        self.addCleanup(patch.stopall)
        patch.object(photo_ocr,'BASE',self.base).start()
        (self.folder/'ocr').mkdir()
        raw=json.dumps({'schema':'docvortex.middle','schema_version':'2.0','pages':[{'blocks':[
            {'type':'text','content':'文字中的参数ρ'},
            {'type':'equation','content':'f(x|p)=p(1-p)^x'}]}]}).encode()
        (self.folder/'original.bin').write_bytes(b'original-upload-bytes')
        (self.folder/'ocr/input.json').write_bytes(raw)
        result=photo_ocr.transcript(json.loads(raw));result['raw_ocr_sha256']=hashlib.sha256(raw).hexdigest()
        self.status={'job_id':'a'*32,'status':'ready','image_sha256':hashlib.sha256(b'original-upload-bytes').hexdigest(),'result':result}
        (self.folder/'status.json').write_text(json.dumps(self.status),encoding='utf-8')

    def payload(self,question='文字中的参数p',revision=0,**extra):
        return {'job_id':'a'*32,'source_fingerprint':notes.get('a'*32)['source_fingerprint'],
                'expected_revision':revision,'question':question,'selected_blocks':[0],**extra}

    def binding(self,revision=1):
        return {'job_id':'a'*32,'revision':revision,'source_fingerprint':notes.get('a'*32)['source_fingerprint']}


class NotebookTests(NotebookFixture):
    def test_versions_preserve_original_and_identical_save_is_idempotent(self):
        before=(self.folder/'ocr/input.json').read_bytes()
        data=notes.save(self.payload(note='对照原图把ρ改成p'))
        self.assertEqual(data['revision'],1)
        self.assertEqual(data['drafts'][0]['selected_raw_text'],'文字中的参数ρ')
        self.assertTrue(data['drafts'][0]['changed_from_selected_ocr'])
        self.assertEqual(notes.save(self.payload(revision=1,note='对照原图把ρ改成p'))['revision'],1)
        self.assertEqual(notes.save(self.payload('新核对稿',revision=1))['revision'],2)
        self.assertEqual((self.folder/'ocr/input.json').read_bytes(),before)
        self.assertEqual(notes.get('a'*32)['review_status'],'local_editing_drafts_not_teacher_approved')

    def test_source_mismatch_and_old_version_never_overwrite(self):
        notes.save(self.payload())
        for payload in [self.payload('旧页面内容'),self.payload('错误来源',revision=1,source_fingerprint='bad')]:
            with self.assertRaises(notes.ConflictError):notes.save(payload)
        self.assertEqual(notes.get('a'*32)['drafts'][0]['question'],'文字中的参数p')

    def test_two_concurrent_writers_only_one_can_commit_same_revision(self):
        payloads=[self.payload('编辑A'),self.payload('编辑B')]
        def write(body):
            try:return notes.save(body)['revision']
            except notes.ConflictError:return 'conflict'
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(write,payloads))
        self.assertCountEqual(results,[1,'conflict'])
        self.assertEqual(len(notes.get('a'*32)['drafts']),1)

    def test_changed_ocr_or_upload_rejects_stale_notebook_but_preserves_history(self):
        notes.save(self.payload());saved=(self.folder/'notebook.json').read_bytes()
        (self.folder/'ocr/input.json').write_bytes((self.folder/'ocr/input.json').read_bytes()+b' ')
        with self.assertRaisesRegex(ValueError,'来源已变化'):notes.get('a'*32)
        self.assertEqual((self.folder/'notebook.json').read_bytes(),saved)

    def test_selected_blocks_and_text_bounds_are_validated(self):
        payload=self.payload()
        for change in ({'selected_blocks':[]},{'selected_blocks':[0,0]},{'selected_blocks':[True]},
                       {'selected_blocks':[5]},{'question':''},{'question':'汉'*6000},
                       {'note':'x'*501},{'expected_revision':True}):
            with self.subTest(change=str(change)[:70]),self.assertRaises(ValueError):notes.save({**payload,**change})
        self.assertFalse((self.folder/'notebook.json').exists())

    def test_running_or_missing_source_not_accepted_as_editable_draft(self):
        self.status['status']='failed';(self.folder/'status.json').write_text(json.dumps(self.status),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'识别完成'):notes.get('a'*32)
        with self.assertRaises(ValueError):notes.get('../a')

    def test_search_can_link_older_saved_version_but_not_different_question(self):
        notes.save(self.payload('第1版'))
        binding=self.binding();notes.save(self.payload('第2版',revision=1))
        notes.validate_search(binding,'第1版')
        with self.assertRaises(notes.ConflictError):notes.validate_search(binding,'改过但没保存')
        result={'hits':[{'id':'example','label':'原题候选','pages':[7]}],'route':'real_route','status':'ok','collection_sha256':'current-corpus'}
        receipt=notes.record_search(binding,'第1版',result)
        self.assertTrue(receipt['saved'])
        row=notes.get('a'*32)['searches'][0]
        self.assertEqual(row['draft_revision'],1)
        self.assertEqual(row['collection_sha256'],'current-corpus')
        self.assertEqual(row['hits'][0]['pages'],[7])


class NotebookHTTPTests(NotebookFixture):
    @classmethod
    def setUpClass(cls):
        from app import Handler
        from http.server import ThreadingHTTPServer
        class QuietHandler(Handler):
            def log_message(self,*args):pass
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),QuietHandler)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.url='http://127.0.0.1:'+str(cls.server.server_address[1])

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join()

    def request(self,path,body=None):
        request=urllib.request.Request(self.url+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'})
        return urllib.request.urlopen(request,timeout=5)

    def test_save_conflict_and_actual_server_result_is_logged(self):
        with self.request('/api/photo-notebook',self.payload()) as response:self.assertEqual(json.load(response)['revision'],1)
        with self.assertRaises(urllib.error.HTTPError) as error:self.request('/api/photo-notebook',self.payload('stale'))
        self.assertEqual(error.exception.code,409)
        computed={'hits':[{'id':'real-id','label':'服务器候选','pages':[9]}],'status':'ok','route':'local','collection_sha256':'real-corpus'}
        body={'question':'文字中的参数p','photo_draft':self.binding(),'hits':[{'id':'invented-by-client'}]}
        with patch('full_book_tutor.retrieve',return_value=computed):
            with self.request('/api/problem-study',body) as response:data=json.load(response)
        self.assertTrue(data['photo_notebook']['saved'])
        with self.request('/api/photo-notebook?id='+'a'*32) as response:state=json.load(response)
        self.assertEqual(state['searches'][0]['hits'][0]['id'],'real-id')
        with self.request('/api/photo-notebook?id='+'a'*32+'&download=1') as response:
            self.assertEqual(response.headers['Content-Disposition'],'attachment; filename="photo-notebook.json"')
            self.assertEqual(json.load(response),state)

    def test_unsaved_text_is_rejected_before_retrieval_and_log_failure_keeps_results(self):
        notes.save(self.payload());body={'question':'未保存的新题干','photo_draft':self.binding()}
        with patch('full_book_tutor.retrieve') as retrieve:
            with self.assertRaises(urllib.error.HTTPError) as error:self.request('/api/problem-study',body)
            self.assertEqual(error.exception.code,409);retrieve.assert_not_called()
        body['question']='文字中的参数p'
        with patch('full_book_tutor.retrieve',return_value={'hits':[],'status':'needs_problem_context'}),patch.object(notes,'record_search',side_effect=OSError('private path')):
            with self.request('/api/problem-study',body) as response:data=json.load(response)
        self.assertFalse(data['photo_notebook']['saved'])
        self.assertEqual(data['status'],'needs_problem_context')
        self.assertNotIn('private path',json.dumps(data))


if __name__=='__main__':unittest.main()
