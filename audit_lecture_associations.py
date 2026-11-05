"""Mechanical chapter-wide consistency audit; not a semantic accuracy benchmark."""
import json
from pathlib import Path
from exercise_vectors import record, snapshot, status
from lecture_library import alignment, segment_index, manifest
from process_full_book import write_json
from sync_sources import fingerprint


def run():
    base,m=manifest('6');index=segment_index('6')
    if not index:raise ValueError('请先构建当前版本的题目分段')
    blocks={b['id']:b for b in (json.loads(line) for line in (base/'normalized-blocks.jsonl').read_text(encoding='utf-8').splitlines())}
    pages={r['pdf_page']:r for r in m['pages']};pairs=[];errors=[]
    for seg in index['segments']:
        identifier=seg['suggested_book_record_id']
        if not identifier:errors.append({'segment':seg['id'],'error':'no_primary_proposal'});continue
        book=record(identifier)
        if int(identifier.rsplit('-',1)[-1])!=seg['printed_number_candidate']:errors.append({'segment':seg['id'],'error':'number_mismatch'})
        if book['chapter']!='6':errors.append({'segment':seg['id'],'error':'chapter_mismatch'})
        if seg['generation_evidence_allowed'] or seg['answer_correctness_approved']:errors.append({'segment':seg['id'],'error':'unexpected_approval'})
        parts=[]
        for span in seg['query_source_spans']:
            block=blocks.get(span['block_id'])
            if block is None or not 0<=span['text_start']<=span['text_end']<=len(block['text']):
                errors.append({'segment':seg['id'],'error':'invalid_source_span'});continue
            parts.append(block['text'][span['text_start']:span['text_end']].strip())
        if '\n'.join(parts)[:2200]!=seg['query_text']:errors.append({'segment':seg['id'],'error':'query_not_reconstructed_from_source'})
        if any(b not in blocks for b in seg['block_ids']):errors.append({'segment':seg['id'],'error':'unknown_block'})
        if any(b-a!=1 for a,b in zip(seg['pages'],seg['pages'][1:])):errors.append({'segment':seg['id'],'error':'non_contiguous_pages'})
        pairs.append({'segment_id':seg['id'],'record_id':identifier,'lecture_pages':seg['pages'],
                      'method':seg['matching_method'],'status':'pending_semantic_review'})
    for page,row in pages.items():
        if fingerprint(base/row['image'])!=row['image_sha256']:errors.append({'page':page,'error':'image_changed'})
    manual=alignment('6')
    info=status();all_books={r['id'] for r in snapshot()[1].values() if r['chapter']=='6' and r['kind']=='exercise'}
    mapped=[p['record_id'] for p in pairs]
    report={'date':'2026-10-27','lecture_source_sha256':m['source_sha256'],'collection_sha256':info['collection_sha256'],
            'segments':len(pairs),'unique_book_records':len(set(mapped)),'duplicate_primary_records':len(mapped)-len(set(mapped)),
            'book_exercises_without_proposal':sorted(all_books-set(mapped)),
            'manual_source_comparison_candidates':len(manual),'errors':errors,'mechanical_checks_passed':not errors,
            'pairs':pairs,'boundary':'Checks page/hash/number/character-span consistency; no independent labels, semantic match accuracy or answer correctness approval.'}
    write_json(base/'association-mechanical-audit-2026-10-27.json',report)
    print(json.dumps({k:v for k,v in report.items() if k!='pairs'},ensure_ascii=False,indent=2));return report


if __name__=='__main__':
    result=run();raise SystemExit(0 if result['mechanical_checks_passed'] else 1)
