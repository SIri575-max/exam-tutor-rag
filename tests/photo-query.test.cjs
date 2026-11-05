/* Check the review boundary and stale upload race without running an OCR engine. */
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const nodes=new Map();
const node=id=>{if(!nodes.has(id))nodes.set(id,{value:'',textContent:'',innerHTML:'',disabled:false,hidden:false,listeners:{},addEventListener(e,f){this.listeners[e]=f},removeAttribute(){},focus(){},querySelectorAll(){return [{dataset:{photoBlock:'0'}}]}});return nodes.get(id)};
let resolveUpload,requests=0,previews=0;
const context={$:node,esc:String,MathView:{prose:x=>x},URL:{createObjectURL:()=>'/local-object',revokeObjectURL(){}},
 URLSearchParams,location:{search:'',pathname:'/problems'},history:{replaceState(){}},
 PhotoCrop:{setSource(){},options:()=>({crop:null,rotation:0}),onChange(){}},
 PhotoNotebook:{clear(){},attach(){},copied(){}},
 updateFormulaPreview:()=>previews++,setTimeout,
 fetch:()=>{requests++;return new Promise(resolve=>{resolveUpload=resolve})}};
vm.createContext(context);vm.runInContext(fs.readFileSync('photo_query.js','utf8'),context);
(async()=>{
 const ready={job_id:'a'.repeat(32),status:'ready',message:'ready',image_url:'/api/photo-image?id=x',elapsed_seconds:1,
 result:{text:'raw',blocks:[{text:'$X_1$来自均匀分布'}]}};
 node('photo-file').files=[{type:'image/png',size:100}];node('photo-file').listeners.change();
 let upload=node('photo-start').onclick();
 node('photo-reset').onclick();
 resolveUpload({ok:true,json:async()=>ready});await upload;
 assert.equal(node('photo-review').hidden,true,'A reset must discard late OCR');
 assert.equal(node('question').value,'');
 node('photo-file').files=[{type:'image/jpeg',size:100}];node('photo-file').listeners.change();
 upload=node('photo-start').onclick();resolveUpload({ok:true,json:async()=>ready});await upload;
 assert.equal(node('photo-review').hidden,false);
 assert.equal(node('question').value,'','OCR must not overwrite an existing query until explicit use');
 node('photo-use').onclick();
 assert.equal(node('question').value,'$X_1$来自均匀分布');
 assert.equal(requests,2,'Using OCR draft must not invoke search or generation');
 assert.equal(previews,1);
 console.log('Photo review, explicit copy and stale upload checks passed');
})().catch(e=>{console.error(e);process.exitCode=1});
