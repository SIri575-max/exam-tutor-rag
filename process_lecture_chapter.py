"""Checkpointed, bounded local lecture OCR using the existing pinned parser."""
import argparse
import concurrent.futures
import datetime as dt
import json
import time
from lecture_pipeline import ROOT, source_for, normalize
from process_full_book import parse_batch, valid_cache, write_json, PIN
from sync_sources import fingerprint


def run(chapter='6',workers=2,batch_size=6):
    source=source_for(chapter)
    if workers not in (1,2) or not 1<=batch_size<=12:raise ValueError('workers=1/2, batch_size=1..12')
    base=ROOT/'data/private/lecture-ocr'/('chapter'+chapter)
    manifest=json.loads((base/'manifest.json').read_text(encoding='utf-8'))
    if source['sha256']!=manifest['source_sha256']:raise ValueError('讲义来源已过期')
    for name in ('logs','mineru-basic'):(base/name).mkdir(exist_ok=True)
    cache_path=base/'ocr-cache.json'
    cache=json.loads(cache_path.read_text(encoding='utf-8')) if cache_path.exists() else {}
    rows={r['pdf_page']:r for r in manifest['pages']}
    start=time.monotonic();results=[]
    progress={'chapter':chapter,'source_sha256':source['sha256'],'total_pages':len(rows),
              'started_at':dt.datetime.now().astimezone().isoformat(),'status':'running',
              'remote_parsing':False,'answer_approval':False,'workers':workers}

    def checkpoint():
        complete=[p for p,r in rows.items() if valid_cache(base,r,cache)]
        progress.update(completed_pages=len(complete),completed_pdf_pages=complete,
                        remaining_pdf_pages=[p for p in rows if p not in complete],
                        elapsed_seconds=round(time.monotonic()-start,2),batches=results,
                        updated_at=dt.datetime.now().astimezone().isoformat())
        write_json(cache_path,cache);write_json(base/'progress.json',progress)
        normalize(chapter)
        print(json.dumps({k:progress[k] for k in ('status','completed_pages','total_pages','elapsed_seconds')}),flush=True)

    def collect(result):
        results.append(result)
        for page in result['pages']:
            row=rows[page];name=f'pdf-{page:03}.json';path=base/'mineru-basic'/name
            if not path.exists():continue
            entry={'input_image_sha256':row['image_sha256'],'output_sha256':fingerprint(path),'package_pin':PIN}
            if valid_cache(base,row,{name:entry}):cache[name]=entry
        checkpoint()

    checkpoint()
    pending=[r for r in rows.values() if not valid_cache(base,r,cache)]
    batches=[pending[n:n+batch_size] for n in range(0,len(pending),batch_size)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures=[executor.submit(parse_batch,batch,1,base) for batch in batches]
        for future in concurrent.futures.as_completed(futures):collect(future.result())
    for attempt in (2,3):
        unresolved=[r for r in rows.values() if not valid_cache(base,r,cache)]
        if not unresolved:break
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            futures=[executor.submit(parse_batch,[row],attempt,base) for row in unresolved]
            for future in concurrent.futures.as_completed(futures):collect(future.result())
    progress['status']='complete_unreviewed' if all(valid_cache(base,r,cache) for r in rows.values()) else 'incomplete_with_errors'
    checkpoint();return progress


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--chapter',default='6')
    p.add_argument('--workers',type=int,choices=(1,2),default=2);p.add_argument('--batch-size',type=int,default=6)
    args=p.parse_args();result=run(args.chapter,args.workers,args.batch_size)
    raise SystemExit(0 if result['status']=='complete_unreviewed' else 1)
