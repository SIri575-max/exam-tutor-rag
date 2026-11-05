"""Local, explicitly human-operated relevance review of a pinned report snapshot."""
import argparse
from datetime import datetime, timezone, timedelta
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import threading

from external_question_bank import BASE, ROOT, write_json
from score_external_relevance import score_case, template

LOCK=threading.Lock()
STRATA={'exact_textbook_duplicate','parameter_or_wording_variant','related_concept_new_problem',
        'outside_current_scope','unresolved'}


class ConflictError(ValueError):pass


def activate(report_path):
    path=Path(report_path).resolve()
    if not path.is_relative_to((BASE/'retrieval-runs').resolve()) or path.name!='report.json':
        raise ValueError('Only a private retrieval report may be selected')
    raw=path.read_bytes();report=json.loads(raw)
    if len(report['cases'])!=len(report['frozen_cases']) or any(len(c['arms'])!=4 for c in report['cases']):
        raise ValueError('Finish the report before opening human review')
    value={'report':path.relative_to(BASE).as_posix(),'report_sha256':hashlib.sha256(raw).hexdigest()}
    write_json(BASE/'active-review.json',value)
    return value


@lru_cache(maxsize=3)
def _load(path_text,expected):
    raw=Path(path_text).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=expected:raise ValueError('Report changed; re-pin the snapshot explicitly')
    report=json.loads(raw)
    return report,{c['case_id']:c for c in report['cases']}


def context():
    pointer=json.loads((BASE/'active-review.json').read_text(encoding='utf-8'))
    path=(BASE/pointer['report']).resolve()
    if not path.is_relative_to((BASE/'retrieval-runs').resolve()) or path.name!='report.json':raise ValueError('Invalid review snapshot')
    if hashlib.sha256(path.read_bytes()).hexdigest()!=pointer['report_sha256']:raise ValueError('Report changed; re-pin the snapshot explicitly')
    report,cases=_load(str(path),pointer['report_sha256'])
    return pointer,report,cases


def development_ids():
    p=ROOT/'evaluation/route_repair_protocol_20261029.json'
    return set(json.loads(p.read_text(encoding='utf-8'))['development_case_ids']) if p.exists() else set()


def state_path(digest,case_id):
    if not re.fullmatch(r'660b-c[1-8]-q\d{3}',case_id):raise ValueError('Invalid case ID')
    return BASE/'human-reviews'/digest/(case_id+'.json')


def read_state(digest,case_id):
    path=state_path(digest,case_id)
    if path.exists():return json.loads(path.read_text(encoding='utf-8'))
    return {'revision':0,'current':None,'history':[]}


def source_checks(cases):
    """Source-only review hints; never inspect retrieval ranks or method identity."""
    hints={identifier:[] for identifier in cases}
    path=BASE/'dataset/math-syntax-audit.json'
    if path.exists():
        for failure in json.loads(path.read_text(encoding='utf-8')).get('failures',[]):
            identifier=failure.get('case_id')
            if identifier in hints and '公式语法待核对' not in hints[identifier]:
                hints[identifier].append('公式语法待核对')
    # Source-page conflict documented by objective-pilot/source-review.json.
    if '660b-c1-q007' in hints:hints['660b-c1-q007'].append('否定与补事件符号待核对')
    for identifier,c in cases.items():
        if len(c.get('source_pages',[]))>1:hints[identifier].append('跨页条件待核对')
    return hints


def overview():
    pointer,report,cases=context();dev=development_ids();rows=[];checks=source_checks(cases)
    for identifier,c in cases.items():
        state=read_state(pointer['report_sha256'],identifier);current=state['current'] or {}
        rows.append({'case_id':identifier,'chapter':c['chapter'],'source_pages':c['source_pages'],
                     'status':current.get('status','pending'),'revision':state['revision'],
                     'development':identifier in dev,'preview':c['query'][:100],
                     'search_text':c['query'],'source_checks':checks[identifier]})
    return {'report_sha256':pointer['report_sha256'],'cases':rows,'total':len(rows),
            'approved':sum(c['status']=='approved' for c in rows),'source_pages':146,
            'boundary':'Blind pooled review; all grades require explicit human entry. No held-out split has been approved.'}


