"""Local editing drafts and server-observed searches, never teacher approvals."""
import hashlib
import json
import time

import photo_ocr


class ConflictError(ValueError):
    pass


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _source(job_id):
    folder=photo_ocr._folder(job_id)
    try:
        job=photo_ocr.get(job_id)
        if job.get('status')!='ready':raise ValueError('请等待题图识别完成后再保存核对稿。')
        raw=(folder/'ocr/input.json').read_bytes()
        if _sha(raw)!=job['result']['raw_ocr_sha256'] or _sha((folder/'original.bin').read_bytes())!=job['image_sha256']:
            raise ValueError('原图或OCR来源已变化，请重新识别，原核对记录仍保留。')
        text=photo_ocr.transcript(json.loads(raw))['text']
        if text!=job['result']['text']:raise ValueError('识别稿与原始OCR不一致，请重新识别。')
    except FileNotFoundError as exc:raise ValueError('未找到完整题图来源，请重新上传。') from exc
    source={'job_id':job_id,'image_sha256':job['image_sha256'],
            'raw_ocr_sha256':job['result']['raw_ocr_sha256'],'preprocessing':job.get('preprocessing')}
    fingerprint=_sha(json.dumps(source,sort_keys=True,ensure_ascii=False).encode())
    return folder,job,source,fingerprint


def _load(job_id):
    folder,job,source,fingerprint=_source(job_id)
    path=folder/'notebook.json'
    if path.is_file():
        data=json.loads(path.read_text(encoding='utf-8'))
        if data['source_fingerprint']!=fingerprint:raise ConflictError('核对记录的来源版本已变化，不能套用旧记录。')
    else:
        data={'schema_version':1,'job_id':job_id,'source':source,'source_fingerprint':fingerprint,
              'raw_text':job['result']['text'],'revision':0,'drafts':[],'searches':[],
              'review_status':'local_editing_drafts_not_teacher_approved',
              'boundary':'本机编辑稿与实际检索记录；不代表数学正确、教师批准或训练数据。'}
    return folder,job,data


def _write(folder,data):
    temporary=folder/'notebook.tmp'
    temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    temporary.replace(folder/'notebook.json')


def get(job_id):
    with photo_ocr._lock:
        return _load(job_id)[2]


def save(body):
    if not isinstance(body,dict):raise ValueError('无效核对稿请求')
    question=body.get('question');note=body.get('note','');indices=body.get('selected_blocks')
    if not isinstance(question,str) or not question.strip() or len(question.encode())>16000:
        raise ValueError('核对题干不能为空，且UTF-8长度不能超过16000字节，请保留单题。')
    if not isinstance(note,str) or len(note)>500:raise ValueError('修改说明请控制在500字以内。')
    expected=body.get('expected_revision')
    if type(expected) is not int or expected<0:raise ValueError('缺少有效的核对稿版本。')
    with photo_ocr._lock:
        folder,job,data=_load(body.get('job_id'))
        if body.get('source_fingerprint')!=data['source_fingerprint'] or expected!=data['revision']:
            raise ConflictError('核对记录已更新，请读取最新版本；当前输入不会被自动覆盖。')
        count=len(job['result']['blocks'])
        if not isinstance(indices,list) or not indices or len(indices)>count or any(type(i) is not int or not 0<=i<count for i in indices) or len(set(indices))!=len(indices):
            raise ValueError('请选择当前原始识别稿中的有效段落。')
        indices=sorted(indices)
        if data['drafts'] and all(data['drafts'][-1][key]==value for key,value in [('question',question),('selected_blocks',indices),('note',note)]):
            return data  # Repeated identical saves do not create duplicate versions.
        if len(data['drafts'])>=100:raise ValueError('当前题图已保存100版，请先导出记录，再新建题图任务。')
        selected='\n\n'.join(job['result']['blocks'][i]['text'] for i in indices)
        data['revision']+=1
        data['drafts'].append({'revision':data['revision'],'question':question,'note':note,
                              'selected_blocks':indices,'selected_raw_text':selected,
                              'changed_from_selected_ocr':question!=selected,
                              'question_sha256':_sha(question.encode()),
                              'saved_at':time.strftime('%Y-%m-%dT%H:%M:%S%z'),
                              'status':'local_draft_not_teacher_approved'})
        _write(folder,data)
        return data


def _draft(data,binding,question):
    if not isinstance(binding,dict) or binding.get('source_fingerprint')!=data['source_fingerprint']:
        raise ConflictError('题图来源版本不一致，请重新保存核对稿。')
    revision=binding.get('revision')
    if type(revision) is not int:raise ValueError('无效核对稿版本')
    draft=next((d for d in data['drafts'] if d['revision']==revision),None)
    if draft is None or draft['question']!=question:
        raise ConflictError('题干已改变或核对稿不存在，请先保存修改后的题干。')
    return draft


def validate_search(binding,question):
    with photo_ocr._lock:
        _,_,data=_load(binding.get('job_id') if isinstance(binding,dict) else None)
        _draft(data,binding,question)


def record_search(binding,question,result):
    """Only call with a retrieval result computed by this server, never client hits."""
    with photo_ocr._lock:
        folder,_,data=_load(binding['job_id'])
        draft=_draft(data,binding,question)
        if len(data['searches'])>=100:raise ValueError('检索记录已达100条，请先导出。')
        row={'sequence':len(data['searches'])+1,'draft_revision':draft['revision'],
             'question_sha256':draft['question_sha256'],'searched_at':time.strftime('%Y-%m-%dT%H:%M:%S%z'),
             'status':result.get('status'),'route':result.get('route'),'mode':result.get('mode'),
             'elapsed_seconds':result.get('elapsed_seconds'),'collection_sha256':result.get('collection_sha256'),
             'hits':[{'id':h['id'],'label':h['label'],'pages':h.get('pages',[])} for h in result.get('hits',[])],
             'boundary':'服务器实际检索候选，尚未人工判定相关性或数学正确性。'}
        data['searches'].append(row)
        _write(folder,data)
        return {'saved':True,'job_id':binding['job_id'],'draft_revision':draft['revision'],
                'search_sequence':row['sequence'],'message':'已关联本次实际检索记录。'}
