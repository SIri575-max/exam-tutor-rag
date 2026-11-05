const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('problem_study.js','utf8');
const fn=source.slice(source.indexOf('async function studyRun(){'),source.indexOf("\ndocument.addEventListener('keydown'"));
const nodes=new Map(),$=id=>{if(!nodes.has(id))nodes.set(id,{value:'',textContent:'',innerHTML:'',disabled:false});return nodes.get(id)};
let resolveSearch,request;
const context={$,updateFormulaPreview(){},api(url,options){request=JSON.parse(options.body);return new Promise(resolve=>resolveSearch=resolve)},PhotoNotebook:{binding:()=>({job_id:'a',revision:1}),recorded(){}},studyPanel(){throw Error('Stale response must not be rendered')}};
vm.createContext(context);vm.runInContext('let studyRequest=0,current=[];\n'+fn,context);
(async()=>{
 $('question').value='保存的旧题';const run=context.studyRun();$('question').value='新的题干';resolveSearch({hits:[]});await run;
 assert.equal(request.question,'保存的旧题');assert.equal(request.photo_draft.revision,1);
 assert.equal($('results').innerHTML,'');assert($('summary').textContent.includes('题干已改变'));assert.equal($('run').disabled,false);
 console.log('Edited-during-retrieval result discard check passed');
})().catch(error=>{console.error(error);process.exitCode=1});
