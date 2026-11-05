/* Presentation-only state: no network requests, credentials or generated data. */
(function(){
'use strict';
const node=id=>document.getElementById(id),menu=node('mobile-menu'),sidebar=node('workspace-sidebar'),backdrop=node('nav-backdrop');
function nav(open){document.body.dataset.navOpen=String(open);menu.setAttribute('aria-expanded',String(open));menu.setAttribute('aria-label',open?'关闭导航':'打开导航');backdrop.hidden=!open;if(open)requestAnimationFrame(()=>sidebar.querySelector('a').focus());else menu.focus();}
menu.addEventListener('click',()=>nav(menu.getAttribute('aria-expanded')!=='true'));
backdrop.addEventListener('click',()=>nav(false));
sidebar.addEventListener('click',e=>{if(e.target.closest('a,button')&&menu.getAttribute('aria-expanded')==='true')nav(false);});
document.addEventListener('keydown',e=>{if(menu.getAttribute('aria-expanded')!=='true')return;if(e.key==='Escape'){e.preventDefault();nav(false);}if(e.key==='Tab'){const focusable=[...sidebar.querySelectorAll('a,button')],first=focusable[0],last=focusable.at(-1);if(!sidebar.contains(document.activeElement)){e.preventDefault();first.focus();}else if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}}});
function sync(){
 node('question-count').textContent=String(node('question').value.length);
 const selected=node('chapter').selectedOptions[0]?.textContent||'全书';
 node('filter-summary').textContent=(node('chapter').value?selected.replace(/\s.*/, ''):'全书')+' · '+({'all':'两类题目','exercise':'课后题','example':'例题'}[node('kind').value]||'题目');
 const pending=node('run').disabled&&node('summary').textContent.includes('正在');
 node('loading-view').hidden=!pending;
 node('clue-details').hidden=pending||!node('formula-analysis').children.length;
 const count=node('results').querySelectorAll('article').length;
 node('match-details').hidden=pending||count===0;
 node('match-total').textContent=count?'· '+count+' 条':'';
 node('study-journey').dataset.stage=node('study-brief').querySelector('.correspondence-panel')?'ready':'input';
}
node('question').addEventListener('input',sync);node('kind').addEventListener('change',sync);node('chapter').addEventListener('change',sync);
const observer=new MutationObserver(sync);
for(const id of ['summary','results','formula-analysis','study-brief'])observer.observe(node(id),{childList:true,subtree:true,characterData:true});
observer.observe(node('run'),{attributes:true,attributeFilter:['disabled']});sync();
window.matchMedia('(max-width:760px)').addEventListener('change',e=>{if(!e.matches&&menu.getAttribute('aria-expanded')==='true'){nav(false);node('question').focus();}});
})();
