"""Capture a small development review batch; never manufacture human approval."""
import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
CASES = [
    ('R01', '例6.3.5', '题号定位', '题号、完整条件、讲解边界与公式是否对应原页。'),
    ('R02', '从均匀分布总体抽取样本，求未知上界的最大似然估计', '自然语言找题', '是否能找到均匀总体上界估计例题；相关练习是否共享估计方法。'),
    ('R03', '总体服从U(θ,2θ)，样本均值如何构造无偏估计，最大似然估计是否无偏', '相近题型区分', '能否区分总体区间与参数条件，不把U(0,θ)直接当成同一道题。'),
    ('R04', '指数分布总体的参数如何用样本均值做矩估计', '方法与条件', '题目采用的指数分布参数化方式是否匹配；不能忽略率参数和尺度参数的区别。'),
    ('R05', '正态总体均值未知且方差未知，如何构造总体均值的置信区间', '区间估计', '是否推荐适用条件一致的例题与练习；能否避免混入方差已知情形作为直接答案。'),
    ('R06', '最大似然估计的不变性如何用于参数函数的估计', '知识点到原例', '是否提供支持“不变性”的原文；推荐练习是否真正用到此性质。'),
    ('R07', '正态样本的总体均值已知，样本对该均值的离差平方和服从什么分布', '公式条件回归', '核对已知均值条件；与用样本均值中心化的情形区分。'),
    ('R08', '比较几种饲料对鸡的增重作用是否相同，进行方差分析', '跨章回归', '例题和课后题是否相互支持；数据表能否回到原页核对。'),
    ('R09', '有一组样本，求参数估计。', '信息不足', '应优先询问总体模型、参数与估计要求；如返回候选，必须明确只是浏览线索。'),
    ('R10', '帮我写一封求职邮件', '范围外输入', '应说明需要统计学题目，不能强行推荐数学题。'),
]


def collect(base):
    with urlopen(base + '/api/problem-index', timeout=15) as response:
        index = json.load(response)
    if not index.get('ready'):
        raise RuntimeError('Current question index is not ready')
    cases = []
    for identifier, query, purpose, check in CASES:
        request = Request(base + '/api/problem-study', json.dumps({
            'question': query, 'mode': 'hybrid', 'kind': 'all', 'limit': 5,
            'adaptive': True,
        }, ensure_ascii=False).encode(), {'Content-Type': 'application/json'})
        with urlopen(request, timeout=90) as response:
            data = json.load(response)
        case = {'id': identifier, 'query': query, 'purpose': purpose, 'review_prompt': check,
                'human_review': {'status': 'pending', 'stem': None, 'topic_relation': None,
                                 'practice_relation': None, 'notes': ''},
                'observed': {'route': data['route'], 'status': data['status'],
                             'message': data.get('message'), 'clarifications': data.get('clarifications', []),
                             'hits': [{k: hit.get(k) for k in ['id', 'label', 'pages', 'question_text', 'review_flags']}
                                      for hit in data['hits'][:3]],
                             'topics': [t['label'] for t in data.get('study', {}).get('query_topics', [])],
                             'llm_used': data.get('llm_used')}}
        cases.append(case)
        print(identifier, data['status'], ', '.join(h['label'] for h in case['observed']['hits']), flush=True)
    return {'generated_at': datetime.now(timezone(timedelta(hours=8))).isoformat(),
            'purpose': 'development review; not an independent test set or teacher-approved benchmark',
            'collection_sha256': index.get('collection_sha256'), 'source_sha256': index.get('source_sha256'),
            'records': index['records'], 'chunks': index['chunks'], 'cases': cases}


