"""Durable study tasks. Retrieval, graph lookup and grading keep separate gates."""
import re
from threading import Lock
from typing import TypedDict
from uuid import uuid4

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from langgraph.types import Command, interrupt
from langsmith import tracing_context

import full_book_tutor
import photo_ocr
from problem_conditions import missing_estimation_context
import rag_generation
from retrieval import ROOT
import study_agent as agent


DB = ROOT / 'data' / 'private' / 'agent' / 'workflows.sqlite3'
LOCKS = [Lock() for _ in range(32)]
MAX_FOLLOWUPS = 2
ID = re.compile(r'[0-9a-f]{32}')
FIELDS = {
    'question': '核对后填写完整题干（保留原题数字、符号和所求量）',
    'model': '总体分布或模型（可写公式）',
    'parameter': '要估计的参数（注明其他参数是否已知）',
    'method': '指定方法或额外条件（可选）',
    'answer': '你的整数、分数或有限小数答案',
}


class State(TypedDict, total=False):
    original_question: str
    question: str
    requested: str
    answer: str
    ocr_pending: bool
    photo_job: str
    strategy: str
    intent: str
    basis: str
    trace: list[dict]
    pause: dict
    followups: int
    retrieval: dict
    selected: list[dict]
    topics: list[dict]
    graph_topics: list[dict]
    paths: list[dict]
    search_section: str
    rechecked: bool
    decision: dict
    calculation: dict
    evidence: list[dict]
    teaching: dict


class Context(TypedDict):
    allow_generation: bool


class StaleTask(ValueError):
    pass


def step(s, name, detail):
    return [*s.get('trace', []), {'step': name, 'detail': detail}]


def decision(status, message):
    return {'status': status, 'message': message}


def clarification(fields, prompt, reasons=()):
    return {'prompt': prompt, 'reasons': list(reasons),
            'fields': [{'id': f, 'label': FIELDS[f], 'required': f != 'method'} for f in fields]}


def ask(s, fields, prompt, reasons=()):
    if s['strategy'] == 'single' or s.get('followups', 0) >= MAX_FOLLOWUPS:
        return {'pause': {}, 'decision': decision('needs_context', prompt),
                'trace': step(s, '信息核对', prompt)}
    return {'pause': clarification(fields, prompt, reasons),
            'trace': step(s, '等待补充', prompt)}


def route(s):
    intent, basis = agent.classify(s['question'], s['requested'], s['answer'])
    return {'intent': intent, 'basis': basis, 'trace': step(s, '意图识别', f'{agent.INTENTS[intent]} · {basis}'),
            'pause': {}, 'decision': {}, 'search_section': '', 'rechecked': False,
            'retrieval': {}, 'selected': [], 'topics': [], 'paths': [], 'graph_topics': []}


def inspect_input(s):
    if s['ocr_pending']:
        return ask(s, ['question'], '请对照题图确认识别稿，再继续处理。')
    if s['intent'] in {'lookup', 'explain'} and (missing := missing_estimation_context(s['question'])):
        return ask(s, ['model', 'parameter', 'method'], '估计题还缺少总体模型和待估参数。', missing)
    return {}


def after_input(s):
    if s.get('pause'):
        return 'clarify'
    if s.get('decision'):
        return 'finish'
    return {'check': 'check', 'review': 'graph'}.get(s['intent'], 'retrieve')


def clarify(s):
    reply = interrupt(s['pause'])
    question = reply.get('question', s['question'])
    if 'model' in reply:
        method = '；方法或约束：' + reply['method'] if reply.get('method') else ''
        question = f"{question}。总体模型：{reply['model']}；待估参数：{reply['parameter']}{method}"
    return {'question': question, 'answer': reply.get('answer', s['answer']), 'ocr_pending': False,
            'followups': s.get('followups', 0) + 1,
            'trace': step(s, '恢复任务', '已读取本机进度并使用你补充的信息。')}


def retrieve(s):
    section = s.get('search_section', '')
    query = s['question'] if len(s['question']) >= 3 else s['question'] + ' 相关题'
    r = full_book_tutor.retrieve(query, section=section)
    # Only the fields used by downstream gates and the explanation tool are persisted.
    data = {key: r[key] for key in ('hits', 'practice_groups', 'status', 'message', 'clarifications') if key in r}
    study = r.get('study', {})
    data['study'] = {key: study[key] for key in ('property_evidence', 'readings') if key in study}
    data['topics'] = r.get('correspondence', {}).get('input_topics', [])[:5]
    detail = f"{r['route']} · {len(r['hits'])} 条主列表候选"
    if section:
        detail = f'教材 {section} 节 · {detail}'
    return {'retrieval': data, 'rechecked': bool(section), 'trace': step(s, '教材补检' if section else '教材检索', detail)}


