'use strict';
const $=id=>document.getElementById(id),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let comparisonData=null;
async function get(url){const r=await fetch(url),d=await r.json();if(!r.ok)throw Error(d.error||'读取失败');return MathView.register(d)}
function rendered(text){return MathView.prose(text||'')}
function evidenceView(evidence){return (evidence||[]).map(e=>'<details><summary>'+esc(e.id+' · '+e.title)+' · PDF '+esc((e.pages||[]).join('、'))+'</summary><div class="prose">'+rendered(e.text)+'</div>'+(e.pages||[]).map(p=>'<a href="/library#page='+Number(p)+'">打开教材PDF '+Number(p)+'</a>').join(' · ')+'</details>').join('')}
function answerView(entry){const t=entry.teaching||entry.generation||{};return '<p class="notice">'+esc(t.used?'模型真实响应 · 待人工核对数学与引用支持':t.message||entry.message||t.status||entry.status)+'</p>'+(t.text?'<div class="answer-content">'+AnswerView.render(t.text,{evidence:entry.evidence||[],citationStyle:'link'})+'</div>':'')+'<p class="muted">'+esc(t.model||'')+' · '+esc(entry.elapsed_seconds??'—')+'秒 · '+esc(t.usage?.total_tokens??'—')+' tokens</p>'+evidenceView(entry.evidence)}
function showCase(){if(!comparisonData)return;const c=comparisonData.cases.find(c=>c.id===$('case-select').value),a=c?.arms[$('arm-select').value];if(!a)return;$('case-output').innerHTML='<h3>'+esc(c.id)+'</h3><div>'+rendered(c.question)+'</div>'+answerView(a)+'<details><summary>助手检查点与审核状态</summary><p>'+esc(c.reference_answer||'暂无参考')+'</p><p>人工数学正确性与引用支持：尚未审核。</p></details>'}
$('case-select').onchange=showCase;$('arm-select').onchange=showCase;
async function showRun(id){try{const d=await get('/api/generation-record?id='+encodeURIComponent(id));$('run-output').innerHTML='<h3>已保存的实际讲解</h3><div>'+rendered(d.question)+'</div>'+answerView(d)+'<a href="/api/generation-record?id='+encodeURIComponent(id)+'&download=1">导出该次讲解与证据</a>'}catch(e){$('run-output').textContent=e.message}}
$('run-list').onclick=e=>{const b=e.target.closest('[data-run]');if(b)showRun(b.dataset.run)};
get('/api/portfolio').then(async d=>{
 const version=d.release.version?.replace('-local','')||'1.1';
 $('release-status').textContent=d.release.status==='local_v1_complete'?'V'+version+' · 本机版已交付':'V'+version+' · 正在验收';
 const i=d.index;
 $('metrics').innerHTML=[[i.kinds?.exercise??'—','课后题'],[i.kinds?.example??'—','例题候选'],[i.chunks??'—','向量片段'],[d.model.model||'未配置','生成模型']].map(([v,k])=>'<div class="metric"><strong>'+esc(v)+'</strong>'+esc(k)+'</div>').join('');
 $('identity').textContent='嵌入：'+i.model+' · '+i.dimensions+'维 · 索引'+(i.ready?'就绪':'待检查')+' · 模型'+(d.model.enabled&&d.model.configured?'已配置，按需调用':'未启用');
 const r=d.retrieval_development,e=d.release.evaluation;let html='';
 if(r){html+='<h3>24条原题定位开发样例</h3><div class="scroll"><table><tr><th>方法</th><th>Hit@1</th><th>Hit@8</th><th>MRR@8</th></tr>'+Object.entries(r.summary).map(([k,v])=>'<tr><td>'+esc(k)+'</td><td>'+v.hit_at_1+'/'+v.cases+'</td><td>'+v.hit_at_8+'/'+v.cases+'</td><td>'+v.mrr_at_8+'</td></tr>').join('')+'</table></div>'}
 if(e){html+='<h3>三组真实生成对照</h3><p>'+e.case_count+'条开发输入 · '+e.request_attempts+'次请求；其中'+e.clarified_cases+'条输入在三组共同检查中澄清，未调用模型。已记录用量'+e.total_tokens+' tokens'+(e.token_usage_missing_requests?'（'+e.token_usage_missing_requests+'次请求的用量缺失）':'')+'。</p><div class="scroll"><table><tr><th>方法</th><th>可展示响应</th><th>引用未通过</th><th>平均请求秒数</th></tr>'+Object.entries(e.arms).map(([k,v])=>'<tr><td>'+esc(k)+'</td><td>'+v.accepted+'/'+v.attempted+'</td><td>'+v.citation_rejected+'</td><td>'+v.mean_seconds+'</td></tr>').join('')+'</table></div><p class="muted">可展示响应表示接口与引用编号检查通过，不是答案正确率。无检索组不要求引用。</p>';}
 $('evaluation-summary').innerHTML=html||'评测运行中，完成后刷新。';
 $('run-list').innerHTML=d.generation_runs.length?d.generation_runs.map(r=>'<div class="row"><button data-run="'+r.id+'">重看 · '+esc(r.question.slice(0,48))+'</button><span class="muted">'+esc(r.created_at)+' · '+esc(r.status)+'</span></div>').join(''):'尚无页面讲解记录；请到题目检索页主动生成一次。';
 $('check-list').innerHTML=(d.release.checks||[]).map(c=>'<p>✓ '+esc(c)+'</p>').join('');
 if(e){comparisonData=await get('/api/evaluation-comparison');$('case-select').innerHTML=comparisonData.cases.map(c=>'<option value="'+esc(c.id)+'">'+esc(c.id+' · '+c.question.slice(0,42))+'</option>').join('');showCase()}
 const run=new URLSearchParams(location.search).get('run');if(run)showRun(run);
}).catch(e=>$('release-status').textContent=e.message);
