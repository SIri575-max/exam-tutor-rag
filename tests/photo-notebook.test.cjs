const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
function harness(){
 const nodes=new Map(),pending=[],calls=[];
 const blocks=[{dataset:{photoBlock:'0'},checked:true}];
 const $=id=>{if(!nodes.has(id))nodes.set(id,{value:'',innerHTML:'',textContent:'',hidden:true,disabled:false,listeners:{},addEventListener(name,fn){this.listeners[name]=fn},querySelectorAll(selector){return selector.includes(':checked')?blocks.filter(b=>b.checked):blocks}});return nodes.get(id)};
 const context={$,esc:String,MathView:{prose:String},updateFormulaPreview(){},fetch(url,options){calls.push({url,options});return new Promise(resolve=>pending.push(resolve))}};
 vm.createContext(context);vm.runInContext(fs.readFileSync('photo_notebook.js','utf8'),context);
 const api=vm.runInContext('PhotoNotebook',context);
 const reply=(data,status=200)=>pending.shift()({ok:status<400,status,json:async()=>data});
 return {$,api,reply,calls};
}
const job={job_id:'a'.repeat(32),result:{text:'原始参数ρ',blocks:[{text:'原始参数ρ'}]}};
const state=(drafts=[])=>({source_fingerprint:'fingerprint',revision:drafts.length,drafts,searches:[]});
const draft=(question,revision=1)=>({revision,question,selected_blocks:[0],note:'对照原图统一参数',saved_at:'local',changed_from_selected_ocr:true});
(async()=>{
 {const h=harness(),load=h.api.attach(job,true);h.reply(state([draft('修改后的p')]));await load;
  assert.equal(h.$('question').value,'修改后的p');assert.equal(h.api.binding('修改后的p').revision,1);
  assert.equal(h.calls.length,1,'Restoring a draft must not submit search or generation');}
 {const h=harness(),load=h.api.attach(job,true);h.$('question').value='正在手动输入';h.reply(state([draft('旧的已保存稿')]));await load;
  assert.equal(h.$('question').value,'正在手动输入','Late loading must not overwrite active typing');}
 {const h=harness(),old=h.api.attach(job,true),newer=h.api.attach({...job,job_id:'b'.repeat(32)},true);
  h.reply(state([draft('旧任务稿')]));await old;assert.equal(h.$('question').value,'');
  h.reply(state([draft('新任务稿')]));await newer;assert.equal(h.$('question').value,'新任务稿');}
 {const h=harness(),load=h.api.attach(job);h.reply(state());await load;h.$('question').value='当前修改p';h.api.copied([0]);
  const save=h.$('photo-save-draft').onclick();assert.equal(JSON.parse(h.calls[1].options.body).question,'当前修改p');
  h.$('question').value='保存期间继续编辑';h.$('question').listeners.input();h.reply(state([draft('当前修改p')]));await save;
  assert.equal(h.$('question').value,'保存期间继续编辑');assert.equal(h.api.binding(h.$('question').value),null);
  assert.equal(h.$('photo-notebook-original').innerHTML,'原始参数ρ');
  assert(!h.calls.some(c=>c.url.includes('problem-study')));}
 {const h=harness(),load=h.api.attach(job);h.reply(state());await load;h.$('question').value='保留本页输入';h.api.copied([0]);
  const save=h.$('photo-save-draft').onclick();h.reply({error:'conflict'},409);
  await new Promise(setImmediate);
  h.reply(state([draft('另一页面保存稿')]));await save;
  assert.equal(h.$('question').value,'保留本页输入');assert(h.$('photo-notebook-status').textContent.includes('保留你的输入'));}
 console.log('Notebook restore, active typing, source race, in-flight save and conflict checks passed');
})().catch(error=>{console.error(error);process.exitCode=1});
