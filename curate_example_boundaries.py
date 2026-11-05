"""Source-linked boundary annotations; never rewrite the raw OCR archive."""
import json
from exercise_collection import rows
from process_full_book import BASE, write_json
from sync_sources import fingerprint

# Inclusive original block offsets. Selection is based on the inspected OCR
# paragraphs, not a fabricated cleaned question. Mathematical correctness is
# outside this boundary review. Selected original pages were also inspected.
RULES = {
 '2.2.6': ([0,1,2], '为此'), '2.7.2': ([0], '这就有'),
 '4.1.1': ([0,1], None), '4.1.2': ([0,1,2], '则'), '4.3.4': ([0,1],None),
 '5.1.3': ([0,1],None), '5.2.1': ([0,1],None), '5.2.2': ([0,1],None),
 '5.2.3': ([0,1,2],None), '5.2.4': ([0,1],None), '5.3.1': ([0,1],None),
 '5.5.1': ([0,1,2],None), '6.2.1': ([0,1,2],'本例中经计算'),
 '6.2.2': ([0,1,2],'此处k'), '6.2.6': ([0,1,2],'由于'),
 '7.1.2': ([0],None), '7.2.2': ([0,1,2],None), '7.2.6': ([0,1,2],None),
 '7.3.1': ([0,1],None), '7.3.2': ([0],None), '7.4.2': ([0],None),
 '7.5.1': ([0,2],None), '7.5.2': ([0,1],None), '7.5.3': ([0,1,2],None),
 '7.5.4': ([0,1],None), '7.6.4': ([0,1,2],None), '7.6.5': ([0,1],None),
 '8.1.1': ([0,1],None), '8.1.4': ([0,1],None), '8.3.1': ([0,1,2,3],None),
 '8.3.2': ([0,1],None), '8.4.1': ([0,1,2],None),
 '8.4.5': ([0,1],None), '8.5.1': ([0,1,2],None),
}
VISUAL_PAGES = {255,295,347,376,377,395,435,436}


def build():
    manifest=json.loads((BASE/'manifest.json').read_text(encoding='utf-8'))
    images={r['pdf_page']:r['image_sha256'] for r in manifest['pages']}
    blocks={r['id']:r for r in rows(BASE/'normalized-blocks.jsonl')}
    items={}
    for r in rows(BASE/'learning-units.jsonl'):
        if r['kind']=='example' and r['id'] not in items:items[r['id']]=r
    annotations={}
    for number,(offsets,cut) in RULES.items():
        item=items['example-'+number];spans=[]
        for offset in offsets:
            block=blocks[item['block_ids'][offset]];text=block['text'];end=len(text)
            if offset==offsets[-1] and cut:
                if cut not in text:raise ValueError('Boundary anchor missing: '+number)
                end=text.index(cut)
            spans.append({'block_id':block['id'],'start':0,'end':end,
                          'text_sha256':__import__('hashlib').sha256(text.encode()).hexdigest()})
        annotation={'spans':spans,'source_sha256':manifest['source_sha256'],
                    'source_unit_text_sha256':__import__('hashlib').sha256(item['text'].encode()).hexdigest(),
                    'page_image_sha256':{str(p):images[p] for p in item['pages']},
                    'review_status':'assistant_OCR_block_boundary_review; mathematical_and_teacher_review_pending',
                    'visually_inspected_pages':sorted(set(item['pages'])&VISUAL_PAGES)}
        if number=='7.5.2':
            header=blocks['block-d371933110ebf22023433836']
            annotation['supplements']=[{'text':'539.35 179.49 782.93 561.10 286.80',
                                        'pdf_page':377,'block_id':header['id'],
                                        'image_sha256':images[377],
                                        'bbox_normalized':header['bbox_normalized'],
                                        'reason':'Five continuing data values were misclassified as a header and concatenated by OCR.',
                                        'review_status':'assistant_visual_transcription_checked; teacher_review_pending'}]
        if number=='7.2.6':annotation['warning']='机床乙数据OCR有数字粘连，计算前必须核对原图'
        if number in {'8.1.4','8.3.1','8.3.2'}:annotation['warning']='原表混有数据与计算列，不能把所有表格数字直接当样本'
        annotations[item['id']]=annotation
    result={'version':1,'source_sha256':manifest['source_sha256'],
            'raw_units_sha256':fingerprint(BASE/'learning-units.jsonl'),
            'raw_blocks_sha256':fingerprint(BASE/'normalized-blocks.jsonl'),
            'annotations':annotations,'boundary':'Span review only; original OCR is unchanged, not full mathematical proofreading.'}
    write_json(BASE/'example-boundary-reviews.json',result)
    print(json.dumps({'annotations':len(annotations),'source_supplements':1},ensure_ascii=False))
    return result


if __name__=='__main__':build()
