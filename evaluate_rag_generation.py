"""Prepare or explicitly run paired no-retrieval/fixed/adaptive RAG comparisons."""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import time
import uuid
from exercise_vectors import status as index_status
from full_book_tutor import retrieve
from prepare_acceptance_review import CASES
from rag_generation import evidence_for, payload, generate
from tutor_provider import status as model_status

ROOT=Path(__file__).resolve().parent


def prepare_arms(question):
    adaptive=retrieve(question)
    # Share the clarification guard across arms: this comparison isolates
    # evidence provision rather than granting only one arm a safety prompt.
    if adaptive['status']=='needs_problem_context':
        return {name:{'status':'clarify_before_generation','message':adaptive['message'],
                      'clarifications':adaptive['clarifications'],'evidence':[]}
                for name in ['no_retrieval','fixed_rag','adaptive_rag']}
    plain=retrieve(question,adaptive=False)
    return {'no_retrieval':{'status':'ready','evidence':[]},
            'fixed_rag':{'status':'ready','evidence':evidence_for(plain),'route':plain['route']},
            'adaptive_rag':{'status':'ready','evidence':evidence_for(adaptive),'route':adaptive['route']}}


def run(dataset=None,live=False):
    if dataset:
        data=json.loads(Path(dataset).read_text(encoding='utf-8'))
    else:
        data={'label_status':'assistant_authored_development_cases_not_independent',
              'cases':[{'id':row[0],'question':row[1],'reference_answer':None} for row in CASES]}
    if not isinstance(data.get('cases'),list) or not 1<=len(data['cases'])<=100:raise ValueError('需要1–100条评测输入')
    model=model_status()
    if live and not (model['enabled'] and model['configured']):raise ValueError('请先在本机启用并配置模型；未发起真实调用')
    info=index_status();folder=ROOT/'data/private/generation-evaluation'/('run-'+uuid.uuid4().hex[:12]);folder.mkdir(parents=True)
    report={'created_at':datetime.now(timezone(timedelta(hours=8))).isoformat(),
            'mode':'live' if live else 'prepared_only','model':model['model'],
            'collection_sha256':info['collection_sha256'],'source_sha256':info['source_sha256'],
            'dataset_sha256':hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),
            'dataset_label_status':data.get('label_status','unspecified_pending_review'),
            'controls':{'temperature':0,'max_tokens':1800,'stage':'solution','same_model_for_all_arms':True,
                        'shared_clarification_guard':True},'cases':[],
            'boundary':'Preparation is not a successful model call. Human answer correctness and citation entailment are never inferred from citation IDs.'}
    for case in data['cases']:
        question=case['question'];arms=prepare_arms(question)
        item={'id':case['id'],'question':question,'reference_answer':case.get('reference_answer'),'arms':{}}
        # Rotate arm order across cases to reduce a fixed ordering confound.
        order=list(arms);shift=len(report['cases'])%len(order);order=order[shift:]+order[:shift]
        for name in order:
            arm=arms[name];entry={**arm,'human_review':{'correctness':None,'conditions':None,
                'citation_support':None,'teaching_usefulness':None,'notes':''}}
            if arm['status']=='ready':
                entry['request_payload']=payload(question,arm['evidence'],'solution',model['model'] or '<configure-model>')
                if live:
                    started=time.monotonic()
                    entry['generation']=generate(question,arm['evidence'],'solution',allow_no_evidence=name=='no_retrieval')
                    entry['elapsed_seconds']=round(time.monotonic()-started,3)
                else:entry['generation']={'used':False,'status':'prepared_only','live_call_verified':False}
            item['arms'][name]=entry
        report['cases'].append(item)
        (folder/'comparison.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(case['id'], 'prepared' if not live else 'completed',flush=True)
    print(folder/'comparison.json')
    return report,folder


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--dataset');parser.add_argument('--live',action='store_true',
        help='Actually call the configured provider; incurs provider usage and sends each question with selected excerpts.')
    args=parser.parse_args();run(args.dataset,args.live)
