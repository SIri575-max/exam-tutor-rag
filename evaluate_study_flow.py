"""New post-implementation source-location probes + study behavior smoke checks."""
import json
from pathlib import Path
from full_book_tutor import retrieve
from exercise_vectors import OUT, snapshot
from question_knowledge import current
from process_full_book import write_json

PROBES=[
 ('三十六只灯泡里只有四只为6W，任取三只，至少一只6W的概率','example-1.3.1'),
 ('离散随机变量取负二到二，给了分布列，怎样求Y=X平方加X的分布','example-2.6.1'),
 ('相互独立的一组随机变量，求它们最大值的分布函数和密度','example-3.3.4'),
 ('一百个独立部件每个可靠性0.9，至少85个工作时系统才正常，求系统可靠性','example-4.4.5'),
 ('正态样本的总体均值已知，样本对该均值的离差平方和服从什么分布','example-5.4.1'),
 ('十二只轮胎的寿命是正态样本，求平均寿命的百分之九十五置信区间','example-6.6.5'),
 ('依次测二十根电缆的耐压值，检验测量是否受非随机因素干扰','example-7.6.1'),
 ('十八组动物的质量和体积，求利用质量预测体积的回归关系','example-8.4.5'),
]


def evaluate():
    details=[]
    for query,target in PROBES:
        r=retrieve(query);ids=[x['id'] for x in r['hits']]
        details.append({'query':query,'target':target,'rank_at_8':ids.index(target)+1 if target in ids else None,
                        'returned_ids':ids,'route':r['route']})
    checks={}
    for query in ['今天晚饭吃什么比较好','请推荐一部好看的电影','帮我写一份请假邮件']:
        checks[query]=retrieve(query)['status']=='needs_problem_context'
    direct=retrieve('例7.5.2',adaptive=False)
    checks['direct_lookup']=direct['route']=='source_number_lookup'
    checks['restored_10_values']='539.35 179.49 782.93 561.10 286.80' in direct['hits'][0]['question_text']
    r=retrieve('掷三颗骰子，求最大点数恰好等于5的概率')
    checks['both_types_present']=all(r['practice_groups'].get(k) for k in ['exercise','example'])
    checks['actual_second_round_consumed']=any(t.get('round')==2 and t.get('consumed_ids') for t in r['trace'])
    ref=retrieve('例8.1.2',adaptive=False)
    checks['literal_preceding_example']=any(x['id']=='example-8.1.1' for x in ref['study']['references'])
    graph=current()
    result={'status':'passed' if all(checks.values()) else 'failed','checks':checks,
            'new_location_probes':details,'hit_at_1':sum(d['rank_at_8']==1 for d in details),
            'hit_at_8':sum(d['rank_at_8'] is not None for d in details),'probe_count':len(details),
            'collection_sha256':graph['report']['collection_sha256'],
            'boundary':'Eight assistant-authored regression probes, one per chapter, not teacher labels or independent student outcomes. The mean-known sum-of-squares miss was used to develop the explicit mathematical query bridge; the pre-change report is preserved.'}
    target='study-flow-after-math-bridge.json' if (OUT/'study-flow-before-math-bridge.json').exists() else 'study-flow-evaluation.json'
    write_json(OUT/target,result)
    print(json.dumps({k:v for k,v in result.items() if k!='new_location_probes'},ensure_ascii=False,indent=2))
    if not all(checks.values()):raise SystemExit(1)
    return result


if __name__=='__main__':evaluate()
