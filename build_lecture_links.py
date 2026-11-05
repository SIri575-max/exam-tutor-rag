"""Preserve four visually inspected source matches, including annotation differences."""
from fractions import Fraction
import hashlib
import json
from pathlib import Path
from exercise_vectors import record, status, search
from lecture_pipeline import source_for
from process_full_book import write_json
from sync_sources import ROOT

MATCHES=[
 (1,'mao3-6.1-1',[0,1,2,3],['首行的红笔方差符号混入了样本记号；原题应对照教材题干。',
                          '手写Var被识别为tan，不能把编译成功当作数学识别正确。']),
 (20,'mao3-6.3-2',[0,1,2,3],['红笔批注与印刷题干混合，支持区间端点被识别为≤/≥；应分开核对。',
                           '手写求和、乘积和次序统计量有明显识别错误，未作为标准题解。']),
 (60,'mao3-6.5-13',[0,1,2],['印刷题干的“共轭先验/贝塔分布”部分识别错误；分布公式主体可对照原页。',
                         '手写推导尚未校对，不能直接进入生成证据。']),
 (77,'mao3-6.6-19',[0,1,2,3,4],['讲义在印刷题干旁另加“最短”要求，这是批注扩展，教材原题仅要求置信区间。',
                              '末尾手写ln α被识别为ln x，未将此OCR结果当成正确公式。']),
]


def build():
    source=source_for('6');base=ROOT/'data/private/lecture-ocr/chapter6'
    manifest=json.loads((base/'manifest.json').read_text(encoding='utf-8'))
    pages={r['pdf_page']:r for r in manifest['pages']}
    blocks=[json.loads(line) for line in (base/'normalized-blocks.jsonl').read_text(encoding='utf-8').splitlines()]
    info=status();items=[];probes=[]
    for page,identifier,indices,notes in MATCHES:
        book=record(identifier);selected=[b for b in blocks if b['pdf_page']==page and b['block_index'] in indices]
        query='\n'.join(b['text'] for b in selected)
        hits=search(query,mode='hybrid',kind='exercise',chapter='6',limit=5)['hits'];ids=[r['id'] for r in hits]
        probes.append({'lecture_pdf_page':page,'query':query,'expected_book_record':identifier,
                       'rank_at_5':ids.index(identifier)+1 if identifier in ids else None,'returned_ids':ids})
        items.append({'id':'lecture6-p'+str(page)+'-'+identifier,'chapter':'6','lecture_source_id':source['id'],
                      'lecture_source_sha256':source['sha256'],'lecture_pdf_page':page,
                      'lecture_image_sha256':pages[page]['image_sha256'],'book_record_id':identifier,
                      'book_label':book['label'],'book_pdf_pages':book['pages'],
                      'book_stem_sha256':hashlib.sha256(book['question_text'].encode()).hexdigest(),
                      'stem_candidate_block_ids':[b['id'] for b in selected],
                      'matching_method':'assistant_visual_comparison_of_printed_stem_and_formulas',
                      'relation':'same_printed_problem_with_lecture_annotations',
                      'user_review_status':'pending','answer_correctness_approved':False,
                      'generation_evidence_allowed':False,'notes':notes})
    data={'date':'2026-10-26','lecture_source_sha256':source['sha256'],'book_source_sha256':info['source_sha256'],
          'collection_sha256':info['collection_sha256'],'items':items,
          'unresolved_pages':[40],'boundary':'Assistant source matching only. Handwriting/annotations differ; not teacher-approved mathematical answers.'}
    write_json(base/'alignment-candidates.json',data)
    write_json(base/'retrieval-probes.json',{'probes':probes,'hit_at_1':sum(p['rank_at_5']==1 for p in probes),
        'hit_at_5':sum(p['rank_at_5'] is not None for p in probes),
        'boundary':'Four selected source-location development probes using OCR from inspected lecture pages; not independent accuracy or handwriting recognition rate.'})
    weights=[[Fraction(1,2),Fraction(1,3),Fraction(1,6)],[Fraction(1,3)]*3,[Fraction(1,6),Fraction(1,6),Fraction(2,3)]]
    check={'book_record_id':'mao3-6.1-1','lecture_pdf_page':1,
           'assumptions':'iid sample with common mean mu and finite variance sigma^2',
           'weight_sums':[str(sum(w)) for w in weights],
           'variance_multipliers':[str(sum(a*a for a in w)) for w in weights],
           'largest_variance_estimator':3,'origin':'independent Fraction arithmetic; not OCR correction or general solver',
           'teacher_review':'pending'}
    write_json(base/'arithmetic-check.json',check)
    print(json.dumps({'matched_candidates':len(items),'unresolved_pages':[40],
                      'retrieval_ranks':[p['rank_at_5'] for p in probes],'arithmetic_check':check},ensure_ascii=False,indent=2))
    return data


if __name__=='__main__':build()
