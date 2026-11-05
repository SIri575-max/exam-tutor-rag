"""Evidence-bearing question graph: literal mentions, references, and locations."""
import collections
import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path
from book_structure import structure
from exercise_collection import rows, searchable_text
from exercise_vectors import OUT, snapshot, status as vector_status
from process_full_book import BASE, write_json
from sync_sources import fingerprint

GRAPH = OUT/'question-knowledge-graph.json'
ALIASES = {
 '1.1.2':['样本空间'], '1.1.5':['事件关系'], '1.1.6':['事件运算','对立事件','互斥事件'],
 '1.2.2':['排列组合'], '1.2.4':['古典概型','等可能'], '1.2.5':['几何概型'],
 '1.4.1':['条件概率'], '1.4.3':['全概率'], '1.4.4':['贝叶斯公式','贝叶斯定理'],
 '1.5.1':['事件独立'], '1.5.2':['相互独立'],
 '2.1.2':['分布函数'], '2.1.3':['分布列'], '2.1.4':['概率密度','密度函数'],
 '2.2.2':['数学期望','期望值'], '2.3.1':['方差','标准差'],
 '2.3.3':['切比雪夫'], '2.4.1':['二项分布','二点分布','伯努利分布'],
 '2.4.2':['泊松分布','Poisson'], '2.4.3':['超几何分布'], '2.4.4':['负二项分布','几何分布'],
 '2.5.1':['正态分布','正态总体','高斯分布'], '2.5.2':['均匀分布','均匀总体'],
 '2.5.3':['指数分布'], '2.5.4':['伽马分布','Gamma'], '2.5.5':['贝塔分布','Beta分布'],
 '2.7.2':['变异系数'], '2.7.3':['分位数'], '2.7.4':['中位数'],
 '3.1.2':['联合分布函数'], '3.1.3':['联合分布列'], '3.1.4':['联合密度'],
 '3.2.1':['边际分布'], '3.3.2':['最大值的分布','最小值的分布','最大点数','最小点数'],
 '3.3.3':['卷积'], '3.4.3':['协方差'], '3.4.4':['相关系数','不相关'],
 '3.5.1':['条件分布'], '3.5.2':['条件期望','条件数学期望'],
 '4.1.1':['依概率收敛'], '4.1.2':['按分布收敛','弱收敛'],
 '4.2.1':['特征函数'], '4.3.1':['伯努利大数定律'], '4.3.2':['大数定律','蒙特卡罗'],
 '4.4.2':['中心极限定理'], '4.4.3':['正态近似'],
 '5.2.1':['经验分布函数'], '5.2.2':['频数频率表','直方图'], '5.2.3':['茎叶图'],
 '5.3.2':['样本均值'], '5.3.3':['样本方差','样本标准差'], '5.3.5':['次序统计量'],
 '5.3.7':['箱线图','五数概括'], '5.4.1':['卡方分布'], '5.4.2':['F分布'], '5.4.3':['t分布'],
 '5.5.1':['充分统计量','充分性'], '5.5.2':['因子分解定理'],
 '6.1.1':['无偏估计','无偏性'], '6.1.2':['有效性'],
 '6.2.1':['矩估计','矩法估计','替换原理'], '6.2.3':['相合估计','相合性','一致性'],
 '6.3.1':['最大似然','极大似然','MLE'], '6.3.2':['EM算法'], '6.3.3':['渐近正态'],
 '6.4.1':['均方误差','MSE'], '6.4.2':['最小方差无偏','UMVUE'],
 '6.4.4':['费希尔信息','Fisher信息','克拉默','C-R下界','Cramer'],
 '6.5.3':['贝叶斯估计'], '6.5.4':['共轭先验'],
 '6.6.1':['置信区间','区间估计'], '6.6.2':['枢轴量'], '6.6.5':['样本量'],
 '7.1.1':['假设检验'], '7.1.3':['p值','P值'], '7.2.1':['均值检验','t检验'],
 '7.2.4':['成对数据','配对检验'], '7.2.5':['方差检验'],
 '7.4.1':['似然比检验'], '7.4.2':['拟合优度'], '7.4.4':['列联表','独立性检验'],
 '7.5.1':['正态概率纸','正态概率图'], '7.5.2':['W检验','Shapiro'], '7.5.3':['EP检验'],
 '7.6.1':['游程检验'], '7.6.2':['符号检验'], '7.6.3':['秩和检验','非参数检验'],
 '8.1.2':['方差分析','单因子试验'], '8.1.3':['平方和分解'],
 '8.2.2':['多重比较'], '8.3.1':['哈特利'], '8.3.2':['巴特利特','Bartlett'],
 '8.4.2':['线性回归','回归方程'], '8.4.3':['最小二乘','LSE'],
 '8.4.5':['预测区间'], '8.5.1':['非线性回归','曲线回归'],
}


