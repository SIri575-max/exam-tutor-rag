"""Score manual question-ID judgments without treating unjudged items as wrong."""
import argparse
import hashlib
import json
from pathlib import Path
from retrieval_metrics import evaluate


def run(source, destination):
    path=Path(source);raw=path.read_bytes();data=json.loads(raw)
    results=[]
    for case in data['cases']:
        if type(case.get('positive_set_complete')) is not bool:
            raise ValueError('Each case must explicitly declare positive_set_complete')
        grades=case['grades']
        for method,ids in case['predictions'].items():
            for k in [1,3,5]:
                results.append({'case_id':case['id'],'method':method,
                                **evaluate(ids,grades,k,positive_set_complete=case['positive_set_complete'])})
    summary={}
    for method in sorted({r['method'] for r in results}):
        summary[method]={}
        for k in [1,3,5]:
            rows=[r for r in results if r['method']==method and r['k']==k]
            summary[method][str(k)]={}
            for metric in ['hit_at_k','precision_at_k','recall_at_k','reciprocal_rank_at_k','annotated_positive_coverage_at_k']:
                values=[r[metric] for r in rows if r[metric] is not None]
                summary[method][str(k)][metric]={'mean':sum(values)/len(values) if values else None,
                                              'scored_cases':len(values),'total_cases':len(rows)}
    report={'input_sha256':hashlib.sha256(raw).hexdigest(),'summary':summary,'details':results,
            'generation_api_calls':0,'boundary':'Means include only scoreable cases; inspect denominators. Incomplete judgments are not a complete relevance benchmark.'}
    Path(destination).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'report':str(destination),'cases':len(data['cases']),'summary':summary},ensure_ascii=False))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('source');parser.add_argument('destination')
    args=parser.parse_args();run(args.source,args.destination)
