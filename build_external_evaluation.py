"""Extract auditable external stems; quarantine answers and unreviewed relevance labels."""
import argparse
import collections
from datetime import datetime, timezone, timedelta
import hashlib
import html
import json
from pathlib import Path
import re
import shutil
import subprocess

from external_question_bank import BASE, ROOT, write_json
from sync_sources import bundled_tool

# Visually verified chapter openings in this specific scan; never infer printed-page offsets.
CHAPTER_STARTS = {1: 6, 2: 16, 3: 26, 4: 38, 5: 43, 6: 54, 7: 71, 8: 82}
ANSWER_START = 88
QUESTION = re.compile(r'(?<!\d)(\d{1,3})\s*[.．、,，。]\s*·?\s*[（(][^\n()（）]{0,40}?([1-5])\s*星[^\n()（）]{0,40}[）)]')
HEADING = re.compile(r'^\s*知识点[一二三四五六七八九十]+\s*[:：]')
SKIP = {'header', 'footer', 'page_number', 'image'}


def chapter_at(page):
    return max((c for c, p in CHAPTER_STARTS.items() if p <= page), default=None)


def extract_questions(pages, overrides=None):
    overrides = overrides or {}
    result = []; current = None; topic = ''; previous_page = None
    def flush(complete=True):
        nonlocal current
        if current:
            current['text'] = '\n\n'.join(p['text'] for p in current['spans']).strip()
            current['text_sha256'] = hashlib.sha256(current['text'].encode()).hexdigest()
            current['pages'] = sorted({p['pdf_page'] for p in current['spans']})
            current['boundary_status'] = 'candidate_complete' if complete else 'missing_page_or_next_boundary'
            current['requires_figure_review'] = bool(current.get('visual_assets'))
            result.append(current); current = None
    for page in sorted(pages, key=lambda r: r['pdf_page']):
        p = page['pdf_page']
        if p < 6 or p >= ANSWER_START: continue
        chapter = chapter_at(p)
        if previous_page and (p != previous_page + 1 or (current and chapter != current['chapter'])):
            flush(complete=p == previous_page + 1)
        previous_page = p
        for index, block in enumerate(page['blocks']):
            if block['type']=='image' and current:
                current.setdefault('visual_assets',[]).append({'pdf_page':p,'block':index,'bbox':block['bbox'],
                                                               'status':'image_semantics_not_transcribed'})
            if block['type'] in SKIP: continue
            text = block['text'].strip()
            if not text: continue
            if HEADING.match(text):
                flush(); topic = text; continue
            if re.match(r'^第[一二三四五六七八]章', text):
                flush(); topic = ''; continue
            starts = [{'start':m.start(), 'number':int(m.group(1)), 'stars':int(m.group(2))}
                      for m in QUESTION.finditer(text)]
            override = overrides.get((p,index))
            if override:
                if hashlib.sha256(text.encode()).hexdigest() != override['block_text_sha256']:
                    raise ValueError('Stale manually reviewed segmentation boundary')
                starts = override['starts']
            offsets = [m['start'] for m in starts] + [len(text)]
            if starts and starts[0]['start'] > 0 and current:
                prefix = text[:starts[0]['start']].strip()
                if prefix: current['spans'].append({'pdf_page': p, 'block': index, 'start': 0,
                                                   'end': starts[0]['start'], 'bbox': block['bbox'], 'text': prefix})
            for j, match in enumerate(starts):
                flush()
                number = match['number']
                current = {'id': f'660b-c{chapter}-q{number:03}', 'chapter': chapter, 'number': number,
                           'difficulty_stars': match['stars'], 'topic_hint': topic,
                           'boundary_review': override.get('review') if override else None,
                           'review_status': 'ocr_and_boundary_pending_review', 'searchable': False,
                           'source_sha256': page['source_sha256'], 'spans': []}
                current['spans'].append({'pdf_page': p, 'block': index, 'start': match['start'],
                                         'end': offsets[j+1], 'bbox': block['bbox'],
                                         'text': text[match['start']:offsets[j+1]].strip()})
            if not starts and current:
                current['spans'].append({'pdf_page': p, 'block': index, 'start': 0, 'end': len(text),
                                         'bbox': block['bbox'], 'text': text})
    flush(complete=previous_page == ANSWER_START - 1)
    return result


def query_text(item):
    # Hide source/number/star/topic/school labels. No answer or relevance labels enter retrieval.
    text = QUESTION.sub('', item['text'], count=1).strip()
    if item.get('boundary_review'):
        text = re.sub(r'^\d{1,3}\s*[.．、,，。]\s*', '', text)
        text = re.sub(r'^[（(]\s*[1-5]\s*星\s*[）)]?\s*', '', text)
    text = re.sub(r'[\[【][^\]】]*(?:19|20)\d{2}[^\]】]*[\]】]', '', text)
    return text.strip()


def lexical_terms(text):
    cleaned = re.sub(r'\\[a-zA-Z]+|\s+|[\W_]', '', text.lower())
    return {cleaned[i:i+3] for i in range(max(0, len(cleaned)-2))}


