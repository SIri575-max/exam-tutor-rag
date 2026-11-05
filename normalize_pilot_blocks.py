"""Convert inspected MinerU 4/docvortex v2 output to source-linked quarantined blocks."""
import hashlib
import json
from pathlib import Path
from sync_sources import ROOT, fingerprint

BASE = ROOT / 'data/private/ocr-pilot'


def convert(data, source, row, output_sha):
    if data.get('schema') != 'docvortex.middle' or data.get('schema_version') != '2.0':
        raise ValueError('Unsupported OCR schema; inspect it before adding an adapter')
    # Each input is a single image. Its internal page_idx=0 is not the textbook PDF page.
    if len(data.get('pages', [])) != 1 or data['pages'][0].get('page_idx') != 0:
        raise ValueError('Expected one image page at internal index zero')
    records=[]
    for offset, block in enumerate(data['pages'][0].get('blocks', [])):
        identity=f"{source['source_sha256']}:{row['pdf_page']}:{output_sha}:{offset}"
        outside=source.get('chapter1_boundary',{}).get('next_chapter_pdf_page')==row['pdf_page']
        channel='reference_answer' if row['purpose']=='reference_answer' else ('boundary_only' if outside else 'textbook_body')
        records.append({'id':'block-'+hashlib.sha256(identity.encode()).hexdigest()[:24],
                        'source_id':source['source_id'],'source_sha256':source['source_sha256'],
                        'pdf_page':row['pdf_page'],'page_idx':row['pdf_page']-1,
                        'printed_page':row.get('printed_page_verified'),
                        'block_index':block.get('index',offset),'type':block.get('type'),
                        'bbox_normalized':block.get('bbox'),'bbox_coordinate_space':'normalized_rendered_image',
                        'segments':block.get('content',[]),
                        'raw_block':block,'parser_output_sha256':output_sha,
                        'channel':channel,'page_image':row['image'],
                        'review_status':'ocr_unreviewed','searchable':False})
    return records


def normalize():
    manifest=json.loads((BASE/'manifest.json').read_text(encoding='utf-8'))
    records=[];processed=[]
    for row in manifest['pages']:
        path=BASE/'mineru-basic'/f"pdf-{row['pdf_page']:03}.json"
        if not path.exists():continue
        records.extend(convert(json.loads(path.read_text(encoding='utf-8')),manifest,row,fingerprint(path)))
        processed.append(row['pdf_page'])
    (BASE/'normalized-blocks.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records),encoding='utf-8')
    summary={'processed_pdf_pages':processed,'block_count':len(records),'review_status':'ocr_unreviewed','searchable':False,
             'boundary':'No automatic question segmentation, answer approval or retrieval release.'}
    (BASE/'normalized-manifest.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))
    return summary


if __name__=='__main__':normalize()
