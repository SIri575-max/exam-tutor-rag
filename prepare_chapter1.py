"""Prepare chapter 1 and its reference answers; reuse verified pilot image/OCR caches."""
import json
import shutil
from sync_sources import ROOT, fingerprint
from prepare_ocr_pilot import prepare


def build():
    pilot=ROOT/'data/private/ocr-pilot';base=ROOT/'data/private/chapter1'
    old=json.loads((pilot/'manifest.json').read_text(encoding='utf-8'))
    current=json.loads((ROOT/'data/private/textbook_registry/manifest.json').read_text(encoding='utf-8'))['files'][0]
    if old['source_sha256']!=current['sha256']:raise ValueError('Pilot belongs to a different textbook version; prepare a new pilot before reusing caches')
    pages=list(range(23,77))+list(range(469,473))
    (base/'pages').mkdir(parents=True,exist_ok=True);(base/'mineru-basic').mkdir(exist_ok=True)
    cached={}
    for row in old['pages']:
        if row['pdf_page'] not in pages:continue
        image=pilot/row['image']
        if fingerprint(image)!=row['image_sha256']:raise ValueError('Pilot image changed')
        target=base/row['image']
        if not target.exists():shutil.copy2(image,target)
        result=pilot/'mineru-basic'/f"pdf-{row['pdf_page']:03}.json"
        if result.exists():
            dest=base/'mineru-basic'/result.name
            if not dest.exists():shutil.copy2(result,dest)
            cached[result.name]={'input_image_sha256':row['image_sha256'],'output_sha256':fingerprint(dest),'package_pin':'4.0.12'}
    manifest=prepare(base,160,pages)
    manifest['chapter1_boundary']=old['chapter1_boundary']
    manifest['answer_boundary_note']='PDF472 includes the end of exercise1.5 answers and starts exercise2.1; segment at its heading, never treat whole page as chapter1 answers.'
    (base/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    cache_path=base/'ocr-cache.json'
    existing=json.loads(cache_path.read_text(encoding='utf-8')) if cache_path.exists() else {}
    existing.update(cached);cache_path.write_text(json.dumps(existing,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'pages':len(pages),'cached_pages':len(existing),'remaining':len(pages)-len(existing)}))


if __name__=='__main__':build()
