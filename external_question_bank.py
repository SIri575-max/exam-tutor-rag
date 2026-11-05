"""Private, resumable external evaluation OCR. Never inserts test data into retrieval."""
import argparse
import concurrent.futures
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import re
import subprocess
import time

from process_full_book import ROOT, POPPLER, PIN, parse_batch, valid_cache, write_json
from sync_sources import fingerprint, poppler_tool
from photo_ocr import _text

BASE = ROOT / 'data/private/660b-evaluation'
DEFAULT_SOURCE = Path.home() / 'Desktop/专业课辅导/660B.pdf'


def prepare(source=DEFAULT_SOURCE):
    source = Path(source).resolve()
    digest = fingerprint(source)
    protocol=json.loads((ROOT/'evaluation/external_660b_protocol.json').read_text(encoding='utf-8'))
    if digest != protocol['source_sha256']:
        raise ValueError('This evaluation protocol belongs to another source fingerprint')
    path = BASE / 'manifest.json'
    old = json.loads(path.read_text(encoding='utf-8')) if path.exists() else None
    if old and (old['source_sha256'] != digest or old['dpi'] != 160):
        raise ValueError('Source changed; preserve old evaluation and use a new directory')
    for name in ('pages', 'mineru-basic', 'logs'):
        (BASE / name).mkdir(parents=True, exist_ok=True)
    info = subprocess.run([str(poppler_tool('pdfinfo')), str(source)],
                          capture_output=True, check=True).stdout.decode('utf-8', errors='replace')
    count = int(re.search(r'^Pages:\s+(\d+)', info, re.M).group(1))
    rows = {r['pdf_page']: r for r in (old or {}).get('pages', [])}
    for page in range(1, count + 1):
        target = BASE / 'pages' / f'pdf-{page:03}.png'
        if page in rows and target.exists() and fingerprint(target) != rows[page]['image_sha256']:
            raise ValueError('Page image changed')
        if not target.exists():
            subprocess.run([str(POPPLER), '-f', str(page), '-l', str(page), '-r', '160',
                            '-singlefile', '-png', str(source), str(target.with_suffix(''))],
                           capture_output=True, check=True, timeout=120)
        rows[page] = {'pdf_page': page, 'image': target.relative_to(BASE).as_posix(),
                      'image_sha256': fingerprint(target), 'purpose': 'evaluation_only'}
        if page % 25 == 0: print('render', page, count, flush=True)
    data = {'source_id': 'external-660b-2026', 'source_path': str(source), 'source_sha256': digest,
            'page_count': count, 'dpi': 160, 'pages': list(rows.values()), 'access': 'private_local',
            'searchable': False, 'answer_channel': 'sealed_evaluation_labels_only',
            'boundary': 'External source, not guaranteed novel: deduplicate against textbook before splitting.'}
    write_json(path, data)
    return data


def page_blocks(parsed):
    if parsed.get('schema') != 'docvortex.middle' or str(parsed.get('schema_version')) != '2.0':
        raise ValueError('Unsupported OCR schema')
    if len(parsed.get('pages', [])) != 1:
        raise ValueError('Expected one rendered PDF page')
    return [{'type': b.get('type', 'text'), 'bbox': b.get('bbox'),
             'text': _text(b.get('content'), b.get('type', '')).strip()}
            for b in parsed['pages'][0].get('blocks', [])]


def normalize(manifest, cache):
    rows = []
    for page in manifest['pages']:
        if not valid_cache(BASE, page, cache): continue
        path = BASE / 'mineru-basic' / f"pdf-{page['pdf_page']:03}.json"
        blocks = page_blocks(json.loads(path.read_text(encoding='utf-8')))
        rows.append({'source_sha256': manifest['source_sha256'], 'pdf_page': page['pdf_page'],
                     'image_sha256': page['image_sha256'], 'ocr_sha256': fingerprint(path),
                     'blocks': blocks, 'text': '\n\n'.join(b['text'] for b in blocks if b['text']),
                     'review_status': 'ocr_unreviewed', 'searchable': False})
    (BASE / 'pages.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False)+'\n' for r in rows), encoding='utf-8')
    return rows


def run(source=DEFAULT_SOURCE, workers=2, batch_size=4, selected=None):
    if workers not in (1, 2) or not 1 <= batch_size <= 8: raise ValueError('Invalid worker/batch limit')
    manifest = prepare(source)
    cache_path = BASE / 'ocr-cache.json'
    cache = json.loads(cache_path.read_text(encoding='utf-8')) if cache_path.exists() else {}
    rows = [r for r in manifest['pages'] if selected is None or r['pdf_page'] in selected]
    started = time.monotonic()
    progress = {'status': 'running', 'total_pages': manifest['page_count'], 'requested_pages': len(rows),
                'remote_parsing': False, 'source_sha256': manifest['source_sha256'], 'searchable': False}
    def checkpoint():
        complete = normalize(manifest, cache)
        progress.update(completed_pages=len(complete), elapsed_seconds=round(time.monotonic()-started, 2),
                        updated_at=datetime.now(timezone(timedelta(hours=8))).isoformat())
        write_json(cache_path, cache); write_json(BASE/'progress.json', progress)
        print(json.dumps(progress), flush=True)
    checkpoint()
    for attempt in (1, 2):
        pending = [r for r in rows if not valid_cache(BASE, r, cache)]
        size = batch_size if attempt == 1 else 1
        batches = [pending[n:n+size] for n in range(0, len(pending), size)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(parse_batch, b, attempt, BASE): b for b in batches}
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                for row in futures[future]:
                    name = f"pdf-{row['pdf_page']:03}.json"; path = BASE/'mineru-basic'/name
                    if path.exists():
                        entry = {'input_image_sha256': row['image_sha256'], 'output_sha256': fingerprint(path), 'package_pin': PIN}
                        if valid_cache(BASE, row, {name: entry}): cache[name] = entry
                checkpoint()
    progress['status'] = 'complete_unreviewed' if all(valid_cache(BASE, r, cache) for r in rows) else 'incomplete_with_errors'
    checkpoint()
    return progress


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=DEFAULT_SOURCE)
    parser.add_argument('--workers', type=int, default=2)
    parser.add_argument('--batch-size', type=int, default=4)
    parser.add_argument('--pages', help='Comma-separated pilot PDF pages; omitted means all pages')
    args = parser.parse_args()
    selected = {int(v) for v in args.pages.split(',')} if args.pages else None
    result = run(args.source, args.workers, args.batch_size, selected)
    raise SystemExit(result['status'] != 'complete_unreviewed')
