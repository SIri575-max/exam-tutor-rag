"""Finish one local OCR batch's dataset/retrieval reports. Never calls paid model APIs."""
import argparse
import json
import time

from external_question_bank import BASE, write_json


def run(wait=False):
    state=BASE/'completion-status.json'
    while True:
        progress=json.loads((BASE/'progress.json').read_text(encoding='utf-8'))
        if progress['status']=='complete_unreviewed' and progress['completed_pages']==progress['total_pages']:break
        if progress['status']=='incomplete_with_errors':raise ValueError('OCR incomplete; inspect failed pages before freezing')
        if not wait:raise ValueError('Full OCR still running; rerun after completion or pass --wait-for-ocr')
        write_json(state,{'stage':'waiting_for_ocr','completed_pages':progress['completed_pages'],
                          'total_pages':progress['total_pages'],'llm_calls':0})
        print('waiting for OCR',progress['completed_pages'],'/',progress['total_pages'],flush=True)
        time.sleep(30)
    write_json(state,{'stage':'building_dataset','llm_calls':0})
    from build_external_evaluation import build
    build()
    write_json(state,{'stage':'running_retrieval_baselines','llm_calls':0})
    from evaluate_external_retrieval import run as retrieval_run
    report,folder=retrieval_run()
    from score_external_anchors import run as anchors_run
    anchors_run(folder/'report.json')
    from score_external_relevance import run as label_template
    if not (folder/'teacher-label-template.json').exists():label_template(folder/'report.json')
    from write_external_audit import write_report
    document=write_report(BASE/'objective-pilot/run-0b83d2f1ea83/report.json',folder/'report.json')
    write_json(state,{'stage':'complete_pending_teacher_review','llm_calls':0,
                      'ocr_pages':progress['completed_pages'],'retrieval_cases':len(report['cases']),
                      'retrieval_report':str(folder/'report.json'),'research_document':str(document),
                      'boundary':'OCR and retrieval complete; mathematical accuracy/relevance human labels still pending.'})
    print(state,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--wait-for-ocr',action='store_true')
    run(p.parse_args().wait_for_ocr)
