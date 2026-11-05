"""Render a private 20-page OCR pilot without changing or uploading the source PDF."""
import argparse
import csv
import json
import shutil
import subprocess
from pathlib import Path
from sync_sources import ROOT, fingerprint, poppler_tool

# 1-based PDF pages. Printed page candidates are not trusted until visually checked.
PAGES = [23, 24, 27, 32, 33, 37, 49, 51, 57, 58, 60, 62, 65, 67, 69, 74, 76, 77, 469, 470]


def prepare(output=None, dpi=160, pages=None):
    output = Path(output) if output else ROOT / 'data/private/ocr-pilot'
    if not output.resolve().is_relative_to((ROOT / 'data/private').resolve()):
        raise ValueError('Pilot must remain in the private project directory')
    registry = json.loads((ROOT / 'data/private/textbook_registry/manifest.json').read_text(encoding='utf-8'))
    source = next(x for x in registry['files'] if x['role'] == 'textbook')
    pdf = Path(source['path'])
    if fingerprint(pdf) != source['sha256']:
        raise ValueError('Source changed: register the new version before rendering')
    executable = str(poppler_tool('pdftoppm'))
    (output / 'pages').mkdir(parents=True, exist_ok=True)
    manifest_path = output / 'manifest.json'
    old = json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else {}
    if old and (old.get('source_sha256') != source['sha256'] or old.get('dpi') != dpi):
        raise ValueError('Use a new output directory for changed source/render settings')
    records = []
    old_pages = {row['pdf_page']: row for row in old.get('pages', [])}
    for page in (PAGES if pages is None else pages):
        prefix = output / 'pages' / f'pdf-{page:03}'
        target = prefix.with_suffix('.png')
        if not target.exists():
            subprocess.run([executable, '-f', str(page), '-l', str(page), '-r', str(dpi),
                            '-singlefile', '-png', str(pdf), str(prefix)], check=True,
                           capture_output=True, timeout=90)
        records.append({'pdf_page': page, 'page_idx': page - 1,
                        'printed_page_candidate': str(page - 22),
                        'page_mapping_status': 'candidate_pending_visual_review',
                        'image': str(target.relative_to(output)), 'image_sha256': fingerprint(target),
                        'purpose': 'boundary_check' if page in (76, 77) else ('reference_answer' if page >= 469 else 'chapter1_pilot'),
                        'ocr_status': 'not_run', 'searchable': False})
        previous = old_pages.get(page, {})
        if previous.get('image_sha256') == records[-1]['image_sha256']:
            for field in ('printed_page_verified', 'page_mapping_status', 'ocr_status'):
                if field in previous:records[-1][field] = previous[field]
    manifest = {'schema_version': 1, 'source_id': source['id'], 'source_sha256': source['sha256'],
                'source_path': str(pdf), 'dpi': dpi, 'access': 'private_local',
                'pages': records, 'page_count': len(records),
                'boundary': 'Rendering and OCR are not validated textbook content; no automatic release to retrieval.'}
    if 'chapter1_boundary' in old:manifest['chapter1_boundary'] = old['chapter1_boundary']
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    # Do not overwrite subsequent human review work on reruns.
    sheet = output / 'page-review.csv'
    if not sheet.exists():
        with sheet.open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=['pdf_page', 'printed_page_candidate', 'printed_page_verified',
                                    'section', 'question_numbers', 'formula_check', 'reviewer', 'review_status', 'notes'])
            writer.writeheader()
            for row in records:
                writer.writerow({'pdf_page': row['pdf_page'], 'printed_page_candidate': row['printed_page_candidate'],
                                 'review_status': 'pending'})
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output')
    parser.add_argument('--dpi', type=int, default=160)
    args = parser.parse_args()
    result = prepare(args.output, args.dpi)
    print(json.dumps({'pages': result['page_count'], 'access': result['access'], 'searchable': False}))
