"""Versioned, local user review of source records; never auto-promote content."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import uuid
from exercise_vectors import OUT, snapshot, status
from full_book_tutor import retrieve

BASE = OUT.parent / 'validation-review'
CHOICES = ['example-6.2.2','example-6.2.5','example-6.2.6','example-6.3.1',
           'example-6.3.2','example-6.3.4','example-6.3.5','example-6.6.2',
           'example-6.6.3','example-6.6.4','example-6.6.5','example-6.6.6',
           'mao3-6.1-1','mao3-6.1-3','mao3-6.2-2','mao3-6.2-7',
           'mao3-6.3-1','mao3-6.3-7','mao3-6.6-3','mao3-6.6-10']
DIMENSIONS = {'stem', 'topic', 'practice'}
VERDICTS = {'pass', 'needs_changes', 'unsure'}


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def build():
    info=status()
    if not info['ready']:raise ValueError('题库未就绪')
    records=snapshot()[1];items=[]
    for identifier in CHOICES:
        item=records[identifier]
        response=retrieve(item['question_text'][:3000],chapter='6',limit=5)
        candidates=[]
        other='exercise' if item['kind']=='example' else 'example'
        pool=response.get('practice_groups',{}).get(other,[])+response.get('practice_groups',{}).get(item['kind'],[])+response['hits']
        seen={identifier}
        # This is a review candidate list, not an approved exercise path.
        for r in pool:
            if r['id'] in seen:continue
            seen.add(r['id'])
            candidates.append({k:r.get(k) for k in ['id','label','kind','question_text','pages','review_flags']})
            if len(candidates)==3:break
        items.append({**{k:item[k] for k in ['id','label','kind','section','section_title','question_text','pages','stem_boundary','review_flags']},
                      'record_text_sha256':hashlib.sha256(item['question_text'].encode()).hexdigest(),
                      'topic_candidates':response['study']['record_topics'].get(identifier,[]),
                      'reading_candidates':response['study']['readings'][:2],
                      'practice_candidates':candidates,'default_review_status':'pending'})
    signature=hashlib.sha256(json.dumps(items,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    batch={'batch_id':'chapter6-'+signature[:16],'created_date':'2026-10-26',
           'collection_sha256':info['collection_sha256'],'source_sha256':info['source_sha256'],
           'items':items,'boundary':'20 assistant-selected development review records; no teacher-approved labels or independent benchmark.'}
    target=BASE/'batch.json'
    if target.exists():
        old=json.loads(target.read_text(encoding='utf-8'))
        if old['batch_id']!=batch['batch_id']:write(BASE/'history'/(old['batch_id']+'.json'),old)
    write(target,batch)
    print(json.dumps({'batch_id':batch['batch_id'],'items':len(items),'pending_human_review':len(items)},ensure_ascii=False))
    return batch


def current(directory=None):
    folder=directory or BASE
    if not (folder/'batch.json').exists():raise ValueError('审核批次尚未建立')
    batch=json.loads((folder/'batch.json').read_text(encoding='utf-8'))
    info=status()
    if not info['ready'] or batch['collection_sha256']!=info['collection_sha256']:
        raise ValueError('审核批次已过期，请针对当前题库重新生成')
    history=[]
    for path in sorted((folder/'decisions').glob('*.json')):
        row=json.loads(path.read_text(encoding='utf-8'))
        if row.get('batch_id')==batch['batch_id'] and row.get('collection_sha256')==batch['collection_sha256']:
            history.append(row)
    latest={}
    for row in sorted(history,key=lambda r:(r['created_at'],r['id'])):latest[row['record_id']]=row
    return {**batch,'latest_reviews':latest,'reviewed_count':len(latest),
            'automatic_approval_or_training':False}


def save(body,directory=None):
    if not isinstance(body,dict):raise ValueError('无效审核记录')
    folder=directory or BASE;batch=current(folder)
    if body.get('batch_id')!=batch['batch_id'] or body.get('collection_sha256')!=batch['collection_sha256']:
        raise ValueError('审核版本已变化，请刷新')
    record=next((r for r in batch['items'] if r['id']==body.get('record_id')),None)
    if record is None:raise ValueError('题目不属于本批次')
    verdicts=body.get('verdicts')
    if not isinstance(verdicts,dict) or set(verdicts)!=DIMENSIONS or any(v not in VERDICTS for v in verdicts.values()):
        raise ValueError('请分别选择题干公式、考点关联和相关练习的审核结果')
    notes=body.get('notes','')
    if not isinstance(notes,str) or len(notes)>2000:raise ValueError('备注限2000字')
    if 'needs_changes' in verdicts.values() and len(notes.strip())<3:raise ValueError('需要修改时请填写具体问题')
    row={'id':uuid.uuid4().hex,'batch_id':batch['batch_id'],'collection_sha256':batch['collection_sha256'],
         'source_sha256':batch['source_sha256'],'record_id':record['id'],
         'record_text_sha256':record['record_text_sha256'],'created_at':datetime.now(timezone(timedelta(hours=8))).isoformat(),
         'verdicts':verdicts,'notes':notes.strip(),'status':'user_review_recorded',
         'teacher_approval_claimed':False,'automatic_approval_or_training':False}
    write(folder/'decisions'/(row['id']+'.json'),row)
    return {'id':row['id'],'message':'已保存本机审核记录；原文和检索标签不会自动改写。','review':row}


if __name__=='__main__':build()
