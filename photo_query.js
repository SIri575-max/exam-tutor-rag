/* Image data is an untrusted query, never a source document or an instruction. */
let photoRevision=0,photoFile=null,photoURL=null,photoResult=null,photoSourceJob=null;
function photoRegionLabel(options){return (options.crop?'已框选单题区域':'整张图片')+' · 顺时针旋转 '+options.rotation+'°'}
function rememberPhoto(id){const params=new URLSearchParams(location.search);if(id){params.set('photo',id);params.delete('q')}else params.delete('photo');history.replaceState(null,'',location.pathname+(params.size?'?'+params.toString():''))}
function resetPhoto(){
 PhotoNotebook.clear();
 photoRevision++;photoFile=null;photoResult=null;photoSourceJob=null;PhotoCrop.setSource('');
 if(photoURL)URL.revokeObjectURL(photoURL);photoURL=null;
 $('photo-file').value='';$('photo-preview').hidden=true;$('photo-zoom').hidden=true;$('photo-preview').removeAttribute('src');
 $('photo-review').hidden=true;$('photo-blocks').innerHTML='';$('photo-raw').textContent='';
 $('photo-start').disabled=true;$('photo-reset').hidden=true;
 $('photo-summary').textContent='';$('photo-panel').open=true;
 $('photo-status').textContent='本机OCR，题图不发送到模型服务。';
 $('photo-region').textContent='默认识别整张图片，可先框选题干，避开题解。';
 rememberPhoto(null);
}
$('photo-file').addEventListener('change',()=>{
 PhotoNotebook.clear();
 const file=$('photo-file').files[0];photoRevision++;photoResult=null;
 photoSourceJob=null;PhotoCrop.setSource('');$('photo-crop').disabled=false;
 rememberPhoto(null);
 $('photo-summary').textContent='';
 $('photo-review').hidden=true;$('photo-blocks').innerHTML='';$('photo-raw').textContent='';
 if(photoURL)URL.revokeObjectURL(photoURL);photoURL=null;photoFile=null;
 $('photo-preview').hidden=true;$('photo-zoom').hidden=true;$('photo-start').disabled=true;
 if(!file){$('photo-status').textContent='请选择单张题图。';return}
 $('photo-reset').hidden=false;
 if(!['image/jpeg','image/png','image/webp'].includes(file.type)||file.size>12*1024*1024){$('photo-status').textContent='请选择不超过12MB的PNG、JPEG或WebP题图。';return}
 photoFile=file;photoURL=URL.createObjectURL(file);$('photo-preview').src=photoURL;
 PhotoCrop.setSource(photoURL);$('photo-region').textContent='默认识别整张图片，可先框选题干，避开题解。';
 $('photo-preview').hidden=false;$('photo-zoom').hidden=false;$('photo-start').disabled=false;
 $('photo-status').textContent='图片已选好。点击识别后，再核对文字与公式。';
});
$('photo-reset').onclick=resetPhoto;
$('photo-zoom').onclick=()=>{$('photo-large-image').src=$('photo-preview').src;$('photo-image-viewer').showModal()};
$('photo-close-image').onclick=()=>$('photo-image-viewer').close();
function displayPhotoResult(job,restoreDraft=false){
 photoSourceJob=job.job_id;PhotoCrop.setSource(job.full_image_url||job.image_url+'&view=full',job.preprocessing||{});
 $('photo-region').textContent=photoRegionLabel(PhotoCrop.options());$('photo-start').disabled=false;
 photoResult=job.result;$('photo-preview').src=job.image_url;$('photo-zoom').hidden=false;
 $('photo-status').textContent='识别完成 · '+job.elapsed_seconds+'秒 · 尚未人工核对，也未自动查题。';
 $('photo-raw').textContent=photoResult.text;
 $('photo-blocks').innerHTML=photoResult.blocks.map((b,i)=>'<div class="path"><label><input type="checkbox" data-photo-block="'+i+'" checked> 保留段落 '+(i+1)+'</label>'+(b.warnings||[]).map(w=>'<p class="notice">'+esc(w)+'</p>').join('')+'<div class="prose">'+MathView.prose(b.text)+'</div></div>').join('');
 $('photo-review').hidden=false;
 $('photo-summary').textContent=' · 已识别，待核对';
 PhotoNotebook.attach(job,restoreDraft);
}
$('photo-start').onclick=async()=>{
 if(!photoFile&&!photoSourceJob)return;
 const revision=++photoRevision,file=photoFile;photoResult=null;
 PhotoNotebook.clear();
 $('photo-start').disabled=true;$('photo-crop').disabled=true;$('photo-review').hidden=true;
 $('photo-status').textContent='正在将题图交给本机OCR…';
 try{
  const options=PhotoCrop.options();
  let response=file?await fetch('/api/photo-ocr',{method:'POST',headers:{'Content-Type':file.type,'X-Photo-Crop':JSON.stringify(options.crop),'X-Photo-Rotation':String(options.rotation)},body:file}):await fetch('/api/photo-retry',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({job_id:photoSourceJob,...options})});
  let job=await response.json();if(!response.ok)throw Error(job.error||'上传未成功');
  if(revision!==photoRevision)return;photoSourceJob=job.job_id;rememberPhoto(job.job_id);
  while(revision===photoRevision){
   $('photo-status').textContent=job.message;
   if(job.status==='ready'){displayPhotoResult(job);return}
   if(job.status==='failed')throw Error(job.message);
   await new Promise(resolve=>setTimeout(resolve,1600));if(revision!==photoRevision)return;
   response=await fetch('/api/photo-ocr?id='+encodeURIComponent(job.job_id));job=await response.json();
   if(!response.ok)throw Error(job.error||'无法读取识别任务');
  }
 }catch(e){if(revision===photoRevision)$('photo-status').textContent=e.message}
 finally{if(revision===photoRevision){$('photo-start').disabled=false;$('photo-crop').disabled=false}}
};
PhotoCrop.onChange((options,preview)=>{
 PhotoNotebook.clear();
 photoRevision++;photoResult=null;rememberPhoto(null);$('photo-review').hidden=true;
 $('photo-preview').src=preview;$('photo-region').textContent=photoRegionLabel(options);
 $('photo-start').disabled=false;$('photo-summary').textContent=' · 选框已应用，待识别';
 $('photo-status').textContent='选框已应用。点击“识别文字与公式”后，再核对识别稿。';
});
$('photo-use').onclick=()=>{
 if(!photoResult)return;
 const indices=Array.from($('photo-blocks').querySelectorAll('[data-photo-block]:checked')).map(n=>Number(n.dataset.photoBlock));
 if(!indices.length){$('photo-status').textContent='请至少选择一段题干。';return}
 // The explicit click copies text only. Search is a separate, user-triggered action.
 $('question').value=indices.map(i=>photoResult.blocks[i].text).join('\n\n');
 updateFormulaPreview();$('question').focus();
 PhotoNotebook.copied(indices);
 $('photo-panel').open=false;$('photo-summary').textContent=' · 已填入，可展开对照原图';
 $('photo-status').textContent='已填入题干。请核对数字、符号与完整条件，再点击“查找相关题”。';
};
// Refreshing the page restores the local job, but never submits the recognized query.
const photoInitialId=new URLSearchParams(location.search).get('photo');
if(photoInitialId&&/^[a-f0-9]{32}$/.test(photoInitialId)){
 (async()=>{const revision=++photoRevision;
  try{while(revision===photoRevision){
   const response=await fetch('/api/photo-ocr?id='+encodeURIComponent(photoInitialId));const job=await response.json();
   if(revision!==photoRevision)return;if(!response.ok)throw Error(job.error||'无法恢复识别任务');
   $('photo-preview').src=job.image_url;$('photo-preview').hidden=false;$('photo-reset').hidden=false;
   $('photo-status').textContent=job.message;
   if(job.status==='ready'){displayPhotoResult(job,true);return}
   if(job.status==='failed')throw Error(job.message);
   await new Promise(resolve=>setTimeout(resolve,1600));
  }}catch(e){if(revision===photoRevision)$('photo-status').textContent=e.message}
 })();
}
