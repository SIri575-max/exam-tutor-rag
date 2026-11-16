'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const kinds = {chapter:'章',section:'节',topic:'知识条目',example:'例题',exercise:'课后题',definition:'定义',theorem:'定理',property:'性质',lemma:'引理',corollary:'推论'};
  const NS = 'http://www.w3.org/2000/svg';
  let data, requestVersion = 0, selected = '';
  function el(tag, text, cls) { const e = document.createElement(tag); if(text)e.textContent=text; if(cls)e.className=cls; return e; }
  function svg(tag, attrs, text) { const e=document.createElementNS(NS,tag); Object.entries(attrs).forEach(([k,v])=>e.setAttribute(k,v)); if(text)e.textContent=text; return e; }
  function color(n) { return n.kind==='exercise'?'#be8a49':['example','definition','theorem','property','lemma','corollary'].includes(n.kind)?'#5877ae':'#267457'; }
  function label(n) { const match=n.id.match(/^(?:definition|theorem|property|lemma|corollary)-(\d+(?:\.\d+)+)$/);return match?(kinds[n.kind]+' '+match[1]):n.label; }
  function review(edge) { return ['contains_section','contains_topic'].includes(edge.kind)?'教材目录层级，页码位置可回看核对':edge.kind==='mentions_topic'?'自动字面关联，考点待核验':['literal_example_mention','data_or_continuation_reference'].includes(edge.kind)?'原文引用候选，待核验':'教材位置关联，未核定为考点'; }
  function pages(container, values) { const box=el('div','','pages'); (values||[]).forEach(p=>{const a=el('a','PDF '+p); a.href='/library#page='+encodeURIComponent(p); a.target='_blank'; a.rel='noopener'; box.append(a);}); container.append(box); }
  function details(id) {
    selected=id; const n=data.nodes.find(x=>x.id===id); const box=$('details'); box.replaceChildren();
    box.append(el('span',kinds[n.kind]||n.kind,'pill'),el('h2',label(n))); pages(box,n.pages);
    const expand=el('button','展开此节点','primary'); expand.onclick=()=>load(id); box.append(expand);
    const edges=data.edges.filter(e=>e.from===id||e.to===id);
    box.append(el('p',edges.length+' 条可见关联','muted'));
    const names=Object.fromEntries(data.nodes.map(x=>[x.id,label(x)]));
    edges.forEach(e=>{const row=el('div','','edge');row.append(el('strong',e.relation_label),el('p',names[e.from]+' → '+names[e.to]));if(e.quote)row.append(el('div',e.quote,'quote'));pages(row,e.source_pages);row.append(el('p',review(e),'muted'));box.append(row);});
    draw();
  }
  function draw() {
    const box=$('canvas'); box.replaceChildren();
    if(!data.nodes.length){box.append(el('p','没有找到对应条目，请尝试明确的知识点或教材题号。','empty'));return;}
    const groups=new Map();data.nodes.forEach(n=>{const group=data.seed_ids.includes(n.id)?0:['chapter','section','topic'].includes(n.kind)?1:2; if(!groups.has(group))groups.set(group,[]);groups.get(group).push(n);});
    const columns=[...groups.keys()].sort();const height=Math.max(520,...[...groups.values()].map(g=>g.length*77+60));const width=Math.max(780,box.clientWidth);const positions={};
    columns.forEach((c,i)=>groups.get(c).forEach((n,j)=>{const columnHeight=Math.max(420,groups.get(c).length*77);positions[n.id]={x:columns.length===1?width/2:125+i*(width-250)/(columns.length-1),y:35+(j+.5)*columnHeight/groups.get(c).length};}));
    const root=svg('svg',{width,height,role:'group','aria-label':'教材关联图，节点可点击或使用Tab键选择'});
    const defs=svg('defs',{});const marker=svg('marker',{id:'arrow',viewBox:'0 0 10 10',refX:9,refY:5,markerWidth:5,markerHeight:5,orient:'auto-start-reverse'});marker.append(svg('path',{d:'M0 0 L10 5 L0 10 z',fill:'#b5c9bd'}));defs.append(marker);root.append(defs);
    data.edges.forEach(e=>{const a=positions[e.from],b=positions[e.to]; if(!a||!b)return;const mid=(a.x+b.x)/2;const line=svg('path',{d:`M${a.x} ${a.y} C${mid} ${a.y},${mid} ${b.y},${b.x} ${b.y}`,fill:'none',stroke:e.from===selected||e.to===selected?'#5a967c':'#ccdcd1','stroke-width':e.from===selected||e.to===selected?2:1.2,'marker-end':'url(#arrow)'});line.append(svg('title',{},e.relation_label));root.append(line);});
    data.nodes.forEach(n=>{const p=positions[n.id],c=color(n),title=label(n);const g=svg('g',{role:'button',tabindex:0,'aria-label':title,transform:`translate(${p.x},${p.y})`});g.append(svg('rect',{x:-104,y:-27,width:208,height:54,rx:10,fill:n.id===selected?'#edf5f0':'#fff',stroke:c,'stroke-width':n.id===selected?2.5:1.2}));g.append(svg('circle',{cx:-89,cy:0,r:4,fill:c}));g.append(svg('text',{x:-76,y:-4,'font-size':13,fill:'#29463b'},title.length>14?title.slice(0,14)+'…':title));g.append(svg('text',{x:-76,y:15,'font-size':10,fill:'#6f8177'},(kinds[n.kind]||n.kind)+(n.pages?.length?' · PDF '+n.pages[0]:'')));g.append(svg('title',{},title));g.onclick=()=>details(n.id);g.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();details(n.id);}};root.append(g);});box.append(root);
  }
  async function load(query='') {
    const version=++requestVersion; $('query').value=query; $('status').textContent='正在查询…';
    const params=new URLSearchParams({q:query,depth:$('depth').value,relation:$('relation').value,limit:'40'});
    try { const response=await fetch('/api/knowledge?'+params);const result=await response.json();if(version!==requestVersion)return;if(!response.ok)throw new Error(result.error||'查询失败');data=result;selected='';
      $('stats').textContent=`${data.report.nodes.toLocaleString()} 个节点 · ${data.report.edges.toLocaleString()} 条来源关系`;
      if($('relation').options.length===1)Object.entries(data.relations).forEach(([v,t])=>{const o=el('option',t);o.value=v;$('relation').append(o);});
      $('heading').textContent=query||'八章教材网络';$('status').textContent=`本次显示 ${data.nodes.length} 个节点、${data.edges.length} 条关系${data.budget.truncated?'；已达显示上限，可展开节点或筛选关系缩小范围。':'。'} 上限40个节点，最多两跳。`;
      const url=new URL(location.href);if(query)url.searchParams.set('q',query);else url.searchParams.delete('q');history.replaceState(null,'',url);
      $('details').replaceChildren(el('h2','查看关联依据'),el('p','点击节点查看关联原文与来源页；选择“展开此节点”继续探索。','muted'));draw();
    } catch(error){if(version===requestVersion){$('status').textContent=error.message;$('canvas').replaceChildren(el('p','暂时无法读取图谱，请检查本机图谱是否已建立。','empty'));}}
  }
  $('search').onsubmit=e=>{e.preventDefault();load($('query').value.trim());};$('overview').onclick=()=>{$('relation').value='';load();};document.querySelectorAll('[data-query]').forEach(b=>b.onclick=()=>load(b.dataset.query));
  window.addEventListener('resize',()=>{if(data)draw();});load(new URL(location.href).searchParams.get('q')||'');
})();
