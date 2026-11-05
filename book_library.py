"""Read-only local navigation for the quarantined full-book OCR archive."""
from contextlib import closing
import json
import sqlite3
from pathlib import Path
from book_structure import structure
from process_full_book import BASE


def overview():
    result = {'structure': structure(), 'report': {}, 'progress': {}}
    for key, name in [('report', 'organization-report.json'), ('progress', 'progress.json')]:
        path = BASE / name
        if path.exists():
            result[key] = json.loads(path.read_text(encoding='utf-8'))
    return result


def connect():
    return sqlite3.connect((BASE / 'catalog.sqlite3').as_uri() + '?mode=ro', uri=True)


def get_page(number):
    if not 1 <= number <= 490:
        raise ValueError('页码应在1至490之间')
    with closing(connect()) as db:
        row = db.execute('SELECT data FROM pages WHERE pdf_page=?', (number,)).fetchone()
        if not row:
            raise ValueError('尚未整理此页')
        page = json.loads(row[0]); page.pop('markdown', None)
        page['blocks'] = []
        for (data,) in db.execute('SELECT data FROM blocks WHERE pdf_page=? ORDER BY rowid', (number,)):
            block = json.loads(data)
            if block.get('excluded_from_reading_view'):
                continue
            page['blocks'].append({key: block.get(key) for key in ('id', 'type', 'text', 'segments', 'bbox_normalized', 'section', 'subsection', 'exercise_id', 'unit_id')})
    return page


