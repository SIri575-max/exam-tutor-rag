"""Local feedback is an issue report, never an automatic teacher approval or corpus edit."""
import datetime as dt
import json
import threading
import uuid
from course_data import PRIVATE,load

LOCK=threading.Lock()


def save(body):
    message=body.get('message','')
    if not isinstance(message,str) or not 3<=len(message.strip())<=1000:raise ValueError('请填写3–1000字的问题说明')
    category=body.get('category')
    if category not in {'wrong_concept','wrong_formula','wrong_source','other'}:raise ValueError('未知反馈类型')
    id=body.get('record_id')
    known={x['id'] for x in load()['exercises']+load()['concepts']}
    if id not in known:raise ValueError('请选择当前预览集中的题目或考点')
    row={'id':uuid.uuid4().hex,'record_id':id,'category':category,'message':message.strip(),
         'created_at':dt.datetime.now(dt.timezone.utc).isoformat(),'status':'issue_pending_review',
         'origin':'automated_test' if body.get('automated_test') is True else 'local_user_feedback',
         'changes_corpus':False,'teacher_approval':False}
    with LOCK:
        with (PRIVATE/'feedback.jsonl').open('a',encoding='utf-8') as stream:stream.write(json.dumps(row,ensure_ascii=False)+'\n')
    return {'id':row['id'],'status':row['status'],'message':'已保存到本地待处理清单；不会自动改写教材或题库。'}
