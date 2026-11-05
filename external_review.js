/* Human-only local annotations. No model call or implicit approval on navigation. */
(function(){
'use strict';
const $=s=>document.querySelector(s),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let catalog=null,current=null,dirty=false,loading=0,saving=false;
const strata={'exact_textbook_duplicate':'教材同题','parameter_or_wording_variant':'参数或文字变式','related_concept_new_problem':'相关知识的新题','outside_current_scope':'当前教材未覆盖','unresolved':'尚未确定'};
const message=(text,error=false)=>{$('#status').textContent=text;$('#status').className='status'+(error?' error':'');};
async function api(url,options){const r=await fetch(url,options),d=await r.json();if(!r.ok)throw Error(d.error||'请求失败');return d;}
function renderOverview(){$('#overview').textContent='冻结快照 '+catalog.report_sha256.slice(0,12)+' · '+catalog.total+' 道文字题 · 已确认 '+catalog.cases.filter(c=>c.status==='approved').length+' 道；原始排序及历史报告保持。';}
function filteredCases(){
 const chapter=$('#chapter').value,filter=$('#filter').value,find=$('#find').value.trim().toLowerCase();
 return catalog.cases.filter(c=>(!chapter||String(c.chapter)===chapter)&&(filter!=='development'||c.development)&&(filter!=='pending'||c.status!=='approved')&&(filter!=='draft'||c.status==='draft')&&(filter!=='source'||c.source_checks?.length)&&(!find||(c.case_id+' '+(c.search_text??c.preview)).toLowerCase().includes(find)));
}
function renderList(){
 const cases=filteredCases();
 $('#case-list').innerHTML='<p class="muted">'+cases.length+' 道 · 确认 '+cases.filter(c=>c.status==='approved').length+' · 草稿 '+cases.filter(c=>c.status==='draft').length+'</p>'+cases.map(c=>'<button class="case'+(current?.case_id===c.case_id?' selected':'')+'" data-case="'+esc(c.case_id)+'">'+esc(c.case_id)+'<br><span class="muted">'+(c.status==='approved'?'已确认':c.status==='draft'?'草稿':'待审核')+(c.development?' · 开发样本':'')+' · PDF '+c.source_pages.join(', ')+'</span>'+(c.source_checks?.length?'<br><span class="badge">题干核对线索 '+c.source_checks.length+' 项</span>':'')+'</button>').join('');
 for(const b of $('#case-list').querySelectorAll('button'))b.onclick=()=>load(b.dataset.case);
}
function renderCase(){
 const row=current.state.current||{},pages=current.source_pages;
 $('#content').innerHTML='<h2>'+esc(current.case_id)+'</h2><p class="muted">'+(current.development?'已用于路由开发；不属于独立测试。':'题族、OCR和相关性仍待审核；暂不划为保留测试集。')+'</p><div class="prose">'+MathView.prose(current.query)+'</div><details class="source"><summary>核对660B原始题干页</summary>'+pages.map(p=>'<p><a target="_blank" rel="noopener" href="/api/external-review/image?n='+p+'">PDF第'+p+'页 · 放大</a></p><img loading="lazy" src="/api/external-review/image?n='+p+'" alt="660B题干原页'+p+'">').join('')+'</details><details><summary>查看原始OCR代码</summary><pre>'+esc(current.query)+'</pre></details><h2>教材候选 · 盲评</h2>'+current.candidates.map(h=>'<div class="candidate"><h3>'+esc(h.label)+'</h3><p class="muted">'+esc(h.id)+' · '+(h.pages||[]).map(p=>'<a target="_blank" rel="noopener" href="/library#page='+p+'">教材PDF '+p+'</a>').join(' · ')+'</p><div class="prose">'+MathView.prose(h.question_text)+'</div><label>相关性 <select data-grade="'+esc(h.id)+'"><option value="">未标注</option>'+[0,1,2,3].map(n=>'<option value="'+n+'"'+(row.grades?.[h.id]===n?' selected':'')+'>'+n+' · '+['无关','同主题','方法可借鉴','同题或完整条件近同'][n]+'</option>').join('')+'</select></label></div>').join('')+'<div class="card"><h2>审核记录</h2><div class="fields"><label>审核人<input id="reviewer" maxlength="64" value="'+esc(row.reviewer||'')+'"></label><label>共同题族ID<input id="family" maxlength="128" placeholder="同题或参数变式使用相同ID" value="'+esc(row.family_id||'')+'"></label><label>与教材重合分层<select id="stratum"><option value="">请选择</option>'+Object.entries(strata).map(([k,v])=>'<option value="'+k+'"'+(row.overlap_stratum===k?' selected':'')+'>'+v+'</option>').join('')+'</select></label><label><span>原页核对</span><span><input type="checkbox" id="ocr-checked"'+(row.ocr_checked?' checked':'')+'> 已核对题干、数字、公式和跨页条件</span></label></div><label>备注<textarea id="notes" maxlength="2000">'+esc(row.notes||'')+'</textarea></label><p class="muted">确认通过需标注全部候选（含无关项）、填写审核人与题族并完成原页核对。该操作记录人工声明，不自动证明教师资质。当前第'+current.state.revision+'版。</p></div><div class="card row sticky"><button id="save-draft">保存草稿</button><button id="approve" class="primary">确认核对并保存</button></div>';
 $('#content h2').insertAdjacentHTML('afterend',(current.source_checks?.length?'<p class="notice">题干核对线索：'+current.source_checks.map(esc).join('；')+'。这些线索不等于错误判定；请以原页为准，存在识别问题时保存草稿。</p>':''));
 $('#save-draft').insertAdjacentHTML('beforebegin','<span id="grade-progress" class="badge" aria-live="polite"></span>');
 $('#approve').insertAdjacentHTML('afterend','<button id="next-pending">下一道待审核</button>');
 for(const input of $('#content').querySelectorAll('input,select,textarea'))input.oninput=input.onchange=()=>{dirty=true;updateProgress();message('有未保存的审核修改');};
 $('#save-draft').onclick=()=>save('draft');$('#approve').onclick=()=>save('approved');
 $('#next-pending').onclick=nextPending;updateProgress();
}
function updateProgress(){
 const inputs=[...$('#content').querySelectorAll('[data-grade]')];
 $('#grade-progress').textContent='候选已标注 '+inputs.filter(el=>el.value!=='').length+' / '+inputs.length;
}
function nextPending(){
 if(!catalog||saving)return;
 const cases=filteredCases(),index=cases.findIndex(c=>c.case_id===current?.case_id);
 const ordered=cases.slice(index+1).concat(cases.slice(0,index+1));
 const next=ordered.find(c=>c.status!=='approved'&&c.case_id!==current?.case_id);
 if(next)return load(next.case_id);
 message('当前筛选范围内没有其他待审核题目');
}
async function load(id){
 if(saving)return;
 if(dirty&&!window.confirm('当前审核尚未保存，仍要切换题目吗？'))return;
 const token=++loading;message('读取题目……');$('#content').style.opacity='.55';$('#content').inert=true;
 try{const data=await api('/api/external-review/case?id='+encodeURIComponent(id));if(token!==loading)return;current=MathView.register(data);dirty=false;renderCase();renderList();window.history.replaceState(null,'','/benchmark?id='+encodeURIComponent(id));message('已载入，标签由你手动填写');}
 catch(e){if(token===loading)message(e.message,true);}
 finally{if(token===loading){$('#content').style.opacity='1';$('#content').inert=false;}}
}
async function save(status){
 if(!current||saving)return;
 saving=true;
 const grades={};for(const el of $('#content').querySelectorAll('[data-grade]'))grades[el.dataset.grade]=el.value===''?null:Number(el.value);
 const body={case_id:current.case_id,report_sha256:current.report_sha256,base_revision:current.state.revision,status,grades,reviewer:$('#reviewer').value,family_id:$('#family').value,ocr_checked:$('#ocr-checked').checked,overlap_stratum:$('#stratum').value,notes:$('#notes').value};
 for(const b of $('#content').querySelectorAll('button,input,select,textarea'))b.disabled=true;
 try{const result=await api('/api/external-review',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});current.state.revision=result.revision;current.state.current={...body};dirty=false;const entry=catalog.cases.find(c=>c.case_id===current.case_id);entry.status=status;entry.revision=result.revision;renderCase();renderList();renderOverview();message('已保存第'+result.revision+'版'+(status==='draft'?'草稿':'人工审核记录'));}
 catch(e){message(e.message,true);}
 finally{saving=false;for(const b of $('#content').querySelectorAll('button,input,select,textarea'))b.disabled=false;}
}
window.addEventListener('beforeunload',e=>{if(dirty){e.preventDefault();e.returnValue='';}});
for(let c=1;c<=8;c++)$('#chapter').insertAdjacentHTML('beforeend','<option value="'+c+'">第'+c+'章</option>');
$('#chapter').onchange=$('#filter').onchange=$('#find').oninput=()=>catalog&&renderList();
api('/api/external-review').then(d=>{catalog=d;renderOverview();renderList();const id=new URLSearchParams(window.location.search).get('id');if(id&&catalog.cases.some(c=>c.case_id===id))load(id);}).catch(e=>message(e.message,true));
})();
