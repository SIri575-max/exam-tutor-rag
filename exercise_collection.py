"""Derived question collection. Source OCR is immutable; solutions are not embedding input."""
import collections
import hashlib
import html
import json
import re
from pathlib import Path
from book_structure import structure
from process_full_book import BASE, write_json
from sync_sources import fingerprint

VERSION = 2
FILES = ('exercise-candidates.jsonl', 'learning-units.jsonl', 'normalized-blocks.jsonl', 'manifest.json', 'example-boundary-reviews.json')
SOLUTION = re.compile(r'(?:^|\n)\s*(?:解(?!释|决|析)(?:法[一二三123]?)?[：:]?|证明[：:]?)\s*|(?<=[。？?])\s*解(?!释|决|析)[：:]?')


def rows(path):
    return [json.loads(x) for x in Path(path).read_text(encoding='utf-8').splitlines() if x.strip()]


def input_signature(base=BASE):
    return {name: fingerprint(Path(base) / name) if (Path(base)/name).exists() else None for name in FILES}


def reviewed_stem(item, blocks, annotation, manifest):
    if annotation['source_sha256'] != manifest['source_sha256'] or annotation['source_unit_text_sha256'] != hashlib.sha256(item['text'].encode()).hexdigest():
        raise ValueError('Stale example boundary review: '+item['id'])
    images={str(p['pdf_page']):p['image_sha256'] for p in manifest['pages']}
    if any(images.get(p)!=h for p,h in annotation['page_image_sha256'].items()):raise ValueError('Changed reviewed source image')
    parts=[]
    for span in annotation['spans']:
        text=blocks[span['block_id']]['text']
        if hashlib.sha256(text.encode()).hexdigest()!=span['text_sha256']:raise ValueError('Changed boundary block')
        if not 0<=span['start']<span['end']<=len(text):raise ValueError('Invalid boundary span')
        parts.append(text[span['start']:span['end']])
    for supplement in annotation.get('supplements',[]):
        if images[str(supplement['pdf_page'])]!=supplement['image_sha256']:raise ValueError('Changed supplement source')
        parts.append(supplement['text'])
    return '\n'.join(parts).strip()


def example_references(item):
    result=[]
    # A literal reference is only a "mentions" edge unless its context also
    # explicitly says that it uses data or continues an earlier example.
    for match in re.finditer(r'例\s*([1-8]\s*\.\s*\d+\s*\.\s*\d+)',item['text'][:700]):
        number=re.sub(r'\s+','',match.group(1));identifier='example-'+number
        if identifier==item['id'] or any(r['id']==identifier for r in result):continue
        quote=item['text'][max(0,match.start()-20):min(len(item['text']),match.end()+35)]
        result.append({'id':identifier,'label':'例'+number,'quote':quote,
                       'kind':'data_or_continuation_reference' if re.search(r'续例|采用|使用|中的.*数据|的数据|在例',quote) else 'literal_example_mention',
                       'review_status':'literal_reference_candidate'})
    return result


def searchable_text(text):
    # Retain table cells and LaTeX content, but remove presentation tags.
    text = re.sub(r'</(?:td|th|tr)>', ' ', text, flags=re.I)
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]*>', ' ', text))).strip()


def example_stem(item, blocks):
    text = item['text']
    marker = SOLUTION.search(text)
    if marker and marker.start() > 0:
        return text[:marker.start()].strip(), 'explicit_solution_marker_candidate'
    # No inferred solution gets promoted to a question. Only use the first
    # original paragraph; this may omit later conditions and may itself mix
    # explanation. Both limitations are visible, not silently hidden.
    first = blocks[item['block_ids'][0]]['text'].strip()
    return first, 'opening_only_boundary_unresolved'