def topic_catalog():
    topics=[]
    for s in structure()['subsections']:
        aliases=list(ALIASES.get(s['id'],[]))
        if len(s['title'])>=4 and s['title'] not in {'问题的提出','参数估计','检验方法','估计与预测'}:aliases.append(s['title'])
        topics.append({**s,'id':'topic:'+s['id'],'subsection':s['id'],
                       'section':'.'.join(s['id'].split('.')[:2]),'aliases':list(dict.fromkeys(aliases))})
    return topics


def mentions(text, topics=None):
    clean=searchable_text(text); result=[]
    for topic in topics or topic_catalog():
        found=[]
        for alias in topic['aliases']:
            match=re.search(re.escape(alias),clean,re.I)
            if match:
                if alias=='二项分布' and match.start()>0 and clean[match.start()-1]=='负':continue
                found.append((match.start(),match.end(),alias))
        if found:
            start,end,alias=max(found,key=lambda m:m[1]-m[0])
            result.append({'id':topic['id'],'label':topic['title'],'subsection':topic['subsection'],
                           'matched_alias':alias,'quote':clean[max(0,start-22):min(len(clean),end+35)],
                           'pdf_page':topic['pdf_first'],'relation':'literal_mention_candidate'})
    return result


def canonical_units(units):
    grouped=collections.defaultdict(list)
    for u in units:grouped[u['id']].append(u)
    result=[]
    for identifier,group in grouped.items():
        reference=lambda u:bool(re.match(r'^(?:定\s*义|定\s*理|性\s*质|推\s*论|引\s*理|命\s*题)\s*\d+\s*\.\s*\d+\s*\.\s*\d+\s*(?:给出|表明|中的|说明|只假设)',u['text']))
        actual=next((u for u in group if not reference(u)),group[0])
        result.append({**actual,'source_commentary':[{'pages':u['pages'],'block_ids':u['block_ids'],'text':u['text']} for u in group if u is not actual]})
    return result


def build():
    info=vector_status()
    if not info['ready']:raise ValueError('Build current question vectors first')
    records=snapshot()[1]; topics=topic_catalog(); topic_ids={x['id'] for x in topics}
    raw_units=[x for x in rows(BASE/'learning-units.jsonl') if x['kind']!='example']
    units=canonical_units(raw_units)
    nodes=[];edges=[]; by_record={};readings=collections.defaultdict(list)
    for topic in topics:
        nodes.append({'id':topic['id'],'label':topic['title'],'kind':'topic','pages':[topic['pdf_first']],
                      'subsection':topic['subsection'],'review_status':'source_TOC_anchor; aliases_are_assistant_rules'})
    for r in records.values():
        nodes.append({'id':r['id'],'label':r['label'],'kind':r['kind'],'pages':r['pages']})
        matches=mentions(r['question_text'],topics);by_record[r['id']]=matches
        for m in matches:
            edges.append({'from':r['id'],'to':m['id'],'kind':'mentions_topic','quote':m['quote'],
                          'source_pages':r['pages'],'review_status':'literal_mention_not_exam_skill_approval'})
        for reference in r.get('example_references',[]):
            if reference['id'] in records:
                edges.append({'from':r['id'],'to':reference['id'],'kind':reference['kind'],
                              'quote':reference['quote'],'source_pages':r['pages'],'review_status':'source_reference_candidate'})
        if r.get('subsection') and 'topic:'+r['subsection'] in topic_ids:
            edges.append({'from':r['id'],'to':'topic:'+r['subsection'],'kind':'located_in_subsection',
                          'source_pages':r['pages'],'review_status':'OCR_heading_context_not_skill_label'})
    for u in units:
        nodes.append({'id':u['id'],'kind':u['kind'],'label':u.get('title',u['id'])[:90],'pages':u['pages']})
        identifier='topic:'+str(u.get('subsection'))
        if identifier in topic_ids:
            edges.append({'from':identifier,'to':u['id'],'kind':'contains_source_unit','source_pages':u['pages'],
                          'review_status':'same_subsection_location'})
            heading = re.match(r'^(?:定义|定理|性质|推论|引理|命题)\s*\d+(?:\.\d+)+', u.get('title', ''))
            readings[identifier].append({'id':u['id'],'kind':u['kind'],'title':heading[0] if heading else u.get('title',u['id']),
                                         'text':u['text'],'pages':u['pages'],'review_status':u['review_status']})
    report={'collection_sha256':info['collection_sha256'],'rules_sha256':fingerprint(Path(__file__)),
            'source_sha256':info['source_sha256'],'topics':len(topics),'question_records':len(records),
            'knowledge_units':len(units),'raw_knowledge_unit_candidates':len(raw_units),
            'merged_numbered_commentary':len(raw_units)-len(units),'nodes':len(nodes),'edges':len(edges),
            'edge_kinds':dict(collections.Counter(e['kind'] for e in edges)),
            'questions_with_literal_topic_mentions':sum(bool(v) for v in by_record.values()),
            'boundary':'Literal mentions, OCR/TOC locations and references only; no automatic teacher-approved tests/requires edges.'}
    graph={'report':report,'nodes':nodes,'edges':edges,'topics':topics,'record_topics':by_record,'readings':dict(readings)}
    write_json(GRAPH,graph);load.cache_clear();print(json.dumps(report,ensure_ascii=False,indent=2));return graph


