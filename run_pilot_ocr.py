"""Run pinned MinerU locally on private pilot images; no remote parsing service."""
import argparse
import datetime as dt
import json
import os
import subprocess
import time
from pathlib import Path
from sync_sources import ROOT, fingerprint


def run(pages=None, workspace='ocr-pilot', resume=False):
    base = (ROOT / 'data/private' / workspace).resolve()
    if not base.is_relative_to((ROOT/'data/private').resolve()):raise ValueError('Invalid private workspace')
    manifest = json.loads((base / 'manifest.json').read_text(encoding='utf-8'))
    selected = [row for row in manifest['pages'] if pages is None or row['pdf_page'] in pages]
    if not selected or (pages and set(pages) - {row['pdf_page'] for row in selected}):
        raise ValueError('Select pages already present in the pilot manifest')
    executable = ROOT / '.venv-ocr/Scripts/mineru-kit.exe'
    if not executable.exists():
        raise FileNotFoundError('Install requirements-ocr.txt in .venv-ocr first')
    output = base / 'mineru-basic'
    output.mkdir(exist_ok=True)
    cache_path=base/'ocr-cache.json'
    cache=json.loads(cache_path.read_text(encoding='utf-8')) if cache_path.exists() else {}
    skipped=[]
    if resume:
        remaining=[]
        for row in selected:
            name=f"pdf-{row['pdf_page']:03}.json";entry=cache.get(name);target=output/name
            if entry and entry.get('package_pin')=='4.0.12' and target.exists() and entry.get('input_image_sha256')==row['image_sha256'] and entry.get('output_sha256')==fingerprint(target):skipped.append(row['pdf_page'])
            else:remaining.append(row)
        selected=remaining
    if not selected:
        print(json.dumps({'status':'cache_current','skipped_pdf_pages':skipped}))
        return {'returncode':0,'status':'cache_current'}
    images = [base / row['image'] for row in selected]
    for row, image in zip(selected, images):
        if fingerprint(image) != row['image_sha256']:
            raise ValueError(f'Pilot image changed: {image.name}')
    env = os.environ.copy()
    env.update({'MINERU_HOME': str(ROOT / 'data/private/ocr-pilot/mineru-home'),
                'HF_HOME': str(base / 'model-cache/huggingface'),
                'MODELSCOPE_CACHE': str(base / 'model-cache/modelscope'),
                'HF_HUB_DISABLE_XET': '1',
                'MINERU_INTRA_OP_NUM_THREADS': '2', 'MINERU_INTER_OP_NUM_THREADS': '1',
                'MINERU_MODEL_SMALL_BACKEND': 'onnx'})
    # Use local stateless parsing, no --remote or --remote-url; basic does not use a VLM.
    command = [str(executable), 'parse', *map(str, images), '-o', str(output),
               '--format', 'middle_json', '--tier', 'basic', '--ocr-mode', 'ocr',
               '--disable-image-analysis']
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    tag = dt.datetime.now().strftime('%Y%m%d-%H%M%S')
    log = base / f'mineru-{tag}.log'
    record_path = base / f'run-{tag}.json'
    record = {'started_at': started, 'engine': 'MinerU', 'package_pin': '4.0.12',
              'tier': 'basic', 'small_backend': 'onnx', 'requested_pdf_pages': [r['pdf_page'] for r in selected],
              'source_sha256': manifest['source_sha256'], 'log': log.name,
              'remote_parsing': False, 'status': 'running', 'searchable': False,'skipped_cached_pages':skipped}
    record_path.write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    start = time.monotonic()
    with log.open('wb') as stream:
        try:
            result = subprocess.run(command, env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=3600)
            record.update(returncode=result.returncode, status='completed_unreviewed' if result.returncode == 0 else 'failed')
        except subprocess.TimeoutExpired:
            record.update(status='timed_out', returncode=None)
    record['elapsed_seconds'] = round(time.monotonic() - start, 2)
    for row in selected:
        name=f"pdf-{row['pdf_page']:03}.json";target=output/name
        if target.exists():
            try:json.loads(target.read_text(encoding='utf-8'))
            except json.JSONDecodeError:continue
            cache[name]={'input_image_sha256':row['image_sha256'],'output_sha256':fingerprint(target),'package_pin':'4.0.12'}
    cache_path.write_text(json.dumps(cache,indent=2)+'\n',encoding='utf-8')
    record_path.write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(record, ensure_ascii=False, indent=2), flush=True)
    return record


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pages', help='Optional comma-separated 1-based PDF pages from the pilot')
    parser.add_argument('--workspace',default='ocr-pilot')
    parser.add_argument('--resume',action='store_true')
    args = parser.parse_args()
    result = run([int(x) for x in args.pages.split(',')] if args.pages else None,args.workspace,args.resume)
    raise SystemExit(0 if result.get('returncode') == 0 else 1)
