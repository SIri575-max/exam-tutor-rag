"""Private, replayable model runs. No credentials or fabricated human ratings."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import uuid
from sync_sources import ROOT

OUT=ROOT/'data/private/generation-records'


def save(question,stage,result,elapsed):
    identifier=uuid.uuid4().hex
    data={'schema_version':1,'id':identifier,
          'created_at':datetime.now(timezone(timedelta(hours=8))).isoformat(),
          'question':question,'stage':stage,'elapsed_seconds':round(elapsed,3),
          **{k:result.get(k) for k in ['teaching','evidence','route','clarifications','retrieval_trace','collection_sha256']},
          'human_review':{'status':'pending','mathematical_correctness':None,'citation_support':None},
          'boundary':'Real application response; reference IDs do not prove correctness or citation entailment.'}
    OUT.mkdir(parents=True,exist_ok=True)
    target=OUT/(identifier+'.json');temporary=OUT/(identifier+'.tmp')
    temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    temporary.replace(target)
    return identifier


def get(identifier):
    if not isinstance(identifier,str) or not re.fullmatch('[a-f0-9]{32}',identifier):raise ValueError('无效讲解记录编号')
    try:return json.loads((OUT/(identifier+'.json')).read_text(encoding='utf-8'))
    except FileNotFoundError as exc:raise ValueError('未找到讲解记录') from exc


def recent(limit=10):
    rows=[]
    if not OUT.exists():return rows
    for path in sorted(OUT.glob('*.json'),key=lambda p:p.stat().st_mtime,reverse=True)[:limit]:
        try:
            data=get(path.stem);teaching=data.get('teaching') or {}
            rows.append({k:data.get(k) for k in ['id','created_at','question','stage','elapsed_seconds']}
                        |{k:teaching.get(k) for k in ['status','model','live_call_verified','citation_ids','usage']})
        except (ValueError,OSError):continue
    return rows
