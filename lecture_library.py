"""Private, source-checked lecture preview; raw handwriting is not approved answers."""
import json
from pathlib import Path
from lecture_pipeline import source_for
from sync_sources import ROOT, fingerprint
from math_presentation import present
from exercise_vectors import record, status
from process_full_book import valid_cache

BASE=ROOT/'data/private/lecture-ocr'


def manifest(chapter='6'):
    source=source_for(chapter);base=BASE/('chapter'+chapter)
    if not (base/'manifest.json').exists():raise ValueError('此章尚未准备讲义预览')
    data=json.loads((base/'manifest.json').read_text(encoding='utf-8'))
    if data['source_sha256']!=source['sha256']:raise ValueError('讲义预览来源已过期')
    return base,data


def alignment(chapter='6'):
    base,data=manifest(chapter);path=base/'alignment-candidates.json'
    if not path.exists():return []
    links=json.loads(path.read_text(encoding='utf-8'))
    extra_path=base/'extra-visual-alignments.json'
    if extra_path.exists():
        extra=json.loads(extra_path.read_text(encoding='utf-8'))
        for field in ('lecture_source_sha256','book_source_sha256','collection_sha256'):
            if extra[field]!=links[field]:raise ValueError('补充视觉关联已过期')
        links['items'].extend(extra['items'])
    info=status()
    if info.get('ready') is False:raise ValueError('教材索引已过期')
    if links['lecture_source_sha256']!=data['source_sha256'] or links['book_source_sha256']!=info['source_sha256'] or links['collection_sha256']!=info['collection_sha256']:
        raise ValueError('讲义与教材的候选关联已过期')
    images={r['pdf_page']:r['image_sha256'] for r in data['pages']}
    for link in links['items']:
        if images.get(link['lecture_pdf_page'])!=link['lecture_image_sha256']:raise ValueError('候选关联的原页已变化')
    return links['items']


def overview(chapter='6'):
    base,data=manifest(chapter)
    report_path=base/'normalization-report.json'
    report=json.loads(report_path.read_text(encoding='utf-8')) if report_path.exists() else {}
    index=segment_index(chapter)
    return {'chapter':chapter,'source_name':data['source_name'],'source_total_pages':data['source_total_pages'],
            'prepared_pages':[r['pdf_page'] for r in data['pages']],
            'processed_pages':report.get('processed_pages',[]) if report.get('source_sha256')==data['source_sha256'] else [],
            'links':all_links(chapter),'segmentation_counts':index.get('counts',{}),
            'catalog':[{'id':s['id'],'start_page':s['start_page'],'pages':s['pages'],
                        'printed_number_candidate':s['printed_number_candidate'],
                        'book_label':next((c['book_label'] for c in s['candidates'] if c['book_record_id']==s['suggested_book_record_id']),None),
                        'matching_method':s['matching_method']} for s in index.get('segments',[])],
            'question_index_changed':False,'answers_approved':False,
            'boundary':'Local OCR and pending source-location proposals, not reviewed solution text.'}


def segment_index(chapter='6'):
    base,data=manifest(chapter);path=base/'question-segments.json'
    if not path.exists():return {}
    index=json.loads(path.read_text(encoding='utf-8'));info=status()
    if info.get('ready') is False:raise ValueError('教材索引已过期')
    if index['lecture_source_sha256']!=data['source_sha256'] or index['book_source_sha256']!=info['source_sha256'] or index['collection_sha256']!=info['collection_sha256']:
        raise ValueError('题目分段候选来源已过期')
    # OCR can grow during a batch run. An older segmentation is not silently reused.
    if fingerprint(base/'normalized-blocks.jsonl')!=index['normalized_sha256']:return {}
    return index


def all_links(chapter='6'):
    manual=alignment(chapter);index=segment_index(chapter)
    anchored={r['id'] for r in manual};rows=list(manual)
    base,data=manifest(chapter);images={r['pdf_page']:r['image_sha256'] for r in data['pages']}
    for seg in index.get('segments',[]):
        if seg['visual_anchor_id'] in anchored or not seg['suggested_book_record_id']:continue
        chosen=next(c for c in seg['candidates'] if c['book_record_id']==seg['suggested_book_record_id'])
        rows.append({**chosen,'id':seg['id'],'chapter':chapter,'lecture_pdf_page':seg['start_page'],
                     'lecture_pdf_pages':seg['pages'],'lecture_image_sha256':images[seg['start_page']],
                     'matching_method':'number_scoped_lexical_proposal','user_review_status':'pending',
                     'answer_correctness_approved':False,'generation_evidence_allowed':False,
                     'notes':['题号与文本相似度给出的算法候选，尚未逐题确认；分数不是正确概率。',
                              '跨页范围按阅读顺序推断，续页需核对题号和上下文。']})
    return rows


def get_page(chapter,number):
    base,data=manifest(chapter);row=next((r for r in data['pages'] if r['pdf_page']==number),None)
    if row is None:raise ValueError('此页尚未准备，请选择已处理页码')
    image=(base/row['image']).resolve()
    if not image.is_relative_to((base/'pages').resolve()) or fingerprint(image)!=row['image_sha256']:raise ValueError('讲义原页缓存已变化')
    cache=json.loads((base/'ocr-cache.json').read_text(encoding='utf-8')) if (base/'ocr-cache.json').exists() else {}
    parsed=valid_cache(base,row,cache)
    blocks=[]
    path=base/'normalized-blocks.jsonl'
    if parsed and path.exists():
        report_path=base/'normalization-report.json'
        if report_path.exists():
            report=json.loads(report_path.read_text(encoding='utf-8'))
            if report['source_sha256']!=data['source_sha256'] or report.get('normalized_sha256')!=fingerprint(path):
                raise ValueError('标准化识别稿已变化，请重新处理后查看')
        for line in path.read_text(encoding='utf-8').splitlines():
            block=json.loads(line)
            if block['pdf_page']==number:
                # Keep original content; flag promotion/footer blocks in the preview only.
                if block.get('source_sha256')!=data['source_sha256']:raise ValueError('OCR来源已变化')
                blocks.append(block)
    links=[v for v in all_links(chapter) if v['lecture_pdf_page']==number]
    books=[present(record(link['book_record_id'])) for link in links]
    segments=[s for s in segment_index(chapter).get('segments',[]) if number in s['pages']]
    return {'chapter':chapter,'lecture_pdf_page':number,'source_name':data['source_name'],
            'source_sha256':data['source_sha256'],'image_sha256':row['image_sha256'],
            'blocks':blocks,'ocr_cache_valid':parsed,'links':links,'book_records':books,'segments':segments,
            'boundary':'Lecture page number is independent from textbook PDF page number.'}


def image_bytes(chapter,number):
    base,data=manifest(chapter);row=next((r for r in data['pages'] if r['pdf_page']==number),None)
    if row is None:raise ValueError('尚未准备的讲义原页')
    path=(base/row['image']).resolve()
    if not path.is_relative_to((base/'pages').resolve()) or fingerprint(path)!=row['image_sha256']:raise ValueError('原页缓存不匹配')
    return path.read_bytes()


def links_for(ids):
    ids=set(ids)
    if len(ids)>20:raise ValueError('一次最多查询20道题')
    rows=all_links('6')
    return {'links':{key:[r for r in rows if r['book_record_id']==key] for key in ids},'status':'source_location_candidates_pending_user_review'}
