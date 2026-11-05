"""Build a complete, provenance-preserving private OCR archive and navigation catalog."""
import collections
import csv
import datetime as dt
import html
import json
import re
import sqlite3
import time
from pathlib import Path
from audit_ocr_pilot import content_strings
from book_structure import structure, location
from normalize_pilot_blocks import convert
from process_full_book import BASE, valid_cache, write_json
from sync_sources import fingerprint

IGNORED = {'header', 'footer', 'page_number'}
LABELS = {'定义': 'definition', '定理': 'theorem', '性质': 'property', '推论': 'corollary',
          '引理': 'lemma', '命题': 'proposition', '例': 'example'}
SECTION_IDS = {r['id'] for r in structure()['sections']}
SUBSECTION_IDS = {r['id'] for r in structure()['subsections']}


def plain(block):
    return ' '.join(content_strings(block.get('raw_block', block))).strip()


def markdown_segments(value):
    if isinstance(value, list):
        return ''.join(markdown_segments(x) for x in value)
    if not isinstance(value, dict):
        return str(value) if value is not None else ''
    content = value.get('content', '')
    if isinstance(content, (list, dict)):
        return markdown_segments(content)
    if value.get('type') == 'equation_inline':
        return '$' + str(content) + '$'
    if value.get('type') in {'equation', 'equation_interline'}:
        return '\n$$\n' + str(content) + '\n$$\n'
    return str(content or '')


def section_heading(text, kind):
    if kind != 'paragraph_title' and not text.lstrip().startswith('§'):
        return None
    match = re.match(r'^[§\s$\\]*([1-8]\s*\.\s*\d{1,2})(?![\d.])', text)
    identifier = re.sub(r'\s+', '', match.group(1)) if match else None
    return identifier if identifier in SECTION_IDS else None


def exercise_heading(text):
    match = re.match(r'^习\s*题\s*([1-8]\s*[.．]\s*\d{1,2})(?!\d)', text)
    identifier = re.sub(r'\s+', '', match.group(1)).replace('．', '.') if match else None
    return identifier if identifier in SECTION_IDS else None


def subsection_heading(text, kind):
    if kind != 'paragraph_title':
        return None
    match = re.match(r'^[\s$\\]*([1-8]\s*\.\s*\d{1,2}\s*\.\s*\d{1,2})(?![\d.])', text)
    identifier = re.sub(r'\s+', '', match.group(1)) if match else None
    return identifier if identifier in SUBSECTION_IDS else None


def numbered_parts(text):
    """Candidate answer labels; validate their order against section numbers downstream."""
    # Compact answer pages may contain several answers in one OCR paragraph.
    pattern = r'(?<!\S)([1-9]\d{0,2})(?:\s*[—–~至-]\s*([1-9]\d{0,2}))?\s*[.．、，,]'
    matches = list(re.finditer(pattern, text))
    parts = []
    for n, match in enumerate(matches):
        part = text[match.start():matches[n + 1].start() if n + 1 < len(matches) else len(text)].strip()
        low = int(match.group(1)); high = int(match.group(2) or low)
        if high < low or high - low > 100:
            continue
        parts.extend((number, part) for number in range(low, high + 1))
    return parts


def formula_segments(value, path=''):
    if isinstance(value, list):
        for n, child in enumerate(value):
            yield from formula_segments(child, f'{path}/{n}')
    elif isinstance(value, dict):
        if value.get('type', '').startswith('equation') and isinstance(value.get('content'), str):
            yield path, value['type'], value['content']
        if value.get('type') == 'table_body' and isinstance(value.get('content'), str):
            for n, match in enumerate(re.finditer(r'<eq>(.*?)</eq>', value['content'], re.DOTALL)):
                yield f'{path}/html/eq/{n}', 'equation_in_table', html.unescape(match.group(1))
        for key, child in value.items():
            if isinstance(child, (list, dict)):
                yield from formula_segments(child, f'{path}/{key}')


def new_object(kind, key, block, section=None, number=None):
    return {'id': key, 'kind': kind, 'section': section, 'number': number, 'pages': [], 'block_ids': [],
            'subsection': block.get('subsection'),
            'text_parts': [], 'source_id': block['source_id'], 'source_sha256': block['source_sha256'],
            'review_status': 'raw_ocr_pending_review', 'approved_for_tutoring': False}


def append_object(item, block, text=None):
    if block['pdf_page'] not in item['pages']:
        item['pages'].append(block['pdf_page'])
    if block['id'] not in item['block_ids']:
        item['block_ids'].append(block['id'])
    item['text_parts'].append(plain(block) if text is None else text)


def jsonl(path, records):
    path.write_text(''.join(json.dumps(x, ensure_ascii=False) + '\n' for x in records), encoding='utf-8')


