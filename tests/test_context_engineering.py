from copy import deepcopy
import unittest

from context_engineering import pack, size


class ContextEngineeringTests(unittest.TestCase):
    def test_source_citation_formula_and_negated_condition_remain_exact(self):
        source = {'id': 'E1', 'record_id': 'r', 'text': r'不要求独立；$P(A\mid B)\ne P(A)$。', 'pages': [24]}
        result = pack('read_source', source)
        self.assertEqual(result['text'], source['text'])
        self.assertEqual(result['id'], 'E1')
        self.assertEqual(result['pages'], [24])
        self.assertEqual(result['context_policy']['output_chars'], size(result))

    def test_whole_record_compression_does_not_mutate_observation(self):
        rows = [{'id': str(i), 'question_text': '正态总体且方差未知。' * 100,
                 'correspondence': {'condition_conflict': True, 'differences': ['方差条件不同']}} for i in range(12)]
        observation = {'candidates': rows + [rows[0]], 'recommendations': rows[:2]}
        original = deepcopy(observation)
        result = pack('search_textbook', observation, 6000)
        self.assertEqual(observation, original)
        self.assertLessEqual(size(result), 6000)
        self.assertGreater(result['context_policy']['dropped_records'], 0)
        self.assertEqual(result['candidates'][0]['question_text'], rows[0]['question_text'])
        self.assertTrue(result['candidates'][0]['correspondence']['condition_conflict'])

    def test_oversize_evidence_is_explicitly_omitted_not_silently_clipped(self):
        result = pack('read_source', {'id': 'E1', 'text': '$a=b$' * 1000}, 1500)
        self.assertEqual(result['error'], 'context_budget_exceeded')
        self.assertNotIn('text', result)
        self.assertTrue(result['context_policy']['omitted_entire_observation'])

    def test_shared_provenance_retains_source_and_quotes(self):
        result = pack('knowledge_path', {'network': {'seed_ids': ['t'], 'nodes': [{'id': 't'}, {'id': 'q'}],
            'edges': [{'from': 'q', 'to': 't', 'quote': '不独立', 'source_pages': [9], 'provenance': {'source_sha256': 'source'}}]}})
        self.assertEqual(result['network']['source_manifest']['source_sha256'], 'source')
        self.assertEqual(result['network']['edges'][0]['quote'], '不独立')


if __name__ == '__main__':
    unittest.main()
