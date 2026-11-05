"""Readable, explicitly planned source tree; not a live approved knowledge graph."""
from html import escape


def render(plan):
    nodes=plan['nodes'];by_id={n['id']:n for n in nodes};children={}
    for e in plan['edges']:children.setdefault(e['from'],[]).append(by_id[e['to']])
    columns=[]
    for branch in children['syllabus-root']:
        body=''
        for topic in children[branch['id']]:
            detail=''.join('<li>'+escape(n['label'])+'</li>' for n in children.get(topic['id'],[]))
            anchors='；'.join('<a href="/library#page='+str(a['pdf_page'])+'">'+escape(a['section']+' '+a['title'])+'</a>' for a in topic['candidate_book_sections'])
            body+='<details><summary>'+str(topic['source_number'])+'. '+escape(topic['label'])+'</summary><p class="muted">原图标注：'+escape(topic['source_priority_annotation'])+'</p><ul>'+detail+'</ul><p>教材候选位置：'+(anchors or '待补充其他资料映射')+'</p><p class="muted">位置与关联待审核，不代表该节点已完整覆盖。</p></details>'
        columns.append('<section class="card"><h2>'+escape(branch['label'])+'</h2>'+body+'</section>')
    return '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>考纲知识网络 · 后续计划</title>
<style>body{margin:0;background:#f4f7f6;color:#203a46;font:15px/1.8 'Segoe UI','Microsoft YaHei',sans-serif}main{max-width:1200px;margin:auto;padding:25px}a,summary{color:#17675d}nav{display:flex;gap:20px;flex-wrap:wrap;border-bottom:1px solid #dce5e6;padding-bottom:15px}h1{font-size:28px}.muted{color:#6b7d84;font-size:13px}.card{background:white;border:1px solid #dce5e6;border-radius:12px;padding:22px;margin:18px 0}.grid{display:grid;grid-template-columns:1fr 1fr;gap:20px}.notice{padding:12px 15px;border-left:3px solid #d0aa50;background:#fff9eb}details{border-top:1px solid #dce5e6;padding:10px 0}summary{cursor:pointer}img{max-width:100%}@media(max-width:750px){.grid{grid-template-columns:1fr}main{padding:15px}}</style>
<main><nav><strong>考纲知识网络 / 后续计划</strong><a href="/validation">返回20题验证</a><a href="/problems">题目检索</a></nav><h1>按考纲组织知识，再连接教材与练习。</h1><p>已按你提供的思维导图整理32个主节点、134个子项。下方可以展开查看，并跳转教材候选位置。</p><p class="notice">这是后续建设的结构草稿。原图的层级和重点标注予以保留；转写、教材映射、考查与先修关系均需审核。</p><section class="card"><h2>后续实施顺序</h2><ol><li>核对考纲节点与层级。</li><li>对齐教材定义、例题、课后题与讲义页，补录适用条件和易错点。</li><li>审核考查、先修、同类题等关系，保留对应出处。</li><li>补充时间序列、多元统计等资料映射，再用于导航与自适应检索。</li></ol></section><div class="grid">'''+''.join(columns)+'''</div><details class="card"><summary>对照你提供的原始网络图</summary><p><a href="/syllabus-image.png" target="_blank">单独打开原图</a></p><img src="/syllabus-image.png" alt="用户提供的北师考纲思维导图"></details></main></html>'''
