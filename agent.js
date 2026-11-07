const byId = id => document.getElementById(id);

function append(parent, tag, text, className) {
  const item = document.createElement(tag);
  if (text) item.textContent = text;
  if (className) item.className = className;
  parent.append(item);
  return item;
}

function pageLinks(parent, pages) {
  const links = append(parent, 'div', '', 'row');
  for (const page of pages) {
    const link = append(links, 'a', `原页 PDF ${page}`);
    link.href = `/book-page/${page}.png`;
    link.target = '_blank';
    link.rel = 'noopener';
  }
}

function showGraph(parent, topics, paths) {
  const section = append(parent, 'section', '', 'card');
  append(section, 'h2', '知识图谱');
  const selectors = append(section, 'div', '', 'row');
  const graph = append(section, 'div', '', 'graph');
  const buttons = [];
  const categories = [['教材条目', path => path.relation === 'contains_source_unit'],
    ['例题', path => path.node.kind === 'example'], ['课后题', path => path.node.kind === 'exercise']];

  function select(topic) {
    buttons.forEach(([id, button]) => button.setAttribute('aria-pressed', String(id === topic.id)));
    graph.replaceChildren();
    append(graph, 'h3', topic.label, 'graph-topic');
    const branches = append(graph, 'div', '', 'graph-branches');
    const details = append(graph, 'div', '选择节点查看关系和原页。', 'notice');
    for (const [label, accepts] of categories) {
      const branch = append(branches, 'div', '', 'graph-branch');
      append(branch, 'h3', label);
      const related = paths.filter(path => path.topic_id === topic.id && accepts(path));
      if (!related.length) append(branch, 'p', '当前主题缺少该类路径', 'muted small');
      for (const path of related) {
        const button = append(branch, 'button', path.node.label, 'graph-node');
        button.addEventListener('click', () => {
          details.replaceChildren();
          append(details, 'strong', path.node.label);
          append(details, 'p', `关系依据：${path.relation_label}`, 'muted small');
          pageLinks(details, [...new Set([...path.node.pages, ...path.source_pages])]);
        });
      }
    }
  }

  for (const topic of topics) {
    const button = append(selectors, 'button', topic.label);
    buttons.push([topic.id, button]);
    button.addEventListener('click', () => select(topic));
  }
  select(topics.find(topic => paths.some(path => path.topic_id === topic.id)) || topics[0]);
}

function showResult(data) {
  const results = byId('results');
  const summary = append(results, 'section', '', 'card');
  append(summary, 'h2', data.intent_label);
  append(summary, 'p', data.decision.message, 'notice');
  for (const detail of data.clarifications || []) append(summary, 'p', detail, 'muted');
  if (data.calculation) {
    append(summary, 'p', `提交 ${data.calculation.submitted} · 精确结果 ${data.calculation.expected}`);
    append(summary, 'p', data.calculation.rule, 'muted');
  }
  if (data.paths?.length) showGraph(results, data.topics, data.paths);
  else if (data.topics?.length) append(summary, 'p', '考点线索 · ' + data.topics.map(topic => topic.label).join('、'), 'muted');
  if (data.teaching?.used) {
    const teaching = append(results, 'section', '', 'card');
    append(teaching, 'h2', '讲解提示');
    append(teaching, 'div', '', 'prose').innerHTML = AnswerView.render(data.teaching.text);
  }
  if (data.evidence?.length) {
    const section = append(results, 'section', '', 'card');
    append(section, 'h2', '讲解依据');
    for (const row of data.evidence) {
      append(section, 'p', `${row.id} · ${row.title}`);
      pageLinks(section, row.pages);
    }
  }
  if (data.recommendations?.length) {
    const section = append(results, 'section', '', 'card');
    append(section, 'h2', '教材候选题');
    const grid = append(section, 'div', '', 'items');
    for (const row of data.recommendations) {
      const item = append(grid, 'article', '', 'item');
      append(item, 'h3', row.label);
      append(item, 'p', row.correspondence?.label || '教材候选', 'muted small');
      for (const note of row.correspondence?.differences || []) append(item, 'p', note, 'muted small');
      const detail = append(item, 'details');
      append(detail, 'summary', '查看题干');
      append(detail, 'p', '', 'prose').innerHTML = MathView.prose(row.question_text);
      pageLinks(item, row.pages);
    }
  }
}

byId('review-example').onclick = () => {
  byId('intent').value = 'auto';
  byId('question').value = '复习最大似然估计';
  byId('answer').value = '';
};
byId('check-example').onclick = () => {
  byId('intent').value = 'auto';
  byId('question').value = '独立掷3颗公平6面骰子，求最大点数恰好等于5的概率';
  byId('answer').value = '61/216';
};
byId('agent-form').onsubmit = async event => {
  event.preventDefault();
  byId('run').disabled = true;
  byId('results').replaceChildren();
  byId('trace').replaceChildren();
  byId('status').textContent = '正在处理…';
  byId('status').className = 'muted';
  const request = {question: byId('question').value, intent: byId('intent').value,
    answer: byId('answer').value, allow_generation: byId('allow-generation').checked};
  byId('allow-generation').checked = false;
  try {
    const response = await fetch('/api/agent', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(request)});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || '处理未完成');
    MathView.register(data);
    showResult(data);
    byId('status').textContent = '本轮处理完成';
    for (const step of data.trace) append(byId('trace'), 'li', `${step.step} · ${step.detail}`);
  } catch (error) {
    byId('status').textContent = error.message;
    byId('status').className = 'error';
  } finally {
    byId('run').disabled = false;
  }
};
