import json
from pathlib import Path
import unittest
from book_structure import structure


class SyllabusPlanTests(unittest.TestCase):
    def test_source_tree_and_candidate_statuses(self):
        path=Path(__file__).resolve().parents[1]/'data/private/syllabus/knowledge-network-plan.json'
        d=json.loads(path.read_text(encoding='utf-8'));nodes=d['nodes'];ids={n['id'] for n in nodes}
        self.assertEqual(len(ids),len(nodes))
        topics=[n for n in nodes if n['kind']=='syllabus_topic']
        self.assertEqual(len(topics),32)
        self.assertEqual(len([n for n in topics if n['id'].startswith('syllabus-statistics-')]),20)
        self.assertEqual(len([n for n in topics if n['id'].startswith('syllabus-probability-')]),12)
        self.assertEqual(len(d['edges']),len(nodes)-1)
        self.assertTrue(all(e['from'] in ids and e['to'] in ids and e['kind']=='source_contains' for e in d['edges']))
        sections={s['id'] for s in structure()['sections']}
        self.assertTrue(all(a['section'] in sections and a['status']=='assistant_proposal_pending_review'
                            for n in topics for a in n['candidate_book_sections']))
        missing=[n['label'] for n in topics if not n['candidate_book_sections']]
        self.assertTrue(any('ARIMA' in label for label in missing))
        self.assertTrue(any('主成分' in label for label in missing))
        self.assertEqual(d['status'],'planned_reference_network_not_live_retrieval_graph')


if __name__=='__main__':unittest.main()