def assess(s):
    r = s['retrieval']
    if r['status'] == 'needs_problem_context' and not s['rechecked']:
        return ask(s, ['question'], r['message'], r.get('clarifications', []))
    _, supported = agent.assess_candidates(r)
    selected = [row for kind in ('example', 'exercise') for row in
                [row for row in supported if row['kind'] == kind][:3]]
    return {'selected': selected, 'topics': r['topics'],
            'trace': step(s, '候选核对', f'{len(selected)} 道题有原页且通过当前方法、结构或出处规则。')}


def after_assess(s):
    if s.get('pause'):
        return 'clarify'
    if s.get('decision'):
        return 'finish'
    if s.get('selected'):
        return 'explain' if s['intent'] == 'explain' else 'finish'
    if s['strategy'] == 'single' or s['rechecked']:
        return 'finish'
    return 'graph'


def graph_lookup(s):
    topics, paths = agent.topic_paths(s['question'])
    # Choose only a section backed by a question edge and an explicit query topic.
    evidenced = {p['topic_id'] for p in paths if p['node']['kind'] in {'example', 'exercise'}}
    section = next(('.'.join(t['subsection'].split('.')[:2]) for t in topics if t['id'] in evidenced), '')
    if not re.fullmatch(r'[1-8]\.\d+', section) or full_book_tutor.explicit_id(s['question']):
        section = ''
    if s['intent'] == 'review':
        if not paths:
            return ask(s, ['question'], '请补充更具体的考点名称，例如最大似然估计。')
        section = ''
    return {'paths': paths, 'graph_topics': topics, 'search_section': section,
            'trace': step(s, '知识图谱', f'{len(paths)} 条有出处的路径' + (f' · 用教材 {section} 节补检' if section else ''))}


def check(s):
    status, message, calculation = agent.check_answer(s['question'], s['answer'])
    if status == 'needs_context':
        return ask(s, ['answer'], message)
    result = {'decision': decision(status, message)}
    if calculation:
        result.update(calculation=calculation, trace=step(s, '精确分数工具', calculation['rule']))
    return result


def explain(s, runtime: Runtime[Context]):
    rows = rag_generation.evidence_for({**s['retrieval'], 'hits': s['selected']})
    evidence = [{k: row[k] for k in ('id', 'title', 'pages')} for row in rows if agent.has_source(row)]
    if not evidence:
        return {'decision': decision('needs_review', '当前可用于讲解的教材证据不足。')}
    if not (runtime.context or {}).get('allow_generation'):
        return {'evidence': evidence, 'decision': decision('evidence_ready', '已备好讲解依据。')}
    valid_ids = {row['id'] for row in evidence}
    teaching = rag_generation.generate(s['question'], [row for row in rows if row['id'] in valid_ids], 'hint')
    status, message = ('citation_checked', '引用编号已核对，推导与结论仍待核验。') if teaching['used'] else (
        'evidence_ready', teaching['message'])
    return {'evidence': evidence, 'teaching': teaching, 'decision': decision(status, message),
            'trace': step(s, '讲解引用核对', teaching['status'])}


def finish(s):
    result = s.get('decision') or (
        decision('candidates_ready', '找到有教材出处的相关题，请对照条件和所求量。') if s.get('selected') else
        decision('review_path_ready', '已整理有出处的复习路径。') if s['intent'] == 'review' and s.get('paths') else
        decision('needs_review', '目前没有足够依据推荐相关题，可核对题干或查看下方复习线索。'))
    return {'decision': result, 'trace': step(s, '结果判定', result['message'])}


def build(saver):
    graph = StateGraph(State, context_schema=Context)
    for name, node in {'route': route, 'input_check': inspect_input, 'clarify': clarify,
                       'retrieve': retrieve, 'assess': assess, 'graph': graph_lookup, 'check': check,
                       'explain': explain, 'finish': finish}.items():
        graph.add_node(name, node)
    graph.add_edge(START, 'route').add_edge('route', 'input_check')
    graph.add_conditional_edges('input_check', after_input, ['clarify', 'finish', 'check', 'graph', 'retrieve'])
    graph.add_edge('clarify', 'route').add_edge('retrieve', 'assess')
    graph.add_conditional_edges('assess', after_assess, ['clarify', 'finish', 'explain', 'graph'])
    graph.add_conditional_edges('graph', lambda s: 'clarify' if s.get('pause') else (
        'retrieve' if s.get('search_section') else 'finish'), ['clarify', 'retrieve', 'finish'])
    graph.add_conditional_edges('check', lambda s: 'clarify' if s.get('pause') else 'finish', ['clarify', 'finish'])
    graph.add_edge('explain', 'finish').add_edge('finish', END)
    return graph.compile(checkpointer=saver)


