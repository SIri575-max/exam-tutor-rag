import unittest
from unittest.mock import patch

import study_agent


class StudyAgentTests(unittest.TestCase):
    dice = '独立掷3颗公平6面骰子，求最大点数恰好等于5的概率'

    def test_exact_check_uses_given_event_and_handles_wrong_answer(self):
        for question, answer, expected, matches in (
            (self.dice, '122/432', '61/216', True),
            (self.dice, '125/216', '61/216', False),
            (self.dice.replace('恰好等于', '不超过'), '125/216', '125/216', True),
        ):
            result = study_agent.run({'question': question, 'answer': answer})
            self.assertEqual(result['decision']['status'], 'checked')
            self.assertEqual(result['calculation']['expected'], expected)
            self.assertIs(result['calculation']['matches'], matches)

    def test_check_abstains_for_missing_assumption_or_multiple_goals(self):
        for question in (self.dice.replace('独立', ''), self.dice + '，并求最小点数的期望'):
            result = study_agent.run({'question': question, 'answer': '61/216'})
            self.assertEqual(result['decision']['status'], 'needs_review')
            self.assertNotIn('calculation', result)
        result = study_agent.run({'question': self.dice, 'answer': '1/0'})
        self.assertEqual(result['decision']['status'], 'needs_context')

    @patch('study_agent.question_knowledge.current')
    @patch('study_agent.question_knowledge.mentions')
    def test_graph_uses_only_provenanced_edges_and_respects_edge_direction(self, mentions, current):
        mentions.return_value = [{'id': 'topic:t', 'matched_alias': '分布'}]
        current.return_value = {'topics': [], 'nodes': [
            {'id': 'definition', 'kind': 'definition', 'pages': [2]},
            {'id': 'example', 'kind': 'example', 'pages': [3]},
            {'id': 'invalid', 'kind': 'example', 'pages': [4]},
        ], 'edges': [
            {'from': 'topic:t', 'to': 'definition', 'kind': 'contains_source_unit', 'source_pages': [2]},
            {'from': 'example', 'to': 'topic:t', 'kind': 'mentions_topic', 'source_pages': [3]},
            {'from': 'topic:t', 'to': 'invalid', 'kind': 'mentions_topic', 'source_pages': [4]},
            {'from': 'invalid', 'to': 'topic:t', 'kind': 'located_in_subsection'},
        ]}
        result = study_agent.run({'question': '复习分布'})
        self.assertEqual(result['decision']['status'], 'review_path_ready')
        self.assertEqual([row['node']['id'] for row in result['paths']], ['definition', 'example'])

    @patch('study_agent.full_book_tutor.retrieve')
    @patch('study_agent.topic_paths', return_value=([{'id': 't'}], [{'topic_id': 't'}]))
    @patch('study_agent.rag_generation.generate')
    def test_conflicting_retrieval_falls_back_to_graph_without_generating(self, generate, graph, retrieve):
        retrieve.return_value = {'route': 'single_retrieval', 'status': 'candidate_matches', 'hits': [
            {'id': 'x', 'pages': [9], 'correspondence': {'level': 'condition_difference', 'condition_conflict': True}},
        ]}
        result = study_agent.run({'question': '讲解这个正态分布题', 'allow_generation': True})
        self.assertEqual(result['decision']['status'], 'review_path_ready')
        graph.assert_called_once()
        generate.assert_not_called()

    @patch('study_agent.full_book_tutor.retrieve')
    @patch('study_agent.rag_generation.evidence_for', return_value=[{'id': 'E1', 'title': '依据', 'pages': [6]}])
    @patch('study_agent.rag_generation.generate')
    def test_optional_generation_requires_explicit_boolean_consent(self, generate, evidence, retrieve):
        retrieve.return_value = {'route': 'single_retrieval', 'status': 'candidate_matches', 'hits': [
            {'id': 'x', 'pages': [6], 'correspondence': {'level': 'structure_related'}},
        ]}
        result = study_agent.run({'question': '讲解这个正态分布题', 'allow_generation': 'true'})
        self.assertEqual(result['decision']['status'], 'evidence_ready')
        self.assertEqual(result['evidence'][0]['id'], 'E1')
        generate.assert_not_called()
