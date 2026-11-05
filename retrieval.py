"""Auditable lexical baseline and graph expansion; no simulated LLM or embeddings."""
import collections
import json
import math
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parent


def corpus():return json.loads((ROOT/'data/private/sample-corpus.json').read_text(encoding='utf-8'))


def tokens(text):
    clean=re.sub(r'\s+','',text.lower())
    return re.findall(r'[a-z]+|\d+',clean)+[clean[i:i+2] for i in range(max(0,len(clean)-1)) if re.search(r'[\u4e00-\u9fff]',clean[i:i+2])]


def bm25(query,docs):
    bags=[collections.Counter(tokens(d)) for d in docs];qt=set(tokens(query));n=len(bags)
    avg=sum(sum(b.values()) for b in bags)/max(n,1)
    df={t:sum(t in b for b in bags) for t in qt}
    scores=[]
    for b in bags:
        length=sum(b.values());score=0
        for t in qt:
            tf=b[t]
            if tf:score+=math.log(1+(n-df[t]+.5)/(df[t]+.5))*tf*2.2/(tf+1.2*(.25+.75*length/max(avg,1)))
        scores.append(score)
    return scores


def retrieve(question,mode='adaptive'):
    if not isinstance(question,str) or not 3<=len(question.strip())<=3000:raise ValueError('请输入3–3000字的完整题目')
    if mode not in {'baseline','graph','adaptive'}:raise ValueError('未知检索模式')
    data=corpus();exercises=[e for e in data['exercises'] if e['retrievable']]
    generic={'最大','位置','长度','独立','至少','恰好','至多','不超过','包含','环'}
    scope_hit=any(alias not in generic and alias.lower() in question.lower() for c in data['concepts'] for alias in c['aliases'])
    scores=bm25(question,[e['title']+' '+e['text'] for e in exercises])
    ranked=sorted(zip(scores,exercises),key=lambda x:(-x[0],x[1]['id']))
    trace=[{'step':'lexical_retrieve','method':'BM25 Chinese bigrams','candidate_count':len(exercises)}]
    if not scope_hit or not ranked or ranked[0][0]<.5:
        return {'status':'insufficient_evidence','question':question,'route':'request_material_or_clarify',
                'message':'当前仅覆盖第一章少量样板，尚未找到可靠相关题。请补充题干或相应章节资料。',
                'matches':[],'concepts':[],'prerequisites':[],'related':[],'trace':trace,'graph':{'nodes':[],'edges':[]}}
    matches=[dict(e,retrieval_score=round(score,4)) for score,e in ranked[:3] if score>=max(.5,ranked[0][0]*.3)]
    # Do not treat lexical closeness as proof that an unfamiliar question is identical.
    anchor=matches[0];concept_ids=set(anchor['concepts'])
    selected=[c for c in data['concepts'] if c['id'] in concept_ids]
    complex_q=len(concept_ids)>=3 or bool(re.search(r'证明|比较|综合|分别',question))
    route='iterative_graph' if mode=='adaptive' and complex_q else ('graph_expansion' if mode!='baseline' else 'single_retrieval')
    prereq_ids={p for c in selected for p in c['prerequisites']} if mode!='baseline' else set()
    prereqs=[c for c in data['concepts'] if c['id'] in prereq_ids and c['id'] not in concept_ids]
    related=[]
    if mode!='baseline':
        trace.append({'step':'graph_expand','hops':1,'anchor':anchor['id'],'basis':'candidate_shared_concepts'})
        for e in exercises:
            shared=set(e['concepts'])&concept_ids
            if e['id']!=anchor['id'] and shared:related.append(dict(e,shared_concepts=sorted(shared)))
    if route=='iterative_graph':
        expansion=' '.join(c['label'] for c in selected+prereqs)
        second=bm25(question+' '+expansion,[e['title']+' '+e['text']+' '+' '.join(e['methods']) for e in exercises])
        accepted=[]
        for score,e in sorted(zip(second,exercises),key=lambda x:-x[0]):
            overlap=set(e['concepts']) & (concept_ids|prereq_ids)
            if score>=.5 and overlap and e['id']!=anchor['id'] and not any(x['id']==e['id'] for x in related):
                related.append(dict(e,shared_concepts=sorted(overlap),relation_reason='prerequisite_background',second_round_score=round(score,4)))
                accepted.append(e['id'])
        trace.append({'step':'bounded_second_retrieval','round':2,'query_expansion':expansion,
                      'added_background_exercises':accepted,
                      'note':'rule-routed lexical expansion, not trained question-complexity classifier'})
    visible={'exercise:'+e['id'] for e in [anchor]+related}|{'concept:'+c['id'] for c in selected+prereqs}
    graph={'nodes':[n for n in data['graph']['nodes'] if n['id'] in visible],
           'edges':[e for e in data['graph']['edges'] if e['from'] in visible and e['to'] in visible]}
    return {'status':'candidate_matches','question':question,'route':route,'matches':matches,
            'concepts':selected,'prerequisites':prereqs,'related':related,'graph':graph,'trace':trace,
            'message':'候选关联待复核；检索分数不是置信概率。原题参数变化时不可直接复用原答案。',
            'generation_status':'not_connected','review_status':'candidate_pending_user_review'}
