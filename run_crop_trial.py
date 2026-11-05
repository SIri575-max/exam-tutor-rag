"""Small local high-resolution crop experiment; retains source boxes and raw OCR."""
import json
import os
import subprocess
import time
from pathlib import Path
from PIL import Image,ImageOps
from sync_sources import ROOT,fingerprint,poppler_tool


def run():
    base=ROOT/'data/private/crop-trial';base.mkdir(exist_ok=True)
    source=json.loads((ROOT/'data/private/textbook_registry/manifest.json').read_text(encoding='utf-8'))['files'][0]
    if fingerprint(Path(source['path']))!=source['sha256']:raise ValueError('Source changed')
    specs=[('conditional-complement',60,[.25,.182,.86,.210]),('conditional-union',60,[.25,.210,.86,.239]),
           ('interval-complement',32,[.177,.509,.28,.541]),('extra-subscript',32,[.18,.429,.31,.458])]
    poppler=str(poppler_tool('pdftoppm'))
    inputs=[];records=[]
    for name,page,box in specs:
        full=base/f'full-{page}.png'
        if not full.exists():subprocess.run([poppler,'-f',str(page),'-l',str(page),'-r','320','-singlefile','-png',source['path'],str(full.with_suffix(''))],check=True,capture_output=True)
        with Image.open(full) as image:
            crop=image.crop(tuple(int(x*y) for x,y in zip(box,[image.width,image.height,image.width,image.height])))
            target=base/(name+'.png');ImageOps.expand(crop,border=100,fill='white').save(target)
        inputs.append(str(target));records.append({'case':name,'pdf_page':page,'bbox_normalized':box,'dpi':320,'image_sha256':fingerprint(target),'source_sha256':source['sha256']})
    env=os.environ.copy();env.update(MINERU_HOME=str(ROOT/'data/private/ocr-pilot/mineru-home'),MINERU_MODEL_SMALL_BACKEND='onnx',MINERU_INTRA_OP_NUM_THREADS='2',HF_HUB_DISABLE_XET='1')
    command=[str(ROOT/'.venv-ocr/Scripts/mineru-kit.exe'),'parse',*inputs,'-o',str(base/'output'),'--format','middle_json','--tier','basic','--ocr-mode','ocr','--disable-image-analysis']
    started=time.monotonic()
    with (base/'run.log').open('wb') as log:result=subprocess.run(command,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=600)
    report={'cases':records,'returncode':result.returncode,'elapsed_seconds':round(time.monotonic()-started,2),'remote_parsing':False,'boundary':'Four targeted cases only; not full-book OCR accuracy.'}
    (base/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(report,ensure_ascii=False));return report


if __name__=='__main__':run()
