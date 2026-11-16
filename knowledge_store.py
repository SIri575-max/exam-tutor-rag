"""Source-bearing SQLite property graph; no inferred mastery or prerequisite labels."""
import argparse
import collections
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile

import book_structure
import question_knowledge

DB = Path(__file__).parent / 'data/private/knowledge/graph.sqlite3'
RELATIONS = {
    'contains_section': '章节包含', 'contains_topic': '小节包含知识条目',
    'contains_source_unit': '同小节原文条目', 'located_in_subsection': '位于小节',
    'mentions_topic': '题干字面提及', 'literal_example_mention': '原文提及例题',
    'data_or_continuation_reference': '原文引用例题数据',
}
BOUNDARY = '目录层级、字面提及和原文引用；自动关联不等于已审核考点、先修关系或学生掌握度。'


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def manifest(graph, outline):
    return {'schema': 1, 'graph_sha256': digest(graph), 'outline_sha256': digest(outline),
            'builder_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


@contextmanager
def connect(path):
    con = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)
    con.row_factory = sqlite3.Row
    try:
        yield con
    finally:
        con.close()


def build(path=DB, graph=None, outline=None):
    graph = question_knowledge.current() if graph is None else graph
    outline = book_structure.structure() if outline is None else outline
    nodes = {n['id']: dict(n) for n in graph['nodes']}
    if len(nodes) != len(graph['nodes']):
        raise ValueError('Duplicate source node IDs')
    edges = list(graph['edges'])
    for chapter in outline['chapters']:
        identifier = 'chapter:' + chapter['id']
        nodes[identifier] = {'id': identifier, 'kind': 'chapter', 'label': chapter['title'],
                             'pages': [chapter['pdf_first']], 'review_status': 'source_TOC_anchor'}
    for section in outline['sections']:
        identifier = 'section:' + section['id']
        nodes[identifier] = {'id': identifier, 'kind': 'section', 'label': section['id'] + ' ' + section['title'],
                             'pages': [section['pdf_first']], 'review_status': section.get('page_mapping_status', 'TOC_location')}
        edges.append({'from': 'chapter:' + str(section['chapter']), 'to': identifier,
                      'kind': 'contains_section', 'source_pages': [section['pdf_first']],
                      'review_status': 'source_TOC_hierarchy'})
    for topic in graph['topics']:
        edges.append({'from': 'section:' + topic['section'], 'to': topic['id'],
                      'kind': 'contains_topic', 'source_pages': [topic['pdf_first']],
                      'review_status': 'source_TOC_hierarchy'})
    unique = {}
    for edge in edges:
        if edge['from'] not in nodes or edge['to'] not in nodes:
            raise ValueError('Dangling source edge: ' + edge['from'] + ' -> ' + edge['to'])
        if edge['kind'] not in RELATIONS:
            raise ValueError('Unsupported relation: ' + edge['kind'])
        if not edge.get('source_pages') or any(type(p) is not int or p < 1 for p in edge['source_pages']):
            raise ValueError('An edge must have positive PDF source pages')
        if edge['kind'] in {'mentions_topic', 'literal_example_mention', 'data_or_continuation_reference'} and not edge.get('quote'):
            raise ValueError('A literal relation must retain its quote')
        identifier = digest([edge['from'], edge['to'], edge['kind'], edge.get('quote', ''), edge['source_pages']])
        unique[identifier] = {**edge, 'id': identifier, 'relation_label': RELATIONS[edge['kind']],
                              'provenance': {k: graph['report'].get(k) for k in ('source_sha256', 'collection_sha256', 'rules_sha256')}}
    report = {'status': 'ready', 'nodes': len(nodes), 'edges': len(unique),
              'deduplicated_edges': len(edges) - len(unique),
              'node_kinds': dict(collections.Counter(n['kind'] for n in nodes.values())),
              'edge_kinds': dict(collections.Counter(e['kind'] for e in unique.values())),
              'boundary': BOUNDARY, 'manifest': manifest(graph, outline),
              'source': graph['report']}
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix='graph-', suffix='.sqlite3', dir=path.parent)
    os.close(handle)
    try:
        con = sqlite3.connect(temporary)
        try:
            con.executescript('''PRAGMA foreign_keys=ON;
                CREATE TABLE nodes(id TEXT PRIMARY KEY, kind TEXT NOT NULL, label TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE edges(id TEXT PRIMARY KEY, source TEXT REFERENCES nodes(id), target TEXT REFERENCES nodes(id), relation TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE INDEX outgoing ON edges(source,relation);
                CREATE INDEX incoming ON edges(target,relation);
                CREATE INDEX node_kind ON nodes(kind);
                CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);''')
            with con:
                con.executemany('INSERT INTO nodes VALUES(?,?,?,?)', [(i, n['kind'], n['label'], json.dumps(n, ensure_ascii=False)) for i, n in nodes.items()])
                con.executemany('INSERT INTO edges VALUES(?,?,?,?,?)', [(i, e['from'], e['to'], e['kind'], json.dumps(e, ensure_ascii=False)) for i, e in unique.items()])
                con.execute('INSERT INTO metadata VALUES(?,?)', ('report', json.dumps(report, ensure_ascii=False)))
            if con.execute('PRAGMA foreign_key_check').fetchone():
                raise ValueError('Invalid graph foreign keys')
            if con.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('Invalid SQLite graph')
        finally:
            con.close()
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return report


