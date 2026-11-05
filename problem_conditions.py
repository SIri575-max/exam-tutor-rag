"""Conservative clarification for explicitly generic estimation requests."""
import re


def missing_estimation_context(query):
    text=re.sub(r'[\s，。！？、,.;；:：?！]','',query)
    generic=(r'(?:(?:有|已知|给定|现有|根据|给出|对于)?'
             r'(?:一组|一份|一些|若干|这些|这个|该)?(?:样本|观测值|观测数据|数据))?'
             r'(?:请|试)?(?:求|计算|求出|估计|如何求)?(?:未知)?参数(?:的)?(?:估计|估计值|值)?')
    if re.fullmatch(generic,text):
        return ['总体的分布或统计模型是什么？','需要估计哪个参数？','是否指定矩估计、最大似然或其他方法，或有额外约束？']
    return []
