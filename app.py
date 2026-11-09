"""Private local demonstration of exercise-to-concept navigation."""
import argparse
import json
import mimetypes
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse,parse_qs
from retrieval import ROOT,corpus,retrieve
import pilot_review
from learning_ui import HTML as LEARNING_HTML
from course_data import load as load_course
from tutoring import learn
import feedback
import book_library
import exercise_vectors
import full_book_tutor
import question_knowledge
import problem_feedback
from problem_search_ui import HTML as PROBLEM_SEARCH_HTML
from math_presentation import present
import validation_review
import syllabus_plan_ui
import rag_generation
import lecture_library
import worked_notes
import photo_ocr
import photo_notebook
import generation_records
import portfolio
import external_review
import external_materials
import matching_evaluation
import study_agent

HTML='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>茆书专业课辅导 · 题目知识图谱</title>
<style>body{font:15px/1.8 "Segoe UI","Microsoft YaHei",sans-serif;background:#f3f5f8;color:#22314a;margin:0}main{max-width:1120px;margin:45px auto;padding:0 24px}h1{font-size:30px;margin-bottom:10px}.sub{color:#718096}textarea{box-sizing:border-box;width:100%;padding:17px;border:1px solid #d5dce5;border-radius:12px;font:inherit;min-height:115px}button,select{font:inherit;border:1px solid #d5dce5;border-radius:7px;padding:9px 15px;background:white;cursor:pointer}button.primary{background:#214b82;color:white;border:0}.row{display:flex;align-items:center;gap:12px;margin:15px 0;flex-wrap:wrap}.panel{background:white;border:1px solid #e1e6ed;border-radius:13px;padding:23px;margin:19px 0}.pill{display:inline-block;background:#edf2fa;color:#32588a;border:1px solid #d7e1f0;padding:4px 12px;border-radius:20px;margin:4px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}.hint{background:#fff8e9;color:#856a2c;padding:12px 17px;border-radius:8px;font-size:13px}.muted{color:#8390a4;font-size:12px}details{margin:12px 0}summary{cursor:pointer;color:#315d91}pre{white-space:pre-wrap;font-size:12px;background:#f7f9fc;padding:13px}img{max-width:100%;max-height:500px;object-fit:contain}a{color:#2b5b96}.graphrow{border-left:3px solid #7693bb;margin:10px;padding:8px 15px;background:#f3f6fb}.tag{font-size:11px;color:#9a722e}h2{font-size:19px}h3{font-size:16px}button:disabled{opacity:.6}@media(max-width:700px){.grid{grid-template-columns:1fr}main{margin-top:22px}h1{font-size:25px}}</style>
<main><div class="muted">PRIVATE COURSE WORKSPACE / 第一章样板</div><h1>输入一道题，找到知识点与练习路径。</h1><p class="sub">以已有茆书课件图片为证据，连接考点、先修概念与相关习题。</p><div class="hint">当前为小范围规则检索与候选图谱样板，尚未连接大模型。考点关联待你复核，不代表全书入库。</div>
<div class="panel"><textarea id="q">掷三颗骰子，求最大点数恰好等于5的概率。</textarea><div class="row"><select id="mode"><option value="adaptive">自适应规则路由 + 图谱</option><option value="graph">固定图谱扩展</option><option value="baseline">单轮BM25基线</option></select><button class="primary" id="run">定位知识点与相关题</button><span id="status" class="muted"></span></div><div class="row"><button data-q="掷三颗骰子，最大点数不超过5与恰好为5的概率有什么区别？">骰子最大点数</button><button data-q="三个事件的交集概率不等式如何证明？">事件不等式</button><button data-q="六根草两端随机配对恰好形成一个环的概率">配对成环</button><button data-q="如何证明最大似然估计的一致性？">未覆盖章节</button></div></div><p id="catalog" class="muted"></p><div id="out"></div></main>
<script>const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));let result=null;
const loc=e=>e.source_location||('课件第'+e.slide+'页');
const image=e=>'<details><summary>查看原始题图与批注 · '+esc(loc(e))+'</summary><p class="muted">原图是课程资料，仅供本机核对；图中手写答案未必正确。</p><img src="/evidence/'+encodeURIComponent(e.image)+'" alt="题目原图"></details>'+(e.alternative_evidence||[]).map(a=>'<details><summary>交叉出处 · 讲义PDF第'+a.pdf_page+'页</summary><img src="/evidence/'+encodeURIComponent(a.image)+'" alt="讲义交叉出处"></details>').join('');
async function go(){const b=document.querySelector('#run');b.disabled=true;try{const r=await fetch('/api/query',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:document.querySelector('#q').value,mode:document.querySelector('#mode').value})});const d=await r.json();if(!r.ok)throw Error(d.error);result=d;document.querySelector('#status').textContent=d.route;if(!d.matches.length){document.querySelector('#out').innerHTML='<div class="panel">'+esc(d.message)+'</div>';return;}let a=d.matches[0];let html='<div class="grid"><section class="panel"><h2>候选考点</h2>'+d.concepts.map(c=>'<span class="pill">'+esc(c.label)+'</span>').join('')+'<p class="tag">助手标注 · 待用户复核</p><h3>解题方法候选</h3>'+a.methods.map(x=>'<div>'+esc(x)+'</div>').join('')+'<h3>先修概念</h3>'+d.prerequisites.map(c=>'<span class="pill">'+esc(c.label)+'</span>').join('')+'<p class="muted">'+esc(d.message)+'</p></section><section class="panel"><h2>最相关原题证据</h2><h3>'+esc(a.title)+'</h3><p>'+esc(a.text)+'</p><p class="muted">'+esc(a.number)+' · '+esc(loc(a))+'<br>版本：'+esc(a.edition)+'</p><div class="hint">'+esc(a.note)+'</div>'+image(a)+'</section></div><section class="panel"><h2>题目知识图谱 · 关联路径</h2>'+d.graph.edges.map(e=>{let names=Object.fromEntries(d.graph.nodes.map(n=>[n.id,n.label]));return '<div class="graphrow">'+esc(names[e.from])+' <b> → '+(e.kind==='tests'?'考查':'需要先修')+' → </b>'+esc(names[e.to])+' <span class="tag">候选</span></div>';}).join('')+'</section><section class="panel"><h2>相关练习</h2>'+(d.related.length?d.related.map(e=>'<details><summary>'+esc(e.title)+' · 第'+e.slide+'页</summary><p>'+esc(e.text)+'</p><p class="muted">推荐依据：共享候选知识点 '+esc(e.shared_concepts.join(', '))+'；不等于完全同题型。</p>'+image(e)+'</details>').join(''):'当前样板中没有更多共享考点练习，不能补造题号。')+'</section><details class="panel"><summary>查看检索轨迹与结构化输出</summary><pre>'+esc(JSON.stringify(d.trace,null,2))+'</pre></details>';document.querySelector('#out').innerHTML=html;}catch(e){document.querySelector('#out').innerHTML='<div class="panel">'+esc(e.message)+'</div>';}finally{b.disabled=false;}}
fetch('/api/sources').then(r=>r.json()).then(d=>document.querySelector('#catalog').textContent='资料登记：'+d.file_count+'份PDF / '+d.total_pages+'页；当前可检索样板：'+d.searchable_sample_exercises+'题。其余待识别与审核。');document.querySelector('#run').onclick=go;document.querySelectorAll('[data-q]').forEach(b=>b.onclick=()=>{document.querySelector('#q').value=b.dataset.q;go();});</script></html>'''


class Handler(BaseHTTPRequestHandler):
    def send(self,status,value,kind='application/json; charset=utf-8',attachment=None):
        if status == 200 and isinstance(value,dict) and urlparse(self.path).path in {'/api/problem-record','/api/problem-search','/api/problem-study','/api/library/page','/api/library/objects','/api/library/search','/api/learn','/api/exercise','/api/validation-review','/api/problem-explain','/api/generation-record','/api/evaluation-comparison','/api/external-review/case','/api/agent'}:
            value = present(value)
        raw=json.dumps(value,ensure_ascii=False).encode() if isinstance(value,dict) else value
        self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store')
        if attachment:self.send_header('Content-Disposition','attachment; filename="'+attachment+'"')
        self.end_headers();self.wfile.write(raw)
    def do_GET(self):
        path=urlparse(self.path).path
        if path=='/agent':return self.send(200,(ROOT/'agent.html').read_bytes(),'text/html; charset=utf-8')
        if path=='/agent.js':return self.send(200,(ROOT/'agent.js').read_bytes(),'text/javascript; charset=utf-8')
        if path in {'/workspace-theme.css','/workspace-ui.js'}:
            asset='workspace-theme.css' if path.endswith('.css') else 'workspace_ui.js'
            return self.send(200,(ROOT/asset).read_bytes(),'text/css; charset=utf-8' if path.endswith('.css') else 'text/javascript; charset=utf-8')
        if path=='/matching-evaluation':return self.send(200,(ROOT/'matching_evaluation.html').read_bytes(),'text/html; charset=utf-8')
        if path=='/matching-evaluation.js':return self.send(200,(ROOT/'matching_evaluation.js').read_bytes(),'text/javascript; charset=utf-8')
        if path in {'/api/matching-evaluation','/api/matching-evaluation/review'}:
            try:
                if path.endswith('/review'):return self.send(200,matching_evaluation.review_template(),attachment='correspondence-human-review-template.json')
                return self.send(200,matching_evaluation.snapshot())
            except (OSError,ValueError,KeyError) as e:return self.send(400,{'error':str(e)})
        if path=='/benchmark':return self.send(200,(ROOT/'external_review.html').read_bytes(),'text/html; charset=utf-8')
        if path=='/660b':return self.send(200,(ROOT/'external_materials.html').read_bytes(),'text/html; charset=utf-8')
        if path=='/external-materials.js':return self.send(200,(ROOT/'external_materials.js').read_bytes(),'text/javascript; charset=utf-8')
        if path in {'/api/660b','/api/660b/question'}:
            args = parse_qs(urlparse(self.path).query)
            try:
                if path.endswith('/question'):
                    return self.send(200,external_materials.get_question(args.get('id',[''])[0]))
                return self.send(200,external_materials.browse(
                    chapter=args.get('chapter',[''])[0], status=args.get('status',['available'])[0],
                    keyword=args.get('q',[''])[0], page=int(args.get('page',['1'])[0])))
            except FileNotFoundError:
                return self.send(404,{'error':'660B 本机题库资料尚未就绪'})
            except ValueError as error:
                return self.send(400,{'error':str(error)})
        if path=='/external-review.js':return self.send(200,(ROOT/'external_review.js').read_bytes(),'text/javascript; charset=utf-8')
        if path.startswith('/api/external-review'):
            args=parse_qs(urlparse(self.path).query)
            try:
                if path=='/api/external-review':return self.send(200,external_review.overview())
                if path=='/api/external-review/case':return self.send(200,external_review.get_case(args.get('id',[''])[0]))
                if path=='/api/external-review/export':return self.send(200,external_review.export(),attachment='660b-human-reviews.json')
                if path=='/api/external-review/image':return self.send(200,external_review.image_bytes(int(args.get('n',['0'])[0])),'image/png')
            except FileNotFoundError:return self.send(404,{'error':'评测快照尚未准备好，请先完成本地评测并选择审核快照'})
            except ValueError as e:return self.send(400,{'error':str(e)})
            return self.send(404,{'error':'Not found'})
        if path in {'/answer-render.js','/answer-render.css'}:
            return self.send(200,(ROOT/path.lstrip('/')).read_bytes(),'text/javascript; charset=utf-8' if path.endswith('.js') else 'text/css; charset=utf-8')
        if path=='/portfolio':return self.send(200,(ROOT/'portfolio.html').read_bytes(),'text/html; charset=utf-8')
        if path=='/portfolio.js':return self.send(200,(ROOT/'portfolio.js').read_bytes(),'text/javascript; charset=utf-8')
        if path=='/generation-ui.js':return self.send(200,(ROOT/'generation_ui.js').read_bytes(),'text/javascript; charset=utf-8')
        if path=='/api/portfolio':return self.send(200,portfolio.snapshot())
        if path=='/api/evaluation-comparison':
            try:return self.send(200,portfolio.comparison())
            except ValueError as exc:return self.send(400,{'error':str(exc)})
        if path=='/api/generation-records':return self.send(200,{'runs':generation_records.recent()})
        if path=='/api/generation-record':
            try:
                query=parse_qs(urlparse(self.path).query)
                return self.send(200,generation_records.get(query.get('id',[''])[0]),attachment='generation-record.json' if query.get('download')==['1'] else None)
            except ValueError as exc:return self.send(400,{'error':str(exc)})
        if path=='/api/photo-notebook':
            try:
                query=parse_qs(urlparse(self.path).query)
                data=photo_notebook.get(query.get('id',[''])[0])
                return self.send(200,data,attachment='photo-notebook.json' if query.get('download')==['1'] else None)
            except photo_notebook.ConflictError as e:return self.send(409,{'error':str(e)})
            except ValueError as e:return self.send(400,{'error':str(e)})
        if path=='/photo-notebook.js':return self.send(200,(ROOT/'photo_notebook.js').read_bytes(),'text/javascript; charset=utf-8')
        if path in {'/api/photo-ocr','/api/photo-image'}:
            try:
                job_id=parse_qs(urlparse(self.path).query).get('id',[''])[0]
                if path=='/api/photo-image':return self.send(200,photo_ocr.image_bytes(job_id,parse_qs(urlparse(self.path).query).get('view',['input'])[0]),'image/png')
                return self.send(200,photo_ocr.get(job_id))
            except (ValueError,FileNotFoundError):return self.send(404,{'error':'未找到识别任务'})
        if path=='/photo-query.js':return self.send(200,(ROOT/'photo_query.js').read_bytes(),'text/javascript; charset=utf-8')
        if path=='/photo-crop.js':return self.send(200,(ROOT/'photo_crop.js').read_bytes(),'text/javascript; charset=utf-8')
        if path=='/worked':return self.send(200,(ROOT/'worked_notes.html').read_bytes(),'text/html; charset=utf-8')
        if path=='/api/worked-notes':
            args=parse_qs(urlparse(self.path).query)
            try:
                if 'id' in args:return self.send(200,worked_notes.get(args['id'][0]))
                return self.send(200,worked_notes.catalog(args['ids'][0].split(',') if 'ids' in args else None))
            except (ValueError,FileNotFoundError) as e:return self.send(400,{'error':str(e)})
        if path=='/lectures':return self.send(200,(ROOT/'lecture_library.html').read_bytes(),'text/html; charset=utf-8')
        if path in {'/api/lecture-pilot','/api/lecture-pilot/page','/api/lecture-links'}:
            args=parse_qs(urlparse(self.path).query)
            try:
                if path=='/api/lecture-pilot':return self.send(200,lecture_library.overview())
                if path=='/api/lecture-pilot/page':return self.send(200,lecture_library.get_page('6',int(args.get('n',['1'])[0])))
                return self.send(200,lecture_library.links_for(args.get('ids',[''])[0].split(',')))
            except (ValueError,FileNotFoundError) as e:return self.send(400,{'error':str(e)})
        if path.startswith('/lecture-page/') and path.endswith('.png'):
            try:
                _,_,chapter,filename=path.split('/')
                return self.send(200,lecture_library.image_bytes(chapter,int(filename[:-4])),'image/png')
            except (ValueError,FileNotFoundError):return self.send(404,{'error':'未准备的讲义页图'})
        if path=='/api/model-status':
            from tutor_provider import status as model_status
            return self.send(200,model_status())
        if path=='/syllabus':return self.send(200,syllabus_plan_ui.render(json.loads((ROOT/'data/private/syllabus/knowledge-network-plan.json').read_text(encoding='utf-8'))).encode(),'text/html; charset=utf-8')
        if path=='/syllabus-image.png':return self.send(200,(ROOT/'data/private/syllabus/syllabus-1.png').read_bytes(),'image/png')
        if path=='/validation':return self.send(200,(ROOT/'validation_review.html').read_bytes(),'text/html; charset=utf-8')
        if path=='/api/validation-review':
            try:return self.send(200,validation_review.current())
            except ValueError as e:return self.send(400,{'error':str(e)})
        if path=='/api/syllabus-plan':return self.send(200,json.loads((ROOT/'data/private/syllabus/knowledge-network-plan.json').read_text(encoding='utf-8')))
        if path=='/api/validation-sources':
            registry=json.loads((ROOT/'data/private/source_registry/manifest.json').read_text(encoding='utf-8'))
            syllabus=json.loads((ROOT/'data/private/syllabus/knowledge-network-plan.json').read_text(encoding='utf-8'))
            return self.send(200,{'files':registry['file_count'],'pages':registry['total_pages'],
                                 'syllabus_topics':sum(n['kind']=='syllabus_topic' for n in syllabus['nodes']),
                                 'lecture_questions_indexed':False})
        if path in {'/math-render.js','/math-render.css'}:
            return self.send(200,(ROOT/path[1:]).read_bytes(),'text/javascript; charset=utf-8' if path.endswith('.js') else 'text/css; charset=utf-8')
        if path.startswith('/assets/katex/'):
            base=(ROOT/'assets/katex').resolve(); target=(ROOT/path.lstrip('/')).resolve()
            if target.is_relative_to(base) and target.is_file():
                return self.send(200,target.read_bytes(),mimetypes.guess_type(target)[0] or 'application/octet-stream')
            return self.send(404,{'error':'Asset not found'})
        if path=='/problems':return self.send(200,PROBLEM_SEARCH_HTML.encode(),'text/html; charset=utf-8')
        if path=='/problem-study.js':return self.send(200,(ROOT/'problem_study.js').read_bytes(),'text/javascript; charset=utf-8')
        if path=='/problem-review.csv':return self.send(200,(exercise_vectors.OUT/'example-review-queue.csv').read_bytes(),'text/csv; charset=utf-8')
        if path=='/api/problem-graph':
            try:return self.send(200,question_knowledge.current()['report'])
            except ValueError as e:return self.send(400,{'error':str(e)})
        if path=='/api/problem-index':return self.send(200,exercise_vectors.status())
        if path=='/api/problem-record':
            try:return self.send(200,exercise_vectors.record(parse_qs(urlparse(self.path).query).get('id',[''])[0]))
            except ValueError as e:return self.send(400,{'error':str(e)})
        if path=='/library':return self.send(200,book_library.HTML.encode(),'text/html; charset=utf-8')
        if path=='/api/library':return self.send(200,book_library.overview())
        if path.startswith('/api/library/'):
            args=parse_qs(urlparse(self.path).query)
            try:
                if path=='/api/library/page':return self.send(200,book_library.get_page(int(args.get('n',['23'])[0])))
                if path=='/api/library/search':return self.send(200,book_library.search(args.get('q',[''])[0],args.get('region',['all'])[0]))
                if path=='/api/library/objects':return self.send(200,book_library.objects(args.get('kind',['exercise'])[0],args.get('section',[''])[0],offset=int(args.get('offset',['0'])[0])))
            except (ValueError,FileNotFoundError) as e:return self.send(400,{'error':str(e)})
        if path=='/library-export/book.md':
            target=ROOT/'data/private/full-book/exports/全书识别稿.md'
            if target.exists():return self.send(200,target.read_bytes(),'text/markdown; charset=utf-8')
            return self.send(404,{'error':'尚未生成整书识别稿'})
        if path=='/':return self.send(200,LEARNING_HTML.encode(),'text/html; charset=utf-8')
        if path=='/legacy':return self.send(200,HTML.encode(),'text/html; charset=utf-8')
        if path=='/api/course':
            from vector_index import status
            from tutor_provider import status as provider_status
            data=load_course();seg=ROOT/'data/private/chapter1/segmentation-report.json'
            raw=json.loads(seg.read_text(encoding='utf-8')) if seg.exists() else {}
            return self.send(200,{'exercise_count':len(data['exercises']),'concept_count':len(data['concepts']),
                                 'raw_candidate_count':raw.get('unique_exercise_ids',0),'semantic':status(),
                                 'provider':provider_status(),'review_status':data['scope']})
        if path=='/api/exercise':
            id=parse_qs(urlparse(self.path).query).get('id',[''])[0]
            item=next((q for q in load_course()['exercises'] if q['id']==id),None)
            return self.send(200,item) if item else self.send(404,{'error':'未找到已整理题目'})
        if path.startswith('/book-page/') and path.endswith('.png'):
            try:
                number=int(path.rsplit('/',1)[-1][:-4]);base=ROOT/'data/private/full-book'
                if not (base/'manifest.json').exists():base=ROOT/'data/private/chapter1'
                manifest=json.loads((base/'manifest.json').read_text(encoding='utf-8'))
                row=next(r for r in manifest['pages'] if r['pdf_page']==number)
                image=(base/row['image']).resolve()
                if not image.is_relative_to((base/'pages').resolve()):raise ValueError('Invalid image')
                return self.send(200,image.read_bytes(),'image/png')
            except (ValueError,StopIteration,FileNotFoundError):return self.send(404,{'error':'未登记的教材页'})
        if path=='/pilot':return self.send(200,pilot_review.HTML.encode(),'text/html; charset=utf-8')
        if path=='/api/pilot':return self.send(200,pilot_review.summary())
        if path.startswith('/pilot-page/') and path.endswith('.png'):
            try:return self.send(200,pilot_review.page_image(int(path.rsplit('/',1)[-1][:-4])),'image/png')
            except (ValueError,FileNotFoundError):return self.send(404,{'error':'Page not in pilot'})
        if path=='/api/health':return self.send(200,{'status':'ok'})
        if path=='/api/sources':
            manifests=[ROOT/'data/private'/d/'manifest.json' for d in ['source_registry','textbook_registry']]
            summaries=[json.loads(p.read_text(encoding='utf-8')) for p in manifests if p.exists()]
            return self.send(200,{'file_count':sum(s['file_count'] for s in summaries),'total_pages':sum(s['total_pages'] for s in summaries),
                                 'searchable_sample_exercises':sum(e['retrievable'] for e in corpus()['exercises']),
                                 'status':'registered_not_fully_indexed'})
        allowed={e['image'] for e in corpus()['exercises'] if e['retrievable']}
        allowed|={a['image'] for e in corpus()['exercises'] for a in e.get('alternative_evidence',[])}
        if path.startswith('/evidence/') and path.split('/')[-1] in allowed:
            return self.send(200,(ROOT/'data/private/evidence'/path.split('/')[-1]).read_bytes(),'image/png')
        return self.send(404,{'error':'Not found'})
    def do_POST(self):
        if self.path not in {'/api/query','/api/learn','/api/feedback','/api/problem-search','/api/problem-study','/api/problem-feedback','/api/validation-review','/api/problem-explain','/api/photo-ocr','/api/photo-retry','/api/photo-notebook','/api/external-review','/api/agent'}:return self.send(404,{'error':'Not found'})
        origin=self.headers.get('Origin')
        if origin and urlparse(origin).netloc!=self.headers.get('Host'):return self.send(403,{'error':'Origin rejected'})
        try:
            size=int(self.headers.get('Content-Length','0'))
            if self.path=='/api/photo-ocr':
                if not 0<size<=photo_ocr.MAX_BYTES:return self.send(413,{'error':'请选择不超过12MB的单张题图'})
                if self.headers.get('Content-Type','').split(';')[0] not in {'image/png','image/jpeg','image/webp'}:return self.send(415,{'error':'请上传PNG、JPEG或WebP题图'})
                region=self.headers.get('X-Photo-Crop','null')
                if len(region)>200:raise ValueError('裁剪坐标过长')
                rotation=int(self.headers.get('X-Photo-Rotation','0'))
                return self.send(202,photo_ocr.submit(self.rfile.read(size),json.loads(region),rotation))
            if not 0<size<=20000:raise ValueError('无效请求长度')
            body=json.loads(self.rfile.read(size))
            if self.path=='/api/agent':
                if isinstance(body,dict) and 'action' in body:
                    try:import study_workflow
                    except ModuleNotFoundError:return self.send(503,{'error':'请先安装 requirements-agent.txt 中的依赖。'})
                    try:return self.send(200,study_workflow.handle(body))
                    except study_workflow.StaleTask as e:return self.send(409,{'error':str(e)})
                return self.send(200,study_agent.run(body))
            if self.path=='/api/external-review':return self.send(200,external_review.save(body))
            if self.path=='/api/photo-notebook':return self.send(200,photo_notebook.save(body))
            if self.path=='/api/photo-retry':return self.send(202,photo_ocr.resubmit(body.get('job_id'),body.get('crop'),body.get('rotation',0)))
            if self.path=='/api/problem-explain':return self.send(200,rag_generation.explain(body.get('question'),body.get('stage','hint'),body.get('mode','hybrid'),body.get('kind','all'),body.get('chapter',''),body.get('adaptive',True) is True))
            if self.path=='/api/validation-review':return self.send(200,validation_review.save(body))
            if self.path=='/api/problem-feedback':return self.send(200,problem_feedback.save(body))
            if self.path=='/api/problem-study':
                binding=body.get('photo_draft')
                if binding is not None:photo_notebook.validate_search(binding,body.get('question'))
                result=full_book_tutor.retrieve(body.get('question'),body.get('mode','hybrid'),body.get('kind','all'),body.get('chapter',''),body.get('section',''),body.get('limit',8),body.get('adaptive',True) is True)
                if binding is not None:
                    try:result['photo_notebook']=photo_notebook.record_search(binding,body.get('question'),result)
                    except (ValueError,OSError):result['photo_notebook']={'saved':False,'job_id':binding['job_id'],'message':'检索完成，但本次记录未保存；请检查本机记录与存储后重试。'}
                return self.send(200,result)
            if self.path=='/api/problem-search':return self.send(200,exercise_vectors.search(body.get('question'),body.get('mode','hybrid'),body.get('kind','all'),body.get('chapter',''),body.get('section',''),body.get('limit',8)))
            if self.path=='/api/feedback':return self.send(200,feedback.save(body))
            if self.path=='/api/learn':return self.send(200,learn(body.get('question'),body.get('mode','adaptive'),body.get('stage','hint'),body.get('use_llm') is True))
            return self.send(200,retrieve(body.get('question'),body.get('mode','adaptive')))
        except (photo_notebook.ConflictError,external_review.ConflictError) as e:return self.send(409,{'error':str(e)})
        except photo_ocr.BusyError as e:return self.send(429,{'error':str(e)})
        except Exception as e:return self.send(400,{'error':str(e)})


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8768);args=parser.parse_args()
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    print(f'Local tutor: http://127.0.0.1:{args.port}',flush=True);server.serve_forever()
