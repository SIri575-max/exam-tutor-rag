"""Publish reproducible local evaluation notes without overstating unfinished labels."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import re

from external_question_bank import BASE, ROOT, write_json


def objective_audit(report_path):
    raw = report_path.read_bytes(); report = json.loads(raw)
    rows=[]; key=[]; diagnostics=[]
    for case in report['cases']:
        for arm, response in case['arms'].items():
            rows.append({'case_id':case['id'],'question':case['question'],
                         'response':response.get('raw_response'), 'status':response['status'],
                         'reasoning_correctness':None,'citation_support':None,'teacher_final_answer':None,'notes':''})
            key.append(arm)
            if response['status']!='parsed':
                text=response.get('raw_response','')
                fraction=re.search(r'"final_answer"\s*:\s*(-?\d+)\s*/\s*(\d+)',text)
                kind='unclassified_request_or_format_failure'
                if fraction:kind='fraction_literal_is_invalid_json_number'
                elif text and not text.rstrip().endswith('}'):kind='incomplete_json_response'
                diagnostics.append({'case_id':case['id'],'arm':arm,'kind':kind,
                                    'strict_result_preserved':True,'posthoc_math_credit_awarded':False})
    permutation=list(range(len(rows)));random.Random(20261029).shuffle(permutation)
    blind=[];mapping=[]
    for j,i in enumerate(permutation):
        ident=f'B{j+1:02}';blind.append({'blind_id':ident,**rows[i]})
        mapping.append({'blind_id':ident,'case_id':rows[i]['case_id'],'arm':key[i]})
    folder=report_path.parent
    write_json(folder/'blind-math-review.json',blind);write_json(folder/'blind-key.json',mapping)
    write_json(folder/'format-failure-audit.json',{'original_report_sha256':hashlib.sha256(raw).hexdigest(),
               'failures':diagnostics,'boundary':'Post-response format diagnosis only; original scores unchanged.'})
    return report,diagnostics


def write_report(objective_path, retrieval_path=None):
    objective,failures=objective_audit(Path(objective_path))
    audit_path=BASE/'dataset/audit.json'
    bank=json.loads(audit_path.read_text(encoding='utf-8'))
    syntax_path=BASE/'dataset/math-syntax-audit.json'
    syntax=json.loads(syntax_path.read_text(encoding='utf-8')) if syntax_path.exists() else None
    retrieval=json.loads(Path(retrieval_path).read_text(encoding='utf-8')) if retrieval_path else None
    arms=['no_retrieval','fixed_rag','adaptive_rag']
    names={'no_retrieval':'纯模型','fixed_rag':'固定混合RAG','adaptive_rag':'规则自适应RAG'}
    lines=['# 660B外部题库与RAG评测记录','', '日期：2026-10-29。私人学习/作品集验证材料，原始PDF和答案不公开。','',
           '## 当前实际完成情况','',
           f'- 来源146页，已完成本地OCR {bank["completed_ocr_pages"]}页；题干扫描范围PDF6–87，参考答案范围PDF88–146。章节首页已对照原页，不能统一减固定偏移得到印刷页码。',
           f'- 已识别题目候选{bank["question_candidates"]}条，教师审核{bank["reviewed_questions"]}条；“660B”是资料名，不直接等于已验证的题数。',
           '- 题库仅放在data/private/660b-evaluation；现有教材向量库保持不变。参考答案单独封存，不进入查题、改写或模型上下文。',
           '- 新增本地OCR断点续跑、跨页切题、合并段落切分、漏号检查、教材重合候选、四种检索对照和盲评模板。',
           '', '逐章主编号候选数：'+ '、'.join(f'第{k}章{v["candidates"]}道' for k,v in bank['chapters'].items())+'。小问未另计；题号无缺号/重号也不能证明全部公式或题干识别正确。',
           '', '## 八章客观题对照：24次真实API请求','',
           '每章选1题，共8题，先冻结题干、答案和原页指纹再请求Qwen-plus；三组使用相同模型、提示词、temperature=0、max_tokens=1000。轮换组别顺序，不自动重试。',
           '题干由助手对照原页转录，答案由助手按数学定义推导，参考答案交叉核对与教师复核仍单列记录。该组为开发对照，不是随机抽样的独立测试。',
           '', '| 项目 | 纯模型 | 固定混合RAG | 规则自适应RAG |','|---|---:|---:|---:|']
    summaries=[objective['summary'][a] for a in arms]
    for label,key in [('实际请求数','attempted'),('JSON可解析','parsed'),('可解析且最终答案匹配','final_answer_match'),('平均请求秒数','mean_seconds'),('记录的Token数','recorded_tokens')]:
        lines.append('|'+label+'|'+'|'.join(str(s[key]) for s in summaries)+'|')
    lines += ['', '原始冻结8条输入中，三组均为5/8条满足“可解析且最终答案字段匹配”。这不是证明过程正确率，也没有显示RAG的解题增益。',
              '对照参考答案原页时发现P01转录的补事件/否定符号与原题不一致：原页答案为1/6，冻结提示词则构成另一道答案为1/3的题。该项在所有组中同时排除；source-review.json另存原页指纹和事后审核，原始数据不改。其余7题答案与参考答案逐项交叉核对，仍待教师审核；主口径三组均为5/7条，属于小规模开发对照，不能称为独立测试准确率。',
              '第一题三组都输出JSON不允许的裸分数1/3，保留为格式失败；第八题部分响应在预算附近留下不完整JSON。第五题三组的答案字段均为C，但解释又得出B；第八题也出现字段C、解释A的矛盾。不能用解释末尾的正确文字替换原始字段，抬高本轮分数。',
              '失败类型已另存format-failure-audit.json，原始报告与原始响应不修改。其余题目仍须教师审核条件、推导和引用支持关系。',
              '', '## 全题库检索验证','']
    if retrieval:
        lines += [f'当前冻结{len(retrieval["frozen_cases"])}条文字检索候选，每题比较BM25、向量、混合RRF和现有自适应路由。含图、缺页或边界不完整项保留排除原因；原始OCR仍待审核。',
                  '', '| 方法 | 已执行 | 返回候选 | 人工标注数 | Hit/Recall@5 |','|---|---:|---:|---:|---|']
        for arm,s in retrieval['summary'].items():
            lines.append(f'|{arm}|{s["attempted"]}|{s["with_candidates"]}|0|待标注|')
        empty=[c['case_id'] for c in retrieval['cases'] if not c['arms']['adaptive_rag'].get('hits')]
        lines += ['', f'自适应组无候选{len(empty)}道：'+('、'.join(empty) if empty else '无')+'。保留原始路由与失败，不回填为混合检索结果。']
        anchors_path=Path(retrieval_path).with_name('source-anchor-metrics.json')
        if anchors_path.exists():
            anchors=json.loads(anchors_path.read_text(encoding='utf-8'))
            lines += ['', '另外，9个助手核对的明确教材引用锚点单独评分，便利选样、非教师独立标注。包括同题、参数符号变式和扩展小问，不能外推为新题检索准确率。出处标签在查看这些题的排序前保存，但此时批量检索已启动，不能称为前瞻冻结测试。',
                      '', '| 方法 | 引用锚点数 | Hit@1 | Hit@5 | MRR@8 |', '|---|---:|---:|---:|---:|']
            for arm,s in anchors['summary'].items():
                lines.append(f'|{arm}|{s["cases"]}|{s["hit_at_1"]}|{s["hit_at_5"]}|{s["mrr_at_8"]}|')
    else:lines += ['完整题库仍在构建，先保留8题×4方法的检索冒烟记录；尚不发布检索准确率。']
    lines += ['', '“有候选”不等于“检索正确”。盲评池对各方法去重、隐藏组别和排序，逐条按0无关/1同主题/2方法可借鉴/3同题或完整条件近同标注。需全部标注负例，才能计算该池上的Recall和NDCG；它们仍不是全语料穷尽相关集的指标。',
              '含图题另记版面位置，未审核图中条件前不进入文字检索主口径。math-syntax-audit.json记录LaTeX编译失败；编译成功仍可能把补事件横线、上下标或参数识别错误，不能据此当作OCR正确率。',
              '早期8题检索发现：事件运算题可能被现有公式路由误判，返回空集或统计推断题。当前保留失败，不在测试过程中改规则后回填旧分数。',
              '', '## 如何证明RAG有用','',
              '1. 同题定位：在660B答案明确引用茆书时，对照双方完整条件审核后，统计教材题号/页码Hit@1/5。此组属于跨资料同题定位，单独报告。',
              '2. 新题关联：剔除同题及参数变式家族，给新题标注相关例题、可借鉴方法和知识点，比较四种检索。',
              '3. 辅导生成：相同新题和模型比较三组；教师盲评最终答案、条件一致性、推导和引用支持，同时记录延迟、Token与格式失败。',
              '4. 拒答与冲突：增加条件不完整、资料未覆盖和错误前提题，检查是否明确说明证据不足，不能只统计正例。',
              '', '不能把整份660B一面加入检索库、一面当独立测试。先审核题族，再按稳定哈希进行20%开发/80%保留分组；尚未完成题族审核的候选维持隔离。凡用于调参的数据转记开发集。',
              '', '## 下一步审核入口','',
              '- 原题与原页：data/private/660b-evaluation/dataset/review.html。',
              '- 题干结构：dataset/questions.jsonl；答案原页文本：dataset/sealed-answer-pages.jsonl。',
              '- 生成盲评：objective-pilot对应run目录的blind-math-review.json；映射blind-key.json单独保存。',
              '- 检索盲评：retrieval-runs对应目录的blind-relevance-review.json、teacher-label-template.json。',
              '- 导入人工标签：python score_external_relevance.py <report.json> --reviews <填写后的标签.json>；来源指纹不一致会拒绝混用。',
              '', '## 复现','', '```powershell',
              r'.\.venv-rag\Scripts\python.exe external_question_bank.py',
              r'.\.venv-rag\Scripts\python.exe build_external_evaluation.py',
              r'.\.venv-rag\Scripts\python.exe evaluate_external_retrieval.py',
              r'.\.venv-rag\Scripts\python.exe -m unittest tests.test_external_evaluation tests.test_external_relevance',
              '```', '', '真实生成需要显式--live，重跑会产生新请求和新run目录；当前24次结果已保存，无需重复付费调用。实际模型为API Qwen-plus，本轮没有部署或评测本地Qwen。',
              '', '## 原始证据','', f'- 模型报告：{Path(objective_path).as_posix()}。',
              f'- 检索报告：{Path(retrieval_path).as_posix() if retrieval_path else "待完整运行"}。',
              f'- 教材集合SHA256：{objective["collection_sha256"]}。',
              '- 协议：evaluation/external_660b_protocol.json。']
    if syntax:
        lines += ['', '## 公式展示核验边界','',
                  f'在{syntax["questions"]}道候选中检测到{syntax["formulas_detected"]}处带分隔符公式，KaTeX语法通过{syntax["syntax_passed"]}处、失败{syntax["syntax_failed"]}处。此项只检验编译语法，不能写成OCR准确率。',
                  '优先核对：'+ '、'.join(sorted({r['case_id'] for r in syntax['failures']}))+'；另核对660b-c1-q007的补事件横线及660b-c1-q060的图中条件。全部候选在教师审核前均不作为独立保留测试成绩。',
                  '审核HTML提供编译公式与原始OCR切换、原页链接；本轮浏览器策略不允许打开file协议，未进行浏览器视觉验收。']
    target=ROOT.parents[1]/'research/660B外部题库与RAG评测-2026-10-29.md'
    target.write_text('\n'.join(lines)+'\n',encoding='utf-8');print(target)
    return target


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('objective');p.add_argument('--retrieval')
    a=p.parse_args();write_report(a.objective,a.retrieval)
