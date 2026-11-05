"""Bounded, rule-routed study retrieval. No simulated LLM reasoning or answers."""
import re
import time
import exercise_vectors as vectors
from question_knowledge import study_context, mentions
from math_query_bridge import expand as math_expand, merge as math_merge
from problem_conditions import missing_estimation_context
import source_properties
import formula_retrieval
import problem_correspondence as correspondence
import math_fingerprint
from retrieval_policy import DEFAULT_BUDGET, RetrievalBudget


def explicit_id(query):
    match=re.search(r'例\s*([1-8]\s*\.\s*\d+\s*\.\s*\d+)',query)
    if match:return 'example-'+re.sub(r'\s+','',match.group(1))
    match=re.search(r'习题\s*([1-8]\s*\.\s*\d+)\s*(?:第\s*)?(\d+)\s*题',query)
    if match:return 'mao3-'+re.sub(r'\s+','',match.group(1))+'-'+str(int(match.group(2)))
    return None


def scope_cues(query):
    if mentions(query) or re.search(r'概率|分布|统计|样本|估计|检验|事件|骰|硬币|摸球|抽球|抽样|排列|组合|随机|机床|饲料|回归|置信|独立|数学|期望|求证|积分|极限|方差|均值|似然|相关|掷|抛|不合格|合格品|正态|均匀|泊松|样本量|[XYZxyz]\s*[=~～]|\\(?:theta|sigma|mu|frac)|\d.*(?:求|计算|问|比较|至少|至多|多少)',query,re.I):return True
    # Short symbolic questions need not repeat the words "probability" or
    # "hypothesis test". Do not accept arbitrary algebra merely for containing =.
    symbolic=formula_retrieval.normalize(query)
    return bool(re.search(r'\\(?:cup|cap|subset(?:eq)?|supset(?:eq)?)(?![a-zA-Z])',query) or re.search(r'(?<![a-z])p\([^)]{1,160}\)|[∪∩⊂⊃]|xrightarrow\{[pld]\}|(?<![a-z])h_?[01](?!\d)|fisher|费舍尔|信息量|蒙特卡洛|montecarlo|第一类错误|第二类错误|两类错误|原假设|备择假设',symbolic,re.I))


