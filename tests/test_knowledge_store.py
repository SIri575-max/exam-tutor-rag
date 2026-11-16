from copy import deepcopy
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import knowledge_store as store
import study_tools


def fixture():
    graph = {'report': {'source_sha256': 'source', 'collection_sha256': 'collection', 'rules_sha256': 'rules'},
             'nodes': [{'id': 'topic:6.3.1', 'kind': 'topic', 'label': '最大似然估计', 'pages': [300]},
                       {'id': 'example-6.3.1', 'kind': 'example', 'label': '例6.3.1', 'pages': [301]},
                       {'id': 'definition-6.3.1', 'kind': 'definition', 'label': '定义6.3.1', 'pages': [300]}],
             'topics': [{'id': 'topic:6.3.1', 'section': '6.3', 'pdf_first': 300}],
             'edges': [{'from': 'example-6.3.1', 'to': 'topic:6.3.1', 'kind': 'mentions_topic',
                        'quote': '求最大似然估计', 'source_pages': [301], 'review_status': 'literal'},
                       {'from': 'topic:6.3.1', 'to': 'definition-6.3.1', 'kind': 'contains_source_unit',
                        'source_pages': [300], 'review_status': 'same_subsection'}]}
    outline = {'chapters': [{'id': '6', 'title': '参数估计', 'pdf_first': 289}],
               'sections': [{'id': '6.3', 'chapter': '6', 'title': '最大似然估计', 'pdf_first': 300}]}
    return graph, outline


class KnowledgeStoreTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / 'graph.sqlite3'
        self.graph, self.outline = fixture()
        self.report = store.build(self.path, self.graph, self.outline)

    def query(self, query='', **kw):
        return store.neighborhood(query, path=self.path, validate=False, **kw)

    def test_normalized_store_has_foreign_keys_indexes_and_provenance(self):
        with store.connect(self.path) as con:
            self.assertEqual(con.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertIsNone(con.execute('PRAGMA foreign_key_check').fetchone())
            self.assertEqual(con.execute('SELECT count(*) FROM nodes').fetchone()[0], 5)
            edge = json.loads(con.execute("SELECT payload FROM edges WHERE relation='mentions_topic'").fetchone()[0])
            self.assertEqual(edge['quote'], '求最大似然估计')
            self.assertEqual(edge['provenance']['source_sha256'], 'source')
        self.assertEqual(self.query()['nodes'][0]['id'], 'chapter:6')

    def test_rebuild_is_idempotent_and_invalid_rebuild_preserves_old_database(self):
        self.assertEqual(store.build(self.path, self.graph, self.outline), self.report)
        before = self.path.read_bytes()
        bad = deepcopy(self.graph)
        bad['edges'][0]['to'] = 'missing'
        with self.assertRaisesRegex(ValueError, 'Dangling'):
            store.build(self.path, bad, self.outline)
        self.assertEqual(self.path.read_bytes(), before)

    def test_two_hops_and_relation_filter_have_real_endpoints(self):
        one = self.query('example-6.3.1')
        self.assertEqual({n['id'] for n in one['nodes']}, {'example-6.3.1', 'topic:6.3.1'})
        two = self.query('example-6.3.1', depth=2)
        self.assertIn('definition-6.3.1', {n['id'] for n in two['nodes']})
        self.assertNotIn('chapter:6', {n['id'] for n in two['nodes']})
        filtered = self.query('topic:6.3.1', relation='contains_source_unit')
        self.assertEqual(len(filtered['edges']), 1)
        for edge in two['edges']:
            self.assertTrue({edge['from'], edge['to']} <= {n['id'] for n in two['nodes']})

    def test_exact_reference_alias_and_literal_wildcard(self):
        self.assertEqual(self.query('例6.3.1')['seed_ids'], ['example-6.3.1'])
        self.assertEqual(self.query('最大似然估计')['seed_ids'], ['topic:6.3.1'])
        self.assertEqual(self.query('%')['nodes'], [])
        self.assertEqual(self.query("' OR 1=1 --")['nodes'], [])

    def test_budgets_and_unapproved_relations_are_rejected(self):
        for options in ({'depth': 3}, {'depth': True}, {'node_limit': 1000}, {'relation': 'requires'}):
            with self.assertRaises(ValueError):
                self.query('topic:6.3.1', **options)
        for edit in ('kind', 'quote', 'source_pages'):
            bad = deepcopy(self.graph)
            bad['edges'][0][edit] = {'kind': 'requires', 'quote': '', 'source_pages': []}[edit]
            with self.assertRaises(ValueError):
                store.build(self.path, bad, self.outline)

    def test_changed_source_is_rejected_and_never_rebuilt_by_a_query(self):
        changed = deepcopy(self.graph)
        changed['nodes'][0]['label'] = 'changed'
        before = self.path.read_bytes()
        with patch('knowledge_store.question_knowledge.current', return_value=changed), patch('knowledge_store.book_structure.structure', return_value=self.outline):
            with self.assertRaisesRegex(ValueError, '重建'):
                store.status(self.path)
        self.assertEqual(self.path.read_bytes(), before)

    def test_node_budget_keeps_definitions_and_examples_among_many_exercises(self):
        for i in range(50):
            identifier = 'exercise-' + str(i)
            self.graph['nodes'].append({'id': identifier, 'kind': 'exercise', 'label': identifier, 'pages': [302]})
            self.graph['edges'].append({'from': identifier, 'to': 'topic:6.3.1', 'kind': 'mentions_topic',
                                       'quote': '最大似然', 'source_pages': [302], 'review_status': 'literal'})
        store.build(self.path, self.graph, self.outline)
        result = self.query('topic:6.3.1', node_limit=8)
        self.assertEqual(len(result['nodes']), 8)
        self.assertTrue(result['budget']['truncated'])
        self.assertTrue({'example', 'definition', 'exercise'} <= {n['kind'] for n in result['nodes']})

    @patch('study_tools.study_agent.topic_paths', return_value=([], []))
    def test_tool_registers_source_backed_neighbors_for_read_source(self, paths):
        network = self.query('example-6.3.1', depth=2)
        with patch('study_tools.knowledge_store.neighborhood', return_value=network):
            result = study_tools.execute('knowledge_path', {'topic': '例6.3.1'}, {})
        self.assertTrue({'example-6.3.1', 'definition-6.3.1'} <= {p['node']['id'] for p in result['paths']})
        self.assertEqual(result['topics'][0]['id'], 'example-6.3.1')
        self.assertEqual(result['topics'][0]['relation'], 'query_anchor_not_skill_label')
        with patch('study_tools.exercise_vectors.record', return_value={'full_text': '原题', 'label': '例6.3.1', 'pages': [301]}):
            source = study_tools.execute('read_source', {'record_id': 'example-6.3.1'}, result)
        self.assertEqual(source['pages'], [301])

    @patch('study_tools.study_agent.topic_paths', return_value=([], []))
    def test_missing_store_falls_back_to_existing_tool(self, paths):
        with patch('study_tools.knowledge_store.neighborhood', side_effect=ValueError('not built')):
            result = study_tools.execute('knowledge_path', {'topic': '最大似然'}, {})
        self.assertEqual(result['network']['status'], 'unavailable')


if __name__ == '__main__':
    unittest.main()
