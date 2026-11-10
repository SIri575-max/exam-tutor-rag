"""Freeze a private 660B Agent pilot and score approved blind reviews."""
import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory
from time import perf_counter

from build_external_evaluation import query_text
from exercise_vectors import status as index_status
from external_materials import catalog, read_questions
from external_review import AGENT_ARMS, BASE, ROOT, activate, context, read_state, write_json
from full_book_tutor import retrieve
from retrieval_metrics import evaluate
from score_external_relevance import score_case


SEED = '660B-agent-pilot-2026-11-10'
KINDS = ('example', 'exercise')
K = 3
CODE_FILES = ('agent_benchmark.py', 'study_workflow.py', 'study_agent.py', 'evaluate_external_retrieval.py',
              'retrieval_policy.py', 'build_external_evaluation.py', 'book_structure.py', 'exercise_collection.py')
HIT_FIELDS = ('id', 'kind', 'label', 'pages', 'question_text', 'section')


def digest(value):
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def sample(per_chapter):
    source = BASE / 'dataset/questions.jsonl'
    originals = read_questions(source, source.stat().st_mtime_ns)
    prior_spot = BASE / 'recognition-review-20261105/spot-check-report.json'
    exposed = set()
    if prior_spot.exists():
        exposed = {row.get('case_id') or row.get('id') for row in json.loads(prior_spot.read_bytes())['sample']}
    eligible = defaultdict(list)
    for identifier, row in catalog().items():
        if row['status'] != 'available' or identifier in exposed or not row['can_prefill']:
            continue
        query = query_text(originals[identifier])
        if 3 <= len(query) <= 3000:
            eligible[int(row['chapter'])].append({
                'case_id': identifier, 'query': query, 'chapter': row['chapter'], 'source_pages': row['pages'],
                'question_text_sha256': row['text_sha256'], 'source_sha256': row['source_sha256'],
            })
    frozen = []
    for chapter in range(1, 9):
        candidates = sorted(eligible[chapter], key=lambda row: digest([SEED, row['case_id']]))
        if len(candidates) < per_chapter:
            raise ValueError(f'Chapter {chapter} lacks eligible cases')
        frozen.extend(candidates[:per_chapter])
    return frozen


def frozen_sample(per_chapter):
    source = BASE / 'dataset/questions.jsonl'
    dataset_sha = sha256(source.read_bytes()).hexdigest()
    folder = BASE / 'agent-runs'
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f'{SEED}-{dataset_sha[:16]}-{per_chapter}.json'
    if path.exists():
        manifest = json.loads(path.read_bytes())
        if manifest['dataset_sha256'] != dataset_sha:
            raise ValueError('Frozen input dataset mismatch')
        return manifest['cases']
    cases = sample(per_chapter)
    write_json(path, {'dataset_sha256': dataset_sha, 'cases': cases})
    return cases


def typed(rows):
    hits = []
    for kind in KINDS:
        found = {}
        for row in rows:
            if row['kind'] == kind and row['id'] not in found:
                found[row['id']] = {key: row.get(key) for key in HIT_FIELDS}
                if len(found) == K:
                    break
        hits.extend(found.values())
    return hits


def run_arm(query, name, db):
    from study_workflow import handle
    started = perf_counter()
    if name == 'retrieval_only':
        result = retrieve(query)
        groups = result.get('practice_groups', {})
        rows = [row for kind in KINDS for row in groups.get(kind, ())]
        state = result['status']
        trace = [result['route']]
    else:
        strategy = 'single' if name == 'agent_single' else 'adaptive'
        result = handle({'action': 'start', 'question': query, 'intent': 'lookup', 'strategy': strategy}, db)
        rows = result['recommendations']
        state = result['decision']['status']
        trace = [row['step'] for row in result['trace']]
    return {'status': state, 'trace': trace, 'elapsed_ms': round((perf_counter() - started) * 1000, 1),
            'hits': typed(rows)}


