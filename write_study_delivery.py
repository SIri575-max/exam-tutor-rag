"""Record the verified study-route stage; retain earlier stage reports and resume facts."""
import json
import re
import shutil
from pathlib import Path
from exercise_vectors import OUT,status
from question_knowledge import current
from process_full_book import write_json


def deliver():
    root=Path(__file__).resolve().parent;workspace=root.parents[1];date='2026-10-25'
    info=status();g=current()['report'];http=json.loads((OUT/'study-http-smoke.json').read_text(encoding='utf-8'))
    audit=json.loads((OUT/'graph-integrity-report.json').read_text(encoding='utf-8'))
    before=json.loads((OUT/'study-flow-before-math-bridge.json').read_text(encoding='utf-8'))
    after=json.loads((OUT/'study-flow-after-math-bridge.json').read_text(encoding='utf-8'))
    tests=(OUT/'study-tests.log').read_text(encoding='utf-8');count=int(re.search(r'Ran (\d+) tests',tests).group(1))
    if not info['ready'] or http['status']!='passed' or audit['status']!='passed' or not tests.rstrip().endswith('OK'):
        raise ValueError('Finish validation before recording this stage')
    relative=f'research/茆书RAG考点关系与学习路径交付记录-{date}.md'
    receipt={'date':date,'stage':'source_linked_full_book_study_routes_ready_pending_content_review',
             'source_sha256':info['source_sha256'],'collection_sha256':info['collection_sha256'],
             'records':info['records'],'kinds':info['kinds'],'vector_chunks':info['chunks'],
             'source_linked_boundary_reviews':info['source_linked_boundary_reviews'],
             'remaining_opening_only_examples':info['boundaries']['opening_only_boundary_unresolved'],
             'source_supplements':info['source_supplements'],'graph':g,'tests_passed':count,
             'new_probe_before':{'hit_at_1':before['hit_at_1'],'hit_at_8':before['hit_at_8'],'cases':8},
             'known_failure_regression_after':{'hit_at_1':after['hit_at_1'],'hit_at_8':after['hit_at_8'],'cases':8},
             'real_llm_generation':False,'teacher_review':'pending','personal_practice':'not_verified',
             'latest_delivery_file':relative}
    write_json(OUT/'study-delivery-status.json',receipt)
    text=f'''# 茆书RAG：考点关系与学习路径交付记录

日期：{date}。本轮按“继续一直做下去”推进现有项目，完成例题检索范围修复、带证据的初步题目图谱、规则自适应检索、学习路径和本地反馈闭环。原始教材与过去经历资料不改写；助手交付不等于用户已独立掌握或已有实习上线成绩。

## 可直接使用

- 页面：http://127.0.0.1:8771/problems 。输入自然语言题意，或直接输入“例7.5.2”“习题1.2第12题”。
- 查看考点线索、教材定义/定理出处、可点击的关系图、引用前例和例题→课后题阅读路径；窄屏使用可读的关系路径列表。
- 自动补充开关：当返回结果缺少另一类题目时，实际发起第二轮检索；可关闭对照。普通闲聊先要求补题目条件，不强行返回数学题。
- 对识别或关联问题提交本地反馈；记录绑定题号、来源/集合版本、问题类型和原输入，保持pending_review，不自动批准、训练或改写教材。
- 例题待校对表：项目`data/private/full-book/question-vectors/example-review-queue.csv`，也可从网页下载。

## 例题质量修复

仍为735道课后题、274条例题候选，共1009条。向量片段从1083增至{info['chunks']}个。

- 34条例题按原始OCR块重划题干/数据检索范围，补齐跨段条件、公式和原始数据表；每条保存块ID、字符范围、原文哈希、页图哈希及审核边界。
- 其中8页对照原图检查（PDF255、295、347、376、377、395、435、436）；并非34条全部逐字人工校对。
- 例7.5.2的后五个观测值被OCR当作页眉并粘连。对照PDF377补录“539.35 179.49 782.93 561.10 286.80”，使题目检索层恢复10个值；原始OCR、补录原因、坐标及页图哈希均保留，详情单独显示补录。
- 原始档案仍维持490页，内容块逐项保存。上述补录用于题目层，不声称全书连续OCR稿的所有页眉/正文误分都已修正。
- 开头摘要待核对例题从133条降至{info['boundaries']['opening_only_boundary_unresolved']}条。说明性例子、使用前例的续例和一般例题分别标记；仍不能把所有例题都当作可独立作答的练习。
- 机床乙数据粘连、表格混有计算列等已加可见提示；未擅自将含糊OCR数字作为可计算标准数据。

## 图谱与出处

图谱实际包含{g['nodes']}个唯一节点、{g['edges']}条边：1009条题目、163个教材小节考点入口、175个归并后的定义/定理/性质等条目。182条原始知识条目候选中，7处“定理…表明/性质…给出”等正文引用归并为附属说明，避免同编号覆盖真正的定义或定理。

- 720条题目含可直接匹配的显式考点词语，生成1531条mentions_topic候选边；这些边有词语摘录和原题页码。
- 272条例题位置边、33条前例引用边、174条教材小节包含知识条目的位置边。
- 词语提及、目录位置和“题目考查某知识点”不是同一主张。没有自动生成teacher-approved的tests/requires关系；余下题目也未强贴考点。
- 引用关系保存原文片段。例如例8.1.2引用例8.1.1的数据，页面可直接打开前例。

## 自适应检索与已知失误修复

当前是可追踪的规则路由，没有伪装成训练过的复杂度分类器：明确题号直接查记录；自然语言执行混合检索；必要时第二轮补另一类题目；明确的“正态总体＋总体均值已知＋离差平方和”使用公式别名扩展，并优先保留同时满足三个条件的候选。最多两轮，数学别名扩展后不再发起依赖它的第三轮。

原先漏召回的例5.4.1，输入自然语言“正态样本的总体均值已知，样本对该均值的离差平方和服从什么分布”现在首位命中。扩展只把明确条件转为对应的符号表达，没有把答案分布名称加入查询。此规则很窄，不等于通用数学推理或数学重排模型。

## 验证与结果边界

- {count}项程序测试通过；前端JS语法检查通过。
- 490页原书哈希、OCR原始块保留与导出完整性再次检查通过；1009条题目覆盖、向量字节/分块覆盖、图谱唯一节点/边端点/词语与引用证据检查通过。
- 一键流程`./build_question_vectors.ps1`实际重跑成功，重建向量库、图谱、待校对表及定位检查；`./start_demo.ps1`启动本地服务。
- HTTP实测了题号定位、10个观测值恢复、补充两类题目、最多两轮、普通闲聊澄清、前例引用、99行待审表、错误反馈拒绝与490页资料库保留。
- 浏览器实测了新页面、公式扩展首位命中、反馈表单、考点路径及窄屏关系呈现；反馈写入的版本绑定和保持待审核在临时目录测试，未向正式待审清单写入伪造反馈。
- 原24条助手改写定位自检保留其范围；本轮新增8条跨八章题意检查最初首位命中5/8、前8命中7/8。根据其中已知失误开发数学查询桥接后，同一组回归首位6/8、前8为8/8。修复前后报告均保留；后者属于已知用例回归，不能声称独立保留集或学生效果提升。

私有记录：`study-flow-before-math-bridge.json`、`study-flow-after-math-bridge.json`、`study-http-smoke.json`、`graph-integrity-report.json`、`study-tests.log`及`example-boundary-reviews.json`。初步图谱为`question-knowledge-graph.json`。

## 后续工作

优先继续核对99条摘要例题，建立分布条件/所求目标/解法的人工审核标签及真正独立题目集。当前别名与拒答规则覆盖有限，词语提及不保证考点适配；大部分公式及表格数值仍待校对。现有第一章55题13考点卡的辅导链保持独立，全书未自动批准生成数学解答，真实Qwen调用、教师审核和本人实践仍未验证。
'''
    (workspace/relative).write_text(text,encoding='utf-8')
    backup=workspace/f'archives/{date}/RAG考点路径更新前';backup.mkdir(parents=True,exist_ok=True)
    for source,name in [(workspace/'README.md','workspace-README.md'),(workspace/'data/ideas.json','ideas.json'),(root/'README.md','project-README.md')]:
        if not (backup/name).exists():shutil.copy2(source,backup/name)
    path=workspace/'data/ideas.json';data=json.loads(path.read_text(encoding='utf-8'));items=data['items'] if 'items' in data else next(v for v in data.values() if isinstance(v,list))
    idea=next(i for i in items if i.get('id')=='build-exam-tutor-adaptive-rag')
    idea.update(updated_date=date,engineering_status='assistant_full_book_source_linked_study_routes_ready; chapter1_curated_tutoring_only',
                tests_passed=count,full_book_study_delivery=receipt,latest_delivery_file=relative,
                next_deliverable='继续校对99条摘要例题，建立条件与解法审核标签和独立题目评测；再联调真实模型辅导',
                boundary='Full-book question retrieval and source-linked graph/study routes implemented. Literal mentions are not approved skill/prerequisite labels; known-case regression is not held-out performance. OCR, teacher review, real LLM generation and personal practice remain pending.')
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    readme=workspace/'README.md';lines=readme.read_text(encoding='utf-8').splitlines()
    for n,line in enumerate(lines):
        if line.startswith('当前推进统计学/应用统计专业课的题目知识图谱：'):
            lines[n]=f'当前推进统计学/应用统计专业课的题目知识图谱：490页待校对资料库、735道课后题和274条例题候选已支持混合检索、出处核对、初步考点关系、前例引用与例题→课后题路径。34条例题补齐检索范围，99条例题摘要仍待核对；图谱为原文提及/位置候选。{count}项程序测试通过，第一章55题13考点卡继续用于辅导预览。全书数学精校、教师审核、真实Qwen联调和本人实践待完成；不混入原实习成绩。'
    link=f'- [考点关系与学习路径交付记录]({relative})'
    if link not in lines:lines.insert(6,link)
    readme.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    project=root/'README.md';existing=project.read_text(encoding='utf-8');marker='## 考点关系与学习路径（2026-10-25）'
    if marker not in existing:project.write_text(existing+f'\n{marker}\n\n继续使用 `/problems`：题号直达、带出处的考点关系与定义/定理、引用前例、最多两轮规则检索、明确条件的数学符号桥接、本地待审反馈。34条例题重划范围；99条仍为待核对摘要；图谱{g["nodes"]}节点/{g["edges"]}边，均非教师批准的考查/先修标签。{count}项测试通过。[实际交付与评测边界](../../{relative})。\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in receipt.items() if k!='graph'},ensure_ascii=False,indent=2))


if __name__=='__main__':deliver()
