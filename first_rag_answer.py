"""Prepare one reproducible smoke case; only --live sends textbook excerpts."""
import argparse
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import uuid
from full_book_tutor import retrieve
from rag_generation import evidence_for,payload,generate
from tutor_provider import status

ROOT=Path(__file__).resolve().parent
QUESTION='独立同分布样本来自均匀总体U(0,θ)，观测值为1、3、2、4。求θ的最大似然估计，并说明似然函数的参数取值范围。'


def run(live=False):
    state=status()
    if live and not (state['enabled'] and state['configured']):raise ValueError('模型尚未配置，未发送请求；先运行configure_model.ps1')
    result=retrieve(QUESTION,kind='example',chapter='6');evidence=evidence_for(result)
    report={'created_at':datetime.now(timezone(timedelta(hours=8))).isoformat(),
            'purpose':'known-source development smoke test, not an independent benchmark',
            'question':QUESTION,'evidence':evidence,
            'request_payload':payload(QUESTION,evidence,'solution',state['model'] or '<configure-model>'),
            'expected_checks':['四个观测值的最大值为4','似然函数在θ≥4时为θ的负四次方，在不满足支持条件时为0',
                               '最大似然估计为4；应说明支持边界，不能只对参数求导令零'],
            'gold_basis':'assistant-authored arithmetic/likelihood check; pending independent human review',
            'human_review':{'mathematical_correctness':None,'source_support':None,'notes':''}}
    report['generation']=generate(QUESTION,evidence,'solution') if live else {'used':False,'status':'prepared_only','live_call_verified':False}
    folder=ROOT/'data/private/first-rag-answer'/uuid.uuid4().hex[:12];folder.mkdir(parents=True,exist_ok=True)
    target=folder/'result.json';target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':report['generation']['status'],'live_call_verified':report['generation']['live_call_verified'],'report':str(target)},ensure_ascii=False,indent=2))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--live',action='store_true',help='Call the configured model, sending this question and selected textbook excerpts.')
    args=parser.parse_args()
    try:run(args.live)
    except ValueError as error:parser.exit(1,str(error)+'\n')
