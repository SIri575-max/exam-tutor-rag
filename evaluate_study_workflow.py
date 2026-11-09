"""Run fixed development scenarios on the local corpus; no model requests."""
import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

import study_agent
import study_workflow


SCENARIOS = (
    ('known_reference', {'question': '帮我找习题6.1第6题'}),
    ('missing_estimation_inputs', {'question': '有一组样本，求参数估计'}),
    ('weak_fisher_search', {'question': 'Fisher信息量', 'intent': 'lookup'}),
    ('knowledge_review', {'question': '复习最大似然估计'}),
    ('supported_answer', {'question': '独立掷3颗公平6面骰子，求最大点数恰好等于5的概率', 'answer': '61/216'}),
    ('unsupported_answer', {'question': '掷3颗公平6面骰子，求最大点数恰好等于5的概率', 'answer': '61/216'}),
)
ESTIMATION_REPLY = {'model': '来自正态分布，方差已知', 'parameter': '均值', 'method': '最大似然估计'}
EXPECTATIONS = {
    'known_reference': ('candidates_ready', 'candidates_ready', 'candidates_ready'),
    'missing_estimation_inputs': ('needs_context', 'needs_context', 'candidates_ready'),
    'weak_fisher_search': ('review_path_ready', 'needs_review', 'needs_review'),
    'knowledge_review': ('review_path_ready', 'review_path_ready', 'review_path_ready'),
    'supported_answer': ('checked', 'checked', 'checked'),
    'unsupported_answer': ('needs_review', 'needs_review', 'needs_review'),
}
VARIANTS = ('legacy', 'single', 'adaptive')


def summarize(result):
    return {'status': result['decision']['status'],
            'candidate_ids': {kind: [r['id'] for r in result.get('recommendations', []) if r['kind'] == kind]
                              for kind in ('example', 'exercise')},
            'sourced_paths': len(result.get('paths', [])), 'calculation': result.get('calculation'),
            'trace': [event['step'] for event in result['trace']]}


def compare(db):
    rows = []
    for case, request in SCENARIOS:
        for index, variant in enumerate(VARIANTS):
            started = perf_counter()
            if variant == 'legacy':
                initial = study_agent.run(request)
            else:
                initial = study_workflow.handle({'action': 'start', 'strategy': variant, **request}, db)
            final = initial
            restored = None
            if case == 'missing_estimation_inputs' and variant == 'adaptive':
                ref = {'task_id': initial['task_id']}
                checkpoint = initial['clarification']['checkpoint']
                fetched = study_workflow.handle({'action': 'get', **ref}, db)
                restored = fetched['clarification']['checkpoint'] == checkpoint
                final = study_workflow.handle({'action': 'resume', **ref, 'checkpoint': checkpoint,
                                               'reply': ESTIMATION_REPLY}, db)
                restored = restored and final['task_id'] == initial['task_id'] and final['followups'] == 1
            row = {'case': case, 'variant': variant, 'initial_status': initial['decision']['status'],
                   **summarize(final), 'restored': restored, 'elapsed_ms': round((perf_counter() - started) * 1000, 1)}
            good = row['status'] == EXPECTATIONS[case][index]
            if case == 'known_reference':
                good &= row['candidate_ids']['exercise'][:1] == ['mao3-6.1-6']
            elif case == 'missing_estimation_inputs' and variant == 'adaptive':
                good &= bool(restored and all(row['candidate_ids'].values()))
            elif case == 'weak_fisher_search' and variant == 'adaptive':
                good &= row['trace'].count('教材补检') == 1 and row['sourced_paths'] > 0 and not any(row['candidate_ids'].values())
            elif case == 'knowledge_review':
                good &= row['sourced_paths'] > 0
            elif case == 'supported_answer':
                good &= (row['calculation'] or {}).get('matches') is True
            elif case == 'unsupported_answer':
                good &= row['calculation'] is None
            rows.append({**row, 'flow_expected': bool(good)})
    return {'scope': 'Fixed local development scenarios; not independently labeled retrieval or math accuracy.',
            'model_requests': 0, 'case_count': len(SCENARIOS), 'variant_count': len(VARIANTS),
            'checks_passed': sum(row['flow_expected'] for row in rows), 'rows': rows}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, help='Optional local output path.')
    args = parser.parse_args()
    with TemporaryDirectory() as tmp:
        report = compare(Path(tmp) / 'workflow.sqlite3')
    content = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(content, encoding='utf-8')
    print(content, end='')
    raise SystemExit(report['checks_passed'] != len(report['rows']))
