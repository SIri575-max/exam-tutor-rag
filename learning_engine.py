"""Source-grounded hybrid retrieval, explicit routing, and bounded graph expansion."""
import re
import time
from fractions import Fraction
from course_data import load, document_text
from retrieval import bm25

GENERIC={'事件','概率','证明','至少','至多','已知','原因','先后','分步','产品','包含','交集','并集','补集'}
OUTSIDE=r'最大似然|假设检验|置信区间|中心极限定理|大数定律|卡方分布|回归分析|矩估计|充分统计|正态分布|泊松分布|习题\s*[2-8]\.|第二章|第[二三四五六七八]章|天气预报|股票|编写代码|牛顿|英语翻译'


def checked_question(question):
    if not isinstance(question,str) or not 3<=len(question.strip())<=3000:raise ValueError('请输入3–3000字的题目或学习问题')
    return question.strip()


def concept_votes(query,concepts):
    votes={}
    for c in concepts:
        hits=[a for a in c['aliases'] if a not in GENERIC and a.lower() in query.lower()]
        if hits:votes[c['id']]=sum(min(len(a),6) for a in hits)+(6 if c['label'] in query else 0)
    return votes


def ranking(query,data,mode):
    items=data['exercises']+data['concepts'];by_id={x['id']:x for x in items}
    scores=bm25(query,[document_text(x) for x in items])
    lexical=sorted(zip([x['id'] for x in items],scores),key=lambda x:-x[1])
    dense=[];semantic={'used':False,'reason':'bm25_baseline'}
    if mode!='bm25':
        try:
            from vector_index import search,MODEL
            dense=search(query,20);semantic={'used':True,'model':MODEL,'backend':'ONNX CPU'}
        except (ImportError,RuntimeError,ValueError,OSError):
            semantic={'used':False,'reason':'semantic_index_or_runtime_unavailable'}
    fused={id:0.0 for id in by_id}
    for rank,(id,score) in enumerate(lexical[:20],1):
        if score>0:fused[id]+=1/(30+rank)
    for rank,(id,score) in enumerate(dense,1):fused[id]+=1/(30+rank)
    votes=concept_votes(query,data['concepts']) if mode!='bm25' else {}
    for id,item in by_id.items():
        keys=item.get('concepts',[id])
        fused[id]+=min(sum(votes.get(c,0) for c in keys),20)*0.0015
    # Explicit book locator is stronger evidence than semantic closeness.
    locator=re.search(r'(?:习题\s*)?(1\.[1-5])\s*(?:第|[-，,、])?\s*(\d+)\s*题?',query)
    if locator:
        id=f'mao3-{locator.group(1)}-{int(locator.group(2))}'
        if id in fused:fused[id]+=10
    ranked=sorted(fused,key=lambda id:(-fused[id],id))
    return ranked,by_id,{'lexical_top_score':float(lexical[0][1]),'dense_top_score':float(dense[0][1]) if dense else None,
                         'semantic':semantic,'scores':fused,'concept_votes':votes}


def public_question(q,reason=None):
    # Answer field intentionally excluded, including from the browser payload.
    keys=['id','section','number','title','text','concepts','citations','review_status']
    result={k:q[k] for k in keys}
    if reason:result['relation_reason']=reason
    return result


