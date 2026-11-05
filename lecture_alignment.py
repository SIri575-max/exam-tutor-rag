"""Conservative question openings, reading-order spans and lexical proposals.

Neither a question number nor proximity proves that a solution belongs to a
textbook exercise. Every span and match remains reviewable source metadata.
"""
import argparse
from collections import defaultdict
from difflib import SequenceMatcher
import hashlib
import json
import re
import unicodedata
from exercise_vectors import snapshot, status
from lecture_pipeline import source_for
from process_full_book import valid_cache, write_json
from retrieval import tokens
from sync_sources import ROOT, fingerprint


def opening_number(block):
    if block.get('type') in {'header','footer','page_number','image'}:return None
    text=unicodedata.normalize('NFKC',block.get('text','')).strip()
    match=re.match(r'^(\d{1,2})\s*[.、]\s*(.*)',text,re.S)
    if not match or len(re.findall(r'[\u4e00-\u9fff]',match[2]))<4:return None
    # Some stems start with numeric observations, e.g. "3.0.50,1.25,...".
    if match[2][:1].isdigit() and not re.match(r'\d+\.\d+\s*[,，]',match[2]):return None
    box=block.get('bbox_normalized')
    if box and (box[1]>.90 or box[0]<.12 or box[3]-box[1]>.10):return None
    return int(match[1])


def expand_merged_openings(block):
    """Derive source-linked text spans without changing the raw OCR block."""
    text=block.get('text','');box=block.get('bbox_normalized')
    if not box or box[0]<.12 or box[3]-box[1]>.10 or opening_number(block) is None:return [block]
    cuts=[0]+[m.start(1) for m in re.finditer(r'\s(\d{1,2})\s*[.．]\s*(?=设|证明|验证|从|某|假设|总体|已知|用)',text)]
    if len(cuts)==1:return [block]
    cuts.append(len(text));parts=[]
    for i,(start,end) in enumerate(zip(cuts,cuts[1:])):
        parts.append({**block,'id':block['id']+'::part'+str(i),'parent_block_id':block['id'],
                      'text_start':start,'text_end':end,'text':text[start:end].strip(),
                      'block_index':block['block_index']+i/100})
    return parts


def teaching_block(block):
    box=block.get('bbox_normalized') or [0,0,1,1]
    return block.get('type') not in {'header','footer','page_number'} and not (
        box[1]>.90 and re.search(r'公众号|扣群|微信群|每日更新',block.get('text','')))