def retrieve(query,mode='hybrid',kind='all',chapter='',section='',limit=8,adaptive=True,budget=DEFAULT_BUDGET):
    if not isinstance(budget,RetrievalBudget):raise ValueError('无效检索预算')
    if not isinstance(query,str) or not 3<=len(query.strip())<=3000:raise ValueError('请输入3–3000字的题目或描述')
    if mode not in {'bm25','vector','hybrid'} or kind not in {'all','exercise','example'}:raise ValueError('无效检索选项')
    started=time.monotonic();trace=[];identifier=explicit_id(query)
    formula=formula_retrieval.profile(query) if not identifier else {'active':False,'formula_like':False}
    missing=missing_estimation_context(query) if not identifier else []
    if missing:
        return {'query':query,'mode':mode,'hits':[],'filtered_records':0,'elapsed_seconds':0,
                'route':'clarify_conditions','status':'needs_problem_context',
                'message':'当前缺少总体模型和待估参数，请先补充条件，再定位题目。',
                'study':{'query_topics':[],'record_topics':{},'readings':[],'references':[], 'graph':{'nodes':[],'edges':[]}},
                'practice_groups':{},'trace':[{'step':'condition_check','basis':'generic_estimation_request','retrieval_executed':False}],
                'clarifications':missing,'llm_used':False}
    properties=[]
    if not identifier and not formula['active'] and not scope_cues(query) and not chapter and not section:
        return {'query':query,'mode':mode,'hits':[],'filtered_records':0,'elapsed_seconds':0,
                'route':'clarify_problem','status':'needs_problem_context',
                'message':'请补充统计学题干、已知条件或教材题号；当前没有足够线索定位题目。',
                'study':{'query_topics':[],'record_topics':{},'readings':[],'references':[], 'graph':{'nodes':[],'edges':[]}},
                'practice_groups':{},'trace':[{'step':'scope_check','basis':'rule_cues_missing','retrieval_executed':False}],
                'clarifications':['请提供题干、总体分布、样本条件及要求。'],
                'formula_analysis':formula_retrieval.describe(formula) if formula['formula_like'] else None,'llm_used':False}
    if identifier:
        item=vectors.record(identifier)
        if kind!='all' and item['kind']!=kind or chapter and item['chapter']!=chapter or section and item['section']!=section:
            raise ValueError('题号与选择的题目类型或章节不一致')
        public={k:v for k,v in item.items() if k not in {'full_text','search_text','block_ids','stem_review'}}
        public.update(matched_chunk=None,matched_text=item['question_text'],cosine=None,bm25=None,rrf=None,nearby_other_type=[])
        result={'query':query,'mode':mode,'hits':[public],'filtered_records':1,'reference_answers_searched':False,
                'route':'source_number_lookup','status':'candidate_matches'}
        trace.append({'step':'source_number_lookup','record_id':identifier,'embedding_executed':False})
    else:
        search_query=query
        if adaptive and formula['active'] and len(query)<2600:
            details=formula_retrieval.describe(formula)
            search_query=query+' '+' '.join(details['models']+details['operations'])
        result=vectors.search(search_query,mode,kind,chapter,section,budget.recall_k if adaptive else limit)
        result['query']=query
        recall_pool=list(result['hits'])
        result.update(route='single_retrieval',status='candidate_matches')
        trace.append({'step':'first_retrieval','query':search_query,'input_query':query,'method':mode,
                      'requested_k':budget.recall_k if adaptive else limit,'records':len(result['hits']),
                      'unit':'unique_parent_questions_after_exact_scoring_and_fusion'})
        bridge=math_expand(query) if adaptive and not formula['active'] else None
        if adaptive and formula['active']:
            formula_base_hits=list(result['hits'])
            matched,_=formula_retrieval.candidates(query,vectors.snapshot()[1],kind,chapter,section,
                                                  {h['id']:i for i,h in enumerate(result['hits'])},budget.formula_k)
            result['formula_analysis']=formula_retrieval.describe(formula)
            result['hits']=correspondence.rank(query,result['hits'],matched,limit)
            result['route']='formula_assisted_fusion'
            if not matched:
                result['formula_analysis']['missing_context'].append('当前范围未找到清晰的公式特征匹配，请补充题干或调整章节。')
            trace.append({'step':'formula_structure_matching','method':'explicit_statistical_patterns_and_stated_conditions',
                          'query_features':result['formula_analysis'],'source_scope':'question_stems_only',
                          'consumed_ids':[h['id'] for h in result['hits']],
                          'boundary':'Formula ranks assist semantic recall; not mathematical equivalence or answer reuse.'})
        elif bridge:
            expanded=vectors.search(bridge['query'],mode,kind,chapter,section,budget.recall_k)
            result['hits']=math_merge(result['hits'],expanded['hits'])[:max(1,min(int(limit),20))]
            result['route']='explicit_math_query_bridge'
            trace.append({'step':'mathematical_alias_retrieval','round':2,**bridge,
                          'consumed_ids':[x['id'] for x in result['hits']]})
        elif adaptive and source_properties.requested(query):
            properties=source_properties.lookup(query,vectors.snapshot()[1])
            if properties:
                records=vectors.snapshot()[1];preferred=[]
                for evidence in properties:
                    r=records[evidence['record_id']]
                    if (kind=='all' or r['kind']==kind) and (not chapter or r['chapter']==chapter) and (not section or r['section']==section):
                        public={k:v for k,v in r.items() if k not in {'full_text','search_text','block_ids','stem_review'}}
                        public.update(matched_chunk=None,matched_text=evidence['text'],cosine=None,bm25=None,rrf=None,
                                      match_basis='literal_property_in_original_explanation')
                        preferred.append(public)
                ids={r['id'] for r in preferred}
                result['hits']=(preferred+[r for r in result['hits'] if r['id'] not in ids])[:max(1,min(int(limit),20))]
                result['route']='source_property_lookup'
                trace.append({'step':'source_property_lookup','round':2,
                              'source_blocks':[e['block_id'] for e in properties],
                              'consumed_ids':[r['id'] for r in preferred],
                              'boundary':'Property paragraph lookup; question vector inputs unchanged.'})
    if adaptive and not identifier and result['route']=='single_retrieval':
        result['hits']=correspondence.rank(query,result['hits'],limit=limit)
    result['hits']=result['hits'][:max(1,min(int(limit),20))]
    hits=result['hits'];groups={k:[x for x in hits if x['kind']==k][:budget.practice_k] for k in ['example','exercise']}
    if adaptive and not identifier and kind=='all' and result['route'] not in {'explicit_math_query_bridge','source_property_lookup'}:
        # Retrieve structure candidates for each kind, so exercises do not crowd
        # source-linked examples out of a global top-k pool.
        for target in ['example','exercise']:
            typed_base=[h for h in recall_pool if h['kind']==target]
            typed_formula=[]
            if formula.get('active'):
                typed_formula,_=formula_retrieval.candidates(query,vectors.snapshot()[1],target,chapter,section,
                                                            {h['id']:i for i,h in enumerate(typed_base)},budget.formula_k)
            lexical_result=vectors.search(query,'bm25',target,chapter,section,budget.typed_lexical_k)
            typed_lexical=[h for h in lexical_result['hits'] if h['kind']==target]
            math_hits=math_fingerprint.candidates(query,vectors.snapshot()[1],target,chapter,section,budget.math_k) if formula.get('formula_like') else []
            ranked=correspondence.rank(query,typed_base,typed_formula,20,typed_lexical,math_hits) if typed_base or typed_formula or typed_lexical or math_hits else []
            groups[target]=correspondence.practice_order(query,ranked,budget.practice_k)
            trace.append({'step':'typed_candidate_reranking','kind':target,
                          'base_count':len(typed_base),'formula_count':len(typed_formula),
                          'lexical_count':len(typed_lexical),'math_count':len(math_hits),
                          'candidate_union_count':len({h['id'] for h in typed_base+typed_formula+typed_lexical+math_hits}),
                          'candidate_ids':sorted({h['id'] for h in typed_base+typed_formula+typed_lexical+math_hits}),
                          'selected_count':len(groups[target]),'selected_ids':[h['id'] for h in groups[target]]})
        trace.append({'step':'typed_lexical_candidate_union','round':2,'query':query,
                      'consumed_ids':list(dict.fromkeys(h['id'] for rows in groups.values() for h in rows)),
                      'basis':'Preserve keyword candidates separately for examples and exercises; scores are not relevance labels.'})
    if adaptive and kind=='all' and hits and not any(t['step'] in {'mathematical_alias_retrieval','source_property_lookup'} for t in trace):
        expansion_query=item['question_text'] if identifier else query
        expansion_chapter=chapter or (item['chapter'] if identifier else '')
        expansion_section=section or (item['section'] if identifier and not item['section'].endswith('.0') else '')
        for target in ['example','exercise']:
            if len(groups[target])>=min(2,budget.practice_k):continue
            # A real second retrieval supplies the missing type. It is neither
            # a trained complexity classifier nor an invented reasoning trace.
            extra=vectors.search(expansion_query,mode,target,expansion_chapter,expansion_section,budget.recall_k)
            extra['hits']=correspondence.rank(expansion_query,extra['hits'],limit=budget.practice_k)
            existing={x['id'] for x in groups[target]}
            accepted=[x for x in extra['hits'] if x['id'] not in existing][:budget.practice_k-len(groups[target])]
            groups[target]+=accepted
            trace.append({'step':'type_balancing_retrieval','round':2,'query':expansion_query,'kind':target,
                          'consumed_ids':[x['id'] for x in accepted]})
        if any(t['step']=='type_balancing_retrieval' for t in trace) and result['route']=='single_retrieval':result['route']='bounded_type_balancing'
    for target in groups:
        if not identifier:groups[target]=correspondence.practice_order(query,groups[target],budget.practice_k)
    context_hits=list({h['id']:h for h in hits[:budget.context_main_k]+groups['example'][:budget.context_per_kind_k]+groups['exercise'][:budget.context_per_kind_k]}.values())
    result['study']=study_context(context_hits,query)
    result['study']['property_evidence']=properties
    result['correspondence']=correspondence.navigation(query,hits,groups,result['study'],bool(identifier))
    result['practice_groups']=groups;result['trace']=trace
    result['retrieval_budget']=budget.describe(limit)
    result['retrieval_budget']['adaptive_enabled']=adaptive
    result['retrieval_budget']['actual_detailed_count']=len(hits)
    result['retrieval_budget']['actual_practice_counts']={k:len(v) for k,v in groups.items()}
    result['clarifications']=[]
    result['clarifications'].extend(result.get('formula_analysis',{}).get('missing_context',[]))
    if len(query.strip())<16 and not identifier:result['clarifications'].append('当前描述较短，请补充总体分布、样本及要求，以区分相近题型。')
    if any('opening_only' in h.get('stem_boundary','') for h in context_hits):result['clarifications'].append('部分例题仅有开头摘要，请先回看原页补齐条件。')
    result['elapsed_seconds']=round(time.monotonic()-started,3);result['llm_used']=False
    result['message']='按相关例题、课后题与知识点组织复习路径；推荐理由和条件差异供核对，知识点线索不等于个人薄弱点诊断。'
    return result
