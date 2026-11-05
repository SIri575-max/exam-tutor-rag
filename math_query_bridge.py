"""Small, explicit mathematical query aliases; never inject distribution answers."""
import re


def profile(text):
    compact=re.sub(r'\s+','',text)
    normal=bool(re.search(r'正态|N\(',compact))
    known_mean=bool(re.search(r'均值.{0,5}已知|\\mu.{0,8}(?:是)?已知',compact))
    if re.search(r'均值.{0,3}未知',compact):known_mean=False
    squared=bool(re.search(r'离差平方和|偏差平方和|\\sum.{0,150}\\mu.{0,30}\^\{?2',compact))
    return {'normal':normal,'known_population_mean':known_mean,'squared_deviations_sum':squared}


def expand(query):
    flags=profile(query)
    if all(flags.values()) and len(query)<=2800:
        return {'query':query+r' 正态总体 N(\mu,\sigma^{2}) \mu 已知 T=\sum_{i=1}^{n}(x_i-\mu)^{2}',
                'rule':'normal_known_mean_squared_deviations',
                'basis':flags,'boundary':'Adds a symbolic spelling of the explicit query conditions, not an answer distribution.'}
    return None


def merge(base,extra):
    by_id={x['id']:x for x in base};ranks={}
    for sequence in (base,extra):
        for rank,item in enumerate(sequence,1):
            by_id[item['id']]=item;ranks[item['id']]=ranks.get(item['id'],0)+1/(60+rank)
    # Matching all explicitly requested conditions takes priority. This is a
    # narrow deterministic gate, not a trained mathematical reranker.
    return sorted(by_id.values(),key=lambda x:(-int(all(profile(x['question_text']).values())),-ranks[x['id']],x['id']))