def search(query, region='all', limit=30):
    query = query.strip()
    if not 1 <= len(query) <= 120:
        raise ValueError('请输入1至120字的关键词')
    regions = {r['id'] for r in structure()['regions']}
    if region not in regions | {'all'}:
        raise ValueError('无效资料范围')
    terms = query.split()[:8]
    # Literal, parameterized substring search also supports 1–2 Chinese characters.
    # A literal query containing SQL/FTS operators must not execute as an expression.
    clauses = []; params = []
    for term in terms:
        clauses.append("text LIKE ? ESCAPE '\\'")
        params.append('%' + term.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%')
    if region != 'all':
        clauses.append('region=?'); params.append(region)
    else:
        clauses.append("region!='answers'")
    params.append(max(1, min(int(limit), 50)))
    with closing(connect()) as db:
        rows = db.execute('SELECT pdf_page,region,chapter,status,text FROM pages WHERE ' + ' AND '.join(clauses) + ' ORDER BY pdf_page LIMIT ?', params).fetchall()
    hits = []
    for page, channel, chapter, status, text in rows:
        position = text.find(terms[0]); position = max(0, position - 85)
        hits.append({'pdf_page': page, 'region': channel, 'chapter': chapter, 'status': status,
                     'snippet': text[position:position + 420]})
    return {'query': query, 'hits': hits, 'answers_hidden_by_default': region == 'all',
            'review_status': 'raw_ocr_pending_review'}


def objects(kind='exercise', section='', limit=50, offset=0):
    if kind not in {'exercise', 'reference_answer', 'definition', 'theorem', 'property', 'example', 'corollary', 'lemma', 'proposition'}:
        raise ValueError('无效条目类型')
    args = [kind]; where = 'kind=?'
    if section:
        if section not in {s['id'] for s in structure()['sections']}:
            raise ValueError('无效章节')
        where += ' AND section=?'; args.append(section)
    with closing(connect()) as db:
        total = db.execute('SELECT COUNT(*) FROM objects WHERE ' + where, args).fetchone()[0]
        rows = db.execute('SELECT data FROM objects WHERE ' + where + ' ORDER BY rowid LIMIT ? OFFSET ?',
                          args + [max(1, min(int(limit), 100)), max(0, int(offset))]).fetchall()
    return {'total': total, 'items': [json.loads(row[0]) for row in rows], 'review_status': 'raw_ocr_pending_review'}


HTML = r'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>茆书 · 全书资料库</title>
<link rel="stylesheet" href="/assets/katex/katex.min.css"><link rel="stylesheet" href="/math-render.css"><script src="/assets/katex/katex.min.js"></script><script src="/math-render.js"></script>
<style>
:root{--ink:#203a46;--green:#17675d;--muted:#6b7d84;--line:#dce5e6;--bg:#f4f7f6}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.8 "Segoe UI","Microsoft YaHei",sans-serif}a{color:var(--green);text-decoration:none}header{padding:20px 32px;background:white;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;gap:15px;flex-wrap:wrap}main{max-width:1600px;margin:auto;padding:25px;display:grid;grid-template-columns:265px minmax(0,1fr);gap:24px}h1{font-size:29px;margin:6px 0}h2{font-size:20px}h3{font-size:16px}.label,.muted{font-size:12px;color:var(--muted)}.badge{background:#e8f2ef;border-radius:18px;padding:4px 12px;color:var(--green);font-size:12px}.notice{border-left:3px solid #c3a34a;background:#fff9e8;color:#7e6831;padding:10px 14px;font-size:13px}.card{background:white;border:1px solid var(--line);border-radius:12px;padding:20px;margin-bottom:16px}button,select,input{font:inherit;border:1px solid #cbd8da;border-radius:7px;background:white;padding:7px 11px;color:var(--ink)}button{cursor:pointer}button:hover{border-color:var(--green)}.primary{background:var(--green);color:white}.row{display:flex;gap:9px;align-items:center;flex-wrap:wrap}.toc details{border-bottom:1px solid var(--line);padding:9px 0}.toc summary{cursor:pointer;font-weight:600}.toc button{display:block;width:100%;text-align:left;border:0;padding:5px 8px;font-size:13px}.toc .sub{padding-left:16px;color:var(--muted);font-size:12px}#query{flex:1;min-width:160px}#page-number{width:90px}.reading{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:18px;align-items:start}.prose{white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.95}.block{padding:8px 0;border-bottom:1px solid #eef2f2}.block:target{background:#fff5ce}.block small{font-size:10px;color:#81928e}.formula{background:#f3f6f7;padding:12px;font:13px/1.8 Consolas,monospace;white-space:pre-wrap;overflow-wrap:anywhere}.table-scroll{overflow:auto}table{border-collapse:collapse;font-size:12px;white-space:normal}td,th{border:1px solid #dce5e6;padding:5px 9px;min-width:45px}.source{position:sticky;top:12px}.source img{display:block;width:100%;border:1px solid var(--line)}.result{padding:12px 0;border-bottom:1px solid var(--line)}.result button{color:var(--green);border:0;background:#edf5f2}#error{color:#a63434}.selected{background:#e7f1ed!important}aside{max-height:85vh;overflow:auto;position:sticky;top:16px}.object{padding:12px 0;border-bottom:1px solid var(--line)}.object summary{cursor:pointer}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}dialog{width:92vw;max-width:1450px;max-height:94vh;border:1px solid var(--line);border-radius:12px}dialog img{width:100%}dialog::backdrop{background:#163742aa}@media(max-width:1100px){.reading{grid-template-columns:1fr}.source{position:static}}@media(max-width:750px){main{display:block;padding:15px}aside{position:static;max-height:250px;margin-bottom:20px}header{padding:15px}h1{font-size:24px}}
</style>
<header><strong>茆书 / 全书资料库</strong><div class="row"><a href="/problems">课后题与例题检索</a><a href="/">题目与考点辅导</a><a href="/pilot">第一章核对</a><span class="badge">本机私有资料</span></div></header>
<main><aside class="card toc"><div class="label">CONTENTS / 全书目录</div><div id="toc"></div></aside><div>
<div class="label">概率论与数理统计教程 · 第三版</div><h1>全书阅读、检索与原页核对</h1><p class="muted" id="coverage">正在读取整理状态…</p><p class="notice">自动识别稿：公式、表格数值、题目边界及答案关联待校对。所有页面保留原图，学习与引用时可随时回看。</p>
<section class="card"><div class="row"><input id="query" placeholder="搜索全书，例如：最大似然估计"><select id="region"><option value="all">正文及附表等（隐藏答案）</option><option value="body">正文与习题</option><option value="appendix">附表</option><option value="answers">参考答案</option><option value="front">前言与目录</option><option value="references">参考文献</option></select><button class="primary" id="search">搜索</button></div><div id="results"></div></section>
<section class="card"><div class="row"><button id="previous">上一页</button><label>PDF页 <input id="page-number" type="number" min="1" max="490" value="23"></label><button id="jump">跳转</button><button id="next">下一页</button><button id="zoom">放大原页</button><a href="/library-export/book.md" download="茆书全书识别稿.md">下载全书 Markdown</a></div><p class="muted" id="page-info"></p><div id="error" role="alert"></div><div class="reading"><article id="text" class="prose"></article><div class="source"><img id="source" alt="教材原始页图"><p class="muted">左侧为OCR；原图保留图形、公式和版式。</p></div></div></section>
<section class="card"><h2>按类型查看整理条目</h2><div class="row"><select id="kind"><option value="exercise">课后题候选</option><option value="example">例题候选</option><option value="definition">定义候选</option><option value="theorem">定理候选</option><option value="property">性质候选</option><option value="reference_answer">参考答案候选</option></select><select id="section"><option value="">全书</option></select><button id="show-objects">查看</button></div><p class="muted" id="object-count"></p><div id="objects"></div><div class="row"><button id="objects-prev">上一组</button><button id="objects-next">下一组</button></div></section>
</div></main><dialog id="viewer"><button id="close">关闭</button><img id="large-source" alt="放大的教材原页"></dialog>
<script>
const $=id=>document.getElementById(id),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));let page=23,offset=0,total=0,request=0;
function safeTable(value){return MathView.table(value);}
function renderSegments(value,type){return MathView.segments(value,type);}

