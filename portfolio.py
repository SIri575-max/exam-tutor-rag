"""Read-only local portfolio snapshots, with measured development results."""
import json
from pathlib import Path
from exercise_vectors import status as index_status
from tutor_provider import status as model_status
from sync_sources import ROOT
import generation_records

RELEASE=ROOT/'data/private/v1.1-release/manifest.json'


def manifest():
    return json.loads(RELEASE.read_text(encoding='utf-8')) if RELEASE.exists() else {'status':'building','evaluation':None}


def comparison():
    relative=manifest().get('comparison_report')
    if not relative:raise ValueError('真实生成对照仍在准备中')
    path=(ROOT/relative).resolve()
    if not path.is_relative_to((ROOT/'data/private/generation-evaluation').resolve()) or path.name!='comparison.json':
        raise ValueError('无效评测来源')
    return json.loads(path.read_text(encoding='utf-8'))


def snapshot():
    index=index_status();release=manifest()
    return {'release':{k:release.get(k) for k in ['version','date','status','checks','evaluation','tests','boundaries']},
            'index':{k:index.get(k) for k in ['ready','records','kinds','chunks','dimensions','model','collection_sha256']},
            'model':model_status(),'generation_runs':generation_records.recent(),
            'retrieval_development':release.get('retrieval_development'),
            'boundary':'本机作品集初版；工程检查、模型响应与教师审核分别记录。'}