def document(data, base):
    lines = [
        '# 茆书辅导 Demo：下一阶段方案与审核清单', '',
        '日期：2026-10-26。状态：方案待用户审核；下列题目关联均未自动批准。', '',
        '## 建议你审核的决定', '',
        '先把第六章“参数估计”做成可验收的辅导样板，再扩展到其他章节。全书检索继续保留。', '',
        '| 顺序 | 下一步交付 | 完成标准 |',
        '| --- | --- | --- |',
        '| 1 | 第六章题目与考点审核工作台，首批20道例题/课后题 | 可同屏核对题干、公式、原页；逐条记录通过/需修改/不确定 |',
        '| 2 | 审核后的题目—知识点—相似题关系 | 区分“考查”“先修”“仅原文提及”；每条有出处、审核状态及修改记录 |',
        '| 3 | 分层辅导：提示→思路→完整讲解 | 先检查条件，再引用已审资料；缺条件或无依据时明确追问/说明限制 |',
        '| 4 | 自适应检索与作品集演示 | 分别展示题号直达、相似题检索、补检、追问、范围外输入；与单轮检索对照 |', '',
        '第一步先完成本地审核与数据闭环。真实模型调用前，需要确定服务、配置方式以及发送片段的范围；密钥不写进聊天。', '',
        '## 当前已核实的基础', '',
        f'- 全书490页；{data["records"]}条题目记录、{data["chunks"]}个向量片段；本地向量库已就绪。',
        '- 735道课后题、274条例题候选；仍有99条例题只保留开头摘要，不能声称已全部整理为完整练习。',
        '- 公式显示已修复，但能排版不等于数学内容正确。',
        '- 当前全书学习路径没有调用大模型生成数学解答；词语提及与目录位置不等于审核后的考查关系。', '',
        '## 你这次怎么审核', '',
        f'打开 [题目检索 Demo]({base}/problems)，复制下表输入。点击“原页”核对，必要时展开原例讲解。', '',
        '每条只需判断三件事：①题干/公式是否完整；②推荐考点是否准确；③相关题是否适合练习。',
        '可回复“R02 通过；R03 需改：……；R05 不确定”。“不确定”会保留为待审核，不自动算通过。', '',
        '以下为当前版本实际运行的候选结果。它们是开发审核样例，不是独立保留集，也没有被计为正确率。', '',
        '| 编号/用途 | 输入 | 当前前三条候选/响应 | 重点审核 |',
        '| --- | --- | --- | --- |',
    ]
    for case in data['cases']:
        observed = case['observed']; hits = observed['hits']
        found = '；'.join(h['label'] + ('（[原页](' + base + '/library#page=' + str(h['pages'][0]) + ')）' if h.get('pages') else '') for h in hits)
        found = found or observed.get('message', observed['status'])
        lines.append(f'| {case["id"]} · {case["purpose"]} | {case["query"]} | {found} | {case["review_prompt"]} |')
    ambiguous = next(case for case in data['cases'] if case['id'] == 'R09')
    lines += ['', '## 已知需要优先检查的边界', '',
              f'信息不足样例 R09 当前状态为 `{ambiguous["observed"]["status"]}`，路由为 `{ambiguous["observed"]["route"]}`。',
              '本轮仅记录实际行为，没有因它返回候选就判为通过。若没有优先澄清，应作为下一阶段明确修复项。', '',
              'R06“最大似然估计的不变性”当前前三条为一般最大似然估计习题。原例6.3.5包含不变性讲解，但本次未进入前三；需要审核性质级检索与推荐关联，而非仅依靠“最大似然估计”这个大类词。', '',
              '后续独立验收集由你另提供未用于调整规则的题目，并在修改检索规则前冻结；当前10条可用于开发反馈。', '',
              '## 批准方式', '',
              '若接受上述范围，可回复：“按第六章样板继续”。也可先指定更希望示范的小节。',
              '题目内容审核与开发范围批准分别记录：同意开发不代表已经认可这10条数学关联。', '',
              '本轮没有覆盖原始教材、向量库、简历事实或审核状态。完整候选快照在项目私有 `acceptance-review` 目录。', '']
    return '\n'.join(lines)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--base', default='http://127.0.0.1:8771')
    args = parser.parse_args(); data = collect(args.base)
    out = ROOT / 'data/private/full-book/acceptance-review'; out.mkdir(parents=True, exist_ok=True)
    (out / 'review-batch-2026-10-26.json').write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    target = ROOT.parents[1] / 'research/茆书RAG下一阶段方案与审核清单-2026-10-26.md'
    target.write_text(document(data, args.base), encoding='utf-8')
    print(target)
