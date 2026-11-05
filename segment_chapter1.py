"""Segment full-chapter OCR into unreviewed exercise candidates with cross-page provenance."""
import json
import re
from sync_sources import ROOT,fingerprint
from normalize_pilot_blocks import convert
from audit_ocr_pilot import content_strings

BASE=ROOT/'data/private/chapter1'
EXPECTED={'1.1':11,'1.2':30,'1.3':23,'1.4':33,'1.5':25}


def segment():
    manifest=json.loads((BASE/'manifest.json').read_text(encoding='utf-8'))
    normalized=[];questions=[];section=None;active=None
    for row in manifest['pages']:
        page=row['pdf_page'];path=BASE/'mineru-basic'/f'pdf-{page:03}.json'
        if not path.exists():continue
        data=json.loads(path.read_text(encoding='utf-8'))
        records=convert(data,manifest,row,fingerprint(path));normalized.extend(records)
        if page>=469:continue # Answers remain a separate evidence channel, not question-search content.
        for block in records:
            kind=block['type'] or ''
            if 'header' in kind or 'footer' in kind or kind=='page_number':continue
            text=' '.join(content_strings(block['raw_block'])).strip()
            heading=re.search(r'习\s*题\s*(1\.[1-5])',text)
            if heading:
                section=heading.group(1);active=None;continue
            if kind=='paragraph_title' and re.match(r'^[§\s]*1\.[1-5](?!\.\d)',text):section=None;active=None
            if not section:continue
            number=re.match(r'^(\d{1,2})\s*[.．、]\s*(?!\d)',text)
            if number and 1<=int(number.group(1))<=EXPECTED[section]:
                n=int(number.group(1));id=f'mao3-{section}-{n}'
                active={'id':id,'section':section,'number':n,'pages':[],'block_ids':[],'text_parts':[],
                        'review_status':'raw_ocr_pending_review','searchable':False}
                questions.append(active)
            if active:
                if page not in active['pages']:active['pages'].append(page)
                active['block_ids'].append(block['id']);active['text_parts'].append(text)
    for q in questions:q['text']='\n'.join(q.pop('text_parts'))
    found={s:{q['number'] for q in questions if q['section']==s} for s in EXPECTED}
    missing={s:sorted(set(range(1,maxn+1))-found[s]) for s,maxn in EXPECTED.items()}
    ids=[q['id'] for q in questions];duplicate_ids=sorted({id for id in ids if ids.count(id)>1})
    (BASE/'normalized-blocks.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in normalized),encoding='utf-8')
    (BASE/'exercise-candidates.jsonl').write_text(''.join(json.dumps(q,ensure_ascii=False)+'\n' for q in questions),encoding='utf-8')
    result={'pdf_pages_processed':len({x['pdf_page'] for x in normalized}),'normalized_blocks':len(normalized),
            'exercise_candidate_records':len(questions),'unique_exercise_ids':len(set(ids)),
            'expected_numbers_from_book_boundaries':EXPECTED,'missing_numbers':missing,'duplicate_ids':duplicate_ids,
            'cross_page_candidates':[q['id'] for q in questions if len(q['pages'])>1],
            'answers_separate':True,'searchable':False,'boundary':'Candidate boundaries and math remain unreviewed, even when numbering is complete.'}
    (BASE/'segmentation-report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2));return result


if __name__=='__main__':segment()
