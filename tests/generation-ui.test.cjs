const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const fragment=fs.readFileSync('generation_ui.js','utf8');
function harness(){
 const nodes=new Map(),$=id=>{if(!nodes.has(id))nodes.set(id,{value:'',checked:false,disabled:false,textContent:'',innerHTML:'',addEventListener(){}});return nodes.get(id)};
 let resolve;
 const context={$,esc:String,renderQuestion:String,AnswerView:{render:String},pageLinks:()=>'',api(url,options){if(url==='/api/model-status')return Promise.resolve({enabled:true,configured:true});if(url==='/api/generation-records')return Promise.resolve({runs:[]});assert.equal(options.method,'POST');assert.equal(options.headers['Content-Type'],'application/json');assert.equal(JSON.parse(options.body).question,$('question').value);assert(!('mode' in options),'hybrid must be JSON data, not a fetch RequestMode');return new Promise(r=>resolve=r)}};
 vm.createContext(context);vm.runInContext(fragment,context);
 return {$,answer:d=>resolve(d)};
}
(async()=>{
 const response={record_saved:true,run_id:'a'.repeat(32),teaching:{used:true,text:'结论[E1]',citation_ids:['E1']},evidence:[{id:'E1',pages:[302],text:'证据',title:'教材'}]};
 {const h=harness();await new Promise(setImmediate);h.$('question').value='原始题目';h.$('allow-generation').checked=true;h.$('allow-generation').onchange();
  const run=h.$('explain').onclick();h.$('allow-generation').checked=false;h.$('allow-generation').onchange();h.$('allow-generation').checked=true;h.$('allow-generation').onchange();
  assert.equal(h.$('explain').disabled,true,'checking again must not reenable an in-flight call');h.answer(response);await run;
  assert.equal(h.$('explain').disabled,false);assert(h.$('teaching-output').innerHTML.includes('/portfolio?run='));}
 {const h=harness();await new Promise(setImmediate);h.$('question').value='旧问题';h.$('allow-generation').checked=true;
  const run=h.$('explain').onclick();h.$('question').value='新问题';h.answer(response);await run;
  assert(h.$('teaching-output').textContent.includes('题目已变化'));assert(!h.$('teaching-output').innerHTML.includes('结论'));}
 console.log('Generation JSON POST, in-flight toggle, saved-record link and stale-question checks passed');
})().catch(error=>{console.error(error);process.exitCode=1});
