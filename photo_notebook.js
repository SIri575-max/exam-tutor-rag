/* Explicit local drafts. No approval, training, model call, or automatic search. */
const PhotoNotebook=(()=>{
 let epoch=0,job=null,data=null,selected=[],bound=false,loadedRevision=null,saving=false;
 const selectedIDs=()=>Array.from($('photo-blocks').querySelectorAll('[data-photo-block]:checked')).map(n=>Number(n.dataset.photoBlock));
 function rawSelected(){return selected.map(i=>job?.result.blocks[i]?.text||'').join('\n\n')}
 function binding(question){
  if(!bound||!data)return null;
  const draft=data.drafts.find(d=>d.revision===loadedRevision);
  return draft&&draft.question===question?{job_id:job.job_id,revision:draft.revision,source_fingerprint:data.source_fingerprint}:null;
 }
 function refresh(){
  $('photo-save-draft').disabled=!bound||!data||saving||!$('question').value.trim();
  $('photo-restore-draft').disabled=!data?.drafts.length;
  $('photo-notebook-original').innerHTML=MathView.prose(bound?rawSelected():(job?.result.text||''));
  $('photo-notebook-edited').innerHTML=MathView.prose(bound?$('question').value:'尚未从当前题图填入题干。');
  if(bound){const b=binding($('question').value);$('photo-draft-state').textContent=b?'当前题干对应本机第'+b.revision+'版；尚非教师审定。':'当前题干尚未保存为核对稿。';}
 }
 function historyView(){
  if(!data)return;
  $('photo-draft-history').innerHTML=data.drafts.length?data.drafts.slice(-10).reverse().map(d=>'<div class="path"><button class="source" data-draft-revision="'+d.revision+'">载入第'+d.revision+'版</button> <span class="muted">'+esc(d.saved_at)+(d.changed_from_selected_ocr?' · 有修改':' · 与所选OCR相同')+'</span><p>'+esc(d.note||'未填写修改说明')+'</p></div>').join(''):'尚未保存核对稿。';
  $('photo-search-history').innerHTML=data.searches.length?data.searches.slice(-5).reverse().map(r=>'<div class="path"><strong>第'+r.draft_revision+'版 · 第'+r.sequence+'次检索</strong><p class="muted">'+esc(r.searched_at)+' · '+esc(r.route||r.status||'')+'</p>'+(r.hits.slice(0,3).map((h,i)=>'<button class="source" data-detail="'+esc(h.id)+'">'+(i+1)+' · '+esc(h.label)+'</button>').join('')||'<p>未返回题目候选。</p>')+'</div>').join(''):'尚无关联检索。先保存核对稿，再点击“查找相关题”即可记录。';
 }
 function clear(){epoch++;job=null;data=null;selected=[];bound=false;loadedRevision=null;saving=false;$('photo-notebook').hidden=true;$('photo-draft-note').value='';$('photo-notebook-status').textContent='';$('photo-draft-state').textContent='';}
 function loadDraft(draft){
  selected=draft.selected_blocks.slice();bound=true;loadedRevision=draft.revision;
  for(const n of $('photo-blocks').querySelectorAll('[data-photo-block]'))n.checked=selected.includes(Number(n.dataset.photoBlock));
  $('question').value=draft.question;$('photo-draft-note').value=draft.note||'';
  $('photo-panel').open=false;$('photo-summary').textContent=' · 已恢复本机第'+draft.revision+'版，可展开原图';
  updateFormulaPreview();refresh();$('photo-notebook-status').textContent='已恢复本机第'+draft.revision+'版。没有自动查题；数学内容仍需核对。';
 }
 async function read(token){const response=await fetch('/api/photo-notebook?id='+encodeURIComponent(job.job_id));const value=await response.json();if(!response.ok)throw Error(value.error||'读取核对记录失败');if(token!==epoch)return null;return value;}
 async function attach(current,restore=false){
  clear();job=current;const token=epoch,initial=$('question').value;$('photo-notebook').hidden=false;
  $('photo-notebook-status').textContent='正在读取本机核对记录…';refresh();
  $('photo-notebook-download').href='/api/photo-notebook?id='+encodeURIComponent(job.job_id)+'&download=1';
  try{const value=await read(token);if(!value)return;data=value;historyView();
   if(restore&&!bound&&!initial.trim()&&!$('question').value.trim()&&data.drafts.length)loadDraft(data.drafts.at(-1));
   else{$('photo-notebook-status').textContent=data.drafts.length?'已找到保存的核对稿，可点击恢复；当前输入未被覆盖。':'选取OCR段落后，可编辑题干并保存本机核对稿。';refresh()}
  }catch(e){if(token===epoch)$('photo-notebook-status').textContent=e.message}
 }
 function copied(indices=selectedIDs()){selected=indices.slice();bound=true;loadedRevision=null;$('photo-draft-note').value='';refresh();}
 $('photo-save-draft').onclick=async()=>{
  if(!data||!bound||saving)return;
  const token=epoch,payload={job_id:job.job_id,source_fingerprint:data.source_fingerprint,expected_revision:data.revision,question:$('question').value,selected_blocks:selected.slice(),note:$('photo-draft-note').value};
  saving=true;refresh();$('photo-notebook-status').textContent='正在保存当前题干…';
  try{const response=await fetch('/api/photo-notebook',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});const value=await response.json();if(token!==epoch)return;
   if(!response.ok){
    if(response.status===409){const latest=await read(token);if(!latest)return;data=latest;historyView();throw Error('另一个页面更新了记录，已刷新版本信息并保留你的输入。请核对后再次保存。')}
    throw Error(value.error||'保存失败');
   }
   data=value;loadedRevision=data.revision;historyView();
   $('photo-notebook-status').textContent='已保存第'+data.revision+'版。原始OCR保留不变；点击查题可关联实际检索。';
  }catch(e){if(token===epoch)$('photo-notebook-status').textContent=e.message}
  finally{if(token===epoch){saving=false;refresh()}}
 };
 $('photo-restore-draft').onclick=()=>{if(data?.drafts.length)loadDraft(data.drafts.at(-1))};
 $('photo-draft-history').addEventListener('click',e=>{const target=e.target.closest('[data-draft-revision]');if(!target)return;const draft=data?.drafts.find(d=>d.revision===Number(target.dataset.draftRevision));if(draft)loadDraft(draft)});
 $('question').addEventListener('input',refresh);
 async function recorded(result,question){
  if(!result||!job||result.job_id&&result.job_id!==job.job_id)return;
  const token=epoch;
  $('photo-notebook-status').textContent=result.message;
  if(!result.saved)return;
  try{const value=await read(token);if(value&&token===epoch){data=value;historyView();refresh();if($('question').value!==question)$('photo-notebook-status').textContent='先前题干的检索已记录，当前输入已改变。'}}catch(e){if(token===epoch)$('photo-notebook-status').textContent='检索已完成，暂未刷新本机历史。'}
 }
 return {attach,clear,copied,binding,recorded};
})();
