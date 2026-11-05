/* Coordinates are normalized AFTER EXIF orientation and explicit clockwise rotation. */
(function(root){
 'use strict';
 const clamp=n=>Math.max(0,Math.min(1,n));
 const box=(a,b)=>[Math.min(clamp(a[0]),clamp(b[0])),Math.min(clamp(a[1]),clamp(b[1])),Math.max(clamp(a[0]),clamp(b[0])),Math.max(clamp(a[1]),clamp(b[1]))];
 const point=(x,y,r)=>[clamp((x-r.left)/r.width),clamp((y-r.top)/r.height)];
 if(typeof module!=='undefined')module.exports={box,point};
 if(!root.document)return;
 let source='',image=null,rotation=0,region=[0,0,1,1],saved={crop:null,rotation:0},start=null,listener=()=>{};
 const canvas=$('photo-crop-canvas'),ctx=canvas.getContext('2d');
 const fields=['crop-left','crop-top','crop-right','crop-bottom'];
 function sync(){fields.forEach((id,i)=>$(id).value=String(Math.round(region[i]*10000)/100));$('photo-crop-angle').textContent='顺时针旋转 '+rotation+'°'}
 function draw(){
  if(!image)return;
  const rotated=rotation===90||rotation===270,w=rotated?image.naturalHeight:image.naturalWidth,h=rotated?image.naturalWidth:image.naturalHeight;
  const scale=Math.min(1,900/w,430/h);canvas.width=Math.round(w*scale);canvas.height=Math.round(h*scale);
  ctx.save();ctx.translate(canvas.width/2,canvas.height/2);ctx.rotate(rotation*Math.PI/180);
  ctx.drawImage(image,-image.naturalWidth*scale/2,-image.naturalHeight*scale/2,image.naturalWidth*scale,image.naturalHeight*scale);ctx.restore();
  const [l,t,r,b]=region,x=l*canvas.width,y=t*canvas.height,rw=(r-l)*canvas.width,rh=(b-t)*canvas.height;
  ctx.beginPath();ctx.rect(0,0,canvas.width,canvas.height);ctx.rect(x,y,rw,rh);ctx.fillStyle='#132f4088';ctx.fill('evenodd');
  ctx.strokeStyle='#00d7ba';ctx.lineWidth=2;ctx.strokeRect(x,y,rw,rh);
  paintSelection($('photo-crop-preview'),680,360);
 }
 async function open(){
  if(!source)return;
  $('photo-crop-error').textContent='';rotation=saved.rotation;region=saved.crop?.slice()||[0,0,1,1];
  const requested=source,img=new Image();
  $('photo-crop').disabled=true;
  try{await new Promise((resolve,reject)=>{img.onload=resolve;img.onerror=()=>reject(Error('原图无法读取，请重新上传'));img.src=requested});
   if(requested!==source)return;image=img;sync();draw();$('photo-crop-viewer').showModal();
  }catch(e){$('photo-status').textContent=e.message}finally{$('photo-crop').disabled=false}
 }
 function paintSelection(out,maxWidth,maxHeight){
  if(!image)return;
  const rotated=rotation===90||rotation===270,w=rotated?image.naturalHeight:image.naturalWidth,h=rotated?image.naturalWidth:image.naturalHeight;
  const [l,t,r,b]=region,sw=(r-l)*w,sh=(b-t)*h;
  if(sw<=0||sh<=0){out.width=1;out.height=1;return}
  const scale=Math.min(1,maxWidth/sw,maxHeight/sh);
  out.width=Math.max(1,Math.round(sw*scale));out.height=Math.max(1,Math.round(sh*scale));const c=out.getContext('2d');
  c.fillStyle='white';c.fillRect(0,0,out.width,out.height);
  c.translate((w/2-l*w)*scale,(h/2-t*h)*scale);c.rotate(rotation*Math.PI/180);
  c.drawImage(image,-image.naturalWidth*scale/2,-image.naturalHeight*scale/2,image.naturalWidth*scale,image.naturalHeight*scale);
 }
 function preview(){
  if(!image)return source;
  const out=document.createElement('canvas');paintSelection(out,1200,1200);
  return out.toDataURL('image/png');
 }
 function rotate(delta){rotation=(rotation+delta+360)%360;region=[0,0,1,1];sync();draw();$('photo-crop-error').textContent='方向已调整，请重新框选题干。'}
 canvas.addEventListener('pointerdown',e=>{if(e.button!==0)return;e.preventDefault();start=point(e.clientX,e.clientY,canvas.getBoundingClientRect());canvas.setPointerCapture(e.pointerId)});
 canvas.addEventListener('pointermove',e=>{if(!start)return;region=box(start,point(e.clientX,e.clientY,canvas.getBoundingClientRect()));sync();draw()});
 const finish=e=>{if(!start)return;region=box(start,point(e.clientX,e.clientY,canvas.getBoundingClientRect()));start=null;sync();draw()};
 canvas.addEventListener('pointerup',finish);canvas.addEventListener('pointercancel',()=>{start=null});
 fields.forEach(id=>$(id).addEventListener('input',()=>{
  const values=fields.map(name=>Number($(name).value)/100);
  if(values.every(Number.isFinite)&&values.every(v=>v>=0&&v<=1)&&values[0]<values[2]&&values[1]<values[3]){region=values;draw();$('photo-crop-error').textContent=''}
  else $('photo-crop-error').textContent='请填写0—100之间的边界，左小于右、上小于下。';
 }));
 $('photo-crop').onclick=open;
 $('crop-rotate-left').onclick=()=>rotate(-90);$('crop-rotate-right').onclick=()=>rotate(90);
 $('crop-whole').onclick=()=>{region=[0,0,1,1];sync();draw();$('photo-crop-error').textContent='已选中整图。'};
 $('crop-cancel').onclick=()=>$('photo-crop-viewer').close();
 $('crop-apply').onclick=()=>{
  const values=fields.map(id=>Number($(id).value)/100);
  if(!image||!values.every(Number.isFinite)||values.some(v=>v<0||v>1)||values[0]>=values[2]||values[1]>=values[3]){$('photo-crop-error').textContent='请先设置有效选框。';return}
  const rotated=rotation===90||rotation===270,w=rotated?image.naturalHeight:image.naturalWidth,h=rotated?image.naturalWidth:image.naturalHeight;
  if((values[2]-values[0])*w<40||(values[3]-values[1])*h<40){$('photo-crop-error').textContent='选框太小，请保留完整题干与公式。';return}
  region=values;saved={crop:values.every((v,i)=>v===[0,0,1,1][i])?null:values.slice(),rotation};
  const cropped=preview();$('photo-crop-viewer').close();listener(saved,cropped);
 };
 root.PhotoCrop={setSource(url,options={}){source=url||'';image=null;saved={crop:options.crop?.slice()||null,rotation:options.rotation_clockwise||0};$('photo-crop').hidden=!source},
  options:()=>({crop:saved.crop?.slice()||null,rotation:saved.rotation}),onChange(fn){listener=fn}};
})(typeof window!=='undefined'?window:globalThis);
