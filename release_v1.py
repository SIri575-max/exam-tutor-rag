"""Build a measured V1 manifest from existing artifacts; makes no model calls."""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
from statistics import mean
from exercise_vectors import status as index_status
from tutor_provider import status as model_status
from sync_sources import ROOT
import generation_records


def generation_summary(report):
    arms={name:{'attempted':0,'accepted':0,'citation_rejected':0,'failed':0,'seconds':[]}
          for name in ['no_retrieval','fixed_rag','adaptive_rag']}
    tokens=missing=guards=0
    for case in report['cases']:
        if all(a['status']=='clarify_before_generation' for a in case['arms'].values()):guards+=1
        for name,entry in case['arms'].items():
            if 'generation' not in entry:continue
            row=arms[name];g=entry['generation'];row['attempted']+=1
            row['accepted']+=bool(g.get('used'));row['citation_rejected']+=g.get('status')=='citation_validation_failed'
            row['failed']+=not g.get('used',False)
            row['seconds'].append(entry['elapsed_seconds'])
            usage=g.get('usage',{}).get('total_tokens')
            if isinstance(usage,int):tokens+=usage
            else:missing+=1
    for row in arms.values():
        row['mean_seconds']=round(mean(row.pop('seconds')),3) if row['attempted'] else None
    return {'case_count':len(report['cases']),'clarified_cases':guards,
            'request_attempts':sum(a['attempted'] for a in arms.values()),'total_tokens':tokens,
            'token_usage_missing_requests':missing,'arms':arms,
            'mathematical_accuracy':None,'independent_teacher_review':False,
            'boundary':'Recorded token sum excludes missing usage. Accepted responses are not an answer-accuracy metric.'}


def build(comparison_path):
    comparison_path=Path(comparison_path).resolve()
    if not comparison_path.is_relative_to((ROOT/'data/private/generation-evaluation').resolve()):raise ValueError('评测必须来自本项目私有目录')
    report=json.loads(comparison_path.read_text(encoding='utf-8'))
    if report['mode']!='live':raise ValueError('准备稿不能作为真实生成交付')
    index=index_status();model=model_status()
    if report['collection_sha256']!=index['collection_sha256']:raise ValueError('评测与当前题库版本不一致')
    source=json.loads((ROOT/'data/private/full-book/question-vectors/source-location-evaluation.json').read_text(encoding='utf-8'))
    formula=json.loads((ROOT/'data/private/formula-retrieval/development-probes-2026-10-27.json').read_text(encoding='utf-8'))
    summary=generation_summary(report)
    test_path=ROOT/'data/private/v1-release/python-tests.txt'
    test_text=test_path.read_text(encoding='utf-8',errors='replace') if test_path.exists() else ''
    count=re.search(r'Ran (\d+) tests',test_text)
    nodes=ROOT/'data/private/v1-release/node-tests.txt'
    node_text=nodes.read_text(encoding='utf-8') if nodes.exists() else ''
    test_pass=bool(count and re.search(r'\nOK\s*$',test_text))
    node_pass=all(s in node_text for s in ['10 renderer checks passed','stale upload checks passed','canvas coordinate checks passed','conflict checks passed','result discard check passed'])
    saved=generation_records.recent(100)
    conditions={
        '全书题目索引与本地嵌入可用':bool(index['ready'] and index['records']==1009),
        '原题定位与公式输入对照已运行':all(v['cases']==24 for v in source['summary'].values()) and len(formula['source_anchored_development_probes'])==6,
        '真实Qwen三组对照与失败记录保留':model['enabled'] and model['configured'] and summary['request_attempts']==18 and summary['clarified_cases']==2,
        '页面真实讲解已保存并可重看':any(r['live_call_verified'] and r['status']=='generated_pending_review' for r in saved),
        '后端与前端回归检查通过':test_pass and node_pass,
    }
    result={'version':'1.0-local','date':datetime.now(timezone(timedelta(hours=8))).isoformat(),
            'status':'local_v1_complete' if all(conditions.values()) else 'building',
            'checks':[k for k,v in conditions.items() if v],'pending_checks':[k for k,v in conditions.items() if not v],
            'evaluation':summary,'comparison_report':str(comparison_path.relative_to(ROOT)),
            'comparison_sha256':hashlib.sha256(comparison_path.read_bytes()).hexdigest(),
            'retrieval_development':{'summary':source['summary'],'formula_cases':6,
                'raw_hybrid_top1':formula['raw_hybrid_top1'],'formula_top1':formula['formula_top1'],
                'label_status':'assistant_development_labels_not_independent'},
            'tests':{'python_passed':int(count.group(1)) if test_pass else None,'frontend_passed':node_pass},
            'collection_sha256':index['collection_sha256'],'model':model['model'],
            'boundaries':['本机作品集，未公开部署','OCR及知识关系候选待校对','开发样例不代表独立准确率','个人技术掌握与教师审核分别验收']}
    folder=ROOT/'data/private/v1-release';folder.mkdir(parents=True,exist_ok=True)
    (folder/'manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':result['status'],'pending_checks':result['pending_checks'],'evaluation':summary},ensure_ascii=False,indent=2))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--comparison',required=True)
    build(parser.parse_args().comparison)
