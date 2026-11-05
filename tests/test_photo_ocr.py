"""Image queries must remain separate from trusted textbook provenance."""
import io
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import urllib.request
import urllib.error
import unittest
from unittest.mock import patch, Mock
from PIL import Image
import photo_ocr as photo


def png(size=(120, 80), fmt='PNG'):
    out = io.BytesIO()
    Image.new('RGB', size, 'white').save(out, format=fmt)
    return out.getvalue()


def middle(blocks):
    return {'schema': 'docvortex.middle', 'schema_version': '2.0',
            'pages': [{'page_idx': 0, 'blocks': blocks}]}


class PhotoOCRTests(unittest.TestCase):
    def test_garbled_math_is_flagged_but_not_silently_corrected(self):
        raw=r'(2)求置信区间 $\frac{ 即 }{ 敦关化 }$'
        result=photo.transcript(middle([{'type':'text','content':raw}]))
        self.assertEqual(result['text'],raw)
        self.assertIn('手写批注',result['blocks'][0]['warnings'][0])
        self.assertFalse(photo.review_warnings(r'$x>0,\text{当参数已知时}$'))
        self.assertTrue(photo.review_warnings('无法识别\ufffd'))
    def test_crop_after_exif_and_clockwise_rotation_keeps_selected_pixels(self):
        im=Image.new('RGB',(120,80),'blue')
        im.paste('red',(0,0,60,80))
        out=io.BytesIO();im.save(out,format='PNG')
        raw,size=photo.normalize_image(out.getvalue(),[0,0,1,.5],90)
        self.assertEqual(size,(180,160))  # 80 by 60 region, plus 50px border.
        with Image.open(io.BytesIO(raw)) as cropped:
            self.assertEqual(cropped.getpixel((70,70)),(255,0,0))
        for crop in ([0,0,2,1],[.5,0,.2,1],[0,0,1],['x',0,1,1],[True,0,1,1],[0,0,float('nan'),1]):
            with self.subTest(crop=crop),self.assertRaises(ValueError):photo.normalize_image(out.getvalue(),crop)
        with self.assertRaises(ValueError):photo.normalize_image(out.getvalue(),[0,0,.1,.1])
        with self.assertRaises(ValueError):photo.normalize_image(out.getvalue(),rotation=True)

    def test_retry_uses_full_original_not_previous_crop_and_retains_parent(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(photo,'BASE',Path(tmp)),patch.object(photo,'_pool'):
            raw=png((200,120));first=photo.submit(raw,[0,0,.5,1]);second=photo.resubmit(first['job_id'],[.5,0,1,1])
            try:
                self.assertEqual(second['parent_job_id'],first['job_id'])
                self.assertEqual(first['image_sha256'],second['image_sha256'])
                self.assertEqual(second['dimensions'],(200,220))
                with Image.open(io.BytesIO(photo.image_bytes(second['job_id'],'full'))) as full:
                    self.assertEqual(full.size,(200,120))
                self.assertEqual((Path(tmp)/second['job_id']/'original.bin').read_bytes(),raw)
            finally:
                for job in (first,second):photo._active.discard(job['job_id']);photo._slots.release()

    def test_legacy_full_preview_is_derived_unpadded_from_original(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(photo,'BASE',Path(tmp)):
            folder=Path(tmp)/('a'*32);folder.mkdir();(folder/'original.bin').write_bytes(png((200,120)))
            with Image.open(io.BytesIO(photo.image_bytes('a'*32,'full'))) as full:self.assertEqual(full.size,(200,120))
            with self.assertRaises(ValueError):photo.image_bytes('a'*32,'../../original.bin')
            with self.assertRaisesRegex(ValueError,'原始题图不存在'):photo.resubmit('b'*32)

    def test_bad_bytes_format_dimensions_and_size_rejected(self):
        for raw in (b'', b'fake png', png(fmt='GIF'), png((20, 80))):
            with self.assertRaises(ValueError):
                photo.normalize_image(raw)
        with patch.object(photo, 'MAX_BYTES', 10):
            with self.assertRaises(ValueError):
                photo.normalize_image(png())
        with patch.object(photo, 'MAX_PIXELS', 100):
            with self.assertRaises(ValueError):
                photo.normalize_image(png())

    def test_orientation_transparency_and_metadata_are_normalized(self):
        im = Image.new('RGBA', (80, 120), (0, 0, 0, 0))
        exif = Image.Exif(); exif[274] = 6
        buf = io.BytesIO(); im.save(buf, format='PNG', exif=exif)
        raw, dimensions = photo.normalize_image(buf.getvalue())
        with Image.open(io.BytesIO(raw)) as result:
            self.assertEqual(dimensions, (220, 180))
            self.assertEqual(result.mode, 'RGB')
            self.assertEqual(result.getpixel((55, 55)), (255, 255, 255))
            self.assertFalse(result.getexif())

    def test_typed_formula_delimiters_preserved_without_source_page_invention(self):
        result = photo.transcript(middle([
            {'type': 'text', 'content': [{'type': 'text', 'content': '设 '},
                {'type': 'equation_inline', 'content': r'X_1\sim U(0,\theta)'}]},
            {'type': 'equation', 'content': r'\frac{4}{3}X_{(3)}'},
            {'type': 'footer', 'content': '不相关页脚'}]))
        self.assertIn(r'$X_1\sim U(0,\theta)$', result['text'])
        self.assertIn(r'$$\frac{4}{3}X_{(3)}$$', result['text'])
        self.assertNotIn('页脚', result['text'])
        self.assertEqual(result['review_status'], 'pending_user_review')
        self.assertNotIn('pdf_page', json.dumps(result))

    def test_empty_unsupported_and_overlong_outputs_require_retry(self):
        for parsed in ({}, middle([]), middle([{'type': 'text', 'content': 'x' * 16001}])):
            with self.assertRaises(ValueError):
                photo.transcript(parsed)

    def test_job_paths_reject_traversal_and_arbitrary_filenames(self):
        for identifier in ('../foo', '/etc/passwd', 'x'*32, 'a'*33, None):
            with self.assertRaises(ValueError):
                photo._folder(identifier)

    def test_queue_limit_does_not_write_upload(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(photo, 'BASE', Path(tmp)), \
                patch.object(photo, '_slots') as slots:
            slots.acquire.return_value = False
            with self.assertRaises(photo.BusyError):
                photo.submit(png())
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_uploaded_bytes_and_raw_output_preserved_ready_still_unreviewed(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(photo, 'BASE', Path(tmp)), \
                patch.object(photo, '_pool') as pool:
            raw = png(); submitted = photo.submit(raw); job_id = submitted['job_id']
            folder = Path(tmp)/job_id
            parsed = middle([{'type': 'equation', 'content': r'E(X)=\theta'}])
            def engine(_):
                (folder/'ocr').mkdir(); (folder/'ocr/input.json').write_text(json.dumps(parsed), encoding='utf-8')
                return parsed
            try:
                with patch.object(photo, '_run_engine', side_effect=engine):
                    photo._work(job_id)
                state = photo.get(job_id)
                self.assertEqual((folder/'original.bin').read_bytes(), raw)
                self.assertEqual(state['status'], 'ready')
                self.assertTrue(state['local_only'])
                self.assertEqual(state['result']['review_status'], 'pending_user_review')
                self.assertTrue((folder/'ocr/input.json').is_file())
                pool.submit.assert_called_once()
            finally:
                photo._active.discard(job_id)

    def test_timeout_releases_slot_and_restart_does_not_leave_infinite_running(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(photo, 'BASE', Path(tmp)), \
                patch.object(photo, '_pool'):
            submitted = photo.submit(png()); job_id = submitted['job_id']
            with patch.object(photo, '_run_engine', side_effect=subprocess.TimeoutExpired('local', 300)):
                photo._work(job_id)
            self.assertEqual(photo.get(job_id)['status'], 'failed')
            self.assertNotIn(job_id, photo._active)
            folder = Path(tmp)/('f'*32); folder.mkdir()
            photo._save(folder, {'job_id': 'f'*32, 'status': 'running'})
            self.assertEqual(photo.get('f'*32)['status'], 'failed')

    def test_command_has_no_remote_engine_and_cached_models_offline(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp); (folder/'ocr').mkdir()
            (folder/'ocr/input.json').write_text('{}', encoding='utf-8')
            with patch.object(photo.subprocess, 'run') as run:
                photo._run_engine(folder)
            command=run.call_args.args[0]; kwargs=run.call_args.kwargs
            self.assertNotIn('--remote', command)
            self.assertNotIn('--remote-url', command)
            self.assertEqual(kwargs['env']['HF_HUB_OFFLINE'], '1')
            self.assertEqual(kwargs['timeout'], 300)


class PhotoHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import Handler
        from http.server import ThreadingHTTPServer
        class QuietHandler(Handler):
            def log_message(self, *args):
                pass
        cls.server=ThreadingHTTPServer(('127.0.0.1', 0), QuietHandler)
        cls.thread=threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url='http://127.0.0.1:'+str(cls.server.server_address[1])

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join()

    def test_bad_mime_cross_origin_oversized_body_and_unknown_job(self):
        cases=[('/api/photo-ocr', b'xx', {'Content-Type':'text/plain'},415),
               ('/api/photo-ocr', b'xx', {'Content-Type':'image/png','Origin':'https://other.example'},403),
               ('/api/photo-ocr', b'xx', {'Content-Type':'image/png','Content-Length':str(photo.MAX_BYTES+1)},413)]
        for path,body,headers,status in cases:
            with self.subTest(status=status):
                with self.assertRaises(urllib.error.HTTPError) as exc:
                    urllib.request.urlopen(urllib.request.Request(self.url+path,data=body,headers=headers),timeout=5)
                self.assertEqual(exc.exception.code,status)
        with self.assertRaises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(self.url+'/api/photo-ocr?id=../../book',timeout=5)
        self.assertEqual(exc.exception.code,404)

    def test_async_upload_response_and_busy_status(self):
        request=urllib.request.Request(self.url+'/api/photo-ocr', data=png(), headers={'Content-Type':'image/png'})
        with patch.object(photo, 'submit', return_value={'job_id':'a'*32,'status':'queued'}):
            with urllib.request.urlopen(request,timeout=5) as response:
                self.assertEqual(response.status,202)
                self.assertEqual(json.load(response)['status'],'queued')
        with patch.object(photo, 'submit', side_effect=photo.BusyError('请等待')):
            with self.assertRaises(urllib.error.HTTPError) as exc:
                urllib.request.urlopen(request,timeout=5)
            self.assertEqual(exc.exception.code,429)

    def test_crop_header_and_retry_options_reach_local_service(self):
        region=[.1,.2,.8,.6]
        request=urllib.request.Request(self.url+'/api/photo-ocr', data=png(), headers={'Content-Type':'image/png','X-Photo-Crop':json.dumps(region),'X-Photo-Rotation':'90'})
        with patch.object(photo,'submit',return_value={'status':'queued'}) as submit:
            with urllib.request.urlopen(request,timeout=5) as response:self.assertEqual(response.status,202)
            self.assertEqual(submit.call_args.args[1:],(region,90))
        request=urllib.request.Request(self.url+'/api/photo-retry',data=json.dumps({'job_id':'a'*32,'crop':region,'rotation':270}).encode(),headers={'Content-Type':'application/json'})
        with patch.object(photo,'resubmit',return_value={'status':'queued'}) as retry:
            with urllib.request.urlopen(request,timeout=5) as response:self.assertEqual(response.status,202)
            retry.assert_called_once_with('a'*32,region,270)


if __name__ == '__main__':
    unittest.main()
