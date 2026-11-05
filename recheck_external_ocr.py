"""Re-recognize selected 660B question pages into a separate local review archive."""
import json
import os
import subprocess

from external_question_bank import BASE, DEFAULT_SOURCE, POPPLER, parse_batch, page_blocks, write_json
from sync_sources import fingerprint


OUT = BASE / 'recognition-review-20261105'
TARGETS = ('660b-c1-q007', '660b-c1-q018', '660b-c1-q060',
           '660b-c3-q022', '660b-c5-q007', '660b-c6-q077')
DPI = 300


def run():
    with (BASE / 'dataset/questions.jsonl').open(encoding='utf-8') as stream:
        questions = {row['id']: row for row in map(json.loads, stream)}
    manifest = json.loads((BASE / 'manifest.json').read_text(encoding='utf-8'))
    source_sha = fingerprint(DEFAULT_SOURCE)
    if source_sha != manifest['source_sha256']:
        raise ValueError('660B source PDF has changed')
    for folder in ('pages', 'logs', 'mineru-basic'):
        (OUT / folder).mkdir(parents=True, exist_ok=True)
    pages = sorted({page for case_id in TARGETS for page in questions[case_id]['pages']})
    if not all(6 <= page <= 87 for page in pages):
        raise ValueError('Only question pages can be re-recognized')
    rows = []
    for page in pages:
        name = f'pages/pdf-{page:03}.png'
        target = OUT / name
        subprocess.run([str(POPPLER), '-f', str(page), '-l', str(page), '-r', str(DPI),
                        '-singlefile', '-png', str(DEFAULT_SOURCE), str(target.with_suffix(''))],
                       check=True, capture_output=True, timeout=120)
        rows.append({'pdf_page': page, 'image': name, 'image_sha256': fingerprint(target)})
    write_json(OUT / 'input-manifest.json', {'source_sha256': source_sha, 'dpi': DPI, 'pages': rows, 'target_ids': TARGETS})
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    batches = []
    for offset in range(0, len(rows), 4):
        batch = parse_batch(rows[offset:offset + 4], 1, OUT)
        batches.append(batch)
        print(json.dumps(batch), flush=True)
        if batch['returncode'] != 0:
            raise RuntimeError(f"OCR batch failed. See {batch['log']}")
    normalized = []
    for row in rows:
        page = row['pdf_page']
        output = OUT / 'mineru-basic' / f'pdf-{page:03}.json'
        blocks = page_blocks(json.loads(output.read_text(encoding='utf-8')))
        if not any(block['text'] for block in blocks):
            raise ValueError(f'Empty OCR result for PDF page {page}')
        normalized.append({**row, 'source_sha256': source_sha, 'ocr_sha256': fingerprint(output), 'blocks': blocks})
    write_json(OUT / 'recognized-pages.json', normalized)
    write_json(OUT / 'ocr-run.json', {'dpi': DPI, 'completed_pages': pages, 'batches': batches, 'source_sha256': source_sha})


if __name__ == '__main__':
    run()
