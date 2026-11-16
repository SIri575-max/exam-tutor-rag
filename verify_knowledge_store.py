"""Non-label checks: source consistency, graph integrity, budgets and GSSC loss guards."""
import json
from pathlib import Path

import context_engineering
import knowledge_store
import question_knowledge
import study_tools


def verify():
    report = knowledge_store.status()
    with knowledge_store.connect(knowledge_store.DB) as con:
        integrity = con.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        foreign_keys = con.execute('PRAGMA foreign_key_check').fetchone() is None
        nodes = {r['id']: json.loads(r['payload']) for r in con.execute('SELECT id,payload FROM nodes')}
        edges = [json.loads(r['payload']) for r in con.execute('SELECT payload FROM edges')]
    original = question_knowledge.current()
    signatures = lambda es: {(e['from'], e['to'], e['kind'], e.get('quote', ''), tuple(e['source_pages'])) for e in es}
    checks = {'sqlite_integrity': integrity, 'foreign_keys': foreign_keys,
              'all_source_edges_preserved': signatures(original['edges']) <= signatures(edges),
              'all_nodes_have_positive_pdf_pages': all(n.get('pages') and all(type(p) is int and p > 0 for p in n['pages']) for n in nodes.values()),
              'no_inferred_tests_or_prerequisite': all(e['kind'] in knowledge_store.RELATIONS for e in edges)}
    probes = []
    for query in ('最大似然估计', '均匀分布', '置信区间', '例6.1.6', 'chapter:6', '不存在的知识条目xyz'):
        result = knowledge_store.neighborhood(query, depth=2)
        ids = {n['id'] for n in result['nodes']}
        ok = len(ids) <= 40 and len(result['edges']) <= 160 and all({e['from'], e['to']} <= ids for e in result['edges'])
        probes.append({'query': query, 'seeds': result['seed_ids'], 'nodes': len(ids), 'edges': len(result['edges']), 'bounded_and_connected': ok})
    checks['bounded_neighborhood_probes'] = all(p['bounded_and_connected'] for p in probes)
    checks['exact_numbered_reference_seed'] = probes[3]['seeds'] == ['example-6.1.6']
    checks['unknown_query_does_not_fabricate_nodes'] = not probes[-1]['nodes']
    observation = study_tools.execute('knowledge_path', {'topic': '最大似然估计'}, {})
    packed = context_engineering.pack('knowledge_path', observation)
    checks['tool_has_source_read_paths'] = bool(observation['paths']) and all(p['node'].get('pages') and p.get('source_pages') for p in observation['paths'])
    checks['packed_context_within_budget'] = context_engineering.size(packed) <= context_engineering.MAX_CHARS
    source = {'id': 'E1', 'record_id': 'probe', 'text': r'不要求独立；$P(A\mid B)\ne P(A)$', 'pages': [23]}
    checks['formula_condition_citation_preserved'] = all(context_engineering.pack('read_source', source)[k] == source[k] for k in source)
    output = {'date': '2026-11-16', 'passed': all(checks.values()), 'checks': checks,
              'graph_counts': {k: report[k] for k in ('nodes', 'edges', 'node_kinds', 'edge_kinds')},
              'source_manifest': report['manifest'], 'probes': probes,
              'context': packed.get('context_policy'),
              'boundary': 'Engineering integrity checks only. No human relevance labels, retrieval accuracy or teaching gain is inferred.'}
    target = Path('data/private/knowledge/verification-20261116.json')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(output, ensure_ascii=False, indent=2))
    if not output['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    verify()