def organize(base=BASE):
    base = Path(base)
    manifest = json.loads((base / 'manifest.json').read_text(encoding='utf-8'))
    cache = json.loads((base / 'ocr-cache.json').read_text(encoding='utf-8'))
    number_path = base / 'exercise-number-checks.json'
    number_source = json.loads(number_path.read_text(encoding='utf-8')) if number_path.exists() else {}
    number_checks = number_source.get('sections', {})
    page_hashes = {r['pdf_page']: r['image_sha256'] for r in manifest['pages']}
    if number_source and (number_source.get('source_sha256') != manifest['source_sha256'] or
                          any(c.get('image_sha256') != page_hashes.get(c['last_question_pdf_page']) for c in number_checks.values())):
        raise ValueError('Exercise number anchors belong to a different source/render version')
    toc = structure()
    pages = []; blocks = []; exercises = []; answers = []; units = []; formulas = []; assets = []
    current_section = None; current_subsection = None; exercise_section = None; active_question = None; active_unit = None
    answer_section = None; active_answer = None; answer_last_number = 0; last_chapter = None; last_processed = 0
    missing = []; issues = []
    anchor_file = base / 'source-anchors.json'
    anchors = json.loads(anchor_file.read_text(encoding='utf-8')).get('pages', {}) if anchor_file.exists() else {}
    check_file = base / 'source-page-checks.json'
    page_checks = json.loads(check_file.read_text(encoding='utf-8')).get('pages', {}) if check_file.exists() else {}
    boundary_path = base / 'block-boundary-reviews.json'
    boundary_source = json.loads(boundary_path.read_text(encoding='utf-8')) if boundary_path.exists() else {}
    if boundary_source and boundary_source.get('source_sha256') != manifest['source_sha256']:
        raise ValueError('Boundary annotations belong to a different source')
    boundary_reviews = {r['block_id']: r for r in boundary_source.get('reviews', [])}
    applied_boundary_reviews = set()
    for row in manifest['pages']:
        row = dict(row)
        if row['pdf_page'] > 488:
            row['printed_page_candidate'] = None
        anchor = anchors.get(str(row['pdf_page']))
        if anchor and anchor.get('image_sha256') == row['image_sha256']:
            row.update(printed_page_verified=anchor.get('printed_page'), page_mapping_status='assistant_visual_anchor_checked')
        page = row['pdf_page']; region, chapter, inferred_section = location(page)
        if not valid_cache(base, row, cache):
            missing.append(page)
            pages.append({**row, 'region': region['id'], 'chapter': chapter['id'] if chapter else None,
                          'ocr_status': 'missing_or_stale', 'text': '', 'blocks': [], 'content_characters': 0})
            continue
        output = base / 'mineru-basic' / f'pdf-{page:03}.json'
        raw = json.loads(output.read_text(encoding='utf-8'))
        records = convert(raw, manifest, row, fingerprint(output))
        check = page_checks.get(str(page), {})
        if check.get('image_sha256') != row['image_sha256']:
            check = {}
        if check.get('supplement_text'):
            supplement = {'type': 'manual_transcription', 'index': len(records),
                          'content': [{'type': 'text', 'content': check['supplement_text']}]}
            records.append({'id': f'manual-{manifest["source_id"]}-{page}', 'source_id': manifest['source_id'],
                            'source_sha256': manifest['source_sha256'], 'pdf_page': page, 'page_idx': page-1,
                            'printed_page': row.get('printed_page_verified'), 'block_index': len(records),
                            'type': 'manual_transcription', 'bbox_normalized': None,
                            'bbox_coordinate_space': 'not_localized_manual_page_transcription',
                            'segments': supplement['content'], 'raw_block': supplement,
                            'parser_output_sha256': None, 'channel': region['id'], 'page_image': row['image'],
                            'review_status': 'assistant_visual_transcription_pending_user_review', 'searchable': False})
        # Never carry an unfinished question over a missing source page.
        if page != last_processed + 1:
            active_question = active_unit = active_answer = None
            current_subsection = None
        last_processed = page
        if (chapter['id'] if chapter else None) != last_chapter:
            current_section = exercise_section = None; active_question = active_unit = None
            current_subsection = None
            last_chapter = chapter['id'] if chapter else None
        if chapter and current_section is None:
            candidates = [s for s in toc['sections'] if s['chapter'] == chapter['id'] and s['pdf_first'] < page]
            current_section = candidates[-1]['id'] if candidates else None
        text_parts = []; page_markdown = []; page_headings = []
        for block in records:
            text = plain(block); kind = block['type'] or ''
            block.update(channel=region['id'], chapter=chapter['id'] if chapter else None,
                         section=current_section, subsection=current_subsection, text=text, approved_for_tutoring=False)
            if kind in IGNORED or 'header' in kind or 'footer' in kind:
                block['excluded_from_reading_view'] = True
                blocks.append(block)
                continue
            heading = section_heading(text, kind) if region['id'] == 'body' else None
            subheading = subsection_heading(text, kind) if region['id'] == 'body' else None
            exheading = exercise_heading(text)
            if heading:
                current_section = heading; exercise_section = None; active_question = active_unit = None
                current_subsection = None
                page_headings.append({'kind': 'section', 'id': heading, 'block_id': block['id']})
            if region['id'] == 'body' and exheading:
                current_section = exercise_section = exheading; active_question = active_unit = None
                current_subsection = None
                page_headings.append({'kind': 'exercises', 'id': exheading, 'block_id': block['id']})
            if region['id'] == 'body' and re.match(r'^本章[小总]结', re.sub(r'\s+', '', text)):
                exercise_section = None; active_question = active_unit = None
                current_subsection = None
            if subheading:
                current_subsection = subheading; current_section = '.'.join(subheading.split('.')[:2])
                exercise_section = None; active_question = active_unit = None
                page_headings.append({'kind': 'subsection', 'id': subheading, 'block_id': block['id']})
            if region['id'] == 'answers' and exheading:
                answer_section = exheading; active_answer = None; answer_last_number = 0
                page_headings.append({'kind': 'answer_section', 'id': exheading, 'block_id': block['id']})
            block['section'] = answer_section if region['id'] == 'answers' else current_section
            block['subsection'] = current_subsection if region['id'] == 'body' else None
            text_parts.append(text)
            rendered = markdown_segments(block['segments'])
            if kind == 'paragraph_title':
                rendered = '### ' + rendered
            elif kind == 'equation' and not rendered.lstrip().startswith('$$'):
                rendered = '$$\n' + rendered + '\n$$'
            elif kind == 'image':
                rendered = (rendered + '\n\n' if rendered else '') + f'[图像区域：见原页](../../pages/pdf-{page:03}.png)'
            elif kind == 'table':
                rendered += f'\n\n[表格数值以原页为准](../../pages/pdf-{page:03}.png)'
            page_markdown.append(f'<!-- {block["id"]} -->\n{rendered}')
            if kind in {'image', 'table'}:
                assets.append({'id': f'asset-{block["id"]}', 'kind': kind, 'block_id': block['id'],
                               'pdf_page': page, 'bbox_normalized': block['bbox_normalized'],
                               'page_image': block['page_image'], 'review_status': 'raw_ocr_pending_review'})
            for path, formula_kind, latex in formula_segments(block['raw_block']):
                formulas.append({'id': f'formula-{block["id"]}-{len(formulas)}', 'block_id': block['id'],
                                 'pdf_page': page, 'section': block['section'], 'channel': region['id'],
                                 'subsection': block['subsection'], 'bbox_granularity': 'parent_block',
                                 'segment_path': path, 'kind': formula_kind, 'latex': latex,
                                 'bbox_normalized': block['bbox_normalized'], 'review_status': 'raw_ocr_pending_review'})
            if region['id'] == 'body' and exercise_section and not exheading:
                number = re.match(r'^([1-9]\d{0,2})\s*[.．、]\s*(?!\d)', text)
                review = boundary_reviews.get(block['id'])
                if review:
                    if (review['section'] != exercise_section or review['pdf_page'] != page
                            or review['parser_output_sha256'] != block['parser_output_sha256']
                            or review['image_sha256'] != row['image_sha256']):
                        raise ValueError('Stale/inconsistent exercise boundary annotation')
                    applied_boundary_reviews.add(review['id'])
                if number or review:
                    n = review['number'] if review else int(number.group(1))
                    active_question = new_object('exercise', f'mao3-{exercise_section}-{n}', block, exercise_section, n)
                    if review:
                        active_question.update(boundary_review_id=review['id'], boundary_review_status=review['review_status'],
                                               reading_order_warning=review.get('reading_order_warning', False))
                    exercises.append(active_question)
                if active_question:
                    append_object(active_question, block)
                    block['exercise_id'] = active_question['id']
            elif region['id'] == 'body' and not heading:
                semantic = re.match(r'^((?:定\s*义|定\s*理|性\s*质|推\s*论|引\s*理|命\s*题|例))\s*([1-8]\s*\.\s*\d+\s*\.\s*\d+)', text)
                if semantic:
                    label = re.sub(r'\s+', '', semantic.group(1)); number = re.sub(r'\s+', '', semantic.group(2))
                    active_unit = new_object(LABELS[label], f'{LABELS[label]}-{number}', block, current_section)
                    active_unit['source_number'] = number; active_unit['title'] = text[:180]
                    units.append(active_unit)
                elif kind == 'paragraph_title':
                    active_unit = None
                if active_unit:
                    append_object(active_unit, block)
                    block['unit_id'] = active_unit['id']
            if region['id'] == 'answers' and not exheading:
                parts = numbered_parts(text) if answer_section else []
                if parts:
                    prefix = text[:text.find(parts[0][1])].strip()
                    if prefix and active_answer:
                        append_object(active_answer, block, prefix)
                    for number, part in parts:
                        # Trusted source ranges are independent of observed question OCR.
                        # A decimal in a formula must not become e.g. answer 166 in a 49-question group.
                        maximum = number_checks.get(answer_section, {}).get('maximum_number', 199)
                        if number <= answer_last_number or number > maximum:
                            if active_answer:
                                append_object(active_answer, block, part)
                            continue
                        active_answer = new_object('reference_answer', f'answer-{answer_section}-{number}', block, answer_section, number)
                        active_answer['exercise_id_candidate'] = f'mao3-{answer_section}-{number}'
                        active_answer['boundary_status'] = 'regex_candidate_pending_source_review'
                        if re.match(r'^\d+\s*[—–~至-]\s*\d+', part):
                            active_answer['source_range_candidate'] = part
                        answer_last_number = number
                        answers.append(active_answer); append_object(active_answer, block, part)
                elif active_answer:
                    append_object(active_answer, block)
            blocks.append(block)
        text = '\n\n'.join(text_parts)
        pages.append({**row, 'region': region['id'], 'chapter': chapter['id'] if chapter else None,
                      'section_candidate': current_section if chapter else None, 'ocr_status': 'complete_unreviewed',
                      'content_characters': len(text), 'block_count': len(records), 'headings': page_headings,
                      'text': text, 'markdown': '\n\n'.join(page_markdown), 'blocks': [b['id'] for b in records],
                      'low_text_warning': len(text.strip()) < 30,
                      'page_visual_status': check.get('classification'),
                      'page_number_ocr': [plain(b) for b in records if b['type'] == 'page_number']})
    for items in (exercises, answers, units):
        for item in items:
            item['text'] = '\n'.join(item.pop('text_parts'))
    exercise_ids = collections.Counter(x['id'] for x in exercises)
    answer_ids = collections.Counter(x['id'] for x in answers)
    for answer in answers:
        answer['association_status'] = ('unique_number_match_candidate' if exercise_ids[answer['exercise_id_candidate']] == 1
                                         and answer_ids[answer['id']] == 1 else 'unresolved_or_ambiguous')
        answer['omitted_in_source_candidate'] = bool(re.search(r'略[.。]?\s*$', answer['text']))
    answer_groups = []
    answer_check_path = base / 'answer-group-source-checks.json'
    answer_check_source = json.loads(answer_check_path.read_text(encoding='utf-8')) if answer_check_path.exists() else {}
    if answer_check_source and answer_check_source.get('source_sha256') != manifest['source_sha256']:
        raise ValueError('Answer-group source checks belong to another book version')
    answer_checks = answer_check_source.get('groups', {})
    for section in toc['sections']:
        group_blocks = [b for b in blocks if b['channel'] == 'answers' and b.get('section') == section['id'] and not b.get('excluded_from_reading_view')]
        group = {'id': 'answer-group-' + section['id'], 'section': section['id'],
                              'pages': sorted({b['pdf_page'] for b in group_blocks}),
                              'block_ids': [b['id'] for b in group_blocks], 'review_status': 'raw_ocr_pending_review',
                              'source_answer_status': 'located' if group_blocks else 'unresolved',
                              'boundary': 'Exercise-group page locator only; shared pages do not identify an exact individual answer.'}
        check = answer_checks.get(section['id'])
        if check and not group_blocks:
            if check['evidence_image_sha256'] != page_hashes[check['evidence_pdf_pages'][0]]:
                raise ValueError('Answer-group source check image changed')
            group.update(source_answer_status=check['status'], source_check=check)
        answer_groups.append(group)
    group_lookup = {g['section']: g for g in answer_groups}
    for question in exercises:
        group = group_lookup[question['section']]
        question['answer_group_locator'] = {'id': group['id'], 'pages': group['pages'],
                                            'precision': 'exercise_group_pages_only', 'review_status': 'raw_ocr_pending_review',
                                            'source_answer_status': group['source_answer_status']}
    section_report = []
    for section in toc['sections']:
        found = [q['number'] for q in exercises if q['section'] == section['id']]
        gaps = sorted(set(range(1, max(found) + 1)) - set(found)) if found else []
        check = number_checks.get(section['id'])
        expected = check['maximum_number'] if check else None
        section_report.append({'section': section['id'], 'title': section['title'], 'candidates': len(found),
                               'maximum_number_observed': max(found) if found else None, 'internal_number_gaps': gaps,
                               'expected_maximum_from_source': expected,
                               'missing_expected_numbers': sorted(set(range(1, expected+1))-set(found)) if expected else None,
                               'unexpected_numbers': sorted(set(found)-set(range(1,expected+1))) if expected else None,
                               'expected_total_status': 'assistant_visual_endpoint_number_checked' if check else 'unknown_until_source_review'})
    low_text = [p['pdf_page'] for p in pages if p.get('low_text_warning')]
    report = {'source_sha256': manifest['source_sha256'], 'updated_at': dt.datetime.now().astimezone().isoformat(),
              'total_pdf_pages': manifest['page_count'], 'pages_with_valid_ocr': len(pages) - len(missing),
              'missing_pdf_pages': missing, 'coverage_complete': not missing,
              'chapters': len(toc['chapters']), 'sections': len(toc['sections']), 'subsections': len(toc['subsections']),
              'detected_subsection_heading_ids': sorted({h['id'] for p in pages for h in p.get('headings', []) if h['kind'] == 'subsection'}),
              'blocks': len(blocks), 'block_types': dict(collections.Counter(b['type'] for b in blocks)),
              'exercise_candidates': len(exercises), 'unique_exercise_ids': len(exercise_ids),
              'expected_exercise_ids_from_visual_number_boundaries': sum(c['maximum_number'] for c in number_checks.values()),
              'applied_source_checked_boundary_reviews': sorted(applied_boundary_reviews),
              'duplicate_exercise_ids': [k for k, n in exercise_ids.items() if n > 1],
              'cross_page_exercise_candidates': sum(len(q['pages']) > 1 for q in exercises),
              'reference_answer_candidates': len(answers), 'unique_answer_number_matches': sum(a['association_status'] == 'unique_number_match_candidate' for a in answers),
              'answer_sections_located': sum(bool(g['pages']) for g in answer_groups),
              'answer_sections_without_locator': [g['section'] for g in answer_groups if not g['pages']],
              'answer_sections_not_listed_in_source': [g['section'] for g in answer_groups if g['source_answer_status'] == 'not_listed_in_reference_answer_section'],
              'answer_sections_unresolved': [g['section'] for g in answer_groups if g['source_answer_status'] == 'unresolved'],
              'omitted_answer_candidates': sum(a['omitted_in_source_candidate'] for a in answers),
              'answer_numbers_without_question_candidate': [a['exercise_id_candidate'] for a in answers if exercise_ids[a['exercise_id_candidate']] == 0],
              'semantic_units': dict(collections.Counter(u['kind'] for u in units)),
              'formula_segments': len(formulas), 'assets': len(assets), 'low_text_pdf_pages': low_text,
              'sections_detail': section_report, 'review_status': 'raw_ocr_pending_review',
              'raw_archive_searchable': True, 'approved_for_tutoring': False,
              'boundary': 'Page coverage is not transcription accuracy. Object boundaries and answer links are candidates; no automatic tutoring release.'}
    write_json(base / 'structure.json', toc)
    jsonl(base / 'normalized-blocks.jsonl', blocks)
    jsonl(base / 'page-catalog.jsonl', pages)
    jsonl(base / 'exercise-candidates.jsonl', exercises)
    jsonl(base / 'answer-candidates.jsonl', answers)
    write_json(base / 'answer-section-locations.json', {'groups': answer_groups, 'boundary': 'Group-level navigation, not exact answer approval.'})
    jsonl(base / 'learning-units.jsonl', units)
    jsonl(base / 'formulas.jsonl', formulas)
    jsonl(base / 'assets.jsonl', assets)
    write_json(base / 'organization-report.json', report)
    export_structure_graph(base, toc, pages, exercises, answers, units, answer_groups)
    build_database(base, pages, blocks, exercises, answers, units)
    export_markdown(base, manifest, toc, pages, report)
    export_indexes(base, toc, exercises, answers, units, formulas, assets)
    export_offline_html(base, toc, pages, blocks, exercises + answers + units, report)
    export_review_sheet(base, pages)
    print(json.dumps({k: v for k, v in report.items() if k != 'sections_detail'}, ensure_ascii=False, indent=2))
    return report


