"""Read-only index/TeX-boundary inspection for explaining the implemented RAG."""
from collections import Counter
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import re
import argparse
import exercise_vectors
from formula_chunking import protected_spans
from exercise_vectors import DB, connect, snapshot, status, CHUNK_CHARS, OVERLAP, MAX_TOKENS
from question_knowledge import current

ROOT=Path(__file__).resolve().parent


def tex_spans(text):
    spans=[(m.start(),m.end(),'command') for m in re.finditer(r'\\[A-Za-z]+',text)]
    stack=[]
    for i,ch in enumerate(text):
        if i and text[i-1]=='\\':continue
        if ch=='{':stack.append(i)
        elif ch=='}' and stack:spans.append((stack.pop(),i+1,'balanced_braces'))
    return spans


def run(index=None,output=None):
    global DB
    if index:
        DB=Path(index).resolve();exercise_vectors.DB=DB;exercise_vectors.OUT=DB.parent
    info=status()
    if not info['ready']:raise ValueError('Inspect a ready index only')
    records=snapshot()[1];by_record={identifier:[] for identifier in records}
    with connect() as conn:
        for identifier,parent,start,end,tokens,text in conn.execute('SELECT id,record_id,start,end,token_count,text FROM chunks ORDER BY record_id,start'):
            by_record[parent].append({'id':identifier,'start':start,'end':end,'token_count':tokens,'text':text})
    cuts=[];risks=[];protected_risks=[];body_lengths=[];token_counts=[];overlaps=[]
    for identifier,rows in by_record.items():
        r=records[identifier];text=r['search_text'];spans=tex_spans(text);covered=set()
        prefix=(r['section_title']+' | '+r['label']+'\n')[:100]
        for c in rows:
            assert 0<=c['start']<c['end']<=len(text)
            assert c['text']==prefix+text[c['start']:c['end']]
            assert c['token_count']<=MAX_TOKENS
            covered.update(range(c['start'],c['end']));body_lengths.append(c['end']-c['start']);token_counts.append(c['token_count'])
        assert len(covered)==len(text),'Uncovered parent content: '+identifier
        overlaps.extend(a['end']-b['start'] for a,b in zip(rows,rows[1:]))
        positions=sorted({n for c in rows for n in [c['start'],c['end']] if 0<n<len(text)})
        for offset in positions:
            if any(a<offset<b for a,b in protected_spans(text)):
                protected_risks.append({'record_id':identifier,'offset':offset,'pages':r['pages']})
            row={'record_id':identifier,'offset':offset,'pages':r['pages'],
                 'inside_tex_structures':sorted({kind for a,b,kind in spans if a<offset<b})}
            cuts.append(row)
            if row['inside_tex_structures']:risks.append(row)
    choices=[r for r in records.values() if r['kind']=='exercise' and 1<len(by_record[r['id']])<=3
             and not any('图像' in f or '表格' in f for f in r.get('review_flags',[]))]
    sample=min(choices,key=lambda r:(len(r['search_text']),r['id']))
    selected={'record_id':sample['id'],'label':sample['label'],'pages':sample['pages'],
              'search_characters':len(sample['search_text']),'chunks':by_record[sample['id']]}
    graph=current()['report']
    report={'date':'2026-11-05','created_at':datetime.now(timezone(timedelta(hours=8))).isoformat(),
            'collection_sha256':info['collection_sha256'],'database_sha256':hashlib.sha256(DB.read_bytes()).hexdigest(),
            'records':len(records),'kinds':dict(Counter(r['kind'] for r in records.values())),
            'chunks':sum(len(r) for r in by_record.values()),'multi_chunk_records':sum(len(r)>1 for r in by_record.values()),
            'maximum_chunks_per_record':max(map(len,by_record.values())),
            'chunk_version':info.get('chunk_version'),
            'chunk_config':{'body_character_target':CHUNK_CHARS,'maximum_overlap_characters':OVERLAP,
                            'token_budget_including_prefix':MAX_TOKENS,'prefix_character_cap':100},
            'actual_ranges':{'body_characters':[min(body_lengths),max(body_lengths)],
                             'token_counts':[min(token_counts),max(token_counts)],
                             'overlap_characters':[min(overlaps),max(overlaps)]},
            'all_parent_text_covered':True,'internal_boundary_positions':len(cuts),
            'boundaries_inside_tex_structures':len(risks),'records_with_tex_boundary_risk':len({r['record_id'] for r in risks}),
            'risk_examples':risks[:10],'boundaries':info['boundaries'],'graph':graph,'example':selected,
            'protected_unit_boundary_risks':protected_risks,
            'chunk_boundary_warnings':info.get('chunk_boundary_warnings',[]),
            'generation_api_calls':0,'index_changed':False,
            'boundary':'TeX command/brace boundary risks only, not a mathematical or OCR error count. Parent recovery does not guarantee a complete or correct source stem.'}
    folder=Path(output) if output else ROOT/'data/private/architecture-20261105'
    folder.mkdir(parents=True,exist_ok=True)
    target=folder/'index-and-boundary-inspection.json';target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    assert hashlib.sha256(DB.read_bytes()).hexdigest()==report['database_sha256']
    print(json.dumps({k:report[k] for k in ['records','chunks','multi_chunk_records','maximum_chunks_per_record','actual_ranges','internal_boundary_positions','boundaries_inside_tex_structures','records_with_tex_boundary_risk']},ensure_ascii=False))
    print(json.dumps({'example':selected['record_id'],'pages':selected['pages'],
                      'chunks':[{k:c[k] for k in ['id','start','end','token_count']} for c in selected['chunks']],
                      'report':str(target)},ensure_ascii=False))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--index');parser.add_argument('--output')
    args=parser.parse_args();run(args.index,args.output)
