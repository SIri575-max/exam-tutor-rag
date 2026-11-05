"""Export private reviewed-preview data using the studied LightRAG/RAG-Anything contracts."""
import json
from course_data import load,PRIVATE,document_text


def export():
    data=load();out=PRIVATE/'adapters';out.mkdir(exist_ok=True)
    items=data['concepts']+data['exercises'];by_id={x['id']:x for x in items}
    chunks=[];indices={};source_map={}
    for item in items:
        for citation in item['citations']:
            source_id=data['source_id']+'-'+citation['id']
            index=indices.get(source_id,0);indices[source_id]=index+1
            chunks.append({'content':document_text(item),'source_id':source_id,'source_chunk_index':index})
            source_map[source_id]={'pdf_page':citation['pdf_page'],'printed_page':citation['printed_page'],'source_sha256':data['source_sha256']}
    entities=[{'entity_name':'Mao3:'+('concept:' if x['kind']=='concept' else 'exercise:')+x['id'],
               'entity_type':x['kind'],'description':document_text(x),
               'source_id':data['source_id']+'-'+x['citations'][0]['id']} for x in items]
    relations=[{'src_id':'Mao3:'+edge['from'],'tgt_id':'Mao3:'+edge['to'],
                'description':'考查知识点' if edge['kind']=='tests' else '学习前需要先修概念',
                'keywords':edge['kind'],'weight':1.0,'source_id':data['source_id']+'-'+edge['evidence']}
               for edge in data['graph']['edges']]
    kg={'entities':entities,'relationships':relations,'chunks':chunks}
    multimodal=[{'type':'text','text':document_text(x),'page_idx':x['pages'][0]-1} for x in items]
    for name,value in [('lightrag-custom-kg.json',kg),('raganything-content-list.json',multimodal),('source-map.json',source_map)]:
        (out/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    result={'entities':len(entities),'relationships':len(relations),'chunks':len(chunks),
            'content_list_items':len(multimodal),'framework_sdks_executed':False,
            'review_status':'preview_data_pending_teacher_review','weight_meaning':'Evidence contribution, not confidence probability.'}
    (out/'manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result));return kg


if __name__=='__main__':export()
