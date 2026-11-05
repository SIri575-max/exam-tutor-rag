"""Explain question-to-textbook correspondence without claiming equivalence or mastery."""
import re
import copy
from functools import lru_cache
import formula_retrieval as formula
from question_knowledge import mentions as raw_mentions, topic_catalog


@lru_cache(maxsize=4096)
def _cached_mentions(text):
    return raw_mentions(text)


def mentions(text):
    # Never let response enrichment mutate a cache shared by later requests.
    return copy.deepcopy(_cached_mentions(text))

MODEL_TOPICS={'normal':'2.5.1','uniform':'2.5.2','poisson':'2.4.2','binomial':'2.4.1',
              'negative_binomial':'2.4.4','exponential':'2.5.3','gamma':'2.5.4','beta':'2.5.5',
              'chi_square':'5.4.1','student_t':'5.4.3'}
OP_TOPICS={'unbiased':'6.1.1','mle':'6.3.1','confidence':'6.6.1','conjugacy':'6.5.4',
           'prior_beta':'6.5.4','minimum':'5.3.5','maximum':'5.3.5','sample_mean':'5.3.2',
           'variance':'2.3.1','expectation':'2.2.2','covariance':'3.4.3','correlation':'3.4.4'}
GOALS={'unbiased','mle','confidence','conjugacy','prior_beta'}
CHECKS={'6.1.1':'能否根据样本分布计算估计量的期望，并与待估参数比较？',
        '6.1.2':'比较前是否确认估计目标一致、无偏性成立，并正确计算方差？',
        '6.3.1':'能否写出似然函数，并检查参数相关的支持区间和边界？',
        '6.6.1':'能否确定所求参数、构造区间所需的分布及覆盖概率？',
        '6.5.4':'能否区分似然中的参数与观测值，并识别后验分布核？',
        '5.3.5':'能否由总体分布推出样本最小值或最大值的分布？',
        '2.3.1':'能否正确处理方差中的系数平方、独立性与协方差项？',
        '3.4.3':'能否区分独立、不相关，并正确计算联合矩？'}


def input_topics(query):
    catalog={t['subsection']:t for t in topic_catalog()};selected={}
    def add(code,basis,quote):
        if code in catalog and code not in selected:
            t=catalog[code]
            selected[code]={'id':t['id'],'label':t['title'],'pdf_page':t['pdf_first'],
                            'subsection':code,'basis':basis,'quote':quote,
                            'self_check':CHECKS.get(code,'能否说明该概念的定义、适用条件，并在原题中找到对应量？')}
    p=formula.profile(query)
    # Learning goals precede distribution names; these are inferred review clues.
    for op in ['unbiased','mle','confidence','conjugacy','prior_beta']:
        if op in p['operations']:add(OP_TOPICS[op],'题干任务线索',formula.OP_LABELS[op])
    if '有效' in query or 'unbiased' in p['operations'] and 'variance' in p['operations']:
        add('6.1.2','题干任务线索','无偏性与方差/有效性比较')
    for t in mentions(query):add(t['subsection'],'题干明确提及',t['matched_alias'])
    for op in ['minimum','maximum','sample_mean','expectation','variance','covariance','correlation']:
        if op in p['operations']:add(OP_TOPICS[op],'公式或运算线索',formula.OP_LABELS[op])
    for model in p['models']:
        if model in MODEL_TOPICS:add(MODEL_TOPICS[model],'分布线索',formula.MODEL_LABELS[model])
    return list(selected.values())[:7]


