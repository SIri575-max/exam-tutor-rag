import datetime as dt
import json
import time
import uuid
from learning_engine import retrieve,guidance
from tutor_provider import answer,status
from sync_sources import ROOT


def learn(question,mode='adaptive',stage='hint',use_llm=False):
    started=time.monotonic();result=retrieve(question,mode)
    teaching=guidance(result,stage)
    provider=answer(result,stage) if use_llm else {'used':False,'status':'not_requested'}
    if provider['used']:teaching={'mode':'model_grounded_generation','text':provider['text'],'stage':stage,'llm_used':True,'usage':provider.get('usage',{})}
    result.update(teaching=teaching,provider=provider,provider_status=status())
    result['request_id']=uuid.uuid4().hex;result['total_seconds']=round(time.monotonic()-started,3)
    output=ROOT/'runs/requests';output.mkdir(parents=True,exist_ok=True)
    log={k:result.get(k) for k in ['request_id','question','mode','route','status','corpus_sha256','semantic','trace','total_seconds']}
    log.update(timestamp=dt.datetime.now(dt.timezone.utc).isoformat(),stage=stage,llm_used=provider['used'],provider_status=provider['status'])
    (output/(result['request_id']+'.json')).write_text(json.dumps(log,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return result