def status(path=DB, validate=True):
    if not Path(path).exists():
        raise ValueError('图谱尚未建立，请运行 python knowledge_store.py build')
    with connect(path) as con:
        report = json.loads(con.execute("SELECT value FROM metadata WHERE key='report'").fetchone()[0])
    if validate and report['manifest'] != manifest(question_knowledge.current(), book_structure.structure()):
        raise ValueError('图谱来源或规则已变更，请运行 python knowledge_store.py build 重建')
    return report


def neighborhood(query='', depth=1, node_limit=40, relation='', path=DB, validate=True):
    if not isinstance(query, str) or len(query) > 300:
        raise ValueError('查询应不超过300字')
    if type(depth) is not int or not 1 <= depth <= 2 or type(node_limit) is not int or not 8 <= node_limit <= 80:
        raise ValueError('depth须为1–2，node_limit须为8–80')
    if relation and relation not in RELATIONS:
        raise ValueError('未知关系筛选')
    report = status(path, validate)
    with connect(path) as con:
        query = query.strip()
        direct = con.execute('SELECT id FROM nodes WHERE id=?', (query,)).fetchone()
        seeds = [direct['id']] if direct else []
        if query and not seeds:
            # Numbered references are resolved locally; the language model cannot invent IDs.
            from full_book_tutor import explicit_id
            identifier = explicit_id(query)
            if identifier and con.execute('SELECT 1 FROM nodes WHERE id=?', (identifier,)).fetchone():
                seeds = [identifier]
        if query and not seeds:
            topics = question_knowledge.mentions(query)
            seeds = [t['id'] for t in sorted(topics, key=lambda t: -len(t['matched_alias']))[:3]
                     if con.execute('SELECT 1 FROM nodes WHERE id=?', (t['id'],)).fetchone()]
        if query and not seeds:
            # Escape LIKE metacharacters: a percent sign in a formula is not "all nodes".
            literal = query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
            seeds = [r['id'] for r in con.execute("SELECT id FROM nodes WHERE label LIKE ? ESCAPE '\\' ORDER BY id LIMIT 3", ('%' + literal + '%',))]
        if not query:
            seeds = [r['id'] for r in con.execute("SELECT id FROM nodes WHERE kind='chapter' ORDER BY id")]
        visible = dict.fromkeys(seeds)
        frontier, selected_edges, truncated = seeds, {}, False
        # Empty query is an overview. Expansion happens after choosing a chapter.
        for _ in range(depth if query else 0):
            following = []
            for identifier in frontier:
                sql = 'SELECT e.payload,n.kind FROM edges e JOIN nodes n ON n.id=CASE WHEN e.source=? THEN e.target ELSE e.source END WHERE (e.source=? OR e.target=?)'
                args = [identifier] * 3
                if relation:
                    sql += ' AND e.relation=?'
                    args.append(relation)
                groups = collections.defaultdict(list)
                for row in con.execute(sql + ' ORDER BY e.relation,e.target,e.source', args):
                    groups[row['kind']].append(json.loads(row['payload']))
                # Round robin prevents a large exercise group from hiding definitions/examples.
                candidates = []
                while any(groups.values()):
                    for kind in sorted(groups):
                        if groups[kind]:
                            candidates.append(groups[kind].pop(0))
                for edge in candidates:
                    if len(selected_edges) >= 160 and edge['id'] not in selected_edges:
                        truncated = True
                        continue
                    other = edge['to'] if edge['from'] == identifier else edge['from']
                    if other not in visible:
                        if len(visible) >= node_limit:
                            truncated = True
                            continue
                        visible[other] = None
                        following.append(other)
                    selected_edges[edge['id']] = edge
            frontier = following
        nodes = [json.loads(con.execute('SELECT payload FROM nodes WHERE id=?', (i,)).fetchone()[0]) for i in visible]
    return {'query': query, 'seed_ids': seeds, 'nodes': nodes, 'edges': list(selected_edges.values()),
            'budget': {'depth': depth, 'node_limit': node_limit, 'edge_limit': 160, 'returned_nodes': len(nodes), 'truncated': truncated},
            'boundary': BOUNDARY, 'relations': RELATIONS, 'report': report}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['build', 'status'], default='status', nargs='?')
    arguments = parser.parse_args()
    print(json.dumps(build() if arguments.action == 'build' else status(), ensure_ascii=False, indent=2))
