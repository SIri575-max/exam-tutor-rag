"""Transcribe the supplied mind map into a source-linked future graph plan."""
import hashlib
import json
from pathlib import Path
from book_structure import structure

ROOT = Path(__file__).resolve().parent
# Labels and child topics transcribed by the assistant after inspecting the PDF.
# Section links are proposed reading locations, never approved exam-skill edges.
STATISTICS = [
('调查的组织与实施','不重要',[],[]),
('概率抽样与非概率抽样','不重要',['概率抽样','非概率抽样','两种抽样的推断逻辑差异','抽样误差的来源与可控性'],[]),
('数据的预处理','不重要',[],[]),
('用图表展示定性、定量数据','考过，综合性强',['定性数据','定量数据','多维数据展示','图表选择原则'],['5.2']),
('用统计量描述数据的水平（集中趋势）','未标注',['平均数','中位数','分位数','众数','均值与中位数的比较及分布形状推断'],['5.2','2.7']),
('用统计量描述数据的差异（离散程度）','未标注',['极差与四分位距','标准差与方差','变异系数','标准化得分（z值）'],['5.2','2.3']),
('参数估计的基本原理','重要',['点估计与区间估计的区别','估计量的优良标准','标准误的概念','置信水平的解释'],['6.1','6.4','6.6']),
('一个总体和两个总体参数的区间估计','未标注',['一个总体','两个总体','独立样本与配对样本的区间构造差异'],['6.6']),
('抽样调查中样本量的确定','不重要',['基于精度要求确定样本量','有限总体校正因子的影响'],['6.6']),
('三种重要的抽样分布：t分布、F分布、卡方分布','重要',['t分布','卡方分布','F分布','三者关系'],['5.4']),
('假设检验的基本原理；临界值方法','重要',['原假设与备择假设的设定','检验统计量的构造思路','显著性水平与拒绝域','临界值法与检验统计量比较的决策逻辑','两类错误及其权衡'],['7.1','7.2']),
('p值的计算和理解','重要',['p值的定义','p值与显著性水平的比较决策','p值不表示效应大小或原假设成立概率','双侧检验与单侧检验的p值差异','常见误解澄清'],['7.1','7.2']),
('一个总体和两个总体参数的检验','未标注',['一个总体','两个总体','独立样本与配对样本的检验差异','大样本近似检验与小样本精确检验','检验前提条件的满足与稳健性'],['7.2','7.3']),
('方差分析的基本原理','重要',['总变异分解为组间变异与组内变异','组间方差与组内方差的比较','基本假设'],['8.1']),
('单因子方差分析的实现和结果解释','未标注',['方差分析表','因子显著性判断','多重比较的必要性与方法'],['8.1','8.2']),
('变量间的关系','未标注',['相关关系与因果关系的区分','相关系数的适用场景','相关性与协方差的关系'],['3.4','8.4']),
('线性回归的估计和检验','难，重要',['回归模型的基本形式与假设','最小二乘估计的几何含义','回归系数解释','回归系数的显著性检验','整体回归显著性检验','决定系数R²与调整R²'],['8.4']),
('残差与模型的检验','未标注',['残差定义及残差图分析','正态性检验','方差齐性检验','独立性检验','异常点与强影响点诊断','模型修正方向'],['7.5','8.3','8.4']),
('主成分分析与因子分析的原理','重要',['主成分分析','因子分析','两者目标差异','载荷矩阵与特征值/方差贡献率','旋转方法的目的'],[]),
('多元正态分布及其边缘分布和条件分布','未标注',['多元正态的密度特征','边缘分布仍为多元/一元正态','条件分布仍为正态','独立性与不相关性在多元正态下的等价性','线性组合仍服从正态分布'],['3.1','3.2','3.5']),
]
PROBABILITY = [
('随机事件及事件的关系和运算','未标注',['样本空间与事件的定义','事件的包含、相等、并、交、差、补','互斥事件与对立事件','事件运算律'],['1.1']),
('随机事件的概率；等可能模型','未标注',['概率的公理化定义','古典概型','几何概型','频率学派概率与主观概率'],['1.2','1.3']),
('条件概率和全概率公式；乘法定理；贝叶斯公式','未标注',['条件概率定义与乘法公式','全概率公式','贝叶斯公式','先验、似然、后验的直观理解','事件独立性与条件概率的关系'],['1.4','1.5']),
('随机变量的定义','未标注',['随机变量作为样本空间到实数的映射','离散型与连续型随机变量的区分','可测性要求'],['2.1']),
('离散型随机变量（分布列、分布函数）及常见分布','重要',['分布列与累积分布函数','离散均匀分布','二项分布','泊松分布','负二项分布','各分布之间的近似关系'],['2.1','2.4']),
('连续型随机变量（密度函数、分布函数）及常见分布','重要',['概率密度函数与累积分布函数','均匀分布','正态分布','指数分布','伽马分布','卡方、t、F分布','随机变量函数的分布','二维随机变量联合分布与边际分布','条件分布与独立性'],['2.1','2.5','2.6','3.1','3.2','3.5','5.4']),
('随机变量的期望与方差','重要',['期望作为概率加权平均','方差作为离差平方期望','期望的线性性质','方差与二阶矩的关系','标准差的意义'],['2.2','2.3']),
('随机变量函数的期望与方差','基础',['线性变换的期望与方差变化','高阶矩概念'],['2.2','2.3','3.4']),
('协方差及相关系数','未标注',['协方差度量两变量协同变异方向','相关系数标准化协方差','正相关、负相关、不相关的解释','独立性⇒不相关，但反之不成立','协方差矩阵'],['3.4']),
('大数定律与中心极限定理','难',['大数定律','中心极限定理','两大定理在统计推断中的基础地位','近似正态的适用条件与样本量要求'],['4.3','4.4']),
('ARMA、ARIMA模型，Yule-Walker估计方法','重要',['AR模型','MA模型','ARMA','ARIMA','Yule-Walker方程','模型识别基础'],[]),
('白噪声与平稳时间序列','重要',['白噪声','严格平稳与弱平稳的区别','平稳性对模型建模的重要性','自相关函数与偏自相关函数的作用','单位根与伪回归的初步概念'],[]),
]


