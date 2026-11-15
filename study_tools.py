"""Typed, local study tools. Each model action is validated before execution."""
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

import exercise_vectors
import full_book_tutor
import study_agent
import study_memory


class Arguments(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class Search(Arguments):
    query: str = Field(min_length=3, max_length=1500)
    section: str = Field(default='', pattern=r'^(?:[1-8]\.\d+)?$')


class Topic(Arguments):
    topic: str = Field(min_length=2, max_length=200)


class Source(Arguments):
    record_id: str = Field(min_length=3, max_length=100)


class Check(Arguments):
    pass


class Recall(Arguments):
    query: str = Field(min_length=2, max_length=300)


class Ask(Arguments):
    kind: Literal['estimation', 'question', 'answer']
    prompt: str = Field(min_length=3, max_length=300)


SCHEMAS = {
    'search_textbook': (Search, '检索茆书例题和课后题，返回考点、出处和条件差异。query 保留原题条件。可按教材小节 section 补检。'),
    'read_source': (Source, '读取本次检索或图谱已找到的教材题原文与例题讲解，取得可引用的 E 编号。'),
    'knowledge_path': (Topic, '按知识点查有出处的教材条目、例题及课后题复习路径。'),
    'check_answer': (Check, '核对用户原题与答案，工具自行读取原始输入。支持范围有限，返回精确核对或待核验状态。'),
    'recall_memory': (Recall, '检索当前学习者以往任务的记录，用于复习建议。历史记录带待核验状态。'),
    'ask_clarification': (Ask, '题干不足或答案缺失时暂停并追问。estimation 追问模型与参数，question 追问完整题干，answer 追问数值答案。'),
}


def descriptions():
    return [{'type': 'function', 'function': {
        'name': name, 'description': description, 'parameters': schema.model_json_schema(),
    }} for name, (schema, description) in SCHEMAS.items()]


def compact(row):
    item = {key: row.get(key) for key in ('id', 'kind', 'label', 'question_text', 'pages', 'section')}
    correspondence = row.get('correspondence') or {}
    item['correspondence'] = {key: correspondence.get(key) for key in (
        'level', 'label', 'reasons', 'differences', 'condition_conflict', 'goal_mismatch')}
    return item


def execute(name, raw, state, memory_path=study_memory.DB):
    if name not in SCHEMAS:
        raise ValueError('未知工具，请选择已登记工具。')
    args = SCHEMAS[name][0].model_validate(raw).model_dump()
    if name == 'search_textbook':
        result = full_book_tutor.retrieve(args['query'], section=args['section'])
        _, supported = study_agent.assess_candidates(result)
        selected = [compact(row) for kind in ('example', 'exercise')
                    for row in [r for r in supported if r['kind'] == kind][:3]]
        raw_candidates = [row for rows in result.get('practice_groups', {}).values() for row in rows] + result['hits']
        candidates = {row['id']: compact(row) for row in raw_candidates if study_agent.has_source(row)}
        return {'status': result['status'], 'recommendations': selected,
                'candidates': list(candidates.values())[:12],
                'topics': result.get('correspondence', {}).get('input_topics', []),
                'clarifications': result.get('clarifications', []),
                'retrieval_budget': result.get('retrieval_budget', {}),
                'search_section': args['section']}
    if name == 'knowledge_path':
        topics, paths = study_agent.topic_paths(args['topic'])
        return {'topics': topics, 'paths': paths}
    if name == 'read_source':
        identifier = args['record_id']
        known = {r['id'] for r in state.get('candidates', [])}
        known.update(p['node']['id'] for p in state.get('paths', []))
        if identifier not in known:
            raise ValueError('请先检索此教材题或图谱条目，再读取原文。')
        if re.fullmatch(r'(?:example-[1-8]\.\d+\.\d+|mao3-[1-8]\.\d+-\d+)', identifier):
            row = exercise_vectors.record(identifier)
            text, label, pages = row['full_text'], row['label'], row['pages']
        else:
            graph = study_agent.question_knowledge.current()
            row = next((r for readings in graph['readings'].values() for r in readings if r['id'] == identifier), None)
            if row is None:
                raise ValueError('该图谱节点没有可读取原文。')
            text, label, pages = row['text'], row['title'], row['pages']
        if len(text) > 9000:
            raise ValueError('原文过长，请选择更小的教材条目或对照原页。')
        return {'record_id': identifier, 'title': label, 'text': text, 'pages': pages}
    if name == 'check_answer':
        status, message, calculation = study_agent.check_answer(state['question'], state['answer'])
        return {'status': status, 'message': message, 'calculation': calculation}
    if name == 'recall_memory':
        return {'memories': study_memory.recall(state['learner_id'], args['query'], state['task_id'], memory_path)}
    return {'kind': args['kind'], 'prompt': args['prompt']}
