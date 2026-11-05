"""Persistent full-book question vectors + BM25/RRF; exact search at this corpus size."""
import collections
import datetime as dt
import hashlib
import json
import math
import sqlite3
import threading
import time
from contextlib import closing
from functools import lru_cache
from pathlib import Path
from exercise_collection import prepare, input_signature, searchable_text
from process_full_book import BASE, write_json
from retrieval import tokens
from vector_index import encoder, LOCK, MODEL
from formula_chunking import intervals

OUT = BASE / 'question-vectors'
DB = OUT / 'vectors.sqlite3'
BUILD_LOCK = threading.Lock()
MAX_TOKENS = 480
CHUNK_CHARS = 320
OVERLAP = 64


def connect(path=None):
    conn = sqlite3.connect(Path(path or DB).resolve().as_uri() + '?mode=ro', uri=True)
    return conn


def legacy_chunks(record, count_tokens):
    text = record['search_text']
    prefix = f"{record['section_title']} | {record['label']}\n"[:100]
    result = []; start = 0
    while start < len(text):
        end = min(len(text), start + CHUNK_CHARS)
        while count_tokens(prefix + text[start:end]) > MAX_TOKENS:
            if end - start < 2: raise ValueError('Cannot fit chunk token budget')
            end = start + (end - start) // 2
        payload = prefix + text[start:end]
        result.append({'id': f"{record['id']}::c{len(result)}", 'record_id': record['id'],
                       'text': payload, 'start': start, 'end': end,
                       'token_count': count_tokens(payload),
                       'content_sha256': hashlib.sha256(payload.encode()).hexdigest()})
        if end == len(text): break
        start = max(start + 1, end - min(OVERLAP, (end - start) // 4))
    return result


def chunks(record, count_tokens):
    text = record['search_text']
    prefix = f"{record['section_title']} | {record['label']}\n"[:100]
    result = []
    for start, end, flags in intervals(text, prefix, count_tokens, CHUNK_CHARS, OVERLAP, MAX_TOKENS):
        payload = prefix + text[start:end]
        result.append({'id': f"{record['id']}::c{len(result)}", 'record_id': record['id'],
                       'text': payload, 'start': start, 'end': end, 'boundary_flags': flags,
                       'token_count': count_tokens(payload),
                       'content_sha256': hashlib.sha256(payload.encode()).hexdigest()})
    return result


@lru_cache(maxsize=1)
def tokenizer_counter():
    # Separate tokenizer: never mutate FastEmbed's shared inference tokenizer.
    from tokenizers import Tokenizer
    model_dir = Path(encoder().model._model_dir)
    tokenizer = Tokenizer.from_file(str(model_dir / 'tokenizer.json'))
    tokenizer.no_truncation(); tokenizer.no_padding()
    return lambda s: len(tokenizer.encode(s).ids), model_dir


def build():
    import numpy as np
    with BUILD_LOCK:
        started = time.monotonic()
        records, report = prepare()
        count, model_dir = tokenizer_counter()
        model_hashes = {str(p.relative_to(model_dir)): hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in model_dir.rglob('*') if p.is_file() and p.suffix in {'.onnx', '.json'}}
        all_chunks = [c for r in records for c in chunks(r, count)]
        staged = OUT / 'vectors.building.sqlite3'
        if staged.exists(): staged.unlink()
        old = {}
        if DB.exists():
            with closing(connect()) as conn:
                meta = {k: json.loads(v) for k, v in conn.execute('SELECT key,value FROM metadata')}
                if meta.get('model') == MODEL and meta.get('model_files_sha256') == model_hashes:
                    old = {h: blob for h, blob in conn.execute('SELECT content_sha256,embedding FROM chunks')}
        pending = [c for c in all_chunks if c['content_sha256'] not in old]
        write_json(OUT / 'build-progress.json', {'status': 'embedding', 'chunks': len(all_chunks), 'pending': len(pending), 'completed': 0})
        for offset in range(0, len(pending), 16):
            batch = pending[offset:offset + 16]
            with LOCK: vectors = list(encoder().embed([c['text'] for c in batch], batch_size=16))
            for c, vector in zip(batch, vectors):
                v = np.asarray(vector, dtype=np.float32)
                if v.shape != (512,) or not np.isfinite(v).all(): raise ValueError('Invalid embedding')
                v /= max(float(np.linalg.norm(v)), 1e-12)
                old[c['content_sha256']] = v.tobytes()
            done = min(offset + 16, len(pending))
            write_json(OUT / 'build-progress.json', {'status': 'embedding', 'chunks': len(all_chunks), 'pending': len(pending), 'completed': done})
            if done % 160 == 0 or done == len(pending): print(f'Embedded {done}/{len(pending)} new chunks', flush=True)
        metadata = {**report, 'model': MODEL, 'dimensions': 512, 'chunks': len(all_chunks),
                    'chunk_version': 2, 'chunk_strategy': 'formula_aware_soft_character_target_hard_token_budget',
                    'chunk_boundary_warnings': [{k:c[k] for k in ['id','record_id','start','end','boundary_flags']} for c in all_chunks if c['boundary_flags']],
                    'max_input_tokens': max(c['token_count'] for c in all_chunks),
                    'chunk_token_budget': MAX_TOKENS, 'chunk_chars': CHUNK_CHARS, 'overlap_chars': OVERLAP,
                    'new_embeddings': len(pending), 'reused_embeddings': len(all_chunks) - len(pending),
                    'backend': 'SQLite float32 vectors + NumPy exact cosine; FastEmbed ONNX CPU',
                    'built_at': dt.datetime.now().astimezone().isoformat(),
                    'elapsed_seconds': round(time.monotonic() - started, 3),
                    'model_files_sha256': model_hashes,
                    'query_methods': ['bm25', 'vector', 'hybrid'], 'external_requests': False}
        with closing(sqlite3.connect(staged)) as conn, conn:
            conn.executescript('CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT);'
                               'CREATE TABLE records(id TEXT PRIMARY KEY,kind TEXT,chapter TEXT,section TEXT,data TEXT);'
                               'CREATE TABLE chunks(id TEXT PRIMARY KEY,record_id TEXT,text TEXT,start INTEGER,end INTEGER,token_count INTEGER,content_sha256 TEXT,embedding BLOB,FOREIGN KEY(record_id) REFERENCES records(id));'
                               'CREATE INDEX by_record ON chunks(record_id); CREATE INDEX by_scope ON records(kind,chapter,section);')
            conn.executemany('INSERT INTO records VALUES(?,?,?,?,?)', [(r['id'], r['kind'], r['chapter'], r['section'], json.dumps(r, ensure_ascii=False)) for r in records])
            conn.executemany('INSERT INTO chunks VALUES(?,?,?,?,?,?,?,?)', [(c['id'], c['record_id'], c['text'], c['start'], c['end'], c['token_count'], c['content_sha256'], old[c['content_sha256']]) for c in all_chunks])
            conn.executemany('INSERT INTO metadata VALUES(?,?)', [(k, json.dumps(v, ensure_ascii=False)) for k,v in metadata.items()])
            if conn.execute('PRAGMA integrity_check').fetchone()[0] != 'ok': raise ValueError('Index integrity failure')
        staged.replace(DB)
        _snapshot.cache_clear()
        write_json(OUT / 'index-report.json', metadata)
        write_json(OUT / 'build-progress.json', {'status': 'ready_pending_content_review', 'records': len(records), 'chunks': len(all_chunks)})
        return metadata


@lru_cache(maxsize=2)
def _snapshot(path, stamp):
    import numpy as np
    with closing(connect(Path(path))) as conn:
        meta = {k: json.loads(v) for k,v in conn.execute('SELECT key,value FROM metadata')}
        records = {i: json.loads(d) for i,d in conn.execute('SELECT id,data FROM records')}
        rows = list(conn.execute('SELECT id,record_id,text,embedding FROM chunks ORDER BY rowid'))
    matrix = np.vstack([np.frombuffer(r[3], dtype=np.float32) for r in rows])
    docs = [r[2] for r in rows]; bags = [collections.Counter(tokens(d)) for d in docs]
    lengths = [sum(b.values()) for b in bags]
    df = collections.Counter(t for bag in bags for t in bag)
    return meta, records, rows, matrix, bags, lengths, df


def snapshot():
    return _snapshot(str(DB), DB.stat().st_mtime_ns)


def status():
    if not DB.exists(): return {'ready': False, 'reason': 'index_not_built'}
    meta = snapshot()[0]
    ready = meta.get('input_sha256') == input_signature()
    return {**meta, 'ready': ready, 'reason': None if ready else 'source_archive_changed_rebuild_required'}


def lexical(query, bags, lengths, df):
    n = len(bags); avg = sum(lengths) / max(n,1); terms = set(tokens(query))
    scores = []
    for bag, length in zip(bags, lengths):
        score = 0.
        for term in terms:
            tf = bag.get(term,0)
            if tf: score += math.log(1 + (n - df[term] + .5)/(df[term] + .5))*tf*2.2/(tf + 1.2*(.25 + .75*length/max(avg,1)))
        scores.append(score)
    return scores


def fuse(vector, lexical_scores, candidates, rows, mode='hybrid', limit=8):
    def aggregate(scores):
        result = {}
        for i in candidates:
            key = rows[i][1]
            if key not in result or scores[i] > result[key][0]: result[key] = (float(scores[i]), i)
        return result
    dense = aggregate(vector) if vector is not None else {}
    sparse = aggregate(lexical_scores)
    order = lambda values: sorted(values, key=lambda k: (-values[k][0], k))
    vr = {k:i+1 for i,k in enumerate(order(dense))}
    lr = {k:i+1 for i,k in enumerate(order(sparse)) if sparse[k][0] > 0}
    if mode == 'vector': rank = order(dense)
    elif mode == 'bm25': rank = [k for k in order(sparse) if sparse[k][0] > 0]
    else:
        # Fuse record ranks after max chunk aggregation: long records don't gain
        # multiple RRF votes merely because they have more chunks.
        keys = set(vr) | set(lr)
        rank = sorted(keys, key=lambda k: (-(1/(60+vr[k]) if k in vr else 0) -(1/(60+lr[k]) if k in lr else 0), k))
    result = []
    for key in rank[:limit]:
        matched = (sparse[key][1] if mode == 'bm25' or mode == 'hybrid' and key in lr and lr[key] < vr.get(key,10**9) else dense[key][1])
        result.append({'id': key, 'matched_chunk': rows[matched][0], 'matched_text': rows[matched][2],
                       'cosine': round(dense[key][0],6) if key in dense else None,
                       'bm25': round(sparse[key][0],6), 'vector_rank': vr.get(key), 'lexical_rank': lr.get(key),
                       'rrf': round((1/(60+vr[key]) if key in vr else 0)+(1/(60+lr[key]) if key in lr else 0),8) if mode=='hybrid' else None})
    return result


@lru_cache(maxsize=128)
def query_lexical(query_text,path,stamp):
    _,_,_,_,bags,lengths,df=_snapshot(path,stamp)
    return tuple(lexical(query_text,bags,lengths,df))


@lru_cache(maxsize=128)
def query_dense(query_text,path,stamp,model):
    import numpy as np
    matrix=_snapshot(path,stamp)[3]
    count,_=tokenizer_counter()
    parts=[query_text[a:b] for a,b,_ in intervals(query_text,'',count,CHUNK_CHARS,OVERLAP,MAX_TOKENS)]
    with LOCK:q=np.asarray(list(encoder().query_embed(parts)),dtype=np.float32)
    q/=np.maximum(np.linalg.norm(q,axis=1,keepdims=True),1e-12)
    scores=np.max(matrix@q.T,axis=1);scores.setflags(write=False)
    return scores,len(parts)


def search(query, mode='hybrid', kind='all', chapter='', section='', limit=8):
    import numpy as np
    if not isinstance(query, str) or not 3 <= len(query.strip()) <= 3000: raise ValueError('请输入3–3000字的题目或描述')
    if mode not in {'bm25','vector','hybrid'}: raise ValueError('未知检索方式')
    if kind not in {'all','exercise','example'}: raise ValueError('未知题目类型')
    if chapter and chapter not in {str(i) for i in range(1,9)}: raise ValueError('未知章节')
    from book_structure import structure
    if section and section not in {s['id'] for s in structure()['sections']}: raise ValueError('未知小节')
    if not status()['ready']: raise ValueError('题目向量库尚未就绪或来源已变化，请重新建库')
    started = time.monotonic(); meta, records, rows, matrix, bags, lengths, df = snapshot()
    allowed = {i for i,r in records.items() if (kind=='all' or r['kind']==kind) and (not chapter or r['chapter']==chapter) and (not section or r['section']==section)}
    candidates = [i for i,r in enumerate(rows) if r[1] in allowed]
    query_text = searchable_text(query.strip())
    if len(query_text) < 3: raise ValueError('请补充可识别的题目文字')
    index_key=(str(DB),DB.stat().st_mtime_ns)
    lexical_scores = query_lexical(query_text,*index_key)
    dense = None; query_chunk_count = 0
    if mode != 'bm25' and candidates:
        # Long queries are segmented as well; never rely on silent 512-token truncation.
        dense,query_chunk_count=query_dense(query_text,*index_key,MODEL)
    rank = fuse(dense, lexical_scores, candidates, rows, mode, max(1,min(int(limit),20))) if candidates else []
    hits = []
    for match in rank:
        r = records[match['id']]
        public = {k:v for k,v in r.items() if k not in {'full_text','search_text','block_ids','stem_review'}}
        # Give a cross-type reading path, not an unverified "same knowledge point" edge.
        links = [x for x in records.values() if x['section']==r['section'] and x['kind']!=r['kind']]
        link_ids = {x['id'] for x in links}
        link_chunks = [i for i,row in enumerate(rows) if row[1] in link_ids]
        link_ranks = fuse(dense,lexical_scores,link_chunks,rows,mode,3) if link_chunks else []
        public['nearby_other_type'] = [{'id':x['id'],'label':records[x['id']]['label'],'pages':records[x['id']]['pages']} for x in link_ranks]
        public['related_basis'] = 'same_section_then_query_retrieval_rank; unreviewed_candidate'
        hits.append({**public, **match})
    return {'query':query,'mode':mode,'hits':hits,'filtered_records':len(allowed),
            'query_chunks':query_chunk_count,'elapsed_seconds':round(time.monotonic()-started,3),
            'collection_sha256':meta['collection_sha256'],'model':MODEL,
            'review_status':'raw_ocr_pending_review','reference_answers_searched':False,
            'message':'相似题候选，分数不是正确率；同节阅读路径不代表相同考点。例题题干边界、OCR公式与数值待校对。'}


def record(identifier):
    if not status()['ready']: raise ValueError('向量库未就绪或已过期')
    r = snapshot()[1].get(identifier)
    if not r: raise ValueError('未找到题目')
    return {**r, 'full_text_role': 'original_example_with_explanation_or_exercise; not_embedding_input'}


if __name__ == '__main__': print(json.dumps(build(),ensure_ascii=False,indent=2))
