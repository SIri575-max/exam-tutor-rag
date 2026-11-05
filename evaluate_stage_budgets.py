"""Source-ID development ablation; no LLM judging or invented relevance labels."""
import argparse
from dataclasses import replace
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import time
import sys
import exercise_vectors as vectors
from full_book_tutor import retrieve
from retrieval_policy import DEFAULT_BUDGET

ROOT=Path(__file__).resolve().parent
BASE=ROOT/'data/private/chunk-topk-20261105'
DATASET=ROOT/'data/private/correspondence-study-20261104/frozen-source-queries.json'
DATASET_SHA='d041f9ac4f3d10410d3b0d4ac4ed787cf96a5200fd876014059d8189c22d71c3'


def metrics(rows,k):
    ranks=[r['returned_ids'][:k].index(r['source_id'])+1 if r['source_id'] in r['returned_ids'][:k] else None for r in rows]
    return {'cases':len(rows),'k':k,'source_hit_count':sum(r is not None for r in ranks),
            'source_hit_rate':sum(r is not None for r in ranks)/len(rows),
            'source_mrr':sum(1/r for r in ranks if r)/len(rows),
            'teacher_relevance_recall':None,'teacher_relevance_precision':None}


def run(phase,index=None):
    BASE.mkdir(parents=True,exist_ok=True)
    raw=DATASET.read_bytes();assert hashlib.sha256(raw).hexdigest()==DATASET_SHA
    if index:
        vectors.DB=Path(index).resolve();vectors.OUT=vectors.DB.parent
    cases=json.loads(raw)['cases'];rows={}
    # Fixed type is supplied to the simple retrieval baselines; correspondence
    # must produce both kinds, matching the original source proxy protocol.
    for mode in ['bm25','vector','hybrid','correspondence']:
        collected=[]
        for c in cases:
            start=time.perf_counter()
            result=retrieve(c['query']) if mode=='correspondence' else vectors.search(c['query'],mode,c['kind'],limit=20)
            hits=result.get('practice_groups',{}).get(c['kind'],[]) if mode=='correspondence' else result['hits']
            collected.append({'case_id':c['id'],'source_id':c['source_id'],'kind':c['kind'],
                              'returned_ids':[h['id'] for h in hits],'seconds':time.perf_counter()-start})
        rows[mode]=collected
        print(phase,mode,'completed',flush=True)
    sweeps=[]
    if phase=='candidate':
        for recall_k,lexical_k in [(10,10),(10,20),(20,10),(20,20)]:
            budget=replace(DEFAULT_BUDGET,recall_k=recall_k,typed_lexical_k=lexical_k,practice_k=5)
            collected=[]
            for c in cases:
                result=retrieve(c['query'],budget=budget)
                hits=result.get('practice_groups',{}).get(c['kind'],[])
                collected.append({'case_id':c['id'],'source_id':c['source_id'],'returned_ids':[h['id'] for h in hits]})
            sweeps.append({'budget':budget.describe(),'metrics':[metrics(collected,k) for k in [1,3,5]],'details':collected})
            print('budget sweep',recall_k,lexical_k,'completed',flush=True)
    report={'date':'2026-11-05','phase':phase,'dataset_sha256':DATASET_SHA,
            'index_sha256':hashlib.sha256(vectors.DB.read_bytes()).hexdigest(),'index_metadata':vectors.status(),
            'summary':{m:[metrics(v,k) for k in ([1,3] if m=='correspondence' else [1,3,5,10,20])] for m,v in rows.items()},
            'details':rows,'budget_sweeps':sweeps,'new_generation_api_calls':0,
            'code_sha256':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in ['exercise_vectors.py','formula_chunking.py','full_book_tutor.py','retrieval_policy.py','evaluate_stage_budgets.py']},
            'loaded_runtime_modules':{m.__name__:{'path':str(Path(m.__file__).resolve()),'sha256':hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest()}
                                      for m in [vectors,sys.modules[retrieve.__module__]]},
            'boundary':'Same 24 known-source paraphrases already used for tuning. Source-ID proxy only. Other candidates are unjudged, so no relevance precision/recall. Timings are diagnostic with cache warming, not a paired latency experiment.'}
    folder=BASE/(phase+'-'+datetime.now(timezone(timedelta(hours=8))).strftime('%H%M%S'));folder.mkdir(exist_ok=False)
    (folder/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'report':str(folder/'report.json'),'summary':report['summary'],'sweeps':[{'budget':s['budget'],'metrics':s['metrics']} for s in sweeps]},ensure_ascii=False))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--phase',choices=['baseline','candidate'],required=True);parser.add_argument('--index')
    args=parser.parse_args();run(args.phase,args.index)
