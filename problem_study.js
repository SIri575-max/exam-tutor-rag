/* Source-linked study UI. The server performs all retrieval and graph selection. */
function studyTopics(matches){return (matches||[]).slice(0,5).map(t=>'<button class="source" data-page="'+t.pdf_page+'" title="'+esc(t.quote)+'">'+esc(t.label)+'</button>').join('');}
function studyNodeLabel(n){const text=n.label.replace(/\s+/g,' ');return text.match(/^(?:定义|定理|性质|推论|引理|命题)\s*\d+(?:\.\d+)+/)?.[0]||text;}
function studyGraph(graph){
  const q=graph.nodes.filter(n=>['example','exercise'].includes(n.kind)).slice(0,3);
  const t=graph.nodes.filter(n=>n.kind==='topic').slice(0,4);
  const k=graph.nodes.filter(n=>!['example','exercise','topic'].includes(n.kind)).slice(0,3);
  const cols=[q,t,k],pos=new Map();
  cols.forEach((ns,c)=>ns.forEach((n,i)=>pos.set(n.id,{x:8+c*272,y:48+i*(c===1?92:138),n})));
  const edges=graph.edges.filter(e=>pos.has(e.from)&&pos.has(e.to)&&pos.get(e.from).x!==pos.get(e.to).x);
  if(!edges.length)return '<p class="muted">这些题目前尚无足够的显式词语关系可画图，请先核对原页与所在小节。</p>';
  const lines=edges.map(e=>{const a=pos.get(e.from),b=pos.get(e.to),dashed=e.kind==='located_in_subsection';return '<path d="M '+(a.x+232)+' '+(a.y+34)+' C '+(a.x+252)+' '+(a.y+34)+', '+(b.x-20)+' '+(b.y+34)+', '+b.x+' '+(b.y+34)+'" fill="none" stroke="'+(dashed?'#b2bac0':'#7aa496')+'" stroke-width="1.5" '+(dashed?'stroke-dasharray="5 4"':'')+' marker-end="url(#study-arrow)"/>';}).join('');
  const nodes=Array.from(pos.values()).map(({x,y,n})=>{const isQ=['example','exercise'].includes(n.kind),attr=isQ?'data-detail="'+esc(n.id)+'"':'data-page="'+n.pages[0]+'"';const label=studyNodeLabel(n).slice(0,28);return '<g '+attr+' role="button" tabindex="0" style="cursor:pointer"><rect x="'+x+'" y="'+y+'" width="232" height="68" rx="9" fill="'+(isQ?'#edf4f1':n.kind==='topic'?'#f4f0fa':'#f0f4f7')+'" stroke="#cddcda"/><text x="'+(x+12)+'" y="'+(y+26)+'" fill="#203a46" font-size="13"><tspan x="'+(x+12)+'">'+esc(label.slice(0,15))+'</tspan><tspan x="'+(x+12)+'" dy="19">'+esc(label.slice(15))+'</tspan></text></g>';}).join('');
  const mobile=edges.map(e=>{const a=pos.get(e.from).n,b=pos.get(e.to).n;const button=n=>'<button class="source" '+(['example','exercise'].includes(n.kind)?'data-detail="'+esc(n.id)+'"':'data-page="'+n.pages[0]+'"')+'>'+esc(studyNodeLabel(n).slice(0,42))+'</button>';return '<div class="path">'+button(a)+'<span class="muted"> → '+(e.kind==='located_in_subsection'?'所在小节':e.kind==='mentions_topic'?'原文提及':'小节内条目')+' → </span>'+button(b)+'</div>';}).join('');
  return '<style>.study-graph-mobile{display:none}@media(max-width:650px){.study-graph-svg{display:none}.study-graph-mobile{display:block}}</style><div class="study-graph-mobile">'+mobile+'</div><div class="study-graph-svg" style="overflow:auto"><svg viewBox="0 0 825 420" style="min-width:680px;width:100%" role="img" aria-label="题目、考点线索和教材条目关系图"><defs><marker id="study-arrow" markerWidth="7" markerHeight="7" refX="6" refY="3" orient="auto"><path d="M0,0 L0,6 L7,3 z" fill="#7aa496"/></marker></defs><text x="8" y="23" fill="#6b7d84" font-size="12">题目候选</text><text x="280" y="23" fill="#6b7d84" font-size="12">原文提及的考点 / 所在小节</text><text x="552" y="23" fill="#6b7d84" font-size="12">该小节的教材定义与定理</text>'+lines+nodes+'</svg></div><p class="muted">实线表示原文词语提及或教材条目位置，虚线表示例题所在小节。点击节点核对原题或教材原页；不代表已经审核的“考查/先修”关系。</p>';
}
function studyPanel(d){
 const s=d.study||{},g=d.practice_groups||{},routes={source_property_lookup:'已定位教材中的性质讲解',clarify_conditions:'先补充题目条件',bounded_type_balancing:'已补充另一类例题或课后题',explicit_math_query_bridge:'已补充明确条件的公式表达',single_retrieval:'题目检索与出处核对',source_number_lookup:'按教材题号直接定位',clarify_problem:'需要补充题目条件'};
 let html='<section class="card"><div class="head"><h2>考点线索与学习路径</h2><span class="badge">'+esc(routes[d.route]||'候选路径')+'</span></div>';
 if(d.status==='needs_problem_context')return html+'<p>'+esc(d.message)+'</p><ul>'+(d.clarifications||[]).map(x=>'<li>'+esc(x)+'</li>').join('')+'</ul></section>';
 html+='<p class="muted">先核对条件，再读教材条目，随后看例题、做练习。可根据这些出处选择讲解层级。</p><div class="row">'+studyTopics(s.query_topics)+'</div>';
 if(!(s.query_topics||[]).length)html+='<p class="muted">输入中未出现可直接匹配的考点名称；以下线索来自候选原题及其出处。</p>';
 if(d.clarifications?.length)html+='<p class="flags">'+d.clarifications.map(esc).join('；')+'</p>';
 if(s.property_evidence?.length)html+='<div class="notice">已找到教材中直接提到该性质的段落；它说明性质，不等于当前题目的完整解答。</div>'+s.property_evidence.map(r=>'<h3>'+esc(r.label)+'</h3><div class="prose">'+renderQuestion(r.text)+'</div>'+pageLinks(r.pages)+'<button class="source" data-detail="'+esc(r.record_id)+'">打开对应原例</button>').join('');
 if(s.readings?.length)html+='<details><summary>先读哪些教材定义与定理</summary>'+s.readings.map(r=>'<div class="path"><strong>'+renderQuestion(r.title)+'</strong>'+pageLinks(r.pages)+'<details><summary>查看识别摘录（待校对）</summary><div class="prose">'+renderQuestion(r.text)+'</div></details></div>').join('')+'</details>';
 if(s.references?.length)html+='<details><summary>这些例题引用的前例</summary>'+s.references.map(r=>'<p>'+renderQuestion(r.quote)+' <button class="source" data-detail="'+esc(r.id)+'">打开'+esc(r.label)+'</button></p>').join('')+'</details>';
 if($('kind').value==='all')html+='<details><summary>例题 → 课后题的练习路径</summary>'+['example','exercise'].map(kind=>'<h3>'+(kind==='example'?'先看例题':'再做课后题')+'</h3>'+(g[kind]||[]).map(r=>'<div class="path"><button class="source" data-detail="'+esc(r.id)+'">'+esc(r.label)+'</button><span class="muted">'+esc(r.section_title)+'</span><p>'+renderQuestion(r.question_text)+'</p>'+pageLinks(r.pages)+'</div>').join('')).join('')+'</details>';
 html+='<details open><summary>查看题目与考点的关系图</summary>'+studyGraph(s.graph||{nodes:[],edges:[]})+'</details><details><summary>这次如何检索 · Top K与实际候选</summary>'+retrievalBudgetPanel(d)+'<details><summary>完整检索轨迹</summary><pre>'+esc(JSON.stringify(d.trace,null,2))+'</pre></details></details></section>';
 return html;
}
function retrievalBudgetPanel(d){
 const b=d.retrieval_budget;if(!b)return '<p class="muted">该响应未记录分阶段候选预算。</p>';
 const counts=b.actual_practice_counts||{};
 return '<p>先检索候选，再按条件调整顺序，最后展示；各阶段的K是数量上限，不是正确率。</p>'+
 '<ul><li>'+(d.route==='source_number_lookup'?'明确题号直接定位，跳过首轮召回':'首轮候选上限：'+esc(b.adaptive_enabled?b.recall_k:b.detailed_k)+'题（按完整题目去重后计数）')+'</li>'+
 '<li>分类型关键词补充预算：每类最多'+esc(b.typed_lexical_k)+'题；实际是否执行见下方轨迹，合并后可能超过首轮K</li>'+
 '<li>页面推荐：每类最多'+esc(b.practice_k)+'题；本次例题'+esc(counts.example||0)+'、课后题'+esc(counts.exercise||0)+'</li>'+
 '<li>详细候选：最多'+esc(b.detailed_k)+'题，本次'+esc(b.actual_detailed_count)+'</li></ul>'+
 '<p class="muted">明确题号走直接定位；未开启辅助排序时不执行自适应补充。生成讲解另选来源证据，不会把全部候选直接交给模型。</p>';
}
let studyRequest=0;
function updateFormulaPreview(){const q=$('question').value.trim(),node=$('formula-preview');if(!q){node.innerHTML='';return}let html=q.includes('$')?MathView.prose(q):/\\[a-z]+/.test(q)?MathView.formula(q,true):MathView.prose(q);if(html.includes('math-fallback'))html='<span class="muted">公式尚未闭合或写法暂不支持，仍可按原文查找。</span>';node.innerHTML='<span class="muted">输入预览</span><div>'+html+'</div>'}
function formulaAnalysis(d){const f=d.formula_analysis;if(!f)return '';let conditions=[];if(f.conditions.sample_size)conditions.push('样本量 '+f.conditions.sample_size);if(f.conditions.mean)conditions.push('总体均值'+(f.conditions.mean==='known'?'已知':'未知'));if(f.conditions.support)conditions.push(({zero_to_parameter:'区间下界为0',parameter_to_double:'区间端点为参数及其2倍',shift_unit_width:'平移区间宽度为1',other_explicit_bounds:'已给出支持区间'})[f.conditions.support]||'支持区间待核对');if(f.conditions.exponential_rate==='one')conditions.push('指数速率为1');return '<section class="card"><h2>这条式子的检索线索</h2><div class="row">'+[...f.models,...f.operations,...conditions].map(s=>'<span class="badge">'+esc(s)+'</span>').join('')+'</div>'+(!f.models.length?'<p class="muted">尚未识别出明确的总体分布。</p>':'')+(f.missing_context.length?'<ul>'+f.missing_context.map(v=>'<li>'+esc(v)+'</li>').join(''):'')+'<p class="muted">'+esc(f.boundary)+'</p></section>'}
function formulaMatch(x){const m=x.formula_match;if(!m)return '';return '<div class="notice"><strong>匹配线索：</strong>'+m.reasons.map(esc).join('、')+(m.differences.length?'<p style="margin:5px 0"><strong>仍需核对：</strong>'+m.differences.map(esc).join('；')+'</p>':'<p style="margin:5px 0">请继续核对变量含义、完整条件和所求量。</p>')+'</div>'}
function correspondenceReason(x){
 const m=x.correspondence;if(!m)return formulaMatch(x);
 return '<div class="notice"><strong>'+esc(m.label)+'</strong><p>为什么推荐：'+m.reasons.map(esc).join('；')+'</p>'+(m.differences.length?'<p>使用前核对：'+m.differences.map(esc).join('；')+'</p>':'<p>仍需核对变量含义、完整条件和所求量。</p>')+'</div>';
}
function correspondencePanel(d){
 const mapping=d.correspondence,g=d.practice_groups||{},topics=mapping.input_topics||[];
 const group=(kind,title)=>'<section class="match-column"><h3>'+title+'</h3>'+(g[kind]?.length?g[kind].map(x=>{
  const m=x.correspondence||{label:'相关题候选',reasons:[],differences:[]};
  return '<div class="match-card"><button class="source" data-detail="'+esc(x.id)+'">'+esc(x.label)+'</button><p class="muted">'+esc(x.section+' '+(x.section_title||''))+' · '+esc(m.label)+'</p><p>关联理由：'+m.reasons.slice(0,3).map(esc).join('；')+'</p>'+(m.differences.length?'<p class="flags">条件核对：'+m.differences.slice(0,2).map(esc).join('；')+'</p>':'')+'<div class="row">'+pageLinks(x.pages)+'</div></div>';
 }).join(''):'<p class="muted">当前范围未找到这一类题。可扩大章节或题目类型范围。</p>')+'</section>';
 return '<section class="card correspondence-panel"><h2>这道题对应哪里</h2><p class="muted">先看知识点，再对照例题与课后题的完整条件。</p><h3>建议回看的知识点</h3>'+(topics.length?'<div class="topic-clues">'+topics.map(t=>'<div><button class="source" data-page="'+t.pdf_page+'">'+esc(t.label)+'</button><span class="muted">'+esc(t.basis)+'</span></div>').join('')+'</div><details><summary>用这些问题自查复习环节</summary><ul>'+topics.map(t=>'<li><strong>'+esc(t.label)+'：</strong>'+esc(t.self_check)+'</li>').join('')+'</ul><p class="muted">'+esc(mapping.self_check_notice)+'</p></details>':'<p class="muted">暂未提取到足够明确的知识点线索，请先对照候选原题。</p>')+'<div class="match-columns">'+group('example','先看相关例题')+group('exercise','再练相关课后题')+'</div><p class="muted">'+esc(mapping.matching_notice)+'</p><div class="study-shortcut"><button class="source" data-study-open="study-panel">查看教材条目与关系图</button></div></section>';
}
function studyBrief(d){
 const hits=d.hits||[];
 if(d.status==='request_failed')return '<section class="empty-result"><h2>暂未完成查题</h2><p>'+esc(d.message)+'</p><p>保留当前题干，检查输入或稍后重试。</p></section>';
 if(d.status==='needs_problem_context')return '<section class="empty-result"><h2>先补充题目条件</h2><p>'+esc(d.message)+'</p><ul>'+(d.clarifications||[]).map(x=>'<li>'+esc(x)+'</li>').join('')+'</ul><p class="muted">请在左侧补充分布、样本及所求量，再点击查题。</p></section>';
 if(!hits.length)return '<section class="empty-result"><h2>当前范围未找到清晰候选</h2><p>请检查章节／题目类型筛选，补充完整分布、支持区间与所求量后重试。</p><p class="muted">也可以上传题图，对照原件核对识别稿。</p></section>';
 if(d.correspondence)return correspondencePanel(d);
 const first=hits[0],topics=d.study?.query_topics||[];
 return '<section class="card"><h2>接下来怎么学</h2><p>先核对 <strong>'+esc(first.label)+'</strong> 的完整条件，再查看知识点与相关练习。</p>'+(topics.length?'<div class="row">'+studyTopics(topics)+'</div>':'')+'<div class="study-shortcut"><button class="source" data-study-open="study-panel">知识点与练习路径</button><button class="source" data-study-open="generation-panel">讲解与本机历史</button>'+pageLinks(first.pages)+'</div><p class="muted">先确认分布、参数和所求量，候选题的答案需要重新核对。</p></section>';
}
async function studyRun(){
 const question=$('question').value,photoDraft=typeof PhotoNotebook!=='undefined'?PhotoNotebook.binding(question):null;
 const token=++studyRequest,b=$('run');b.disabled=true;current=[];updateFormulaPreview();$('results').innerHTML='';$('study-brief').innerHTML='';$('formula-analysis').innerHTML='';if(typeof invalidateTeaching==='function')invalidateTeaching();else $('teaching-output').innerHTML='';$('error').textContent='';$('summary').textContent='正在匹配公式与已有题目…';
 try{
  const d=await api('/api/problem-study',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question,mode:$('mode').value,kind:$('kind').value,chapter:$('chapter').value,adaptive:$('adaptive').checked,...(photoDraft?{photo_draft:photoDraft}:{})})});
  if(token!==studyRequest)return;
  if(typeof PhotoNotebook!=='undefined')PhotoNotebook.recorded(d.photo_notebook,question);
  if($('question').value!==question){$('summary').textContent='题干已改变，请重新查找相关题。';$('study-output').innerHTML='';return}
  current=d.hits;$('summary').textContent=d.status==='needs_problem_context'?d.message:'相关例题 '+(d.practice_groups?.example?.length||0)+' 道 · 相关课后题 '+(d.practice_groups?.exercise?.length||0)+' 道 · '+d.elapsed_seconds+' 秒';
  $('formula-analysis').innerHTML=formulaAnalysis(d);
  $('study-output').innerHTML=studyPanel(d);
  $('study-brief').innerHTML=studyBrief(d);
  $('results').innerHTML=d.hits.map((x,i)=>'<article class="card"><div class="head"><h2><span class="number">'+(i+1)+'</span>'+esc(x.label)+'</h2><span class="badge '+(x.kind==='example'?'example':'')+'">'+(x.example_role==='illustration'?'说明性例子':x.example_role==='worked_continuation'?'续例':x.kind==='example'?'例题':'课后题')+'</span></div><div class="muted">第'+x.chapter+'章 · '+esc(x.section+' '+x.section_title)+'</div><div class="row">'+studyTopics(d.study.record_topics[x.id])+'</div><p class="flags">'+x.review_flags.map(esc).join('；')+'</p><div class="prose">'+renderQuestion(x.question_text)+'</div>'+correspondenceReason(x)+'<div class="row">'+pageLinks(x.pages)+'<button class="source" data-detail="'+esc(x.id)+'">'+(x.kind==='example'?'展开原例与讲解':'查看题目完整记录')+'</button><button class="source" data-feedback="'+esc(x.id)+'">报告识别或关联问题</button></div>'+'<div class="row" data-lecture-for="'+esc(x.id)+'"></div>'+(x.example_references?.length?'<details><summary>引用前例</summary>'+x.example_references.map(r=>'<p>'+renderQuestion(r.quote)+'<button class="source" data-detail="'+esc(r.id)+'">'+esc(r.label)+'</button></p>').join('')+'</details>':'')+(x.answer_group_locator?'<details><summary>教材参考答案页定位</summary><p class="muted">只定位习题组，逐题边界待校对。</p>'+(x.answer_group_locator.pages.length?pageLinks(x.answer_group_locator.pages):'<p>原书参考答案区未列出此组。</p>')+'</details>':'')+'<details><summary>命中片段与分数</summary><pre>'+esc(x.matched_text)+'\n'+esc(JSON.stringify({cosine:x.cosine,bm25:x.bm25,rrf:x.rrf},null,2))+'</pre></details></article>').join('');
 attachLectureLinks(current);
 attachWorkedNotes(current);
 $('summary').scrollIntoView({behavior:'smooth',block:'start'});
 }catch(e){if(token===studyRequest){$('error').textContent=e.message;$('summary').textContent='';$('results').innerHTML='';$('study-output').innerHTML='';$('study-brief').innerHTML=studyBrief({status:'request_failed',message:e.message});}}finally{if(token===studyRequest)b.disabled=false;}
}
document.addEventListener('keydown',e=>{const n=e.target.closest('g[data-page],g[data-detail]');if(n&&e.key==='Enter')n.dispatchEvent(new MouseEvent('click',{bubbles:true}));});

