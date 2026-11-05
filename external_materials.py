"""Browse external question stems and their known evaluation history."""
import json
from functools import lru_cache

from external_question_bank import BASE
from external_review import development_ids, source_checks


PAGE_SIZE = 18
STATUS_LABELS = {'available': '待选素材', 'used': '已有专项记录', 'review': '优先核对'}


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


@lru_cache(maxsize=2)
def read_questions(path, stamp):
    with path.open(encoding='utf-8') as source:
        return {row['id']: row for row in map(json.loads, source)}


def catalog():
    path = BASE / 'dataset/questions.jsonl'
    questions = read_questions(path, path.stat().st_mtime_ns)
    anchors = read_json(BASE / 'source-anchor-labels.json')['cases']
    objective = read_json(BASE / 'objective-pilot/frozen-cases.json')['cases']
    dev = development_ids() | {item['case_id'] for item in anchors}
    controls = {item['source_question'] for item in objective}
    reviewed = {path.stem for path in (BASE / 'human-reviews').glob('*/*.json')}
    checks = source_checks({identifier: {'source_pages': row['pages']} for identifier, row in questions.items()})
    records = {}
    for identifier, question in questions.items():
        uses = []
        if identifier in dev:
            uses.append('检索开发或出处核对')
        if identifier in controls:
            uses.append('生成对照样本')
        if identifier in reviewed:
            uses.append('已有人工核对记录')
        issues = checks[identifier]
        if question['requires_figure_review']:
            issues.append('含图，需对照原页')
        if question['boundary_status'] != 'candidate_complete':
            issues.append('切题边界待核对')
        needs_review = any(issue != '跨页条件待核对' for issue in issues)
        status = 'used' if uses else 'review' if needs_review else 'available'
        records[identifier] = {
            'id': identifier,
            'chapter': question['chapter'],
            'number': question['number'],
            'topic_hint': question['topic_hint'],
            'difficulty_stars': question['difficulty_stars'],
            'pages': question['pages'],
            'status': status,
            'status_label': STATUS_LABELS[status],
            'uses': uses,
            'source_checks': issues,
            'can_prefill': not question['requires_figure_review'] and 3 <= len(question['text'].strip()) <= 3000,
            'text': question['text'],
            'text_sha256': question['text_sha256'],
            'source_sha256': question['source_sha256'],
        }
    return records


def get_question(identifier):
    question = catalog().get(identifier)
    if question is None:
        raise ValueError('未找到该题号')
    return question


def browse(chapter='', status='available', keyword='', page=1):
    if chapter not in {'', '1', '2', '3', '4', '5', '6', '7', '8'}:
        raise ValueError('请选择第一至第八章')
    if status not in {'all', *STATUS_LABELS}:
        raise ValueError('请选择有效的素材范围')
    if len(keyword) > 150 or page < 1:
        raise ValueError('请输入有效的搜索词或页码')
    records = list(catalog().values())
    needle = keyword.strip().casefold()
    matches = [row for row in records
               if (not chapter or str(row['chapter']) == chapter)
               and (status == 'all' or row['status'] == status)
               and any(needle in str(row[key] or '').casefold() for key in ('id', 'topic_hint', 'text'))]
    pages = max(1, (len(matches) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = min(page, pages)
    start = (page - 1) * PAGE_SIZE
    return {
        'counts': {status: sum(row['status'] == status for row in records) for status in STATUS_LABELS},
        'total': len(records),
        'matches': len(matches),
        'page': page,
        'page_count': pages,
        'questions': [{key: row[key] for key in ('id', 'chapter', 'number', 'topic_hint', 'pages', 'status_label')}
                      for row in matches[start:start + PAGE_SIZE]],
    }
