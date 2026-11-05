"""Import explicit human relevance grades; never use model scores as gold labels."""
import argparse
import hashlib
import json
import math
from pathlib import Path


def score_case(case, review, k=5):
    if review.get('status') != 'approved' or not str(review.get('reviewer', '')).strip():
        return {'status':'pending_review','metrics':None}
    if review.get('ocr_checked') is not True or not isinstance(review.get('family_id'),str) or not review['family_id'].strip() or review.get('overlap_stratum') not in {'exact_textbook_duplicate','parameter_or_wording_variant','related_concept_new_problem','outside_current_scope'}:
        raise ValueError('Approved review requires OCR, family and overlap-stratum checks')
    labels=review.get('grades',{})
    if not isinstance(labels,dict) or any(type(v) is not int or not 0<=v<=3 for v in labels.values()):
        raise ValueError('Grades must be integers 0..3')
    pool={h['id'] for arm in case['arms'].values() for h in arm.get('hits',[])}
    if set(labels)!=pool:raise ValueError('Label exactly the pooled candidates, including negatives')
    positives={r for r,v in labels.items() if v>=2}
    ideal=sorted(labels.values(),reverse=True)[:k]
    idcg=sum((2**grade-1)/math.log2(i+2) for i,grade in enumerate(ideal))
    metrics={}
    for name,arm in case['arms'].items():
        ids=[h['id'] for h in arm.get('hits',[])][:k]
        dcg=sum((2**labels.get(r,0)-1)/math.log2(i+2) for i,r in enumerate(ids))
        metrics[name]={'hit_at_5':bool(set(ids)&positives) if positives else None,
                       'pooled_recall_at_5':len(set(ids)&positives)/len(positives) if positives else None,
                       'pooled_ndcg_at_5':dcg/idcg if idcg else None,
                       'empty_retrieval':not ids}
    return {'status':'reviewed','reviewer':review['reviewer'],'family_id':review['family_id'],
            'overlap_stratum':review['overlap_stratum'],'split':review.get('split','quarantine'),
            'relevant_pool_size':len(positives),'metrics':metrics,
            'boundary':'Recall and NDCG use the judged candidate pool, not exhaustive corpus relevance.'}


def template(report):
    return {'report_sha256':None,'boundary':'Fill manually, approve only after checking question, candidates and source pages.',
            'cases':[{'case_id':c['case_id'],'status':'pending','reviewer':'','ocr_checked':False,
                      'family_id':None,'overlap_stratum':None,'split':'quarantine',
                      'grades':{i:None for i in sorted({h['id'] for a in c['arms'].values() for h in a.get('hits',[])})},
                      'notes':''} for c in report['cases']]}


def run(report_path,review_path=None):
    report_path=Path(report_path);raw=report_path.read_bytes();report=json.loads(raw)
    digest=hashlib.sha256(raw).hexdigest()
    if review_path is None:
        data=template(report);data['report_sha256']=digest
        target=report_path.with_name('teacher-label-template.json')
        if target.exists():raise ValueError('Template already exists; preserve annotations')
    else:
        reviews=json.loads(Path(review_path).read_text(encoding='utf-8'))
        if reviews.get('report_sha256')!=digest:raise ValueError('Review refers to another report snapshot')
        keyed={r['case_id']:r for r in reviews['cases']}
        if len(keyed)!=len(reviews['cases']):raise ValueError('Duplicate reviewed case ID')
        data={'report_sha256':digest,'cases':[{'case_id':c['case_id'],**score_case(c,keyed.get(c['case_id'],{}))} for c in report['cases']]}
        data['reviewed_cases']=sum(r['status']=='reviewed' for r in data['cases'])
        target=report_path.with_name('reviewed-metrics.json')
    target.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(target)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('report');parser.add_argument('--reviews')
    args=parser.parse_args();run(args.report,args.reviews)
