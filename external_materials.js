const byId = id => document.getElementById(id);
const params = new URLSearchParams(location.search);
const selectedId = params.get('id');
const filters = new URLSearchParams({
  chapter: params.get('chapter') || '',
  status: params.get('status') || 'available',
  q: params.get('q') || '',
  page: params.get('page') || '1'
});

function append(parent, tag, text, className) {
  const element = document.createElement(tag);
  if (text) element.textContent = text;
  if (className) element.className = className;
  parent.append(element);
  return element;
}

function libraryLink(values) {
  const query = new URLSearchParams(filters);
  for (const [key, value] of Object.entries(values)) query.set(key, value);
  return '/660b?' + query;
}

async function read(url) {
  const response = await fetch(url);
  const value = await response.json();
  if (!response.ok) throw new Error(value.error || '读取题库失败');
  return value;
}

function title(question) {
  return `第 ${question.chapter} 章 · 第 ${question.number} 题`;
}

async function showList() {
  const data = await read('/api/660b?' + filters);
  byId('catalog-summary').textContent = `${data.total} 道题 · 待选 ${data.counts.available} 道 · 优先核对 ${data.counts.review} 道 · 已有专项记录 ${data.counts.used} 道`;
  byId('match-count').textContent = `${data.matches} 道匹配 · 第 ${data.page} / ${data.page_count} 页`;
  filters.set('page', data.page);
  for (const question of data.questions) {
    const row = append(byId('question-list'), 'li');
    const link = append(row, 'a', title(question), 'question');
    link.href = libraryLink({id: question.id});
    if (question.id === selectedId) link.setAttribute('aria-current', 'true');
    append(link, 'small', `${question.topic_hint || '主题待核对'} · ${question.status_label}`);
  }
  if (!data.matches) append(byId('question-list'), 'li', '没有匹配的题目。');
  if (data.page > 1) append(byId('pagination'), 'a', '上一页').href = libraryLink({page: data.page - 1});
  if (data.page < data.page_count) append(byId('pagination'), 'a', '下一页').href = libraryLink({page: data.page + 1});
}

async function showQuestion() {
  const detail = byId('question-detail');
  const question = await read('/api/660b/question?' + new URLSearchParams({id: selectedId}));
  detail.replaceChildren();
  append(detail, 'h2', title(question));
  append(detail, 'p', `${question.id} · ${question.status_label} · PDF ${question.pages.join('、')} 页`, 'muted');
  if (question.uses.length) append(detail, 'p', question.uses.join('、'), 'muted');
  append(detail, 'p', ['OCR 题干待核对', ...question.source_checks].join(' · '), 'notice');
  append(detail, 'div', '', 'prose').innerHTML = MathView.prose(question.text);
  const actions = append(detail, 'p', '', 'row');
  if (question.can_prefill) {
    append(actions, 'a', '带入查题', 'action').href = '/problems?' + new URLSearchParams({from660b: question.id});
    append(actions, 'a', '查看该题人工核对页').href = '/benchmark?' + new URLSearchParams({id: question.id});
  }
  for (const page of question.pages) {
    const source = append(detail, 'details');
    append(source, 'summary', `查看原页 · PDF ${page}`);
    const image = append(source, 'img', '', 'source-image');
    image.alt = `660B PDF 第 ${page} 页`;
    source.addEventListener('toggle', () => {
      if (source.open && !image.hasAttribute('src')) image.src = `/api/external-review/image?n=${page}`;
    });
  }
}

for (let chapter = 1; chapter <= 8; chapter++) byId('chapter').add(new Option(`第 ${chapter} 章`, chapter));
byId('chapter').value = filters.get('chapter');
byId('scope').value = filters.get('status');
byId('find').value = filters.get('q');
showList().catch(error => { byId('catalog-summary').textContent = error.message; });
if (selectedId) showQuestion().catch(error => { byId('question-detail').textContent = error.message; });
