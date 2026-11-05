"""Real local BGE ONNX embeddings, SQLite vector storage and cosine search."""
import json
import sqlite3
import threading
from contextlib import closing
from functools import lru_cache
from pathlib import Path
from course_data import PRIVATE, load, document_text

MODEL='BAAI/bge-small-zh-v1.5'
DB=PRIVATE/'retrieval.sqlite3'
LOCK=threading.RLock()


@lru_cache(maxsize=1)
def encoder():
    from fastembed import TextEmbedding
    return TextEmbedding(model_name=MODEL,cache_dir=str(PRIVATE/'embedding-cache'),threads=2,
                         providers=['CPUExecutionProvider'],local_files_only=True)


def build():
    import numpy as np
    data=load();items=data['exercises']+data['concepts']
    with LOCK: vectors=list(encoder().embed([document_text(x) for x in items],batch_size=16))
    staged=DB.with_suffix('.building.sqlite3')
    if staged.exists():staged.unlink()
    with closing(sqlite3.connect(staged)) as conn, conn:
        conn.executescript('CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT); CREATE TABLE documents(id TEXT PRIMARY KEY,kind TEXT,text TEXT,embedding BLOB);')
        for item,vector in zip(items,vectors):
            v=np.asarray(vector,dtype=np.float32);v=v/max(float(np.linalg.norm(v)),1e-12)
            conn.execute('INSERT INTO documents VALUES(?,?,?,?)',(item['id'],item['kind'],document_text(item),v.tobytes()))
        meta={'model':MODEL,'dimensions':len(vectors[0]),'corpus_sha256':data['corpus_sha256'],'documents':len(items),'backend':'fastembed ONNX CPU'}
        conn.executemany('INSERT INTO metadata VALUES(?,?)',[(k,json.dumps(v)) for k,v in meta.items()])
    staged.replace(DB)
    print(json.dumps(meta,ensure_ascii=False))
    return meta


def status():
    if not DB.exists():return {'ready':False,'reason':'index_not_built'}
    with closing(sqlite3.connect(DB)) as conn:meta={k:json.loads(v) for k,v in conn.execute('SELECT key,value FROM metadata')}
    meta['ready']=meta.get('corpus_sha256')==load()['corpus_sha256']
    if not meta['ready']:meta['reason']='corpus_changed_rebuild_required'
    return meta


def search(query,limit=12):
    import numpy as np
    if not status()['ready']:raise RuntimeError('Semantic index unavailable or stale')
    with LOCK: vector=np.asarray(list(encoder().query_embed([query]))[0],dtype=np.float32)
    vector=vector/max(float(np.linalg.norm(vector)),1e-12)
    with closing(sqlite3.connect(DB)) as conn:rows=list(conn.execute('SELECT id,embedding FROM documents'))
    scores=np.vstack([np.frombuffer(blob,dtype=np.float32) for _,blob in rows])@vector
    return sorted([(row[0],float(score)) for row,score in zip(rows,scores)],key=lambda x:-x[1])[:limit]


if __name__=='__main__':build()