let studyFeedbackRecord=null;
document.addEventListener('click',e=>{const b=e.target.closest('[data-study-open]');if(!b)return;const panel=$(b.dataset.studyOpen);if(panel){panel.open=true;panel.scrollIntoView({behavior:'smooth',block:'start'})}});
document.addEventListener('click',e=>{const b=e.target.closest('[data-feedback]');if(b){studyFeedbackRecord=b.dataset.feedback;$('feedback-title').textContent='报告问题 · '+studyFeedbackRecord;$('feedback-message').value='';$('study-feedback-status').textContent='';$('feedback-viewer').showModal();}});
$('close-study-feedback').onclick=()=>$('feedback-viewer').close();
$('save-study-feedback').onclick=async()=>{const b=$('save-study-feedback');b.disabled=true;try{const r=await api('/api/problem-feedback',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({record_id:studyFeedbackRecord,category:$('feedback-category').value,message:$('feedback-message').value,query:$('question').value})});$('study-feedback-status').textContent=r.message;}catch(e){$('study-feedback-status').textContent=e.message;}finally{b.disabled=false;}};

async function attachLectureLinks(records){try{const d=await api('/api/lecture-links?ids='+encodeURIComponent(records.map(r=>r.id).join(',')));if(current!==records)return;for(const node of $('results').querySelectorAll('[data-lecture-for]')){const links=d.links[node.dataset.lectureFor]||[];node.innerHTML=links.map(v=>'<a class="source" href="/lectures#page='+v.lecture_pdf_page+'" target="_blank">讲义'+(v.matching_method.includes('visual')?'原图对照候选':'算法关联候选')+' · 第六章PDF '+v.lecture_pdf_page+'</a>').join('')}}catch(_){/* Lecture preview is optional; preserve the original search results. */}}
async function attachWorkedNotes(records){try{const d=await api('/api/worked-notes?ids='+encodeURIComponent(records.map(r=>r.id).join(',')));if(current!==records)return;for(const n of d.items){const article=Array.from($('results').querySelectorAll('[data-lecture-for]')).find(el=>el.dataset.lectureFor===n.record_id)?.closest('article');if(article){const row=document.createElement('div');row.className='row';row.innerHTML='<a class="source" href="/worked?id='+encodeURIComponent(n.record_id)+'" target="_blank">分步讲解样板 · 教师待审</a>';article.appendChild(row)}}}catch(_){/* Optional authored notes never block source retrieval. */}}
$('question').addEventListener('input',updateFormulaPreview);$('question').addEventListener('keydown',e=>{if(e.ctrlKey&&e.key==='Enter'){e.preventDefault();studyRun()}});
async function prefill660b(identifier){
 const input=$('question');
 try{
  const material=await api('/api/660b/question?'+new URLSearchParams({id:identifier}));
  if(input.value)return;
  if(!material.can_prefill)throw Error('这道题需要对照原页录入完整条件。');
  input.value=material.text;
  input.dispatchEvent(new Event('input',{bubbles:true}));
  const note=document.createElement('p');note.className='muted';
  const link=document.createElement('a');
  link.href='/660b?'+new URLSearchParams({id:material.id,q:material.id,status:'all'});
  link.textContent=`660B 第 ${material.chapter} 章第 ${material.number} 题 · PDF ${material.pages.join('、')} 页`;
  note.append(link,'。对照原页核对后，点击查找相关题。');input.before(note);
 }catch(error){$('error').textContent=error.message;}
}
const studyParams=new URLSearchParams(location.search);
const studyInitialQuery=studyParams.get('q');
if(studyInitialQuery?.trim()){$('question').value=studyInitialQuery;studyRun()}
else if(studyParams.get('from660b'))prefill660b(studyParams.get('from660b'));
