"""Export ungraded development pools; never turn source IDs into teacher labels."""
import hashlib
import json
from pathlib import Path
from exercise_vectors import snapshot

ROOT=Path(__file__).resolve().parent
BASE=ROOT/'data/private/chunk-topk-20261105'


def run():
    measured=BASE/'candidate-113902/report.json'
    report=json.loads(measured.read_text(encoding='utf-8'))
    source=ROOT/'data/private/correspondence-study-20261104/frozen-source-queries.json'
    raw=source.read_bytes();assert hashlib.sha256(raw).hexdigest()==report['dataset_sha256']
    queries={c['id']:c for c in json.loads(raw)['cases']};records=snapshot()[1]
    by_method={m:{r['case_id']:r for r in rows} for m,rows in report['details'].items()}
    # The 20/20 sweep supplies up to five final recommendations per kind.
    sweep=next(s for s in report['budget_sweeps'] if s['budget']['recall_k']==20 and s['budget']['typed_lexical_k']==20)
    by_method['correspondence_top5']={r['case_id']:r for r in sweep['details']}
    cases=[]
    for identifier,c in queries.items():
        predictions={m:rows[identifier]['returned_ids'] for m,rows in by_method.items()}
        pool=sorted({i for ids in predictions.values() for i in ids})
        cases.append({'id':identifier,'query':c['query'],'kind':c['kind'],'positive_set_complete':False,
                      'grades':{i:None for i in pool},'predictions':predictions,
                      'candidates':[{k:records[i][k] for k in ['id','kind','label','question_text','pages']} for i in pool],
                      'reviewer':None,'notes':None})
    target=BASE/'relevance-review-template.json'
    if target.exists():raise FileExistsError('Do not overwrite manual review work')
    value={'date':'2026-11-05','status':'ungraded_development_pool','source_proxy_dataset_sha256':report['dataset_sha256'],
           'measurement_sha256':hashlib.sha256(measured.read_bytes()).hexdigest(),
           'relevance_protocol':'evaluation/题目相关性评测协议.json','cases':cases,
           'boundary':'Known-source development paraphrases; source truth omitted from grade fields. All judgments start null. Not an independent benchmark or completed blind review.'}
    target.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'template':str(target),'cases':len(cases),'judgments':sum(len(c['grades']) for c in cases),'human_grades':0},ensure_ascii=False))


if __name__=='__main__':run()
