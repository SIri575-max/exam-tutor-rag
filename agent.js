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
  if (data.clarification) showClarification(results, data);
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
    append(section, 'h2', '相关教材题');
    for (const [kind, label] of [['example', '教材例题'], ['exercise', '课后题']]) {
      append(section, 'h3', label);
      const grid = append(section, 'div', '', 'items');
      const rows = data.recommendations.filter(row => row.kind === kind);
      if (!rows.length) append(grid, 'p', '这组暂时没有足够相关的候选。', 'muted');
      for (const row of rows) {
        const item = append(grid, 'article', '', 'item');
        append(item, 'strong', row.label);
        append(item, 'p', row.correspondence?.label || '教材候选', 'muted small');
        for (const note of row.correspondence?.differences || []) append(item, 'p', note, 'muted small');
        const detail = append(item, 'details');
        append(detail, 'summary', '查看题干');
        append(detail, 'p', '', 'prose').innerHTML = MathView.prose(row.question_text);
        pageLinks(item, row.pages);
      }
    }
  }
}

const taskKey = 'zhiti.study-task';
let photoJob = '', busy = false, photoBusy = false;

function clearPhoto() {
  photoJob = '';
  byId('photo-file').value = '';
  byId('photo-status').textContent = '';
  byId('photo-clear').hidden = true;
  byId('question').readOnly = false;
}

function fillSample(question, answer = '') {
  clearPhoto();
  byId('intent').value = 'auto';
  byId('question').value = question;
  byId('answer').value = answer;
}

byId('followup-example').onclick = () => fillSample('有一组样本，求参数估计');
byId('review-example').onclick = () => fillSample('复习最大似然估计');
byId('check-example').onclick = () => fillSample('独立掷3颗公平6面骰子，求最大点数恰好等于5的概率', '61/216');
byId('photo-clear').onclick = () => { clearPhoto(); byId('question').value = ''; };
byId('photo-file').onchange = () => {
  if (photoJob) byId('question').value = '';
  photoJob = '';
  byId('question').readOnly = false;
  byId('photo-clear').hidden = !byId('photo-file').files.length;
  byId('photo-status').textContent = '';
};

async function readJSON(response) {
  const data = await response.json();
  if (!response.ok) {
    const error = new Error(data.error || '处理未完成');
    error.status = response.status;
    throw error;
  }
  return data;
}

function syncControls() {
  byId('agent-form').querySelectorAll('button, input[type=file]').forEach(
    control => { control.disabled = busy || photoBusy; });
  document.querySelectorAll('#results form button').forEach(control => { control.disabled = busy || photoBusy; });
}

byId('photo-start').onclick = async () => {
  const file = byId('photo-file').files[0];
  if (!file) { byId('photo-status').textContent = '请先选择一张题图。'; return; }
  photoBusy = true;
  syncControls();
  byId('photo-status').textContent = '正在把题图交给本机 OCR…';
  try {
    let job = await readJSON(await fetch('/api/photo-ocr', {method: 'POST',
      headers: {'Content-Type': file.type}, body: file}));
    for (let attempt = 0; attempt < 250; attempt++) {
      byId('photo-status').textContent = job.message;
      if (job.status === 'failed') throw new Error(job.message);
      if (job.status === 'ready') {
        photoJob = job.job_id;
        byId('question').value = job.result.text;
        byId('question').readOnly = true;
        byId('photo-clear').hidden = false;
        byId('photo-status').textContent = '识别完成。点「开始新任务」，对照原图确认识别稿。';
        return;
      }
      await new Promise(resolve => setTimeout(resolve, 1200));
      job = await readJSON(await fetch('/api/photo-ocr?id=' + encodeURIComponent(job.job_id)));
    }
    throw new Error('识别等待超时，可重新选择单题图。');
  } catch (error) {
    byId('photo-status').textContent = error.message;
  } finally {
    photoBusy = false;
    syncControls();
  }
};

function showClarification(results, data) {
  const form = append(results, 'form', '', 'card');
  append(form, 'h2', '补充信息后继续');
  const prompt = data.clarification;
  for (const note of prompt.reasons) append(form, 'p', note, 'muted small');
  if (data.photo_job && prompt.fields.some(field => field.id === 'question')) {
    const image = append(form, 'img', '', 'preview');
    image.src = '/api/photo-image?id=' + encodeURIComponent(data.photo_job) + '&view=full';
    image.alt = '待确认的题图原稿';
  }
  const fields = new Map();
  for (const field of prompt.fields) {
    const label = append(form, 'label', field.label, 'field');
    const input = append(label, field.id === 'question' ? 'textarea' : 'input');
    input.required = field.required;
    input.maxLength = {question: 3000, answer: 80}[field.id] || 450;
    if (field.id === 'question') {
      input.value = data.question;
      const preview = append(form, 'div', '', 'prose notice');
      function render() { preview.innerHTML = MathView.prose(input.value); }
      input.addEventListener('input', render);
      render();
    }
    fields.set(field.id, input);
  }
  const submit = append(form, 'button', '继续当前题目', 'primary');
  submit.type = 'submit';
  form.onsubmit = event => {
    event.preventDefault();
    const reply = Object.fromEntries([...fields].map(([key, input]) => [key, input.value]));
    sendTask({action: 'resume', task_id: data.task_id, checkpoint: prompt.checkpoint, reply,
      allow_generation: readConsent()});
  };
}

function readConsent() {
  const consent = byId('allow-generation').checked;
  byId('allow-generation').checked = false;
  return consent;
}

function display(data) {
  MathView.register(data);
  byId('results').replaceChildren();
  byId('trace').replaceChildren();
  showResult(data);
  byId('status').textContent = data.clarification ? '进度已保存，等待补充' : '本轮处理完成';
  for (const step of data.trace) append(byId('trace'), 'li', `${step.step} · ${step.detail}`);
}

async function sendTask(request) {
  if (busy || photoBusy) return;
  busy = true;
  syncControls();
  byId('status').textContent = '正在处理…';
  byId('status').className = 'muted';
  try {
    const data = await readJSON(await fetch('/api/agent', {method: 'POST',
      headers: {'Content-Type': 'application/json'}, body: JSON.stringify(request)}));
    sessionStorage.setItem(taskKey, data.task_id);
    clearPhoto();
    byId('question').value = data.question;
    byId('intent').value = data.requested;
    byId('answer').value = data.answer;
    display(data);
  } catch (error) {
    if (request.action === 'get' && error.status === 409) sessionStorage.removeItem(taskKey);
    byId('status').textContent = error.message;
    byId('status').className = 'error';
  } finally {
    busy = false;
    syncControls();
  }
}

byId('agent-form').onsubmit = event => {
  event.preventDefault();
  sendTask({action: 'start', question: byId('question').value, intent: byId('intent').value,
    answer: byId('answer').value, photo_job: photoJob, allow_generation: readConsent()});
};
const previousTask = sessionStorage.getItem(taskKey);
if (previousTask) sendTask({action: 'get', task_id: previousTask});
