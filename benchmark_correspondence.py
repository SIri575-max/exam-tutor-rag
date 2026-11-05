"""Paired source-location proxy benchmark; generation and teacher accuracy are separate."""
import argparse
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import statistics
import time
from exercise_vectors import search, status
from full_book_tutor import retrieve

ROOT=Path(__file__).resolve().parent
BASE=ROOT/'data/private/correspondence-study-20261104'
DATASET_SHA='d041f9ac4f3d10410d3b0d4ac4ed787cf96a5200fd876014059d8189c22d71c3'
CODE_FILES=['benchmark_correspondence.py','full_book_tutor.py','formula_retrieval.py',
            'problem_correspondence.py','exercise_vectors.py','question_knowledge.py','math_fingerprint.py']
ARMS=['bm25','vector','hybrid','correspondence']


def scores(rows):
    ranks=[r['source_rank_at_3'] for r in rows];times=[r['seconds'] for r in rows]
    return {'cases':len(rows),'hit_at_1':sum(r==1 for r in ranks),
            'hit_at_3':sum(r is not None for r in ranks),
            'mrr_at_3':round(sum(1/r for r in ranks if r)/len(rows),4) if rows else None,
            'median_seconds':round(statistics.median(times),4) if times else None,
            'p95_seconds':round(sorted(times)[max(0,int(.95*len(times)+.999)-1)],4) if times else None}


def call(arm,c):
    start=time.perf_counter()
    if arm=='correspondence':
        r=retrieve(c['query']);hits=r.get('practice_groups',{}).get(c['kind'],[])[:3]
    else:r=search(c['query'],mode=arm,kind=c['kind'],limit=3);hits=r['hits']
    elapsed=time.perf_counter()-start
    ids=[h['id'] for h in hits];target=c['source_id']
    return {'case_id':c['id'],'kind':c['kind'],'chapter':c['chapter'],
            'source_rank_at_3':ids.index(target)+1 if target in ids else None,
            'seconds':round(elapsed,6),'returned_ids':ids,
            'candidates':[{k:h.get(k) for k in ['id','label','pages','question_text','correspondence']} for h in hits]}


def run(label):
    raw=(BASE/'frozen-source-queries.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=DATASET_SHA:raise ValueError('Frozen dataset changed')
    data=json.loads(raw);cases=data['cases'];info=status()
    # First request (model/index loading and caches) is explicit, outside warm timings.
    warmup={}
    for arm in ARMS:warmup[arm]=call(arm,cases[0])['seconds']
    rows={a:[] for a in ARMS}
    for i,c in enumerate(cases):
        ordered=ARMS[i%4:]+ARMS[:i%4]
        for arm in ordered:rows[arm].append(call(arm,c))
        if (i+1)%8==0:print('benchmarked',i+1,'/',len(cases),flush=True)
    summary={arm:scores(v) for arm,v in rows.items()}
    baseline={r['case_id']:r for r in rows['hybrid']}
    wins=[];losses=[]
    for r in rows['correspondence']:
        a=baseline[r['case_id']]['source_rank_at_3'];b=r['source_rank_at_3']
        if b==1 and a!=1:wins.append(r['case_id'])
        if a==1 and b!=1:losses.append(r['case_id'])
    report={'date':'2026-11-04','label':label,'dataset_sha256':DATASET_SHA,'collection_sha256':info['collection_sha256'],
            'source_label_provenance':data['boundary'],'summary':summary,'details':rows,'warmup_seconds':warmup,
            'paired_top1_wins_against_hybrid':wins,'paired_top1_losses_against_hybrid':losses,
            'by_kind':{k:{a:scores([r for r in rows[a] if r['kind']==k]) for a in ARMS} for k in ['example','exercise']},
            'code_sha256':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in CODE_FILES},
            'generation_api_calls':0,'teacher_relevance_accuracy':None,'student_time_saved':None,
            'timing_boundary':'Baseline is typed top-3 retrieval; correspondence includes both-type retrieval, explanations and study navigation. Compare before/after correspondence for equivalent service latency, not baseline speed as equivalent work.',
            'boundary':'24 assistant-authored paraphrases of known source OCR. Source-ID recovery proxy only; not independent relevance, new-question generalization, LLM answer accuracy or student efficiency.'}
    stamp=datetime.now(timezone(timedelta(hours=8))).strftime('%H%M%S')
    folder=BASE/('run-'+label+'-'+stamp);folder.mkdir(parents=True,exist_ok=False)
    (folder/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'report':str(folder/'report.json'),'summary':summary,'wins':wins,'losses':losses},ensure_ascii=False))
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--label',choices=['before','after'],required=True);run(p.parse_args().label)
