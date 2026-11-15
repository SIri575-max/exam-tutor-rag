"""Explicit live tool-loop checks with per-case records and source boundaries."""
import argparse
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
from time import perf_counter
from uuid import uuid4

import reasoning_agent
import study_agent
from retrieval import ROOT
from process_full_book import write_json


DICE = '独立掷3颗公平6面骰子，求最大点数恰好等于5的概率'
CASES = [
    {'id': 'lookup', 'question': '帮我找习题6.1第6题及相关例题，并说明对应考点。', 'intent': 'lookup',
     'expected_tools': ['search_textbook']},
    {'id': 'explain', 'question': '讲解习题6.1第6题，给出教材依据和解题思路。', 'intent': 'explain',
     'expected_tools': ['search_textbook', 'read_source']},
    {'id': 'review', 'question': '复习最大似然估计，给我有出处的教材阅读与练习路径。', 'intent': 'review',
     'expected_tools': ['knowledge_path']},
    {'id': 'check', 'question': DICE, 'intent': 'check', 'answer': '125/216',
     'expected_tools': ['check_answer']},
    {'id': 'clarify', 'question': '有一组样本，求参数估计', 'intent': 'explain',
     'expected_tools': ['ask_clarification'],
     'reply': {'model': '来自正态分布，方差已知', 'parameter': '均值', 'method': '最大似然估计'}},
    {'id': 'memory', 'question': '回顾我此前核对的骰子最大点数题，根据学习记录说说我提交的数值和精确结果。', 'intent': 'auto',
     'expected_tools': ['recall_memory']},
]


def run(only=None):
    learner = uuid4().hex
    stamp = datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d-%H%M%S')
    folder = ROOT / 'data/private/agent' / ('live-tools-' + stamp)
    folder.mkdir(parents=True)
    report = {'scope': 'Six author-created development scenarios. Flow checks only; generated math and relevance await human review.',
              'learner_id': learner, 'cases': [], 'all_calls': 0, 'all_tools': 0, 'passed_flow_checks': 0}
    for case in [case for case in CASES if not only or case['id'] in only]:
        started = perf_counter()
        baseline = study_agent.run({'question': case['question'], 'intent': case['intent'], 'answer': case.get('answer', '')})
        output = reasoning_agent.handle({'action': 'start', 'learner_id': learner, 'allow_generation': True,
                                         'question': case['question'], 'intent': case['intent'], 'answer': case.get('answer', '')})
        initial_status = output['decision']['status']
        restored = None
        if 'reply' in case and output.get('clarification'):
            restored_output = reasoning_agent.handle({'action': 'get', 'learner_id': learner, 'task_id': output['task_id']})
            restored = restored_output['clarification'] == output['clarification']
            fields = {f['id'] for f in output['clarification']['fields']}
            reply = case['reply'] if 'model' in fields else {
                'question': '正态总体方差已知，求均值的最大似然估计。'}
            output = reasoning_agent.handle({'action': 'resume', 'learner_id': learner, 'allow_generation': True,
                                             'task_id': output['task_id'], 'checkpoint': output['clarification']['checkpoint'],
                                             'reply': reply})
        tools = [row['detail'].split(' · ')[0] for row in output['trace'] if row['step'] == '工具执行']
        passed = set(case['expected_tools']) <= set(tools) and output['decision']['status'] in {
            'candidates_ready', 'citation_checked', 'review_path_ready', 'checked', 'memory_recalled'}
        if case['id'] == 'lookup':
            passed &= any(r['id'] == 'mao3-6.1-6' for r in output['recommendations'])
        if case['id'] == 'check':
            passed &= bool(output['calculation'] and output['calculation']['expected'] == '61/216'
                           and output['calculation']['matches'] is False)
        if case['id'] == 'clarify':
            passed &= restored is True and output['followups'] == 1
        if case['id'] == 'memory':
            passed &= any(m['metadata'].get('calculation', {}).get('expected') == '61/216' for m in output['memories'])
        row = {'case_id': case['id'], 'input': case['question'], 'baseline_status': baseline['decision']['status'],
               'initial_status': initial_status, 'final_status': output['decision']['status'], 'tools': tools,
               'model_calls': output['model_calls'], 'tool_count': output['tool_count'],
               'elapsed_seconds': round(perf_counter() - started, 3), 'restored': restored, 'flow_passed': bool(passed),
               'usage': output['usage']}
        write_json(folder / (case['id'] + '.json'), output)
        report['cases'].append(row)
        report['all_calls'] += output['model_calls']
        report['all_tools'] += output['tool_count']
        report['passed_flow_checks'] += int(passed)
        write_json(folder / 'report.json', report)
        print(case['id'], row['final_status'], tools, bool(passed), flush=True)
    print(folder / 'report.json', flush=True)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--only', nargs='+', choices=[case['id'] for case in CASES if case['id'] != 'memory'],
                        help='Run selected development scenarios. Memory needs the preceding check scenario.')
    args = parser.parse_args()
    if not args.live:
        parser.error('Use --live to authorize requests to the configured provider.')
    report = run(args.only)
    raise SystemExit(report['passed_flow_checks'] != len(report['cases']))
