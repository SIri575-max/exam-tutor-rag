/* Small, escaped Markdown subset for model answers. Math is protected before parsing. */
(function(root){
 'use strict';
 const escape=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 function render(value,options={}){
  let text=String(value??'').replace(/\r\n?/g,'\n'),prefix='\uE000ANSWER';
  while(text.includes(prefix))prefix+='_';
  const tokens=[],put=(html,block=false)=>{const key=prefix+tokens.length+'\uE001';tokens.push({html,block,key});return key};
  text=text.replace(/^\s*```([^\n`]*)\n([\s\S]*?)^\s*```\s*$/gm,(_,lang,body)=>{
   if(/^(?:latex|tex|math)$/i.test(lang.trim())){
    const latex=body.trim().replace(/^\$\$([\s\S]*)\$\$$/,'$1').replace(/^\\\[([\s\S]*)\\\]$/,'$1');
    return put(root.MathView.formula(latex,true),true);
   }
   return put('<pre><code>'+escape(body.trimEnd())+'</code></pre>',true);
  });
  text=text.replace(/`([^`\n]+)`/g,(_,code)=>put('<code>'+escape(code)+'</code>'));
  text=text.replace(/\$\$([\s\S]+?)\$\$|\\\[([\s\S]+?)\\\]|\\\(([\s\S]+?)\\\)|(?<!\\)\$([^$\n]+?)\$/g,(...args)=>{
   const [,display,bracket,paren,inline]=args,isBlock=display!==undefined||bracket!==undefined;
   const token=put(root.MathView.formula(display??bracket??paren??inline,isBlock),isBlock);
   return isBlock?'\n'+token+'\n':token;
  });
  const evidence=new Map((options.evidence||[]).map(e=>[e.id,e]));
  function inline(s){
   let html=escape(s).replace(/\*\*([^*\n]+)\*\*/g,'<strong>$1</strong>').replace(/__([^_\n]+)__/g,'<strong>$1</strong>');
   html=html.replace(/\[(E\d+)\]/g,(original,id)=>{
    const e=evidence.get(id),page=e?.pages?.find(p=>Number.isInteger(p)&&p>0);
    if(!page)return original;
    const label=escape(id+' · PDF '+page);
    return options.citationStyle==='link'?'<a class="source" href="/library#page='+page+'">'+label+'</a>':'<button class="source" data-page="'+page+'">'+label+'</button>';
   });
   return html;
  }
  const lines=text.split('\n'),html=[];let paragraph=[],list=null,quotes=[];
  const flushParagraph=()=>{if(paragraph.length){html.push('<p>'+paragraph.map(inline).join('<br>')+'</p>');paragraph=[]}};
  const closeList=()=>{if(list){html.push('</'+list+'>');list=null}};
  const flushQuotes=()=>{if(quotes.length){html.push('<blockquote>'+quotes.map(inline).join('<br>')+'</blockquote>');quotes=[]}};
  const flush=()=>{flushParagraph();closeList();flushQuotes()};
  const cells=line=>line.trim().replace(/^\|/,'').replace(/\|$/,'').split(/(?<!\\)\|/).map(s=>s.trim().replace(/\\\|/g,'|'));
  const separator=line=>line.includes('|')&&cells(line).every(c=>/^:?-{3,}:?$/.test(c));
  for(let i=0;i<lines.length;i++){
   const line=lines[i],trim=line.trim();
   if(!trim){flush();continue}
   const block=tokens.find(t=>t.block&&t.key===trim);
   if(block){flush();html.push(block.key);continue}
   const heading=trim.match(/^(#{1,6})\s+(.+?)\s*#*$/);
   if(heading){flush();const level=Math.min(4,Math.max(2,heading[1].length));html.push('<h'+level+'>'+inline(heading[2])+'</h'+level+'>');continue}
   if(/^(?:-{3,}|\*{3,}|_{3,})$/.test(trim)){flush();html.push('<hr>');continue}
   if(i+1<lines.length&&line.includes('|')&&separator(lines[i+1])){
    flush();const header=cells(line);html.push('<div class="answer-table"><table><thead><tr>'+header.map(c=>'<th>'+inline(c)+'</th>').join('')+'</tr></thead><tbody>');i++;
    while(i+1<lines.length&&lines[i+1].includes('|')&&lines[i+1].trim()){
     const row=cells(lines[++i]);html.push('<tr>'+header.map((_,j)=>'<td>'+inline(row[j]||'')+'</td>').join('')+'</tr>');
    }
    html.push('</tbody></table></div>');continue;
   }
   const item=trim.match(/^(?:([-+*])|\d+[.)])\s+(.+)$/);
   if(item){flushParagraph();flushQuotes();const type=item[1]?'ul':'ol';if(list!==type){closeList();html.push('<'+type+'>');list=type}html.push('<li>'+inline(item[2])+'</li>');continue}
   if(trim.startsWith('> ')){flushParagraph();closeList();quotes.push(trim.slice(2));continue}
   closeList();flushQuotes();paragraph.push(line);
  }
  flush();
  return html.join('\n').replace(new RegExp(prefix+'(\\d+)\uE001','g'),(_,i)=>tokens[Number(i)]?.html||'');
 }
 root.AnswerView={render};
 if(typeof module!=='undefined')module.exports=root.AnswerView;
})(typeof window!=='undefined'?window:globalThis);
