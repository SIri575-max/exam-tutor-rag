"""Pin measured quality/latency results and retain ungraded human-review fields."""
import hashlib
import json
from pathlib import Path
from problem_correspondence import input_topics
from benchmark_correspondence import BASE, ROOT, DATASET_SHA


def read(path):return json.loads(path.read_text(encoding='utf-8'))


def run():
    before_path=sorted(BASE.glob('run-before-*/report.json'))[-1]
    after_path=sorted(BASE.glob('run-after-*/report.json'))[-1]
    before,after=read(before_path),read(after_path)
    lbp=sorted(BASE.glob('latency-before-*.json'))[-1];lap=sorted(BASE.glob('latency-after-*.json'))[-1]
    lb,la=read(lbp),read(lap)
    assert all(x['dataset_sha256']==DATASET_SHA for x in [before,after,lb,la])
    assert before['collection_sha256']==after['collection_sha256']
    for arm in ['bm25','vector','hybrid']:
        assert [(r['case_id'],r['returned_ids']) for r in before['details'][arm]]==[(r['case_id'],r['returned_ids']) for r in after['details'][arm]]
    assert all(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==sha for name,sha in after['code_sha256'].items())
    dataset=read(BASE/'frozen-source-queries.json');template=[]
    for c in dataset['cases']:
        pool={h['id']:h for report in [before,after] for rows in report['details'].values()
              for r in rows if r['case_id']==c['id'] for h in r['candidates']}
        template.append({'case_id':c['id'],'query':c['query'],'status':'pending_human_review','reviewer':None,
                         'source_ocr_checked':False,'family_id':None,'split':'development_source_location_proxy',
                         'candidates':[{k:pool[i].get(k) for k in ['id','label','pages','question_text']}|{'grade':None} for i in sorted(pool)],
                         'topic_candidates':[{'id':t['id'],'label':t['label'],'pdf_page':t['pdf_page'],'relevant':None} for t in input_topics(c['query'])]})
    review=BASE/'human-review-template.json'
    review.write_text(json.dumps({'status':'pending_human_review','cases':template,'boundary':'No model-generated grades or approval. Source retrieval proxy labels are distinct from useful-related-question labels.'},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    result={'date':'2026-11-04','cases':len(dataset['cases']),'dataset_sha256':DATASET_SHA,
            'quality':{'before':before['summary'],'after':after['summary'],'by_kind':after['by_kind']},
            'latency':{'before':{k:lb[k] for k in ['first_pass','repeated_queries','warmup_seconds']},
                       'after':{k:la[k] for k in ['first_pass','repeated_queries','warmup_seconds']}},
            'paired':{'wins_against_hybrid':after['paired_top1_wins_against_hybrid'],'losses_against_hybrid':after['paired_top1_losses_against_hybrid']},
            'source_artifacts':{str(p.relative_to(BASE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [before_path,after_path,lbp,lap]},
            'implementation_sha256':after['code_sha256'],'review_template':review.name,'new_generation_api_calls':0,
            'remaining_boundary':'知识点相关性、全部推荐是否有用、学生查书时间和数学解题提升仍未完成独立验证；本轮仅证明这批已知出处开发改写题的定位改进及本机服务耗时变化。'}
    path=BASE/'comparison.json';path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (BASE/'latest.json').write_text(json.dumps({'report':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()},indent=2)+'\n',encoding='utf-8')
    a=after['summary']['correspondence'];b=before['summary']['correspondence'];h=after['summary']['hybrid'];lex=after['summary']['bm25']
    ms=lambda x:round(x*1000,1)
    first_reduction=100*(1-la['first_pass']['median_seconds']/lb['first_pass']['median_seconds'])
    repeat_reduction=100*(1-la['repeated_queries']['median_seconds']/lb['repeated_queries']['median_seconds'])
    doc=f'''# 题目对应效果与服务效率对照（2026-11-04）

目标是新题对应教材例题、课后题和知识点。此次对固定来源改写题进行四方法配对评价，并单独复测同一完整服务耗时。没有请求生成模型，也未把正确题号写入查询。

## 已测得的结果

| 方法 | 首位找回原题 | 前三位找回原题 | MRR@3 |
|---|---:|---:|---:|
| 关键词BM25 | {lex['hit_at_1']}/24 | {lex['hit_at_3']}/24 | {lex['mrr_at_3']} |
| 语义向量 | {after['summary']['vector']['hit_at_1']}/24 | {after['summary']['vector']['hit_at_3']}/24 | {after['summary']['vector']['mrr_at_3']} |
| 固定混合检索 | {h['hit_at_1']}/24 | {h['hit_at_3']}/24 | {h['mrr_at_3']} |
| 原对应流程 | {b['hit_at_1']}/24 | {b['hit_at_3']}/24 | {b['mrr_at_3']} |
| 优化后对应流程 | {a['hit_at_1']}/24 | {a['hit_at_3']}/24 | {a['mrr_at_3']} |

当前首位{a['hit_at_1']}/24，相较固定混合的{h['hit_at_1']}/24增加{a['hit_at_1']-h['hit_at_1']}题，即{(a['hit_at_1']-h['hit_at_1'])/24*100:.2f}个百分点；相较原对应流程增加{a['hit_at_1']-b['hit_at_1']}题。关键词基线也较强，必须同时披露，不能只选择较弱向量基线。

独立进程依次运行完整服务；各预热一次，随后24条首轮请求和72条重复请求。首轮中位耗时 {ms(lb['first_pass']['median_seconds'])}→{ms(la['first_pass']['median_seconds'])}毫秒，下降{first_reduction:.1f}%；首轮P95 {ms(lb['first_pass']['p95_seconds'])}→{ms(la['first_pass']['p95_seconds'])}毫秒；重复查询中位数 {ms(lb['repeated_queries']['median_seconds'])}→{ms(la['repeated_queries']['median_seconds'])}毫秒，下降{repeat_reduction:.1f}%。两轮中缓存均未改变候选顺序。

## 数据与边界

- 固定24道已知出处改写题，来自8章、8条例题与16道课后题。由助手根据来源编写，剔除缺题意/缺条件条目后冻结；数据SHA-256 `{DATASET_SHA}`。
- 本批与此前24条历史来源开发样例是两批数据，不能混写为同一组提升，也不能相加成独立样本。
- 先运行原实现再据失败案例改进，因此24条全部是开发数据。虽然出处可按来源记录核对，这不是教师相关性标签、学生新题或独立保留测试集。
- 基线预先知道题型（例题或课后题）；当前流程同时找两类题，评价时只取对应类型前三项。只找到预定出处才计命中，其他有用题目可能被这个代理指标漏算。
- 耗时是本机检索和导航服务时间，未包含上传、OCR、模型生成或人工查书，不可写作学生学习效率提升。预热与首轮、重复查询分别保留，不用多方法对照时的缓存时间冒充独立服务耗时。
- 早期耗时文件`latency-before-223018.json`在预热阶段与另一开发检查并发，保留供审计，最终对照使用后续串行复测。

## 实际改动

保留类型内BM25候选与混合、公式候选做并集，减少全局前20被另一类题占满的漏检；添加保留数字的公式字符n-gram相似度，达到分数与区分度门槛才参与融合，绝不认证数学等价；查询向量与词法分数按查询、索引路径及修改戳缓存，知识点提及缓存返回副本，防止响应改写污染后续查询。

与固定混合比较新增首位命中：{', '.join(after['paired_top1_wins_against_hybrid'])}；首位退化：{', '.join(after['paired_top1_losses_against_hybrid']) or '无'}。失败全部留在报告，不补分。

## 下一阶段

人工评价例题/课后题的可借鉴性、知识点相关性，并按题族划分未参与调参的新题测试。用学生实际任务计时才能验证人工查找效率。人工核对表所有等级和知识点标签保持空值，导出入口在评测页。

评测页：http://127.0.0.1:8771/matching-evaluation 。完整报告及阶段快照保存在`projects/exam-tutor-rag/data/private/correspondence-study-20261104/`，运行脚本为`benchmark_correspondence.py`、`benchmark_correspondence_latency.py`。
'''
    target=ROOT.parents[1]/'research/统计学RAG对应质量与效率实验-2026-11-04.md';target.write_text(doc,encoding='utf-8')
    print(json.dumps({'comparison':str(path),'document':str(target),'first_pass_reduction_percent':round(first_reduction,2),
                      'repeated_query_reduction_percent':round(repeat_reduction,2),'hit_at_1':a['hit_at_1'],'hit_at_3':a['hit_at_3']},ensure_ascii=False))


if __name__=='__main__':run()
