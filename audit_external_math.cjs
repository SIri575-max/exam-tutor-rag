/* Syntax-only audit. Valid LaTeX can still be a wrongly recognized formula. */
'use strict';
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const katex=require('./assets/katex/katex.min.js');
const base=path.join(__dirname,'data/private/660b-evaluation');
if (process.argv.length !== 2 && process.argv.length !== 4) {
  throw new Error('Provide both the input JSONL and the output report path');
}
const dataset=process.argv[2] || path.join(base,'dataset/questions.jsonl');
const reportPath=process.argv[3] || path.join(base,'dataset/math-syntax-audit.json');
const raw=fs.readFileSync(dataset);
const questions=raw.toString('utf8').trim().split(/\r?\n/).filter(Boolean).map(JSON.parse);
let total=0,passed=0;const failures=[];
for(const q of questions){
  const pattern=/\$\$([\s\S]+?)\$\$|\\\[([\s\S]+?)\\\]|\\\(([\s\S]+?)\\\)|(?<!\\)\$([^$\n]+?)\$/g;
  for(const m of q.text.matchAll(pattern)){
    total++;const latex=m[1]??m[2]??m[3]??m[4];
    try{
      if(/\\(?:href|url|includegraphics|html\w*)\b/.test(latex))throw new Error('Unsupported external command');
      katex.renderToString(latex,{throwOnError:true,trust:false,strict:'ignore',maxExpand:1000,maxSize:12});passed++;
    }catch(e){failures.push({case_id:q.id,pages:q.pages,text_offset:m.index,latex,error:String(e.message).slice(0,400)});}
  }
}
const report={questions:questions.length,formulas_detected:total,syntax_passed:passed,syntax_failed:total-passed,
  dataset_sha256:crypto.createHash('sha256').update(raw).digest('hex'),failures,
  boundary:'Delimiter-detected LaTeX compilation only. Does not check missing formulas, OCR symbol correctness, mathematical equivalence or solutions.'};
fs.writeFileSync(reportPath,JSON.stringify(report,null,2)+'\n','utf8');
console.log(JSON.stringify({questions:questions.length,formulas_detected:total,syntax_passed:passed,syntax_failed:total-passed}));
