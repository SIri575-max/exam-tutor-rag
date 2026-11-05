import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import configure_model as setup
import tutor_provider

VALUES={'TUTOR_ENABLE_LLM':'1','TUTOR_BASE_URL':'https://model.example/compatible-mode/v1',
        'TUTOR_MODEL':'test-model','TUTOR_API_KEY':'private-fixture-key'}


class ModelSetupTests(unittest.TestCase):
    def test_url_must_be_a_real_base_endpoint(self):
        for url in ['http://remote.example/v1','https://u:secret@model.example/v1',
                    'https://model.example/v1?key=secret','https://{WorkspaceId}.example/v1',
                    'https://model.example/v1/chat/completions']:
            with self.subTest(url=url),self.assertRaises(ValueError):setup.validate({**VALUES,'TUTOR_BASE_URL':url})
        setup.validate({**VALUES,'TUTOR_BASE_URL':'http://localhost:11434/v1'})

    def test_existing_settings_preserved_without_logging_key(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'.env';path.write_text('# keep comment\nOTHER_SETTING=yes\nTUTOR_ENABLE_LLM=0\n',encoding='utf-8')
            stream=io.StringIO()
            with contextlib.redirect_stdout(stream):setup.save(VALUES,path)
            text=path.read_text(encoding='utf-8')
            self.assertIn('OTHER_SETTING=yes',text);self.assertIn('# keep comment',text)
            self.assertEqual(text.count('TUTOR_ENABLE_LLM='),1)
            self.assertNotIn(VALUES['TUTOR_API_KEY'],stream.getvalue())
            self.assertFalse(list((path.parent/'data/private/model-setup').glob('*.env')))

    def test_invalid_configuration_does_not_overwrite_existing(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'.env';path.write_text('ORIGINAL=yes\n',encoding='utf-8')
            with self.assertRaises(ValueError):setup.save({**VALUES,'TUTOR_API_KEY':''},path)
            self.assertEqual(path.read_text(encoding='utf-8'),'ORIGINAL=yes\n')

    def test_status_never_returns_credentials(self):
        text=json.dumps(setup.safe_status(VALUES))
        self.assertNotIn(VALUES['TUTOR_API_KEY'],text)
        self.assertNotIn(VALUES['TUTOR_BASE_URL'],text)
        self.assertTrue(setup.safe_status(VALUES)['key_present'])

    def test_connection_test_sends_no_textbook_and_is_not_fake_live_proof(self):
        captured={}
        def fake(url,body,key):
            captured.update(body)
            return {'choices':[{'message':{'content':'OK'}}],'model':'fixture'}
        result=setup.connection_test(VALUES,request=fake)
        self.assertTrue(result['connected']);self.assertTrue(result['generation_ready'])
        self.assertFalse(result['live_call_verified']);self.assertFalse(result['textbook_sent'])
        self.assertEqual(len(captured['messages']),1)
        self.assertNotIn('evidence',captured['messages'][0]['content'])

    def test_no_final_text_does_not_mean_generation_ready(self):
        result=setup.connection_test(VALUES,request=lambda *a:{'choices':[{'message':{'content':'','reasoning_content':'thinking'}}]})
        self.assertTrue(result['connected']);self.assertFalse(result['generation_ready'])

    def test_disabled_model_cannot_be_tested(self):
        with self.assertRaises(ValueError):setup.connection_test({**VALUES,'TUTOR_ENABLE_LLM':'0'},request=lambda *a:self.fail('network'))

    def test_no_masked_input_fallback_in_noninteractive_session(self):
        with patch('configure_model.sys.stdin.isatty',return_value=False),patch('configure_model.getpass.getpass') as key:
            with self.assertRaises(ValueError):setup.interactive()
            key.assert_not_called()

    def test_direct_model_requests_use_scoped_opener_and_preserve_auth(self):
        from unittest.mock import MagicMock
        response=MagicMock()
        response.__enter__.return_value.read.return_value=b'{"choices":[]}'
        opener=MagicMock();opener.open.return_value=response
        with patch('tutor_provider.configuration',return_value={'TUTOR_TRUST_ENV_PROXY':'0'}),patch('tutor_provider.urllib.request.build_opener',return_value=opener) as build,patch('tutor_provider.urllib.request.urlopen') as default:
            self.assertEqual(tutor_provider.transport('https://model.example/v1/chat/completions',{'model':'fixture'},'fixture-private-key'),{'choices':[]})
        self.assertEqual(build.call_args.args[0].proxies,{})
        request=opener.open.call_args.args[0]
        self.assertEqual(request.get_header('Authorization'),'Bearer fixture-private-key')
        self.assertEqual(request.method,'POST')
        default.assert_not_called()


if __name__=='__main__':unittest.main()