def operational(cases):
    summary = {}
    for name in AGENT_ARMS:
        arms = [row['arms'][name] for row in cases]
        summary[name] = {
            'cases': len(arms), 'status_counts': dict(Counter(arm['status'] for arm in arms)),
            'cases_with_examples': sum(any(h['kind'] == 'example' for h in a['hits']) for a in arms),
            'cases_with_exercises': sum(any(h['kind'] == 'exercise' for h in a['hits']) for a in arms),
            'graph_retries': sum('教材补检' in a['trace'] for a in arms),
            'median_ms': median(a['elapsed_ms'] for a in arms),
        }
    summary['adaptive_output_changed_cases'] = sum(
        [h['id'] for h in row['arms']['agent_single']['hits']] !=
        [h['id'] for h in row['arms']['agent_adaptive']['hits']] for row in cases)
    return summary


def freeze(per_chapter=3):
    from evaluate_external_retrieval import CODE_FILES as RETRIEVAL_FILES
    index = index_status()
    if not index['ready']:
        raise ValueError('Build the textbook question index first')
    frozen = frozen_sample(per_chapter)
    code = {f: sha256((ROOT / f).read_bytes()).hexdigest() for f in sorted(set(CODE_FILES + RETRIEVAL_FILES))}
    config = {'suite': 'agent', 'seed': SEED, 'retrieval_arms': list(AGENT_ARMS), 'display_k_per_kind': K,
              'collection_sha256': index['collection_sha256'], 'code_sha256': digest(code),
              'input_variant': 'raw_ocr', 'frozen_cases': frozen}
    identity = digest(config)
    path = BASE / 'agent-runs' / identity[:16] / 'report.json'
    if path.exists():
        report = json.loads(path.read_bytes())
        if report.get('identity_sha256') != identity or any(report.get(k) != v for k, v in config.items()):
            raise ValueError('Frozen report identity mismatch')
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    cases = []
    with TemporaryDirectory() as tmp:
        for offset, row in enumerate(frozen):
            # Rotate arm order to share warm-cache effects across variants.
            order = offset % len(AGENT_ARMS)
            names = AGENT_ARMS[order:] + AGENT_ARMS[:order]
            arms = {name: run_arm(row['query'], name, Path(tmp) / 'pilot.sqlite3') for name in names}
            cases.append({**row, 'arms': arms})
            print(f'Evaluated {len(cases)}/{len(frozen)}', flush=True)
    report = {**config, 'identity_sha256': identity, 'cases': cases, 'summary': operational(cases), 'model_requests': 0}
    write_json(path, report)
    return path


def per_kind_metrics(cases, reviews, kind):
    rows = {name: [] for name in AGENT_ARMS}
    for case, review in zip(cases, reviews, strict=True):
        pool = {h['id'] for arm in case['arms'].values() for h in arm['hits'] if h['kind'] == kind}
        grades = {identifier: review['grades'][identifier] for identifier in pool}
        has_positive = any(grade >= 2 for grade in grades.values())
        for name, arm in case['arms'].items():
            ids = [h['id'] for h in arm['hits'] if h['kind'] == kind]
            measures = evaluate(ids, grades, K)
            rows[name].append((has_positive, measures, sum(grades[i] < 2 for i in ids)))
    result = {}
    for name, values in rows.items():
        positives = [m for has_positive, m, _ in values if has_positive]
        sent = sum(m['returned_count'] for _, m, _ in values)
        weak = sum(n for _, _, n in values)
        result[name] = {
            'reviewed_cases': len(values), 'positive_pool_cases': len(positives),
            'pooled_recall_at_3': mean(m['annotated_positive_coverage_at_k'] for m in positives),
            'mrr_at_3': mean(m['reciprocal_rank_at_k'] for m in positives),
            'precision_at_3': mean(m['precision_at_k'] for _, m, _ in values),
            'below_grade_2': weak, 'displayed': sent, 'weak_recommendation_rate': weak / sent if sent else None,
        }
    return result


def mean(values):
    values = list(values)
    return sum(values) / len(values) if values else None


