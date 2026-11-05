"""24 assistant-authored source-location checks; not a held-out or teaching evaluation."""
import json
from exercise_vectors import search, OUT
from process_full_book import write_json

CASES = [
 ('掷两个硬币，问正反面各出现一次的可能性','example-1.2.2'),
 ('彩票只有一张能中奖，第二位抽奖的人中奖机会多大','example-1.4.5'),
 ('十个人服用有效率百分之九十五的药，至少八个人治愈的概率','example-2.4.1'),
 ('正态随机变量均值108标准差3，计算102至117之间的概率和百分之九十五分位点','example-2.5.2'),
 ('已知二维离散联合分布表，求两变量和、差及最大值的分布','example-3.3.1'),
 ('在线段上独立任取两点，两点距离的平均值如何求','example-3.4.1'),
 ('用随机投点的蒙特卡罗方法估计零到一上的定积分','example-4.3.1'),
 ('机械轴加工误差由许多独立的微小随机因素叠加产生','example-4.4.1'),
 ('收集二十名青年的娱乐支出数据进行统计整理','example-5.3.1'),
 ('运动员十次射击只有第三和第六次未命中，研究命中率信息','example-5.5.1'),
 ('均匀总体U(0,theta)，未知上界theta的最大似然估计','example-6.3.5'),
 ('天平称物体九次，平均15.4克，已知标准差0.1，求质量置信区间','example-6.6.3'),
 ('甲地重复发送信号五次，乙地测量到8.05等数值，检验真实信号是不是8','example-7.2.1'),
 ('正态总体均值方差都未知，构造均值双侧假设的似然比检验','example-7.4.1'),
 ('养鸡试验比较三种饲料配方的增重效果','example-8.1.1'),
 ('用合金钢中的碳含量预测钢材强度，建立回归关系','example-8.4.1'),
 ('三个骰子投出后，最大数等于五或者不超过五的概率','mao3-1.2-12'),
 ('产品不良率一成，抽三件至多一件不合格的可能性','mao3-2.4-1'),
 ('均匀骰子掷两次，计算两个点数最小值的数学期望','mao3-3.4-1'),
 ('投骰子八十次，估计总点数超过三百的概率','mao3-4.4-5'),
 ('随机检查十页书的印刷错误数，求样本均值方差标准差','mao3-5.3-1'),
 ('总体均匀分布U(theta,2theta)，比较无偏相合估计与最大似然估计','mao3-6.3-7'),
 ('枪弹保存后抽九发测初速，检验平均初速是否比出厂时下降','mao3-7.2-1'),
 ('三十名大学生分组喝不同剂量咖啡因，用手指叩击次数做方差分析','mao3-8.1-6'),
]


def evaluate():
    details=[];summary={}
    for mode in ['bm25','vector','hybrid']:
        scores=[]
        for query,target in CASES:
            r=search(query,mode=mode,limit=8)
            ids=[x['id'] for x in r['hits']]
            rank=ids.index(target)+1 if target in ids else None
            scores.append(rank)
            details.append({'query':query,'target':target,'mode':mode,'rank_at_8':rank,'returned_ids':ids})
        summary[mode]={'cases':len(scores),'hit_at_1':sum(r==1 for r in scores),
                       'hit_at_5':sum(r is not None and r<=5 for r in scores),
                       'hit_at_8':sum(r is not None for r in scores),
                       'mrr_at_8':round(sum(1/r for r in scores if r)/len(scores),4)}
    report={'status':'completed','summary':summary,'details':details,
            'label_provenance':'assistant_authored_paraphrases_of_24_known_OCR_records; source_ids_are_candidate_labels',
            'selection':'16 examples + 8 exercises; all 8 chapters; selected after initial UI preset smoke checks',
            'boundary':'Small source-location self-check only; no held-out labels, no teacher evaluation, no generalization or teaching claims.'}
    write_json(OUT/'source-location-evaluation.json',report)
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    return report


if __name__=='__main__':evaluate()
