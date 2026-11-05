"""Incremental private PDF registry; registration does not imply OCR or indexing."""
import datetime as dt
import argparse
import hashlib
import json
import logging
import re
import shutil
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parent


def bundled_tool(*parts):
    return Path.home() / '.cache/codex-runtimes/codex-primary-runtime/dependencies' / Path(*parts)


def poppler_tool(name):
    installed = shutil.which(name)
    if installed:
        return Path(installed)
    cached = bundled_tool('native', 'poppler', 'Library', 'bin', name + '.exe')
    return cached if cached.is_file() else Path(name)


def fingerprint(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def inspect_pdf(path):
    # Poppler reads the page tree without processing the unreliable OCR layer.
    executable=poppler_tool('pdfinfo')
    if executable.is_file():
        p=subprocess.run([str(executable),str(path)],capture_output=True,timeout=60)
        text=p.stdout.decode('utf-8',errors='replace')
        match=re.search(r'^Pages:\s*(\d+)',text,re.MULTILINE)
        if p.returncode==0 and match:
            return {'pages':int(match.group(1)),'inspection_tool':'Poppler pdfinfo',
                    'structure_warning_present':bool(p.stderr.strip())}
    from pypdf import PdfReader
    logging.getLogger('pypdf').setLevel(logging.ERROR)
    reader=PdfReader(path)
    return {'pages':len(reader.pages),'inspection_tool':'pypdf fallback','structure_warning_present':None}


def sync(config_path=None):
    config_file=Path(config_path) if config_path else ROOT/'source_config.json'
    if not config_file.is_absolute():config_file=ROOT/config_file
    config=json.loads(config_file.read_text(encoding='utf-8'))
    directory=Path(config['primary_source_directory'])
    if not directory.is_dir():raise FileNotFoundError(directory)
    output=(ROOT/config['generated_output_directory']).resolve()
    if not output.is_relative_to(ROOT.resolve()):raise ValueError('Output directory must stay inside project')
    output.mkdir(parents=True,exist_ok=True);manifest_path=output/'manifest.json'
    previous=json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else {'files':[]}
    by_path={x['path']:x for x in previous['files']}
    changed=[];added=[];unchanged=[];records=[];seen=set();unsupported=[]
    candidates=directory.rglob('*') if config['recursive'] else directory.glob('*')
    for path in sorted(candidates):
        if not path.is_file() or path.name.startswith('~$'):continue
        if path.suffix.lower() not in config['include_extensions']:
            unsupported.append(str(path.relative_to(directory)));continue
        real=path.resolve()
        if not real.is_relative_to(directory.resolve()):continue
        key=str(real);seen.add(key);digest=fingerprint(real);old=by_path.get(key)
        if old and old['sha256']==digest:
            records.append(old);unchanged.append(path.name);continue
        meta=inspect_pdf(real)
        record={'id':'src-'+digest[:16],'path':key,'name':path.name,'sha256':digest,'bytes':path.stat().st_size,
                'role':config.get('file_roles',{}).get(path.relative_to(directory).as_posix(),config.get('new_source_role','unclassified_pending_review')),
                'edition':config.get('file_editions',{}).get(path.relative_to(directory).as_posix()),'access':'private_local',
                'processing_status':'registered_pending_ocr_and_review','searchable':False,
                'ocr_quality':'unverified_do_not_trust_existing_text_layer','metadata':meta}
        if old:
            record['previous_sha256']=old['sha256'];changed.append(path.name)
        else:added.append(path.name)
        records.append(record)
    missing=[x['name'] for x in previous['files'] if x['path'] not in seen]
    result={'schema_version':1,'source_directory':str(directory),'role':config['source_role'],
            'updated_at':dt.datetime.now(dt.timezone.utc).isoformat(),'files':records,
            'file_count':len(records),'total_pages':sum(x['metadata']['pages'] for x in records),
            'delta':{'added':added,'content_changed':changed,'unchanged':unchanged,'no_longer_present':missing},
            'unsupported_files_pending_adapter':unsupported,
            'boundary':'File registry only; page count does not imply question segmentation, verified answers or searchable index.'}
    if previous.get('files') and (added or changed or missing):
        prior_bytes=manifest_path.read_bytes();archive=output/('manifest-history-'+hashlib.sha256(prior_bytes).hexdigest()[:16]+'.json')
        if not archive.exists():archive.write_bytes(prior_bytes)
    manifest_path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in {'files','updated_at'}},ensure_ascii=False,indent=2))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',help='Separate source config, relative to the project or absolute')
    sync(parser.parse_args().config)