def relation(query,hit,query_profile=None,query_mentions=None):
    qp=query_profile or formula.profile(query);cp=formula.profile(hit['question_text'])
    comparison=formula.comparison(qp,cp)
    qm=query_mentions if query_mentions is not None else mentions(query)
    cm=mentions(hit['question_text']);shared={t['id'] for t in qm}&{t['id'] for t in cm}
    reasons=list(comparison['reasons']);differences=list(comparison['differences'])
    for t in cm:
        if t['id'] in shared and t['label'] not in reasons:reasons.append('共同提及：'+t['label'])
    missing_goal=bool((set(qp['operations'])&GOALS)-(set(cp['operations'])&GOALS))
    hard_conflict=any(qp['conditions'].get(k) is not None and cp['conditions'].get(k) is not None
                      and qp['conditions'][k]!=cp['conditions'][k] for k in ['support','mean','exponential_rate'])
    model_conflict=bool(qp['models'] and cp['models'] and not set(qp['models'])&set(cp['models']))
    if model_conflict:differences.append('总体分布类型不同，不能直接沿用候选题结论')
    if hard_conflict or model_conflict:
        level,label='condition_difference','条件有差异的参考题'
    elif missing_goal:
        level,label='different_goal','所求量需核对'
    elif set(qp['operations'])&set(cp['operations'])&GOALS:
        level,label='method_related','所求任务相关'
    elif comparison['eligible']:
        level,label='structure_related','分布或公式结构相关'
    elif shared:
        level,label='topic_related','知识点词语相关'
    else:
        level,label='semantic_candidate','语义检索候选'
    if 'opening_only' in hit.get('stem_boundary',''):differences.append('例题仅有开头摘要，完整条件需看原页')
    background=len(cp['models'])>=3 and len(qp['models'])<=2
    if background:
        level,label='background_reference','多种分布汇总，仅供背景阅读'
        differences.append('候选包含多种分布或汇总内容，不能据此认定为同一题型')
    if not reasons:reasons=['根据题干的关键词与语义召回，尚无明确的同方法证据']
    return {'level':level,'label':label,'reasons':reasons[:6],
            'differences':list(dict.fromkeys(differences)),
            'shared_models':sorted(set(qp['models'])&set(cp['models'])),
            'shared_operations':sorted(set(qp['operations'])&set(cp['operations'])),
            'record_topics':cm[:5],'condition_conflict':hard_conflict or model_conflict,
            'goal_mismatch':missing_goal,'equivalence_verified':False}


def rank(query,base_hits,formula_hits=(),limit=8,lexical_hits=(),math_hits=()):
    """Keep semantic recall; formula ranks give a bounded bonus, never a veto."""
    strong_math=bool(math_hits and math_hits[0]['math_fingerprint_match']['similarity']>=.65 and
                     (len(math_hits)==1 or math_hits[0]['math_fingerprint_match']['similarity']-math_hits[1]['math_fingerprint_match']['similarity']>=.08))
    math_hits=list(math_hits) if strong_math else []
    pool={h['id']:h for h in list(formula_hits)+list(lexical_hits)+list(base_hits)+math_hits}
    br={h['id']:i+1 for i,h in enumerate(base_hits)};fr={h['id']:i+1 for i,h in enumerate(formula_hits)}
    lr={h['id']:i+1 for i,h in enumerate(lexical_hits)}
    mr={h['id']:i+1 for i,h in enumerate(math_hits)}
    qp=formula.profile(query);qm=mentions(query);output=[]
    # Specific, stated statistical structure deserves more influence than a
    # generic variance symbol. Both channels remain in the candidate pool.
    fw=(.65 if len(qp['operations'])>=2 and qp['conditions'] else .5) if qp['models'] and qp['operations'] else .25
    if not formula_hits:fw=0
    mw=.55 if strong_math else 0;fw*=1-mw
    lw=.6*(1-fw-mw) if lexical_hits else 0;bw=1-fw-lw-mw
    for identifier,hit in pool.items():
        info=relation(query,hit,qp,qm)
        score=(bw/(4+br[identifier]) if identifier in br else 0)+(fw/(4+fr[identifier]) if identifier in fr else 0)+(lw/(4+lr[identifier]) if identifier in lr else 0)
        if identifier in mr:
            score+=mw/(4+mr[identifier]);info['reasons'].append('公式字符结构相近，需核对括号及条件')
        if info['condition_conflict']:score-=.04
        if info['goal_mismatch']:score-=.025
        if info['level']=='background_reference':score-=.07
        output.append({**hit,'correspondence':info,
                       'correspondence_ranking':{'score':round(score,8),'base_rank':br.get(identifier),
                           'formula_rank':fr.get(identifier),'formula_weight':fw,'typed_lexical_rank':lr.get(identifier),
                           'typed_lexical_weight':lw,
                           'math_rank':mr.get(identifier),'math_weight':mw,
                           'policy':'bounded_rank_fusion_with_stated_structure_and_condition_penalties; development_default'}})
    output.sort(key=lambda h:(-h['correspondence_ranking']['score'],br.get(h['id'],10**6),h['id']))
    return output[:max(1,min(int(limit),20))]