def scores(pointer, cases):
    approved, new_problem, exclusions = [], [], Counter()
    for case_id, case in cases.items():
        review = read_state(pointer['report_sha256'], case_id)['current'] or {}
        if score_case(case, review)['status'] != 'reviewed':
            exclusions['pending_or_draft'] += 1
            continue
        approved.append((case, review))
        if review['overlap_stratum'] == 'related_concept_new_problem':
            new_problem.append((case, review))
        else:
            exclusions[review['overlap_stratum']] += 1
    groups = {'development_bucket': [], 'holdback_bucket': []}
    for case, review in new_problem:
        family = review['family_id'].strip().casefold()
        bucket = 'development_bucket' if int(digest([case['source_sha256'], family]), 16) % 5 == 0 else 'holdback_bucket'
        groups[bucket].append((case, review))
    metric_groups = {'all_approved_new_problems': new_problem, **groups}
    return {
        'report_sha256': pointer['report_sha256'], 'frozen_cases': len(cases), 'approved_cases': len(approved),
        'exclusions': dict(exclusions),
        'metrics': {name: {kind: per_kind_metrics([c for c, _ in pairs], [r for _, r in pairs], kind)
                           for kind in KINDS} for name, pairs in metric_groups.items()},
        'boundary': 'Recall and MRR use cases with at least one judged positive per kind. Recall uses the union of the three arms. Family buckets are provisional until cross-snapshot overlap is reviewed.',
    }


def recovery(fixtures):
    from study_workflow import handle

    source_rows = catalog()
    rows = []
    with TemporaryDirectory() as tmp:
        db = Path(tmp) / 'recovery.sqlite3'
        for fixture in fixtures:
            case_id = fixture['case_id']
            source = source_rows[case_id]
            if source['pages'] != fixture['source_pages']:
                raise ValueError(f'660B source pages changed for {case_id}')
            masked = fixture['masked_question']
            without_reply = run_arm(masked, 'agent_single', db)
            started = perf_counter()
            initial = handle({'action': 'start', 'question': masked, 'intent': 'lookup'}, db)
            clarification = initial.get('clarification')
            if not clarification:
                rows.append({'case_id': case_id, 'paused': False, 'resumed': False, 'initial_status': initial['decision']['status']})
                continue
            identifier = initial['task_id']
            restored = handle({'action': 'get', 'task_id': identifier}, db)
            resume = handle({'action': 'resume', 'task_id': identifier, 'checkpoint': clarification['checkpoint'],
                             'reply': fixture['reply']}, db)
            elapsed_ms = round((perf_counter() - started) * 1000, 1)
            direct = run_arm(resume['question'], 'agent_single', db)
            resumed = restored.get('clarification') == clarification and resume['task_id'] == identifier and resume['followups'] == 1
            ids = [h['id'] for h in typed(resume['recommendations'])]
            rows.append({
                'case_id': case_id, 'source_pages': source['pages'],
                'source_page_sha256': [sha256((BASE / 'pages' / f'pdf-{p:03}.png').read_bytes()).hexdigest() for p in source['pages']],
                'paused': True, 'resumed': resumed, 'masked_single_status': without_reply['status'],
                'resumed_status': resume['decision']['status'], 'full_single_status': direct['status'],
                'matched_full_input_candidates': ids == [h['id'] for h in direct['hits']],
                'returned_candidates': len(ids), 'masked_single_ms': without_reply['elapsed_ms'], 'recovery_service_ms': elapsed_ms,
                'full_single_ms': direct['elapsed_ms'],
            })
    return {
        'case_count': len(rows), 'paused_count': sum(row['paused'] for row in rows),
        'resumed_count': sum(row['resumed'] for row in rows),
        'same_candidate_list_count': sum(row.get('matched_full_input_candidates', False) for row in rows),
        'model_requests': 0, 'cases': rows,
        'boundary': 'Controlled deletion of model and parameter information. Replies were transcribed or paraphrased from question pages; no answer keys. Candidate equality measures execution, without a relevance judgment.',
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('freeze', 'score', 'recovery'))
    parser.add_argument('--per-chapter', type=int, default=3)
    parser.add_argument('--fixtures', type=Path)
    args = parser.parse_args()
    if args.action == 'freeze':
        if not 1 <= args.per_chapter <= 8:
            parser.error('--per-chapter must be between 1 and 8')
        report_path = freeze(args.per_chapter)
        print(json.dumps(activate(report_path, 'agent'), ensure_ascii=False), flush=True)
        print(report_path)
    elif args.action == 'score':
        pointer, _, cases = context('agent')
        result = scores(pointer, cases)
        target = (BASE / pointer['report']).with_name('reviewed-metrics.json')
        write_json(target, result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if args.fixtures is None:
            parser.error('recovery requires --fixtures with private source-checked replies')
        print(json.dumps(recovery(json.loads(args.fixtures.read_bytes())), ensure_ascii=False, indent=2))
