"""Build a source-linked OCR diagnostic; string hits are not mathematical validation."""
import csv
from collections import Counter
import json
import re
from pathlib import Path
from sync_sources import ROOT

BASE = ROOT / 'data/private/ocr-pilot'


def normalize_latex(text):
    # Preserve bars, inequality directions, indices, signs and all brace scope.
    text = text.replace('\\left', '').replace('\\right', '')
    for old, new in [('\\mid', '|'), ('\\leq', '\\le'), ('\\geq', '\\ge'),
                     ('\\dfrac', '\\frac'), ('\\tfrac', '\\frac')]:
        text = text.replace(old, new)
    return re.sub(r'\s+', '', text)


def content_strings(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {'content', 'text', 'latex'} and isinstance(child, str):
                yield child
            elif isinstance(child, (dict, list)):
                yield from content_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from content_strings(child)


def audit():
    manifest = json.loads((BASE / 'manifest.json').read_text(encoding='utf-8'))
    references = [json.loads(x) for x in (BASE / 'formula-reference.jsonl').read_text(encoding='utf-8').splitlines() if x.strip()]
    texts = {};page_records=[]
    for row in manifest['pages']:
        page=row['pdf_page']
        paths=sorted((BASE/'mineru-basic').rglob(f'pdf-{page:03}.json'))
        data=json.loads(paths[0].read_text(encoding='utf-8')) if paths else None
        texts[page]='\n'.join(content_strings(data)) if data is not None else ''
        (BASE/'extracted-text').mkdir(exist_ok=True)
        if paths:(BASE/'extracted-text'/f'pdf-{page:03}.txt').write_text(texts[page],encoding='utf-8')
        page_records.append({'pdf_page':page,'output_present':bool(paths),'extracted_text_characters':len(texts[page]),
                             'status':'unreviewed' if paths else 'not_processed','searchable':False})
    comparisons=[]
    for ref in references:
        hit=bool(texts[ref['pdf_page']]) and normalize_latex(ref['expected_latex']) in normalize_latex(texts[ref['pdf_page']])
        comparisons.append({**ref,'diagnostic':'literal_formula_candidate_hit' if hit else 'needs_visual_comparison',
                            'diagnostic_is_math_accuracy':False})
    with (BASE/'ocr-quality-review.csv').open(encoding='utf-8-sig',newline='') as stream: checks=list(csv.DictReader(stream))
    pending=sum(row['result']!='pass' or not row['reviewer'].strip() for row in checks)
    assistant_counts=dict(Counter(row.get('assistant_result','not_checked') for row in checks))
    report={'source_sha256':manifest['source_sha256'],'engine':'MinerU 4.0.12 / basic / local ONNX',
            'pages_requested':len(page_records),'pages_with_output':sum(x['output_present'] for x in page_records),
            'pages':page_records,'formula_diagnostics':comparisons,'review_items':len(checks),'pending_review_items':pending,
            'assistant_initial_review':assistant_counts,
            'quality_gate':'requires_math_correction' if assistant_counts.get('correction_required') else ('pending_review' if pending else 'review_sheet_passed_content_release_still_separate'),
            'searchable':False,'boundary':'Formula substring checks are navigation aids, not OCR/math accuracy. No automatic corpus release.'}
    (BASE/'quality-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in {'pages','formula_diagnostics','source_sha256'}},ensure_ascii=False,indent=2))
    return report


if __name__=='__main__':audit()