def segment_blocks(blocks, processed_pages, anchors=()):
    by_page=defaultdict(list)
    for b in blocks:
        if teaching_block(b):by_page[b['pdf_page']].extend(expand_merged_openings(b))
    anchored={a['lecture_pdf_page']:a for a in anchors}
    segments=[];unassigned=[];current=None;previous_page=None
    for page in sorted(processed_pages):
        if previous_page is None or page!=previous_page+1:current=None
        page_blocks=sorted(by_page[page],key=lambda b:b['block_index'])
        anchor=anchored.get(page)
        anchor_start=min((b['block_index'] for b in page_blocks if b['id'] in anchor['stem_candidate_block_ids']),default=None) if anchor else None
        prefix=[b for b in page_blocks if anchor_start is not None and b['block_index']<anchor_start]
        if prefix and all(b.get('type')=='image' for b in prefix):anchor_start=prefix[0]['block_index']
        for block in page_blocks:
            number=opening_number(block)
            is_anchor=anchor_start is not None and block['block_index']==anchor_start
            if number is not None or is_anchor:
                current={'id':'lecture-segment-'+str(page)+'-'+str(block['block_index']),
                         'start_page':page,'start_block_id':block['id'],'printed_number_candidate':number,
                         'opening_method':'visual_anchor' if is_anchor else 'numbered_chinese_opening',
                         'visual_anchor_id':anchor['id'] if is_anchor else None,
                         'pages':[],'blocks':[],'review_status':'pending',
                         'answer_correctness_approved':False,'generation_evidence_allowed':False}
                if is_anchor:current['printed_number_candidate']=int(anchor['book_record_id'].rsplit('-',1)[-1])
                segments.append(current)
            if current is None:unassigned.append(block['id']);continue
            if page not in current['pages']:current['pages'].append(page)
            current['blocks'].append(block)
        previous_page=page
    # OCR windows may include annotations. They are queries, never clean answers.
    for seg in segments:
        opening=[b for b in seg['blocks'] if b['pdf_page']==seg['start_page']][:6]
        if seg['visual_anchor_id']:
            ids=set(anchored[seg['start_page']]['stem_candidate_block_ids'])
            opening=[b for b in seg['blocks'] if b['id'] in ids]
            spans={s['block_id']:s for s in anchored[seg['start_page']].get('stem_candidate_text_spans',[])}
            opening=[{**b,'parent_block_id':b['id'],'text_start':spans[b['id']]['text_start'],
                      'text_end':spans[b['id']]['text_end'],
                      'text':b['text'][spans[b['id']]['text_start']:spans[b['id']]['text_end']]}
                     if b['id'] in spans else b for b in opening]
        else:
            # Stop before large handwritten blocks, when there is enough printed text.
            selected=[]
            for b in opening:
                box=b.get('bbox_normalized') or [0,0,1,0]
                if selected and (box[3]-box[1]>.065 or box[0]<.12):break
                selected.append(b)
            opening=selected
        seg['query_block_ids']=[b['id'] for b in opening]
        seg['query_source_spans']=[{'block_id':b.get('parent_block_id',b['id']),
                                   'text_start':b.get('text_start',0),'text_end':b.get('text_end',len(b.get('text','')))} for b in opening]
        seg['query_text']='\n'.join(b.get('text','') for b in opening)[:2200]
        seg['block_ids']=list(dict.fromkeys(b.get('parent_block_id',b['id']) for b in seg.pop('blocks')))
        seg['continuation_pages']=[p for p in seg['pages'] if p!=seg['start_page']]
        seg['span_basis']='page context in reading order; neither continuation boundaries nor answer ownership is confirmed'
    counts=defaultdict(int)
    for seg in segments:
        for page in seg['pages']:counts[page]+=1
    for seg in segments:seg['shared_question_pages']=[p for p in seg['pages'] if counts[p]>1]
    return segments,unassigned


def compact(text):
    text=unicodedata.normalize('NFKC',text).lower()
    return re.sub(r'[\s{}\\$]','',text)


def rank_candidates(segment, books):
    query=segment['query_text'];number=segment['printed_number_candidate']
    qt=set(tokens(query));qnorm=compact(query);out=[]
    for book in books:
        same_number=int(book['id'].rsplit('-',1)[-1])==number
        # Number narrows the chapter, never identifies a section by itself.
        if number is not None and not same_number:continue
        text=book['question_text'];bt=set(tokens(text))
        dice=2*len(qt&bt)/max(1,len(qt)+len(bt))
        sequence=SequenceMatcher(None,qnorm,compact(text),autojunk=False).ratio()
        score=.55*dice+.45*sequence
        out.append({'book_record_id':book['id'],'book_label':book['label'],'book_pdf_pages':book['pages'],
                    'score':round(score,4),'token_dice':round(dice,4),'sequence_similarity':round(sequence,4),
                    'number_agrees':same_number,
                    'book_stem_sha256':hashlib.sha256(text.encode()).hexdigest()})
    out.sort(key=lambda r:(-r['score'],r['book_record_id']))
    return out[:3]


def choose_proposal(segment,candidates):
    if not candidates:return None
    margin=candidates[0]['score']-(candidates[1]['score'] if len(candidates)>1 else 0)
    enough_text=len(re.findall(r'[\u4e00-\u9fff]',segment['query_text']))>=10 or (candidates[0]['score']>=.85 and len(tokens(segment['query_text']))>=15)
    # Development thresholds, not calibrated probabilities or human approval.
    if enough_text and candidates[0]['number_agrees'] and candidates[0]['score']>=.50 and margin>=.12:
        return candidates[0]['book_record_id']
    return None


