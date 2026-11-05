"""Explicit statistical formula patterns and source-stem matching, not a CAS.

Variable names may differ. Numeric constants, support and stated conditions are
kept for comparison; a structural match never certifies equivalent questions.
"""
from functools import lru_cache
import re
import unicodedata

GREEK={'α':'alpha','β':'beta','γ':'gamma','λ':'lambda','μ':'mu','σ':'sigma','θ':'theta','ϑ':'theta','π':'pi',
       'η':'eta','ρ':'rho','τ':'tau','κ':'kappa','ν':'nu','ξ':'xi','δ':'delta','φ':'phi','ω':'omega'}
SUBS=str.maketrans('₀₁₂₃₄₅₆₇₈₉','0123456789')
MODEL_LABELS={'uniform':'均匀分布','normal':'正态分布','exponential':'指数分布',
              'shifted_exponential':'平移指数密度','negative_binomial':'负二项分布',
              'binomial':'二项分布','poisson':'泊松分布','gamma':'伽马分布','beta':'贝塔分布',
              'chi_square':'卡方分布','student_t':'t分布'}
OP_LABELS={'minimum':'样本最小值','maximum':'样本最大值','linear_combination':'线性组合',
           'squared_sum':'平方和','sample_mean':'样本均值','unbiased':'无偏性',
           'variance':'方差','confidence':'置信区间','mle':'最大似然估计','conjugacy':'共轭先验',
           'prior_beta':'Beta先验/共轭族','expectation':'数学期望','covariance':'协方差','correlation':'相关系数'}


def group(text,start):
    """Return a balanced brace/parenthesis group and its end offset."""
    if start>=len(text) or text[start] not in '({':return None
    stack=[];pairs={')':'(','}':'{'}
    for i in range(start,len(text)):
        c=text[i]
        if c in '({':stack.append(c)
        elif c in ')}':
            if not stack or stack.pop()!=pairs[c]:return None
            if not stack:return text[start+1:i],i+1
    return None


def normalize(text):
    text=re.sub(r'([A-Za-z])([₀₁₂₃₄₅₆₇₈₉]+)',lambda m:m[1]+'_'+m[2].translate(SUBS),text)
    text=unicodedata.normalize('NFKC',text)
    for a,b in GREEK.items():text=text.replace(a,'\\'+b)
    text=text.replace('Σ',r'\sum').replace('∑',r'\sum').replace('∏',r'\prod').replace('∞',r'\infty')
    text=text.replace('≤','<=').replace('≥','>=').replace('−','-').replace('～','~').replace('∼','~')
    text=re.sub(r'\\sim(?![a-zA-Z])','~',text)
    text=re.sub(r'\\(?:cdot|times)(?![a-zA-Z])','*',text)
    text=re.sub(r'\\(?:geqslant|geq|ge)(?![a-zA-Z])','>=',text)
    text=re.sub(r'\\(?:leqslant|leq|le)(?![a-zA-Z])','<=',text)
    text=re.sub(r'\\(?:left|right|bigg?|Bigg?|quad|qquad)(?![a-zA-Z])|\\[!,;]', '',text)
    text=re.sub(r'\\(?:mathrm|operatorname|mathbf|boldsymbol|mathsf|mathbb)\s*\{([^{}]*)\}',r'\1',text)
    text=re.sub(r'\s+','',text).replace('，',',').replace('；',';')
    # Flatten only well-formed TeX fraction/binomial groups; never evaluate them.
    for _ in range(20):
        match=re.search(r'\\(frac|dfrac|tfrac|binom)',text)
        if not match:break
        first=group(text,match.end())
        second=group(text,first[1]) if first else None
        if not second:break
        replacement=('choose('+first[0]+','+second[0]+')' if match[1]=='binom' else '('+first[0]+')/('+second[0]+')')
        text=text[:match.start()]+replacement+text[second[1]:]
    text=text.lower().replace('\\','')
    text=re.sub(r'_\{([^{}]*)\}',r'_\1',text)
    text=re.sub(r'\^\{([^{}]*)\}',r'^(\1)',text)
    return text


def calls(text,name):
    result=[]
    prefix='' if name=='exp' else r'(?<![a-z])'
    for m in re.finditer(prefix+re.escape(name)+r'\(',text):
        part=group(text,m.end()-1)
        if not part:continue
        inside=part[0];depth=0;split=[];at=0
        for i,c in enumerate(inside):
            if c in '({':depth+=1
            elif c in ')}':depth-=1
            elif c==',' and depth==0:split.append(inside[at:i]);at=i+1
        split.append(inside[at:]);result.append(split)
    return result