def prepare(base=BASE):
    base = Path(base)
    signatures = input_signature(base)
    blocks = {b['id']: b for b in rows(base / 'normalized-blocks.jsonl')}
    manifest = json.loads((base / 'manifest.json').read_text(encoding='utf-8'))
    review_path=base/'example-boundary-reviews.json'
    reviews=json.loads(review_path.read_text(encoding='utf-8')) if review_path.exists() else {}
    if reviews and (reviews['raw_units_sha256']!=signatures['learning-units.jsonl'] or reviews['raw_blocks_sha256']!=signatures['normalized-blocks.jsonl']):
        raise ValueError('Raw archive changed; rebuild/review example annotations')
    sections = {s['id']: s for s in structure()['sections']}
    items = rows(base / 'exercise-candidates.jsonl')
    items += [x for x in rows(base / 'learning-units.jsonl') if x['kind'] == 'example']
    ids = set(); records = []; excluded = []
    for item in items:
        if item['source_sha256'] != manifest['source_sha256']:
            raise ValueError('Mixed source versions')
        item_blocks = [blocks[b] for b in item['block_ids']]
        if any(b['channel'] != 'body' for b in item_blocks):
            raise ValueError('Reference answers/non-body material cannot enter question collection')
        if item['id'] in ids:
            # This OCR unit is a reference to an earlier example, not a new one.
            # Do not fix the original archive or silently overwrite a duplicate.
            ref = re.sub(r'\s+', '', item['text'])
            if item['kind'] == 'example' and re.match(r'^例\d+\.\d+\.\d+(?:可以归结|中|的)', ref):
                excluded.append({'id': item['id'], 'pages': item['pages'], 'block_ids': item['block_ids'],
                                 'reason': 'duplicate_example_number_in_body_reference', 'text': item['text']})
                continue
            raise ValueError('Ambiguous duplicate record: ' + item['id'])
        ids.add(item['id'])
        stem, boundary = ((item['text'], 'exercise_number_boundary_candidate') if item['kind'] == 'exercise'
                          else example_stem(item, blocks))
        annotation=reviews.get('annotations',{}).get(item['id'])
        if annotation:
            stem=reviewed_stem(item,blocks,annotation,manifest)
            boundary='source_linked_block_span_review'
        if not stem.strip():
            raise ValueError('Empty question stem: ' + item['id'])
        section_id = item['section'] or '.'.join(item.get('source_number', '').split('.')[:2])
        if section_id.endswith('.0'):
            chapter_id = section_id.split('.')[0]
            chapter = next(c for c in structure()['chapters'] if c['id'] == chapter_id)
            section = {'chapter': chapter_id, 'title': chapter['title'] + '·章前引例'}
        else:
            section = sections[section_id]
        label = (f"习题{item['section']} 第{item['number']}题" if item['kind'] == 'exercise'
                 else f"例{item['source_number']}")
        flags = []
        if not item['section']: flags.append('小节由例号推断，待核对')
        if boundary == 'opening_only_boundary_unresolved': flags.append('例题仅索引开头摘要；条件可能不全、讲解边界待核对')
        if item.get('reading_order_warning'): flags.append('OCR阅读顺序待校对')
        if any(b['type'] == 'image' for b in item_blocks): flags.append('含图像条件，请核对原页')
        if any(b['type'] == 'table' for b in item_blocks): flags.append('含表格，数值待校对')
        if annotation and annotation.get('warning'):flags.append(annotation['warning'])
        if annotation and annotation.get('supplements'):flags.append('含对照原图补录数据，原始OCR保留')
        references=example_references(item) if item['kind']=='example' else []
        role='exercise' if item['kind']=='exercise' else 'worked_example'
        if item['kind']=='example' and re.search(r'说明.*例子|常见的事件域|随机现象的例子|事件独立的例子',item['text'][:60]):role='illustration'
        if references and re.search(r'续例|采用例|使用例|对例|在例|已在例',item['text'][:160]):role='worked_continuation'
        records.append({'id': item['id'], 'kind': item['kind'], 'label': label,
                        'chapter': section['chapter'], 'section': section_id,
                        'section_title': section['title'], 'subsection': item.get('subsection'),
                        'pages': item['pages'], 'block_ids': item['block_ids'],
                        'source_id': item['source_id'], 'source_sha256': item['source_sha256'],
                        'question_text': stem, 'search_text': searchable_text(stem),
                        'full_text': item['text'], 'stem_boundary': boundary,
                        'stem_review':annotation, 'example_role':role,'example_references':references,
                        'answer_group_locator': item.get('answer_group_locator'),
                        'review_flags': flags, 'review_status': 'raw_ocr_pending_review',
                        'approved_for_tutoring': False})
    identity = {'version': VERSION, 'inputs': signatures, 'records': records}
    signature = hashlib.sha256(json.dumps(identity, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    out = base / 'question-vectors'; out.mkdir(exist_ok=True)
    (out / 'records.jsonl').write_text(''.join(json.dumps(x, ensure_ascii=False) + '\n' for x in records), encoding='utf-8')
    (out / 'excluded.json').write_text(json.dumps(excluded, ensure_ascii=False, indent=2), encoding='utf-8')
    report = {'version': VERSION, 'input_sha256': signatures, 'collection_sha256': signature,
              'source_sha256': manifest['source_sha256'], 'records': len(records),
              'kinds': dict(collections.Counter(x['kind'] for x in records)),
              'boundaries': dict(collections.Counter(x['stem_boundary'] for x in records)),
              'chapters': dict(collections.Counter(x['chapter'] for x in records)),
              'excluded_duplicate_references': len(excluded),
              'source_linked_boundary_reviews':sum(r['stem_boundary']=='source_linked_block_span_review' for r in records),
              'source_supplements':sum(len((r['stem_review'] or {}).get('supplements',[])) for r in records),
              'example_roles':dict(collections.Counter(r['example_role'] for r in records if r['kind']=='example')),
              'reference_answer_documents': 0, 'full_text_embedded': False,
              'review_status': 'raw_ocr_pending_review'}
    write_json(out / 'collection-report.json', report)
    return records, report


if __name__ == '__main__':
    _, report = prepare(); print(json.dumps(report, ensure_ascii=False, indent=2))