def retrieve(question,mode='adaptive'):
    query=checked_question(question)
    if mode not in {'bm25','hybrid','adaptive'}:raise ValueError('未知检索模式')
    started=time.monotonic();data=load()
    base={'question':query,'mode':mode,'collection':data['collection'],'corpus_sha256':data['corpus_sha256'],
          'review_status':'assistant_source_checked_pending_teacher_review'}
    if re.search(OUTSIDE,query):
        return {**base,'status':'out_of_scope','route':'outside_first_chapter','message':'当前预览覆盖第一章随机事件与概率；该问题需要其他章节资料。','matches':[],'concepts':[],'related':[],'citations':[],'trace':[{'step':'scope_check','result':'outside'}],'graph':{'nodes':[],'edges':[]}}
    if len(query)<14 and re.search(r'^请?(帮我)?(求|算|解|计算).*(概率|这道题)|^这(道)?题怎么',query):
        return {**base,'status':'clarification_needed','route':'clarify_conditions','message':'请补充完整题干，包括试验过程、已知条件及要求的事件。','matches':[],'concepts':[],'related':[],'citations':[],'trace':[{'step':'condition_check','result':'missing_question'}],'graph':{'nodes':[],'edges':[]}}
    ranked,items,meta=ranking(query,data,mode)
    if meta['lexical_top_score']<1 and (meta['dense_top_score'] or 0)<0.52 and not meta['concept_votes']:
        return {**base,'status':'insufficient_evidence','route':'clarify_or_add_material','message':'未找到足够相关的第一章依据，请补充题干或说明考点。','matches':[],'concepts':[],'related':[],'citations':[],'trace':[{'step':'retrieve','result':'weak_evidence'}],'graph':{'nodes':[],'edges':[]}}
    trace=[{'step':'retrieve','method':'BM25 + BGE + reciprocal-rank fusion' if meta['semantic']['used'] else 'BM25',
            'semantic':meta['semantic'],'lexical_top_score':round(meta['lexical_top_score'],3),'dense_top_cosine':meta['dense_top_score']}]
    qids=[id for id in ranked if items[id]['kind']=='exercise'][:3]
    direct=sorted(meta['concept_votes'],key=lambda c:-meta['concept_votes'][c])[:2]
    cids=list(dict.fromkeys(direct+items[qids[0]]['concepts']))[:4]
    if mode=='bm25':cids=list(dict.fromkeys(items[qids[0]]['concepts']))[:3]
    cmap={c['id']:c for c in data['concepts']}
    missing=[p for c in cids for p in cmap[c]['prerequisites'] if p not in cids]
    missing=list(dict.fromkeys(missing))[:3]
    multi=mode=='adaptive' and bool(re.search(r'证明|比较|综合|贝叶斯|反推|逆概率|先.*再|区别|为什么',query))
    route='bounded_multi_retrieval' if multi else ('hybrid_graph' if mode=='adaptive' else 'single_retrieval')
    if multi:
        second_query=query+' '+' '.join(cmap[c]['label'] for c in missing)
        second,_,second_meta=ranking(second_query,data,'hybrid')
        new_ids=[id for id in second if items[id]['kind']=='concept' and id in missing]
        cids=list(dict.fromkeys(cids+new_ids))[:7]
        trace.append({'step':'second_retrieval','round':2,'query':second_query,'added_evidence_ids':new_ids,
                      'semantic_used':second_meta['semantic']['used'],'routing':'rules_not_trained_paper_classifier'})
    concepts=[cmap[c] for c in cids]
    prereqs=[cmap[c] for c in missing if c not in cids]
    related=[]
    anchor_concepts=set(cids)|set(items[qids[0]]['concepts'])
    if mode=='adaptive':
        for q in sorted(data['exercises'],key=lambda q:(-len(set(q['concepts'])&anchor_concepts),q['id'])):
            shared=set(q['concepts'])&anchor_concepts
            if q['id'] not in qids and shared:
                related.append(public_question(q,'共享考点：'+'、'.join(cmap[c]['label'] for c in sorted(shared))))
            if len(related)==5:break
        trace.append({'step':'course_graph_expand','hops':1,'related_exercises':[q['id'] for q in related]})
    matches=[public_question(items[id]) for id in qids]
    citations={x['id']:x for item in concepts+[items[id] for id in qids] for x in item['citations']}
    visible={'concept:'+c['id'] for c in concepts+prereqs}|{'exercise:'+q['id'] for q in matches+related}
    node_by_id={n['id']:n for n in data['graph']['nodes']}
    ordered=['concept:'+c['id'] for c in concepts+prereqs]+['exercise:'+q['id'] for q in matches+related]
    graph={'nodes':[node_by_id[id] for id in dict.fromkeys(ordered) if id in visible],
           'edges':[e for e in data['graph']['edges'] if e['from'] in visible and e['to'] in visible]}
    clarifications=[]
    if re.search(r'(?:原来|原有|原本|原球).*?(?:不知|不知道|未知)',query) and not re.search(r'先验|各半|各为|1/2|二分之一',query):
        clarifications.append('原来那颗球为黑/白的先验概率如何规定？不知道颜色并不自动表示两种颜色各占一半。')
    if re.search(r'其中一件|有一件|至少一件',query) and re.search(r'合格|告知|抽检',query):
        clarifications.append('已知的是“至少一件合格/不合格”，还是指定检查的那一件？告知机制会影响条件事件。')
    if clarifications:route='clarify_with_evidence'
    return {**base,'status':'evidence_found','route':route,'message':'关联是学习参考；相似题不代表题目条件相同。','clarifications':clarifications,
            'matches':matches,'concepts':concepts,'prerequisites':prereqs,'related':related,'graph':graph,
            'citations':list(citations.values()),'trace':trace,'semantic':meta['semantic'],
            'elapsed_seconds':round(time.monotonic()-started,3)}


