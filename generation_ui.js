/* Explicit generation and local replay share the same safe answer view. */
let generationConfigured=false,generationBusy=false,generationDisplayEpoch=0,historyReadEpoch=0;
const refreshGeneration=()=>{$('explain').disabled=generationBusy||!(generationConfigured&&$('allow-generation').checked)};
function generationRecordLink(d){return d.record_saved?'<p><a href="/portfolio?run='+encodeURIComponent(d.run_id)+'">在作品集重看</a> · <a href="/api/generation-record?id='+encodeURIComponent(d.run_id)+'&download=1">导出记录</a></p>':d.record_saved===false?'<p class="notice">本次讲解记录未能保存；当前回答仍可阅读。</p>':''}
function invalidateTeaching(){generationDisplayEpoch++;$('teaching-output').innerHTML=''}
function showTeaching(d,historical=false){
 const t=d.teaching||{},evidence=d.evidence||[];
 const history=historical?'<div class="notice"><strong>已保存的历史讲解</strong><p>对应题干：'+esc(d.question)+'</p><span class="muted">'+esc(d.created_at)+' · 没有重新调用模型</span></div>':'';
 if(!t.used){$('teaching-output').innerHTML=history+'<p class="notice">'+esc(t.message||'讲解未生成，请检查条件或模型状态。')+'</p>'+(d.clarifications||[]).map(x=>'<p>'+esc(x)+'</p>').join('')+generationRecordLink(d);return}
 $('teaching-output').innerHTML=history+'<p class="notice">模型生成 · 待核对。引用编号已检查；数学正确性和引用是否支持结论仍需审核。</p><div class="answer-content">'+AnswerView.render(t.text,{evidence})+'</div><details><summary>查看本次引用来源</summary>'+evidence.filter(e=>(t.citation_ids||[]).includes(e.id)).map(e=>'<h3>'+esc(e.id+' · '+e.title)+'</h3><div class="prose">'+renderQuestion(e.text)+'</div>'+pageLinks(e.pages)).join('')+'</details>'+generationRecordLink(d);
}
async function refreshGenerationHistory(){
 const token=++historyReadEpoch;
 try{const data=await api('/api/generation-records');if(token!==historyReadEpoch)return;
  $('recent-generation-list').innerHTML=(data.runs||[]).slice(0,5).map(r=>'<div class="history-row"><button class="source" data-load-answer="'+esc(r.id)+'">重看 · '+esc(r.question?.slice(0,58)||'未命名题目')+'</button><span class="muted">'+esc(r.created_at)+' · '+(r.status==='generated_pending_review'?'已生成，待核对':'未生成／需补条件')+'</span></div>').join('')||'<p class="muted">尚无讲解记录。生成后会保存在本机，可在这里重看。</p>';
 }catch(e){if(token===historyReadEpoch)$('recent-generation-list').textContent='暂未读取本机讲解记录：'+e.message}
}
async function loadSavedTeaching(id){
 if(generationBusy)return;
 const token=++generationDisplayEpoch;$('teaching-output').textContent='正在读取已保存的讲解…';
 try{const d=await api('/api/generation-record?id='+encodeURIComponent(id));if(token!==generationDisplayEpoch)return;showTeaching({...d,run_id:d.id,record_saved:true},true)}
 catch(e){if(token===generationDisplayEpoch)$('teaching-output').textContent=e.message}
}
$('recent-generation-list').addEventListener('click',e=>{const b=e.target.closest('[data-load-answer]');if(b)loadSavedTeaching(b.dataset.loadAnswer)});
api('/api/model-status').then(d=>{generationConfigured=d.enabled&&d.configured;$('generation-status').textContent=generationConfigured?'模型已配置。请选择讲解层级并主动生成，或重看本机保存的记录。':'当前可检索与阅读教材；配置模型服务后可生成带出处的讲解。';refreshGeneration()}).catch(e=>$('generation-status').textContent=e.message);
$('allow-generation').onchange=refreshGeneration;
$('explain').onclick=async()=>{
 if(generationBusy)return;
 const question=$('question').value,token=++generationDisplayEpoch;
 generationBusy=true;refreshGeneration();$('teaching-output').textContent='正在检索证据并生成讲解…';
 try{const d=await api('/api/problem-explain',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question,stage:$('explain-stage').value,mode:$('mode').value,kind:$('kind').value,chapter:$('chapter').value,adaptive:$('adaptive').checked})});
  refreshGenerationHistory();if(token!==generationDisplayEpoch)return;
  if($('question').value!==question){$('teaching-output').textContent='题目已变化，请重新生成。已保存的旧题讲解可从历史记录重看。';return}
  showTeaching(d);
 }catch(e){if(token===generationDisplayEpoch)$('teaching-output').textContent=e.message}
 finally{generationBusy=false;refreshGeneration()}
};
refreshGenerationHistory();
