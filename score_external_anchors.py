"""Exact source-location checks against explicit cross-book references, not novel QA."""
import argparse
import hashlib
import json
from pathlib import Path
from external_question_bank import BASE, write_json
from evaluate_external_retrieval import ARMS


def run(report_path):
    report_path=Path(report_path);report=json.loads(report_path.read_text(encoding='utf-8'))
    label_path=BASE/'source-anchor-labels.json';labels=json.loads(label_path.read_text(encoding='utf-8'))
    cases={c['case_id']:c for c in report['cases']};details=[]
    for gold in labels['cases']:
        actual=cases.get(gold['case_id'])
        if not actual or len(actual['arms'])!=4:continue
        if actual['question_text_sha256']!=gold['text_sha256'] or actual['query']!=gold['query']:
            raise ValueError('Question/query changed after source review')
        arms={}
        for name in ARMS:
            ids=[h['id'] for h in actual['arms'][name]['hits']]
            rank=ids.index(gold['expected_record'])+1 if gold['expected_record'] in ids else None
            arms[name]={'rank_at_8':rank,'returned_ids':ids}
        details.append({**gold,'arms':arms})
    summary={}
    for name in ARMS:
        ranks=[r['arms'][name]['rank_at_8'] for r in details]
        summary[name]={'cases':len(ranks),'hit_at_1':sum(r==1 for r in ranks),
                       'hit_at_5':sum(r is not None and r<=5 for r in ranks),
                       'hit_at_8':sum(r is not None for r in ranks),
                       'mrr_at_8':round(sum(1/r for r in ranks if r)/len(ranks),4) if ranks else None}
    result={'source_labels_sha256':hashlib.sha256(label_path.read_bytes()).hexdigest(),
            'retrieval_report_sha256':hashlib.sha256(report_path.read_bytes()).hexdigest(),
            'summary':summary,'details':details,'teacher_reviewed':False,
            'boundary':labels['boundary'],'label_timing':labels['label_timing']}
    target=report_path.with_name('source-anchor-metrics.json');write_json(target,result)
    print(json.dumps(summary,ensure_ascii=False));return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('report');run(p.parse_args().report)