def build():
    pdf = Path.home() / 'Desktop/专业课辅导/应用统计考研考纲.pdf'
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
    sections = {s['id']: s for s in structure()['sections']}
    nodes = [{'id':'syllabus-root','label':'北师考纲','kind':'root'}]; edges=[]
    for branch, label, rows in [('statistics','统计学部分',STATISTICS),('probability','概率论部分',PROBABILITY)]:
        parent='syllabus-'+branch;nodes.append({'id':parent,'label':label,'kind':'branch'})
        edges.append({'from':'syllabus-root','to':parent,'kind':'source_contains'})
        for number,(title,priority,children,anchors) in enumerate(rows,1):
            identifier=f'{parent}-{number:02}'
            mappings=[{'section':a,'title':sections[a]['title'],'pdf_page':sections[a]['pdf_first'],
                       'status':'assistant_proposal_pending_review'} for a in anchors]
            nodes.append({'id':identifier,'label':title,'kind':'syllabus_topic','source_number':number,
                          'source_priority_annotation':priority,'source_pdf_page':1,'source_sha256':digest,
                          'review_status':'assistant_transcription_pending_user_review',
                          'candidate_book_sections':mappings,
                          'coverage_status':'candidate_partial_mapping' if mappings else 'needs_other_source_mapping'})
            edges.append({'from':parent,'to':identifier,'kind':'source_contains'})
            for i,child in enumerate(children,1):
                leaf=f'{identifier}-{i:02}';nodes.append({'id':leaf,'label':child,'kind':'syllabus_detail',
                    'source_pdf_page':1,'source_sha256':digest,'review_status':'assistant_transcription_pending_user_review'})
                edges.append({'from':identifier,'to':leaf,'kind':'source_contains'})
    data={'date':'2026-10-26','status':'planned_reference_network_not_live_retrieval_graph',
          'source':{'path':str(pdf),'sha256':digest,'pages':1,'visible_title':'北师考纲',
                    'year_basis':'用户指定为当前考纲，图中未见年份或发布单位',
                    'extraction':'assistant_visual_transcription; PDF has no extractable text',
                    'priority_basis':'Labels copied from the supplied map; not independently verified exam weights'},
          'nodes':nodes,'edges':edges,
          'planned_steps':['核对考纲树的32个主节点及其子项','逐项审核与教材定义、例题、课后题、讲义页的对应',
                           '单独记录条件、易错点、解法与先修关系，不从目录自动推断',
                           '补齐时间序列和多元统计等资料映射','按考纲节点展示已审题目及证据覆盖，连接自适应检索'],
          'boundary':'Source tree preserved; textbook links are candidates. No teacher approval, generated solution or full syllabus coverage claimed.'}
    out=ROOT/'data/private/syllabus';out.mkdir(parents=True,exist_ok=True)
    target=out/'knowledge-network-plan.json';target.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    topics=[n for n in nodes if n['kind']=='syllabus_topic'];details=[n for n in nodes if n['kind']=='syllabus_detail']
    print(json.dumps({'main_topics':len(topics),'child_topics':len(details),'nodes':len(nodes),
        'unmapped_main_topics':[n['label'] for n in topics if not n['candidate_book_sections']]},ensure_ascii=False))
    return data


if __name__=='__main__':build()
