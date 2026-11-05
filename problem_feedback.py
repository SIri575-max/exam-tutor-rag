"""Private pending-review feedback; never automatically approves or retrains content."""
import csv
import datetime as dt
import json
import uuid
from exercise_vectors import OUT, snapshot, status
from process_full_book import write_json

CATEGORIES={'stem_missing','formula','topic','ranking','source','other'}


def save(body,directory=None):
    if not isinstance(body,dict):raise ValueError('无效反馈')
    identifier=body.get('record_id');category=body.get('category');text=body.get('message','')
    info=status()
    if not info['ready']:raise ValueError('资料已变化，请重建后反馈')
    if not isinstance(identifier,str) or identifier not in snapshot()[1]:raise ValueError('未知题号')
    if category not in CATEGORIES:raise ValueError('未知反馈类别')
    if not isinstance(text,str) or not 3<=len(text.strip())<=2000:raise ValueError('请填写3–2000字的问题说明')
    query=body.get('query','')
    if not isinstance(query,str) or len(query)>3000:raise ValueError('题干过长')
    record=snapshot()[1][identifier]
    item={'id':uuid.uuid4().hex,'created_at':dt.datetime.now().astimezone().isoformat(),
          'record_id':identifier,'label':record['label'],'category':category,'message':text.strip(),
          'query':query,'pages':record['pages'],'source_sha256':info['source_sha256'],
          'collection_sha256':info['collection_sha256'],'status':'pending_review',
          'automatic_training_or_approval':False}
    folder=directory or OUT/'feedback';folder.mkdir(parents=True,exist_ok=True)
    write_json(folder/(item['id']+'.json'),item)
    return {'id':item['id'],'status':'pending_review','message':'已保存到本地待复核清单；不会自动改写教材或加入训练。'}


def export_queue():
    records=snapshot()[1];pending=[r for r in records.values() if r['stem_boundary']=='opening_only_boundary_unresolved']
    path=OUT/'example-review-queue.csv'
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=['id','label','section','pdf_pages','example_role','opening_text','action','source_sha256'])
        writer.writeheader()
        for r in pending:
            writer.writerow({'id':r['id'],'label':r['label'],'section':r['section'],
                             'pdf_pages':','.join(map(str,r['pages'])),'example_role':r['example_role'],
                             'opening_text':r['question_text'],'action':'核对说明例/续例/独立问题，补齐条件并标注题干与讲解边界',
                             'source_sha256':r['source_sha256']})
    return {'pending_example_boundaries':len(pending),'path':str(path)}


if __name__=='__main__':print(json.dumps(export_queue(),ensure_ascii=False))
