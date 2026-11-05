"""Audit coverage, provenance, vector bytes, and question-only embedding inputs."""
import collections
import hashlib
import json
from contextlib import closing
import numpy as np
from exercise_collection import rows, reviewed_stem
from exercise_vectors import DB, OUT, MAX_TOKENS, status, connect
from process_full_book import BASE, write_json


def verify():
    info=status(); failures=[]
    if not info['ready']:failures.append('stale index')
    with closing(connect()) as conn:
        integrity=conn.execute('PRAGMA integrity_check').fetchone()[0]
        records={i:json.loads(data) for i,data in conn.execute('SELECT id,data FROM records')}
        chunks=list(conn.execute('SELECT record_id,text,start,end,token_count,content_sha256,embedding FROM chunks'))
    if integrity!='ok':failures.append('SQLite integrity')
    original=rows(BASE/'exercise-candidates.jsonl')
    if {x['id'] for x in original}!={i for i,r in records.items() if r['kind']=='exercise'}:failures.append('exercise coverage')
    originals={x['id']:x for x in original}
    source_blocks={x['id']:x for x in rows(BASE/'normalized-blocks.jsonl')}
    manifest=json.loads((BASE/'manifest.json').read_text(encoding='utf-8'))
    for x in rows(BASE/'learning-units.jsonl'):
        if x['kind']=='example' and x['id'] not in originals:originals[x['id']]=x
    for i,r in records.items():
        if r['kind'] not in {'exercise','example'}:failures.append('non-question '+i)
        if r['full_text']!=originals[i]['text'] or r['block_ids']!=originals[i]['block_ids']:failures.append('changed source '+i)
        if r.get('stem_review'):
            if r['question_text']!=reviewed_stem(originals[i],source_blocks,r['stem_review'],manifest):failures.append('changed reviewed stem '+i)
        elif r['question_text'] not in r['full_text']:failures.append('invented stem '+i)
    coverage=collections.defaultdict(set)
    for identifier,text,start,end,tokens,digest,blob in chunks:
        r=records[identifier]; v=np.frombuffer(blob,dtype=np.float32)
        if v.shape!=(512,) or not np.isfinite(v).all() or abs(np.linalg.norm(v)-1)>1e-4:failures.append('invalid vector '+identifier)
        if tokens>MAX_TOKENS:failures.append('truncated input '+identifier)
        if not text.endswith(r['search_text'][start:end]):failures.append('wrong embedded slice '+identifier)
        if hashlib.sha256(text.encode()).hexdigest()!=digest:failures.append('chunk hash '+identifier)
        coverage[identifier].update(range(start,end))
    for i,r in records.items():
        if coverage[i]!=set(range(len(r['search_text']))):failures.append('chunk coverage '+i)
    report={'status':'passed' if not failures else 'failed','failures':failures,'records':len(records),
            'kinds':dict(collections.Counter(r['kind'] for r in records.values())),
            'chunks':len(chunks),'dimensions':512,'sqlite_integrity':integrity,
            'all_question_text_characters_covered':not failures,'reference_answer_documents':0,
            'boundary':'Checks coverage and indexing integrity, not OCR or mathematical correctness.'}
    write_json(OUT/'integrity-report.json',report)
    print(json.dumps(report,ensure_ascii=False,indent=2))
    if failures:raise SystemExit(1)
    return report


if __name__=='__main__':verify()
