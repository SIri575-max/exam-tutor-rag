"""Record an actually completed full-book archive; never promote it to resume facts."""
import collections
import datetime as dt
import json
import shutil
from pathlib import Path
from process_full_book import BASE, write_json
from sync_sources import ROOT


def finalize():
    report = json.loads((BASE / 'organization-report.json').read_text(encoding='utf-8'))
    audit = json.loads((BASE / 'coverage-audit.json').read_text(encoding='utf-8'))
    progress = json.loads((BASE / 'progress.json').read_text(encoding='utf-8'))
    if (audit['status'] != 'coverage_integrity_passed' or not report['coverage_complete']
            or progress['status'] != 'complete_unreviewed'):
        raise ValueError('Finish processing and pass the final coverage audit before recording completion')
    date = dt.date.today().isoformat()
    workspace = ROOT.parents[1]
    relative_report = f'research/茆书整书整理交付记录-{date}.md'
    questions = [json.loads(line) for line in (BASE / 'exercise-candidates.jsonl').read_text(encoding='utf-8').splitlines()]
    chapter_counts = collections.Counter(q['section'].split('.')[0] for q in questions)
    missing = {s['section']: s['missing_expected_numbers'] for s in report['sections_detail'] if s.get('missing_expected_numbers')}
    unexpected = {s['section']: s['unexpected_numbers'] for s in report['sections_detail'] if s.get('unexpected_numbers')}
    graph = json.loads((BASE / 'book-structure-graph.json').read_text(encoding='utf-8'))
    status = {'date': date, 'stage': 'full_book_raw_archive_complete_pending_content_review',
              'source_pdf_pages': 490, 'ocr_pages': report['pages_with_valid_ocr'],
              'chapters': 8, 'sections': 43, 'subsections': 163,
              'expected_exercise_ids': report['expected_exercise_ids_from_visual_number_boundaries'],
              'unique_exercise_candidates': report['unique_exercise_ids'],
              'numbering_missing': missing, 'numbering_unexpected': unexpected,
              'duplicate_exercise_ids': report['duplicate_exercise_ids'],
              'source_checked_boundary_repairs': report.get('applied_source_checked_boundary_reviews', []),
              'cross_page_exercises': report['cross_page_exercise_candidates'],
              'raw_blocks': report['blocks'], 'semantic_units': report['semantic_units'],
              'formula_segments': report['formula_segments'], 'assets': report['assets'],
              'answer_candidates': report['reference_answer_candidates'],
              'answer_sections_located': report['answer_sections_located'],
              'answer_sections_not_listed_in_source': report['answer_sections_not_listed_in_source'],
              'answer_sections_unresolved': report['answer_sections_unresolved'],
              'structure_graph_nodes': len(graph['nodes']), 'structure_graph_edges': len(graph['edges']),
              'coverage_audit': audit['status'], 'formula_syntax_flags': audit['formula_syntax_flag_count'],
              'tests_passed': 37, 'teacher_review': 'pending', 'real_llm_generation': 'not_configured_or_live_tested',
              'curated_tutoring_scope': 'chapter1_55_exercises_13_concepts',
              'personal_practice': 'not_yet_verified', 'delivery_report': relative_report}
    write_json(BASE / 'delivery-status.json', status)
    text = f'''# 茆书整书整理交付记录

日期：{date}。本轮按用户“把整本书所有内容整理下来”的要求，完成490页私有扫描教材的本机处理、结构化整理与阅读导出。助手实现和检查不等于用户本人已掌握，也不改变过去实习经历。

## 实际完成

- 教材：《概率论与数理统计教程》第三版，茆诗松、程依明、濮晓龙；源文件保持不变。
- 覆盖490/490页：书前22页、八章正文及习题419页、附表27页、参考答案19页、参考文献及书末3页。
- 目录：8章、43节、163个小节；逐页、分节、分章及整书阅读稿均已生成。
- 归一化内容块{report['blocks']}个，所有原始OCR内容块逐项保留，原页图及原始解析JSON可追溯。
- 对照原书43节的末题编号建立735个题号基准；切分{report['unique_exercise_ids']}个唯一题目候选，跨页题{report['cross_page_exercise_candidates']}道。
- 题号断档：{json.dumps(missing,ensure_ascii=False)}；额外题号：{json.dumps(unexpected,ensure_ascii=False)}；重复题号：{json.dumps(report['duplicate_exercise_ids'],ensure_ascii=False)}。
- 定义、定理、性质、例题等候选：{json.dumps(report['semantic_units'],ensure_ascii=False)}；公式片段{report['formula_segments']}个；图表区域{report['assets']}个。
- 参考答案候选{report['reference_answer_candidates']}条，题干与答案分开；按唯一编号匹配的候选关联{report['unique_answer_number_matches']}条。原书“略”保留，未补造教材证明。
- 已定位41个习题组的参考答案页。原书答案区从习题4.4直接转入5.3，未列出5.1、5.2组，不补造解答；逐题答案切分仍需校对，649条候选不等于649道已核准解答。

| 章 | 整理出的课后题候选 |
| --- | --- |
'''
    for chapter in range(1, 9):
        text += f'| 第{chapter}章 | {chapter_counts[str(chapter)]} |\n'
    text += f'''
## 打开与复用

- 在线资料库：http://127.0.0.1:8771/library 。按目录导航、全文搜索、逐页对照、类型筛选、答案单独查看。
- 离线入口：projects/exam-tutor-rag/data/private/full-book/exports/全书资料库.html 。无需后端接口或网络；保留整个full-book目录以保持相对页图链接。
- 阅读目录：同目录开始阅读.md；连续稿：全书识别稿.md；另有8章正文、4份书前/附表/答案/书末稿、43节稿和490份逐页稿。
- 习题目录、知识条目索引、参考答案索引、图表索引与公式索引.csv可单独使用。
- JSONL：normalized-blocks、page-catalog、exercise-candidates、answer-candidates、learning-units、formulas、assets。
- catalog.sqlite3提供本地检索；book-structure-graph.json为目录、条目位置与答案编号候选图，{len(graph['nodes'])}个节点、{len(graph['edges'])}条边。

位置关系不等于经过审核的“考查知识点/先修知识”语义关系。现有第一章55道原页整理题、13张考点卡与全书原始识别稿继续分开，未自动将待审内容批准进辅导索引。

## 验证与限制

- 全书覆盖、原书/页图哈希、原始块保留、SQLite、离线阅读稿与Markdown完整性检查通过。62个印刷页码锚点和43节末题编号由助手对照原图检查；不是全文逐字人工校对。
- 在项目.venv-rag运行环境中，程序回归37项通过；系统Python缺少语义检索运行依赖时有1项检索测试失败，切回正确环境后通过。此前40条第一章检索工程样例的结果保持原范围，不能拿来声称全书检索或教学效果提升。
- 自动公式语法检查标出{audit['formula_syntax_flag_count']}处复核线索；没有标记也不等于公式正确。公式、表格数字、题干切分及答案关联仍需内容审核。
- 复核表：page-review.csv、quality-review-queue.csv；来源页码、坐标、原始块和单独的封面补录均保留。
- 当前未配置真实Qwen生成，没有全书标准解答准确率、学生效果或生产上线结论。
- HTML阅读与搜索已在静态网页模式检查，脚本不请求后端接口。内置浏览器的URL策略拒绝file://协议，因此未在其中验证直接双击本地HTML的打开方式；在线资料库和导出文件核验已完成。

## 可复现处理

本机MinerU4.0.12 basic/ONNX CPU，160dpi，2个批次并发；复用58页原有结果，分批保存、逐页重试。MINERU_HOME复用本地权重，未调用远程解析或上传整本教材。详细批次耗时和失败/重试记录保留在progress.json及logs。

第129页触发零像素检测框异常；本地兼容处理只在框没有可读像素时返回None，沿用上游既有过滤路径。补丁前文件、前后哈希、触发页和测试记录位于environment-patches。原始教材未被修改。完整依赖快照及parser-profile.json记录版本。

重跑入口：projects/exam-tutor-rag/organize_full_book.ps1；缓存以来源、输入图和输出哈希校验。后续审核通过的条目再加入语义考点与辅导检索。
'''
    (workspace / relative_report).write_text(text, encoding='utf-8')
    backup = workspace / f'archives/{date}/RAG整书完成状态更新前'
    backup.mkdir(parents=True, exist_ok=True)
    for name in ('data/ideas.json', 'README.md'):
        source = workspace / name; target = backup / source.name
        if not target.exists():
            shutil.copy2(source, target)
    idea_path = workspace / 'data/ideas.json'
    ideas = json.loads(idea_path.read_text(encoding='utf-8'))
    items = ideas['items'] if 'items' in ideas else next(v for v in ideas.values() if isinstance(v, list))
    idea = next(x for x in items if x.get('id') == 'build-exam-tutor-adaptive-rag')
    idea.update(updated_date=date, engineering_status='assistant_full_book_raw_archive_ready; chapter1_curated_tutoring_preview',
                full_corpus_ocr_and_indexing_status='490pages_raw_archive_complete; local_archive_search_ready; tutoring_curated_chapter1_only',
                textbook_processing_status='490_of_490_private_pages_organized; content_review_pending', tests_passed=37,
                full_book_delivery=status, latest_delivery_file=relative_report,
                next_deliverable='校对全书公式、表格和答案关联，确认考点实体及题目关系，将审核通过的内容逐步加入辅导检索',
                boundary='Full-book raw OCR archive is complete and source-linked, not fully proofread. Teacher review and personal practice pending; no live Qwen generation, teaching outcomes or production release claimed.')
    idea['full_book_request']['status'] = 'full_book_raw_archive_complete_pending_content_review'
    idea['chapter1_delivery_file'] = 'research/茆书RAG连续推进交付记录-2026-10-25.md'
    idea_path.write_text(json.dumps(ideas, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    root_readme = workspace / 'README.md'
    lines = root_readme.read_text(encoding='utf-8').splitlines()
    for n, line in enumerate(lines):
        if line.startswith('当前推进统计学/应用统计专业课的题目知识图谱：'):
            lines[n] = (f'当前推进统计学/应用统计专业课的题目知识图谱：整书490页已整理为待校对资料库，覆盖8章43节，切分{report["unique_exercise_ids"]}道课后题候选，提供离线阅读、全文搜索和原页对照。第一章55道原页整理题、13张考点卡继续用于混合检索、候选图谱和规则自适应辅导预览。37项程序检查通过；全书内容审核、本人实践及真实Qwen生成联调仍待完成。旧LoRA原型保留，不混入原实习成绩。')
            break
    link = f'- [整书整理交付记录]({relative_report})'
    if link not in lines:
        lines.insert(6, link)
    root_readme.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    project_readme = ROOT / 'README.md'
    existing = project_readme.read_text(encoding='utf-8')
    addition = f'\n整书最终核对：490/490页；{report["unique_exercise_ids"]}个唯一题目候选；37项程序检查通过。完整统计与边界见[整书交付记录](../../{relative_report})。\n'
    if addition.strip() not in existing:
        existing += addition
        project_readme.write_text(existing, encoding='utf-8')
    print(json.dumps(status, ensure_ascii=False, indent=2))
    return status


if __name__ == '__main__':
    finalize()
