"""Save the verified question-retrieval stage without changing resume facts."""
import json
import re
import shutil
from pathlib import Path
from exercise_vectors import OUT, status
from process_full_book import write_json


def deliver():
    root=Path(__file__).resolve().parent; workspace=root.parents[1]; date='2026-10-25'
    info=status()
    audit=json.loads((OUT/'integrity-report.json').read_text(encoding='utf-8'))
    smoke=json.loads((OUT/'http-smoke.json').read_text(encoding='utf-8'))
    evaluation=json.loads((OUT/'source-location-evaluation.json').read_text(encoding='utf-8'))
    tests=(OUT/'tests-latest.log').read_text(encoding='utf-8')
    if not info['ready'] or audit['status']!='passed' or smoke['status']!='passed' or not tests.rstrip().endswith('OK'):
        raise ValueError('Finish validation before recording delivery')
    count=int(re.search(r'Ran (\d+) tests',tests).group(1))
    relative=f'research/茆书课后题与例题向量库交付记录-{date}.md'
    backup=workspace/f'archives/{date}/RAG题目向量库更新前';backup.mkdir(parents=True,exist_ok=True)
    for source,name in [(workspace/'README.md','workspace-README.md'),(workspace/'data/ideas.json','ideas.json'),(root/'README.md','project-README.md')]:
        if not (backup/name).exists():shutil.copy2(source,backup/name)
    delivery={k:info[k] for k in ['collection_sha256','source_sha256','kinds','records','chunks','model','dimensions','boundaries']}
    delivery.update(date=date,stage='full_book_question_vector_search_ready_pending_content_review',
                    engineering_tests_passed=count,source_location_self_check=evaluation['summary'],
                    semantic_knowledge_graph='not_yet_approved; cross_type_links_are_same_section_query_ranked_candidates',
                    personal_practice='not_verified',teacher_review='pending',real_llm_generation=False,
                    delivery_file=relative)
    write_json(OUT/'delivery-status.json',delivery)
    text=f'''# 茆书课后题与例题向量库交付记录

日期：{date}。按用户“建立向量库，重点在于课后题与例题”的要求，在整书490页私有资料库之上完成题目检索层。原书和OCR归档不改写；本轮实现不转为过往实习成果，不等于用户已经独立掌握。

## 可使用的入口

- 题目检索：http://127.0.0.1:8771/problems
- 原书阅读：http://127.0.0.1:8771/library
- 启动：项目目录运行 `./start_demo.ps1`。
- 重新建库及校验：`./build_question_vectors.ps1`。本轮二次建库新增向量0个、复用1083个，复用前比较模型文件哈希和分块内容哈希。

输入题干或题意后，可选择课后题/例题、章节以及混合/向量/关键词检索；查看题号、OCR题干、命中片段、原页、原例讲解与同节另一类题目的检索候选。书末参考答案默认不进入匹配，课后题的答案按钮只定位习题组答案页，未伪造逐题解答。

## 题目集合

- 735道课后题候选全部纳入；275条例题原始候选去除1处正文对例1.4.3的重复引用，得到274个唯一例号候选。
- 合计1009条题目记录、1083个向量片段、512维float32；按题号/例号保留来源SHA、原始块ID、章节、页码与OCR审核状态。
- 141条例题按显式“解/证明”标记截出题干候选；133条无法明确分离的例题只索引首个原始段落，并标记“开头摘要，条件可能不全、讲解边界待核对”。摘要本身也可能混有说明；没有宣称全书例题题干已精校或完全无讲解。
- 完整原例、讲解与表格保留在记录详情中，未把完整讲解字段送入embedding。题干/摘要中表格内容保留，HTML标签不参与向量编码。
- 例5.0.1位于第五章章前引例，保留此例号，小节位置单列章前引例，未强塞进5.1。

## 实际实现

复用已有本地 `BAAI/bge-small-zh-v1.5` 与FastEmbed0.9.1/ONNX CPU。SQLite持久保存题目、分块向量与元数据，NumPy做精确余弦检索；当前千题规模无需额外数据库服务或GPU。该模型及运行库的说明见[模型卡](https://huggingface.co/BAAI/bge-small-zh-v1.5)与[FastEmbed官方仓库](https://github.com/qdrant/fastembed)。

- 检索单元是题目，不是整页；320字符滑窗、最多64字符重叠，附小节上下文。使用独立、关闭截断的tokenizer核验输入，本次最大输入{info['max_input_tokens']}tokens，预算480；长题与长查询分段处理。
- 先按题目聚合片段分数，再以RRF融合语义排名和BM25排名，避免长题因片段多而获得重复票。
- 同节课后题/例题路径按当前查询的检索排名生成，属于候选阅读关联，不是教师核准的“同一考点”关系。
- 来源集合变更时拒绝静默使用过期索引；原有第一章55题、13考点卡的辅导链继续保留，全书原始候选未自动批准进入辅导生成。

主要文件：`exercise_collection.py`、`exercise_vectors.py`、`problem_search_ui.py`、`verify_question_vectors.py`、`evaluate_question_vectors.py`。私有数据位于 `data/private/full-book/question-vectors/`，包括records.jsonl、excluded.json、vectors.sqlite3、index-report.json和验收记录。

## 验证结果

- {count}项程序测试通过；覆盖题干/讲解边界、表格与公式文本保留、长题分块全覆盖、按题目融合、过滤先于排名、过期库拒绝、非法输入等。
- 集合与原始记录对照、735题覆盖、1083个向量的维度/归一化/字节、全部索引题干字符的分块覆盖及SQLite完整性通过。此检查不证明OCR数学内容正确。
- HTTP与浏览器实际核验：骰子最大点数→习题1.2第12题；第八章例题筛选→例8.1.1；可展开原例表格与PDF395原图，题目类型和章节过滤生效。
- 24条跨八章定位自检：16条例题、8道课后题；依据已知OCR记录由助手改写，属于来源定位自检，没有独立保留集或教师标签，不能当作泛化/教学准确率。先完成初始页面预设冒烟检查，再选定这24条样例，未隐瞒选择过程。

| 方法 | 首位命中 | 前5命中 | 前8命中 | MRR@8 |
| --- | --- | --- | --- | --- |
'''
    labels={'bm25':'BM25','vector':'语义向量','hybrid':'混合检索'}
    for mode,values in evaluation['summary'].items():
        text+=f"| {labels[mode]} | {values['hit_at_1']}/24 | {values['hit_at_5']}/24 | {values['hit_at_8']}/24 | {values['mrr_at_8']} |\n"
    text+='''
本次混合检索首位和前8表现较好，BM25的前5命中反而更多；保留三种方法供检查，没有据此宣称混合检索全面优于基线。当前对不相关输入也可能返回候选，没有训练“无相关题”判定器。

## 仍需完成

优先校对133条例题的题干、条件和讲解边界，特别是图表条件；再核对全书公式与表格数字。之后为题目补考点、解法、先修关系、难度与条件标签，通过教师审核后接入全书Adaptive RAG辅导。当前只完成真实向量检索，没有全书自动解题、精确语义知识图谱或生产上线结论。
'''
    (workspace/relative).write_text(text,encoding='utf-8')
    idea_path=workspace/'data/ideas.json';ideas=json.loads(idea_path.read_text(encoding='utf-8'))
    items=ideas['items'] if 'items' in ideas else next(v for v in ideas.values() if isinstance(v,list))
    idea=next(x for x in items if x.get('id')=='build-exam-tutor-adaptive-rag')
    idea.update(updated_date=date,engineering_status='assistant_full_book_question_vector_search_ready; chapter1_curated_tutoring_preview',
                full_corpus_ocr_and_indexing_status='490page_archive_ready; 735exercises_274example_candidates_indexed; semantic_tutoring_curated_chapter1_only',
                tests_passed=count,question_vector_delivery=delivery,latest_delivery_file=relative,
                next_deliverable='优先校对133条例题题干与讲解边界，审核题目考点关系；用独立题目评测召回与拒答，再接入全书Adaptive RAG辅导',
                boundary='Full-book question vector search exists; OCR and example stems pending review. Query-ranked cross-type links are not teacher-approved semantic edges; no full-book generated-solution or learning-outcome claim.')
    idea_path.write_text(json.dumps(ideas,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    readme=workspace/'README.md';lines=readme.read_text(encoding='utf-8').splitlines()
    for n,line in enumerate(lines):
        if line.startswith('当前推进统计学/应用统计专业课的题目知识图谱：'):
            lines[n]='当前推进统计学/应用统计专业课的题目知识图谱：整书490页已整理为待校对资料库；735道课后题、274条例题候选已建立本地向量库，支持混合检索、类型/章节筛选、原页对照与同节题例阅读路径。第一章55题、13考点卡继续用于辅导预览。45项程序测试通过；例题题干与公式校对、考点语义审核、本人实践及真实Qwen生成仍待完成。旧LoRA原型保留，不混入原实习成绩。'
    link=f'- [课后题与例题向量库交付记录]({relative})'
    if link not in lines:lines.insert(6,link)
    readme.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    project_readme=root/'README.md';existing=project_readme.read_text(encoding='utf-8')
    marker='## 全书课后题与例题向量检索（2026-10-25）'
    addition=f'''\n{marker}\n\n入口：http://127.0.0.1:8771/problems 。735道课后题、274条例题候选，共1009条记录/1083个512维向量片段；题意向量+BM25/RRF检索，支持题型、章节、原页、讲解详情与同节另一类题目的检索候选。133条例题暂只索引开头摘要，条件与讲解边界待校对；不是全书自动解题。\n\n重建：`./build_question_vectors.ps1`；启动：`./start_demo.ps1`。45项测试通过。24条来源定位自检的样例、全部结果和限制见[交付记录](../../{relative})。\n'''
    if marker not in existing:project_readme.write_text(existing+addition,encoding='utf-8')
    print(json.dumps(delivery,ensure_ascii=False,indent=2))


if __name__=='__main__':deliver()
