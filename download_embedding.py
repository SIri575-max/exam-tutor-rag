"""Explicit public-weight download; textbook content is not sent to the model repository."""
import json
import os
from fastembed import TextEmbedding
from course_data import PRIVATE
from vector_index import MODEL


if __name__=='__main__':
    os.environ.setdefault('HF_HUB_DISABLE_XET','1')
    model=TextEmbedding(model_name=MODEL,cache_dir=str(PRIVATE/'embedding-cache'),threads=2,providers=['CPUExecutionProvider'])
    vector=list(model.embed(['样本空间与概率']))[0]
    result={'model':MODEL,'dimensions':len(vector),'providers':['CPUExecutionProvider'],'status':'local_embedding_executed'}
    (PRIVATE/'embedding-bootstrap.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))
