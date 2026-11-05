"""Build transparent source-review notes and a blinded review pack; no model calls."""
import argparse
import hashlib
import json
from pathlib import Path
from exercise_vectors import record
from evaluate_rag_value import ARMS,score

ROOT=Path(__file__).resolve().parent
NAMES={'no_retrieval':'无检索LLM','fixed_rag':'固定混合RAG','adaptive_rag':'规则自适应RAG'}


def build(report_path):
    path=Path(report_path).resolve();report=json.loads(path.read_text(encoding='utf-8'));folder=path.parent
    if report['mode']!='live' or len(report['cases'])!=6:raise ValueError('本审计针对完整六条真实任务')
    if any(len(c['arms'])!=3 for c in report['cases']):raise ValueError('三组响应未完成')
    unique=['S01','S02','S03','S05']
    review={'date':'2026-10-29','reviewer':'assistant_source_page_review_not_independent_teacher',
            'source_report_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'main_source_subset':unique,'main_unique_source_records':3,
            'label_amendments':[{'case':'S04','original_target':'example-6.3.5',
                'also_relevant':'example-6.3.6','basis':'教材PDF302先说明不变性，再在例6.3.6中直接应用；原标签仅接收例6.3.5过窄。',
                'timing':'post_response_source_review','main_metric_action':'exclude ambiguous case for all arms; keep original frozen report unchanged'}],
            'main_metrics':{},'amended_five_source_tasks':{},'page_anchors':[],
            'mathematical_correctness':None,'semantic_citation_entailment':None}
    for page in [294,322,335,302]:
        image=ROOT/'data/private/full-book/pages'/('pdf-'+str(page)+'.png')
        review['page_anchors'].append({'pdf_page':page,'image_sha256':hashlib.sha256(image.read_bytes()).hexdigest(),'review_status':'assistant_viewed_original_page'})
    for name in ARMS:
        entries=[c['arms'][name] for c in report['cases'] if c['id'] in unique]
        review['main_metrics'][name]={'tasks':len(entries),
            'source_location_pass':sum(e.get('score',{}).get('source_location_pass') is True for e in entries),
            'scope':'four tasks over three underlying textbook exercises, not four independent questions'}
        accepted=0
        for case in report['cases']:
            if 'expected_record' not in case:continue
            entry=case['arms'][name];answer=entry.get('answer')
            if not answer:continue
            targets=['example-6.3.5','example-6.3.6'] if case['id']=='S04' else [case['expected_record']]
            accepted+=any(score({**case,'expected_record':identifier},answer,entry['evidence'])['source_location_pass'] for identifier in targets)
        review['amended_five_source_tasks'][name]={'tasks':5,'source_location_pass':accepted,'status':'posthoc_label_amendment_not_independent_benchmark'}
    (folder/'source-review.json').write_text(json.dumps(review,ensure_ascii=False,indent=2),encoding='utf-8')
    blind=[];key=[];lines=['# 匿名回答复核包','','状态：待本人／独立教师复核。隐藏组名不保证完全盲法；回答可能带有引用线索。','',
                        '请分别检查条件、数学结论、来源相关性与引用支持，不把编号存在直接记成正确。','']
    for case in report['cases']:
        lines+=['## '+case['id'],case['question'],'']
        ordered=sorted(case['arms'],key=lambda name:hashlib.sha256((case['id']+name+report['dataset_sha256']).encode()).hexdigest())
        for n,name in enumerate(ordered,1):
            entry=case['arms'][name];identifier=case['id']+'-'+str(n)
            answer=entry.get('answer',{});text=answer.get('answer',entry.get('raw_response',entry['status']))
            blind.append({'response_id':identifier,'case_id':case['id'],'question':case['question'],'answer':answer or {'raw_response':text},
                          'review':{'status':'pending','conditions_correct':None,'mathematical_correctness':None,
                                    'source_relevant':None,'citation_support':None,'usefulness':None,'notes':''}})
            key.append({'response_id':identifier,'arm':name})
            lines+=['### 回答 '+identifier,text,'','出处字段：`'+json.dumps(answer.get('sources',[]),ensure_ascii=False)+'`','',
                    '- 条件是否一致：待评','- 数学结论是否正确：待评','- 来源是否相关／支持结论：待评','- 是否适合教学使用：待评','']
    (folder/'blind-review.json').write_text(json.dumps(blind,ensure_ascii=False,indent=2),encoding='utf-8')
    (folder/'blind-key.json').write_text(json.dumps(key,ensure_ascii=False,indent=2),encoding='utf-8')
    (folder/'blind-review.md').write_text('\n'.join(lines),encoding='utf-8')
    s=report['summary'];m=review['main_metrics']
    lines=['# RAG来源价值补测：结果与边界','','2026-10-29。Qwen-plus API版，未使用本地Qwen。6条输入×3组，共18次真实请求。',
           '模型、系统提示、temperature=0、max_tokens=900保持一致，轮换请求顺序，不自动重试。问题与原始标签在首次响应前保存。','',
           '## 来源依赖任务与通用计算分别报告','',
           '主表使用4条无歧义来源任务，覆盖3道原题（同一道题的改写查询和错误前提核对分列），不是4道独立试题。','',
           '| 方法 | 正确题号＋PDF页码 | 通用MLE数值控制 | 全部来源声明中页码错误／不可核验 | 平均请求秒数 | 已记录tokens |',
           '| --- | --- | --- | --- | --- | --- |']
    for name in ARMS:
        row=s[name];lines.append(f"| {NAMES[name]} | {m[name]['source_location_pass']}/4 | {row['numeric_control_pass']}/1 | {row['unverifiable_or_wrong_source_claims']}/{row['source_claims']}条 | {row['mean_seconds']} | {row['tokens_recorded']} |")
    lines+=['','## 标签复核修订：完整保留原始结果','',
            'S04询问直接讲解MLE不变性的原例。冻结标签只接收例6.3.5；复核PDF302页发现，例6.3.6直接应用该性质，同样可作为相关来源。',
            '因此主表对所有组排除S04；原始report.json的单一目标分数不改。若事后接受两个相关来源，五条来源任务中无检索为0/5、固定RAG为3/5、自适应RAG为4/5；该修订口径只能作为开发分析，不能包装成独立测试成绩。','',
            '## 实际案例','',
            '- S02：无检索声称教材没有该负二项共轭先验习题；原书PDF322页明确存在习题6.5第13题。两种RAG均返回正确题号、页码。',
            '- S05：无检索虽否定Transformer前提，却把习题6.1第6题说成充分统计量题，报PDF228页；原页PDF294表明其为均匀总体无偏估计有效性比较。RAG正确定位。',
            '- S01：自然语言“最大值／最小值”描述使固定和自适应检索均漏掉题目；模型没有获得相应证据，未能定位。失败保留，未在本轮中途调规则。',
            '- S04：固定检索虽把相关原例排到候选第4，但上下文只选前3题，导致生成看不到不变性段落；自适应性质查找将原段落送入上下文，返回例6.3.6／PDF302。',
            '- S06：三组均算出MLE=4，单条控制未体现RAG的数学解题收益。','',
            '## 这些结果不能证明什么','',
            '不能证明总体数学准确率、真实学生效果或独立泛化，也不能把本次结果归给尚未部署的本地Qwen。来源字段评分不覆盖answer文本中的全部事实，页码正确也不代表内容支持数学结论。',
            'RAG本轮增加了输入用量和平均时延；没有提速或降本结论。样例由助手据已知来源编写，S04有事后标签复核，需冻结后由独立人员补充真实新题再评。','',
            '## 下一步可执行复核','',
            'blind-review.md／json包含隐藏组名的原始回答及空白审核栏；blind-key.json单独保存组别。请本人或教师逐项核对条件、数学与引用支持，审核结果不能从现有引用编号自动生成。',
            '正式扩大为30–50条真实新题时，按来源题目分组，避免同一原题的改写同时进入开发与测试；先冻结标注和代码，再评检索覆盖、引用支持、数学正确性与成本。']
    (folder/'summary.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps({'report':str(folder/'summary.md'),'main_source_metrics':m,'review_pending_responses':len(blind),'original_report_unchanged':True},ensure_ascii=False,indent=2))
    return review


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('report');args=parser.parse_args();build(args.report)