def build_database(base, pages, blocks, exercises, answers, units):
    path = base / 'catalog-building.sqlite3'
    if path.exists():
        path.unlink()
    with sqlite3.connect(path) as db:
        db.executescript('''CREATE TABLE pages(pdf_page INTEGER PRIMARY KEY,region TEXT,chapter TEXT,status TEXT,text TEXT,data TEXT);
          CREATE TABLE blocks(id TEXT PRIMARY KEY,pdf_page INTEGER,section TEXT,kind TEXT,text TEXT,data TEXT);
          CREATE INDEX page_blocks ON blocks(pdf_page);
          CREATE TABLE objects(id TEXT,kind TEXT,section TEXT,number INTEGER,text TEXT,data TEXT);
          CREATE INDEX object_section ON objects(section,kind);
          CREATE VIRTUAL TABLE page_search USING fts5(text,tokenize='trigram');''')
        db.executemany('INSERT INTO pages VALUES(?,?,?,?,?,?)', [(p['pdf_page'], p['region'], p['chapter'], p['ocr_status'], p['text'], json.dumps(p, ensure_ascii=False)) for p in pages])
        db.executemany('INSERT INTO page_search(rowid,text) VALUES(?,?)', [(p['pdf_page'], p['text']) for p in pages])
        db.executemany('INSERT INTO blocks VALUES(?,?,?,?,?,?)', [(b['id'], b['pdf_page'], b.get('section'), b['type'], b['text'], json.dumps(b, ensure_ascii=False)) for b in blocks])
        db.executemany('INSERT INTO objects VALUES(?,?,?,?,?,?)', [(x['id'], x['kind'], x['section'], x.get('number'), x['text'], json.dumps(x, ensure_ascii=False)) for x in exercises + answers + units])
    db.close()
    for attempt in range(6):
        try:
            path.replace(base / 'catalog.sqlite3')
            break
        except PermissionError:
            if attempt == 5:
                raise
            time.sleep(.1 * (2 ** attempt))


