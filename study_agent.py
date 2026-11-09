"""Orchestrate local study tools and expose the basis of each decision."""

from fractions import Fraction
import re

import full_book_tutor
import question_knowledge
import rag_generation


INTENTS = {'lookup': '找相关题', 'review': '复习知识点', 'explain': '获得讲解', 'check': '核对答案'}
USEFUL_RELATIONS = {'source_number', 'method_related', 'structure_related'}
PATH_RELATIONS = {
    'contains_source_unit': '教材条目',
    'mentions_topic': '题干提及',
    'located_in_subsection': '所在小节',
}
RULES = (
    ('check', r'核对(?:一下|我的)?(?:数值)?答案|答案.{0,8}(?:对吗|正确|判定)|我算.{0,20}对吗|判对错'),
    ('review', r'复习|学习路径|知识图谱|知识网络|考点地图'),
    ('lookup', r'(?:找|查|推荐|定位).{0,10}(?:例题|习题|课后题|相似题|原题|同类题)'),
    ('explain', r'讲解|解答|解题思路|提示|如何推导|怎么做|怎么算|怎么求'),
)
# The exact checker accepts a single event with explicit independence and fairness.
DICE = re.compile(
    r'独立掷\s*(?P<count>[0-9]{1,2})\s*颗\s*公平\s*(?P<sides>[0-9]{1,2})\s*面骰子[，,。]\s*'
    r'求\s*最大点数\s*(?P<event>恰好等于|等于|不超过|小于等于)\s*(?P<point>[0-9]{1,2})\s*的概率[。？?]?'
)


def has_source(row):
    return any(type(page) is int and page > 0 for page in row.get('pages', []))


def topic_paths(question):
    graph = question_knowledge.current()
    matches = question_knowledge.mentions(question, graph['topics'])
    topics = sorted(matches, key=lambda row: -len(row['matched_alias']))[:3]
    nodes = {row['id']: row for row in graph['nodes']}
    paths = []
    for topic in topics:
        titles = {row['id']: row['title'] for row in graph.get('readings', {}).get(topic['id'], [])}
        groups = {}
        for edge in graph['edges']:
            relation = edge['kind']
            if relation == 'contains_source_unit' and edge['from'] == topic['id']:
                target = nodes[edge['to']]
                target = {**target, 'label': titles.get(target['id'], target.get('label', target['id']))}
                category = 'reading'
            elif relation in {'mentions_topic', 'located_in_subsection'} and edge['to'] == topic['id']:
                target = nodes[edge['from']]
                category = target['kind']
            else:
                continue
            if not has_source(target) or not edge.get('source_pages'):
                continue
            entries = groups.setdefault(category, {})
            if target['id'] not in entries or relation == 'mentions_topic':
                entries[target['id']] = {
                    'topic_id': topic['id'], 'node': target, 'relation': relation,
                    'relation_label': PATH_RELATIONS[relation], 'source_pages': edge['source_pages'],
                    'review_status': edge.get('review_status'),
                }
        for category in ('reading', 'example', 'exercise'):
            paths.extend(list(groups.get(category, {}).values())[:2])
    return topics, paths


def check_answer(question, answer):
    if not answer:
        return 'needs_context', '请在答案栏填写你的数值答案。', None
    match = DICE.fullmatch(question)
    if not match:
        return 'needs_review', '这道题需要人工判定。可用查题或复习入口定位教材依据。', None
    count, sides, point = (int(match[key]) for key in ('count', 'sides', 'point'))
    if not (1 <= count <= 30 and 2 <= sides <= 20 and 0 <= point <= sides):
        return 'needs_review', '参数超出当前骰子核对工具的范围。', None
    if not re.fullmatch(r'(?:[0-9]{1,24}(?:\.[0-9]{1,24}|/[0-9]{1,24})?|\.[0-9]{1,24})', answer):
        return 'needs_context', '请填写整数、分数或有限小数。', None
    try:
        actual = Fraction(answer)
    except ZeroDivisionError:
        return 'needs_context', '分数的分母应为非零值。', None
    cumulative = Fraction(point**count, sides**count)
    exact = match['event'] in {'恰好等于', '等于'}
    expected = cumulative - Fraction(max(point - 1, 0)**count, sides**count) if exact else cumulative
    calculation = {
        'expected': str(expected), 'submitted': str(actual), 'matches': expected == actual,
        'rule': '两个相邻累计概率作差' if exact else '各骰子同时不超过给定点数',
    }
    message = '数值与精确计算一致。' if expected == actual else '数值与精确计算有差异，请核对计算。'
    return 'checked', message, calculation


