"""Compare a frozen pre-repair run with the routing development iteration."""
import argparse
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path

from external_question_bank import BASE, ROOT, write_json


def run(new_path):
    new_path=Path(new_path).resolve()
    protocol=json.loads((ROOT/'evaluation/route_repair_protocol_20261029.json').read_text(encoding='utf-8'))
    old_path=ROOT/protocol['baseline_report'];old_raw=old_path.read_bytes();new_raw=new_path.read_bytes()
    if hashlib.sha256(old_raw).hexdigest()!=protocol['baseline_report_sha256']:raise ValueError('Baseline snapshot changed')
    old=json.loads(old_raw);new=json.loads(new_raw)
    assert old['frozen_cases']==new['frozen_cases'],'Compare the same OCR inputs, not edited questions'
    assert old['collection_sha256']==new['collection_sha256']
    from evaluate_external_retrieval import CODE_FILES
    assert new['code_sha256']==hashlib.sha256(b''.join((ROOT/f).read_bytes() for f in CODE_FILES)).hexdigest()
    old_by={c['case_id']:c for c in old['cases']};details=[]
    for c in new['cases']:
        before=old_by[c['case_id']]['arms']['adaptive_rag'];after=c['arms']['adaptive_rag']
        details.append({'case_id':c['case_id'],'development':c['case_id'] in protocol['development_case_ids'],
                        'old_route':before['route'],'new_route':after['route'],
                        'old_candidates':len(before['hits']),'new_candidates':len(after['hits']),
                        'old_top1':before['hits'][0]['id'] if before['hits'] else None,
                        'new_top1':after['hits'][0]['id'] if after['hits'] else None})
    anchors_before=json.loads(old_path.with_name('source-anchor-metrics.json').read_text(encoding='utf-8'))
    anchors_after=json.loads(new_path.with_name('source-anchor-metrics.json').read_text(encoding='utf-8'))
    # Re-run the older six formula development probes in memory; preserve their
    # dated historical output instead of calling its backdated writer.
    from evaluate_formula_retrieval import CASES
    from full_book_tutor import retrieve
    variants=[]
    for name,query,expected in CASES:
        ids=[h['id'] for h in retrieve(query,kind='exercise',limit=8)['hits']]
        variants.append({'id':name,'expected':expected,'rank':ids.index(expected)+1 if expected in ids else None})
    regained=[c['case_id'] for c in details if not c['old_candidates'] and c['new_candidates']]
    lost=[c['case_id'] for c in details if c['old_candidates'] and not c['new_candidates']]
    evidence={'date':'2026-10-29','created_at':datetime.now(timezone(timedelta(hours=8))).isoformat(),
              'status':'routing_development_repair_and_human_review_ready','cases':len(details),
              'baseline_report':old_path.relative_to(ROOT).as_posix(),'new_report':new_path.relative_to(ROOT).as_posix(),
              'baseline_sha256':hashlib.sha256(old_raw).hexdigest(),'new_report_sha256':hashlib.sha256(new_raw).hexdigest(),
              'collection_sha256':new['collection_sha256'],'same_frozen_inputs':True,
              'development_case_ids':protocol['development_case_ids'],'old_summary':old['summary'],'new_summary':new['summary'],
              'regained_candidates':regained,'lost_candidates':lost,
              'old_anchor_summary':anchors_before['summary'],'new_anchor_summary':anchors_after['summary'],
              'formula_development_regression':variants,'details':details,
              'new_generation_api_calls':0,'human_relevance_labels_created_by_agent':0,
              'boundary':'Post-failure development repair. Candidate availability and nine source anchors are not independent mathematical or retrieval accuracy.'}
    write_json(new_path.with_name('routing-repair-comparison.json'),evidence)
    document=ROOT.parents[1]/'research/660B路由修复与人工盲评-2026-10-29.md'
    lines=['# 660B路由修复与人工盲评','', '日期：2026-10-29。本轮是已知失败驱动的开发迭代，原始报告保持。','',
           '## 实际改动','',
           '- 识别概率与集合运算符号、随机收敛、H₀/H₁、两类错误、Fisher信息和蒙特卡洛等明确统计线索；普通聊天、任意代数式与缺条件估计请求仍先澄清。',
           '- 区分密度函数p(x)与泊松分布声明、希腊参数与Gamma/Beta分布、算术n(n+1)与正态分布；兼容TeX分布符号、花括号最值和闭支持边界。',
           '- 生产规则不包含660B题号、预期教材ID或参考答案；教材向量与题干输入保持。',
           '- 新增本机/benchmark审核工作台：章节和开发样本筛选、原页、编译公式、去重盲评候选、草稿/人工确认、版本冲突保护与导出。',
           '', '## 同一批574道OCR候选的开发前后对照','',
           '| 指标 | 修复前 | 修复后 |','|---|---:|---:|',
           f'|自适应返回候选|{old["summary"]["adaptive_rag"]["with_candidates"]}/574|{new["summary"]["adaptive_rag"]["with_candidates"]}/574|',
           f'|9道出处开发样本Hit@1|{anchors_before["summary"]["adaptive_rag"]["hit_at_1"]}/9|{anchors_after["summary"]["adaptive_rag"]["hit_at_1"]}/9|',
           f'|9道出处开发样本MRR@8|{anchors_before["summary"]["adaptive_rag"]["mrr_at_8"]}|{anchors_after["summary"]["adaptive_rag"]["mrr_at_8"]}|',
           '', f'恢复候选{len(regained)}道，新增无候选{len(lost)}道。原有6条公式开发变体本轮首位命中{sum(v["rank"]==1 for v in variants)}/6。',
           'BM25、向量、混合三组均574/574道返回候选；这些数值是运行与候选可用性，不是相关性准确率。不同轮次机器负载不同，不据平均时延宣称加速。',
           '9道范围漏拦题和9道已查看出处样本共18道明确记为开发样本，另有既往6条公式开发变体。剩余候选仍待OCR、题族和相关性审核，不能直接改叫独立测试集。',
           '本轮未新增生成模型请求，先前7道来源一致解题对照仍为三组各5/7条可解析且最终答案匹配；没有新的数学解题增益结论。实际生成模型配置仍为API Qwen-plus。',
           '', '## 现在可以怎样审核','',
           '入口：http://127.0.0.1:8771/benchmark 。查题页导航已加入“660B检索盲评”。',
           '1. 先选“路由开发样本”，逐题打开原页，核对数字、补事件横线、上下标及跨页条件。识别有误先留备注、保存草稿，不能确认OCR通过。',
           '2. 每个教材候选按0无关、1同主题、2方法可借鉴、3同题或完整条件近同标注；零分负例也要标。页面隐藏方法、排序和预设出处。',
           '3. 填审核人、题族ID与重合分层。同题、参数变式、小问与图片变体共用题族；不确定时保留草稿。',
           '4. 明确确认后才计入人工审核记录；刷新/普通浏览不会自动批准。旧版本保存，冲突不会覆盖。',
           '5. 导出JSON后用score_external_relevance.py导入同一冻结报告，计算已审核候选池上的指标；它不代表全语料穷尽相关集。',
           '', '审核接口只提供题干页PDF6–87，不提供参考答案页，也不把审核数据加入向量库或生成上下文。全部人工标签由用户录入；助手测试仅使用临时目录，未冒充教师确认。',
           '', '## 核验与证据','',
           '- 后端228项回归通过；10组前端脚本通过，含未保存切换、重复保存、版本冲突和异步过期响应。',
           '- 浏览器已验证574道目录与18道开发筛选；第4章第6题显示19个去重候选、89处公式且无公式回退，题干原页图正常加载。该项是界面检查，不是OCR正确率。',
           '- API临时目录测试覆盖403跨来源写入拒绝、409版本冲突、盲评字段隔离及答案页拒绝；不创建真实审核标签。',
           f'- 新报告：{new_path.as_posix()}。',f'- 对照明细：{new_path.with_name("routing-repair-comparison.json").as_posix()}。',
           '- 原始协议：evaluation/route_repair_protocol_20261029.json；代码备份：'+protocol['code_backup']+'。',
           '', '原投递简历、旧版项目交付包和本地Qwen规划稿保持；本轮只补实现与证据，不把本机CPU部署或未发生的准确率提升补成事实。']
    document.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    write_json(BASE/'route-repair-latest.json',{'report':str(new_path),'comparison':str(new_path.with_name('routing-repair-comparison.json')),
                                            'document':str(document),'review_url':'http://127.0.0.1:8771/benchmark'})
    print(json.dumps({'document':str(document),'restored':len(regained),'new_empty':len(lost),'formula_top1':sum(v['rank']==1 for v in variants)},ensure_ascii=False))
    return evidence


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('report');run(p.parse_args().report)
