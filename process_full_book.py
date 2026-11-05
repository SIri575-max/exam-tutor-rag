"""Resume-safe, local full-book rendering and OCR. Originals are never modified."""
import argparse
import concurrent.futures
import datetime as dt
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from sync_sources import ROOT, fingerprint, poppler_tool

BASE = ROOT / 'data/private/full-book'
PIN = '4.0.12'
POPPLER = poppler_tool('pdftoppm')


def write_json(path, data):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def valid_cache(base, row, cache):
    name = f"pdf-{row['pdf_page']:03}.json"
    target = base / 'mineru-basic' / name
    entry = cache.get(name, {})
    if (not target.exists() or entry.get('package_pin') != PIN
            or entry.get('input_image_sha256') != row['image_sha256']
            or entry.get('output_sha256') != fingerprint(target)):
        return False
    try:
        data = json.loads(target.read_text(encoding='utf-8'))
        return (data.get('schema') == 'docvortex.middle' and data.get('schema_version') == '2.0'
                and len(data.get('pages', [])) == 1 and data['pages'][0].get('page_idx') == 0)
    except (ValueError, KeyError):
        return False


def link_or_copy(source, target):
    if target.exists():
        return
    try:
        os.link(source, target)
    except OSError:
        shutil.copy2(source, target)


def prepare(workers=2):
    registry = json.loads((ROOT / 'data/private/textbook_registry/manifest.json').read_text(encoding='utf-8'))
    source = next(x for x in registry['files'] if x['role'] == 'textbook')
    if fingerprint(Path(source['path'])) != source['sha256']:
        raise ValueError('Source changed; register it as a new edition first')
    BASE.mkdir(parents=True, exist_ok=True)
    for directory in ('pages', 'mineru-basic', 'logs'):
        (BASE / directory).mkdir(exist_ok=True)
    old = json.loads((BASE / 'manifest.json').read_text(encoding='utf-8')) if (BASE / 'manifest.json').exists() else {}
    if old and (old['source_sha256'] != source['sha256'] or old['dpi'] != 160):
        raise ValueError('Full-book source/render version changed')
    cache = json.loads((BASE / 'ocr-cache.json').read_text(encoding='utf-8')) if (BASE / 'ocr-cache.json').exists() else {}
    reusable = {r['pdf_page']: r for r in old.get('pages', [])}
    for directory in ('chapter1', 'ocr-pilot'):
        parent = ROOT / 'data/private' / directory
        manifest = json.loads((parent / 'manifest.json').read_text(encoding='utf-8'))
        if manifest['source_sha256'] != source['sha256'] or manifest['dpi'] != 160:
            continue
        other_cache = json.loads((parent / 'ocr-cache.json').read_text(encoding='utf-8')) if (parent / 'ocr-cache.json').exists() else {}
        for row in manifest['pages']:
            image = parent / row['image']
            if not image.exists() or fingerprint(image) != row['image_sha256']:
                continue
            link_or_copy(image, BASE / 'pages' / image.name)
            reusable.setdefault(row['pdf_page'], row)
            name = f"pdf-{row['pdf_page']:03}.json"
            candidate = parent / 'mineru-basic' / name
            if name not in other_cache and candidate.exists():
                parsed = json.loads(candidate.read_text(encoding='utf-8'))
                if parsed.get('metadata', {}).get('producer', {}).get('version') == PIN:
                    # Legacy pilot predates cache manifests; import its explicitly pinned local output.
                    other_cache[name] = {'input_image_sha256': row['image_sha256'],
                                         'output_sha256': fingerprint(candidate), 'package_pin': PIN}
            if valid_cache(parent, row, other_cache):
                name = f"pdf-{row['pdf_page']:03}.json"
                original_output = parent / 'mineru-basic' / name
                reused_output = BASE / 'mineru-basic' / name
                # OCR JSON may be regenerated later; keep historical chapter/pilot outputs independent.
                if reused_output.exists() and os.path.samefile(original_output, reused_output):
                    temporary = reused_output.with_suffix('.copy-tmp')
                    temporary.write_bytes(original_output.read_bytes())
                    temporary.replace(reused_output)
                elif not reused_output.exists():
                    shutil.copy2(original_output, reused_output)
                cache[name] = other_cache[name]
    manifest = {'schema_version': 1, 'source_id': source['id'], 'source_sha256': source['sha256'],
                'source_path': source['path'], 'dpi': 160, 'access': 'private_local',
                'page_count': source['metadata']['pages'], 'pages': [],
                'boundary': 'All-page OCR archive; mathematical content is not automatically reviewed or released to tutoring.'}
    def render(page):
        image = BASE / 'pages' / f'pdf-{page:03}.png'
        if not image.exists():
            subprocess.run([str(POPPLER), '-f', str(page), '-l', str(page), '-r', '160',
                            '-singlefile', '-png', source['path'], str(image.with_suffix(''))],
                           check=True, capture_output=True, timeout=120)
        previous = reusable.get(page, {})
        actual_sha = fingerprint(image)
        if previous.get('image_sha256') and actual_sha != previous['image_sha256']:
            raise ValueError(f'Cached source page {page} changed; preserve any annotations and rerender from the original before reuse')
        row = {'pdf_page': page, 'page_idx': page - 1, 'image': f'pages/pdf-{page:03}.png',
               'image_sha256': actual_sha, 'purpose': 'full_book',
               'printed_page_candidate': str(page - 22) if page >= 23 else None,
               'page_mapping_status': 'candidate_pending_review', 'searchable': False}
        if previous.get('image_sha256') == row['image_sha256']:
            for key in ('printed_page_verified', 'page_mapping_status'):
                if key in previous:
                    row[key] = previous[key]
        return row
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        for row in executor.map(render, range(1, manifest['page_count'] + 1)):
            manifest['pages'].append(row)
            if len(manifest['pages']) % 25 == 0:
                print(json.dumps({'stage': 'render', 'pages': len(manifest['pages']), 'total': manifest['page_count']}), flush=True)
    write_json(BASE / 'manifest.json', manifest)
    write_json(BASE / 'ocr-cache.json', cache)
    return manifest, cache


