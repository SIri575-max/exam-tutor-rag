const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
function harness(){
 const nodes=new Map(),pending=[],calls=[],$=id=>{if(!nodes.has(id))nodes.set(id,{value:'当前题干',checked:true,disabled:false,textContent:'',innerHTML:'',addEventListener(){}});return nodes.get(id)};
 const c={$,esc:String,AnswerView:{render:String},renderQuestion:String,pageLinks:()=>'',api(url,options){calls.push({url,options});if(url==='/api/model-status')return Promise.resolve({enabled:true,configured:true});if(url==='/api/generation-records')return Promise.resolve({runs:[]});return new Promise(resolve=>pending.push({url,resolve}))}};
 vm.createContext(c);vm.runInContext(fs.readFileSync('generation_ui.js','utf8'),c);
 return {$,c,pending,calls};
}
const record=(id,text)=>({id,question:'历史题干'+id,created_at:'2026-10-27',evidence:[],teaching:{used:true,text,citation_ids:[]}});
(async()=>{
 {const h=harness();await new Promise(setImmediate);const a=h.c.loadSavedTeaching('a'),b=h.c.loadSavedTeaching('b');
  h.pending[1].resolve(record('b','回答B'));await b;h.pending[0].resolve(record('a','回答A'));await a;
  assert(h.$('teaching-output').innerHTML.includes('回答B'));assert(!h.$('teaching-output').innerHTML.includes('回答A'));
  assert.equal(h.$('question').value,'当前题干');assert(!h.calls.some(c=>c.options?.method==='POST'),'replay must not call the model');}
 {const h=harness();await new Promise(setImmediate);const a=h.c.loadSavedTeaching('a');h.c.invalidateTeaching();h.pending[0].resolve(record('a','旧回答'));await a;assert.equal(h.$('teaching-output').innerHTML,'');}
 {const h=harness();await new Promise(setImmediate);const a=h.c.loadSavedTeaching('a'),g=h.$('explain').onclick();
  h.pending[0].resolve(record('a','旧回答'));await a;assert(!h.$('teaching-output').innerHTML.includes('旧回答'));
  h.pending[1].resolve({...record('n','本次新回答'),record_saved:true,run_id:'n'});await g;
  assert(h.$('teaching-output').innerHTML.includes('本次新回答'));
  assert.equal(h.calls.filter(c=>c.options?.method==='POST').length,1);}
 console.log('History replay, selection race, query reset and generation priority checks passed');
})().catch(e=>{console.error(e);process.exitCode=1});
