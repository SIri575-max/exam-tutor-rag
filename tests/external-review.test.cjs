const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const text=fs.readFileSync('external_review.js','utf8');
const funcs=text.slice(text.indexOf('async function load(id){'),text.indexOf("window.addEventListener('beforeunload'"));
function setup(){
 const fields={};const $=s=>fields[s]??=( {value:'',checked:false,style:{},inert:false,disabled:false} );
 const grade0={dataset:{grade:'r0'},value:'0'},blank={dataset:{grade:'r1'},value:''};
 const controls=[grade0,blank,$('#reviewer'),$('#family'),$('#ocr-checked'),$('#notes')];
 $('#content').querySelectorAll=s=>s==='[data-grade]'?[grade0,blank]:controls;
 let renders=0,requests=[],resolvers=[],messages=[];
 const context={$,
  MathView:{register:x=>x},window:{confirm:()=>false,history:{replaceState:()=>{}}},
  api:(url,options)=>{requests.push({url,options});return new Promise((resolve,reject)=>resolvers.push({resolve,reject}));},
  renderCase:()=>renders++,renderList:()=>{},renderOverview:()=>{},message:(...a)=>messages.push(a)};
 vm.createContext(context);
 vm.runInContext('let current={case_id:"660b-c1-q001",report_sha256:"frozen",state:{revision:0}};let catalog={cases:[{case_id:"660b-c1-q001"}]};let dirty=true,loading=0,saving=false;'+funcs,context);
 return {context,fields,$,controls,requests,resolvers,messages,renders:()=>renders,state:()=>vm.runInContext('({current,dirty,loading,saving})',context)};
}
(async()=>{
 let s=setup();s.$('#reviewer').value='审核人';s.$('#ocr-checked').checked=true;
 let pending=s.context.save('draft');assert(s.controls.every(c=>c.disabled));assert.equal(s.requests.length,1);
 await s.context.save('approved');assert.equal(s.requests.length,1,'double submission blocked');
 let body=JSON.parse(s.requests[0].options.body);assert.equal(body.status,'draft');assert.equal(body.grades.r0,0);assert.equal(body.grades.r1,null);assert.equal(body.ocr_checked,true);
 s.resolvers[0].reject(Error('conflict'));await pending;
 assert.equal(s.state().dirty,true);assert.equal(s.state().current.state.revision,0);assert(s.controls.every(c=>!c.disabled));assert.equal(s.renders(),0);
 pending=s.context.save('draft');s.resolvers[1].resolve({revision:1});await pending;
 assert.equal(s.state().dirty,false);assert.equal(s.state().current.state.revision,1);assert.equal(s.renders(),1);
 s=setup();await s.context.load('next');assert.equal(s.requests.length,0,'unsaved changes kept when switching cancelled');
 vm.runInContext('dirty=false',s.context);
 const first=s.context.load('first');assert.equal(s.$('#content').inert,true);
 const second=s.context.load('second');s.resolvers[1].resolve({case_id:'second',state:{revision:0}});await second;
 s.resolvers[0].resolve({case_id:'first',state:{revision:0}});await first;
 assert.equal(s.state().current.case_id,'second');assert.equal(s.renders(),1);assert.equal(s.$('#content').inert,false);
 const nav={$:s=>({value:({'#chapter':'','#filter':'source','#find':'末尾关键词'})[s]||''}),
  catalog:{cases:[{case_id:'a',search_text:'前'.repeat(120)+'末尾关键词',source_checks:['跨页'],status:'draft'},
                  {case_id:'b',search_text:'末尾关键词',source_checks:[],status:'pending'}]},
  current:{case_id:'a'},saving:false,message:()=>{},load:id=>id};
 vm.createContext(nav);
 vm.runInContext(text.slice(text.indexOf('function filteredCases(){'),text.indexOf('function renderList(){'))+
                 text.slice(text.indexOf('function nextPending(){'),text.indexOf('async function load(id){')),nav);
 assert.deepEqual(Array.from(nav.filteredCases(),c=>c.case_id),['a'],'full text search and source-only filter');
 nav.$=s=>({value:({'#chapter':'','#filter':'pending','#find':''})[s]||''});
 nav.catalog.cases=[{case_id:'a',status:'draft'},{case_id:'b',status:'approved'},{case_id:'c',status:'pending'}];
 assert.equal(nav.nextPending(),'c','next skips approved within filter');nav.current={case_id:'c'};
 assert.equal(nav.nextPending(),'a','next wraps and includes drafts without approving');
 nav.saving=true;assert.equal(nav.nextPending(),undefined);
 console.log('External review: typed grades, draft isolation, duplicate save, conflict preservation, cancelled switch and stale-load checks passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
