"""Read-only local side-by-side review of source images, OCR output and reference checks."""
import json
from pathlib import Path
from sync_sources import ROOT
from audit_ocr_pilot import content_strings

BASE = ROOT / 'data/private/ocr-pilot'


def summary():
    path = BASE / 'manifest.json'
    if not path.exists():
        return {'pages': [], 'status': 'pilot_not_prepared'}
    manifest = json.loads(path.read_text(encoding='utf-8'))
    def lines(name):
        p = BASE / name
        return [json.loads(line) for line in p.read_text(encoding='utf-8').splitlines() if line.strip()] if p.exists() else []
    formulas = lines('formula-reference.jsonl')
    questions = lines('question-checklist.jsonl')
    pages = []
    for row in manifest['pages']:
        page = row['pdf_page']
        outputs = sorted((BASE / 'mineru-basic').rglob(f'pdf-{page:03}.json')) if (BASE / 'mineru-basic').exists() else []
        raw = outputs[0].read_text(encoding='utf-8') if outputs else ''
        pages.append({**row, 'ocr_output_present': bool(outputs),
                      'ocr_json': raw[:150000],
                      'ocr_text': '\n'.join(content_strings(json.loads(raw))) if raw else '',
                      'formula_checks': [x for x in formulas if x['pdf_page'] == page],
                      'question_checks': [x for x in questions if x['pdf_page'] == page]})
    runs = [json.loads(p.read_text(encoding='utf-8')) for p in sorted(BASE.glob('run-*.json'))]
    return {'pages': pages, 'runs': runs, 'status': 'unreviewed_not_searchable',
            'formula_reference_count': len(formulas), 'question_check_count': len(questions)}


def page_image(page):
    manifest = json.loads((BASE / 'manifest.json').read_text(encoding='utf-8'))
    row = next((r for r in manifest['pages'] if r['pdf_page'] == page), None)
    if row is None:
        raise ValueError('Page not in the pilot')
    target = (BASE / row['image']).resolve()
    if not target.is_relative_to((BASE / 'pages').resolve()):
        raise ValueError('Invalid pilot image')
    return target.read_bytes()


HTML = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>教材 OCR 样页核对</title>
<style>body{font:15px/1.7 "Microsoft YaHei",sans-serif;background:#f3f5f8;color:#22314a;margin:0}main{margin:24px auto;max-width:1600px;padding:0 24px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:20px}.box{background:white;padding:18px;border:1px solid #dce1e9;border-radius:12px}img{width:100%;height:auto}select,button{font:inherit;padding:8px;margin:10px 8px 15px 0}pre{white-space:pre-wrap;word-break:break-word;max-height:900px;overflow:auto}small{color:#6b778a}.check{padding:10px 0;border-bottom:1px solid #e5e7eb}@media(max-width:850px){.grid{grid-template-columns:1fr}}</style>
<main><a href="/">返回题目检索</a><h1>教材 OCR 样页核对</h1><p>原页、OCR 原始输出与助手核对参考并排展示。识别完成不代表校对通过；参考转写也待人工复核。</p><select id="pages"></select><button id="reload">刷新识别进度</button><small id="status"></small>
<div class="grid"><section class="box"><h2 id="title">原始页面</h2><img id="source" alt="教材原页"></section><section class="box"><h2>公式与题目核对项</h2><div id="checks"></div><h2>OCR 转写（待校对）</h2><pre id="ocr"></pre><details><summary>查看解析结构（开发核对）</summary><pre id="raw"></pre></details></section></div></main>
<script>let data;const el=id=>document.getElementById(id);function show(){const p=data.pages.find(p=>p.pdf_page===Number(el('pages').value));if(!p)return;el('title').textContent='PDF第'+p.pdf_page+'页 · 印刷页候选 '+p.printed_page_candidate;el('source').src='/pilot-page/'+p.pdf_page+'.png';el('ocr').textContent=p.ocr_text||'本页尚无OCR结果。';el('raw').textContent=p.ocr_json||'';el('checks').replaceChildren();for(const c of [...p.formula_checks,...p.question_checks]){const d=document.createElement('div');d.className='check';d.textContent=(c.id||'')+'：'+(c.expected_latex||c.topic)+'；核对：'+c.critical_conditions;el('checks').append(d);}if(!el('checks').children.length)el('checks').textContent='核对页码、节标题、跨页边界及图文完整性。';}async function load(){const previous=el('pages').value;const r=await fetch('/api/pilot');if(!r.ok)throw Error('无法读取样页');data=await r.json();el('pages').replaceChildren();for(const p of data.pages){const o=document.createElement('option');o.value=p.pdf_page;o.textContent='PDF '+p.pdf_page+' / 候选印刷页 '+p.printed_page_candidate+(p.ocr_output_present?' · 有OCR输出':' · 待识别');el('pages').append(o);}if(data.pages.some(p=>String(p.pdf_page)===previous))el('pages').value=previous;el('status').textContent=data.pages.filter(p=>p.ocr_output_present).length+'/'+data.pages.length+'页有输出；'+data.formula_reference_count+'项公式 / '+data.question_check_count+'道题待核对';show();}el('pages').onchange=show;el('reload').onclick=()=>load().catch(e=>el('status').textContent=e.message);load().catch(e=>el('status').textContent=e.message);</script></html>'''
