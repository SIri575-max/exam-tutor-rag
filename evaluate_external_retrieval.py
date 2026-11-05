"""Checkpointed external retrieval candidates; no invented recall without human labels."""
import argparse
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import time

from external_question_bank import BASE, ROOT, write_json
from build_external_evaluation import query_text
from exercise_vectors import search, status
from full_book_tutor import retrieve

ARMS = ('bm25', 'vector', 'hybrid', 'adaptive_rag')
CODE_FILES = ('evaluate_external_retrieval.py', 'full_book_tutor.py', 'exercise_vectors.py',
              'formula_retrieval.py', 'math_query_bridge.py', 'source_properties.py',
              'problem_conditions.py', 'question_knowledge.py', 'problem_correspondence.py','math_fingerprint.py')


def payload(item):
    return {'case_id': item['id'], 'query': query_text(item), 'question_text_sha256': item['text_sha256'],
            'source_pages': item['pages'], 'chapter': item['chapter'],
            'boundary_status': item['boundary_status'], 'review_status': item['review_status'],
            'family_id': item.get('family_id'), 'split': item.get('split')}


def summarize(entries):
    result = {}
    for name in ARMS:
        rows = [e['arms'][name] for e in entries if name in e.get('arms', {})]
        result[name] = {'attempted': len(rows), 'completed': sum(r['status']=='completed' for r in rows),
                        'with_candidates': sum(bool(r.get('hits')) for r in rows),
                        'mean_seconds': round(sum(r.get('elapsed_seconds',0) for r in rows)/len(rows),3) if rows else None,
                        'reviewed_relevance_cases': 0, 'recall_at_5': None, 'ndcg_at_5': None}
    return result


def run(limit=None):
    dataset = BASE/'dataset/questions.jsonl'
    data = [json.loads(s) for s in dataset.read_text(encoding='utf-8').splitlines()]
    # Partial/invalid boundary cases are retained in the exclusion report, not silently evaluated.
    excluded = [{'id': r['id'], 'reason': r['boundary_status'] if r['boundary_status']!='candidate_complete' else 'figure_semantics_pending_review'}
                for r in data if r['boundary_status']!='candidate_complete' or r.get('requires_figure_review')]
    items = [r for r in data if r['boundary_status']=='candidate_complete' and not r.get('requires_figure_review')]
    if limit: items = items[:limit]
    frozen = [payload(r) for r in items]
    index = status()
    code_sha = hashlib.sha256(b''.join((ROOT/f).read_bytes() for f in CODE_FILES)).hexdigest()
    cache_dir=BASE/'retrieval-cache'/code_sha[:16];cache_dir.mkdir(parents=True,exist_ok=True)
    identity = hashlib.sha256(json.dumps({'cases': frozen, 'collection': index['collection_sha256'], 'code': code_sha},
                                         ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    folder = BASE/'retrieval-runs'/identity[:16]; folder.mkdir(parents=True, exist_ok=True)
    target = folder/'report.json'
    if target.exists():
        report = json.loads(target.read_text(encoding='utf-8'))
        if report['identity_sha256'] != identity: raise ValueError('Identity conflict')
    else:
        report = {'created_at': datetime.now(timezone(timedelta(hours=8))).isoformat(),
                  'identity_sha256': identity, 'collection_sha256': index['collection_sha256'],
                  'code_sha256': code_sha, 'source_sha256': data[0]['source_sha256'] if data else None,
                  'frozen_cases': frozen, 'excluded': excluded, 'cases': [], 'llm_calls': 0,
                  'boundary': 'Unreviewed external retrieval candidates. Candidate presence is not recall or accuracy.'}
        write_json(folder/'frozen-inputs.json', frozen)
    done = {r['case_id']: r for r in report['cases']}
    def persist():
        report['summary'] = summarize(report['cases']); write_json(target, report)
    persist()
    for ordinal,item in enumerate(frozen,1):
        entry = done.get(item['case_id'])
        if entry is not None and all(name in entry['arms'] for name in ARMS):continue
        if entry is None:
            entry = {**item, 'arms': {}}; report['cases'].append(entry)
        for name in ARMS:
            if name in entry['arms']: continue
            cache_id=hashlib.sha256(json.dumps({'query':item['query'],'arm':name,'collection':index['collection_sha256']},
                                             ensure_ascii=False,sort_keys=True).encode()).hexdigest()
            cache_path=cache_dir/(cache_id+'.json')
            if cache_path.exists():
                cached=json.loads(cache_path.read_text(encoding='utf-8'))
                if cached.get('cache_identity')!=cache_id:raise ValueError('Cache identity mismatch')
                entry['arms'][name]={**cached['result'],'cache_reused':True}
                continue
            started = time.monotonic()
            try:
                result = retrieve(item['query']) if name=='adaptive_rag' else search(item['query'], mode=name, limit=8)
                value = {'status': 'completed', 'route': result.get('route', name),
                         'retrieval_status': result.get('status'), 'hits': [
                             {**{k: h[k] for k in ('id','label','pages','question_text','section') if k in h},
                              'relevance_grade': None, 'same_problem': None} for h in result['hits']]}
            except (ValueError, OSError) as error:
                value = {'status': 'failed', 'error': str(error)[:300], 'hits': []}
            value['elapsed_seconds'] = round(time.monotonic()-started,3)
            value['cache_reused']=False
            entry['arms'][name] = value
            if value['status']=='completed':write_json(cache_path,{'cache_identity':cache_id,'result':value})
        if ordinal%10==0:persist()
        if ordinal%20==0:
            print('retrieved', len(report['cases']), '/', len(frozen), flush=True)
    persist()
    write_review(folder, report)
    print(target, flush=True)
    return report, folder


def write_review(folder, report):
    # Pool all arms, sort by record ID: reviewers do not see ranks or arm names.
    rows = []
    for item in report['cases']:
        pooled = {h['id']: h for arm in item['arms'].values() for h in arm.get('hits', [])}
        rows.append({'case_id': item['case_id'], 'query': item['query'], 'source_pages': item['source_pages'],
                     'candidates': [pooled[k] for k in sorted(pooled)],
                     'review_status': 'pending_teacher_review',
                     'relevance_scale': '0无关 1同主题 2可借鉴方法/例题 3同题或完整条件近同'})
    write_json(folder/'blind-relevance-review.json', rows)


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--limit', type=int)
    run(p.parse_args().limit)
