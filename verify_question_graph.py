"""Verify graph endpoints and evidence roles, not pedagogical correctness."""
import collections
import json
from question_knowledge import current, mentions
from exercise_vectors import OUT, snapshot
from process_full_book import write_json


def verify():
    g=current();errors=[];ids=[n['id'] for n in g['nodes']];known=set(ids);records=snapshot()[1]
    if len(ids)!=len(known):errors.append('Duplicate graph node IDs')
    for e in g['edges']:
        if e['from'] not in known or e['to'] not in known:errors.append('Dangling edge')
        if e['kind'] in {'tests','requires'}:errors.append('Unapproved pedagogical edge')
        if e['kind']=='mentions_topic':
            record=records[e['from']]
            if not any(m['id']==e['to'] and m['quote']==e['quote'] for m in mentions(record['question_text'],g['topics'])):
                errors.append('Unsupported literal edge '+e['from'])
        if e['kind'] in {'data_or_continuation_reference','literal_example_mention'}:
            if not any(r['id']==e['to'] and r['quote']==e['quote'] for r in records[e['from']]['example_references']):errors.append('Unsupported reference')
    result={'status':'passed' if not errors else 'failed','errors':errors,
            'nodes':len(ids),'edges':len(g['edges']),'edge_kinds':dict(collections.Counter(e['kind'] for e in g['edges'])),
            'collection_sha256':g['report']['collection_sha256'],
            'boundary':'Literal and location evidence is checked; skill labels and prerequisites still need teacher review.'}
    write_json(OUT/'graph-integrity-report.json',result);print(json.dumps(result,ensure_ascii=False,indent=2))
    if errors:raise SystemExit(1)
    return result


if __name__=='__main__':verify()
