"""Local source-location development checks for question correspondence; no LLM calls."""
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path

from full_book_tutor import retrieve
from evaluate_formula_retrieval import CASES
from exercise_vectors import status
from external_question_bank import BASE


def run():
    rows=[]
    for identifier,query,expected in CASES:
        result=retrieve(query);ids=[h['id'] for h in result['hits']]
        rows.append({'id':identifier,'query':query,'expected_source_record':expected,
                     'source_rank':ids.index(expected)+1 if expected in ids else None,'result':result})
    anchor_rows=[]
    for c in json.loads((BASE/'source-anchor-labels.json').read_text(encoding='utf-8'))['cases']:
        result=retrieve(c['query']);ids=[h['id'] for h in result['hits']]
        anchor_rows.append({'id':c['case_id'],'expected_source_record':c['expected_record'],
                            'source_rank':ids.index(c['expected_record'])+1 if c['expected_record'] in ids else None,
                            'result':result})
    stamp=datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d-%H%M%S')
    out=Path(__file__).resolve().parent/'data/private/correspondence-20261104'/('run-'+stamp)
    out.mkdir(parents=True,exist_ok=False)
    info=status()
    report={'date':'2026-11-04','collection_sha256':info['collection_sha256'],'cases':rows,
            'source_top1_development':sum(r['source_rank']==1 for r in rows),
            'external_source_anchors':anchor_rows,
            'external_anchor_top1_development':sum(r['source_rank']==1 for r in anchor_rows),
            'cases_with_both_practice_types':sum(all(r['result']['practice_groups'].get(k) for k in ['exercise','example']) for r in rows),
            'knowledge_labels_human_reviewed':0,'generation_api_calls':0,
            'code_sha256':{name:hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in
                           ['full_book_tutor.py','problem_correspondence.py','formula_retrieval.py','problem_study.js']},
            'boundary':'Six previously exposed source-location development variants. Type coverage is not relevance. Topic clues are not teacher labels or student mastery diagnosis.'}
    (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'report':str(out/'report.json'),'source_top1_development':report['source_top1_development'],
                      'external_anchor_top1_development':report['external_anchor_top1_development'],
                      'both_practice_types':report['cases_with_both_practice_types'],'generation_api_calls':0},ensure_ascii=False))
    return report


if __name__=='__main__':run()
