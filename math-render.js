/* Local KaTeX rendering. Original OCR strings remain available in the API. */
(function (root) {
  'use strict';
  const cache = new Map();
  const escape = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function register(value) {
    if (!value || typeof value !== 'object') return value;
    if (value._math) for (const [key, spans] of Object.entries(value._math)) {
      const text = value[key];
      if (!cache.has(text) || cache.get(text).length < spans.length) cache.set(text, spans);
    }
    for (const [key, child] of Object.entries(value)) if (key !== '_math') register(child);
    // Bound memory during long browsing sessions.
    while (cache.size > 3000) cache.delete(cache.keys().next().value);
    return value;
  }
  function formula(latex, display = false) {
    try {
      // No external links/images, HTML extensions or persistent user macros.
      if (/\\(?:href|url|includegraphics|html\w*)\b/.test(latex)) throw Error('Unsupported external command');
      return '<span class="math-' + (display ? 'block' : 'inline') + '">' + root.katex.renderToString(latex, {
        displayMode: display, throwOnError: true, trust: false, strict: 'ignore',
        output: 'htmlAndMathml', maxExpand: 1000, maxSize: 12, macros: {}
      }) + '</span>';
    } catch (_) {
      return '<details class="math-fallback"><summary>公式待校对 · 查看识别原文</summary><code>' + escape(latex) + '</code></details>';
    }
  }
  function delimited(text) {
    const pattern = /\$\$([\s\S]+?)\$\$|\\\[([\s\S]+?)\\\]|\\\(([\s\S]+?)\\\)|(?<!\\)\$([^$\n]+?)\$/g;
    let html = '', cursor = 0;
    for (const m of text.matchAll(pattern)) {
      html += escape(text.slice(cursor, m.index)) + formula(m[1] ?? m[2] ?? m[3] ?? m[4], m[1] !== undefined || m[2] !== undefined);
      cursor = m.index + m[0].length;
    }
    return html + escape(text.slice(cursor));
  }
  function table(text) {
    const doc = new DOMParser().parseFromString(text, 'text/html');
    const allowed = new Set(['TABLE','TBODY','THEAD','TFOOT','TR','TD','TH','CAPTION']);
    const clean = n => {
      if (n.nodeType === 3) return delimited(n.textContent);
      if (n.nodeType !== 1 || ['SCRIPT','STYLE','IFRAME','OBJECT'].includes(n.tagName)) return '';
      if (n.tagName === 'EQ') return formula(n.textContent);
      const children = () => Array.from(n.childNodes).map(clean).join('');
      if (!allowed.has(n.tagName)) return children();
      let attrs = '';
      for (const key of ['rowspan','colspan']) {
        const v = n.getAttribute(key);
        if (v && /^[1-9][0-9]?$/.test(v)) attrs += ' ' + key + '="' + v + '"';
      }
      return '<' + n.tagName.toLowerCase() + attrs + '>' + children() + '</' + n.tagName.toLowerCase() + '>';
    };
    return '<div class="math-table-scroll">' + Array.from(doc.body.childNodes).map(clean).join('') + '</div>';
  }
  function prose(value) {
    const text = String(value ?? '');
    const delimiters = Array.from(text.matchAll(/\$\$[\s\S]+?\$\$|\\\[[\s\S]+?\\\]|\\\([\s\S]+?\\\)|(?<!\\)\$[^$\n]+?\$/g));
    const spans = (cache.get(text) || []).filter(s => !delimiters.some(m => s.start < m.index + m[0].length && s.end > m.index));
    const chunks = []; let cursor = 0;
    for (const match of text.matchAll(/<table[\s\S]*?<\/table>/gi)) {
      chunks.push([cursor, match.index, false], [match.index, match.index + match[0].length, true]);
      cursor = match.index + match[0].length;
    }
    chunks.push([cursor, text.length, false]);
    return chunks.map(([start, end, isTable]) => {
      if (isTable) return table(text.slice(start, end));
      let html = '', at = start;
      for (const s of spans) if (s.start >= start && s.end <= end && s.start >= at) {
        html += delimited(text.slice(at, s.start)) + formula(text.slice(s.start, s.end), s.display);
        at = s.end;
      }
      return html + delimited(text.slice(at, end));
    }).join('');
  }
  function segments(value, type = '') {
    if (Array.isArray(value)) return value.map(v => segments(v)).join('');
    if (typeof value === 'string') return type.startsWith('equation') ? formula(value, type !== 'equation_inline') : delimited(value);
    if (!value || typeof value !== 'object') return '';
    return value.type === 'table_body' ? table(value.content) : segments(value.content, value.type || '');
  }
  root.MathView = {register, prose, table, segments, formula};
  if (typeof module !== 'undefined') module.exports = root.MathView;
})(typeof window !== 'undefined' ? window : globalThis);