@lru_cache(maxsize=3500)
def profile(text):
    c=normalize(text);models=set();ops=set();conditions={}
    raw=re.sub(r'\s+','',unicodedata.normalize('NFKC',text))
    sample=re.search(r'(?:容量为|样本量(?:为|=)?|(?<![a-zA-Z])n=)(\d+)',raw)
    if sample:conditions['sample_size']=sample[1]
    elif not re.search(r'cdots|ldots|dots|\.\.\.|⋯|…|_[nm](?![a-z])',c):
        indices=re.search(r'i=1(?:,\d+){1,10}',c)
        listing=re.search(r'([a-z])_?1,\1_?2,\1_?3(?:,\1_?\d+)*',c)
        values=[int(v) for v in re.findall(r'\d+',indices[0] if indices else listing[0] if listing else '')]
        if values and values==list(range(1,len(values)+1)):conditions['sample_size']=str(len(values))
    uniform=calls(c,'u')
    if uniform or '均匀分布' in c:models.add('uniform')
    if uniform and len(uniform[0])==2:
        lo,hi=uniform[0]
        conditions['support_expression']=lo+','+hi
        if lo=='0':conditions['support']='zero_to_parameter'
        elif re.fullmatch(r'2\*?'+re.escape(lo),hi):conditions['support']='parameter_to_double'
        elif re.fullmatch(re.escape(lo)+r'\+1',hi):conditions['support']='shift_unit_width'
        else:conditions['support']='other_explicit_bounds'
    normal=calls(c,'n')
    # n(n+1) is arithmetic, not a normal-distribution declaration.
    normal=[v for v in normal if len(v)==2]
    if normal or '正态' in c:models.add('normal')
    negative=bool('负二项' in c or (re.search(r'(?:choose|c)\([^,]+-1,[^)]+-1\)',c) and re.search(r'\(1-[a-z]+\)\^',c)))
    if negative:models.add('negative_binomial')
    elif '二项分布' in c or calls(c,'b') or calls(c,'bin'):models.add('binomial')
    # p(x) is also the conventional name of an arbitrary density. Only an
    # explicit distribution declaration permits the short Poisson name P().
    if '泊松' in c or 'poisson' in c or re.search(r'(?:~|服从)p\(',c):models.add('poisson')
    if '指数分布' in c or re.search(r'(?:~|服从)exp\(',c):models.add('exponential')
    # exp(-(t-a)) and e^{-(x-theta)} need no variable-name convention.
    exponents=[v[0] for v in calls(c,'exp') if len(v)==1]
    for m in re.finditer(r'e\^',c):
        part=group(c,m.end())
        if part:exponents.append(part[0])
        else:
            m2=re.match(r'-[a-z_0-9]+',c[m.end():])
            if m2:exponents.append(m2[0])
    for exponent in exponents:
        if re.fullmatch(r'-[({]?[a-z]+-[a-z]+[)}]?',exponent) and re.search(r'[a-z]+>=?[a-z]+',c):
            models.update(['exponential','shifted_exponential']);conditions['exponential_rate']='one'
        elif re.fullmatch(r'-[a-z]+\*?[a-z]+',exponent) and re.search(r'[a-z]+>0',c):models.add('exponential')
    if '伽马' in c or 'gamma分布' in c or any(len(v)==2 for v in calls(c,'gamma')+calls(c,'ga')):models.add('gamma')
    beta=bool('贝塔' in c or 'beta分布' in c or any(len(v)==2 for v in calls(c,'beta')+calls(c,'be')))
    if beta:
        if '先验' in c or '共轭' in c:ops.add('prior_beta')
        else:models.add('beta')
    if '先验' in c and len(models)>1:models.discard('gamma')
    if '卡方' in c or 'chi' in c:models.add('chi_square')
    if 't分布' in c:models.add('student_t')
    if re.search(r'min[({]|最小值|[a-z]_\(1\)',c):ops.add('minimum')
    if re.search(r'max[({]|最大值|[a-z]_\((?:n|m)\)',c) or conditions.get('sample_size') and re.search(r'[a-z]_\('+re.escape(conditions['sample_size'])+r'\)',c):ops.add('maximum')
    if 'sum' in c and re.search(r'(?:\)|\})\^\(?2\)?|平方和',c):ops.add('squared_sum')
    if re.search(r'bar\{|样本均值|样本平均',c) or 'sum' in c and re.search(r'/\(?n\)?',c):ops.add('sample_mean')
    if ('sum' in c and re.search(r'[abwc]_i',c) and re.search(r'[xyz]_i',c)) or (
        len(re.findall(r'[xyz]_\d',c))>=3 and len(re.findall(r'\+',c))>=2 and re.search(r'/|frac',text)):
        ops.add('linear_combination')
    for key,pattern in [('unbiased',r'无偏'),('variance',r'(?<!协)方差|var\(|更有效|有效性'),('confidence',r'置信|confidence'),
                        ('mle',r'最大似然|极大似然|mle'),('conjugacy',r'共轭'),
                        ('expectation',r'数学期望|期望值|(?<![a-z])e[\[(]'),
                        ('covariance',r'协方差|cov\('),('correlation',r'相关系数|corr\(')]:
        if re.search(pattern,c):ops.add(key)
    if re.search(r'均值.{0,4}未知|mu.{0,4}未知',c):conditions['mean']='unknown'
    elif re.search(r'均值.{0,4}已知|mu.{0,4}(?:是)?已知',c):conditions['mean']='known'
    if normal and len(normal[0])==2 and re.fullmatch(r'[a-z]+',normal[0][0]):
        symbol=re.escape(normal[0][0])
        if re.search(symbol+r'(?:为|是)?未知|未知(?:参数)?'+symbol,c):conditions['mean']='unknown'
        elif re.search(symbol+r'(?:为|是)?已知|已知(?:参数)?'+symbol,c):conditions['mean']='known'
    fractions=set(re.findall(r'(?<!\d)([1-9]\d*)/([1-9]\d*)(?!\d)',c))
    fractions.update(re.findall(r'\((\d+)\)/\((\d+)\)',c))
    if fractions:conditions['fractions']=sorted('/'.join(v) for v in fractions)
    active=bool(models or ops&{'linear_combination','squared_sum','sample_mean','minimum','maximum','variance','expectation','covariance','correlation'})
    formula_like=bool(re.search(r'\\(?:sum|frac|theta|sigma|mu|binom|sim|min|max)|[=~^∼～]|[Σ∑∏₁₂₃]|_[a-z0-9({]|(?:min|max|var|cov|corr|e)[\[({]',text,re.I))
    return {'canonical':c,'models':sorted(models),'operations':sorted(ops),'conditions':conditions,
            'active':active and formula_like,'formula_like':formula_like}


