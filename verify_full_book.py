"""Audit source/page coverage and export integrity, never certify OCR mathematics."""
import collections
import csv
import datetime as dt
import json
import re
import sqlite3
from contextlib import closing
from pathlib import Path
from process_full_book import BASE, valid_cache, write_json
from sync_sources import fingerprint


def load_lines(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def formula_flags(latex):
    flags = []
    unescaped = re.sub(r'\\[{}]', '', latex)
    depth = 0
    for character in unescaped:
        if character == '{':
            depth += 1
        elif character == '}':
            depth -= 1
        if depth < 0:
            break
    if depth != 0:
        flags.append('unbalanced_latex_braces')
    if re.search(r'\\(?:d?frac|tfrac)\s*(?:\{\s*\}|\{[^{}]*\}\s*\{\s*\})', latex):
        flags.append('empty_fraction_component')
    begins = re.findall(r'\\begin\{([^}]+)\}', latex)
    ends = re.findall(r'\\end\{([^}]+)\}', latex)
    if collections.Counter(begins) != collections.Counter(ends):
        flags.append('mismatched_latex_environment')
    return flags


def verify(base=BASE):
    base = Path(base)
    manifest = json.loads((base / 'manifest.json').read_text(encoding='utf-8'))
    report = json.loads((base / 'organization-report.json').read_text(encoding='utf-8'))
    cache = json.loads((base / 'ocr-cache.json').read_text(encoding='utf-8'))
    pages = load_lines(base / 'page-catalog.jsonl'); blocks = load_lines(base / 'normalized-blocks.jsonl')
    formulas = load_lines(base / 'formulas.jsonl'); assets = load_lines(base / 'assets.jsonl')
    exercises = load_lines(base / 'exercise-candidates.jsonl'); answers = load_lines(base / 'answer-candidates.jsonl')
    expected = set(range(1, 491)); failures = []
    if fingerprint(Path(manifest['source_path'])) != manifest['source_sha256']:
        failures.append('Original source SHA256 changed')
    if len(pages) != 490 or {p['pdf_page'] for p in pages} != expected:
        failures.append('Page catalog must contain each of the 490 source pages exactly once')
    damaged_images = []; missing_outputs = []
    for row in manifest['pages']:
        image = base / row['image']
        if not image.exists() or fingerprint(image) != row['image_sha256']:
            damaged_images.append(row['pdf_page'])
        if not valid_cache(base, row, cache):
            missing_outputs.append(row['pdf_page'])
    if damaged_images:
        failures.append('Page image hash mismatch')
    if missing_outputs or not report['coverage_complete']:
        failures.append('OCR page coverage incomplete')
    ids = {b['id'] for b in blocks}
    if len(ids) != len(blocks):
        failures.append('Duplicate content block identities')
    if any(f['block_id'] not in ids for f in formulas) or any(a['block_id'] not in ids for a in assets):
        failures.append('Orphaned formula or visual asset')
    if any(b['source_sha256'] != manifest['source_sha256'] or b['page_idx'] != b['pdf_page'] - 1 for b in blocks):
        failures.append('Broken original-PDF provenance')
    if any(set(x['block_ids']) - ids for x in exercises + answers):
        failures.append('Orphaned exercise/answer block reference')
    retained = collections.defaultdict(list)
    for block in blocks:
        if block.get('parser_output_sha256'):
            retained[block['pdf_page']].append(block)
    raw_block_mismatches = []
    for row in manifest['pages']:
        page = row['pdf_page']
        if page in missing_outputs:
            continue
        original = json.loads((base / 'mineru-basic' / f'pdf-{page:03}.json').read_text(encoding='utf-8'))['pages'][0].get('blocks', [])
        normalized = retained[page]
        if len(original) != len(normalized) or any(raw != item['raw_block'] for raw, item in zip(original, normalized)):
            raw_block_mismatches.append(page)
    if raw_block_mismatches:
        failures.append('Raw OCR block content lost or changed during organization')
    with closing(sqlite3.connect((base / 'catalog.sqlite3').as_uri() + '?mode=ro', uri=True)) as db:
        database_pages = db.execute('SELECT COUNT(*) FROM pages').fetchone()[0]
        database_valid_pages = db.execute("SELECT COUNT(*) FROM pages WHERE status='complete_unreviewed'").fetchone()[0]
        integrity = db.execute('PRAGMA integrity_check').fetchone()[0]
    if database_pages != 490 or database_valid_pages != 490 or integrity != 'ok':
        failures.append('SQLite catalog coverage/integrity failed')
    exported_pages = list((base / 'exports/pages').glob('pdf-*.md'))
    exported_sections = list((base / 'exports/sections').glob('*.md'))
    exported_chapters = list((base / 'exports/chapters').glob('*.md'))
    if len(exported_pages) != 490 or len(exported_sections) != 43 or len(exported_chapters) != 12:
        failures.append('Missing page/section/chapter reading exports')
    if any(not (base / 'exports' / name).is_file() for name in ['全书资料库.html', '开始阅读.md', '全书识别稿.md']):
        failures.append('Missing reading entry')
    offline_valid_pages = 0
    offline = (base / 'exports/全书资料库.html').read_text(encoding='utf-8')
    if 'const LOCAL=' in offline:
        payload, _ = json.JSONDecoder().raw_decode(offline.split('const LOCAL=', 1)[1])
        offline_valid_pages = sum(p['ocr_status'] == 'complete_unreviewed' for p in payload['pages'].values())
    if offline_valid_pages != 490:
        failures.append('Offline reader content is incomplete/stale')
    if '此页尚未识别' in (base / 'exports/全书识别稿.md').read_text(encoding='utf-8'):
        failures.append('Merged Markdown still contains missing-page placeholders')
    # Heuristics route review effort; they are not a mathematical accuracy score.
    formula_issues = collections.defaultdict(list); formula_counts = collections.Counter()
    table_counts = collections.Counter(a['pdf_page'] for a in assets if a['kind'] == 'table')
    for f in formulas:
        formula_counts[f['pdf_page']] += 1
        for flag in formula_flags(f['latex']):
            formula_issues[f['pdf_page']].append({'formula_id': f['id'], 'flag': flag})
    queue = []
    known_issues = collections.defaultdict(list)
    pilot_sheet = base.parent / 'ocr-pilot/ocr-quality-review.csv'
    if pilot_sheet.exists():
        with pilot_sheet.open(encoding='utf-8-sig', newline='') as stream:
            for row in csv.DictReader(stream):
                if row.get('assistant_result') != 'correction_required':
                    continue
                page = int(row['pdf_page'])
                first = base.parent / 'ocr-pilot/mineru-basic' / f'pdf-{page:03}.json'
                current = base / 'mineru-basic' / f'pdf-{page:03}.json'
                if first.exists() and current.exists() and fingerprint(first) == fingerprint(current):
                    known_issues[page].append(row['id'])
    for page in pages:
        n = page['pdf_page']; flags = []
        if page['ocr_status'] != 'complete_unreviewed':
            flags.append('missing_ocr')
        if page.get('low_text_warning') and page.get('page_visual_status') not in {'blank_visually_checked', 'dedication'}:
            flags.append('low_text_needs_visual_check')
        flags += sorted({f['flag'] for f in formula_issues[n]})
        if table_counts[n]:
            flags.append('table_values_require_source_review')
        if formula_counts[n] >= 40:
            flags.append('dense_mathematics')
        if known_issues[n]:
            flags.append('source_checked_math_issue_retained_in_raw')
        score = 10 * ('missing_ocr' in flags) + 8 * ('low_text_needs_visual_check' in flags) + 4 * len(formula_issues[n]) + 2 * table_counts[n] + ('dense_mathematics' in flags) + 12 * bool(known_issues[n])
        queue.append({'pdf_page': n, 'region': page['region'], 'priority_score': score,
                      'formula_segments': formula_counts[n], 'tables': table_counts[n],
                      'known_issue_ids': ';'.join(known_issues[n]),
                      'flags': ';'.join(flags), 'review_status': 'pending', 'reviewer': '', 'notes': ''})
    queue.sort(key=lambda x: (-x['priority_score'], x['pdf_page']))
    sheet = base / 'quality-review-queue.csv'
    old = {}
    if sheet.exists():
        with sheet.open(encoding='utf-8-sig', newline='') as stream:
            old = {int(r['pdf_page']): r for r in csv.DictReader(stream)}
    with sheet.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(queue[0])); writer.writeheader()
        for row in queue:
            for field in ('review_status', 'reviewer', 'notes'):
                row[field] = old.get(row['pdf_page'], {}).get(field, row[field])
            writer.writerow(row)
    result = {'checked_at': dt.datetime.now().astimezone().isoformat(), 'source_sha256': manifest['source_sha256'],
              'status': 'coverage_integrity_passed' if not failures else 'incomplete_or_failed', 'failures': failures,
              'source_pages': 490, 'page_catalog_rows': len(pages), 'valid_ocr_pages': 490 - len(missing_outputs),
              'damaged_image_pages': damaged_images, 'missing_ocr_pages': missing_outputs,
              'region_page_counts': dict(collections.Counter(p['region'] for p in pages)),
              'markdown_pages': len(exported_pages), 'markdown_sections': len(exported_sections), 'markdown_chapters_and_regions': len(exported_chapters),
              'sqlite_integrity': integrity, 'source_page_anchors_visually_checked': len(json.loads((base / 'source-anchors.json').read_text(encoding='utf-8'))['pages']),
              'sqlite_valid_ocr_pages': database_valid_pages, 'offline_valid_ocr_pages': offline_valid_pages,
              'raw_block_mismatch_pages': raw_block_mismatches,
              'formula_syntax_flag_count': sum(len(x) for x in formula_issues.values()),
              'pages_with_formula_syntax_flags': sorted(n for n, flags in formula_issues.items() if flags),
              'quality_review_queue': str(sheet.relative_to(base)),
              'mathematical_accuracy': 'not_certified', 'teacher_review': 'pending',
              'boundary': 'Coverage and hash integrity only. Formula flags are review heuristics; no flag does not mean a formula is correct.'}
    write_json(base / 'coverage-audit.json', result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


if __name__ == '__main__':
    result = verify()
    raise SystemExit(0 if result['status'] == 'coverage_integrity_passed' else 1)
