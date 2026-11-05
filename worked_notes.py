"""Version-bound, assistant-authored teaching notes kept outside model evidence."""
import argparse
import hashlib
import json
from pathlib import Path
from exercise_vectors import record, status
from lecture_pipeline import source_for
from process_full_book import write_json
from question_knowledge import current
from sync_sources import ROOT, fingerprint
from worked_note_content import NOTES
from worked_note_checks import checks

BASE=ROOT/'data/private/worked-notes'


def text_sha(text):return hashlib.sha256(text.encode()).hexdigest()


def build():
    source=source_for('6');info=status();graph=current()
    if not info['ready']:raise ValueError('教材索引已过期')
    lecture_base=ROOT/'data/private/lecture-ocr/chapter6'
    manifest=json.loads((lecture_base/'manifest.json').read_text(encoding='utf-8'))
    if manifest['source_sha256']!=source['sha256']:raise ValueError('讲义来源已过期')
    pages={r['pdf_page']:r for r in manifest['pages']};topics={t['id']:t for t in graph['topics']}
    results=checks()
    if not all(r['passed'] for r in results.values()):raise ValueError('数学样板检查失败')
    BASE.mkdir(parents=True,exist_ok=True);items=[]
    for note in NOTES:
        book=record(note['record_id']);row=pages[note['lecture_page']]
        if fingerprint(lecture_base/row['image'])!=row['image_sha256']:raise ValueError('讲义原图已变化')
        practice=[]
        for p in note['practice']:
            r=record(p['id']);practice.append({**p,'label':r['label'],'pages':r['pages'],'record_text_sha256':text_sha(r['question_text'])})
        items.append({**note,'date':'2026-10-27','book_label':book['label'],'book_pages':book['pages'],
                      'book_stem_sha256':text_sha(book['question_text']),
                      'lecture_image_sha256':row['image_sha256'],
                      'author':'assistant','content_kind':'assistant_authored_explanation_not_raw_transcription',
                      'teacher_review_status':'pending','generation_evidence_allowed':False,
                      'topics':[{'id':tid,'label':topics[tid]['title'],'pdf_page':topics[tid]['pdf_first'],
                                 'relation':'explanation_topic_mapping_pending_teacher_review'} for tid in note['topic_ids']],
                      'practice':practice,'check':results[note['check_key']]})
    data={'version':1,'date':'2026-10-27','lecture_source_sha256':source['sha256'],
          'book_source_sha256':info['source_sha256'],'collection_sha256':info['collection_sha256'],
          'content_code_sha256':fingerprint(Path(__file__).with_name('worked_note_content.py')),
          'items':items,'boundary':'Assistant explanations with narrow checks, not teacher-approved model evidence.'}
    write_json(BASE/'notes.json',data)
    write_json(BASE/'manifest.json',{'notes_sha256':fingerprint(BASE/'notes.json'),'date':'2026-10-27'})
    write_json(BASE/'checks.json',{'date':'2026-10-27','checks':results,'all_passed':True,
                                'boundary':'Arithmetic, quadrature and simulation checks; not RAG answer quality or general proof certification.'})
    return {'notes':len(items),'checks_passed':len(results),'teacher_reviews':0,'model_calls':0}


def load():
    path=BASE/'notes.json'
    if not path.exists():return {'items':[]}
    manifest=json.loads((BASE/'manifest.json').read_text(encoding='utf-8'))
    if manifest['notes_sha256']!=fingerprint(path):raise ValueError('整理讲解文件已变化，请重新核对构建')
    data=json.loads(path.read_text(encoding='utf-8'));source=source_for('6');info=status()
    if not info['ready'] or data['lecture_source_sha256']!=source['sha256'] or data['book_source_sha256']!=info['source_sha256'] or data['collection_sha256']!=info['collection_sha256']:
        raise ValueError('整理讲解的来源版本已变化，请重新核对')
    if data['content_code_sha256']!=fingerprint(Path(__file__).with_name('worked_note_content.py')):raise ValueError('讲解内容已更新，请重新构建')
    for n in data['items']:
        if n.get('generation_evidence_allowed') is not False or n.get('teacher_review_status')!='pending':raise ValueError('未支持的讲解审核状态')
        if text_sha(record(n['record_id'])['question_text'])!=n['book_stem_sha256']:raise ValueError('讲解对应题干已变化')
    return data


def catalog(ids=None):
    wanted=set(ids) if ids is not None else None
    if wanted is not None and len(wanted)>20:raise ValueError('一次最多查询20道题')
    data=load()
    return {'items':[{'record_id':n['record_id'],'title':n['title'],'book_label':n['book_label'],
                     'lecture_page':n['lecture_page'],'teacher_review_status':n['teacher_review_status']}
                     for n in data['items'] if wanted is None or n['record_id'] in wanted],
            'generated_live':False,'teacher_approved':False}


def get(identifier):
    data=load();note=next((n for n in data['items'] if n['record_id']==identifier),None)
    if note is None:raise ValueError('这道题尚未整理讲解样板')
    base=ROOT/'data/private/lecture-ocr/chapter6'
    if fingerprint(base/'pages'/f"pdf-{note['lecture_page']:03}.png")!=note['lecture_image_sha256']:raise ValueError('讲解对应原图已变化')
    from math_presentation import present
    return {'note':note,'book_record':present(record(identifier)),'generated_live':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--build',action='store_true');args=parser.parse_args()
    print(json.dumps(build() if args.build else catalog(),ensure_ascii=False,indent=2))