def get_case(identifier):
    pointer,report,cases=context()
    if identifier not in cases:raise ValueError('Unknown review case')
    c=cases[identifier]
    pool={h['id']:h for a in c['arms'].values() for h in a.get('hits',[])}
    # Hide routes, ranks, scores, expected IDs and answer pages from blind relevance review.
    candidates=[{k:pool[i].get(k) for k in ['id','label','question_text','pages','section']} for i in sorted(pool)]
    return {'report_sha256':pointer['report_sha256'],'case_id':identifier,'query':c['query'],
            'source_pages':c['source_pages'],'candidates':candidates,'development':identifier in development_ids(),
            'source_checks':source_checks(cases)[identifier],
            'state':read_state(pointer['report_sha256'],identifier)}


def save(body):
    if not isinstance(body,dict):raise ValueError('Invalid review')
    with LOCK:
        pointer,report,cases=context();identifier=body.get('case_id')
        if identifier not in cases or body.get('report_sha256')!=pointer['report_sha256']:raise ValueError('Review snapshot mismatch')
        state=read_state(pointer['report_sha256'],identifier)
        if type(body.get('base_revision')) is not int or body['base_revision']!=state['revision']:raise ConflictError('审核已更新，请重新载入后编辑')
        status=body.get('status')
        if status not in {'draft','approved'}:raise ValueError('Choose draft or approved explicitly')
        grades=body.get('grades',{});pool={h['id'] for a in cases[identifier]['arms'].values() for h in a.get('hits',[])}
        if not isinstance(grades,dict) or not set(grades)<=pool:raise ValueError('Unknown candidate grade')
        if any(v is not None and (type(v) is not int or not 0<=v<=3) for v in grades.values()):raise ValueError('Grades must be blank or integers 0..3')
        for key,maximum in [('reviewer',64),('family_id',128),('notes',2000)]:
            if not isinstance(body.get(key,''),str) or len(body.get(key,''))>maximum:raise ValueError('Invalid '+key)
        if type(body.get('ocr_checked')) is not bool:raise ValueError('Confirm OCR explicitly')
        stratum=body.get('overlap_stratum') or None
        if stratum is not None and stratum not in STRATA:raise ValueError('Invalid overlap stratum')
        row={'case_id':identifier,'status':status,'reviewer':body.get('reviewer','').strip(),
             'ocr_checked':body['ocr_checked'],'family_id':body.get('family_id','').strip() or None,
             'overlap_stratum':stratum,'split':'development' if identifier in development_ids() else 'quarantine',
             'grades':{k:grades.get(k) for k in sorted(pool)},'notes':body.get('notes',''),
             'review_origin':'explicit_local_user_entry','saved_at':datetime.now(timezone(timedelta(hours=8))).isoformat()}
        if status=='approved':
            if stratum=='unresolved':raise ValueError('重合分层未解决，请保存草稿')
            if score_case(cases[identifier],row)['status']!='reviewed':raise ValueError('请填写审核人后确认通过')
        if len(state['history'])>=100:raise ValueError('审核历史达到100版，请先导出归档')
        value={'revision':state['revision']+1,'current':row,'history':state['history']+[row]}
        path=state_path(pointer['report_sha256'],identifier);path.parent.mkdir(parents=True,exist_ok=True)
        temporary=path.with_suffix('.tmp');write_json(temporary,value);temporary.replace(path)
        return {'saved':True,'case_id':identifier,'revision':value['revision'],'status':status}


def export():
    pointer,report,cases=context();data=template(report);data['report_sha256']=pointer['report_sha256']
    for n,c in enumerate(data['cases']):
        current=read_state(pointer['report_sha256'],c['case_id'])['current']
        if current:data['cases'][n]=current
    return data


def image_bytes(number):
    if type(number) is not int or not 6<=number<=87:raise ValueError('Only registered question pages are available here')
    return (BASE/'pages'/f'pdf-{number:03}.png').read_bytes()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('report');print(json.dumps(activate(p.parse_args().report)))