def practice_order(query,rows,limit=3):
    """Prefer usable study analogues; keep mismatched questions visibly qualified."""
    qp=formula.profile(query);qm=mentions(query);annotated=[]
    for index,h in enumerate(rows):
        m=h.get('correspondence') or relation(query,h,qp,qm)
        level=m['level'];models=bool(m.get('shared_models'))
        priority=(0 if level=='method_related' and models else
                  1 if level=='structure_related' and models else
                  2 if level=='method_related' else 3 if level=='topic_related' else
                  4 if level=='different_goal' and models else
                  5 if level=='structure_related' else 6 if level=='different_goal' else
                  6 if level=='condition_difference' and set(m.get('shared_operations',[]))&GOALS else
                  7 if level=='semantic_candidate' else 9 if level=='background_reference' else 8)
        annotated.append((priority,-len(m.get('shared_operations',[])),index,{**h,'correspondence':m}))
    annotated.sort(key=lambda row:row[:3])
    return [r[3] for r in annotated[:limit]]


def navigation(query,hits,groups,study,explicit=False):
    qp=formula.profile(query);qm=mentions(query)
    for h in list(hits)+[h for rows in groups.values() for h in rows]:
        if 'correspondence' not in h:h['correspondence']=relation(query,h,qp,qm)
        if explicit and hits and h['id']==hits[0]['id']:
            h['correspondence']={**h['correspondence'],'level':'source_number','label':'按明确题号定位',
                                  'reasons':['输入中包含该教材题号，直接定位原记录']}
    topics=input_topics(query)
    # A source location is useful but must not masquerade as an inferred exam skill.
    if not topics:
        for h in hits[:2]:
            for t in study.get('record_topics',{}).get(h['id'],[])[:2]:
                if t['id'] not in {x['id'] for x in topics}:
                    topics.append({**t,'basis':'候选题原文线索','source_record_id':h['id'],
                                   'self_check':'先核对候选题是否与你的问题同方法，再回看该知识点。'})
    nodes=[{'id':'input-question','label':'当前题目','kind':'input'}]
    nodes += [{'id':t['id'],'label':t['label'],'kind':'topic','pdf_page':t['pdf_page']} for t in topics]
    selected=list({h['id']:h for rows in groups.values() for h in rows}.values())
    nodes += [{'id':h['id'],'label':h.get('label',h['id']),'kind':h['kind'],'pages':h.get('pages',[])} for h in selected]
    edges=[{'from':'input-question','to':t['id'],'kind':'topic_clue','basis':t['basis']} for t in topics]
    edges += [{'from':'input-question','to':h['id'],'kind':'candidate_correspondence','basis':h['correspondence']['label']} for h in selected]
    return {'goal':'question_to_examples_exercises_and_topics','input_topics':topics,'graph':{'nodes':nodes,'edges':edges},
            'self_check_notice':'这些是复习自查线索；仅凭上传题目无法判断你已经掌握或薄弱的知识点。',
            'matching_notice':'对应表示可供核对的相关题，不保证同题、同解法或相同参数。'}
