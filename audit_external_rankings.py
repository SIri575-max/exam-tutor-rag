"""Compare frozen retrieval snapshots; rank stability is not correctness."""
from collections import Counter
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path

from external_question_bank import BASE, ROOT, write_json
from external_review import source_checks, development_ids

OLD='4d3ad059a2d51335'
NEW='f9142a446db0c345'
EXPECTED={OLD:'f0c90a3012a8c7609348d689468429c865d477478e4bd435c1b16fb0b6a07867',
          NEW:'178d3421dbc47f2c93a5161f87f9d038b53cf4a50a6f3d8e41d8e18293a4154a'}


def compare(old,new,dev):
    before={c['case_id']:c for c in old['cases']};after={c['case_id']:c for c in new['cases']}
    if set(before)!=set(after):raise ValueError('Case sets differ')
    rows=[];summary={arm:Counter() for arm in ['bm25','vector','hybrid','adaptive_rag']}
    for identifier,c in after.items():
        prev=before[identifier]
        if (prev['query'],prev['source_pages'])!=(c['query'],c['source_pages']):raise ValueError('Frozen query changed')
        arms={}
        for arm in summary:
            a=prev['arms'][arm];b=c['arms'][arm]
            left=[h['id'] for h in a.get('hits',[])];right=[h['id'] for h in b.get('hits',[])]
            top1=(left or [None])[0]!=(right or [None])[0]
            ordered=left!=right;pool=set(left)!=set(right)
            summary[arm].update(cases=1,top1_changed=int(top1),order_changed=int(ordered),
                                pool_changed=int(pool),recovered_empty=int(not left and bool(right)),
                                newly_empty=int(bool(left) and not right))
            arms[arm]={'top1_changed':top1,'order_changed':ordered,'pool_changed':pool,
                       'old_ids':left,'new_ids':right,'old_route':a.get('route'),'new_route':b.get('route')}
        rows.append({'case_id':identifier,'chapter':c['chapter'],'source_pages':c['source_pages'],
                     'development':identifier in dev,'arms':arms})
    return {'summary':{k:dict(v) for k,v in summary.items()},'cases':rows}


def run():
    reports={}
    for run_id,digest in EXPECTED.items():
        path=BASE/'retrieval-runs'/run_id/'report.json';raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('Frozen report digest changed')
        reports[run_id]=json.loads(raw)
    old,new=reports[OLD],reports[NEW]
    result=compare(old,new,development_ids());cases={c['case_id']:c for c in new['cases']}
    checks=source_checks(cases)
    result.update(date='2026-10-30',created_at=datetime.now(timezone(timedelta(hours=8))).isoformat(),
                  frozen_report_sha256s=EXPECTED,source_review_hints=[{'case_id':k,'reasons':v} for k,v in checks.items() if v],
                  human_labels_created=0,generation_api_calls=0,
                  boundary='Changes and method disagreement are review signals, not error labels. No independent-test accuracy is available.')
    bychapter=[]
    for chapter in range(1,9):
        rows=[r for r in result['cases'] if r['chapter']==chapter]
        bychapter.append({'chapter':chapter,'cases':len(rows),
            'adaptive_top1_changed':sum(r['arms']['adaptive_rag']['top1_changed'] for r in rows),
            'adaptive_order_changed':sum(r['arms']['adaptive_rag']['order_changed'] for r in rows),
            'adaptive_pool_changed':sum(r['arms']['adaptive_rag']['pool_changed'] for r in rows)})
    result['by_chapter']=bychapter
    result['changed_outside_development']=[r['case_id'] for r in result['cases'] if not r['development'] and r['arms']['adaptive_rag']['top1_changed']]
    path=BASE/'analysis/ranking-stability-20261030.json';path.parent.mkdir(parents=True,exist_ok=True);write_json(path,result)
    table='\n'.join('| {chapter} | {cases} | {adaptive_top1_changed} | {adaptive_order_changed} | {adaptive_pool_changed} |'.format(**r) for r in bychapter)
    s=result['summary'];adaptive=s['adaptive_rag'];outside=len(result['changed_outside_development'])
    hints=len(result['source_review_hints'])
    doc=f'''# 660B全量排序变化与审核改进（2026-10-30）

比较同一批574道文字题的两个冻结报告，检查路由修复的影响范围。没有新增生成API调用，没有代填人工标签，也没有重新OCR或改写冻结题干。

## 排序变化

- 自适应检索首位候选改变 {adaptive['top1_changed']} 题，其中 {adaptive['recovered_empty']} 题原先没有候选；新出现空结果 {adaptive['newly_empty']} 题。
- 首位候选变化中有 {outside} 题在18道已知路由开发样本之外，仍需人工检查，不能据此称为改善或退化。
- 自适应候选顺序变化 {adaptive['order_changed']} 题，候选集合变化 {adaptive['pool_changed']} 题。
- BM25、向量、混合检索首位变化分别为 {s['bm25']['top1_changed']}、{s['vector']['top1_changed']}、{s['hybrid']['top1_changed']} 题。运行时间受到缓存等因素影响，本次不据两轮耗时宣称加速。

| 章 | 题数 | 自适应首位变化 | 顺序变化 | 集合变化 |
|---|---:|---:|---:|---:|
{table}

## 可以直接使用的审核功能

入口：http://127.0.0.1:8771/benchmark

- “题干核对线索”筛选包含 {hints} 题，来源仅为公式语法失败、已记录的否定/补事件问题和跨页条件；不是检索错误标签。
- 支持完整题干关键词搜索、已保存草稿筛选、已标注候选计数、当前筛选范围内的下一道待审核和题目链接。
- 核对线索不显示方法、名次或预设正确出处，盲评候选仍按ID排序。
- 发现OCR错误先记备注并保存草稿；冻结报告不变。通过审核仍需逐项标注、核对原页、填写题族、重合分层及审核人。

推荐先检查PDF43页第7题、PDF65页第77题和第1章第7题，再审核跨页题。之后按章节逐步审核，不能把未审核556题直接称为独立测试集。575道候选中的1道图形题不在574道文字检索报告内，本轮也未将其算作完成检索。

## 证据边界

排序稳定性不是相关性或解题准确率。有候选574/574只说明检索流程返回了结果。Recall@5/NDCG@5仍需人工标签；独立测试还需题族去重、OCR核验与开发集隔离。已有小样本生成对照未证明数学准确率提升。实际模型仍为Qwen-plus API，本机未部署Qwen。

明细：`{path}`。两份原始报告SHA-256：旧版 `{EXPECTED[OLD]}`；新版 `{EXPECTED[NEW]}`。原始报告、答案隔离区和既有人工记录均未改写。
'''
    target=ROOT.parents[1]/'research/660B全量排序核查与审核改进-2026-10-30.md'
    target.write_text(doc,encoding='utf-8')
    print(json.dumps({'analysis':str(path),'document':str(target),'summary':result['summary'],
                      'outside_development_top1_changed':outside,'source_hint_cases':hints},ensure_ascii=False))


if __name__=='__main__':run()