def export_markdown(base, manifest, toc, pages, report):
    export = base / 'exports'
    for directory in ('pages', 'chapters', 'sections'):
        (export / directory).mkdir(parents=True, exist_ok=True)
    preface = '# 概率论与数理统计教程（第三版）· 私有全书整理\n\n'
    preface += f'> 原书490页；当前有效OCR {report["pages_with_valid_ocr"]}/490 页。识别稿待校对，公式、表格与答案以原页为准。\n\n来源 SHA256：`{manifest["source_sha256"]}`\n\n'
    all_parts = [preface]
    by_region = collections.defaultdict(list); by_chapter = collections.defaultdict(list)
    for page in pages:
        n = page['pdf_page']
        candidate = page.get('printed_page_candidate')
        heading = f'## PDF第{n}页' + (f' · 印刷页候选 {candidate}' if candidate else ' · 书前页')
        content = page.get('markdown', '> 此页尚未识别。') or '> 本页未识别出可读文字；请查看原页，不能直接判作空白。'
        single = f'{heading}\n\n[原始页图](../../pages/pdf-{n:03}.png)\n\n{content}\n'
        (export / 'pages' / f'pdf-{n:03}.md').write_text(single, encoding='utf-8')
        combined = f'{heading}\n\n[原始页图](../pages/pdf-{n:03}.png)\n\n{content.replace("../../pages/", "../pages/")}\n'
        all_parts.append(combined)
        by_region[page['region']].append(single)
        if page.get('chapter'):
            by_chapter[page['chapter']].append(single)
    (export / '全书识别稿.md').write_text('\n\n---\n\n'.join(all_parts), encoding='utf-8')
    for chapter in toc['chapters']:
        (export / 'chapters' / f'{chapter["id"]}-{chapter["title"]}.md').write_text(
            f'# 第{chapter["id"]}章 {chapter["title"]}\n\n> OCR识别稿，待校对。\n\n' + '\n\n'.join(by_chapter[chapter['id']]), encoding='utf-8')
    for region in toc['regions']:
        if region['id'] != 'body':
            (export / 'chapters' / f'{region["id"]}-{region["title"]}.md').write_text(
                f'# {region["title"]}\n\n> OCR识别稿，待校对。\n\n' + '\n\n'.join(by_region[region['id']]), encoding='utf-8')
    # Section boundaries use normalized block membership, including two sections on the same page.
    block_rows = [json.loads(line) for line in (base / 'normalized-blocks.jsonl').read_text(encoding='utf-8').splitlines()]
    for section in toc['sections']:
        selected = [b for b in block_rows if b['channel'] == 'body' and b.get('section') == section['id'] and not b.get('excluded_from_reading_view')]
        parts = [f'# {section["id"]} {section["title"]}\n\n> OCR识别稿，待校对；正文、公式、例题和课后题按书中顺序保留。\n']
        page = None
        for block in selected:
            if block['pdf_page'] != page:
                page = block['pdf_page']; parts.append(f'\n## PDF第{page}页\n\n[查看原页](../../pages/pdf-{page:03}.png)\n')
            parts.append(markdown_segments(block['segments']) or f'[{block["type"]}，见原页]')
        (export / 'sections' / f'{section["id"]}-{section["title"]}.md').write_text('\n\n'.join(parts), encoding='utf-8')
    index = preface + '| 章节 | PDF页 | 阅读稿 |\n| --- | --- | --- |\n'
    for chapter in toc['chapters']:
        name = f'{chapter["id"]}-{chapter["title"]}.md'
        index += f'| 第{chapter["id"]}章 {chapter["title"]} | {chapter["pdf_first"]}–{chapter["pdf_last"]} | [打开](chapters/{name}) |\n'
    for region in toc['regions']:
        if region['id'] != 'body':
            index += f'| {region["title"]} | {region["pdf_first"]}–{region["pdf_last"]} | [打开](chapters/{region["id"]}-{region["title"]}.md) |\n'
    index += '\n[全书连续识别稿](全书识别稿.md) · [浏览与搜索](http://127.0.0.1:8771/library)\n\n'
    index += '[离线资料库](全书资料库.html) · [习题目录](习题目录.md) · [知识条目索引](知识条目索引.md) · [参考答案索引](参考答案索引.md) · [图表索引](图表索引.md)\n\n'
    index += '所有490页的图像均保留。版面中的图片、曲线和表格通过原页可复核；OCR没有识别出的图文不能由文字稿替代。\n\n'
    index += '题目、答案、公式、定义/定理/例题候选分别存储于上一级目录JSONL；原始解析JSON与内容块保留，不自动覆盖已校对的第一章辅导题库。\n'
    (export / '开始阅读.md').write_text(index, encoding='utf-8')