def comparison(query,candidate):
    qm,cm=set(query['models']),set(candidate['models']);qo,co=set(query['operations']),set(candidate['operations'])
    shared_m=qm&cm;shared_o=qo&co
    reasons=[MODEL_LABELS[k] for k in sorted(shared_m) if k!='exponential' or 'shifted_exponential' not in shared_m]
    reasons += [OP_LABELS[k] for k in sorted(shared_o)]
    differences=[];score=0.
    if qm:
        score+=8*len(shared_m)
        if not shared_m:score-=12
        if 'shifted_exponential' in qm and 'shifted_exponential' not in cm:score-=6
    score+=sum(3 if k in {'minimum','maximum','linear_combination','squared_sum','sample_mean','variance','expectation','covariance','correlation'} else 1.5 for k in shared_o)
    for k,label in [('support','支持区间形式'),('mean','均值已知/未知'),('sample_size','样本量'),('exponential_rate','指数速率')]:
        q=query['conditions'].get(k);c=candidate['conditions'].get(k)
        if q is not None and c is not None:
            if q==c:score+=2
            else:score-=4;differences.append(label+'不同，需重新核对')
        elif q is not None and c is None:differences.append('候选题中尚未识别到相同的'+label+'条件')
    qf=set(query['conditions'].get('fractions',[]));cf=set(candidate['conditions'].get('fractions',[]))
    if qf and cf:
        if qf==cf:score+=2;reasons.append('出现相同的分数系数')
        elif not qf<=cf:score-=2;differences.append('分数系数不同，不能直接套用原题数值')
    goals=(qo-co)&{'unbiased','variance','confidence','mle','conjugacy'}
    if goals:differences.append('候选题干未显式标明：'+'、'.join(OP_LABELS[k] for k in sorted(goals)))
    meaningful=bool(shared_m or shared_o&{'linear_combination','squared_sum','sample_mean','minimum','maximum','variance','expectation','covariance','correlation'})
    return {'score':round(score,3),'reasons':reasons,'differences':differences,'eligible':meaningful and score>=(5 if qm else 3)}


def candidates(query,records,kind='all',chapter='',section='',base_ranks=None,limit=8):
    p=profile(query);base_ranks=base_ranks or {};rows=[]
    if not p['active']:return [],p
    for record in records.values():
        if kind!='all' and record['kind']!=kind or chapter and record['chapter']!=chapter or section and record['section']!=section:continue
        evidence=comparison(p,profile(record['question_text']))
        if evidence['eligible']:rows.append((evidence,record))
    rows.sort(key=lambda v:(-v[0]['score'],base_ranks.get(v[1]['id'],10000),v[1]['id']))
    hits=[]
    for evidence,r in rows[:limit]:
        public={k:v for k,v in r.items() if k not in {'full_text','search_text','block_ids','stem_review'}}
        public.update(matched_text=r['question_text'],matched_chunk=None,cosine=None,bm25=None,rrf=None,
                      formula_match={**evidence,'status':'structural_candidate_not_equivalence',
                                     'boundary':'Pattern and explicit conditions only; variable roles, omitted conditions and OCR require source checking.'})
        hits.append(public)
    return hits,p


def describe(p):
    return {'models':[MODEL_LABELS[k] for k in p['models']],
            'operations':[OP_LABELS[k] for k in p['operations']],
            'conditions':p['conditions'],
            'missing_context':(['请补充样本分布或独立性等条件，以区分结构相近的题目。'] if not p['models'] else [])+
                              (['请补充所求量，例如比较无偏性、求最大似然估计或构造置信区间。']
                               if not set(p['operations'])&{'unbiased','variance','confidence','mle','conjugacy'} else []),
            'boundary':'候选结果按公式特征与显式条件匹配，等价性需另行核对。'}