@lru_cache(maxsize=2)
def load(stamp):
    return json.loads(GRAPH.read_text(encoding='utf-8'))


def current():
    if not GRAPH.exists():raise ValueError('Build the question knowledge graph first')
    graph=load(GRAPH.stat().st_mtime_ns)
    vector_info=vector_status()
    if not vector_info['ready'] or graph['report']['collection_sha256']!=vector_info['collection_sha256'] or graph['report']['rules_sha256']!=fingerprint(Path(__file__)):
        raise ValueError('Question graph is stale; rebuild it against the current question collection')
    return graph


def study_context(hits,query):
    graph=current();query_topics=sorted(mentions(query,graph['topics']),key=lambda m:-len(m['matched_alias']))
    selected=list(dict.fromkeys(x['id'] for x in query_topics))
    record_topics={h['id']:graph['record_topics'].get(h['id'],[]) for h in hits}
    for matches in list(record_topics.values())[:3]:
        for x in sorted(matches,key=lambda m:-len(m['matched_alias']))[:4]:
            if x['id'] not in selected:selected.append(x['id'])
    readings=[]
    for tid in selected:
        readings.extend(graph['readings'].get(tid,[])[:2])
    unique={r['id']:r for r in readings}
    # Original source order is stable and doesn't pretend to be a difficulty score.
    topic_priority={u['id']:n for n,tid in reversed(list(enumerate(selected))) for u in graph['readings'].get(tid,[])}
    readings=sorted(unique.values(),key=lambda x:(topic_priority[x['id']],x['pages'][0],x['id']))[:6]
    questions=hits[:1]
    if questions:
        other=next((h for h in hits if h['kind']!=questions[0]['kind']),None)
        if other:questions.append(other)
    for h in hits:
        if len(questions)>=3:break
        if h['id'] not in {q['id'] for q in questions}:questions.append(h)
    question_ids={h['id'] for h in questions}
    visible=question_ids|set(selected)|{r['id'] for r in readings}
    edges=[e for e in graph['edges'] if e['from'] in visible and e['to'] in visible]
    referenced=[]
    records=snapshot()[1]
    for h in hits[:3]:
        for ref in records[h['id']].get('example_references',[]):
            if ref['id'] in records:referenced.append({**ref,'from':h['id'],'pages':records[ref['id']]['pages']})
    node_by_id={n['id']:n for n in graph['nodes']}
    ordered_ids=list(dict.fromkeys([q['id'] for q in questions]+selected+[r['id'] for r in readings]))
    return {'query_topics':query_topics,'record_topics':record_topics,'readings':readings,
            'references':referenced,'graph':{'nodes':[node_by_id[i] for i in ordered_ids if i in visible], 'edges':edges},
            'graph_boundary':graph['report']['boundary']}


if __name__=='__main__':build()