async function api(url){const r=await fetch(url);const d=await r.json();if(!r.ok)throw Error(d.error||'请求失败');return MathView.register(d);}
async function openPage(n){const token=++request;try{const d=await api('/api/library/page?n='+n);if(token!==request)return;page=n;$('page-number').value=n;history.replaceState(null,'','#page='+n);$('source').src='/book-page/'+n+'.png';$('large-source').src=$('source').src;$('page-info').textContent='PDF第'+n+'页 · '+(d.printed_page_verified?'印刷第'+d.printed_page_verified+'页（已核对页码）':d.printed_page_candidate?'印刷页候选 '+d.printed_page_candidate:'书前页')+' · '+(d.ocr_status==='complete_unreviewed'?'已识别，待校对':'尚未识别');$('text').innerHTML=d.blocks.length?d.blocks.map(b=>'<div class="block '+(b.type==='equation'?'formula':'')+'" id="'+esc(b.id)+'">'+(['paragraph_title','doc_title'].includes(b.type)?'<h3>'+MathView.prose(b.text)+'</h3>':(b.segments && (typeof b.segments==='string' || b.segments.length || typeof b.segments==='object' && !Array.isArray(b.segments))?renderSegments(b.segments,b.type):MathView.prose(b.text||'图像区域，请看右侧原页')))+'<br><small>'+esc(b.subsection||b.section||'')+' · '+esc(({manual_transcription:'对照原页补录',equation:'公式识别稿',table:'表格识别稿',image:'图像区域'})[b.type]||'')+'</small></div>').join(''):(d.page_visual_status==='blank_visually_checked'?'原书空白页（助手已对照原图）。':'本页没有可显示的识别文字，请核对原图。');$('error').textContent='';}catch(e){$('error').textContent=e.message;}}
async function search(){try{const d=await api('/api/library/search?q='+encodeURIComponent($('query').value)+'&region='+$('region').value);$('results').innerHTML='<p class="muted">'+d.hits.length+'个匹配页（最多显示30页）</p>'+d.hits.map(h=>'<div class="result"><button data-page="'+h.pdf_page+'">PDF第'+h.pdf_page+'页</button><p>'+MathView.prose(h.snippet)+'</p></div>').join('');}catch(e){$('error').textContent=e.message;}}
function objectProse(text){return MathView.prose(text);}

async function showObjects(){try{const d=await api('/api/library/objects?kind='+$('kind').value+'&section='+$('section').value+'&offset='+offset);total=d.total;$('object-count').textContent=total+'条候选；当前'+(total?offset+1:0)+'–'+Math.min(offset+50,total)+'。自动边界与关联待核对。';$('objects').innerHTML=d.items.map(x=>'<details class="object"><summary>'+esc(x.source_number||x.section+' · 第'+x.number+'题')+' · PDF '+x.pages.join('、')+(x.reading_order_warning?' · OCR阅读顺序待校对':'')+'</summary><div class="prose">'+objectProse(x.text)+'</div>'+x.pages.map(n=>'<button data-page="'+n+'">原页 '+n+'</button>').join(' ')+'</details>').join('');}catch(e){$('error').textContent=e.message;}}
$('search').onclick=search;$('query').onkeydown=e=>{if(e.key==='Enter')search()};$('jump').onclick=()=>openPage(Number($('page-number').value));$('previous').onclick=()=>openPage(Math.max(1,page-1));$('next').onclick=()=>openPage(Math.min(490,page+1));$('zoom').onclick=()=>$('viewer').showModal();$('close').onclick=()=>$('viewer').close();$('show-objects').onclick=()=>{offset=0;showObjects()};$('objects-prev').onclick=()=>{offset=Math.max(0,offset-50);showObjects()};$('objects-next').onclick=()=>{if(offset+50<total){offset+=50;showObjects()}};
document.addEventListener('click',e=>{const b=e.target.closest('[data-page]');if(b){openPage(Number(b.dataset.page));$('page-number').scrollIntoView({behavior:'smooth',block:'center'})}});
api('/api/library').then(d=>{const r=d.report,p=d.progress,s=d.structure;$('coverage').textContent='原书490页 · 已识别 '+(p.completed_pages||0)+'页 · 已整理 '+(r.pages_with_valid_ocr||0)+'页 · '+s.chapters.length+'章 / '+s.sections.length+'节 / '+s.subsections.length+'个小节 · '+(r.unique_exercise_ids||0)+'道题目候选';$('toc').innerHTML=s.chapters.map(c=>'<details><summary>第'+c.id+'章 '+esc(c.title)+'</summary>'+s.sections.filter(x=>x.chapter===c.id).map(x=>'<button data-page="'+x.pdf_first+'">'+x.id+' '+esc(x.title)+'</button>'+s.subsections.filter(y=>y.id.startsWith(x.id+'.')).map(y=>'<button class="sub" data-page="'+y.pdf_first+'">'+y.id+' '+esc(y.title)+'</button>').join('')).join('')+'</details>').join('')+s.regions.filter(x=>x.id!=='body').map(x=>'<button data-page="'+x.pdf_first+'">'+esc(x.title)+'</button>').join('');$('section').innerHTML+='<optgroup label="各节">'+s.sections.map(x=>'<option value="'+x.id+'">'+x.id+' '+esc(x.title)+'</option>').join('')+'</optgroup>';const n=Number(new URLSearchParams(location.hash.slice(1)).get('page'));openPage(n>=1&&n<=490?n:23);showObjects();}).catch(e=>$('error').textContent=e.message);
</script></html>'''