def build(chapter='6'):
    source=source_for(chapter);base=ROOT/'data/private/lecture-ocr'/('chapter'+chapter)
    manifest=json.loads((base/'manifest.json').read_text(encoding='utf-8'))
    report=json.loads((base/'normalization-report.json').read_text(encoding='utf-8'))
    path=base/'normalized-blocks.jsonl';normalized_sha=fingerprint(path)
    if manifest['source_sha256']!=source['sha256'] or report['source_sha256']!=source['sha256'] or report.get('normalized_sha256')!=normalized_sha:
        raise ValueError('讲义来源或标准化结果已变化，请重新标准化')
    cache=json.loads((base/'ocr-cache.json').read_text(encoding='utf-8'))
    for row in manifest['pages']:
        if row['pdf_page'] in report['processed_pages']:
            if fingerprint(base/row['image'])!=row['image_sha256'] or not valid_cache(base,row,cache):raise ValueError('讲义OCR缓存已变化')
    blocks=[json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
    if any(b['source_sha256']!=source['sha256'] or b['approved_for_tutoring'] for b in blocks):raise ValueError('非待审讲义块')
    manual_path=base/'alignment-candidates.json'
    manual=json.loads(manual_path.read_text(encoding='utf-8')) if manual_path.exists() else {'items':[]}
    extra_path=base/'extra-visual-alignments.json'
    if extra_path.exists():
        extra=json.loads(extra_path.read_text(encoding='utf-8'))
        if any(extra.get(k)!=manual.get(k) for k in ('lecture_source_sha256','book_source_sha256','collection_sha256')):
            raise ValueError('补充视觉关联已过期')
        manual['items'].extend(extra['items'])
    info=status()
    if not info['ready']:raise ValueError('教材索引已过期')
    if manual['items'] and (manual['lecture_source_sha256']!=source['sha256'] or manual['collection_sha256']!=info['collection_sha256']):
        raise ValueError('人工对照候选来源已过期')
    anchors=manual['items'];segments,unassigned=segment_blocks(blocks,report['processed_pages'],anchors)
    books=[r for r in snapshot()[1].values() if r['chapter']==chapter and r['kind']=='exercise']
    anchor_ids={a['id']:a for a in anchors}
    for seg in segments:
        seg['candidates']=rank_candidates(seg,books)
        seg['suggested_book_record_id']=choose_proposal(seg,seg['candidates'])
        if seg['visual_anchor_id']:seg['suggested_book_record_id']=anchor_ids[seg['visual_anchor_id']]['book_record_id']
        seg['matching_method']='assistant_visual_comparison' if seg['visual_anchor_id'] else 'number_scoped_lexical_proposal'
    result={'schema_version':1,'chapter':chapter,'lecture_source_sha256':source['sha256'],
            'normalized_sha256':normalized_sha,'book_source_sha256':info['source_sha256'],
            'collection_sha256':info['collection_sha256'],'processed_pages':report['processed_pages'],
            'segments':segments,'unassigned_block_ids':unassigned,
            'counts':{'segments':len(segments),'pages':len(report['processed_pages']),
                      'visual_anchors':sum(bool(s['visual_anchor_id']) for s in segments),
                      'algorithm_proposals':sum(bool(s['suggested_book_record_id']) and not s['visual_anchor_id'] for s in segments),
                      'unresolved_segments':sum(not s['suggested_book_record_id'] for s in segments),
                      'continuation_pages':len({p for s in segments for p in s['continuation_pages']})},
            'thresholds':{'min_score':.50,'min_margin':.12,'min_chinese_characters':10,
                          'math_dense_alternative':{'min_score':.85,'min_tokens':15}},
            'boundary':'Algorithmic source-location proposals and possible continuations; no answer approval, no model evidence.'}
    write_json(base/'question-segments.json',result)
    print(json.dumps(result['counts'],ensure_ascii=False),flush=True);return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--chapter',default='6');args=p.parse_args();build(args.chapter)
