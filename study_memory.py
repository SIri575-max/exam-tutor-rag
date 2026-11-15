"""Learner-scoped episodes with local BGE vectors and exact cosine retrieval."""
from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

from retrieval import ROOT
from vector_index import encoder, LOCK, MODEL


DB = ROOT / 'data/private/agent/episodes.sqlite3'


def embedding(text, query=False):
    import numpy as np
    with LOCK:
        model = encoder()
        vectors = model.query_embed([text[:900]]) if query else model.embed([text[:900]])
        vector = np.asarray(next(iter(vectors)), dtype=np.float32)
    vector /= max(float(np.linalg.norm(vector)), 1e-12)
    return vector


def connect(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=15)
    connection.execute('''CREATE TABLE IF NOT EXISTS episodes(
        task_id TEXT PRIMARY KEY, learner_id TEXT NOT NULL, created_at TEXT NOT NULL,
        question TEXT NOT NULL, summary TEXT NOT NULL, metadata TEXT NOT NULL,
        embedding BLOB NOT NULL, model TEXT NOT NULL)''')
    connection.execute('CREATE INDEX IF NOT EXISTS episode_learner ON episodes(learner_id, created_at)')
    return connection


def save(task_id, learner_id, question, summary, metadata, path=DB):
    vector = embedding(question + '\n' + summary)
    with closing(connect(path)) as connection, connection:
        connection.execute('INSERT OR REPLACE INTO episodes VALUES(?,?,?,?,?,?,?,?)', (
            task_id, learner_id, datetime.now(timezone.utc).isoformat(),
            question, summary, json.dumps(metadata, ensure_ascii=False), vector.tobytes(), MODEL))


def recall(learner_id, query, exclude_task='', path=DB):
    import numpy as np
    with closing(connect(path)) as connection:
        rows = connection.execute(
            'SELECT task_id,created_at,question,summary,metadata,embedding FROM episodes '
            'WHERE learner_id=? AND task_id!=? AND model=? ORDER BY created_at DESC LIMIT 100',
            (learner_id, exclude_task, MODEL)).fetchall()
    if not rows:
        return []
    vector = embedding(query, query=True)
    matches = []
    now = datetime.now(timezone.utc)
    for task, timestamp, question, summary, metadata, blob in rows:
        stored = np.frombuffer(blob, dtype=np.float32)
        if stored.shape != vector.shape:
            continue
        similarity = float(stored @ vector)
        days = max(0., (now - datetime.fromisoformat(timestamp)).total_seconds() / 86400)
        score = .85 * similarity + .15 / (1 + days)
        matches.append({'task_id': task, 'created_at': timestamp, 'question': question,
                        'summary': summary, 'metadata': json.loads(metadata),
                        'similarity': round(similarity, 4), 'rank_score': round(score, 4)})
    return sorted(matches, key=lambda row: -row['rank_score'])[:3]
