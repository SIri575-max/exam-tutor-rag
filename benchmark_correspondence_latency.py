"""Measure only the complete service, with no baseline methods warming each query."""
import argparse
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time
import full_book_tutor
import exercise_vectors
import problem_correspondence

ROOT=Path(__file__).resolve().parent
BASE=ROOT/'data/private/correspondence-study-20261104'


def summary(rows):
    v=sorted(r['seconds'] for r in rows)
    return {'requests':len(v),'median_seconds':round(statistics.median(v),6),
            'p95_seconds':round(v[int(.95*len(v)+.999)-1],6)}


def run(label):
    raw=(BASE/'frozen-source-queries.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!='d041f9ac4f3d10410d3b0d4ac4ed787cf96a5200fd876014059d8189c22d71c3':raise ValueError('Dataset changed')
    cases=json.loads(raw)['cases'];start=time.perf_counter();full_book_tutor.retrieve(cases[0]['query'])
    warmup=time.perf_counter()-start;rows=[];expected={}
    for repeat in range(4):
        for c in cases:
            start=time.perf_counter();r=full_book_tutor.retrieve(c['query']);elapsed=time.perf_counter()-start
            ids=[h['id'] for h in r.get('practice_groups',{}).get(c['kind'],[])[:3]]
            if repeat:assert ids==expected[c['id']],'Cached ranking changed'
            else:expected[c['id']]=ids
            rows.append({'case_id':c['id'],'repeat':repeat,'seconds':round(elapsed,6),'returned_ids':ids})
        print(label,'completed round',repeat+1,'/4',flush=True)
    modules={m.__name__:{'path':str(Path(m.__file__).resolve()),'sha256':hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest()}
             for m in [full_book_tutor,exercise_vectors,problem_correspondence]}
    result={'date':'2026-11-04','label':label,'dataset_sha256':hashlib.sha256(raw).hexdigest(),
            'warmup_seconds':round(warmup,6),'first_pass':summary([r for r in rows if r['repeat']==0]),
            'repeated_queries':summary([r for r in rows if r['repeat']>0]),'details':rows,'runtime_modules':modules,
            'generation_api_calls':0,'cached_ranking_consistent':True,
            'boundary':'Local service latency. One generic warmup precedes 24-query first pass; later 72 requests repeat those queries. Not OCR, API generation, human search time or student efficiency.'}
    stamp=datetime.now(timezone(timedelta(hours=8))).strftime('%H%M%S')
    target=BASE/('latency-'+label+'-'+stamp+'.json');target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'report':str(target),'first_pass':result['first_pass'],'repeated':result['repeated_queries']},ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--label',choices=['before','after'],required=True);run(p.parse_args().label)
