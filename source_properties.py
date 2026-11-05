"""Narrow property lookup in original source blocks, separate from question vectors."""
from functools import lru_cache
import hashlib
import json
import re
from process_full_book import BASE


@lru_cache(maxsize=2)
def source_blocks(stamp):
    with (BASE/'normalized-blocks.jsonl').open(encoding='utf-8') as stream:
        return {b['id']:b for b in (json.loads(line) for line in stream if line.strip())}


def requested(query):
    return bool(re.search(r'最大似然|(?<![A-Za-z])MLE(?![A-Za-z])',query,re.I) and re.search(r'不变性|不变性质|(?<![A-Za-z])invariance(?![A-Za-z])',query,re.I))


def lookup(query,records):
    if not requested(query):
        return []
    path=BASE/'normalized-blocks.jsonl';blocks=source_blocks(path.stat().st_mtime_ns)
    result=[];seen=set()
    for r in records.values():
        for identifier in r.get('block_ids',[]):
            block=blocks.get(identifier,{})
            if identifier in seen or '最大似然估计的不变性' not in block.get('text',''):continue
            seen.add(identifier)
            result.append({'id':'source-property-'+identifier,'record_id':r['id'],'label':'最大似然估计的不变性',
                           'text':block['text'],'pages':[block['pdf_page']],'block_id':identifier,
                           'source_sha256':block['source_sha256'],
                           'text_sha256':hashlib.sha256(block['text'].encode()).hexdigest(),
                           'review_status':'source_OCR_property_mention_pending_review',
                           'boundary':'Original source paragraph, not an approved solution to the current problem.'})
            if len(result)==3:return result
    return result
