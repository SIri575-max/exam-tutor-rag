"""Read a locally pinned, aggregate matching experiment; no model calls."""
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
BASE=ROOT/'data/private/correspondence-study-20261104'


def snapshot():
    pointer=json.loads((BASE/'latest.json').read_text(encoding='utf-8'))
    target=(BASE/pointer['report']).resolve()
    if not target.is_relative_to(BASE.resolve()) or target.name!='comparison.json':raise ValueError('Invalid result pointer')
    raw=target.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=pointer['sha256']:raise ValueError('Experiment snapshot changed')
    result=json.loads(raw)
    result['code_current']=all(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==sha
                               for name,sha in result['implementation_sha256'].items())
    return result


def review_template():
    value=snapshot()
    path=(BASE/value['review_template']).resolve()
    if not path.is_relative_to(BASE.resolve()) or path.name!='human-review-template.json':raise ValueError('Invalid review file')
    return json.loads(path.read_text(encoding='utf-8'))