def parse_request(body):
    if not isinstance(body, dict):
        raise ValueError('请输入题干或知识点。')
    question = body.get('question')
    if not isinstance(question, str) or not 2 <= len(question.strip()) <= 3000:
        raise ValueError('请输入 2–3000 字的题干或知识点。')
    question = question.strip()
    requested = body.get('intent', 'auto')
    answer = body.get('answer', '')
    if not isinstance(requested, str) or requested not in {'auto', *INTENTS}:
        raise ValueError('请选择有效的任务。')
    if not isinstance(answer, str) or len(answer) > 80:
        raise ValueError('答案最多 80 字。')
    return question, requested, answer.strip()


def classify(question, requested, answer):
    matched = next(((intent, found[0]) for intent, pattern in RULES if (found := re.search(pattern, question))), None)
    if requested != 'auto':
        intent, basis = requested, '手动选择'
    elif answer:
        intent, basis = 'check', '已填写数值答案'
    elif matched:
        intent, basis = matched
    else:
        intent, basis = 'lookup', '默认查题'
    return intent, basis


def assess_candidates(retrieved):
    groups = retrieved.get('practice_groups', {})
    typed = groups.get('example', [])[:3] + groups.get('exercise', [])[:3]
    unique = {row['id']: row for row in typed + retrieved['hits']}
    sourced = [row for row in unique.values() if has_source(row)]
    supported = [row for row in sourced if row.get('correspondence', {}).get('level') in USEFUL_RELATIONS
                 and not row.get('correspondence', {}).get('condition_conflict')]
    return sourced, supported


def run(body):
    question, requested, answer = parse_request(body)
    intent, basis = classify(question, requested, answer)
    result = {'intent': intent, 'intent_label': INTENTS[intent], 'trace': [
        {'step': '意图识别', 'detail': f'{INTENTS[intent]} · {basis}'},
    ]}

    def finish(status, message):
        result['decision'] = {'status': status, 'message': message}
        result['trace'].append({'step': '结果判定', 'detail': message})
        return result

    if intent == 'check':
        status, message, calculation = check_answer(question, answer.strip())
        if calculation:
            result['calculation'] = calculation
            result['trace'].append({'step': '精确分数工具', 'detail': calculation['rule']})
        return finish(status, message)

    def graph_route():
        topics, paths = topic_paths(question)
        result['topics'] = topics
        result['paths'] = paths
        result['trace'].append({'step': '知识图谱', 'detail': f'{len(topics)} 个主题线索，{len(paths)} 条有来源的路径'})
        return paths

    if intent == 'review':
        if graph_route():
            return finish('review_path_ready', '已整理当前可用的教材路径，可按出处复习。')
        return finish('needs_context', '请提供更具体的知识点名称，例如置信区间或最大似然估计。')

    query = question if len(question) >= 3 else question + ' 相关题'
    retrieved = full_book_tutor.retrieve(query)
    result['trace'].append({'step': '教材检索', 'detail': f"{retrieved['route']} · {len(retrieved['hits'])} 条主列表候选"})
    if retrieved['status'] == 'needs_problem_context':
        result['clarifications'] = retrieved['clarifications']
        return finish('needs_context', retrieved['message'])

    sourced, supported = assess_candidates(retrieved)
    result['topics'] = retrieved.get('correspondence', {}).get('input_topics', [])[:5]
    result['recommendations'] = sourced[:8]
    result['clarifications'] = retrieved.get('clarifications', [])
    if not supported:
        if graph_route():
            return finish('review_path_ready', '相关题的条件或方法需复核，已补充可查阅的知识点路径。')
        return finish('needs_review', '相关题依据不足，请补充总体分布、已知条件或所求量。')
    if intent == 'lookup':
        return finish('candidates_ready', '已找到有教材出处的相关题候选，请核对条件和所求量。')

    evidence = rag_generation.evidence_for({**retrieved, 'hits': supported})
    result['evidence'] = [{key: row[key] for key in ('id', 'title', 'pages')} for row in evidence]
    if not evidence:
        return finish('needs_review', '当前可用于讲解的教材证据不足。')
    if body.get('allow_generation') is not True:
        return finish('evidence_ready', '已备好讲解依据。启用模型讲解后可生成提示。')
    teaching = rag_generation.generate(question, evidence, 'hint')
    result['teaching'] = teaching
    result['trace'].append({'step': '模型讲解', 'detail': teaching['status']})
    if teaching['used']:
        return finish('citation_checked', '引用编号已核对，讲解内容待复核。')
    return finish('evidence_ready', teaching['message'])