def parse_batch(rows, attempt, base=None):
    # Explicit workspace keeps lecture pages separate from textbook numbering.
    base = Path(base or BASE)
    tag = f"{rows[0]['pdf_page']:03}-{rows[-1]['pdf_page']:03}-{attempt}-{time.time_ns()}"
    log = base / 'logs' / f'{tag}.log'
    env = os.environ.copy()
    env.update({'MINERU_HOME': str(ROOT / 'data/private/ocr-pilot/mineru-home'),
                'HF_HOME': str(ROOT / 'data/private/ocr-pilot/model-cache/huggingface'),
                'MODELSCOPE_CACHE': str(ROOT / 'data/private/ocr-pilot/model-cache/modelscope'),
                'HF_HUB_DISABLE_XET': '1', 'MINERU_INTRA_OP_NUM_THREADS': '2',
                'MINERU_INTER_OP_NUM_THREADS': '1', 'MINERU_MODEL_SMALL_BACKEND': 'onnx'})
    for row in rows:
        if fingerprint(base / row['image']) != row['image_sha256']:
            raise ValueError('Input page image changed')
    command = [str(ROOT / '.venv-ocr/Scripts/mineru-kit.exe'), 'parse',
               *[str(base / row['image']) for row in rows], '-o', str(base / 'mineru-basic'),
               '--format', 'middle_json', '--tier', 'basic', '--ocr-mode', 'ocr', '--disable-image-analysis']
    start = time.monotonic()
    try:
        with log.open('wb') as stream:
            result = subprocess.run(command, env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=1800)
        code = result.returncode
    except subprocess.TimeoutExpired:
        code = 'timeout'
    return {'pages': [r['pdf_page'] for r in rows], 'returncode': code,
            'elapsed_seconds': round(time.monotonic() - start, 2), 'log': str(log.relative_to(base))}


def run(workers=2, batch_size=12):
    start = time.monotonic()
    manifest, cache = prepare(workers)
    results = []
    status = {'source_sha256': manifest['source_sha256'], 'started_at': dt.datetime.now().astimezone().isoformat(),
              'status': 'running', 'workers': workers, 'total_pages': manifest['page_count'],
              'review_status': 'raw_ocr_pending_review', 'remote_parsing': False}
    def checkpoint():
        complete = [r['pdf_page'] for r in manifest['pages'] if valid_cache(BASE, r, cache)]
        status.update(completed_pages=len(complete), completed_pdf_pages=complete,
                      remaining_pdf_pages=[r['pdf_page'] for r in manifest['pages'] if r['pdf_page'] not in complete],
                      elapsed_seconds=round(time.monotonic() - start, 2), batches=results,
                      updated_at=dt.datetime.now().astimezone().isoformat())
        write_json(BASE / 'ocr-cache.json', cache)
        write_json(BASE / 'progress.json', status)
        print(json.dumps({key: status[key] for key in ('status', 'completed_pages', 'total_pages', 'elapsed_seconds')}), flush=True)
    def collect(result):
        results.append(result)
        for page in result['pages']:
            row = manifest['pages'][page - 1]
            name = f'pdf-{page:03}.json'
            path = BASE / 'mineru-basic' / name
            if path.exists():
                entry = {'input_image_sha256': row['image_sha256'], 'output_sha256': fingerprint(path), 'package_pin': PIN}
                if valid_cache(BASE, row, {name: entry}):
                    cache[name] = entry
        checkpoint()
    checkpoint()
    remaining = [r for r in manifest['pages'] if not valid_cache(BASE, r, cache)]
    batches = [remaining[n:n + batch_size] for n in range(0, len(remaining), batch_size)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(parse_batch, batch, 1) for batch in batches]
        for future in concurrent.futures.as_completed(futures):
            collect(future.result())
    # A failed batch must not cause its later pages to disappear. Retry unresolved pages individually.
    for attempt in (2, 3):
        unresolved = [r for r in manifest['pages'] if not valid_cache(BASE, r, cache)]
        if not unresolved:
            break
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(parse_batch, [row], attempt) for row in unresolved]
            for future in concurrent.futures.as_completed(futures):
                collect(future.result())
    status['status'] = 'complete_unreviewed' if all(valid_cache(BASE, r, cache) for r in manifest['pages']) else 'incomplete_with_errors'
    checkpoint()
    return status


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workers', type=int, choices=(1, 2), default=2)
    parser.add_argument('--batch-size', type=int, default=12)
    args = parser.parse_args()
    result = run(args.workers, args.batch_size)
    raise SystemExit(0 if result['status'] == 'complete_unreviewed' else 1)
