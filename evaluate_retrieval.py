"""Fixed engineering comparison; no answer-accuracy or teacher-quality claims."""
import hashlib
import json
import statistics
import time
from course_data import PRIVATE,load
from learning_engine import retrieve


def evaluate():
    path=PRIVATE/'retrieval-eval.json';raw=path.read_bytes();cases=json.loads(raw)['cases']
    results=[];summaries=[]
    retrieve('样本空间如何列出','hybrid') # Explicit warmup; timings below exclude first model load.
    for mode in ['bm25','hybrid','adaptive']:
        for case in cases:
            start=time.monotonic();r=retrieve(case['question'],mode);elapsed=time.monotonic()-start
            ranked=[q['id'] for q in r['matches']];target=case['target_exercise']
            found={c['id'] for c in r['concepts']};expected=set(case['expected_concepts'])
            results.append({'case_id':case['id'],'split':case['split'],'mode':mode,'ranked':ranked,
                            'target':target,'reciprocal_rank':1/(ranked.index(target)+1) if target in ranked else 0,
                            'concept_coverage':len(found&expected)/len(expected) if expected else None,
                            'route':r['route'],'route_expected':case['expected_route'],
                            'route_correct':r['route']==case['expected_route'] if case['expected_route'] else None,
                            'semantic_used':r.get('semantic',{}).get('used',False),'seconds':round(elapsed,4)})
        for split in ['dev','holdout']:
            group=[r for r in results if r['mode']==mode and r['split']==split]
            anchors=[r for r in group if r['target']];concepts=[r['concept_coverage'] for r in group if r['concept_coverage'] is not None]
            routes=[r for r in group if r['route_expected']]
            times=sorted(r['seconds'] for r in group)
            summaries.append({'mode':mode,'split':split,'cases':len(group),'anchor_cases':len(anchors),
                'anchor_recall_at_3':sum(r['reciprocal_rank']>0 for r in anchors)/len(anchors),
                'mrr_at_3':sum(r['reciprocal_rank'] for r in anchors)/len(anchors),
                'specified_concept_coverage':statistics.mean(concepts),
                'explicit_route_cases':len(routes),'explicit_route_accuracy':sum(r['route_correct'] for r in routes)/len(routes),
                'warm_retrieval_median_seconds':statistics.median(times),'warm_retrieval_p95_seconds':times[max(0,int(len(times)*.95)-1)]})
    output=PRIVATE/'evaluation';output.mkdir(exist_ok=True)
    report={'dataset_sha256':hashlib.sha256(raw).hexdigest(),'corpus_sha256':load()['corpus_sha256'],
            'cases':len(cases),'summaries':summaries,'results':results,
            'limitations':['Assistant labels, not independent teacher gold','Small engineering smoke set','No LLM answer accuracy, citation entailment or tutoring-outcome evaluation','Adaptive currently uses explicit rules, not a trained complexity classifier','No before/after improvement claim is pre-assumed']}
    (output/'retrieval-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'dataset_sha256':report['dataset_sha256'],'summaries':summaries},ensure_ascii=False,indent=2));return report


if __name__=='__main__':evaluate()
