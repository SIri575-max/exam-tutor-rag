"""Formatting-tolerant mathematical n-grams; similarity is never equivalence."""
from collections import Counter
from functools import lru_cache
import math
import re
from formula_retrieval import normalize


@lru_cache(maxsize=4096)
def signature(text):
    # Retain symbol order, operators and numbers. Bracket removal is only an IR
    # feature: grouped expressions with different meanings can collide.
    raw=re.sub(r'例\s*\d+(?:\.\d+)+|^\s*\d+\s*[.、]','',text)
    raw=normalize(raw)
    compact=re.sub(r'[^a-z0-9+*/^<>=.!-]','',raw)
    grams=frozenset(compact[i:i+4] for i in range(max(0,len(compact)-3)))
    return compact,grams


@lru_cache(maxsize=3)
def index(items):
    entries=[(i,kind,chapter,section,signature(text)[1]) for i,kind,chapter,section,text in items]
    df=Counter(g for *_,grams in entries for g in grams)
    weights={g:math.log(1+(len(entries)+1)/(v+1)) for g,v in df.items()}
    return [(i,k,ch,se,g,sum(weights[x] for x in g)) for i,k,ch,se,g in entries],weights


def candidates(query,records,kind='all',chapter='',section='',limit=12):
    compact,q=signature(query)
    if len(compact)<18 or len(re.findall(r'[+*/^<>=-]',compact))<2:return []
    items=tuple((r['id'],r['kind'],r.get('chapter',''),r.get('section',''),r['question_text']) for r in records.values())
    entries,weights=index(items);score=[];query_total=sum(weights.get(g,1.) for g in q)
    for identifier,k,ch,se,grams,total in entries:
        if kind!='all' and k!=kind or chapter and ch!=chapter or section and se!=section:continue
        shared=q&grams
        intersection=sum(weights.get(g,1.) for g in shared)
        union=query_total+total-intersection
        value=intersection/union if union else 0.
        if value>=.12:score.append((value,identifier))
    score.sort(key=lambda v:(-v[0],v[1]));out=[]
    for value,identifier in score[:limit]:
        r=records[identifier];public={k:v for k,v in r.items() if k not in {'full_text','search_text','block_ids','stem_review'}}
        out.append({**public,'math_fingerprint_match':{'similarity':round(value,6),'equivalence_verified':False,
                    'boundary':'Formatting-tolerant symbol n-grams; check grouping, variable meaning and source OCR.'}})
    return out
