import unittest

from agent_benchmark import per_kind_metrics


class AgentBenchmarkTests(unittest.TestCase):
    def test_pool_recall_is_typed_and_distinguishes_missing_from_no_labels(self):
        example = {'id': 'e', 'kind': 'example'}
        weak = {'id': 'w', 'kind': 'example'}
        exercise = {'id': 'x', 'kind': 'exercise'}
        case = {'arms': {
            'retrieval_only': {'hits': [weak, example, exercise]},
            'agent_single': {'hits': [exercise]},
            'agent_adaptive': {'hits': [example, exercise]},
        }}
        grades = {'grades': {'e': 2, 'w': 1, 'x': 3}}
        examples = per_kind_metrics([case], [grades], 'example')
        self.assertEqual(examples['retrieval_only']['pooled_recall_at_3'], 1)
        self.assertEqual(examples['retrieval_only']['mrr_at_3'], .5)
        self.assertEqual(examples['retrieval_only']['weak_recommendation_rate'], .5)
        self.assertEqual(examples['agent_single']['pooled_recall_at_3'], 0)
        self.assertIsNone(examples['agent_single']['weak_recommendation_rate'])
        exercises = per_kind_metrics([case], [grades], 'exercise')
        self.assertEqual(exercises['agent_single']['pooled_recall_at_3'], 1)
        self.assertIsNone(per_kind_metrics([], [], 'example')['agent_adaptive']['mrr_at_3'])
