"""Local lecture OCR pilot with separate provenance and no textbook page offsets."""
import argparse
import json
from pathlib import Path
import subprocess
from audit_ocr_pilot import content_strings
from normalize_pilot_blocks import convert
from process_full_book import POPPLER, write_json, valid_cache
from sync_sources import ROOT, fingerprint

NAMES={'1':'一','2':'二','3':'三','4':'四','5':'五','6':'六','7':'七','8':'八'}


def source_for(chapter):
    if chapter not in NAMES:raise ValueError('章节应为1–8')
    registry=json.loads((ROOT/'data/private/source_registry/manifest.json').read_text(encoding='utf-8'))
    name='_茆第'+NAMES[chapter]+'章强化课.pdf'
    source=next((r for r in registry['files'] if r['name']==name),None)
    if not source:raise ValueError('缺少指定章节的已登记讲义')
    if fingerprint(Path(source['path']))!=source['sha256']:raise ValueError('讲义已变化，请先更新来源登记')
    return source


def prepare(chapter,pages,dpi=160):
    source=source_for(chapter);pages=sorted(set(pages))
    if not pages or any(type(p) is not int or not 1<=p<=source['metadata']['pages'] for p in pages):raise ValueError('页码超出讲义范围')
    base=ROOT/'data/private/lecture-ocr'/('chapter'+chapter);(base/'pages').mkdir(parents=True,exist_ok=True)
    path=base/'manifest.json';old=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    if old and (old['source_sha256']!=source['sha256'] or old['dpi']!=dpi):raise ValueError('来源/渲染参数已变化，请保留现有审核并使用新的工作目录')
    rows={r['pdf_page']:r for r in old.get('pages',[])}
    for page in pages:
        target=base/'pages'/f'pdf-{page:03}.png'
        if target.exists() and page in rows and fingerprint(target)!=rows[page]['image_sha256']:raise ValueError('讲义页图已变化')
        if not target.exists():
            subprocess.run([str(POPPLER),'-f',str(page),'-l',str(page),'-r',str(dpi),'-singlefile','-png',source['path'],str(target.with_suffix(''))],
                           capture_output=True,check=True,timeout=120)
        rows[page]={'pdf_page':page,'page_idx':page-1,'image':target.relative_to(base).as_posix(),
                    'image_sha256':fingerprint(target),'purpose':'lecture_explanations','searchable':False,
                    'page_mapping_status':'lecture_pdf_page_only; textbook_alignment_pending'}
    manifest={'schema_version':1,'source_id':source['id'],'source_sha256':source['sha256'],'source_path':source['path'],
              'source_name':source['name'],'source_total_pages':source['metadata']['pages'],'chapter':chapter,
              'source_role':'lecture_exercise_explanations','dpi':dpi,'access':'private_local',
              'pages':[rows[p] for p in sorted(rows)],'page_count':len(rows),
              'boundary':'Lecture pages, not textbook pages. OCR and same-question alignment remain pending review.'}
    write_json(path,manifest);return manifest


def normalize(chapter):
    source=source_for(chapter)
    base=ROOT/'data/private/lecture-ocr'/('chapter'+chapter)
    manifest=json.loads((base/'manifest.json').read_text(encoding='utf-8'))
    if source['sha256']!=manifest['source_sha256']:raise ValueError('讲义来源已过期')
    cache=json.loads((base/'ocr-cache.json').read_text(encoding='utf-8'))
    blocks=[];processed=[]
    for row in manifest['pages']:
        if not valid_cache(base,row,cache):continue
        output=base/'mineru-basic'/f"pdf-{row['pdf_page']:03}.json"
        records=convert(json.loads(output.read_text(encoding='utf-8')),manifest,row,fingerprint(output))
        for block in records:
            block.update(channel='lecture_explanation',chapter=chapter,text=' '.join(content_strings(block['raw_block'])).strip(),
                         lecture_pdf_page=row['pdf_page'],textbook_alignment_status='pending',approved_for_tutoring=False)
        blocks.extend(records);processed.append(row['pdf_page'])
    target=base/'normalized-blocks.jsonl';temporary=target.with_suffix('.jsonl.tmp')
    temporary.write_text(''.join(json.dumps(b,ensure_ascii=False)+'\n' for b in blocks),encoding='utf-8')
    temporary.replace(target)
    report={'source_sha256':manifest['source_sha256'],'processed_pages':processed,'blocks':len(blocks),'searchable':False,
            'approved_for_tutoring':False,'boundary':'Original OCR retained; no automatic answer approval or textbook page mapping.'}
    report['normalized_sha256']=fingerprint(target)
    write_json(base/'normalization-report.json',report);return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--chapter',default='6');parser.add_argument('--pages',default='1,20,40,60,77')
    parser.add_argument('--normalize',action='store_true');args=parser.parse_args()
    result=normalize(args.chapter) if args.normalize else prepare(args.chapter,[int(p) for p in args.pages.split(',')])
    print(json.dumps({k:v for k,v in result.items() if k!='pages'},ensure_ascii=False,indent=2))
