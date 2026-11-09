import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


try:
    from study_workflow import StaleTask, handle
except ModuleNotFoundError:
    if importlib.util.find_spec('langgraph') and importlib.util.find_spec('langgraph.checkpoint.sqlite'):
        raise
    raise unittest.SkipTest('Install requirements-agent.txt to test the LangGraph workflow.')


def candidate(identifier, kind='example', *, conflict=False, pages=(18,)):
    return {'id': identifier, 'kind': kind, 'pages': list(pages),
            'correspondence': {'level': 'method_related', 'condition_conflict': conflict}}


def retrieval(*rows):
    return {'route': 'hybrid', 'status': 'candidate_matches', 'hits': list(rows)}


class StudyWorkflowTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = Path(temp.name) / 'workflow.sqlite3'

    def call(self, action, **data):
        # Each call recreates the graph and opens its own SQLite connection.
        return handle({'action': action, **data}, self.db)

    def reply(self, view, **reply):
        return self.call('resume', task_id=view['task_id'], checkpoint=view['clarification']['checkpoint'], reply=reply)

    @patch('study_workflow.full_book_tutor.retrieve', return_value=retrieval(candidate('e'), candidate('x', 'exercise')))
    def test_durable_structured_clarification_and_stale_resume(self, retrieve):
        original = '有一组样本，求参数估计'
        paused = self.call('start', question=original)
        retrieve.assert_not_called()
        restored = self.call('get', task_id=paused['task_id'])
        self.assertEqual(paused['clarification'], restored['clarification'])
        with self.assertRaises(ValueError):
            self.reply(restored, model='不知道', parameter='均值')
        result = self.reply(restored, model='来自正态总体，方差已知', parameter='均值', method='最大似然')
        self.assertEqual(result['decision']['status'], 'candidates_ready')
        self.assertEqual(result['task_id'], paused['task_id'])
        self.assertEqual(result['followups'], 1)
        sent = retrieve.call_args.args[0]
        for text in (original, '方差已知', '待估参数：均值', '最大似然'):
            self.assertIn(text, sent)
        self.assertEqual([x['id'] for x in result['recommendations']], ['e', 'x'])
        with self.assertRaises(StaleTask):
            self.reply(restored, model='均匀总体', parameter='上端点')
        retrieve.assert_called_once()

    @patch('study_workflow.photo_ocr.get', return_value={'status': 'ready', 'result': {'text': '求参数估计'}})
    @patch('study_workflow.full_book_tutor.retrieve', return_value=retrieval(candidate('e')))
    def test_photo_draft_is_not_retrieved_before_correction(self, retrieve, ocr):
        paused = self.call('start', question='客户端文字不覆盖识别稿', photo_job='f' * 32)
        self.assertEqual(paused['question'], '求参数估计')
        self.assertEqual(paused['clarification']['fields'][0]['id'], 'question')
        retrieve.assert_not_called()
        updated = r'设样本来自 $N(\mu,1)$，求均值 $\mu$ 的最大似然估计。'
        self.reply(paused, question=updated)
        retrieve.assert_called_once_with(updated, section='')

    @patch('study_workflow.agent.topic_paths')
    @patch('study_workflow.full_book_tutor.retrieve')
    def test_bounded_graph_retry_requires_sourced_nonconflicting_candidates(self, retrieve, graph):
        graph.return_value = ([{'id': 't', 'subsection': '6.3.1'}],
                              [{'topic_id': 't', 'node': {'kind': 'exercise'}}])
        retrieve.side_effect = [
            retrieval(candidate('bad', conflict=True), candidate('no-source', pages=())),
            retrieval(candidate('good', 'exercise'), candidate('bad2', conflict=True)),
        ]
        result = self.call('start', question='均匀总体的最大似然估计')
        self.assertEqual([call.kwargs['section'] for call in retrieve.call_args_list], ['', '6.3'])
        self.assertEqual(result['decision']['status'], 'candidates_ready')
        self.assertEqual([row['id'] for row in result['recommendations']], ['good'])

    @patch('study_workflow.agent.topic_paths')
    @patch('study_workflow.full_book_tutor.retrieve', return_value=retrieval(candidate('bad', conflict=True)))
    def test_one_pass_control_uses_the_same_gate_without_retry(self, retrieve, graph):
        result = self.call('start', strategy='single', question='均匀总体的最大似然估计')
        self.assertEqual(result['decision']['status'], 'needs_review')
        self.assertFalse(result['recommendations'])
        retrieve.assert_called_once()
        graph.assert_not_called()

    @patch('study_workflow.rag_generation.generate')
    @patch('study_workflow.rag_generation.evidence_for', return_value=[{'id': 'E1', 'title': '依据', 'pages': [18]}])
    @patch('study_workflow.full_book_tutor.retrieve', return_value=retrieval(candidate('e')))
    def test_start_consent_does_not_carry_over_to_resume(self, retrieve, evidence, generate):
        paused = self.call('start', question='有一组样本，求参数估计', intent='explain', allow_generation=True)
        result = self.reply(paused, model='均匀总体', parameter='上端点')
        self.assertEqual(result['decision']['status'], 'evidence_ready')
        generate.assert_not_called()

    def test_resume_exact_check_keeps_event_and_limits_repeated_clarification(self):
        dice = '独立掷3颗公平6面骰子，求最大点数恰好等于5的概率'
        paused = self.call('start', question=dice, intent='check')
        retry = self.reply(paused, answer='1/0')
        self.assertNotEqual(retry['clarification']['checkpoint'], paused['clarification']['checkpoint'])
        with self.assertRaises(StaleTask):
            self.reply(paused, answer='61/216')
        result = self.reply(retry, answer='61/216')
        self.assertTrue(result['calculation']['matches'])
        self.assertEqual(result['calculation']['expected'], '61/216')
        missing = self.call('start', question=dice.replace('独立', ''), answer='61/216')
        self.assertEqual(missing['decision']['status'], 'needs_review')
        self.assertNotIn('calculation', missing)
        paused = self.call('start', question=dice, intent='check')
        end = self.reply(self.reply(paused, answer='1/0'), answer='1/0')
        self.assertEqual(end['decision']['status'], 'needs_context')
        self.assertNotIn('clarification', end)