def export_indexes(base, toc, exercises, answers, units, formulas, assets):
    export = base / 'exports'
    def cell(value, length=100):
        return str(value).replace('\n', ' ').replace('|', '\\|')[:length]
    def links(item):
        return '、'.join(f'[PDF {p}](pages/pdf-{p:03}.md)' for p in item['pages'])
    questions = ['# 全书课后习题目录\n\n> 自动切分候选，题干、边界和编号仍待对照原页校对。完整文字和表格见逐页稿及原图。\n']
    answer_lines = ['# 全书参考答案索引\n\n> 原书参考答案的编号候选，不是助手生成的解答。唯一编号匹配仍待审核；原书“略”不补成已有证明。\n']
    answer_groups = json.loads((base / 'answer-section-locations.json').read_text(encoding='utf-8'))['groups']
    for section in toc['sections']:
        questions.append(f'\n## {section["id"]} {section["title"]}\n\n| 题号 | 题干预览（OCR） | 出处 |\n| --- | --- | --- |')
        for item in exercises:
            if item['section'] == section['id']:
                questions.append(f'| {item["number"]} | {cell(item["text"])} | {links(item)} |')
        group = next(g for g in answer_groups if g['section'] == section['id'])
        group_links = '、'.join(f'[PDF {n}](pages/pdf-{n:03}.md)' for n in group['pages'])
        if not group_links:
            group_links = '本书参考答案区未列出该习题组（不补造解答）' if group['source_answer_status'] == 'not_listed_in_reference_answer_section' else '尚未定位'
        answer_lines.append(f'\n## 习题{section["id"]}\n\n题组答案所在页：{group_links}。同页可能包含其他题组；逐题边界待审。\n\n| 题号 | 原书省略标记候选 | 编号关联 | 出处 |\n| --- | --- | --- | --- |')
        for item in answers:
            if item['section'] == section['id']:
                answer_lines.append(f'| {item["number"]} | {"略" if item["omitted_in_source_candidate"] else ""} | {"唯一编号匹配，待审核" if item["association_status"] == "unique_number_match_candidate" else "未解决/有歧义"} | {links(item)} |')
    (export / '习题目录.md').write_text('\n'.join(questions), encoding='utf-8')
    (export / '参考答案索引.md').write_text('\n'.join(answer_lines), encoding='utf-8')
    names = {'definition': '定义', 'theorem': '定理', 'property': '性质', 'example': '例题',
             'corollary': '推论', 'lemma': '引理', 'proposition': '命题'}
    lines = ['# 全书知识条目索引\n\n> 从原文标签切分的候选条目；尚未完成语义命名、先修关系和适用条件审核。\n']
    for chapter in toc['chapters']:
        lines.append(f'\n## 第{chapter["id"]}章 {chapter["title"]}\n\n| 类型与编号 | 原文开头（OCR） | 出处 |\n| --- | --- | --- |')
        for item in units:
            if item['source_number'].startswith(chapter['id'] + '.'):
                lines.append(f'| {names[item["kind"]]} {item["source_number"]} | {cell(item["text"])} | {links(item)} |')
    (export / '知识条目索引.md').write_text('\n'.join(lines), encoding='utf-8')
    lines = ['# 全书图表索引\n\n> 原始图表区域均可回看。表格识别值和图像语义尚未完成逐项校对。\n\n| 类型 | PDF页 | 版面区域（归一化坐标） |\n| --- | --- | --- |']
    for asset in assets:
        n = asset['pdf_page']
        lines.append(f'| {"表格" if asset["kind"] == "table" else "图像"} | [PDF {n}](../pages/pdf-{n:03}.png) | {asset["bbox_normalized"]} |')
    (export / '图表索引.md').write_text('\n'.join(lines), encoding='utf-8')
    with (export / '公式索引.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        fields = ['id', 'pdf_page', 'section', 'subsection', 'channel', 'kind', 'latex', 'block_id', 'review_status']
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore'); writer.writeheader(); writer.writerows(formulas)


def export_review_sheet(base, pages):
    target = base / 'page-review.csv'
    existing = {}
    if target.exists():
        with target.open(encoding='utf-8-sig', newline='') as stream:
            existing = {int(r['pdf_page']): r for r in csv.DictReader(stream)}
    fields = ['pdf_page', 'region', 'chapter', 'printed_page_candidate', 'ocr_status', 'text_characters', 'low_text_warning',
              'printed_page_verified', 'text_review', 'formula_review', 'table_figure_review', 'reviewer', 'notes']
    with target.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader()
        for p in pages:
            old = existing.get(p['pdf_page'], {})
            item = {k: old.get(k, '') for k in fields}
            item.update(pdf_page=p['pdf_page'], region=p['region'], chapter=p.get('chapter'),
                        printed_page_candidate=p.get('printed_page_candidate'), ocr_status=p['ocr_status'],
                        text_characters=p['content_characters'], low_text_warning=p.get('low_text_warning', False))
            writer.writerow(item)


def export_offline_html(base, toc, pages, blocks, objects, report):
    """The same reader works from a local file, without a server or network access."""
    from book_library import HTML
    by_page = collections.defaultdict(list)
    for block in blocks:
        if not block.get('excluded_from_reading_view'):
            by_page[block['pdf_page']].append({key: block.get(key) for key in
                ('id', 'type', 'text', 'segments', 'bbox_normalized', 'section', 'subsection', 'exercise_id', 'unit_id')})
    page_data = {str(p['pdf_page']): {**{k: v for k, v in p.items() if k not in ('markdown', 'blocks')},
                                      'blocks': by_page[p['pdf_page']]} for p in pages}
    payload = {'overview': {'structure': toc, 'report': report,
                            'progress': {'completed_pages': report['pages_with_valid_ocr']}},
               'pages': page_data, 'objects': objects}
    encoded = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c')
    local_api = '''async function api(url){const u=new URL(url,'http://local');const a=u.searchParams;
      if(u.pathname==='/api/library')return LOCAL.overview;
      if(u.pathname==='/api/library/page'){const p=LOCAL.pages[a.get('n')];if(!p)throw Error('页码应在1至490之间');return p;}
      if(u.pathname==='/api/library/search'){const q=(a.get('q')||'').trim(),r=a.get('region')||'all';if(!q)throw Error('请输入关键词');const terms=q.split(/\\s+/);return{hits:Object.values(LOCAL.pages).filter(p=>(r==='all'?p.region!=='answers':p.region===r)&&terms.every(t=>p.text.includes(t))).slice(0,30).map(p=>{let n=Math.max(0,p.text.indexOf(terms[0])-85);return{pdf_page:p.pdf_page,snippet:p.text.slice(n,n+420)}})};}
      if(u.pathname==='/api/library/objects'){const s=a.get('section'),k=a.get('kind'),start=Number(a.get('offset')||0);const items=LOCAL.objects.filter(x=>x.kind===k&&(!s||x.section===s));return{total:items.length,items:items.slice(start,start+50)};}
      throw Error('此离线入口不支持该操作');}
    '''
    start = HTML.index('async function api(url)')
    end = HTML.index('async function openPage(n)')
    content = HTML[:start] + 'const LOCAL=' + encoded + ';\n' + local_api + HTML[end:]
    content = content.replace("'/book-page/'+n+'.png'", "'../pages/pdf-'+String(n).padStart(3,'0')+'.png'")
    content = content.replace('href="/library-export/book.md"', 'href="全书识别稿.md"')
    content = content.replace('href="/"', 'href="http://127.0.0.1:8771/"').replace('href="/pilot"', 'href="http://127.0.0.1:8771/pilot"')
    content = content.replace('本机私有资料</span>', '离线阅读 · 本机私有资料</span>')
    (base / 'exports/全书资料库.html').write_text(content, encoding='utf-8')


def export_structure_graph(base, toc, pages, exercises, answers, units, answer_groups):
    """Document location edges only; section membership is not a claim of tested concepts."""
    nodes = []; edges = []
    for kind, rows in [('chapter', toc['chapters']), ('section', toc['sections']), ('subsection', toc['subsections'])]:
        for row in rows:
            identifier = kind + '-' + row['id']
            nodes.append({'id': identifier, 'kind': kind, 'label': row['id'] + ' ' + row['title'], 'pdf_first': row['pdf_first']})
            if kind != 'chapter':
                parent = ('chapter-' + row['id'].split('.')[0]) if kind == 'section' else 'section-' + '.'.join(row['id'].split('.')[:2])
                edges.append({'from': identifier, 'to': parent, 'kind': 'part_of_book_structure', 'review_status': 'source_toc_transcribed'})
    seen = collections.Counter(x['id'] for x in exercises + units + answers)
    for group in answer_groups:
        if group['pages']:
            nodes.append({'id': group['id'], 'kind': 'reference_answer_group', 'label': '习题' + group['section'] + '答案页组',
                          'pdf_pages': group['pages'], 'review_status': 'raw_ocr_pending_review'})
    for item in exercises + units + answers:
        if seen[item['id']] != 1:
            continue
        nodes.append({'id': item['id'], 'kind': item['kind'], 'label': item.get('title', item['id']), 'pdf_pages': item['pages'], 'review_status': item['review_status']})
        if item.get('section'):
            edges.append({'from': item['id'], 'to': 'section-' + item['section'], 'kind': 'located_in_section_candidate', 'review_status': 'raw_ocr_pending_review'})
        if item.get('subsection'):
            edges.append({'from': item['id'], 'to': 'subsection-' + item['subsection'], 'kind': 'located_in_subsection_candidate', 'review_status': 'raw_ocr_pending_review'})
        if item.get('association_status') == 'unique_number_match_candidate':
            edges.append({'from': item['exercise_id_candidate'], 'to': item['id'], 'kind': 'reference_answer_number_match_candidate', 'review_status': 'raw_ocr_pending_review'})
        if item.get('answer_group_locator', {}).get('pages'):
            edges.append({'from': item['id'], 'to': item['answer_group_locator']['id'], 'kind': 'reference_answer_group_page_locator',
                          'review_status': 'raw_ocr_pending_review'})
    write_json(base / 'book-structure-graph.json', {'nodes': nodes, 'edges': edges,
        'boundary': 'Document navigation graph. No automatic prerequisite/tested-concept semantic edges inferred from section membership.',
        'approved_for_tutoring': False})


if __name__ == '__main__':
    organize()
