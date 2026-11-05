"""Source-anchored development probes for typed formulas, not a held-out exam."""
import json
from pathlib import Path
from exercise_vectors import search, status
from full_book_tutor import retrieve
from process_full_book import write_json
from sync_sources import ROOT

CASES=[
 ('unicode_order', 'Y₁,Y₂,Y₃ ~ U(0,ϑ)，比较 (4/3)max(Y₁,Y₂,Y₃) 与 4min(Y₁,Y₂,Y₃) 的无偏性和方差','mao3-6.1-6'),
 ('renamed_order',r'V_1,V_2,V_3\sim U(0,\beta),\frac{4}{3}V_{(3)} 与4V_{(1)}，哪个估计更有效？','mao3-6.1-6'),
 ('ascii_shift','f(t|a)=exp(-(t-a)) I(t>a)，n个独立样本，求a的置信区间','mao3-6.6-19'),
 ('tex_shift',r'f(z|b)=e^{-(z-b)}I_{z>b}, 求b的置信区间','mao3-6.6-19'),
 ('ascii_negbin','f(y|q)=C(y-1,r-1)q^r(1-q)^(y-r)，先验Beta(α,β)','mao3-6.5-13'),
 ('tex_negbin',r'f(z|q)=\binom{z-1}{m-1}q^{m}(1-q)^{z-m}，求共轭先验','mao3-6.5-13'),
]


def run():
    rows=[]
    for name,query,expected in CASES:
        base=search(query,kind='exercise',limit=8)
        result=retrieve(query,kind='exercise',limit=8)
        b=[r['id'] for r in base['hits']];a=[r['id'] for r in result['hits']]
        rows.append({'id':name,'query':query,'expected_source_record':expected,
                     'raw_hybrid_ids':b,'formula_ids':a,
                     'raw_rank_at_8':b.index(expected)+1 if expected in b else None,
                     'formula_rank_at_8':a.index(expected)+1 if expected in a else None,
                     'formula_analysis':result.get('formula_analysis'),'route':result['route']})
    changed=retrieve('Z_i~U(0,a),n=4，比较 (2/3)max(Z_1,Z_2,Z_3,Z_4) 与 4min(Z_1,Z_2,Z_3,Z_4) 的无偏性',kind='exercise')
    old=next((r for r in changed['hits'] if r['id']=='mao3-6.1-6'),None)
    ambiguity=retrieve('p(x;λ)=λ exp(-λx),x>0',kind='exercise')
    info=status();report={'date':'2026-10-27','collection_sha256':info['collection_sha256'],
           'source_anchored_development_probes':rows,
           'raw_hybrid_top1':sum(r['raw_rank_at_8']==1 for r in rows),
           'formula_top1':sum(r['formula_rank_at_8']==1 for r in rows),
           'changed_conditions':{'query':changed['query'],'source_candidate_shown':old is not None,
                                 'differences':old.get('formula_match',{}).get('differences',[]) if old else []},
           'ambiguous_density':{'query':ambiguity['query'],'returned_ids':[r['id'] for r in ambiguity['hits']],
                                'clarifications':ambiguity['clarifications']},
           'boundary':'Six assistant-labelled source-location development variants used during implementation; not independent accuracy, CAS equivalence, solved-answer quality or teaching effectiveness.'}
    out=ROOT/'data/private/formula-retrieval';out.mkdir(exist_ok=True)
    write_json(out/'development-probes-2026-10-27.json',report)
    print(json.dumps({k:v for k,v in report.items() if k!='source_anchored_development_probes'},ensure_ascii=False,indent=2))
    return report


if __name__=='__main__':run()
