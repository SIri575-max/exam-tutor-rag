import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import numpy as np

import reasoning_agent as agent
import study_memory
import study_tools


def call(name, args):
    return {'choices': [{'message': {'role': 'assistant', 'content': None, 'tool_calls': [
        {'id': 'call-one', 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(args)}}]}}]}


def answer(text):
    return {'choices': [{'message': {'role': 'assistant', 'content': text}}]}


class ReasoningAgentTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.db = Path(temporary.name) / 'tasks.sqlite3'
        self.memory = Path(temporary.name) / 'memory.sqlite3'
        self.learner = 'a' * 32
        patcher = patch('study_memory.embedding', return_value=np.asarray([1., 0.], dtype=np.float32))
        patcher.start()
        self.addCleanup(patcher.stop)

    def invoke(self, request, **body):
        return agent.handle({'action': 'start', 'learner_id': self.learner, 'question': '复习最大似然估计',
                             'allow_generation': True, **body}, self.db, request, self.memory)

    def scripted(self, *responses):
        iterator = iter(responses)
        self.payloads = []

        def request(url, payload, key):
            self.payloads.append(payload)
            return next(iterator)
        return request

    def test_same_task_resume_requires_fresh_checkpoint_consent_and_owner(self):
        request = self.scripted(call('ask_clarification', {'kind': 'estimation', 'prompt': '请补充总体与参数'}),
                                call('check_answer', {}), answer('数值核对完成。'))
        paused = self.invoke(request, question='求参数估计')
        get_body = {'action': 'get', 'task_id': paused['task_id'], 'learner_id': self.learner}
        self.assertEqual(agent.handle(get_body, self.db)['clarification'], paused['clarification'])
        with self.assertRaises(agent.StaleTask):
            agent.handle({**get_body, 'learner_id': 'b' * 32}, self.db)
        resume_body = {**get_body, 'action': 'resume', 'checkpoint': paused['clarification']['checkpoint'],
                       'reply': {'model': '正态总体', 'parameter': '均值'}}
        with self.assertRaises(ValueError):
            agent.handle(resume_body, self.db, request, self.memory)
        resumed = agent.handle({**resume_body, 'allow_generation': True}, self.db, request, self.memory)
        self.assertEqual(resumed['task_id'], paused['task_id'])
        self.assertEqual(resumed['followups'], 1)
        self.assertIn('正态总体', resumed['question'])
        with self.assertRaises(agent.StaleTask):
            agent.handle({**resume_body, 'allow_generation': True}, self.db, request, self.memory)

    def test_native_tool_result_is_sent_back_and_check_uses_original_question(self):
        question = '独立掷3颗公平6面骰子，求最大点数恰好等于5的概率'
        request = self.scripted(call('check_answer', {}), answer('精确计算后，数值不一致。'))
        response = self.invoke(request, question=question, answer='125/216')
        self.assertFalse(response['calculation']['matches'])
        tool_message = self.payloads[1]['messages'][-1]
        self.assertEqual(tool_message['role'], 'tool')
        self.assertEqual(tool_message['tool_call_id'], 'call-one')
        self.assertEqual(json.loads(tool_message['content'])['calculation']['expected'], '61/216')
        self.assertEqual(response['decision']['status'], 'checked')

    def test_hallucinated_source_id_is_not_displayed(self):
        response = self.invoke(self.scripted(*[answer('教材表明成立[E999]。')] * 3))
        self.assertEqual(response['decision']['status'], 'citation_failed')
        self.assertNotIn('teaching', response)

    def test_plain_text_clarification_is_retried_as_a_resumable_tool_action(self):
        request = self.scripted(answer('请提供总体分布和待估参数。'),
                                call('ask_clarification', {'kind': 'estimation', 'prompt': '请补充总体和参数'}))
        response = self.invoke(request, question='有一组样本，求参数估计', intent='explain')
        self.assertEqual(response['decision']['status'], 'awaiting_input')
        self.assertIn('checkpoint', response['clarification'])
        self.assertEqual(response['model_calls'], 2)

    def test_checked_number_does_not_authorize_an_invented_textbook_location(self):
        request = self.scripted(call('check_answer', {}), answer('结果61/216，参见例1.4.3。'),
                                answer('根据核对工具，相邻累计概率相减得到61/216。'))
        response = self.invoke(request, question='独立掷3颗公平6面骰子，求最大点数恰好等于5的概率',
                               intent='check', answer='125/216')
        self.assertEqual(response['decision']['status'], 'checked')
        self.assertNotIn('例1.4.3', response['teaching']['text'])
        self.assertEqual(response['model_calls'], 3)

    @patch('study_tools.execute')
    def test_source_feedback_reads_and_uses_actual_evidence(self, execute):
        execute.side_effect = [
            {'status': 'candidate_matches', 'recommendations': [{'id': 'e', 'kind': 'example'}],
             'candidates': [{'id': 'e', 'kind': 'example'}], 'topics': []},
            {'record_id': 'e', 'title': '教材条目', 'text': '原文', 'pages': [9]},
        ]
        request = self.scripted(call('search_textbook', {'query': '最大似然估计'}),
                                answer('成立[E999]'), call('read_source', {'record_id': 'e'}),
                                answer('可按教材方法处理[E1]。'))
        response = self.invoke(request, intent='explain')
        self.assertEqual(response['decision']['status'], 'citation_checked')
        self.assertEqual(response['evidence'][0]['id'], 'E1')
        self.assertIn('[E1]', response['teaching']['text'])
        self.assertTrue(any(row['step'] == '引用反馈' for row in response['trace']))

    @patch('study_tools.execute')
    def test_lookup_displays_source_backed_candidates_without_requiring_a_generated_solution(self, execute):
        execute.return_value = {'status': 'candidate_matches',
            'recommendations': [{'id': 'mao3-6.1-6', 'kind': 'exercise', 'pages': [294]}],
            'candidates': [{'id': 'mao3-6.1-6', 'kind': 'exercise', 'pages': [294]}], 'topics': []}
        request = self.scripted(call('search_textbook', {'query': '习题6.1第6题'}),
                                answer('找到习题6.1第6题。'))
        response = self.invoke(request, question='找习题6.1第6题', intent='lookup')
        self.assertEqual(response['decision']['status'], 'candidates_ready')
        self.assertEqual(response['model_calls'], 2)
        self.assertNotIn('teaching', response)

    def test_repeated_invalid_calls_stop_at_budget_without_saving_false_result(self):
        def request(url, payload, key):
            return call('run_arbitrary_python', {'code': 'print(1)'})
        response = self.invoke(request)
        self.assertEqual(response['model_calls'], agent.MAX_CALLS)
        self.assertEqual(response['tool_count'], 0)
        self.assertEqual(response['decision']['status'], 'budget_exhausted')
        self.assertNotIn('teaching', response)

    def test_reading_requires_a_previously_found_source_and_strict_arguments(self):
        with self.assertRaises(ValueError):
            study_tools.execute('read_source', {'record_id': 'mao3-6.1-6'}, {})
        with self.assertRaises(ValueError):
            study_tools.execute('check_answer', {'question': 'changed event'}, {})
        with self.assertRaises(ValueError):
            study_tools.execute('search_textbook', {'query': '正态总体', 'section': '../files'}, {})

    def test_episodic_memory_is_idempotent_and_scoped_before_vector_ranking(self):
        study_memory.save('1', self.learner, '均值估计', '有教材候选', {}, self.memory)
        study_memory.save('1', self.learner, '均值估计', '更新记录', {}, self.memory)
        study_memory.save('2', 'b' * 32, '均值估计', '另一学习者', {}, self.memory)
        memories = study_memory.recall(self.learner, '均值', path=self.memory)
        self.assertEqual(len(memories), 1)
        self.assertEqual(memories[0]['summary'], '更新记录')
        self.assertFalse(study_memory.recall('c' * 32, '均值', path=self.memory))
        self.assertFalse(study_memory.recall(self.learner, '均值', exclude_task='1', path=self.memory))
