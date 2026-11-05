"""Promote the measured local candidate; preserve old index and benchmark files."""
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import exercise_vectors as vectors

ROOT=Path(__file__).resolve().parent
BASE=ROOT/'data/private/chunk-topk-20261105'


def run():
    baseline_path=BASE/'baseline-104012/report.json'
    measured_path=BASE/'candidate-113902/report.json'
    inspection_path=BASE/'accepted-inspection/index-and-boundary-inspection.json'
    before=json.loads(baseline_path.read_text(encoding='utf-8'))
    after=json.loads(measured_path.read_text(encoding='utf-8'))
    inspection=json.loads(inspection_path.read_text(encoding='utf-8'))
    candidate=BASE/'final-index/vectors.sqlite3'
    digest=hashlib.sha256(candidate.read_bytes()).hexdigest()
    assert digest==after['index_sha256']==inspection['database_sha256']
    assert before['dataset_sha256']==after['dataset_sha256']
    assert before['index_metadata']['collection_sha256']==after['index_metadata']['collection_sha256']
    assert inspection['all_parent_text_covered'] and not inspection['protected_unit_boundary_risks']
    assert inspection['actual_ranges']['token_counts'][1]<=vectors.MAX_TOKENS
    assert all('protected_unit_split_for_token_budget' not in c['boundary_flags'] for c in inspection['chunk_boundary_warnings'])
    for key in ['exercise_vectors.py','formula_chunking.py','full_book_tutor.py','retrieval_policy.py']:
        assert hashlib.sha256((ROOT/key).read_bytes()).hexdigest()==after['code_sha256'][key],key
    old={r['case_id']:r for r in before['details']['correspondence']}
    for row in after['details']['correspondence']:
        prev=old[row['case_id']]
        for k in [1,3]:
            if prev['source_id'] in prev['returned_ids'][:k]:
                assert row['source_id'] in row['returned_ids'][:k],(row['case_id'],k)
    assert hashlib.sha256(vectors.DB.read_bytes()).hexdigest()==before['index_sha256'],'Live index changed since baseline'
    backup=BASE/'pre-promotion';backup.mkdir(exist_ok=False)
    for name in ['vectors.sqlite3','index-report.json','build-progress.json']:
        source=vectors.OUT/name
        if source.exists():shutil.copy2(source,backup/name)
    staged=vectors.OUT/'vectors.promoting.sqlite3';shutil.copy2(candidate,staged)
    with sqlite3.connect(staged) as conn:
        assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    conn.close()
    staged.replace(vectors.DB)
    for name in ['index-report.json','build-progress.json']:
        shutil.copy2(candidate.parent/name,vectors.OUT/name)
    result={'date':'2026-11-05','promoted_at':datetime.now(timezone(timedelta(hours=8))).isoformat(),
            'old_index_sha256':before['index_sha256'],'new_index_sha256':digest,
            'baseline':str(baseline_path.relative_to(ROOT)),'accepted_measurement':str(measured_path.relative_to(ROOT)),
            'inspection':str(inspection_path.relative_to(ROOT)),
            'records':inspection['records'],'chunks':inspection['chunks'],
            'teacher_relevance_verified':False,'generation_api_calls':0,
            'boundary':'Development source proxy does not regress on previous Top1/Top3 hits. New relevance or generation accuracy is not established.'}
    (BASE/'promotion.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':run()