CN={'一':1,'二':2,'两':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10}


def dice_calculation(query):
    if not re.search(r'骰子|色子|骰',query) or not re.search(r'最大|最高',query):return None
    count=re.search(r'(\d+|[一二两三四五六七八九十])\s*(?:颗|个|枚)\s*(?:骰子|色子|骰)',query)
    threshold=re.search(r'(?:最大(?:值|点数)?|最高(?:数字|点数)?).{0,12}?(?:恰好(?:等于|为)?|等于|为|不超过|小于等于|≤|<=)\s*(\d+|[一二两三四五六七八九十])',query)
    if not count or not threshold:return None
    number=lambda s: int(s) if s.isdigit() else CN[s]
    n=number(count.group(1));k=number(threshold.group(1))
    sides_match=re.search(r'(\d+|[一二两三四五六七八九十])\s*面',query)
    sides=number(sides_match.group(1)) if sides_match else 6
    if not (1<=n<=30 and 2<=sides<=20 and 0<=k<=sides):return None
    if re.search(r'不公平|有偏|不独立|相关|最大.*最小',query):return None
    cumulative=Fraction(k**n,sides**n);exact=Fraction(k**n-max(k-1,0)**n,sides**n)
    return {'tool':'exact_fraction_dice_max','n':n,'k':k,'sides':sides,
            'assumptions':[f'{n}颗骰子相互独立',f'每颗为公平{sides}面骰；题目未写明时这是一项演示假设'],
            'cumulative':str(cumulative),'exact':str(exact),
            'formula':f'P(M≤{k})=({k}/{sides})^{n}；P(M={k})=({k}/{sides})^{n}−({max(k-1,0)}/{sides})^{n}',
            'boundary':'按当前输入参数计算，不使用相似题的存储答案。'}


def guidance(result,stage='hint'):
    if stage not in {'hint','steps','solution'}:raise ValueError('未知辅导层级')
    if result['status']!='evidence_found':return {'mode':'clarification','text':result['message'],'calculation':None}
    concepts=result['concepts'];lines=['需要确认：'+q for q in result.get('clarifications',[])]
    for c in concepts[:3]:lines.append(c['label']+'：'+(c['hint'] if stage=='hint' else c['text'])+''.join('['+x['id']+']' for x in c['citations']))
    calc=dice_calculation(result['question'])
    if calc:
        if stage=='hint':lines.append('先把“最大值不超过边界”写成每颗骰子都不超过边界；恰好取边界可用两次累计概率作差。')
        else:lines.append('在明确假设下：'+calc['formula'])
        if stage=='solution':lines.append(f"累计概率={calc['cumulative']}；恰好概率={calc['exact']}。")
    else:lines.append('以上是从教材依据整理的学习指引；完整题目推导尚需配置模型或由教师核对。')
    return {'mode':'retrieved_guidance_with_exact_tool' if calc else 'retrieved_guidance','stage':stage,'text':'\n\n'.join(lines),
            'calculation':calc if stage=='solution' else None,'llm_used':False}