def overlap_candidates(items, records):
    source = {k: lexical_terms(r['question_text']) for k, r in records.items()}
    inverted = collections.defaultdict(set)
    for key, terms in source.items():
        for term in terms: inverted[term].add(key)
    for item in items:
        terms = lexical_terms(query_text(item)); counts = collections.Counter()
        for term in terms: counts.update(inverted.get(term, []))
        matches = []
        for key, common in counts.most_common(80):
            score = common / max(1, len(terms | source[key]))
            matches.append({'record_id': key, 'jaccard': round(score, 4),
                            'label': records[key]['label'], 'pages': records[key]['pages']})
        item['overlap_candidates'] = sorted(matches, key=lambda r: (-r['jaccard'], r['record_id']))[:3]
        item['overlap_status'] = 'possible_near_duplicate_pending_review' if matches and max(m['jaccard'] for m in matches) >= .45 else 'novelty_unreviewed'
        # Split stays pending: a nominal hash before duplicate review would create a false held-out test.
        item['family_id'] = None; item['split'] = 'quarantine_pending_ocr_and_family_review'
        item['relevance_labels'] = []; item['answer_correctness_label'] = None
    return items


def audit(items, completed_pages):
    report = {}
    for chapter in range(1, 9):
        rows = [r for r in items if r['chapter'] == chapter]
        numbers = [r['number'] for r in rows]; counts = collections.Counter(numbers)
        report[str(chapter)] = {'candidates': len(rows), 'max_detected_number': max(numbers, default=0),
                               'missing_numbers_through_max': sorted(set(range(1, max(numbers, default=0)+1))-set(numbers)),
                               'duplicate_numbers': [k for k, n in counts.items() if n > 1],
                               'figure_review_candidates': [r['id'] for r in rows if r.get('requires_figure_review')],
                               'incomplete_boundaries': [r['id'] for r in rows if r['boundary_status'] != 'candidate_complete']}
    return {'completed_ocr_pages': len(completed_pages), 'total_source_pages': 146,
            'question_page_range': [6, 87], 'answer_page_range': [88, 146],
            'question_candidates': len(items), 'reviewed_questions': 0,
            'chapters': report, 'mathematical_accuracy': None, 'retrieval_recall': None,
            'boundary': 'Candidate counts are not verified completeness or teaching performance.'}


def review_html(items, report):
    sections = []
    for item in items:
        pages = ' '.join(f'<a href="../pages/pdf-{p:03}.png" target="_blank">PDF {p}</a>' for p in item['pages'])
        sections.append(f'<article id="{item["id"]}"><h2>{item["id"]} · {html.escape(item["topic_hint"])}</h2>'
                        f'<p>{pages} | {item["boundary_status"]} | {item["overlap_status"]}</p>'
                        f'<div class="compiled">{html.escape(item["text"])}</div>'
                        f'<details><summary>查看原始OCR代码</summary><pre>{html.escape(item["text"])}</pre></details>'
                        '<p>核对项：公式/数字/上下标；题干是否跨页；与教材同题或变式；参考答案是否正确。</p></article>')
    return ('<!doctype html><html lang="zh"><meta charset="utf-8"><title>660B 外部评测候选审核</title>'
            '<link rel="stylesheet" href="../../../../assets/katex/katex.min.css">'
            '<link rel="stylesheet" href="../../../../math-render.css">'
            '<style>body{max-width:1100px;margin:35px auto;font:17px/1.7 system-ui;background:#f4f6f9;color:#172c42}'
            'article{background:white;padding:25px;margin:20px 0;border-radius:12px}pre{white-space:pre-wrap;font:16px/1.8 system-ui}'
            '.compiled{white-space:pre-wrap;overflow-wrap:anywhere}.math-block{white-space:normal;overflow:auto}'
            'a{color:#176b9b}h2{font-size:20px}</style><h1>660B 外部评测候选审核</h1>'
            f'<p>OCR {report["completed_ocr_pages"]}/146 页，题目候选 {len(items)} 条。尚未教师审核，不代表660道或效果通过。</p>'
            '<p>题干未加入教材向量库；答案仅保存在独立评测区。公式由原始 OCR 编译，编译成功不代表识别正确，点击原页核对。</p>' + ''.join(sections) +
            '<script src="../../../../assets/katex/katex.min.js"></script>'
            '<script src="../../../../math-render.js"></script>'
            '<script>for(const el of document.querySelectorAll(".compiled")){el.innerHTML=MathView.prose(el.textContent);}</script></html>')


def build():
    pages = [json.loads(line) for line in (BASE/'pages.jsonl').read_text(encoding='utf-8').splitlines()]
    override_path=BASE/'segmentation-reviews.json'
    overrides=json.loads(override_path.read_text(encoding='utf-8')) if override_path.exists() else []
    items = extract_questions(pages, {(r['pdf_page'],r['block']):r for r in overrides})
    from exercise_vectors import snapshot, status
    index = status(); overlap_candidates(items, snapshot()[1])
    folder = BASE/'dataset'; folder.mkdir(exist_ok=True)
    (folder/'questions.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False)+'\n' for r in items), encoding='utf-8')
    # Raw answer pages are sealed separately, with provenance and no prompt-generation helper.
    answer_pages = [p for p in pages if p['pdf_page'] >= ANSWER_START]
    (folder/'sealed-answer-pages.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False)+'\n' for r in answer_pages), encoding='utf-8')
    report = audit(items, pages)
    report.update(created_at=datetime.now(timezone(timedelta(hours=8))).isoformat(),
                  collection_sha256=index['collection_sha256'], answer_pages_ocr=len(answer_pages),
                  query_answer_leakage_prevented=True, protocol='evaluation/external_660b_protocol.json')
    write_json(folder/'audit.json', report)
    (folder/'review.html').write_text(review_html(items, report), encoding='utf-8')
    node=Path(shutil.which('node') or bundled_tool('node', 'bin', 'node.exe'))
    if node.exists():
        subprocess.run([str(node),str(ROOT/'audit_external_math.cjs')],check=True,cwd=ROOT,capture_output=True)
    print(json.dumps(report, ensure_ascii=False), flush=True)
    return items, report


if __name__ == '__main__': build()
