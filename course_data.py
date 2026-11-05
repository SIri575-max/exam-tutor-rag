"""Versioned, source-checked preview collection; raw OCR and reference answers stay separate."""
import hashlib
import json
from pathlib import Path
from sync_sources import ROOT, fingerprint

PRIVATE=ROOT/'data/private'


def citation(page,role='textbook'):
    return {'id':f'P{page}','pdf_page':page,'printed_page':str(page-22),
            'label':f'教材印刷第{page-22}页 / PDF第{page}页','url':f'/book-page/{page}.png','role':role}


def load():return json.loads((PRIVATE/'course.json').read_text(encoding='utf-8'))


def document_text(item):
    # Never put reference answers or solution hints into the question-matching index.
    return (item.get('title') or item.get('label',''))+' '+item['text']


def build():
    registry=json.loads((PRIVATE/'textbook_registry/manifest.json').read_text(encoding='utf-8'))['files'][0]
    questions=json.loads((PRIVATE/'curated-exercises.json').read_text(encoding='utf-8'))+json.loads((PRIVATE/'extra-bayes-exercises.json').read_text(encoding='utf-8'))
    concepts=json.loads((PRIVATE/'concept-cards.json').read_text(encoding='utf-8'))
    for item in questions+concepts:
        item['citations']=[citation(p) for p in item['pages']]
        item['source_sha256']=registry['sha256']
        for p in item['pages']:
            image=PRIVATE/'chapter1/pages'/f'pdf-{p:03}.png'
            if not image.exists():raise FileNotFoundError(image)
        if item.get('answer'):
            item['answer']['citations']=[citation(p,'reference_answer') for p in item['answer']['pages']]
            item['answer']['review_status']='assistant_source_checked_pending_teacher_review'
        item['transcription_revision']=1
    ids=[x['id'] for x in concepts+questions]
    if len(ids)!=len(set(ids)):raise ValueError('Duplicate IDs')
    cids={c['id'] for c in concepts}
    for q in questions:
        if set(q['concepts'])-cids:raise ValueError(q['id'])
    nodes=[{'id':'concept:'+c['id'],'label':c['label'],'kind':'concept'} for c in concepts]
    nodes += [{'id':'exercise:'+q['id'],'label':f"习题{q['section']} 第{q['number']}题",'kind':'exercise'} for q in questions]
    edges=[{'from':'exercise:'+q['id'],'to':'concept:'+c,'kind':'tests','evidence':q['citations'][0]['id'],'review_status':q['review_status']} for q in questions for c in q['concepts']]
    edges += [{'from':'concept:'+c['id'],'to':'concept:'+p,'kind':'requires','evidence':c['citations'][0]['id'],'review_status':'assistant_pedagogical_relation_pending_teacher_review'} for c in concepts for p in c['prerequisites']]
    data={'schema_version':2,'collection':'chapter1_assistant_checked_preview','title':'茆书第一章 · 随机事件与概率',
          'source_id':registry['id'],'source_sha256':registry['sha256'],'concepts':concepts,'exercises':questions,
          'graph':{'nodes':nodes,'edges':edges},'scope':'First chapter only; curated preview, not teacher-approved corpus.'}
    data['corpus_sha256']=hashlib.sha256(json.dumps(data,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    (PRIVATE/'course.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'exercises':len(questions),'concepts':len(concepts),'nodes':len(nodes),'edges':len(edges),'collection':data['collection']}))
    return data


if __name__=='__main__':build()