def public(snapshot, task):
    s = snapshot.values
    pending = [i for t in snapshot.tasks for i in t.interrupts]
    if not s.get('intent') or (snapshot.next and not pending):
        raise StaleTask('当前任务未完成，请重新开始。')
    output = {k: s[k] for k in ('intent', 'trace', 'calculation', 'paths', 'evidence', 'teaching', 'decision') if k in s}
    output.update(task_id=task, workflow='langgraph', intent_label=agent.INTENTS[s['intent']],
                  question=s['question'], requested=s['requested'], answer=s['answer'],
                  photo_job=s.get('photo_job', ''), followups=s.get('followups', 0),
                  recommendations=s.get('selected', []), topics=s.get('graph_topics') or s.get('topics', []))
    if pending:
        output.update(clarification={**pending[0].value, 'checkpoint': snapshot.config['configurable']['checkpoint_id']},
                      decision=decision('awaiting_input', pending[0].value['prompt']))
    return output


def validated_reply(body, prompt):
    reply = body.get('reply')
    fields = {row['id']: row for row in prompt['fields']}
    if not isinstance(reply, dict) or reply.keys() - fields.keys():
        raise ValueError('请按当前追问填写。')
    clean = {}
    for key, spec in fields.items():
        value = reply.get(key, '')
        limit = {'question': 3000, 'answer': 80}.get(key, 450)
        if not isinstance(value, str) or len(value.strip()) > limit:
            raise ValueError(f"{spec['label']}，最多 {limit} 字。")
        value = value.strip()
        if spec['required'] and (not any(c.isalnum() for c in value) or value in {'不知道', '不清楚', '未知', '无'}):
            raise ValueError(f"请填写：{spec['label']}。")
        if key == 'question' and len(value) < 2:
            raise ValueError('题干至少 2 字。')
        if value:
            clean[key] = value
    return clean


def handle(body, db=None):
    if not isinstance(body, dict) or body.get('action') not in ('start', 'resume', 'get'):
        raise ValueError('无效的任务操作。')
    action = body['action']
    if action == 'start':
        photo_job = body.get('photo_job', '')
        if not isinstance(photo_job, str) or (photo_job and not ID.fullmatch(photo_job)):
            raise ValueError('无效的题图编号。')
        if photo_job:
            photo = photo_ocr.get(photo_job)
            if photo['status'] != 'ready':
                raise ValueError('题图还未识别完成。')
            body = {**body, 'question': photo['result']['text']}
        question, requested, answer = agent.parse_request(body)
        strategy = body.get('strategy', 'adaptive')
        if strategy not in ('adaptive', 'single'):
            raise ValueError('无效的任务选项。')
        if strategy == 'single' and photo_job:
            raise ValueError('请在查题前确认题图识别稿。')
        task = uuid4().hex
        value = {'question': question, 'original_question': question, 'requested': requested, 'answer': answer,
                 'strategy': strategy, 'photo_job': photo_job, 'ocr_pending': bool(photo_job), 'trace': []}
    else:
        task = body.get('task_id')
        if not isinstance(task, str) or not ID.fullmatch(task):
            raise ValueError('无效的任务编号。')
    config = {'configurable': {'thread_id': task}, 'recursion_limit': 40}
    db = db or DB
    db.parent.mkdir(parents=True, exist_ok=True)
    with LOCKS[int(task[:2], 16) % len(LOCKS)], SqliteSaver.from_conn_string(str(db)) as saver, tracing_context(enabled=False):
        graph = build(saver)
        if action != 'start':
            previous = graph.get_state(config)
            if not previous.values:
                raise StaleTask('找不到这道题的任务，请重新开始。')
            view = public(previous, task)
            if action == 'get':
                return view
            prompt = view.get('clarification')
            if not prompt or body.get('checkpoint') != prompt['checkpoint']:
                raise StaleTask('这次追问已更新，请刷新当前任务。')
            reply = validated_reply(body, prompt)
            if 'model' in reply and len(view['question']) + sum(map(len, reply.values())) > 2940:
                raise ValueError('补充后的题干过长，请缩短输入。')
            value = Command(resume=reply)
        graph.invoke(value, config, context={'allow_generation': body.get('allow_generation') is True})
        return public(graph.get_state(config), task)
